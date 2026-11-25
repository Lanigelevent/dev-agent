#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""覆盖率门禁：治理壳（skills/llm）与 agent 关键路径的覆盖率基线对账。

用途：
    阶段三 3.3 门禁。measure 用仓库 .venv 里的 coverage 跑固定测试子集
    （默认 tests/test_scripts_*.py 拆分族、tests/test_agent.py、
    tests/test_dual_reviewer.py、
    tests/test_provider_ssrf.py、
    tests/test_report_adapter.py），子进程经 sitecustomize 注入一并采集，
    产出逐文件覆盖率基线 JSON；check 把实测与基线按容差比对——逐文件
    覆盖率下降超过容差、基线内文件消失、整体下降，任一成立即失败
    （平台漂移用容差吸收，默认 0.5 个百分点）。基线文件入库，更新基线
    必须显式走 measure 并随提交说明理由。

用法：
    python coverage-gate.py measure --root . --out skills/self-iteration/coverage-baseline.json
    python coverage-gate.py check --root .
    python coverage-gate.py check --root . --measured reports/coverage-round56/measured.json
    python coverage-gate.py measure --root . --out reports/tmp.json --tests test_dual_reviewer.py

退出码：
    0 = 通过（measure 产出基线 / check 无回退）
    1 = 覆盖率回退或基线内文件缺失
    2 = 环境或输入错误（缺 coverage、venv 不可用、测试失败、JSON 非法）
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "coverage-baseline/1"
DEFAULT_BASELINE = "skills/self-iteration/coverage-baseline.json"
DEFAULT_SOURCE = ["skills", "llm", "agent"]
DEFAULT_TESTS = ["test_scripts_*.py", "test_agent.py",
             "test_dual_reviewer.py",
             "test_provider_ssrf.py",
             "test_report_adapter.py"]
DEFAULT_TOLERANCE = 0.5
HERE = Path(__file__).resolve().parent


class GateError(Exception):
    """可报告的环境/输入错误（退出码 2）。"""


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _venv_python(root, override):
    """解释器：显式指定 > 仓库 .venv > 当前解释器（CI 无 .venv 时用系统 python）。"""
    if override:
        return str(Path(override))
    exe = "python.exe" if os.name == "nt" else "python"
    sub = "Scripts" if os.name == "nt" else "bin"
    venv = Path(root) / ".venv" / sub / exe
    if venv.is_file():
        return str(venv)
    return sys.executable


def _run(cmd, cwd, env=None, timeout=1800):
    proc = subprocess.run(cmd, cwd=str(cwd), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), \
        proc.stderr.decode("utf-8", "replace")


def _rel(path, root):
    p = str(path).replace("\\", "/")
    r = str(Path(root).resolve()).replace("\\", "/").rstrip("/")
    if p.startswith(r + "/"):
        p = p[len(r) + 1:]
    return p


