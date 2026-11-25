#!/usr/bin/env python3
"""反馈闭环入口：把用户驳回项写入误报模式库，同维度同 pattern 聚合累计。

用途:
    主流程步骤 10。读驳回清单（JSON），逐项调用 experience.record——
    同 pattern+dimension 累计 rejected_count、不新增条目，然后回读聚合结果。

用法:
    python feedback-close.py --findings rejects.json --experience runs/experience.json
    python feedback-close.py --findings rejects.json --experience runs   # 目录亦可

退出码:
    0 = 写入成功
    2 = 参数/环境错误（清单不存在、JSON 非法、经验库不可写）
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "experience.py"


def _run_json(argv_list):
    """以纯参数列表执行子进程并解析 stdout JSON；shell 恒为 False。"""
    if not isinstance(argv_list, list) or not all(isinstance(c, str) for c in argv_list):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(argv_list, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, None


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="反馈闭环：驳回项入库并聚合")
    parser.add_argument("--findings", required=True, help="驳回清单 JSON 文件")
    parser.add_argument("--experience", required=True, help="经验库 JSON 路径或其目录")
    argv = parser.parse_args()
    fp = Path(argv.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "驳回清单不存在: %s" % fp})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "驳回清单 JSON 非法: %s" % exc})
        return 2
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        _emit({"ok": False, "error": "驳回清单需为数组或含 items 键"})
        return 2
    exp_arg = Path(argv.experience)
    if exp_arg.is_dir() or exp_arg.suffix == "":
        db_path = exp_arg / "experience.json"
    else:
        db_path = exp_arg
    db_path.parent.mkdir(parents=True, exist_ok=True)
    recorded = skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        pattern = str(item.get("pattern") or item.get("rule_id") or "")
        if not pattern:
            skipped += 1
            continue
        dimension = str(item.get("dimension", ""))
        count = int(item.get("count", 1))
        rc, out = _run_json([sys.executable, str(SCRIPT), "record",
                             "--dir", str(db_path.parent), "--pattern", pattern,
                             "--dimension", dimension, "--count", str(count)])
        if rc == 0 and out:
            recorded += 1
        else:
            skipped += 1
    entries = {"entries": []}
    if db_path.is_file():
        try:
            entries = json.loads(db_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = {"entries": []}
    patterns = {str(i.get("pattern") or i.get("rule_id") or "")
                for i in items if isinstance(i, dict)}
    aggregated = [e for e in entries.get("entries", []) if e.get("pattern") in patterns]
    _emit({
        "ok": True,
        "recorded": recorded,
        "skipped": skipped,
        "experience": str(db_path),
        "aggregated": aggregated,
        "note": "同维度同 pattern 累计 rejected_count，不新增条目",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
