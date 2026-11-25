#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布闸：一键验证「可以打 tag」的全部前置条件（ROADMAP 3.5，D-035）。

用途：
    发布边界（docs/DECISIONS.md D-035）的唯一机械判据。**只读检查，绝不
    创建或推送 tag**；tag 仍由人工在 main 上打。七项检查全 PASS 才输出 ok：
      [R1] version_sync：真值 .zcode-plugin/plugin.json 的 version 与
           pyproject.toml / mcp/review_mcp.py SERVER_INFO / README 头条 /
           docs/DEVELOPMENT.md 发布口径 / docs/BASELINE-HISTORY.md 最近一条
           「version 升」沿革一致（v1.87.0 起沿革从 BASELINE.md 分卷；
           历史文件缺失时回退 BASELINE.md），
           且形如 X.Y.Z（真值源本身必须可解析）
      [R2] doc_freshness：doc-freshness.py（计数/版本 vs 真值）rc=0
      [R3] doc_drift：doc-drift.py 十五问 rc=0
      [R4] secret_scan / license_check：CI 同款门禁 rc=0
      [R5] suite_double_run：两份全量套件日志均「Ran N tests」+ OK，两次数
           相等且等于 discover 真值；--run-suite 则本闸当场顺序跑两遍
      [R6] git_state：工作树干净、当前分支为 main（--branch 可改）、
           若给 --tag 则必须是 v<version> 且尚未存在（tag 不复用版本号）

    日志「复用」与「当场执行」分开记：复用只证明日志内容自洽（sha256 +
    计数入库），不证明日志来自当前树；发布签核优先用 --run-suite。

    --only 只用于 CI 分项对账与调试：输出 partial=true，**不构成发布签核**。

用法示例：
    python release-gate.py --root . --tag v1.58.0 \
        --suite-log logs/suite-r57-run1.log --suite-log logs/suite-r57-run2.log \
        --out reports/release-gate/1.58.0/release-gate.json
    python release-gate.py --root . --tag v1.58.0 --run-suite
    python release-gate.py --root . --only version_sync      # CI 分项

退出码：
    0 = 七项全绿（若 --only 则所选检查全绿，仅作分项对账）
    1 = 有检查未通过（failed 列出检查 id）
    2 = 参数或环境错误（缺日志文件、日志重复、未知检查 id、
        --suite-log 与 --run-suite 同时给出等）
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import unittest
from datetime import datetime
from pathlib import Path

CHECKS = ("version_sync", "doc_freshness", "doc_drift", "secret_scan",
          "license_check", "suite_double_run", "git_state")
GATE_SCRIPTS = {
    "doc_freshness": "skills/self-iteration/scripts/doc-freshness.py",
    "doc_drift": "skills/self-iteration/scripts/doc-drift.py",
    "secret_scan": "skills/self-iteration/scripts/secret-scan.py",
    "license_check": "skills/self-iteration/scripts/license-check.py",
}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
README_VER = re.compile(r"\*\*版本 (\d+\.\d+\.\d+)\*\*")
MCP_VER = re.compile(r'SERVER_INFO\s*=\s*\{[^}\n]*"version"\s*:\s*"([^"]+)"')
BASELINE_VER = re.compile(r"version 升 \*{0,2}(\d+\.\d+\.\d+)")
DEV_VER = re.compile(r"当前\s*(\d+\.\d+\.\d+)")
RAN_RE = re.compile(r"Ran (\d+) tests? in ([\d.]+)s")
OK_RE = re.compile(r"^OK(?: \(skipped=(\d+)\))?\s*$", re.M)
FAILED_RE = re.compile(r"^FAILED\b", re.M)
PASSED_RE = re.compile(r"(\d+) passed")
FAILED_CNT_RE = re.compile(r"(\d+) failed")
ERROR_CNT_RE = re.compile(r"(\d+) error")
SKIPPED_CNT_RE = re.compile(r"(\d+) skipped")
PYTEST_DUR_RE = re.compile(r"in ([\d.]+)s")
NEWLINE = "\n"
# D-052（round-135 批准落地，2026-11-10）：600s 为硬挂死护栏并判红——
# 疑似挂死即阻断发布；300s 观测线已废，450s→540s 为「连续 3 轮」升级触发线（DECISIONS 口径）。
REDLINE_SEC = 600


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "check": "release-gate", "error": error})
    return 2


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _line_of(text, index):
    return text.count(NEWLINE, 0, index) + 1


