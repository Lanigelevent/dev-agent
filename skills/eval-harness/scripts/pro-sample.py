#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SWE-bench Pro 评测驱动器：把「任务清单 → 镜像就绪 → 容器内重置/打测试补丁 →
应用候选补丁 → pytest -rA → 判定 → 台账」串成单命令（round-50 阶段二适配层）。

与既有驱动的分工：
    gold-sample.py    SWE-bench Lite 官方 harness（容器外 eval/report）
    deepswe-sample.py DeepSWE（ECR 镜像 + reward.txt）
    pro-sample.py     SWE-bench Pro v2（自管容器：before_repo_set_cmd 字段
                      + selected_test_files_to_run 直接落成 pytest 参数）
本驱动不下载数据集、不解析 parquet：任务清单由 .venv 侧一次性抽取成 JSONL
（治理壳只依赖标准库），每行字段：
    instance_id / repo / base_commit / docker_image / test_patch / gold_patch /
    fail_to_pass / pass_to_pass / before_repo_set_cmd /
    selected_test_files_to_run
fail_to_pass / pass_to_pass / selected_test_files_to_run 允许数组或 JSON 字符串。

环境适配字段（可选，逐实例显式写在任务行里，不硬编码到驱动）：
    pre_test_cmd   pytest 前在容器内执行的命令（如启动常驻 Xvfb）
    env            追加给 pytest 的环境变量 dict（如 DISPLAY /
                   QTWEBENGINE_DISABLE_SANDBOX）
    pytest_args    追加到 pytest 的参数列表（如 ["-p", "no:xvfb"]）
适配只修「跑不起来」的环境，不改判分点与期望；dry-run 会原样打印最终命令。

判分口径（round-49 报告 §2 的代码化，不发明新口径）：
    1. docker run -d -v <staging>:/tests <image> tail -f /dev/null
    2. docker exec bash -lc "cd /app\\n<before_repo_set_cmd>"
       （数据集字段已含 git reset/clean/checkout + git apply test_patch）
    3. gold / predictions 模式再 git apply /tests/candidate.patch
    4. cd /app && python -m pytest -rA <selected_test_files_to_run...>
    5. 按 `PASSED|FAILED|...  <node id>` 逐项对账；同一 node 取最后一次出现。
       resolved = F2P 全 PASSED 且 P2P 全 PASSED（SKIPPED/XFAIL/缺失都不算过）。
    baseline 模式不打候选补丁：期望 F2P 一个都不过且 P2P 全过，用于环境自检；
    baseline_unexpected（F2P 有通过）与 baseline_p2p_failed 都按失败计（退出码 1）。

补丁闸与 agent-sample/deepswe-sample 同源（`_patch_well_formed` /
`_patch_integrity`，按路径加载复用，不复制实现）：
    - test_patch 结构损坏 → malformed_test_patch（环境不可信，不计结果）；
    - gold 补丁结构损坏 → malformed_patch；
    - predictions 补丁结构损坏 → malformed_patch；critical 完整性命中 →
      integrity_flagged（`--allow-test-edits` 可豁免但保留 critical 痕迹），
      两者都不参加 resolved。
镜像铁律（硬约束 8）：镜像缺失时只经 `--mirror`（缺省 ghcr.nju.edu.cn）走
docker-image-fetch.py 四阶段拉取；`--no-fetch` 下缺失一律 blocked_source，
样本不静默丢弃（记入台账与汇总计数）。镜像本地 tag 依次探测
`<mirror>/<repo>:<tag>` → 数据集 docker_image → `<repo>:<tag>`。

用法示例:
    py pro-sample.py --tasks datasets/swebench/pro/gate-3.jsonl \\
        --instances <id1>,<id2> --mode baseline --out datasets/swebench/pro-runs
    py pro-sample.py --tasks <jsonl> --mode gold --out <目录>
    py pro-sample.py --tasks <jsonl> --mode predictions --predictions p.jsonl --out <目录>
    py pro-sample.py --tasks <jsonl> --mode predictions --patches <agent补丁根目录> --out <目录>
    py pro-sample.py --tasks <jsonl> --dry-run          # 只出计划，不碰 docker

