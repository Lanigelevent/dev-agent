#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SWE-bench Live 评测驱动器：源码获取 → 环境构建 → 测试补丁 → test_cmds →
F2P/P2P 判定 → 台账（round-51 阶段二适配层）。

与既有驱动的分工：
    gold-sample.py    SWE-bench Lite 官方 harness
    deepswe-sample.py DeepSWE（ECR 镜像 + reward.txt）
    pro-sample.py     SWE-bench Pro v2（预构建镜像 + before_repo_set_cmd）
    live-sample.py    SWE-bench Live（无官方镜像：本机 clone + venv + test_cmds；
                      full clone 失败时 depth-1 单提交救援，r82 产品化）
Live 的判分点与 Pro/DeepSWE 同口径：F2P 全 PASSED 且 P2P 全 PASSED 才算
resolved；零 P2P 实例只要求 F2P（数据集真实形态，不因缺失 P2P 拒跑）。
pytest 解析与 judge 直接复用 pro-sample.py（单一实现，不复制）。

任务清单（JSONL，gate 语料不入库；由 .venv 侧从 parquet 一次性抽取）：
    instance_id / repo / base_commit / test_patch / gold_patch /
    test_cmds / fail_to_pass / pass_to_pass
可选任务级字段（不硬编码实例差异）：
    setup_cmds   构建环境的命令列表（在 venv 内执行；给定时替换默认 pip 流程）
    python      该实例要求的解释器路径（缺省用 --python）

环境获取顺序（硬约束 8：国内优先）：
    1. 本地缓存 <source-root>/<repo 名>（如 gitee 镜像仓，零外网）；
    2. gitee 镜像 `https://gitee.com/mirrors/<repo 名>`（可达性由 --source-timeout
       实测截断，慢即判死）；
    3. GitHub 直连仅作回退，记录降级原因。
全部不可达或 base_commit 不存在 → `blocked_source`，样本保留在台账，不静默丢。

工作区纪律（round-49 真坑）：`git worktree add` 的目标路径一律用绝对路径，
否则被解析到源仓库内部；worktree 目录按 `<iid>|<mode>` 分桶，baseline 与
gold 互不污染。

判分流程：
    1. 写 test_patch 并做结构自检（损坏 → malformed_test_patch，不进环境）；
    2. `git worktree add` 分离 HEAD 到 <base_commit>，git apply test_patch；
    3. gold / predictions 再 apply 候选补丁（结构闸 + 完整性闸，同 pro-sample）；
    4. 建 venv（或用 --skip-venv / --python），清华 PyPI 安装（或任务级 setup_cmds）；
    5. 在仓库根目录按 test_cmds 执行，合并输出按 `-rA` 逐 node 解析；
    6. judge 三分支（baseline / gold / predictions），结果写台账。

平台口径：Live 官方在 Linux 容器内评测；本驱动在本机（Windows）建环境。
平台与依赖来源偏差必须写进报告，不得用本机结果直接宣称官方通过率。

用法示例:
    py live-sample.py --tasks datasets/swebench/live/gate-10.jsonl \\
        --mode baseline --out datasets/swebench/live-runs
    py live-sample.py --tasks <jsonl> --mode gold --out <目录> \\
        --source-root datasets/swe-repos
    py live-sample.py --tasks <jsonl> --mode predictions --predictions p.jsonl \\
        --out <目录>
    py live-sample.py --tasks <jsonl> --dry-run     # 只出计划，不建环境不触网

退出码: 0 = 选定实例全部达到期望状态（gold/pred 的 resolved/unresolved 均算
完成，baseline 的 baseline_ok 算完成）；1 = 存在失败状态（blocked_source /
env_failed / malformed / malformed_node_ids / integrity_flagged /
patch_apply_failed / prepare_failed / infra_error / baseline_unexpected /
baseline_p2p_failed）；2 = 参数或输入错误。stdout 单 JSON 文档；进度与诊断
走 stderr。
"""
import argparse
import importlib.util
import json
import os
import shutil
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_ROOT = ROOT / "datasets" / "swe-repos"
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
_PRO = None


def _pro():
    """按路径加载 pro-sample.py，复用 pytest 解析 / judge / 字段归一。"""
    global _PRO
    if _PRO is None:
        path = Path(__file__).with_name("pro-sample.py")
        spec = importlib.util.spec_from_file_location("pro_sample_shared", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PRO = mod
    return _PRO


def _deepswe():
    return _pro()._deepswe()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _log(message):
    sys.stderr.write("[live-sample] %s\n" % message)
    sys.stderr.flush()


def _kill_tree(proc):
    """杀整棵进程树（round-51 真坑：git 会派生 git-remote-https，只杀直接子进程
    会把孙进程留成孤儿并占住工作目录）。Windows 用 taskkill /T，POSIX 杀进程组。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, text=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()