def truth_version(root):
    """读真值源；失败返回 (None, 错误文本)。"""
    path = root / ".zcode-plugin" / "plugin.json"
    try:
        return json.loads(_read(path)).get("version"), None
    except (OSError, ValueError) as exc:
        return None, "真值源不可读: .zcode-plugin/plugin.json (%s)" % exc


def _source(root, name, rel, extract):
    """抽一处派生版本；extract(text) -> (value, line, error)。"""
    path = root / rel
    if not path.is_file():
        return {"source": name, "path": rel, "line": None,
                "value": None, "error": "文件缺失"}
    text = _read(path)
    value, line, error = extract(text)
    return {"source": name, "path": rel, "line": line,
            "value": value, "error": error}


def _regex_source(pattern):
    def extract(text):
        m = pattern.search(text)
        if not m:
            return None, None, "未找到版本字样"
        return m.group(1), _line_of(text, m.start()), None
    return extract


def _pyproject_ver(text):
    try:
        value = tomllib.loads(text)["project"]["version"]
    except (ValueError, KeyError, TypeError) as exc:
        return None, None, "project.version 不可读 (%s)" % exc
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return value, (_line_of(text, m.start()) if m else None), None


def _dev_ver(text):
    for i, line in enumerate(text.splitlines(), 1):
        if "版本唯一事实源" in line:
            m = DEV_VER.search(line)
            if m:
                return m.group(1), i, None
    return None, None, "未找到「版本唯一事实源 …（当前 X.Y.Z）」口径行"


def _baseline_ver(text):
    last = None
    for m in BASELINE_VER.finditer(text):
        last = m
    if last is None:
        return None, None, "未找到「version 升 X.Y.Z」版本沿革条目"
    return last.group(1), _line_of(text, last.start()), None


def _baseline_source(root):
    """BASELINE 沿革真值源：沿革卷优先，缺失回退现行卷（旧布局兼容）。"""
    hist = root / "docs" / "BASELINE-HISTORY.md"
    if hist.is_file():
        return "BASELINE 最近 round", "docs/BASELINE-HISTORY.md", hist
    return "BASELINE 最近 round", "BASELINE.md", root / "BASELINE.md"


def check_version_sync(root):
    truth, error = truth_version(root)
    errors = [error] if error else []
    bname, brel, bpath = _baseline_source(root)
    sources = [
        _source(root, "pyproject.toml", "pyproject.toml", _pyproject_ver),
        _source(root, "review_mcp.SERVER_INFO", "mcp/review_mcp.py",
                _regex_source(MCP_VER)),
        _source(root, "README 头条", "README.md", _regex_source(README_VER)),
        _source(root, "DEVELOPMENT 发布口径", "docs/DEVELOPMENT.md", _dev_ver),
        _source(root, bname, brel, _baseline_ver),
    ]
    for item in sources:
        item["ok"] = bool(truth) and item["error"] is None \
            and item["value"] == truth
        if item["error"]:
            errors.append("%s: %s" % (item["source"], item["error"]))
        elif item["value"] != truth:
            errors.append("%s = %r ≠ 真值 %r"
                          % (item["source"], item["value"], truth))
    if truth is not None and not SEMVER.match(truth):
        errors.append("真值版本 %r 不是 X.Y.Z 形态" % truth)
    status = "PASS" if truth and not errors else "FAIL"
    return {"id": "version_sync", "status": status, "version": truth,
            "sources": sources, "errors": errors}