退出码: 0 = 选定实例全部达到期望状态（gold/pred 的 resolved/unresolved 均算
完成，baseline 的 baseline_ok 算完成）；1 = 存在失败状态（blocked_source /
malformed / integrity_flagged / patch_apply_failed / prepare_failed /
infra_error / baseline_unexpected / baseline_p2p_failed）；2 = 参数或输入错误。
stdout 单 JSON 文档；进度与诊断走 stderr。
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FETCH = ROOT / "scripts" / "docker-image-fetch.py"
DEFAULT_MIRROR = "ghcr.nju.edu.cn"
NODE_RE = re.compile(
    r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(.+?)\s*$")
_DEEPSWE = None
_AGENT = None


def _deepswe():
    """按路径加载 deepswe-sample.py，复用补丁双闸（单一实现，不复制）。"""
    global _DEEPSWE
    if _DEEPSWE is None:
        path = Path(__file__).with_name("deepswe-sample.py")
        spec = importlib.util.spec_from_file_location("deepswe_sample_shared",
                                                      path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _DEEPSWE = mod
    return _DEEPSWE


def _agent_sample():
    """按路径加载 agent-sample.py，复用补丁收集/版本选择（单一实现）。"""
    global _AGENT
    if _AGENT is None:
        path = Path(__file__).with_name("agent-sample.py")
        spec = importlib.util.spec_from_file_location("agent_sample_shared",
                                                      path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _AGENT = mod
    return _AGENT


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _log(message):
    sys.stderr.write("[pro-sample] %s\n" % message)
    sys.stderr.flush()


def _run(cmd, timeout):
    """子进程统一入口；超时返回 rc=124 而不是抛异常（失败要入台账）。"""
    try:
        p = subprocess.run([str(c) for c in cmd], shell=False,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout
    return p.returncode, p.stdout or "", p.stderr or ""


def _json_or_none(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def _as_list(value):
    """数组 / JSON 字符串 / 换行列表 → list[str]（数据集两种形态都出现过）。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            return [str(v).strip() for v in data if str(v).strip()]
        except ValueError:
            return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_tasks(path):
    """读任务 JSONL；返回 {instance_id: task dict}（字段校验在 main 做）。"""
    tasks = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        iid = str(row.get("instance_id") or "").strip()
        if iid:
            tasks[iid] = row
    return tasks


def load_predictions(path):
    preds = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        preds[str(row.get("instance_id") or "").strip()] = row
    preds.pop("", None)
    return preds


def split_ref(ref):
    """`[registry/]owner/repo[:tag]` → (registry, path, tag)。

    仅当首段像域名（含 `.` / `:` / 为 localhost）才视为 registry，避免把
    `owner/repo:tag` 的 owner 误判。
    """
    text = str(ref or "").strip()
    registry = ""
    if "/" in text:
        head, rest = text.split("/", 1)
        if "." in head or ":" in head or head == "localhost":
            registry, text = head, rest
    if ":" in text:
        path, tag = text.rsplit(":", 1)
    else:
        path, tag = text, "latest"
    return registry, path, tag


def image_candidates(task, mirror):
    """本地 tag 探测顺序：镜像源前缀 → 数据集原名 → 去 registry 的短名。"""
    registry, path, tag = split_ref(task.get("docker_image", ""))
    cands = []
    if mirror and registry:
        cands.append("%s/%s:%s" % (mirror, path, tag))
    if registry:
        cands.append("%s/%s:%s" % (registry, path, tag))
    cands.append("%s:%s" % (path, tag))
    out = []
    for cand in cands:
        if cand and cand not in out:
            out.append(cand)
    return out


def docker_bin(explicit=""):
    """docker 可执行文件：显式参数 → Docker Desktop 用户级安装 → PATH。"""
    if explicit:
        return explicit if Path(explicit).is_file() else shutil.which(explicit) or ""
    import os
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cand = Path(local) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if cand.is_file():
            return str(cand)
    return shutil.which("docker") or ""


def docker_images(docker):
    """本地镜像 tag 集合；docker 缺席返回 None（与「空集合」区分）。"""
    if not docker:
        return None
    rc, out, _ = _run([docker, "images", "--format",
                       "{{.Repository}}:{{.Tag}}"], timeout=60)
    if rc != 0:
        return None
    return {line.strip() for line in out.splitlines() if line.strip()}


def find_local_image(task, mirror, images):
    for cand in image_candidates(task, mirror):
        if cand in images:
            return cand
    return ""


def ensure_image(task, argv, images):
    """确保镜像在本地；返回 (local_ref, state, detail)。

    state: local / fetched / blocked。blocked 时把原因放 detail（不静默丢）。
    """
    if images is None:
        images = set()
    local = find_local_image(task, argv.mirror, images)
    if local:
        return local, "local", ""
    if argv.no_fetch:
        return "", "blocked", "镜像不在本地且已指定 --no-fetch"
    if not argv.mirror:
        return "", "blocked", "镜像不在本地且未提供 --mirror"
    registry, path, tag = split_ref(task.get("docker_image", ""))
    repo = "%s:%s" % (path, tag)
    cache = Path(argv.out) / "imagecache" / _short_tag(task["instance_id"])
    _log("拉取镜像 %s（mirror=%s）" % (repo, argv.mirror))
    rc, out, err = _run([sys.executable, FETCH, "plan", "--image", repo,
                         "--mirror", argv.mirror, "--out", str(cache)],
                        timeout=180)
    if rc != 0:
        return "", "blocked", "plan 失败: %s" % ((out or err).strip()[:300])
    rc, out, err = _run([sys.executable, FETCH, "fetch", "--image", repo,
                         "--mirror", argv.mirror,
                         "--plan", str(cache / "plan.json"),
                         "--out", str(cache),
                         "--retries", argv.retries,
                         "--segments", argv.segments,
                         "--workers", argv.workers], timeout=7200)
    if rc != 0:
        detail = (_json_or_none(out) or {}).get("error") or err
        return "", "blocked", "fetch 失败: %s" % str(detail).strip()[:300]
    local_ref = image_candidates(task, argv.mirror)[0]
    archive = cache / ("%s.tar" % _short_tag(task["instance_id"]))
    rc, out, err = _run([sys.executable, FETCH, "assemble",
                         "--plan", str(cache / "plan.json"),
                         "--blobs", str(cache), "--out", str(archive),
                         "--image", local_ref], timeout=3600)
    if rc != 0:
        return "", "blocked", "assemble 失败: %s" % ((out or err).strip()[:300])
    rc, out, err = _run([sys.executable, FETCH, "load",
                         "--archive", str(archive),
                         "--docker", argv.docker], timeout=1800)
    if rc != 0:
        detail = (_json_or_none(out) or {}).get("error") or err
        return "", "blocked", "load 失败: %s" % str(detail).strip()[:300]
    if images is not None:
        images.add(local_ref)
    return local_ref, "fetched", ""


def _short_tag(text):
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:12]


def _container_name(task, mode):
    return "pro-sample-%s" % _short_tag("%s|%s" % (task["instance_id"], mode))


def parse_pytest_output(text):
    """`-rA` 摘要行 → {node: status}；同一 node 取最后一次。

    `-rA` 的 skip 汇总行形如 `SKIPPED [1] path:line: reason`，第二列是计数
    不是 node id——以 `[` 开头的 token 一律不当判分点。
    """
    results = {}
    for line in (text or "").splitlines():
        match = NODE_RE.match(line.strip())
        if not match:
            continue
        node = match.group(2)
        if node.startswith("["):
            continue
        results[node] = match.group(1)
    return results


def lookup_node(results, node):
    """精确匹配优先；再容忍 ` - reason` 尾注与 rootdir 前缀差异。

    pytest 短摘要里 FAILED/SKIPPED 行可能带 ` - <reason>`；参数化 node 本身
    也可能含空格（round-51 实踩 `test_data[Hello World! ...]` 被判 missing）。
    """
    node = node.strip()
    if node in results:
        return results[node]
    cands = [key for key in results
             if key.startswith(node + " - ") or key.endswith(node)
             or node.endswith(key)]
    return results[cands[0]] if len(cands) == 1 else None


def judge(results, fail_to_pass, pass_to_pass, mode):
    """返回 (verdict, detail)：verdict ∈ resolved / unresolved /
    baseline_ok / baseline_unexpected / baseline_p2p_failed。

    多测点（同一 node 在多个测试文件重复定义）不做特殊处理：pytest 输出
    本身会由 node 唯一化，重复定义会被 pytest 拒绝收集并体现为 missing。
    """
    f2p = {node: lookup_node(results, node) for node in fail_to_pass}
    p2p = {node: lookup_node(results, node) for node in pass_to_pass}
    missing_f2p = [n for n, s in f2p.items() if s is None]
    missing_p2p = [n for n, s in p2p.items() if s is None]
    p2p_pass = [n for n, s in p2p.items() if s == "PASSED"]
    detail = {
        "fail_to_pass": {"total": len(f2p),
                         "passed": sum(1 for s in f2p.values()
                                       if s == "PASSED"),
                         "missing": missing_f2p[:10],
                         "statuses": {n: s for n, s in list(f2p.items())[:10]}},
        "pass_to_pass": {"total": len(p2p),
                         "passed": len(p2p_pass),
                         "missing": missing_p2p[:10]},
    }
    if mode == "baseline":
        if missing_f2p or missing_p2p:
            verdict = "baseline_unexpected"
            detail["reason"] = "基线判分点未被收集（测试补丁/环境不可信）"
        elif any(s == "PASSED" for s in f2p.values()):
            verdict = "baseline_unexpected"
            detail["reason"] = "F2P 在基线即通过（判分点失效或镜像不干净）"
        elif len(p2p_pass) != len(p2p):
            verdict = "baseline_p2p_failed"
            detail["reason"] = "P2P 在基线失败"
        else:
            verdict = "baseline_ok"
        return verdict, detail
    resolved = (bool(f2p) and not missing_f2p and not missing_p2p
                and all(s == "PASSED" for s in f2p.values())
                and all(s == "PASSED" for s in p2p.values()))
    return ("resolved" if resolved else "unresolved"), detail


def _patch_text(task, key):
    text = task.get(key) or ""
    if isinstance(text, list):
        text = "\n".join(str(part) for part in text)
    return str(text)


def _adaptation(task):
    """任务级环境适配：返回 (pre_test_cmd, env dict, pytest_args list)。

    只接受合法环境变量名（防拼接注入）；其余字段原样透传，dry-run 可见。
    """
    pre = str(task.get("pre_test_cmd") or "").strip()
    env = task.get("env") or {}
    if not isinstance(env, dict):
        env = {}
    env = {str(k): str(v) for k, v in env.items()
           if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", str(k))}
    return pre, env, _as_list(task.get("pytest_args"))


def pytest_command(task):
    """最终 pytest 命令（含任务级 env 前缀与附加参数）；dry-run 与执行共用。"""
    _, env, extra = _adaptation(task)
    prefix = "".join("%s=%s " % (key, shlex.quote(value))
                     for key, value in env.items())
    files = _as_list(task.get("selected_test_files_to_run"))
    cmd = "cd /app && %spython -m pytest -rA" % prefix
    if extra:
        cmd += " " + " ".join(shlex.quote(arg) for arg in extra)
    if files:
        cmd += " " + " ".join(shlex.quote(item) for item in files)
    return cmd


def _write_patch(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _gate(task, argv):
    """补丁双闸（应用前）：返回 (state, detail, note)；放行时 state 为空。

    note 记录「critical 已豁免」等痕迹，豁免不等于无痕。
    """
    test_patch = _patch_text(task, "test_patch")
    if not test_patch.strip():
        return "malformed_test_patch", "test_patch 为空", None
    stage = Path(argv.out) / _short_tag(task["instance_id"]) / "gate-test.patch"
    _write_patch(stage, test_patch)
    verdict = _deepswe()._patch_well_formed(stage)
    if not verdict.get("ok"):
        return "malformed_test_patch", (verdict.get("issues") or [""])[:3], None
    if argv.mode == "baseline":
        return "", "", None
    if argv.mode == "gold":
        gold = _patch_text(task, "gold_patch")
        if not gold.strip():
            return "malformed_patch", "gold_patch 为空", None
        stage = Path(argv.out) / _short_tag(task["instance_id"]) / "gate-gold.patch"
        _write_patch(stage, gold)
        verdict = _deepswe()._patch_well_formed(stage)
        if not verdict.get("ok"):
            return "malformed_patch", (verdict.get("issues") or [""])[:3], None
        return "", "", None
    candidate = _patch_text(task, "candidate_patch")
    if not candidate.strip():
        return "malformed_patch", "预测补丁为空", None
    stage = Path(argv.out) / _short_tag(task["instance_id"]) / "gate-candidate.patch"
    _write_patch(stage, candidate)
    verdict = _deepswe()._patch_well_formed(stage)
    if not verdict.get("ok"):
        return "malformed_patch", (verdict.get("issues") or [""])[:3], None
    integrity = _deepswe()._patch_integrity(stage)
    critical = integrity.get("critical") or []
    if critical and not argv.allow_test_edits:
        return "integrity_flagged", critical[:5], None
    if critical:
        return "", "", {"waived_critical": critical[:5]}
    return "", "", None


def prepare_task(task, argv, docker, images):
    """单实例全链：闸 → 镜像 → 容器 → apply → pytest → 判定。返回结果 dict。"""
    started = time.monotonic()
    iid = task["instance_id"]
    mode = argv.mode
    out_dir = Path(argv.out) / _short_tag(iid) / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    result = {"instance_id": iid, "key": "%s|%s" % (iid, mode), "mode": mode,
              "repo": task.get("repo"), "state": "?", "resolved": None,
              "image": task.get("docker_image"), "meta": str(meta_path)}
    state, detail, gate_note = _gate(task, argv)
    if gate_note:
        result["gate_note"] = gate_note
    if state:
        result.update(state=state, error=detail)
        return _finish(result, started, meta_path)
    if not docker:
        result.update(state="infra_error", error="docker 不可执行")
        return _finish(result, started, meta_path)
    image_ref, image_state, why = ensure_image(task, argv, images)
    result["image_ref"] = image_ref
    result["image_state"] = image_state
    if not image_ref:
        result.update(state="blocked_source", error=why)
        return _finish(result, started, meta_path)
    staging = (out_dir / "tests").resolve()
    _write_patch(staging / "test_patch.patch", _patch_text(task, "test_patch"))
    if mode == "gold":
        _write_patch(staging / "candidate.patch",
                     _patch_text(task, "gold_patch"))
    elif mode == "predictions":
        _write_patch(staging / "candidate.patch",
                     _patch_text(task, "candidate_patch"))
    name = _container_name(task, mode)
    _run([docker, "rm", "-f", name], timeout=60)
    _log("%s [%s] 启动容器 %s（镜像 %s）" % (iid[-24:], mode, name, image_ref))
    rc, out, err = _run([docker, "run", "-d", "--name", name,
                         "-v", "%s:/tests" % staging, image_ref,
                         "tail", "-f", "/dev/null"], timeout=120)
    if rc != 0:
        result.update(state="infra_error",
                      error="docker run 失败: %s" % (err or out).strip()[:300])
        return _finish(result, started, meta_path)
    apply_log = []
    try:
        before = str(task.get("before_repo_set_cmd") or "").strip()
        if not before:
            result.update(state="prepare_failed",
                          error="before_repo_set_cmd 为空")
            return _finish(result, started, meta_path)
        rc, out, err = _exec(docker, name, "cd /app\n" + before,
                             argv.exec_timeout)
        apply_log.append({"stage": "prepare", "rc": rc,
                          "tail": (out + err).strip()[-1200:]})
        if rc != 0:
            result.update(state="prepare_failed",
                          error="before_repo_set_cmd 失败（rc=%s）" % rc)
            return _finish(result, started, meta_path)
        if mode in ("gold", "predictions"):
            rc, out, err = _exec(docker, name,
                                 "cd /app && git apply --verbose "
                                 "/tests/candidate.patch", 300)
            apply_log.append({"stage": "apply_candidate", "rc": rc,
                              "tail": (out + err).strip()[-800:]})
            if rc != 0:
                result.update(state="patch_apply_failed",
                              error="候选补丁 git apply 失败（rc=%s）" % rc)
                return _finish(result, started, meta_path)
        pre, env, extra = _adaptation(task)
        if pre:
            rc, out, err = _exec(docker, name, "cd /app\n" + pre, 120)
            apply_log.append({"stage": "pre_test", "rc": rc,
                              "tail": (out + err).strip()[-500:]})
            if rc != 0:
                result.update(state="prepare_failed",
                              error="pre_test_cmd 失败（rc=%s）" % rc)
                return _finish(result, started, meta_path)
        if pre or env or extra:
            result["adaptation"] = {"pre_test_cmd": pre or None,
                                    "env": sorted(env), "pytest_args": extra}
        files = _as_list(task.get("selected_test_files_to_run"))
        if not files:
            result.update(state="prepare_failed",
                          error="selected_test_files_to_run 为空")
            return _finish(result, started, meta_path)
        pytest_cmd = pytest_command(task)
        started_test = time.monotonic()
        rc, out, err = _exec(docker, name, pytest_cmd, argv.exec_timeout)
        test_seconds = round(time.monotonic() - started_test, 3)
        log_path = out_dir / "pytest.log"
        log_path.write_text((out or "") + "\n" + (err or ""),
                            encoding="utf-8", errors="replace", newline="\n")
        if rc == 124:
            result.update(state="infra_error",
                          error="pytest 超时（%ss）" % argv.exec_timeout)
            return _finish(result, started, meta_path)
        results = parse_pytest_output(out)
        if not results:
            result.update(state="infra_error",
                          error="pytest 无判分行（rc=%s），见 pytest.log" % rc)
            return _finish(result, started, meta_path)
        verdict, detail = judge(results, _as_list(task.get("fail_to_pass")),
                                _as_list(task.get("pass_to_pass")), mode)
        result.update(state=verdict,
                      resolved=(True if verdict == "resolved" else
                                False if mode != "baseline" else None),
                      judge=detail, pytest_sec=test_seconds, rc=rc,
                      pytest_log=str(log_path), apply=apply_log)
        return _finish(result, started, meta_path)
    finally:
        _run([docker, "rm", "-f", name], timeout=60)


def _finish(result, started, meta_path):
    result["elapsed_sec"] = round(time.monotonic() - started, 3)
    try:
        meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                             encoding="utf-8", newline="\n")
    except OSError:
        pass
    return result


def _exec(docker, name, script, timeout):
    """docker exec：优先 bash -lc，镜像无 bash 时退回 sh -lc。"""
    rc, out, err = _run([docker, "exec", name, "/bin/bash", "-lc", script],
                        timeout=timeout)
    missing_bash = (rc != 0 and "/bin/bash" in (err or "")
                    and ("no such file" in (err or "").lower()
                         or "executable file not found" in (err or "").lower()))
    if missing_bash:
        rc, out, err = _run([docker, "exec", name, "/bin/sh", "-lc", script],
                            timeout=timeout)
    return rc, out, err


def dry_run(tasks, argv):
    docker = docker_bin(argv.docker)
    images = docker_images(docker)
    plan = {"ok": True, "dry_run": True, "mode": argv.mode,
            "docker": docker or None,
            "docker_images_known": images is not None,
            "tasks": []}
    for iid, task in tasks.items():
        _, _, tag = split_ref(task.get("docker_image", ""))
        staging = (Path(argv.out) / _short_tag(iid) / argv.mode /
                   "tests").resolve()
        files = _as_list(task.get("selected_test_files_to_run"))
        pre, env, extra = _adaptation(task)
        item = {
            "instance_id": iid,
            "repo": task.get("repo"),
            "image_candidates": image_candidates(task, argv.mirror),
            "local_image": (find_local_image(task, argv.mirror, images)
                            if images is not None else ""),
            "staging": str(staging),
            "fail_to_pass": len(_as_list(task.get("fail_to_pass"))),
            "pass_to_pass": len(_as_list(task.get("pass_to_pass"))),
            "selected_test_files": len(files),
            "prepare_cmd": "cd /app\n" + str(task.get("before_repo_set_cmd")
                                             or "").strip(),
            "pre_test_cmd": pre or None,
            "env": sorted(env),
            "pytest_args": extra,
            "apply_cmd": ("cd /app && git apply --verbose /tests/"
                          "candidate.patch" if argv.mode != "baseline" else ""),
            "pytest_cmd": pytest_command(task),
            "tag": tag,
        }
        plan["tasks"].append(item)
    _emit(plan)
    return 0


def main():
    parser = argparse.ArgumentParser(description="SWE-bench Pro 评测驱动器")
    parser.add_argument("--tasks", required=True,
                        help="任务 JSONL（每行一个实例，字段见模块 docstring）")
    parser.add_argument("--instances", default="",
                        help="逗号分隔实例 id（缺省=清单全部）")
    parser.add_argument("--limit", type=int, default=0,
                        help="按清单顺序取前 N 条（0=不限制）")
    parser.add_argument("--mode", choices=("baseline", "gold", "predictions"),
                        default="gold", help="baseline=只打测试补丁；gold/predictions=再打候选补丁")
    parser.add_argument("--predictions", default="",
                        help="predictions 模式的补丁 jsonl（instance_id + model_patch）")
    parser.add_argument("--patches", default="",
                        help="predictions 模式的 agent 补丁根目录"
                             "（<iid>/edits.patch，与 --predictions 互斥）")
    parser.add_argument("--out", required=True, help="产物目录")
    parser.add_argument("--mirror", default=DEFAULT_MIRROR,
                        help="国内镜像源（硬约束 8；空串=禁止拉取）")
    parser.add_argument("--no-fetch", action="store_true",
                        help="镜像缺失时不拉取，记 blocked_source")
    parser.add_argument("--docker", default="", help="docker 可执行文件")
    parser.add_argument("--exec-timeout", dest="exec_timeout", type=int,
                        default=1800, help="单次容器内命令超时（秒）")
    parser.add_argument("--retries", type=int, default=12)
    parser.add_argument("--segments", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--allow-test-edits", dest="allow_test_edits",
                        action="store_true",
                        help="predictions 模式豁免完整性 critical（保留痕迹）")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="只输出计划（不碰 docker、不写产物）")
    parser.add_argument("--force", action="store_true",
                        help="已 DONE 的实例也重跑")
    argv = parser.parse_args()

    tasks_path = Path(argv.tasks)
    if not tasks_path.is_file():
        return _param_error("任务清单不存在: %s" % tasks_path)
    try:
        tasks = load_tasks(tasks_path)
    except (OSError, ValueError) as exc:
        return _param_error("任务清单解析失败: %s" % exc)
    wanted = [item.strip() for item in argv.instances.split(",") if item.strip()]
    if not wanted:
        wanted = list(tasks)
    missing = [iid for iid in wanted if iid not in tasks]
    if missing:
        return _param_error("任务清单缺少实例: %s" % missing)
    patches_dir = Path(argv.patches) if argv.patches else None
    patches_provenance = []
    if argv.mode == "predictions":
        if bool(argv.predictions) == bool(argv.patches):
            return _param_error("predictions 模式必须且只能提供 "
                                "--predictions 或 --patches 之一")
        if patches_dir is not None:
            # agent 侧入口：直接把编码循环的 edits.patch 目录装配成预测文件，
            # 版本选择/补丁校验证据复用 agent-sample.collect_patches（单一实现）。
            if not patches_dir.is_dir():
                return _param_error("补丁目录不存在: %s" % patches_dir)
            try:
                patches, patches_provenance = _agent_sample().collect_patches(
                    patches_dir, set(wanted))
            except (OSError, ValueError) as exc:
                return _param_error("补丁收集失败: %s" % exc)
            if not patches:
                return _param_error("补丁目录内无有效补丁: %s" % patches_dir)
            preds = {iid: {"instance_id": iid, "model_patch": text}
                     for iid, text in patches.items()}
        else:
            pred_path = Path(argv.predictions)
            if not pred_path.is_file():
                return _param_error("预测文件不存在: %s" % pred_path)
            try:
                preds = load_predictions(pred_path)
            except (OSError, ValueError) as exc:
                return _param_error("预测文件解析失败: %s" % exc)
    else:
        preds = {}
    if argv.mode == "predictions":
        missing_pred = [iid for iid in wanted if iid not in preds]
        if missing_pred:
            return _param_error("预测文件缺少实例: %s" % missing_pred)
    if argv.limit and argv.limit > 0:
        wanted = wanted[:argv.limit]
    selected = {}
    for iid in wanted:
        task = dict(tasks[iid])
        if argv.mode == "predictions":
            task["candidate_patch"] = preds[iid].get("model_patch") or ""
        for key in ("fail_to_pass", "pass_to_pass",
                    "selected_test_files_to_run"):
            task[key] = _as_list(task.get(key))
        selected[iid] = task
    bad = []
    for iid, task in selected.items():
        absent = [key for key in ("docker_image", "test_patch",
                                  "before_repo_set_cmd")
                  if not str(task.get(key) or "").strip()]
        # pass_to_pass 允许为空：Pro 数据集存在零 P2P 实例（round-51 实测
        # ansible-11c1777d）。judge 已按「只要求 F2P 非空」判分，旧校验把
        # 这类样本永远挡在门外，等于把「没有 P2P 可跑」误判成任务字段缺失。
        if not task["fail_to_pass"] or not task["selected_test_files_to_run"]:
            absent.append("fail_to_pass/selected_test_files_to_run")
        if absent:
            bad.append({iid: absent})
    if bad:
        return _param_error("任务字段缺失: %s" % json.dumps(bad, ensure_ascii=False))
    Path(argv.out).mkdir(parents=True, exist_ok=True)
    predictions_path = ""
    if argv.mode == "predictions" and patches_dir is not None:
        predictions_path = str(Path(argv.out) / "predictions-agent.jsonl")
        with open(predictions_path, "w", encoding="utf-8", newline="\n") as fh:
            for iid in wanted:
                fh.write(json.dumps({"instance_id": iid,
                                     "model_name_or_path": "dev-agent",
                                     "model_patch": preds[iid]["model_patch"]},
                                    ensure_ascii=False) + "\n")
        (Path(argv.out) / "patch-provenance.json").write_text(
            json.dumps({"source": str(patches_dir),
                        "instances": patches_provenance},
                       ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
        _log("装配预测 %d 条 → %s" % (len(wanted), predictions_path))
    if argv.dry_run:
        return dry_run(selected, argv)

    docker = docker_bin(argv.docker)
    if not docker:
        _log("docker 不可执行：所有实例将记为 infra_error")
    images = docker_images(docker)
    ledger_path = Path(argv.out) / "pro-sample-ledger.json"
    ledger = {"results": []}
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ledger = {"results": []}
        # --force 只用于重跑 DONE 样本，不得丢弃其他台账行（round-51 真坑：
        # 单实例 --force 曾把 20 行台账覆盖成 1 行）。
        ledger.setdefault("results", [])
    done_keys = {row.get("key") or "%s|%s" % (row.get("instance_id"),
                                              row.get("mode"))
                 for row in ledger["results"]
                 if row.get("state") in ("resolved", "unresolved",
                                         "baseline_ok")}
    run_results = []
    started = time.monotonic()
    for iid, task in selected.items():
        key = "%s|%s" % (iid, argv.mode)
        if key in done_keys and not argv.force:
            _log("%s 已完成，跳过（--force 重跑）" % iid[-24:])
            continue
        _log("开始 %s（%s）" % (iid[-24:], argv.mode))
        result = prepare_task(task, argv, docker, images)
        _log("%s → %s" % (iid[-24:], result["state"]))
        ledger["results"] = [row for row in ledger["results"]
                             if (row.get("key") or "%s|%s" % (
                                 row.get("instance_id"), row.get("mode")))
                             != key] + [result]
        run_results.append(result)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                               encoding="utf-8", newline="\n")

    current = [row for row in ledger["results"]
               if row.get("mode") == argv.mode]
    counts = {}
    for row in current:
        counts[row.get("state", "?")] = counts.get(row.get("state", "?"), 0) + 1
    failed_states = {"blocked_source", "malformed_test_patch",
                     "malformed_patch", "integrity_flagged",
                     "patch_apply_failed", "prepare_failed", "infra_error",
                     "baseline_unexpected", "baseline_p2p_failed"}
    failed = [row["instance_id"] for row in current
              if row.get("state") in failed_states]
    _emit({"ok": not failed, "mode": argv.mode,
           "total": len(current), "run_this_time": len(run_results),
           "counts": counts,
           "resolved": sum(1 for row in current if row.get("resolved") is True),
           "blocked_source": counts.get("blocked_source", 0),
           "malformed": counts.get("malformed_patch", 0)
           + counts.get("malformed_test_patch", 0),
           "integrity_flagged": counts.get("integrity_flagged", 0),
           "failed": failed,
           "elapsed_sec": round(time.monotonic() - started, 3),
           "predictions": predictions_path,
           "ledger": str(ledger_path)})
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
