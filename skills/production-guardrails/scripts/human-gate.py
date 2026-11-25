#!/usr/bin/env python3
"""人工介入门：五类情况触发人工确认，四类情况明确不算门。

用途:
    主流程步骤 0/2/6。触发即暂停等待人工确认，不自动继续。

用法:
    python human-gate.py --situation preflight_rejected --details "预算两档都超"

退出码:
    0 = 不触发（含四类明确不算门的情况）
    1 = 触发人工介入
    2 = 参数错误（未知 situation）
"""
import argparse
import json
import sys

TRIGGERS = {
    "preflight_rejected": "预检拒绝（仓库/对象不可解析或预算两档都超）",
    "budget_both_exceeded": "预算两档都超",
    "conclusions_unconverged": "结论未收敛（多轮查证不一致）",
    "verification_incomplete": "查证未完成（核验/反向验证缺口）",
    "downgrade_two_levels": "降级跨两级以上（如 L 档直接降为 XL/quick）",
}
NOT_GATE = {
    "single_low_confidence_finding": "单个低置信度发现：记录并继续，不构成门",
    "material_insufficient": "材料不足：按「受材料范围限制，无法判断」记录，不构成门",
    "style_suggestion": "风格建议：不构成门",
    "test_suggestion": "测试建议：不构成门",
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="人工介入门")
    parser.add_argument("--situation", required=True,
                        help="五类触发或四类不算门的情形标识")
    parser.add_argument("--details", default="", help="补充说明")
    argv = parser.parse_args()
    if argv.situation in TRIGGERS:
        _emit(
            {
                "ok": True,
                "gate": True,
                "category": "trigger",
                "situation": argv.situation,
                "reason": TRIGGERS[argv.situation],
                "details": argv.details,
                "options": ["补充材料后重跑", "提高预算后重跑", "人工确认后继续"],
            }
        )
        return 1
    if argv.situation in NOT_GATE:
        _emit(
            {
                "ok": True,
                "gate": False,
                "category": "not_gate",
                "situation": argv.situation,
                "reason": NOT_GATE[argv.situation],
                "details": argv.details,
            }
        )
        return 0
    _emit({"ok": False, "error": "未知 situation: %s" % argv.situation,
           "known": sorted(list(TRIGGERS) + list(NOT_GATE))})
    return 2


if __name__ == "__main__":
    sys.exit(main())