def _run_gate(root, check_id):
    rel = GATE_SCRIPTS[check_id]
    script = root / rel
    if not script.is_file():
        return {"id": check_id, "status": "FAIL", "script": rel,
                "error": "门禁脚本缺失"}
    try:
        p = subprocess.run([sys.executable, str(script), "--root", str(root)],
                           shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"id": check_id, "status": "FAIL", "script": rel,
                "error": "无法执行: %s" % exc}
    summary = None
    try:
        summary = json.loads(p.stdout)
    except ValueError:
        summary = None
    detail = {"id": check_id, "script": rel, "rc": p.returncode,
              "status": "PASS" if p.returncode == 0 else "FAIL"}
    if isinstance(summary, dict):
        for key in ("ok", "drift_count", "state", "files", "allowlisted",
                    "stale", "packages", "violations"):
            if key in summary:
                detail[key] = summary[key]
    return detail


def _parse_suite(text):
    """unittest/pytest 双格式解析（round-151 补齐：与 round-gate 对齐，
    D-051 批 A「发布闸提速可选」xdist 路径的配套能力）。"""
    m = RAN_RE.search(text)
    ok = OK_RE.search(text)
    failed = FAILED_RE.search(text)
    if m:
        skipped = int(ok.group(1)) if ok and ok.group(1) else 0
        return {
            "ran": int(m.group(1)) if m else None,
            "duration_sec": float(m.group(2)) if m else None,
            "skipped": skipped,
            "green": bool(ok) and not failed,
        }
    mp = PASSED_RE.search(text)
    if mp:
        passed = int(mp.group(1))
        f = FAILED_CNT_RE.search(text)
        e = ERROR_CNT_RE.search(text)
        s = SKIPPED_CNT_RE.search(text)
        failed_n = int(f.group(1)) if f else 0
        error_n = int(e.group(1)) if e else 0
        skipped_n = int(s.group(1)) if s else 0
        dur = PYTEST_DUR_RE.search(text)
        return {
            "ran": passed + failed_n + error_n + skipped_n,
            "duration_sec": float(dur.group(1)) if dur else None,
            "skipped": skipped_n,
            "green": passed > 0 and failed_n == 0 and error_n == 0,
        }
    return {
        "ran": None,
        "duration_sec": None,
        "skipped": 0,
        "green": False,
    }


def _suite_from_log(path):
    data = path.read_bytes()
    text = data.decode("utf-8", errors="replace")
    run = {"mode": "reuse", "log": str(path), "bytes": len(data),
           "sha256": hashlib.sha256(data).hexdigest()[:16]}
    run.update(_parse_suite(text))
    return run


