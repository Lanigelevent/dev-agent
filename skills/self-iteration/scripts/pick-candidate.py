#!/usr/bin/env python3
"""改进候选排序：ROI → evidence 具体度 → 依赖满足，三键排序。

用途:
    自迭代链路。输入候选清单（含 roi/evidence/deps），输出执行顺序。

用法:
    python pick-candidate.py --items items.json [--resolved id1,id2]

退出码:
    0 = 正常排序
    1 = 无可选候选
    2 = 参数/环境错误
"""
import argparse
import json
import re
import sys
from pathlib import Path


def specificity(evidence):
    """evidence 具体度：含 文件:行号 记 2；长度 >=20 记 1；否则 0。"""
    if re.search(r"\w+\.\w+:\d+|\w+:\d+", str(evidence)):
        return 2
    return 1 if len(str(evidence)) >= 20 else 0


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="改进候选排序")
    parser.add_argument("--items", required=True, help="候选 JSON 文件（数组）")
    parser.add_argument("--resolved", default="", help="已完成的候选 id，逗号分隔")
    argv = parser.parse_args()
    ip = Path(argv.items)
    if not ip.is_file():
        _emit({"ok": False, "error": "候选文件不存在: %s" % ip})
        return 2
    try:
        items = json.loads(ip.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "候选 JSON 非法: %s" % exc})
        return 2
    if not isinstance(items, list):
        _emit({"ok": False, "error": "候选需为数组"})
        return 2
    items = [i for i in items if isinstance(i, dict) and i.get("id")]
    if not items:
        _emit({"ok": False, "error": "无可选候选"})
        return 1
    resolved = {r for r in argv.resolved.split(",") if r.strip()}
    done_ids = {i["id"] for i in items if i.get("done")}

    def sort_key(item):
        deps = [d for d in item.get("deps", []) if d != item["id"]]
        deps_ok = all(d in resolved or d in done_ids for d in deps)
        return (-int(item.get("roi", 0)), -specificity(item.get("evidence", "")),
                0 if deps_ok else 1, str(item["id"]))

    ranked = sorted(items, key=sort_key)
    out = []
    for rank, item in enumerate(ranked, 1):
        deps = [d for d in item.get("deps", []) if d != item["id"]]
        out.append({
            "rank": rank,
            "id": item["id"],
            "title": item.get("title", ""),
            "roi": item.get("roi", 0),
            "evidence_score": specificity(item.get("evidence", "")),
            "deps_ok": all(d in resolved or d in done_ids for d in deps),
            "deps": deps,
        })
    _emit({"ok": True, "ranked": out, "count": len(out)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