def _run(cmd, timeout, cwd=None, env=None, shell=False):
    """子进程统一入口；超时杀整棵进程树后返回 rc=124（失败要入台账）。

    不用 subprocess.run：它超时只 kill 直接子进程，git-remote-https 这类孙进程
    会存活并占住目录（round-51 实测 clou 10 分钟无进展）。
    """
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd) if cwd else None, env=env, shell=shell,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            start_new_session=(os.name != "nt"),
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                           if os.name == "nt" else 0))
    except OSError as exc:
        return 2, "", str(exc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        return 124, out or "", "timeout after %ss" % timeout
    return proc.returncode, out or "", err or ""


def _short(text):
    return _pro()._short_tag(str(text))


def _repo_name(repo):
    return str(repo or "").rstrip("/").split("/")[-1]


def _python_bin(venv):
    cands = [venv / "Scripts" / "python.exe", venv / "bin" / "python"]
    for cand in cands:
        if cand.is_file():
            return cand
    return cands[0]


def source_cache_path(source_root, task):
    return Path(source_root) / _repo_name(task.get("repo"))


def _git_env():
    """git 统一环境：禁交互（无凭据时直接失败，不挂起等输入）。"""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_ASKPASS", "echo")
    return env


def _git_has_commit(repo, sha):
    rc, _, _ = _run(["git", "-C", str(repo), "cat-file", "-e",
                     "%s^{commit}" % sha], timeout=30, env=_git_env())
    return rc == 0


def _depth1_rescue(url, dest, sha, timeout, env):
    """depth-1 单提交救援取法（round-82 产品化；r66/r81 两次实跑验证）。

    full clone 对大仓在 source_timeout 内不可行（round-81：checkov/
    conan 级别仓库连续超时），而判分链只需要 base_commit 一棵树——
    GitHub/gitee 均支持按 sha 单提交 depth-1 fetch。dest 必须为绝对
    路径（round-81 坑 91a0a024ece2：相对路径按 -C 的 cwd 解析）。
    """
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rc, _, _ = _run(["git", "init", "-q", str(dest)], timeout=60, env=env)
    if rc != 0:
        return False
    rc, _, _ = _run(["git", "-C", str(dest), "remote", "add", "origin",
                     url], timeout=60, env=env)
    if rc != 0:
        return False
    rc, _, _ = _run(["git", "-C", str(dest), "fetch", "--depth", "1",
                     "origin", sha], timeout=timeout, env=env)
    if rc != 0:
        return False
    rc, _, _ = _run(["git", "-C", str(dest), "checkout", "-q",
                     "FETCH_HEAD"], timeout=60, env=env)
    return rc == 0 and _git_has_commit(dest, sha)


def find_source(task, argv, out_dir):
    """定位源码仓（本地缓存 → gitee → GitHub 回退）。

    返回 (repo_path, kind, detail)；失败时 repo_path 为空、kind=blocked。
    """
    cache = source_cache_path(argv.source_root, task)
    if cache.is_dir() and _git_has_commit(cache, task["base_commit"]):
        return cache, "cache", ""
    if argv.no_network:
        return "", "blocked", "本地缓存无该 base_commit，且已指定 --no-network"
    name = _repo_name(task["repo"])
    urls = [("gitee", "https://gitee.com/mirrors/%s" % name),
            ("github", "https://github.com/%s.git" % str(task["repo"]).strip("/"))]
    dest = Path(out_dir) / "sources" / name
    if dest.is_dir() and not (dest / ".git").is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    for kind, url in urls:
        if not dest.is_dir():
            _log("clone %s（%s）" % (url, kind))
            rc, out, err = _run(["git", "clone", "--quiet", url, str(dest)],
                                timeout=argv.source_timeout, env=_git_env())
            if rc != 0:
                detail = (err or out).strip().splitlines()
                _log("clone 失败(%s): %s" % (kind, detail[-1] if detail else rc))
                shutil.rmtree(dest, ignore_errors=True)
                continue
        if _git_has_commit(dest, task["base_commit"]):
            return dest, kind, ("" if kind == "gitee" else "GitHub 回退")
        _log("%s 缺 base_commit，尝试 fetch" % kind)
        rc, _, _ = _run(["git", "-C", str(dest), "fetch", "origin",
                         task["base_commit"]], timeout=argv.source_timeout,
                        env=_git_env())
        if rc == 0 and _git_has_commit(dest, task["base_commit"]):
            return dest, kind, ("" if kind == "gitee" else "GitHub 回退")
        shutil.rmtree(dest, ignore_errors=True)
        # depth-1 单提交救援（round-82 产品化）：full clone / fetch 都
        # 失败时（典型为大仓超时），只取 base_commit 一棵树。
        if _depth1_rescue(url, dest, task["base_commit"],
                          argv.source_timeout, _git_env()):
            _log("%s depth-1 救援成功" % kind)
            return dest, kind, ("depth-1 救援" if kind == "gitee"
                                else "GitHub depth-1 救援")
    return "", "blocked", "gitee/GitHub 均不可达或缺少 base_commit"


def prepare_worktree(repo, task, work_dir, timeout=300):
    """绝对路径 worktree（round-49 真坑）；已存在先移除，避免状态污染。"""
    work_dir = Path(work_dir).resolve()
    repo_rel = str(work_dir)
    rc, _, _ = _run(["git", "-C", str(repo), "worktree", "remove", "--force",
                     repo_rel], timeout=120, env=_git_env())
    if rc != 0 and work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    _run(["git", "-C", str(repo), "worktree", "prune"], timeout=60,
         env=_git_env())
    work_dir.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = _run(["git", "-C", str(repo), "worktree", "add",
                         "--detach", repo_rel, task["base_commit"]],
                        timeout=timeout, env=_git_env())
    if rc != 0:
        return False, (err or out).strip()[:300]
    return True, ""


def build_env(repo_dir, task, argv, work_dir=None):
    """构建/定位解释器；返回 (python_bin, state, detail)。

    repo_dir 是仓库根（worktree）；venv 建在 work_dir（外层）以免把未跟踪
    venv 塞进被审 worktree（给定时），pip/setup_cmds 一律在 repo_dir 执行
    （round-51 真坑：cwd 用外层目录会导致 `pip install -e .` 找不到工程）。
    state: venv / system / failed。--skip-venv 时不建 venv（测试与预置环境）；
    setup_cmds 在两种模式下都会执行（给定即覆盖默认 pip 流程）。
    """
    repo_dir = Path(repo_dir)
    venv_root = Path(work_dir) if work_dir else repo_dir
    if argv.skip_venv:
        python = Path(argv.python) if argv.python else Path(sys.executable)
        state = "system"
    else:
        venv = venv_root / "venv"
        if not venv.exists():
            rc, out, err = _run([argv.python, "-m", "venv", str(venv)],
                                timeout=argv.setup_timeout)
            if rc != 0:
                return "", "failed", "venv 创建失败: %s" % (
                    (err or out).strip()[:300])
        python = _python_bin(venv)
        state = "venv"
    env = env_for(python)
    setup_cmds = _pro()._as_list(task.get("setup_cmds"))
    if setup_cmds:
        for cmd in setup_cmds:
            rc, out, err = _run(cmd, timeout=argv.setup_timeout,
                                cwd=repo_dir, env=env, shell=True)
            if rc != 0:
                tail = ((err or out).strip().splitlines() or [""])[-1][:200]
                return python, "failed", "setup_cmds 失败(%s): %s" % (
                    cmd[:80], tail)
        return python, state, ""
    if state == "system":
        return python, state, ""
    # 默认流程：editable 安装 + pytest（清华源）；装不上即 env_failed，
    # 由任务级 setup_cmds 显式覆盖，不静默跳过。
    for cmd in ([str(python), "-m", "pip", "install", "-i", argv.mirror,
                 "-e", "."],
                [str(python), "-m", "pip", "install", "-i", argv.mirror,
                 "pytest"]):
        rc, out, err = _run(cmd, timeout=argv.setup_timeout,
                            cwd=repo_dir, env=env)
        if rc != 0:
            tail = ((err or out).strip().splitlines() or [""])[-1][:200]
            return python, "failed", "pip 失败(%s): %s" % (
                " ".join(cmd[3:6]), tail)
    return python, "venv", ""


def env_for(python_bin):
    env = dict(os.environ)
    # 必须绝对化：cwd 是 worktree，相对 PATH 会在 worktree 内解析成不存在
    # 的目录（round-51 真坑：venv 里的 pytest 明明存在却报“不是内部或外部命令”）。
    bindir = str(Path(python_bin).resolve().parent)
    env["PATH"] = bindir + os.pathsep + env.get("PATH", "")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    return env


def _shquote(text):
    """node id 只在含空白时加引号；Windows cmd.exe 不认 shlex 的单引号。"""
    text = str(text)
    return '"%s"' % text if any(ch.isspace() for ch in text) else text


def write_patch(path, text):
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def apply_patch(repo_dir, patch_path):
    rc, out, err = _run(["git", "-C", str(repo_dir), "apply", "--verbose",
                         str(Path(patch_path).resolve())], timeout=120,
                        env=_git_env())
    return rc == 0, (err or out).strip()[:300]


def run_test_cmds(cmds, repo_dir, python, timeout):
    """按 test_cmds 顺序执行，合并输出；任一命令超时即 infra_error。"""
    env = env_for(python)
    chunks = []
    for cmd in cmds:
        _log("执行: %s" % cmd)
        rc, out, err = _run(cmd, timeout=timeout, cwd=repo_dir, env=env,
                            shell=True)
        chunks.append(out or "")
        if err:
            chunks.append(err)
        if rc == 124:
            return False, "\n".join(chunks), "test_cmd 超时: %s" % cmd
    return True, "\n".join(chunks), ""


def judge_output(text, fail_to_pass, pass_to_pass, mode):
    return _pro().judge(_pro().parse_pytest_output(text), fail_to_pass,
                        pass_to_pass, mode)


def _django_node_candidates(node):
    """django-runner 节点「test_x (module.Class)」→ pytest 节点候选列表
    （非 django 格式返回空表）。"""
    m = re.match(r"^(test_\w+)\s+\(([\w.]+)\)$", str(node).strip())
    if not m:
        return []
    test_name, target = m.group(1), m.group(2)
    module, _, cls = target.rpartition(".")
    if not module or not cls:
        return []
    base = module.replace(".", "/")
    return [c + "::" + cls + "::" + test_name
            for c in (base + ".py", "tests/" + base + ".py",
                      base.replace("/tests", "") + "/tests.py")]


def _normalize_django_nodes(task, repo_dir):
    """verified 的 django 系任务 F2P/P2P 为 django-runner 节点格式；
    依 repo 文件存在性机械转 pytest 节点，写入 `*_pytest` 键（原单
    保留——runtests 口径直接吃原标签，pytest 口径吃转换单；round-101，
    round-102 重构为双轨）。非 django 格式或文件解析不出的条目按原样
    进转换单。"""
    hit = 0
    for key in ("fail_to_pass", "pass_to_pass"):
        out = []
        for node in task.get(key) or []:
            pick = None
            for cand in _django_node_candidates(node):
                if (Path(repo_dir) / cand.split("::")[0]).is_file():
                    pick = cand
                    break
            if pick:
                out.append(pick)
                hit += 1
            else:
                out.append(node)
        task[key + "_pytest"] = out
    return task, hit


def _judge_django_runtests(output, fail_to_pass):
    """django runtests.py -v 2 输出判分：逐 F2P 标签解析出全点分名，在
    「<full_dotted> ... ok/ERROR/FAIL」行中匹配状态；缺行记 missing。
    r107 补：unittest -v 2 对带 docstring 的测试把「... 状态」换行
    （docstring 首行插在测试名与状态之间）——状态行归属紧邻的上一个
    测试名行，否则此类测试恒判 missing（11087 实踩）。"""
    statuses = {}
    name_re = re.compile(r"^(test_\w+) \(([\w.]+)\)$")
    pending = None  # 上一个未定状态的测试名行（docstring 折行情形）
    for line in output.splitlines():
        s = line.strip()
        m = re.match(r"^(.+) \.\.\. (\w+)$", s)
        if m:
            key = m.group(1).strip()
            if name_re.match(key):
                pending = None
            elif pending is not None:
                key = pending
                pending = None
            statuses[key] = m.group(2).upper()
        elif name_re.match(s):
            pending = s
    passed, missing = 0, []
    st = {}
    for label in fail_to_pass:
        dm = re.match(r"^(test_\w+)\s+\(([\w.]+)\)$", str(label).strip())
        full = (dm.group(2) + "." + dm.group(1)) if dm else str(label).strip()
        # 输出行的 group(1) 含括号：test_x (full.dotted)——找含 full 的行
        verdict = None
        for key, v in statuses.items():
            if full in key:
                verdict = v
                break
        if verdict == "OK":
            passed += 1
            st[label] = "PASSED"
        elif verdict in ("ERROR", "FAIL"):
            st[label] = "FAILED"
        else:
            missing.append(label)
            st[label] = None
    return {"fail_to_pass": {"total": len(fail_to_pass), "passed": passed,
                             "missing": missing, "statuses": st}}


def node_id_problems(task, f2p_only=False):
    """上游数据体检：参数化 node id 含空格会被截断（`[` 未闭合）。

    round-65 实踩 cfn-lint-3749：lite.parquet 的 PASS_TO_PASS 里 1223 条有
    329 条形如 `...::test_sorted[Different`（原表 0 条含空格）——exact-match
    判分必判 missing，跑完完整套件才拿到一个迟到的 baseline_unexpected。
    开跑前判 `malformed_node_ids`，不建环境、不浪费时间。
    round-67 补：体检范围对齐判分范围——--f2p-only 只判 F2P，P2P 里的坏 id
    与判分无关，不得把整条 f2p-only 通路拦死（round-51 matplotlib-28933 的
    结案复验命令因此失灵两轮未察觉）。
    """
    ids = list(task.get("fail_to_pass") or [])
    if not f2p_only:
        ids += list(task.get("pass_to_pass") or [])
    bad = [str(n) for n in ids
           if str(n).count("[") != str(n).count("]")]
    return bad


def _gate_file(patch_path):
    return (_deepswe()._patch_well_formed(patch_path),
            _deepswe()._patch_integrity(patch_path))


SBCLI_EXPORT_STATES = {"resolved", "f2p_passed"}


def _export_sbcli(argv, current):
    """P0-1（r111）：f2p_passed/resolved 样本导出 sb-cli predictions
    JSONL（instance_id + model_patch，官方字段），补丁读自
    work/<short(key)>/tests/candidate.patch；缺补丁的如实列 missing。
    states 副档保留本地判定，官方 resolved 与本地口径分开陈述。"""
    if not argv.export_sbcli:
        return None
    rows, missing = [], []
    for row in current:
        if row.get("state") not in SBCLI_EXPORT_STATES:
            continue
        key = row.get("key") or "%s|%s" % (row.get("instance_id"),
                                             row.get("mode"))
        cpatch = (Path(argv.out) / "work" / _short(key)
                  / "tests" / "candidate.patch")
        if cpatch.is_file():
            rows.append({"instance_id": row.get("instance_id"),
                         "model_patch": cpatch.read_text(encoding="utf-8")})
        else:
            missing.append(row.get("instance_id"))
    out_path = Path(argv.export_sbcli)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    info = {"path": str(out_path), "n": len(rows),
            "missing_patch": missing,
            "states": {r.get("instance_id"): r.get("state")
                       for r in current}}
    _log("sb-cli 导出 %d 项 -> %s" % (len(rows), out_path))
    return info


def run_one(task, argv):
    iid = task["instance_id"]
    mode = argv.mode
    result = {"instance_id": iid, "key": "%s|%s" % (iid, mode), "mode": mode,
              "state": "", "resolved": None, "detail": "", "repo": "",
              "source_kind": "", "elapsed_sec": None,
              "fail_to_pass": len(task["fail_to_pass"]),
              "pass_to_pass": len(task["pass_to_pass"])}
    started = time.monotonic()
    out_root = Path(argv.out)
    work_dir = out_root / "work" / _short(result["key"])
    tests_dir = work_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    bad_nodes = node_id_problems(task, f2p_only=argv.f2p_only)
    if bad_nodes:
        result.update(
            state="malformed_node_ids",
            detail="判分点 id 括号不闭合（上游数据集截断）%d 条，如: %s"
                   % (len(bad_nodes), bad_nodes[0][:160]))
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    test_patch = tests_dir / "test_patch.patch"
    write_patch(test_patch, task["test_patch"])
    verdict, issues = _gate_file(test_patch)
    if not verdict.get("ok", True):
        result.update(state="malformed_test_patch",
                      detail="; ".join(issues)[:300])
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    candidate = None
    if mode in ("gold", "predictions"):
        candidate = tests_dir / "candidate.patch"
        candidate_text = (task["candidate_patch"] if mode == "predictions"
                          else task.get("gold_patch"))
        if not str(candidate_text or "").strip():
            result.update(state="malformed_patch", detail="候选补丁为空")
            result["elapsed_sec"] = round(time.monotonic() - started, 3)
            return result
        write_patch(candidate, candidate_text or "")
        verdict, issues = _gate_file(candidate)
        if not verdict.get("ok", True):
            result.update(state="malformed_patch",
                          detail="; ".join(issues)[:300])
            result["elapsed_sec"] = round(time.monotonic() - started, 3)
            return result
        if not issues.get("ok", True) and not argv.allow_test_edits:
            result.update(state="integrity_flagged",
                          detail="; ".join(c.get("code", "")
                                           for c in issues.get("critical") or [])[:300])
            result["elapsed_sec"] = round(time.monotonic() - started, 3)
            return result
        if issues.get("ok") is False:
            result["integrity_waived"] = True

    repo, kind, detail = find_source(task, argv, out_root)
    result["source_kind"] = kind
    if not repo:
        result.update(state="blocked_source", detail=detail)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    result["repo"] = str(repo)
    ok, detail = prepare_worktree(repo, task, work_dir / "repo")
    if not ok:
        result.update(state="prepare_failed", detail=detail)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    repo_dir = work_dir / "repo"
    ok, detail = apply_patch(repo_dir, test_patch)
    if not ok:
        result.update(state="patch_apply_failed",
                      detail="test_patch: %s" % detail)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    if candidate is not None:
        ok, detail = apply_patch(repo_dir, candidate)
        if not ok:
            result.update(state="patch_apply_failed",
                          detail="candidate: %s" % detail)
            result["elapsed_sec"] = round(time.monotonic() - started, 3)
            return result
    task, django_converted = _normalize_django_nodes(task, repo_dir)

    python, state, detail = build_env(repo_dir, task, argv, work_dir)
    if state == "failed":
        result.update(state="env_failed", detail=detail)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    cmds = task["test_cmds"]
    if argv.f2p_only:
        if not all("pytest" in cmd for cmd in cmds):
            result.update(state="infra_error",
                          detail="--f2p-only 需要全部 test_cmds 为 pytest 调用")
            result["elapsed_sec"] = round(time.monotonic() - started, 3)
            return result
        if task.get("test_runner") == "django-runtests":
            # django 系：原标签即 runtests.py 的 test label，直接喂给
            # 自带引导（settings 配置 + django.setup()），判分走 unittest
            # 输出解析（round-101 判分链格式缺口的解锁路径）。
            labels = " ".join('"%s"' % l for l in task["fail_to_pass"])
            runtests_labels = []
            for label in task["fail_to_pass"]:
                m = re.match(r"^(test_\w+)\s+\(([\w.]+)\)$",
                             str(label).strip())
                if not m:
                    result.update(state="infra_error",
                                  detail="django-runtests 标签格式无法解析: %s"
                                  % label)
                    result["elapsed_sec"] = round(time.monotonic()
                                                  - started, 3)
                    return result
                runtests_labels.append(m.group(2) + "." + m.group(1))
            labels = " ".join(runtests_labels)
            cmds = [str(Path(python).resolve()) + " tests/runtests.py " + labels
                    + " -v 2"]
        else:
            nodes = " ".join(
                _shquote(node)
                for node in (task.get("fail_to_pass_pytest")
                             or task["fail_to_pass"]))
            cmds = [cmd + " " + nodes for cmd in cmds]
        result["partial"] = True
    ok, output, detail = run_test_cmds(cmds, repo_dir, python,
                                       argv.exec_timeout)
    result["test_log"] = str(work_dir / "test.log")
    Path(result["test_log"]).write_text(output, encoding="utf-8",
                                        newline="\n")
    if not ok:
        result.update(state="infra_error", detail=detail)
        result["elapsed_sec"] = round(time.monotonic() - started, 3)
        return result
    if task.get("test_runner") == "django-runtests":
        judged = _judge_django_runtests(output, task["fail_to_pass"])
        f2p = judged["fail_to_pass"]
        all_pass = (f2p["passed"] == f2p["total"]
                    and not f2p["missing"])
        all_fail = (f2p["passed"] == 0
                    and not f2p["missing"]
                    and f2p["total"] > 0)
        if mode == "baseline":
            verdict = "baseline_ok" if all_fail else "baseline_unexpected"
        elif argv.f2p_only:
            verdict = "f2p_passed" if all_pass else "unresolved"
            judged["partial"] = True
        else:
            verdict = "resolved" if all_pass else "unresolved"
    else:
        verdict, judged = judge_output(
            output,
            (task.get("fail_to_pass_pytest") or task["fail_to_pass"]),
            ([] if argv.f2p_only
             else (task.get("pass_to_pass_pytest")
                   or task.get("pass_to_pass") or [])), mode)
        if argv.f2p_only and verdict == "resolved":
            verdict = "f2p_passed"
            judged["partial"] = True
    result["state"] = verdict
    result["resolved"] = (True if verdict == "resolved" else
                          (False if verdict == "unresolved" else None))
    result["detail"] = json.dumps(judged, ensure_ascii=False)[:2000]
    result["elapsed_sec"] = round(time.monotonic() - started, 3)
    return result


def dry_run(selected, argv):
    plan = {"ok": True, "dry_run": True, "mode": argv.mode,
            "source_root": str(Path(argv.source_root).resolve()),
            "skip_venv": bool(argv.skip_venv), "python": argv.python,
            "mirror": argv.mirror, "tasks": []}
    for iid, task in selected.items():
        cache = source_cache_path(argv.source_root, task)
        plan["tasks"].append({
            "instance_id": iid, "repo": task.get("repo"),
            "source_cache": str(cache),
            "source_ready": bool(cache.is_dir()
                                 and _git_has_commit(cache,
                                                     task["base_commit"])),
            "worktree": str((Path(argv.out) / "work" /
                             _short("%s|%s" % (iid, argv.mode)) /
                             "repo").resolve()),
            "test_cmds": task["test_cmds"],
            "setup_cmds": task.get("setup_cmds") or [],
            "fail_to_pass": len(task["fail_to_pass"]),
            "pass_to_pass": len(task["pass_to_pass"]),
            "node_id_problems": len(node_id_problems(task,
                                                        f2p_only=argv.f2p_only)),
        })
    _emit(plan)
    return 0


def main():
    parser = argparse.ArgumentParser(description="SWE-bench Live 评测驱动器")
    parser.add_argument("--tasks", required=True, help="任务 JSONL")
    parser.add_argument("--instances", default="", help="逗号分隔实例 id")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    parser.add_argument("--mode", choices=("baseline", "gold", "predictions"),
                        default="gold",
                        help="baseline=只打测试补丁；gold/predictions=再打候选补丁")
    parser.add_argument("--predictions", default="",
                        help="predictions 模式的补丁 jsonl（instance_id + model_patch）")
    parser.add_argument("--export-sbcli", dest="export_sbcli", default="",
                        help="r111 P0-1：运行后把 f2p_passed/resolved 样本导出为 sb-cli predictions JSONL（给路径）")
    parser.add_argument("--out", required=True, help="产物目录")
    parser.add_argument("--source-root", dest="source_root",
                        default=str(DEFAULT_SOURCE_ROOT),
                        help="本地源码缓存根目录（每仓一个子目录，优先使用）")
    parser.add_argument("--mirror", default=PIP_MIRROR,
                        help="pip 索引（默认清华镜像）")
    parser.add_argument("--python", default=sys.executable,
                        help="创建 venv 的基础解释器；--skip-venv 时直接使用")
    parser.add_argument("--skip-venv", dest="skip_venv", action="store_true",
                        help="不建 venv，直接用 --python（预置环境/测试）")
    parser.add_argument("--source-timeout", dest="source_timeout", type=int,
                        default=300, help="单次 clone/fetch 超时（秒）")
    parser.add_argument("--setup-timeout", dest="setup_timeout", type=int,
                        default=900, help="venv/pip/setup_cmds 超时（秒）")
    parser.add_argument("--exec-timeout", dest="exec_timeout", type=int,
                        default=1800, help="单条 test_cmd 超时（秒）")
    parser.add_argument("--no-network", dest="no_network", action="store_true",
                        help="禁止 clone（只用本地缓存；离线与测试用）")
    parser.add_argument("--allow-test-edits", dest="allow_test_edits",
                        action="store_true",
                        help="predictions 模式豁免完整性 critical（保留痕迹）")
    parser.add_argument("--f2p-only", dest="f2p_only", action="store_true",
                        help="只跑 F2P 判分点（Live 全量 P2P 成本过高时的可行性"
                             "口径；结果记 f2p_passed，不计 resolved）")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="只出计划，不建环境不触网")
    parser.add_argument("--force", action="store_true",
                        help="已 DONE 的实例也重跑")
    argv = parser.parse_args()

    tasks_path = Path(argv.tasks)
    if not tasks_path.is_file():
        return _param_error("任务清单不存在: %s" % tasks_path)
    try:
        tasks = _pro().load_tasks(tasks_path)
    except (OSError, ValueError) as exc:
        return _param_error("任务清单解析失败: %s" % exc)
    wanted = [item.strip() for item in argv.instances.split(",") if item.strip()]
    if not wanted:
        wanted = list(tasks)
    missing = [iid for iid in wanted if iid not in tasks]
    if missing:
        return _param_error("任务清单缺少实例: %s" % missing)
    preds = {}
    if argv.mode == "predictions":
        pred_path = Path(argv.predictions)
        if not argv.predictions or not pred_path.is_file():
            return _param_error("predictions 模式必须提供 --predictions")
        try:
            preds = _pro().load_predictions(pred_path)
        except (OSError, ValueError) as exc:
            return _param_error("预测文件解析失败: %s" % exc)
        missing_pred = [iid for iid in wanted if iid not in preds]
        if missing_pred:
            return _param_error("预测文件缺少实例: %s" % missing_pred)
    if argv.limit and argv.limit > 0:
        wanted = wanted[:argv.limit]
    selected = {}
    for iid in wanted:
        task = dict(tasks[iid])
        for key in ("fail_to_pass", "pass_to_pass", "test_cmds",
                    "setup_cmds"):
            task[key] = _pro()._as_list(task.get(key))
        if argv.mode == "predictions":
            task["candidate_patch"] = preds[iid].get("model_patch") or ""
        selected[iid] = task
    bad = []
    for iid, task in selected.items():
        absent = [key for key in ("repo", "base_commit", "test_patch")
                  if not str(task.get(key) or "").strip()]
        if not task["fail_to_pass"] or not task["test_cmds"]:
            absent.append("fail_to_pass/test_cmds")
        if argv.mode in ("gold", "predictions") and \
                not str(task.get("gold_patch") or task.get("candidate_patch")
                        or "").strip():
            absent.append("gold_patch/candidate_patch")
        if absent:
            bad.append({iid: absent})
    if bad:
        return _param_error("任务字段缺失: %s" % json.dumps(bad,
                                                            ensure_ascii=False))

    Path(argv.out).mkdir(parents=True, exist_ok=True)
    if argv.dry_run:
        return dry_run(selected, argv)

    ledger_path = Path(argv.out) / "live-sample-ledger.json"
    ledger = {"results": []}
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ledger = {"results": []}
        # --force 只重跑目标 key，不得丢弃其他台账行（round-51 真坑，
        # 与 pro-sample 同根因：单实例 --force 曾覆盖全量台账）。
        ledger.setdefault("results", [])
    done_keys = {row.get("key") or "%s|%s" % (row.get("instance_id"),
                                              row.get("mode"))
                 for row in ledger["results"]
                 if row.get("state") in ("resolved", "unresolved",
                                         "baseline_ok", "f2p_passed")}
    run_results = []
    started = time.monotonic()
    for iid, task in selected.items():
        key = "%s|%s" % (iid, argv.mode)
        if key in done_keys and not argv.force:
            _log("%s 已 DONE，跳过" % iid)
            continue
        _log("开始 %s（%s）" % (iid, argv.mode))
        try:
            result = run_one(task, argv)
        except (OSError, ValueError, KeyError) as exc:
            result = {"instance_id": iid, "key": key, "mode": argv.mode,
                      "state": "infra_error", "resolved": None,
                      "detail": "驱动异常: %s" % exc}
        result.setdefault("key", key)
        result.setdefault("mode", argv.mode)
        _log("%s → %s" % (iid, result["state"]))
        ledger["results"] = [row for row in ledger["results"]
                             if (row.get("key") or "%s|%s" % (
                                 row.get("instance_id"), row.get("mode")))
                             != key] + [result]
        run_results.append(result)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                               encoding="utf-8", newline="\n")

    current = [row for row in ledger["results"] if row.get("mode") == argv.mode]
    counts = {}
    for row in current:
        counts[row.get("state", "?")] = counts.get(row.get("state", "?"), 0) + 1
    failed_states = {"blocked_source", "env_failed", "malformed_test_patch",
                     "malformed_patch", "malformed_node_ids",
                     "integrity_flagged", "patch_apply_failed",
                     "prepare_failed", "infra_error",
                     "baseline_unexpected", "baseline_p2p_failed"}
    failed = [row["instance_id"] for row in current
              if row.get("state") in failed_states]
    export = _export_sbcli(argv, current)
    _emit({"ok": not failed, "mode": argv.mode, "total": len(current),
           "run_this_time": len(run_results), "counts": counts,
           "resolved": sum(1 for row in current if row.get("resolved") is True),
           "f2p_passed": counts.get("f2p_passed", 0),
           "blocked_source": counts.get("blocked_source", 0),
           "env_failed": counts.get("env_failed", 0),
           "failed": failed,
           "elapsed_sec": round(time.monotonic() - started, 3),
           "ledger": str(ledger_path),
           "sbcli_export": export})
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