def _measure(root, tests, python, keep_data=False):
    """跑固定测试子集（coverage 采集含子进程），返回 (files, totals, meta)。"""
    root = Path(root).resolve()
    if not (root / "tests").is_dir():
        raise GateError("tests/ 不存在: %s" % root)
    rc, _, err = _run([python, "-c", "import coverage"], root)
    if rc != 0:
        raise GateError(".venv 缺 coverage（uv pip install coverage）: %s"
                        % err.strip()[:200])
    work = root / "reports" / "_work" / ("coverage-gate-%d" % os.getpid())
    shim = work / "shim"
    work.mkdir(parents=True, exist_ok=True)
    shim.mkdir(exist_ok=True)
    (shim / "sitecustomize.py").write_text(
        "try:\n"
        "    import coverage\n"
        "except Exception:  # 外来解释器没有 coverage 时静默跳过，\n"
        "    pass          # 不让 sitecustomize 往 stderr 吐噪声\n"
        "else:\n"
        "    coverage.process_startup()\n", encoding="utf-8")
    data_base = (work / "cov").as_posix()
    rc_file = work / "coveragerc"
    rc_file.write_text(
        "[run]\nparallel = True\nrelative_files = True\n"
        "data_file = %s\nsource =\n%s\n"
        "omit =\n    */__pycache__/*\n    */tests/*\n    */datasets/*\n"
        % (data_base, "".join("    %s\n" % s for s in DEFAULT_SOURCE)),
        encoding="utf-8")
    env = dict(os.environ)
    env["COVERAGE_PROCESS_START"] = str(rc_file)
    env["COVERAGE_FILE"] = data_base
    env["PYTHONPATH"] = str(shim) + (os.pathsep + env["PYTHONPATH"]
                                     if env.get("PYTHONPATH") else "")
    runs = []
    started = time.monotonic()
    try:
        for pattern in tests:
            cmd = [python, "-m", "coverage", "run", "--rcfile", str(rc_file),
                   "-m", "unittest", "discover", "-s", "tests", "-p", pattern]
            t0 = time.monotonic()
            rc, out, err = _run(cmd, root, env)
            # unittest 把进度与 FAIL 块写 stderr、摘要写 stdout：stdout 为空时
            # 退回 stderr 末行，否则报错只留一个空「末行:」（round-56 实踩）
            tail = ((out.strip().splitlines() or [""])[-1]
                    or (err.strip().splitlines() or [""])[-1])
            # 末行只有 FAILED (failures=1)，不带用例名：把 FAIL:/ERROR: 行
            # 一并摘出，失败时能直接定位到用例（round-56 实踩）
            failed = [ln.strip() for ln in err.splitlines()
                      if ln.startswith(("FAIL:", "ERROR:"))]
            if failed:
                tail = "%s | %s" % (tail, "; ".join(failed[:3]))
            runs.append({"pattern": pattern, "rc": rc,
                         "elapsed_sec": round(time.monotonic() - t0, 3),
                         "tail": tail})
            if rc != 0:
                raise GateError("测试失败（%s rc=%d，末行: %s）——覆盖率测量"
                                "作废，先修测试" % (pattern, rc, tail))
        rc, out, err = _run([python, "-m", "coverage", "combine", "--rcfile",
                             str(rc_file)], work, env)
        if rc != 0:
            raise GateError("coverage combine 失败: %s" % err.strip()[:300])
        out_json = work / "measured.json"
        rc, out, err = _run([python, "-m", "coverage", "json", "--rcfile",
                             str(rc_file), "-o", str(out_json)], root, env)
        if rc != 0:
            raise GateError("coverage json 失败: %s" % err.strip()[:300])
        raw = json.loads(out_json.read_text(encoding="utf-8"))
    finally:
        if not keep_data:
            shutil.rmtree(work, ignore_errors=True)
    files = {}
    for path, info in (raw.get("files") or {}).items():
        summary = info.get("summary") or {}
        files[_rel(path, root)] = {
            "pct": round(float(summary.get("percent_covered", 0.0)), 2),
            "statements": int(summary.get("num_statements", 0)),
            "covered": int(summary.get("covered_lines", 0)),
        }
    totals = raw.get("totals") or {}
    meta = {
        "elapsed_sec": round(time.monotonic() - started, 3),
        "python": "%d.%d.%d" % sys.version_info[:3],
        "platform": sys.platform,
        "runs": runs,
        "work_data": None if not keep_data else str(work),
    }
    return files, round(float(totals.get("percent_covered", 0.0)), 2), meta


def _build_baseline(root, tests, python, tolerance, keep_data):
    files, overall, meta = _measure(root, tests, python, keep_data)
    return {
        "schema": SCHEMA,
        "generated_at": datetime.datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "scope": {"source": list(DEFAULT_SOURCE), "tests": list(tests),
                  "python": meta["python"], "platform": meta["platform"]},
        "tolerance_pct": tolerance,
        "overall_pct": overall,
        "files": files,
        "platform_optional": [],
        "measure_meta": {"elapsed_sec": meta["elapsed_sec"],
                         "runs": meta["runs"]},
    }


