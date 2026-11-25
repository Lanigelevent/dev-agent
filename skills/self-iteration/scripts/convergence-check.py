#!/usr/bin/env python3
"""收敛判定：测试/一致性/队列/指标四维全满足才允许停。

用途:
    自迭代链路。四维任一不满足即不可停，防止「看起来收敛」的假停。

用法:
    python convergence-check.py --root /path/project --metrics metrics.json

退出码:
    0 = 可停（四维全绿）
    1 = 不可停
    2 = 参数/环境错误（metrics 缺失或字段不全）
"""
import argparse
import json
import sys
from pathlib import Path

DIMENSIONS = ["tests_passed", "consistency_clean", "queue_empty", "metrics_stable"]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="收敛判定")
    parser.add_argument("--root", required=True, help="项目根目录（存在性检查）")
    parser.add_argument("--metrics", required=True, help="指标 JSON 文件")
    argv = parser.parse_args()
    root = Path(argv.root)
    if not root.is_dir():
        _emit({"ok": False, "error": "root 不存在: %s" % root})
        return 2
    mp = Path(argv.metrics)
    if not mp.is_file():
        _emit({"ok": False, "error": "metrics 文件不存在: %s" % mp})
        return 2
    try:
        metrics = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "metrics JSON 非法: %s" % exc})
        return 2
    missing = [k for k in DIMENSIONS if k not in metrics]
    if missing:
        _emit({"ok": False, "error": "metrics 缺字段: %s" % missing})
        return 2
    detail = {k: bool(metrics[k]) for k in DIMENSIONS}
    stop = all(detail.values())
    _emit({
        "ok": True,
        "can_stop": stop,
        "dimensions": detail,
        "reason": "四维全绿，可停" if stop else
                  "未满足: %s" % [k for k, v in detail.items() if not v],
    })
    return 0 if stop else 1


if __name__ == "__main__":
    sys.exit(main())