def _run_suite_once(root, log_dir, index):
    cmd = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests",
           "-v"]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    started = time.monotonic()
    run = {"mode": "executed", "log": None, "bytes": None, "sha256": None}
    try:
        p = subprocess.run(cmd, cwd=str(root), shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=1800, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        run.update({"green": False, "ran": None, "duration_sec": None,
                    "skipped": 0, "error": "执行失败: %s" % exc})
        return run
    text = (p.stdout or "") + NEWLINE + (p.stderr or "")
    run.update(_parse_suite(text))
    run["rc"] = p.returncode
    run["green"] = run["green"] and p.returncode == 0
    run["duration_sec"] = run["duration_sec"] or round(
        time.monotonic() - started, 3)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / ("release-gate-run%d.log" % index)
        path.write_bytes(text.encode("utf-8"))
        data = path.read_bytes()
        run["log"] = str(path)
        run["bytes"] = len(data)
        run["sha256"] = hashlib.sha256(data).hexdigest()[:16]
    return run


def _discovered_count(root):
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return None, "tests/ 目录缺失"
    # 发现会 import 测试模块：不写 __pycache__，否则本闸自己把工作树弄脏
    # （round-57 实踩：git_state 在套件检查之后跑，被 tests/__pycache__ 判脏）
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader = unittest.defaultTestLoader
        suite = loader.discover(str(tests_dir), pattern="test_*.py",
                                top_level_dir=str(tests_dir))
        return suite.countTestCases(), None
    except (ImportError, ValueError) as exc:
        return None, "测试发现失败: %s" % exc
    finally:
        sys.dont_write_bytecode = previous


def check_suite(root, logs, run_suite, expect_tests, log_dir):
    runs = [_run_suite_once(root, log_dir, i + 1) for i in range(2)] \
        if run_suite else [_suite_from_log(p) for p in logs]
    errors = []
    for i, run in enumerate(runs, 1):
        if not run["green"]:
            errors.append("第 %d 跑未全绿（ran=%r）" % (i, run["ran"]))
    counts = [run["ran"] for run in runs]
    if None not in counts and counts[0] != counts[1]:
        errors.append("两跑测试数不一致: %r" % (counts,))
    expected = expect_tests
    if expected is None:
        expected, error = _discovered_count(root)
        if error:
            errors.append(error)
    if expected is not None:
        for i, count in enumerate(counts, 1):
            if count != expected:
                errors.append("第 %d 跑计数 %r ≠ 期望 %r"
                              % (i, count, expected))
    durations = [run["duration_sec"] or 0 for run in runs]
    over = [d for d in durations if d > REDLINE_SEC]
    if over:
        for i, d in enumerate(durations, 1):
            if d > REDLINE_SEC:
                errors.append("第 %d 跑 %s 秒 > %ds 挂死护栏（D-052，超时判红疑似挂死）"
                              % (i, d, REDLINE_SEC))
    status = "PASS" if not errors else "FAIL"
    return {"id": "suite_double_run", "status": status,
            "mode": "executed" if run_suite else "reuse",
            "expected_tests": expected, "runs": runs, "errors": errors,
            "redline_sec": REDLINE_SEC, "redline_exceeded": over,
            "redline_note": "600s 挂死护栏（D-052，2026-11-10 批准落地）："
                            "超时判红阻断发布；300s 观测线已废"}


def _git(root, *args):
    p = subprocess.run(["git", "-C", str(root)] + list(args), shell=False,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def check_git_state(root, version, tag, branch_expected, out_path=None):
    rc, status, err = _git(root, "status", "--porcelain")
    if rc != 0:
        return {"id": "git_state", "status": "FAIL",
                "error": "不是可读的 git 仓库: %s" % (err or rc)}
    dirty = [line for line in status.splitlines() if line.strip()]
    # r191 自豁免：本闸自身的 --out 证据文件在重跑场景必然与上次落盘内容
    # 不同（每次闸运行都重写证据面）——它不是发布快照污染，排除后重跑不再
    # 被自己的产物绊倒；其余任何脏项仍判红（发布快照必须是已提交状态）。
    excluded = 0
    if out_path:
        out_norm = str(Path(out_path).resolve()).replace("\\", "/").lower()
        kept = []
        for line in dirty:
            # _git() 返回已 strip 的行，porcelain 前缀列宽不保证——按首个
            # 空白切出路径段（含 R 重命名的 "-> new" 尾段）。
            path_part = line.split(None, 1)[-1].strip('"') if line else ""
            if "->" in path_part:
                path_part = path_part.split("->")[-1].strip()
            path_part = path_part.replace("\\", "/").lower()
            try:
                resolved = str((root / path_part).resolve()).replace("\\", "/").lower()
            except OSError:
                resolved = path_part
            if resolved == out_norm or out_norm.startswith(resolved.rstrip("/") + "/"):
                # 精确匹配，或 porcelain 把全未跟踪目录折叠为 "dir/" 而
                # out 文件恰在该目录下（r191 实弹）——两种形态都豁免。
                excluded += 1
                continue
            kept.append(line)
        dirty = kept
    rc_b, cur_branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    rc_h, head, _ = _git(root, "rev-parse", "--short", "HEAD")
    errors = []
    if dirty:
        errors.append("工作树不干净（%d 项），发布快照必须是已提交状态"
                      % len(dirty))
    if rc_b != 0 or cur_branch != branch_expected:
        errors.append("当前分支 %r ≠ 发布分支 %r"
                      % (cur_branch or "?", branch_expected))
    tag_checked = bool(tag)
    tag_exists = None
    if tag:
        if not TAG_RE.match(tag):
            errors.append("tag %r 不是 vX.Y.Z 形态" % tag)
        elif version and tag != "v" + version:
            errors.append("tag %r ≠ v<版本>（v%s）" % (tag, version))
        rc_t, listed, _ = _git(root, "tag", "--list", tag)
        tag_exists = rc_t == 0 and bool(listed)
        if tag_exists:
            errors.append("tag %s 已存在：版本号不可复用，发布必须升版本"
                          % tag)
    return {"id": "git_state", "status": "PASS" if not errors else "FAIL",
            "branch": cur_branch, "branch_expected": branch_expected,
            "head": head if rc_h == 0 else None, "clean": not dirty,
            "dirty": dirty[:10], "dirty_count": len(dirty),
            "out_evidence_excluded": excluded,
            "tag": tag, "tag_checked": tag_checked, "tag_exists": tag_exists,
            "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="发布闸（只读，不打 tag）")
    parser.add_argument("--root", default=".")
    parser.add_argument("--tag", default=None, help="计划使用的 tag，如 v1.58.0")
    parser.add_argument("--branch", default="main", help="发布分支（默认 main）")
    parser.add_argument("--suite-log", action="append", default=[],
                        help="全量套件日志，恰好两份（与 --run-suite 二选一）")
    parser.add_argument("--run-suite", action="store_true",
                        help="当场顺序跑两遍全量套件")
    parser.add_argument("--suite-log-dir", default=None,
                        help="--run-suite 时把两跑日志写到这里")
    parser.add_argument("--expect-tests", type=int, default=None,
                        help="期望测试数（缺省用 discover 真值）")
    parser.add_argument("--only", default=None,
                        help="逗号分隔的检查 id（CI 分项，输出 partial=true）")
    parser.add_argument("--out", default=None, help="证据 JSON 落盘路径")
    argv = parser.parse_args()

    root = Path(argv.root).resolve()
    if not root.is_dir():
        return _param_error("root 不是目录: %s" % root)
    selected = list(CHECKS)
    if argv.only:
        selected = [part.strip() for part in argv.only.split(",")
                    if part.strip()]
        unknown = [cid for cid in selected if cid not in CHECKS]
        if unknown or not selected:
            return _param_error("未知检查 id: %r（可选 %s）"
                                % (unknown or argv.only, ", ".join(CHECKS)))
    logs = [Path(p) for p in argv.suite_log]
    if "suite_double_run" in selected:
        if argv.run_suite and logs:
            return _param_error("--suite-log 与 --run-suite 二选一")
        if not argv.run_suite:
            if len(logs) != 2:
                return _param_error("需要恰好两份 --suite-log（当前 %d）"
                                    % len(logs))
            if logs[0].resolve() == logs[1].resolve():
                return _param_error("两份日志必须是不同文件")
            for path in logs:
                if not path.is_file():
                    return _param_error("日志不存在: %s" % path)

    version, _ = truth_version(root)
    checks = []
    if "version_sync" in selected:
        checks.append(check_version_sync(root))
    for cid in ("doc_freshness", "doc_drift", "secret_scan", "license_check"):
        if cid in selected:
            checks.append(_run_gate(root, cid))
    if "suite_double_run" in selected:
        log_dir = Path(argv.suite_log_dir).resolve() if argv.suite_log_dir \
            else None
        checks.append(check_suite(root, logs, argv.run_suite,
                                  argv.expect_tests, log_dir))
    if "git_state" in selected:
        checks.append(check_git_state(root, version, argv.tag, argv.branch,
                                      out_path=argv.out))

    failed = [c["id"] for c in checks if c["status"] != "PASS"]
    result = {
        "ok": not failed,
        "check": "release-gate",
        "partial": bool(argv.only),
        "selected": selected,
        "release": {"version": version, "tag": argv.tag,
                    "branch": argv.branch, "tag_checked": bool(argv.tag)},
        "root": str(root),
        "checks": checks,
        "failed": failed,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if argv.out:
        out = Path(argv.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
        result["out"] = str(out)
    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
