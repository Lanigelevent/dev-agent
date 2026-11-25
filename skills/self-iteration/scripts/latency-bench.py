#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan 延迟基准与 SLO 门禁：合成 diff 分档跑 38 规则臂 → p50/p95（r154 基准 / r155 门禁化）。

用途:
    r154：把「性能」从单点实测升级为可回归基准。合成三类规模的 unified
    diff（S=100 行 / M=500 行 / L=2000 行，各内嵌真实规则命中形态），每档
    实跑 N 遍 deterministic-rules.py（子进程实跑，非模拟），输出
    p50/p95/最小/最大延迟与 findings 数。
    r155：check 动词把 SLO 变成可执行门禁——报告 p95 对 latency-slo.json
    （单一事实源）逐档断言 p95 ≤ p95_max_s，任一档超限 rc=1；CI nightly
    接线。阈值给约 10 倍余量（实测 0.12s 级），只抓量级回归，不抓机器噪声。

判定规则（先写死）:
    - 每档 runs 缺省 5 次；延迟取 wall-clock（子进程完整生命周期）。
    - p95 = 排序后 ceil(0.95*n)-1 位（n=5 时即最大值）。
    - findings 数随档位记录（口径漂移可由跨次 run 对比发现）。

用法示例:
    py latency-bench.py run --rules skills/multi-agent-review/scripts/deterministic-rules.py \
        --runs 5 --out reports/_work/latency-bench-r155.json
    py latency-bench.py check --report reports/_work/latency-bench-r155.json