def _load_measured(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "files" not in data:
        raise GateError("实测 JSON 缺 files: %s" % path)
    files = {}
    for name, info in data["files"].items():
        info = info or {}
        if "pct" in info:
            files[name.replace("\\", "/")] = {"pct": float(info["pct"])}
        else:
            summary = info.get("summary") or {}
            files[name.replace("\\", "/")] = {
                "pct": round(float(summary.get("percent_covered", 0.0)), 2)}
    totals = data.get("totals") or {}
    overall = data.get("overall_pct")
    if overall is None:
        overall = round(float(totals.get("percent_covered", 0.0)), 2)
    return files, float(overall)


def _compare(baseline, current_files, current_overall, tolerance):
    regressions, missing = [], []
    optional = set(baseline.get("platform_optional") or [])
    for path, info in (baseline.get("files") or {}).items():
        base_pct = float(info.get("pct", 0.0))
        if path not in current_files:
            if path not in optional:
                missing.append(path)
            continue
        cur_pct = float(current_files[path]["pct"])
        drop = round(base_pct - cur_pct, 2)
        if drop > tolerance:
            regressions.append({"file": path, "baseline_pct": base_pct,
                                "current_pct": cur_pct, "drop": drop})
    base_overall = float(baseline.get("overall_pct", 0.0))
    overall_drop = round(base_overall - current_overall, 2)
    overall_regression = overall_drop > tolerance
    new_files = sorted(set(current_files) - set(baseline.get("files") or {}))
    ok = not regressions and not missing and not overall_regression
    return {
        "ok": ok,
        "state": "PASS" if ok else "REGRESSION",
        "tolerance_pct": tolerance,
        "baseline_overall_pct": base_overall,
        "current_overall_pct": current_overall,
        "overall_drop": overall_drop,
        "overall_regression": overall_regression,
        "regressions": regressions,
        "missing": missing,
        "new_files_count": len(new_files),
        "new_files": new_files[:20],
    }


def cmd_measure(argv):
    root = Path(argv.root).resolve()
    python = _venv_python(root, argv.python)
    tests = argv.tests or list(DEFAULT_TESTS)
    tolerance = argv.tolerance if argv.tolerance is not None \
        else DEFAULT_TOLERANCE
    baseline = _build_baseline(root, tests, python, tolerance,
                               argv.keep_data)
    out = Path(argv.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(baseline, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    _emit({"ok": True, "state": "BASELINE_WRITTEN", "out": str(out),
           "overall_pct": baseline["overall_pct"],
           "files": len(baseline["files"]),
           "tolerance_pct": tolerance,
           "scope": baseline["scope"],
           "elapsed_sec": baseline["measure_meta"]["elapsed_sec"],
           "runs": baseline["measure_meta"]["runs"]})
    return 0


def cmd_check(argv):
    root = Path(argv.root).resolve()
    base_path = Path(argv.baseline)
    if not base_path.is_absolute():
        base_path = root / base_path
    if not base_path.is_file():
        raise GateError("基线不存在: %s（先跑 measure 生成并入仓）" % base_path)
    try:
        baseline = json.loads(base_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise GateError("基线 JSON 非法: %s (%s)" % (base_path, exc))
    if baseline.get("schema") != SCHEMA:
        raise GateError("基线 schema 不符: %s" % baseline.get("schema"))
    tolerance = argv.tolerance if argv.tolerance is not None \
        else float(baseline.get("tolerance_pct", DEFAULT_TOLERANCE))
    if argv.measured:
        files, overall = _load_measured(argv.measured)
        measured_from = str(Path(argv.measured).resolve())
    else:
        tests = (baseline.get("scope") or {}).get("tests") or list(
            DEFAULT_TESTS)
        python = _venv_python(root, argv.python)
        files, overall, meta = _measure(root, tests, python, False)
        measured_from = "live（%s）" % ", ".join(tests)
    result = _compare(baseline, files, overall, tolerance)
    result.update({"baseline": str(base_path), "measured_from": measured_from,
                   "files_measured": len(files),
                   "files_in_baseline": len(baseline.get("files") or {})})
    _emit(result)
    return 0 if result["ok"] else 1


def main():
    parser = argparse.ArgumentParser(description="覆盖率门禁（基线对账）")
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("measure")
    p.add_argument("--root", default=".")
    p.add_argument("--out", required=True)
    p.add_argument("--tests", nargs="*", default=None,
                   help="测试文件名模式（默认固定五项）")
    p.add_argument("--tolerance", type=float, default=None)
    p.add_argument("--python", default=None, help="解释器路径（默认仓库 .venv）")
    p.add_argument("--keep-data", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--root", default=".")
    p.add_argument("--baseline", default=DEFAULT_BASELINE)
    p.add_argument("--measured", default=None,
                   help="已有实测 JSON（不给则现场测量）")
    p.add_argument("--tolerance", type=float, default=None)
    p.add_argument("--python", default=None, help="解释器路径（默认仓库 .venv）")
    argv = parser.parse_args()
    try:
        if argv.mode == "measure":
            return cmd_measure(argv)
        return cmd_check(argv)
    except GateError as exc:
        _emit({"ok": False, "state": "ERROR", "error": str(exc)})
        return 2
    except subprocess.TimeoutExpired as exc:
        _emit({"ok": False, "state": "ERROR",
               "error": "子进程超时: %s" % exc})
        return 2
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "state": "ERROR", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
