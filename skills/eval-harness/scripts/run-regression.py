#!/usr/bin/env python3
"""回归评测：抽 N 个样本跑「prepare → 硬规则 → judge」全链，与基线指标对比。

用途:
    用 deterministic-rules 充当确定性评审器，链路无需真实模型即可回归。
    汇总层必须输出 valid_samples（易错点 4）；两组数字完全相同视为断链（易错点 5）。

用法:
    python run-regression.py --repo /path/repo --baseline baseline.json [--sample-size 5]

退出码:
    0 = 无回归
    1 = 回归（recall 明显下降，或指标与基线完全相同但样本集不同）
    2 = 参数/环境错误
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FORWARD = Path(__file__).resolve().parent / "forward-bench.py"
RULES = ROOT / "skills" / "multi-agent-review" / "scripts" / "deterministic-rules.py"


def locate_agent_json(explicit=None):
    """定位 agent.json：显式参数 > CWD > 项目根（脚本位置上溯）。找不到返回 None。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.cwd() / "agent.json")
    candidates.append(Path(__file__).resolve().parents[3] / "agent.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_args(explicit=None):
    """读取 agent.json 的 args；找不到返回空 dict 与 None 来源。"""
    p = locate_agent_json(explicit)
    if not p:
        return {}, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, str(p)
    return dict(data.get("args") or {}), str(p)


def _run(argv_list):
    """以纯参数列表执行子进程；shell 恒为 False，无 shell 解释面。"""
    if not isinstance(argv_list, list) or not all(isinstance(c, str) for c in argv_list):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(argv_list, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    return p.returncode, data, p.stderr


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="回归评测")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--baseline", required=True, help="基线 JSON（含 samples 与 metrics）")
    parser.add_argument("--sample-size", dest="sample_size", type=int, default=None,
                        help="回归样本数（默认 eval_regression_sample_size）")
    parser.add_argument("--config", help="agent.json 路径")
    argv = parser.parse_args()
    bp = Path(argv.baseline)
    if not bp.is_file():
        _emit({"ok": False, "error": "基线文件不存在: %s" % bp})
        return 2
    try:
        baseline = json.loads(bp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "基线 JSON 非法: %s" % exc})
        return 2
    samples = baseline.get("samples") if isinstance(baseline, dict) else baseline
    if not isinstance(samples, list) or not samples:
        _emit({"ok": False, "error": "基线无样本"})
        return 2
    args, _ = load_args(argv.config)
    size = argv.sample_size if argv.sample_size is not None else \
        int(args.get("eval_regression_sample_size", 5))
    picked = sorted(samples, key=lambda s: s.get("fix_commit", ""))[:size]
    picked_ids = [s["fix_commit"] for s in picked]
    with tempfile.TemporaryDirectory(prefix="cra-regression-") as tmp:
        tmpdir = Path(tmp)
        samples_file = tmpdir / "picked.json"
        samples_file.write_text(json.dumps({"samples": picked}, ensure_ascii=False), encoding="utf-8")
        rc_p, prep, err_p = _run([sys.executable, str(FORWARD), "prepare",
                                  "--samples", str(samples_file), "--repo", argv.repo,
                                  "--out", str(tmpdir / "prepared")])
        if rc_p != 0 or not prep:
            _emit({"ok": False, "error": "prepare 失败: %s" % (err_p or prep)[:300]})
            return 2
        manifest = json.loads(Path(prep["manifest"]).read_text(encoding="utf-8"))
        findings = {"samples": {}}
        for entry in manifest:
            merged = []
            for name in entry.get("diffs", []):
                diff_path = tmpdir / "prepared" / name
                rc_r, rules, err_r = _run([sys.executable, str(RULES),
                                           "--diff-file", str(diff_path)])
                if rc_r == 0 and rules:
                    merged.extend(rules.get("findings", []))
                else:
                    _emit({"ok": False, "error": "deterministic-rules 失败: %s" % (err_r or "")[:300]})
                    return 2
            findings["samples"][entry["sample_id"]] = merged
        findings_file = tmpdir / "findings.json"
        findings_file.write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
        rc_j, judge, err_j = _run([sys.executable, str(FORWARD), "judge",
                                   "--findings", str(findings_file),
                                   "--prepared", str(tmpdir / "prepared" / "manifest.json"),
                                   "--repo", argv.repo])
        if rc_j not in (0, 1) or not judge:
            _emit({"ok": False, "error": "judge 失败: %s" % (err_j or judge)[:300]})
            return 2
    base_metrics = baseline.get("metrics") or {}
    current = {"recall": judge.get("recall"), "hits": judge.get("hits"),
               "precision": judge.get("precision"), "claimed": judge.get("claimed"),
               "grounded": judge.get("grounded"),
               "valid_samples": judge.get("valid_samples"),
               "weak_samples": judge.get("weak_samples")}
    regressed = False
    reasons = []
    suspect = False
    if base_metrics:
        base_recall = base_metrics.get("recall")
        if base_recall is not None and current["recall"] is not None \
                and current["recall"] < base_recall - 0.05:
            regressed = True
            reasons.append("recall 下降 %s -> %s" % (base_recall, current["recall"]))
        base_ids = set(baseline.get("sample_ids") or
                       [s.get("fix_commit") for s in baseline.get("samples", [])])
        if base_recall == current["recall"] and base_metrics.get("hits") == current["hits"] \
                and base_ids != set(picked_ids):
            suspect = True
            regressed = True
            reasons.append("两组数字完全相同但样本集不同，疑似评测断链（易错点 5）")
    _emit({
        "ok": not regressed,
        "regressed": regressed,
        "reasons": reasons,
        "suspect_identical": suspect,
        "current": current,
        "baseline_metrics": base_metrics,
        "picked_ids": picked_ids,
        "sample_size": size,
        "valid_samples": current["valid_samples"],
        "budget_minutes": args.get("eval_regression_budget_minutes", 10),
    })
    return 1 if regressed else 0


if __name__ == "__main__":
    sys.exit(main())