退出码:
    0 = run 完成 / check PASS（逐档 p95 ≤ 阈值）
    1 = check SLO 失败（任一档 p95 超限——量级回归信号）
    2 = 参数/输入错误（rules/报告/SLO 配置缺失或 schema 不符）
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SLO = ROOT / "skills" / "self-iteration" / "latency-slo.json"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _synth_diff(n_lines):
    """确定性合成 unified diff：ctx/add 交替，含 2 个真实规则命中形态
    （可变默认参 / ==None），保证 findings 口径非零可对账。"""
    out = ["diff --git a/bench.py b/bench.py", "--- a/bench.py",
           "+++ b/bench.py", "@@ -1,%d +1,%d @@" % (n_lines, n_lines + 2)]
    for i in range(max(1, n_lines // 3)):
        out.append(" ctx_%d = compute(%d)" % (i, i))
        if i == 0:
            out.append("+def f(x={}, y=None):")
            out.append("+    if x == None:")
            out.append("+        return 0")
        out.append("+ok_%d = %d + %d" % (i, i, 1))
    return chr(10).join(out)


TIERS = (("S", 100), ("M", 500), ("L", 2000))


def run_tier(rules_path, name, lines, runs, timeout, tmpdir):
    """写一次 diff 文件，实跑 rules N 遍计 wall-clock。"""
    diff = _synth_diff(lines)
    dpath = Path(tmpdir) / ("bench-%d.diff" % lines)
    dpath.write_text(diff, encoding="utf-8")
    lat = []
    findings = None
    for _ in range(runs):
        t0 = time.time()
        p = subprocess.run(
            [sys.executable, "-X", "utf8", str(rules_path),
             "--diff-file", str(dpath)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout)
        lat.append(time.time() - t0)
        try:
            findings = len(json.loads(p.stdout).get("findings", []))
        except ValueError:
            findings = None
    lat.sort()
    n = len(lat)

    def pct(q):
        k = max(0, min(n - 1, -(-int(q * 100 * n) // 100) - 1))
        return lat[k]
    return {"name": name, "lines": lines, "runs": n, "p50": round(pct(50), 3),
            "p95": round(pct(95), 3), "min": round(lat[0], 3),
            "max": round(lat[-1], 3), "findings": findings}


def load_slo(path=None):
    """读 SLO 配置（单一事实源 latency-slo.json）。缺文件/坏 schema → code=2。"""
    p = Path(path) if path else DEFAULT_SLO
    if not p.is_file():
        raise ValueError("SLO 配置不存在: %s" % p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("SLO 配置不可读: %s (%s)" % (p, exc))
    if data.get("schema") != "latency-slo/1" or not isinstance(
            data.get("tiers"), dict) or not data["tiers"]:
        raise ValueError("SLO 配置 schema 不符（latency-slo/1）: %s" % p)
    for name, tier in data["tiers"].items():
        v = tier.get("p95_max_s") if isinstance(tier, dict) else None
        if not isinstance(v, (int, float)) or v <= 0:
            raise ValueError("SLO 档 %s 缺正数 p95_max_s" % name)
    return data


def cmd_check(argv):
    """check 动词：报告 p95 对 SLO 上限逐档断言（r155 门禁化）。"""
    report_path = Path(argv.report)
    if not report_path.is_file():
        _emit({"ok": False, "mode": "latency-slo-check",
               "error": "报告不存在: %s" % report_path})
        return 2
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        slo = load_slo(argv.slo)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "mode": "latency-slo-check",
               "error": str(exc)})
        return 2
    if report.get("mode") != "latency-bench" or not isinstance(
            report.get("tiers"), list) or not report["tiers"]:
        _emit({"ok": False, "mode": "latency-slo-check",
               "error": "报告形状不符（mode=latency-bench + tiers 列表）"})
        return 2
    lines2name = {lines: name for name, lines in TIERS}
    tiers = {}
    for t in report["tiers"]:
        key = t.get("name") or lines2name.get(t.get("lines"))
        if key:
            tiers[key] = t
    verdicts = []
    failed = []
    for name, tier in slo["tiers"].items():
        t = tiers.get(name)
        if not t or not isinstance(t.get("p95"), (int, float)):
            _emit({"ok": False, "mode": "latency-slo-check",
                   "error": "报告缺档 %s 的 p95" % name})
            return 2
        limit = tier["p95_max_s"]
        ok = t["p95"] <= limit
        verdicts.append({"tier": name, "p95": t["p95"],
                         "p95_max_s": limit,
                         "verdict": "PASS" if ok else "FAIL",
                         "margin_s": round(limit - t["p95"], 3)})
        if not ok:
            failed.append(name)
    out = {"ok": not failed, "mode": "latency-slo-check",
           "report": str(report_path), "slo": str(argv.slo or DEFAULT_SLO),
           "verdicts": verdicts,
           "note": "p95 ≤ p95_max_s 逐档断言；margin_s=阈值-实测；"
                   "FAIL 即 SLO 量级回归"}
    _emit(out)
    return 1 if failed else 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="scan 延迟基准与 SLO 门禁（p50/p95 分档）")
    p = ap.add_subparsers(dest="cmd", required=True)
    pr = p.add_parser("run", help="三档合成 diff 实跑 38 规则臂")
    pr.add_argument("--rules", required=True)
    pr.add_argument("--runs", type=int, default=5)
    pr.add_argument("--timeout", type=int, default=60)
    pr.add_argument("--out", default="")
    pc = p.add_parser("check", help="报告 p95 对 SLO 上限逐档断言（门禁）")
    pc.add_argument("--report", required=True)
    pc.add_argument("--slo", default="")
    args = ap.parse_args()
    if args.cmd == "check":
        return cmd_check(args)
    rp = Path(args.rules)
    if not rp.is_file():
        _emit({"ok": False, "mode": "latency-bench",
               "error": "rules 不存在: %s" % rp})
        return 2
    tiers = []
    with tempfile.TemporaryDirectory(prefix="latbench-") as tmpdir:
        for name, lines in TIERS:
            tiers.append(run_tier(rp, name, lines, args.runs, args.timeout,
                                  tmpdir))
    result = {
        "ok": True, "mode": "latency-bench",
        "rules": args.rules, "runs_per_tier": args.runs,
        "tiers": tiers,
        "note": "wall-clock 含子进程启动；p95 在 n=5 时即最大值；"
                "findings 口径跨次对比可发现规则漂移",
    }
    if args.out:
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        result["out"] = args.out
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
