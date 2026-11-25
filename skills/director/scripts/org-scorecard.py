#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误预算结算（SRE 实践）：从产物痕迹结算各团队质量预算，超限给出整改口径。

预算口径（org.json error_budget，全部可从产物客观计算）：
- repair   rollback_ratio = ROLLED_BACK / (APPLIED + ROLLED_BACK)，阈值 0.2；
- approval rejected_per_round = REJECTED 批准书数，阈值 3；
- retro    open_pitfalls = 台账未结坑数，阈值 8；
- research cases_without_archive = 无 url 且无 local_ref 的案例数，阈值 0；
- review   high_without_evidence 由扫描器结构性保证（发现必附证据），
           结算器标 manual（如实标注，不假造数据）。

判定：值 <= 阈值 PASS；<= 2×阈值 WARN（整改关注）；> 2×阈值 EXCEEDED
（整队进入整改冻结：只修质量不扩功能）。数据不足（如无落盘记录）标 N/A。

用法示例：
    py org-scorecard.py --org org.json --scan retro --scan runs

退出码：0=结算完成；2=输入或组织架构错误。
"""
import argparse
import json
import sys
from pathlib import Path


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _verdict(value, threshold):
    if value <= threshold:
        return "PASS"
    if value <= threshold * 2:
        return "WARN"
    return "EXCEEDED"


def _apply_log_stats(roots, errors):
    applied = rolled_back = 0
    for root in roots:
        if not Path(root).exists():
            continue
        for path in Path(root).rglob("apply-log.json"):
            try:
                status = json.loads(path.read_text(encoding="utf-8")).get("status")
            except (OSError, ValueError) as exc:
                errors.append("apply-log 解析失败(%s): %s" % (path, exc))
                continue
            if status == "APPLIED":
                applied += 1
            elif status == "ROLLED_BACK":
                rolled_back += 1
    return applied, rolled_back


def _rejected_count(roots, errors):
    rejected = 0
    for root in roots:
        if not Path(root).exists():
            continue
        for path in Path(root).rglob("approval.json"):
            try:
                if json.loads(path.read_text(encoding="utf-8")).get(
                        "verdict") == "REJECTED":
                    rejected += 1
            except (OSError, ValueError) as exc:
                errors.append("approval 解析失败(%s): %s" % (path, exc))
    return rejected


def _ledger_stats(roots, errors):
    open_count = 0
    for root in roots:
        pitfall_path = Path(root) / "pitfalls.json"
        if not pitfall_path.is_file():
            continue
        try:
            data = json.loads(pitfall_path.read_text(encoding="utf-8"))
            open_count += sum(1 for p in data.get("pitfalls", [])
                              if p.get("status") == "open")
        except (OSError, ValueError) as exc:
            errors.append("台账解析失败(%s): %s" % (pitfall_path, exc))
    return open_count


def _case_archive_gaps(roots, errors):
    gaps = 0
    for root in roots:
        cases_path = Path(root) / "cases.json"
        if not cases_path.is_file():
            continue
        try:
            data = json.loads(cases_path.read_text(encoding="utf-8"))
            for case in data.get("cases", []):
                if not case.get("url") and not case.get("local_ref"):
                    gaps += 1
        except (OSError, ValueError) as exc:
            errors.append("案例库解析失败(%s): %s" % (cases_path, exc))
    return gaps


def main():
    parser = argparse.ArgumentParser(description="错误预算结算（SRE 实践）")
    parser.add_argument("--org", default=str(Path(__file__).resolve().parents[1]
                                             / "org.json"),
                        help="组织架构 JSON")
    parser.add_argument("--scan", action="append", default=[],
                        help="产物扫描根目录，可多次（缺省项目 retro/ 与 runs/）")
    argv = parser.parse_args()
    org_path = Path(argv.org)
    if not org_path.is_file():
        _emit({"ok": False, "error": "组织架构文件不存在: %s" % org_path})
        return 2
    try:
        data = json.loads(org_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "组织架构非法: %s" % exc})
        return 2
    roots = [Path(r) for r in (argv.scan or ["retro", "runs"])]
    errors = []
    applied, rolled_back = _apply_log_stats(roots, errors)
    rejected = _rejected_count(roots, errors)
    open_pitfalls = _ledger_stats(roots, errors)
    archive_gaps = _case_archive_gaps(roots, errors)

    metrics = {}
    total = applied + rolled_back
    if total:
        metrics["repair.rollback_ratio"] = {
            "value": round(rolled_back / total, 3), "threshold": 0.2}
    else:
        metrics["repair.rollback_ratio"] = {"value": None, "threshold": 0.2}
    metrics["approval.rejected_per_round"] = {"value": rejected, "threshold": 3}
    metrics["retro.open_pitfalls"] = {"value": open_pitfalls, "threshold": 8}
    metrics["research.cases_without_archive"] = {
        "value": archive_gaps, "threshold": 0}
    metrics["review.high_without_evidence"] = {
        "value": None, "threshold": 0, "note": "扫描器结构性保证，人工复核"}

    scorecard = []
    freeze = []
    for key, item in metrics.items():
        role = key.split(".")[0]
        budget = next((r.get("error_budget", {}) for r in data.get("org", [])
                       if r.get("role") == role), {})
        value, threshold = item.get("value"), item.get("threshold", 0)
        if value is None:
            status = "N/A" if item.get("note") else "N/A（无数据）"
        else:
            status = _verdict(value, threshold)
        if status == "EXCEEDED":
            freeze.append(role)
        scorecard.append({"team": role, "metric": key,
                          "budget_metric": budget.get("metric", key),
                          "value": value, "threshold": threshold,
                          "status": status})
    _emit({"ok": True, "scorecard": scorecard,
           "scanned_roots": [str(r) for r in roots],
           "freeze_teams": freeze,
           "advice": ("整改冻结：以下团队只修质量不扩功能：%s" % ",".join(freeze))
                     if freeze else "全部预算内；可按各自 initiatives 主动优化",
           "errors": errors})
    return 0


if __name__ == "__main__":
    sys.exit(main())
