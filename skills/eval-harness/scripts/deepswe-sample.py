#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSWE 评测适配器（治理壳，零第三方依赖，AGENTS.md 硬约束 1）。

把 DeepSWE 任务的「clone 仓库 → checkout base_commit → 调 code-task.py 生成
补丁 → Docker 验证 → 台账」串成单命令。

DeepSWE 验证器（tests/test.sh）期望 Docker 容器中：
  /app              目标仓库（已在 base_commit，agent 补丁已应用）
  /tests/test.patch 隐藏测试补丁
  /tests/test.sh    验证器入口
  /logs/artifacts/  产物目录

本适配器编排：
  1. 读 deepswe-tasks.jsonl（步骤 0.5 产出）
  2. 每个任务：clone 目标仓库 → checkout base_commit → 调 code-task.py →
     将 agent 补丁注入 Docker → 跑 test.sh → 读 /logs/verifier/reward.txt
     （reward=1 判 resolved；退出码只表脚本跑完）
  3. stdout 输出一个 JSON 文档（硬约束 2）

宿主 LLM 模式（--host-loop，round-46）：code-task.py 以 CRA_LLM_PROVIDER=host
运行，遇到需要模型回复时写 llm-tasks/*.prompt.md 并以 WAIT_HOST_LLM 退出；
本适配器记为 waiting_host 并 exit 1（不记失败），宿主把动作 JSON 写入同目录
*.response.md 后**原命令重跑**即续跑（clone 幂等、code-task 带续跑参数）。
评测链环境自足（round-46）：语料 CRLF→LF 暂存副本、预建 verifier 目录并清
旧 reward、宿主已有镜像跳过拉取、子模块未初始化时从镜像内置 /app 补齐。

用法示例:
    py deepswe-sample.py --jsonl data/deepswe-tasks.jsonl --out datasets/deepswe-out
    py deepswe-sample.py --jsonl <路径> --out <目录> --limit 5 --lang python
    py deepswe-sample.py --jsonl <路径> --out <目录> --dry-run
    py deepswe-sample.py --jsonl <路径> --out <目录> --no-eval
    py deepswe-sample.py --jsonl <路径> --out <目录> --host-loop --no-eval

退出码: 0 = 全部任务完成（resolved/unresolved 均算完成）；
1 = 存在失败任务（环境/clone/code-task 失败），或 --host-loop 下有任务在
    等宿主回复（waiting_host）；2 = 参数或输入错误。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CODE_TASK = ROOT / "agent" / "code-task.py"
DEFAULT_JSONL = ROOT / "skills" / "eval-harness" / "data" / "deepswe-tasks.jsonl"
DEEP_SWE_REPO = ROOT / "skills" / "eval-harness" / "data" / "deep-swe"

# category → difficulty 映射（DeepSWE 用 category 字段，无显式 difficulty）
DIFF_MAP = {
    "enhancement": "medium",
    "feature_request": "medium",
    "bug": "hard",
    "bugfix": "hard",
    "refactor": "easy",
    "documentation": "easy",
    "test": "easy",
}


def _emit(obj):
    """stdout 只输出一个 JSON 文档（硬约束 2）。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _run(cmd, **kw):
    """subprocess.run 封装，统一编码处理。"""
    kw.setdefault("shell", False)
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, **kw)


def _find_docker():
    """查找 docker 可执行文件。"""
    for name in ("docker", "docker.exe"):
        p = shutil.which(name)
        if p:
            return p
    # Windows Docker Desktop 常见路径
    win = os.environ.get("LOCALAPPDATA", "")
    if win:
        p = Path(win) / "Programs" / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
        if p.is_file():
            return str(p)
    return ""


def _load_tasks(jsonl_path, lang_filter, diff_filter, limit):
    """加载并过滤任务。缺 id 的行视为坏输入（抛出 ValueError）。"""
    tasks = []
    with jsonl_path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            if not t.get("id"):
                raise ValueError("第 %d 行缺 id 字段" % lineno)
            if lang_filter and t.get("language", "").lower() != lang_filter.lower():
                continue
            cat = t.get("category", "unknown")
            diff = DIFF_MAP.get(cat, "medium")
            t["_difficulty"] = diff
            if diff_filter and diff != diff_filter.lower():
                continue
            tasks.append(t)
    if limit:
        tasks = tasks[:limit]
    return tasks


def _clone_repo(repo_url, dest, base_commit):
    """clone 目标仓库并 checkout base_commit。返回 (ok, error)。

    断点续跑：如果 dest 已存在且是有效 git 仓库，直接 fetch+checkout。
    """
    if dest.is_dir() and (dest / ".git").is_dir():
        # 已有仓库，fetch + checkout。fetch 失败但 base_commit 本地已在时
        # 不判死：续跑与离线复现不该被一次网络抖动打断（round-46 实测
        # github.com:443 超时，本地仓库完好却整轮 CLONE_FAIL）。
        r = _run(["git", "fetch", "--all"], cwd=str(dest), timeout=120)
        if r.returncode != 0:
            have = _run(["git", "cat-file", "-e", base_commit + "^{commit}"],
                        cwd=str(dest), timeout=30)
            if have.returncode != 0:
                return False, "git fetch 失败: %s" % (r.stderr or "")[:300]
            print("[deepswe] fetch 失败，但 base_commit 本地已存在，继续离线评测",
                  file=sys.stderr)
    else:
        # clone
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = _run(["git", "clone", "--filter=blob:none", repo_url, str(dest)],
                 timeout=300)
        if r.returncode != 0:
            return False, "git clone 失败: %s" % (r.stderr or "")[:300]
    # checkout base_commit
    r = _run(["git", "checkout", "-f", base_commit], cwd=str(dest), timeout=60)
    if r.returncode != 0:
        return False, "git checkout %s 失败: %s" % (base_commit[:12],
                                                     (r.stderr or "")[:300])
    # clean
    _run(["git", "clean", "-fdx"], cwd=str(dest), timeout=60)
    # 子模块（如 tomlkit 的 tests/toml-test）未初始化时，仓库自带测试
    # 收集直接 FileNotFoundError → baseline 必挂、reward 恒为 0。这里先
    # 初始化；失败如实告警（离线仍可跑，但结论按 baseline 不通过记）。
    r = _run(["git", "submodule", "update", "--init", "--recursive"],
             cwd=str(dest), timeout=180)
    if r.returncode != 0:
        print("[deepswe] 子模块初始化失败（baseline 可能无法通过）: %s"
              % (r.stderr or "")[:200], file=sys.stderr)
    return True, ""


def _run_code_task(repo_path, task, out_dir, rounds=6, allow_probe=True,
                   resume=False, host_loop=False):
    """调 agent/code-task.py 生成补丁。

    返回 (status, patch_path, detail)：
      ok / waiting / failed；waiting 仅 --host-loop 下出现（WAIT_HOST_LLM）。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    venv_py = str(ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(venv_py).is_file():
        venv_py = sys.executable
    if resume:
        # --resume 从 task-meta.json 续跑；repo/task/授权态都取自持久化状态
        cmd = [venv_py, str(CODE_TASK), "--out", str(out_dir),
               "--rounds", str(rounds), "--resume"]
    else:
        cmd = [venv_py, str(CODE_TASK),
               "--repo", str(repo_path),
               "--task", task.get("task", task.get("title", "")),
               "--out", str(out_dir),
               "--rounds", str(rounds)]
        if allow_probe:
            cmd.append("--allow-probe")
    env = None
    if host_loop:
        env = os.environ.copy()
        env["CRA_LLM_PROVIDER"] = "host"
    r = _run(cmd, timeout=600, env=env)
    patch_path = out_dir / "edits.patch"
    payload = {}
    try:
        payload = json.loads(r.stdout or "")
    except ValueError:
        payload = {}
    if host_loop and isinstance(payload, dict) \
            and payload.get("state") == "WAIT_HOST_LLM":
        return "waiting", patch_path, {
            "llm_task": payload.get("llm_task", ""),
            "llm_response": payload.get("llm_response", ""),
            "out_dir": payload.get("out_dir", str(out_dir)),
        }
    if r.returncode != 0:
        return "failed", patch_path, "code-task.py exit %d: %s" % (
            r.returncode, (r.stderr or "")[:300])
    if not patch_path.is_file() or not patch_path.read_text(
            encoding="utf-8", errors="replace").strip():
        return "failed", patch_path, "code-task.py 未产出有效补丁"
    return "ok", patch_path, ""


def _docker_ref(docker_image, registry_mirror):
    """按镜像源前缀拼出实际拉取/运行引用。

    registry_mirror 由人工先经 scripts/docker-mirror-probe.py 实测可达后传入
    （AGENTS.md 硬约束 8：国内镜像优先，慢即判死）。空串 = 原注册表直连。
    """
    mirror = (registry_mirror or "").strip().rstrip("/")
    if not mirror:
        return docker_image
    return "%s/%s" % (mirror, docker_image.lstrip("/"))


def _to_docker_path(win_path):
    """Windows 路径 → Docker Desktop 挂载路径（C:\\x → //c/x）。"""
    norm = win_path.replace("\\", "/")
    if len(norm) >= 3 and norm[1] == ":" and norm[2] == "/":
        return "//%s/%s" % (norm[0].lower(), norm[3:])
    return norm


def _seed_submodules_from_image(docker_bin, image, repo_path):
    """子模块未初始化时，从评测镜像内置的 /app 克隆补齐；返回是否全就绪。

    镜像构建时已 checkout 同一 base_commit 并初始化子模块；GitHub 不可达
    或宿主仓库缺子模块时，这是不篡改语料的补齐途径。round-46 实踩：未
    初始化的 tests/toml-test 让 baseline 收集失败，任何补丁都拿不到
    reward=1。克隆后校验 HEAD 与钉定 sha 一致，不一致即判失败。
    """
    if not docker_bin:
        return False
    r = _run(["git", "submodule", "status"], cwd=str(repo_path), timeout=60)
    missing = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("-"):
            parts = line[1:].split()
            if len(parts) >= 2:
                missing.append((parts[1], parts[0]))
    if not missing:
        return True
    mount = _to_docker_path(str(repo_path.resolve()))
    all_ok = True
    for path, sha in missing:
        cmd = [
            docker_bin, "run", "--rm",
            "-v", "%s:/work" % mount,
            "-e", "SUBPATH=%s" % path,
            "-e", "WANTSHA=%s" % sha,
            image, "bash", "-lc",
            'git clone -q "/app/$SUBPATH" "/work/$SUBPATH" && '
            'test "$(git -C "/work/$SUBPATH" rev-parse HEAD)" = "$WANTSHA"',
        ]
        run = _run(cmd, timeout=300)
        if run.returncode != 0:
            all_ok = False
            print("[deepswe] 子模块补齐失败: %s: %s"
                  % (path, (run.stderr or run.stdout or "")[:200]),
                  file=sys.stderr)
        else:
            print("[deepswe] 已从镜像补齐子模块: %s (%s)"
                  % (path, sha[:12]), file=sys.stderr)
    return all_ok


def _stage_tests(tests_dir, stage_dir):
    """把语料 tests/ 复制到 stage_dir 并做 CRLF→LF 归一化，返回暂存目录。

    语料不入库，Windows 检出时常带 CRLF；直接挂语料目录进 Linux 容器会让
    `bash /tests/test.sh` 报 `$'\\r': command not found`（round-46 实踩：
    verifier exit=2 看似评测失败，实为语料装载问题）。这里挂暂存副本，
    含 NUL 的二进制文件原样保留，其余文本只把 CRLF 换成 LF；语料本身不动。
    """
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    shutil.copytree(tests_dir, stage_dir)
    normalized = 0
    for path in stage_dir.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\r\n" not in data or b"\x00" in data:
            continue
        path.write_bytes(data.replace(b"\r\n", b"\n"))
        normalized += 1
    if normalized:
        print("[deepswe] tests 暂存归一化 CRLF→LF: %d 个文件" % normalized,
              file=sys.stderr)
    return stage_dir


# ---------------------------------------------------------------- 补丁完整性
# 动机（2026-10-28 行业对标）：SWE 类评测存在「测试黑客」面——Berkeley RDI
# 实测仅 10 行 conftest.py 钩子（pytest_collection_modifyitems 强制标 passed）
# 就能让任意策略刷分。我们自己的评测链此前只认 reward.txt，不检查补丁改了
# 什么，等于把「补丁是否只改产品代码」交给运气。这里在读 reward 之前先做
# patch provenance：触碰测试基础设施/pytest 配置/解释器启动钩子的补丁不参加
# resolved 计数（status=integrity_flagged），新增测试文件只记 warning。
_TEST_DIR_PARTS = {"tests", "test", "__tests__"}
_INTERPRETER_HOOK_NAMES = {"conftest.py", "sitecustomize.py", "usercustomize.py"}
_PYTEST_CONFIG_NAMES = {"pytest.ini", "tox.ini", "setup.cfg"}
_PYTEST_MARKERS = ("[tool.pytest", "[pytest", "addopts", "python_files",
                   "testpaths", "pytest11", "python_functions")
_DEP_MANIFEST_RE_PARTS = ("requirements", "pyproject.toml", "setup.py",
                          "package.json", "go.mod", "Cargo.toml", "pom.xml")


def _is_test_path(path):
    """判定补丁里的路径是否属测试面（目录、文件名、conftest 三类形态）。"""
    parts = path.replace("\\", "/").split("/")
    base = parts[-1]
    if base == "conftest.py":
        return True
    if any(p in _TEST_DIR_PARTS for p in parts[:-1]):
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith(("_test.py", ".spec.js", ".spec.ts", ".test.js", ".test.ts")):
        return True
    return False


def _patch_integrity(patch_path):
    """校验补丁是否触碰评测完整性红线 → {ok, critical, warnings, ...}。

    critical（一票否决，不参加 resolved）：改/删既有测试、conftest.py、
    sitecustomize/usercustomize/*.pth、pytest 配置（pytest.ini/tox.ini/
    setup.cfg 或 pyproject.toml 的 pytest 段）。
    warnings（记录不否决）：新增测试文件、改 CI、改依赖清单。

    只看补丁文本，不执行补丁里任何代码；路径取 diff 头的 a/ b/ 段，
    不依赖行首正则（硬约束 6：+/- 前缀会让 ^ 锚定失配）。
    """
    text = Path(patch_path).read_text(encoding="utf-8", errors="replace")
    files = []
    cur = None
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            bits = raw.split()
            a_raw = bits[2] if len(bits) > 2 else ""
            b_raw = bits[3] if len(bits) > 3 else ""
            a_path = a_raw[1:-1] if a_raw.startswith('"') and a_raw.endswith('"') else a_raw
            b_path = b_raw[1:-1] if b_raw.startswith('"') and b_raw.endswith('"') else b_raw
            a_path = a_path[2:] if a_path.startswith("a/") else ""
            b_path = b_path[2:] if b_path.startswith("b/") else ""
            cur = {"path": b_path or a_path, "new": False, "deleted": False,
                   "added": 0, "removed": 0,
                   "added_lines": [], "removed_lines": []}
            files.append(cur)
            continue
        if cur is None:
            continue
        if raw.startswith("new file mode"):
            cur["new"] = True
        elif raw.startswith("deleted file mode"):
            cur["deleted"] = True
        elif raw.startswith("+++ "):
            p = raw[4:].strip().split("\t")[0]
            if p.startswith('"') and p.endswith('"'):
                p = p[1:-1]  # 含空格/特殊字符的路径会被 git 加引号
            if p == "/dev/null":
                cur["deleted"] = True
            elif p.startswith("b/"):
                cur["path"] = p[2:]
        elif raw.startswith("--- "):
            if raw[4:].strip().split("\t")[0].strip('"') == "/dev/null":
                cur["new"] = True
        elif raw.startswith("+"):
            cur["added"] += 1
            cur["added_lines"].append(raw[1:])
        elif raw.startswith("-"):
            cur["removed"] += 1
            cur["removed_lines"].append(raw[1:])

    critical, warnings = [], []
    for item in files:
        path = item["path"].replace("\\", "/")
        base = path.rsplit("/", 1)[-1]
        if base in _INTERPRETER_HOOK_NAMES or base.endswith(".pth"):
            critical.append({"code": "interpreter_or_pytest_hook",
                             "path": path,
                             "detail": "解释器启动钩子/测试根钩子可劫持判分"})
        elif base in _PYTEST_CONFIG_NAMES:
            critical.append({"code": "pytest_config",
                             "path": path,
                             "detail": "pytest 配置可改变收集与判定口径"})
        elif base == "pyproject.toml" and any(
                marker in "\n".join(item["added_lines"] + item["removed_lines"])
                for marker in _PYTEST_MARKERS):
            critical.append({"code": "pytest_config",
                             "path": path,
                             "detail": "pyproject 的 pytest 段被改动"})
        elif _is_test_path(path):
            if item["new"] and not item["deleted"]:
                warnings.append({"code": "new_test_file", "path": path,
                                 "detail": "新增测试文件（记录，不否决）"})
            else:
                critical.append({"code": "test_file_modified",
                                 "path": path,
                                 "detail": "改/删既有测试属评测完整性问题"})
        elif ".github/workflows" in path or ".gitlab-ci" in path \
                or base == "Jenkinsfile":
            warnings.append({"code": "ci_config", "path": path,
                             "detail": "CI 配置改动（记录，不否决）"})
        elif any(part in path for part in _DEP_MANIFEST_RE_PARTS):
            warnings.append({"code": "dependency_manifest", "path": path,
                             "detail": "依赖清单改动（记录，不否决）"})

    return {
        "ok": not critical,
        "critical": critical,
        "warnings": warnings,
        "files": len(files),
        "added_lines": sum(i["added"] for i in files),
        "removed_lines": sum(i["removed"] for i in files),
        "touched": [i["path"] for i in files][:50],
    }


_HUNK_HEADER_RE = re.compile(
    r"^@@ -(?P<old>\d+)(?:,(?P<oldn>\d+))? "
    r"\+(?P<new>\d+)(?:,(?P<newn>\d+))? @@")


def _patch_well_formed(patch_path):
    """unified diff 结构自检：hunk 头声明的旧/新行数须与实际行数一致。

    截断补丁（编码循环中途写盘、摘抄丢尾）在 `git apply` 时必然失败，
    但对只读文件头与增删行的完整性检查不可见——round-48 合并率抽检在
    django-11019 上实踩：补丁尾部缺失仍通过完整性检查进入评测，最终只能
    记 F2P_MISSED，与「修错了」混为一谈。本函数只做结构判定，不执行补丁
    内容；hunk 头以 @@ 开头（git 语法固定），正文不依赖行首锚定。
    """
    text = Path(patch_path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    issues = []
    hunks = 0
    i = 0
    while i < len(lines):
        m = _HUNK_HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        hunks += 1
        old_need = int(m.group("oldn") or 1)
        new_need = int(m.group("newn") or 1)
        old_seen = new_seen = 0
        i += 1
        while i < len(lines) and (old_seen < old_need or new_seen < new_need):
            raw = lines[i]
            if raw.startswith("\\"):
                i += 1
                continue
            if not raw:
                issues.append("hunk 内出现空行（截断或换行丢失）")
                break
            tag = raw[0]
            if tag == " ":
                old_seen += 1
                new_seen += 1
            elif tag == "-":
                old_seen += 1
            elif tag == "+":
                new_seen += 1
            else:
                issues.append("hunk 内出现非 diff 行（截断或结构损坏）")
                break
            i += 1
        if issues:
            break
        if old_seen != old_need or new_seen != new_need:
            issues.append(
                "hunk 行数不符：声明 -%d,+%d，实见 -%d,+%d（截断补丁）"
                % (old_need, new_need, old_seen, new_seen))
            break
    if not issues and hunks == 0:
        issues.append("补丁无任何 hunk（无法应用）")
    return {"ok": not issues, "hunks": hunks, "issues": issues[:10]}


def _apply_structural_gate(result, patch_path):
    """把结构自检结果写进 result；结构损坏返回 False（调用方记失败并跳过评测）。

    结构损坏与「修错了」是两类问题：前者是坏产物（编码循环中途写盘/摘抄丢尾），
    后者是语义未对齐。归因分开才不会让截断补丁伪造成 F2P_MISSED；也不受
    --allow-test-edits 影响——豁免是给测试编辑策略的，不是给坏补丁的。
    """
    well_formed = _patch_well_formed(patch_path)
    result["patch_well_formed"] = well_formed
    if well_formed["ok"]:
        return True
    result["status"] = "malformed_patch"
    result["error"] = "补丁结构损坏: %s" % "; ".join(
        well_formed.get("issues", [])[:3])
    return False


def _code_task_stats(out_dir):
    """从 code-task 产物读取轮数/编辑数/测试状态（成本与效率指标）。"""
    for name in ("task-manifest.json", "task-meta.json"):
        path = Path(out_dir) / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stats = {}
        for src, dst in (("rounds", "rounds"), ("round", "rounds"),
                         ("edits", "edits"), ("edits_applied", "edits"),
                         ("tests", "tests"), ("elapsed_sec", "elapsed_sec"),
                         ("patch_validation", None)):
            if dst and src in data and dst not in stats:
                stats[dst] = data[src]
        return stats
    return {}


def _verdict(exit_code, reward):
    """按「退出码 + reward」判分，返回 (resolved, reason)。

    resolved 仅当 exit 0 且 reward=1；退出码 8 表示补丁注入失败（非
    环境失败，也非 resolved）；其余非 0 退出码按语料脚本语义记原因。
    """
    if exit_code == 0 and reward == 1:
        return True, ""
    if exit_code == 8:
        return False, "patch apply failed"
    if exit_code == 0:
        return False, "reward=%s" % reward
    return False, "verifier exit %d" % exit_code


def _run_docker_eval(docker_bin, docker_image, repo_path, patch_path,
                     task_dir, timeout=1800, registry_mirror="",
                     pull_timeout=300):
    """Docker 验证：注入 agent 补丁 → 跑 test.sh → 读 reward.txt 判分。

    流程：
      1. docker pull（可经 --registry-mirror 走已验证的国内镜像源）
      2. docker run，挂载 repo→/app、tests→/tests、out→/logs
      3. 容器内：git apply model.patch → bash /tests/test.sh
    语料 tests/ 先经 _stage_tests 归一化换行再挂载（语料本身不改）。

    返回 (ok, err, exit_code, output, reward)：
      reward 取 /logs/verifier/reward.txt（1=通过，0=未通过，None=未写出）。
      本类语料脚本写 reward 后以 0 收尾——**退出码 0 不等于 resolved**，
      判定必须看 reward（round-46 实踩：baseline 收集失败 reward=0，只看
      退出码会把失败误报成 resolved）。exit_code 非 0（3/4/5/6/8）表示
      装载/注入故障；其语义见语料脚本自身。
    """
    if not docker_bin:
        return False, "docker 不可用", -1, "", None
    run_ref = _docker_ref(docker_image, registry_mirror)
    if run_ref != docker_image:
        print("[deepswe] 经镜像源拉取: %s" % run_ref, file=sys.stderr)
    # 本地已有镜像就不再联网拉取（评测机断网时照样可复现；round-46 实测
    # 网络抖动下 pull 的 TLS 握手超时会把纯本地评测判成 env_failed）
    r = _run([docker_bin, "image", "inspect", run_ref], timeout=30)
    if r.returncode == 0:
        print("[deepswe] 镜像本地已存在，跳过 pull", file=sys.stderr)
    else:
        r = _run([docker_bin, "pull", run_ref], timeout=pull_timeout)
        if r.returncode != 0:
            return (False, "docker pull 失败: %s" % (r.stderr or "")[:300], -1,
                    "", None)
    # 准备挂载：把 patch 复制到 out_dir 下
    logs_dir = patch_path.parent / "docker-logs"
    logs_dir.mkdir(exist_ok=True)
    # 语料 tests/ 先归一化换行再挂载；暂存放 logs 的兄弟目录，避免 /tests
    # 嵌在 /logs 挂载点内部
    staged_tests = _stage_tests(task_dir / "tests",
                                patch_path.parent / "docker-tests")
    # 子模块缺失时先用镜像内置副本补齐（离线可复现）；失败仅告警，
    # baseline 会如实体现在 reward 里
    if not _seed_submodules_from_image(docker_bin, run_ref, repo_path):
        print("[deepswe] 警告：存在未初始化子模块，baseline 可能无法通过",
              file=sys.stderr)
    # 容器内脚本：apply patch + run test
    inner_script = (
        "#!/bin/bash\n"
        "set -uo pipefail\n"
        "cd /app || exit 6\n"
        "git config --global --add safe.directory /app 2>/dev/null || true\n"
        "git checkout . 2>/dev/null || true\n"
        "git clean -fdx 2>/dev/null || true\n"
        "# Apply agent patch\n"
        "if [ -f /logs/artifacts/model.patch ]; then\n"
        "  git apply --whitespace=nowarn /logs/artifacts/model.patch || "
        "    { echo 'PATCH_APPLY_FAILED'; exit 8; }\n"
        "fi\n"
        "# Run verifier\n"
        "bash /tests/test.sh\n"
    )
    script_path = logs_dir / "run-eval.sh"
    script_path.write_text(inner_script, encoding="utf-8", newline="\n")
    # 挂载映射（Windows 盘符 → Docker Desktop 路径）
    repo_mount = _to_docker_path(str(repo_path.resolve()))
    tests_mount = _to_docker_path(str(staged_tests.resolve()))
    logs_mount = _to_docker_path(str(logs_dir.resolve()))
    # 复制 patch 到 logs_dir/artifacts/model.patch
    artifacts_dir = logs_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    shutil.copy2(patch_path, artifacts_dir / "model.patch")
    # 语料脚本会把 reward 写到 /logs/verifier/reward.txt；宿主不预建目录
    # 时容器内重定向失败，判分前就以 exit=5 中断（round-46 实踩）。
    # 顺手清掉上一轮遗留，避免旧 reward=1 被当成本轮判分依据。
    (logs_dir / "verifier").mkdir(exist_ok=True)
    stale_reward = logs_dir / "verifier" / "reward.txt"
    if stale_reward.exists():
        stale_reward.unlink()
    cmd = [
        docker_bin, "run", "--rm",
        "-v", "%s:/app" % repo_mount,
        "-v", "%s:/tests:ro" % tests_mount,
        "-v", "%s:/logs" % logs_mount,
        "-w", "/app",
        run_ref,
        "bash", "/logs/run-eval.sh",
    ]
    r = _run(cmd, timeout=timeout)
    exit_code = r.returncode
    output = (r.stdout or "") + (r.stderr or "")
    # 完整验证输出落盘，结果里只留尾部 500 字，全程证据仍可复查
    (logs_dir / "verifier-output.log").write_text(
        output, encoding="utf-8", errors="replace")
    # 判分只认 reward.txt；上一轮遗留已在 run 前清掉
    reward = None
    reward_path = logs_dir / "verifier" / "reward.txt"
    if reward_path.is_file():
        try:
            reward = int(reward_path.read_text(encoding="utf-8").strip())
        except ValueError:
            reward = -1
    _, reason = _verdict(exit_code, reward)
    return True, reason, exit_code, output, reward


def main():
    parser = argparse.ArgumentParser(
        description="DeepSWE 评测适配器")
    parser.add_argument("--jsonl", default=str(DEFAULT_JSONL),
                        help="任务清单 JSONL（步骤 0.5 产出）")
    parser.add_argument("--out", required=True,
                        help="评测输出目录")
    parser.add_argument("--limit", type=int, default=0,
                        help="只跑前 N 个任务（0=全部）")
    parser.add_argument("--lang", default="",
                        help="只跑指定语言的任务")
    parser.add_argument("--diff", default="",
                        help="只跑指定难度的任务（easy/medium/hard）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只列出任务，不执行")
    parser.add_argument("--no-eval", action="store_true",
                        help="只跑 code-task.py 生成补丁，不跑 Docker 验证")
    parser.add_argument("--host-loop", action="store_true",
                        help="code-task 走宿主 LLM 协议（CRA_LLM_PROVIDER=host）："
                             "WAIT_HOST_LLM 记 waiting_host 非失败；宿主填响应后"
                             "原命令重跑即续跑")
    parser.add_argument("--docker-bin", default="",
                        help="docker 可执行路径（默认自动查找）")
    parser.add_argument("--registry-mirror", default="",
                        help="已验证可达的镜像源前缀（硬约束 8；空=原注册表直连）")
    parser.add_argument("--pull-timeout", type=int, default=300,
                        help="docker pull 超时秒数（默认 300）")
    parser.add_argument("--rounds", type=int, default=6,
                        help="code-task.py 的 --rounds 参数")
    parser.add_argument("--repos-dir", default="",
                        help="仓库 clone 根目录（默认 <out>/repos）")
    parser.add_argument("--timeout", type=int, default=1800,
                        help="Docker 验证超时秒数")
    parser.add_argument("--allow-test-edits", dest="allow_test_edits",
                        action="store_true",
                        help="允许补丁触碰测试/pytest 配置（patch_integrity "
                             "仍会记录 critical，但标记 waived 不拦 resolved；"
                             "默认关闭——测试黑客面按完整性红线处理）")
    argv = parser.parse_args()

    jsonl_path = Path(argv.jsonl)
    if not jsonl_path.is_file():
        _emit({"ok": False, "error": "JSONL 不存在: %s" % jsonl_path})
        return 2
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    repos_dir = Path(argv.repos_dir) if argv.repos_dir else out_dir / "repos"
    repos_dir.mkdir(parents=True, exist_ok=True)

    try:
        tasks = _load_tasks(jsonl_path, argv.lang, argv.diff, argv.limit)
    except (ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": "JSONL 格式错误: %s: %s" % (
            jsonl_path, str(exc)[:300])})
        return 2
    if not tasks:
        _emit({"ok": False, "error": "无匹配任务",
               "filters": {"lang": argv.lang, "diff": argv.diff,
                           "limit": argv.limit}})
        return 2

    if argv.dry_run:
        _emit({"ok": True, "dry_run": True, "total": len(tasks),
               "tasks": [{"id": t["id"], "language": t.get("language", ""),
                          "difficulty": t.get("_difficulty", ""),
                          "repo": t.get("repo", ""),
                          "category": t.get("category", "")}
                         for t in tasks]})
        return 0

    docker_bin = argv.docker_bin or _find_docker()
    if not argv.no_eval and not argv.registry_mirror:
        print("[deepswe] 提示：未指定 --registry-mirror，将直连原注册表；"
              "按硬约束 8 应先实测国内镜像可达性", file=sys.stderr)
    results = []
    resolved_count = 0
    failed_count = 0
    waiting_count = 0

    def _record(res, started):
        """统一补效率指标（每任务墙钟耗时），并在收尾时落 results。"""
        res["elapsed_sec"] = round(time.monotonic() - started, 3)
        results.append(res)

    for idx, task in enumerate(tasks):
        task_started = time.monotonic()
        task_id = task["id"]
        repo_url = task.get("repo", "")
        base_commit = task.get("base_commit", "")
        language = task.get("language", "unknown")
        difficulty = task.get("_difficulty", "medium")
        task_dir_raw = str(task.get("task_dir", "")).strip()
        task_dir = Path(task_dir_raw) if task_dir_raw else None
        docker_image = task.get("docker_image", "")

        print("[deepswe] %d/%d %s (%s/%s)" % (
            idx + 1, len(tasks), task_id, language, difficulty),
              file=sys.stderr)

        result = {
            "id": task_id,
            "language": language,
            "difficulty": difficulty,
            "category": task.get("category", ""),
            "repo": repo_url,
            "base_commit": base_commit,
            "status": "pending",
        }

        # 1. Clone + checkout
        repo_name = repo_url.rsplit("/", 1)[-1].replace(".git", "")
        repo_dest = repos_dir / repo_name
        ok, err = _clone_repo(repo_url, repo_dest, base_commit)
        if not ok:
            result["status"] = "clone_failed"
            result["error"] = err
            failed_count += 1
            _record(result, task_started)
            print("  CLONE_FAIL: %s" % err, file=sys.stderr)
            continue

        # 2. 调 code-task.py 生成补丁
        task_out = out_dir / task_id
        # 宿主循环档的可续跑态：已有任务态（或已收束清单）就走 --resume，
        # 使「宿主填响应 → 原命令重跑」自然续上，不用另记参数
        resume = (task_out / "task-meta.json").is_file() \
            or (task_out / "task-manifest.json").is_file()
        status, patch_path, detail = _run_code_task(
            repo_dest, task, task_out, rounds=argv.rounds,
            resume=resume, host_loop=argv.host_loop)
        if status == "waiting":
            result["status"] = "waiting_host"
            result["llm_task"] = detail.get("llm_task", "")
            result["llm_response"] = detail.get("llm_response", "")
            waiting_count += 1
            _record(result, task_started)
            print("  WAIT_HOST_LLM: %s" % detail.get("llm_task", ""),
                  file=sys.stderr)
            continue
        if status != "ok":
            result["status"] = "code_task_failed"
            result["error"] = detail
            failed_count += 1
            _record(result, task_started)
            print("  CODE_TASK_FAIL: %s" % detail, file=sys.stderr)
            continue
        result["patch"] = str(patch_path)
        stats = _code_task_stats(task_out)
        if stats:
            result["code_task"] = stats
        # 补丁完整性（patch provenance）：读 reward 之前先看补丁改了什么。
        # 触碰测试基础设施/pytest 配置/解释器钩子的补丁不参加 resolved 计数，
        # 避免把「测试黑客」当能力（Berkeley RDI conftest 钩子刷分为依据）。
        integrity = _patch_integrity(patch_path)
        result["patch_integrity"] = integrity
        if argv.allow_test_edits and not integrity["ok"]:
            integrity["waived"] = True
            integrity["ok"] = True
        if not integrity["ok"]:
            result["status"] = "integrity_flagged"
            result["error"] = "补丁触碰评测完整性红线: %s" % ", ".join(
                "%s:%s" % (c.get("code", ""), c.get("path", ""))
                for c in integrity.get("critical", [])[:3])
            failed_count += 1
            _record(result, task_started)
            print("  INTEGRITY_FLAG: %s" % result["error"], file=sys.stderr)
            continue

        # 结构闸（round-48）：hunk 声明行数与正文不符 = 坏产物，不计 resolved、
        # 不进入评测；与 integrity 闸同属「补丁先行」的前置判定，但不可豁免。
        if not _apply_structural_gate(result, patch_path):
            failed_count += 1
            _record(result, task_started)
            print("  MALFORMED_PATCH: %s" % result["error"], file=sys.stderr)
            continue

        # 3. Docker 验证（除非 --no-eval）
        if argv.no_eval:
            result["status"] = "patch_generated"
            _record(result, task_started)
            continue

        if not docker_image:
            result["status"] = "no_docker_image"
            result["error"] = "task.toml 无 docker_image 字段"
            failed_count += 1
            _record(result, task_started)
            continue

        if task_dir is None or not (task_dir / "tests" / "test.sh").is_file():
            result["status"] = "env_failed"
            result["error"] = "task_dir/tests/test.sh 缺失: %s" % (task_dir_raw,)
            failed_count += 1
            _record(result, task_started)
            print("  ENV_FAIL: task_dir 缺失或 tests/test.sh 不存在",
                  file=sys.stderr)
            continue

        ok, err, exit_code, output, reward = _run_docker_eval(
            docker_bin, docker_image, repo_dest, patch_path,
            task_dir, timeout=argv.timeout,
            registry_mirror=argv.registry_mirror,
            pull_timeout=argv.pull_timeout)
        if not ok:
            result["status"] = "env_failed"
            result["error"] = err
            failed_count += 1
            _record(result, task_started)
            print("  ENV_FAIL: %s" % err, file=sys.stderr)
            continue

        result["verifier_exit"] = exit_code
        result["reward"] = reward
        # resolved 以语料 reward=1 为准（baseline 与新增测试双通过），
        # 退出码 0 只是「脚本跑完」，单独不能判 resolved
        if exit_code == 0 and reward == 1:
            result["status"] = "resolved"
            resolved_count += 1
        else:
            result["status"] = "unresolved"
            result["verifier_output"] = output[-500:]
            if err:
                result["error"] = err
        _record(result, task_started)
        print("  %s (exit=%d)" % (result["status"], exit_code),
              file=sys.stderr)

    _emit({
        "ok": failed_count == 0 and waiting_count == 0,
        "total": len(tasks),
        "resolved": resolved_count,
        "failed": failed_count,
        "waiting": waiting_count,
        "results": results,
        "out": str(out_dir),
    })
    return 1 if (failed_count or waiting_count) else 0


if __name__ == "__main__":
    sys.exit(main())
