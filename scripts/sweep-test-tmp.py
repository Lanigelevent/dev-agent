#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运维口径：临时快照回收报表（先列后删，缺省只看不动盘）。

本机 `%TEMP%` 下有一千多个 `cra-tests-*` 快照，是被中断的评测/测试跑次留下的。
测试侧的自建自删已经由 `tests/tmpspace.py` 落地（新目录带归属标记、atexit 兜底、
下次跑测试时回收超龄的自己的标记目录）；**这批历史遗留没有标记**，
所以本脚本把它们单独列成「待人工决定」，绝不由自动路径删掉。

两类目录、两套口径：
- 有归属标记（tmpspace 建的）：超过年龄阈值即可回收，`--apply` 才真删；
- 无归属标记：只统计（数量 / 文件数 / 字节数 / 最老时间），不进 removed，
  要删请人确认后按前缀显式指定 `--purge-unmarked <prefix>`。

用法：
    py scripts/sweep-test-tmp.py                        # 报表（缺省 dry-run）
    py scripts/sweep-test-tmp.py --apply                # 回收超龄且有标记的
    py scripts/sweep-test-tmp.py --root <目录> --json   # 指定临时根
    py scripts/sweep-test-tmp.py --purge-unmarked cra-tests- --min-age-hours 24 --apply

退出码：0=成功；2=输入错误（路径不存在 / 参数矛盾）。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

import tmpspace  # noqa: E402  （测试侧生命周期与这里是同一份口径，不另写一遍）

DEFAULT_PREFIXES = tmpspace.KNOWN_PREFIXES


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _stat_tree(path):
    """目录的文件数与字节数（跳过标记文件本身，读不到的条目按 0 记账）。"""
    files = 0
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                files += 1
                total += entry.stat().st_size
        except OSError:
            continue
    return files, total


def _unmarked_report(root, prefixes, min_age_hours, now, stat_limit=10):
    """无标记历史遗留：先给全量清单，只给前 `stat_limit` 个目录做体积统计。

    本机临时根有 2.6 万个目录，逐个 rglob 数文件会把一条运维命令变成十几分钟的
    磁盘扫描；报表要的是「有多少、多大、多老」的量级，抽样足够。
    返回 (rows, report)：rows 是**全量**名字（--purge-unmarked 要用它点名删）。
    """
    rows = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if prefixes and not any(entry.name.startswith(p) for p in prefixes):
            continue
        if tmpspace.owner_of(entry) is not None:
            continue
        try:
            age_hours = (now - entry.stat().st_mtime) / 3600.0
        except OSError:
            continue
        if age_hours < min_age_hours:
            continue
        rows.append({"name": entry.name, "age_hours": round(age_hours, 1)})
    sampled = rows[:stat_limit]
    for row in sampled:
        files, size = _stat_tree(root / row["name"])
        row["files"], row["bytes"] = files, size
    by_prefix = {}
    for row in rows:
        key = next((p for p in sorted(prefixes, key=len, reverse=True)
                    if row["name"].startswith(p)),
                   row["name"].split("-")[0] + "-")
        by_prefix[key] = by_prefix.get(key, 0) + 1
    report = {"count": len(rows),
              "by_prefix": dict(sorted(by_prefix.items(),
                                       key=lambda kv: -kv[1])),
              "sampled": len(sampled),
              "sampled_files": sum(r.get("files", 0) for r in sampled),
              "sampled_bytes": sum(r.get("bytes", 0) for r in sampled),
              "sample": sampled}
    return rows, report


def main():
    parser = argparse.ArgumentParser(description="临时快照回收报表（缺省 dry-run）")
    parser.add_argument("--root", default="", help="临时目录根（缺省取系统临时目录）")
    parser.add_argument("--prefix", action="append", default=[],
                        help="只看这些前缀（可多次；缺省用内置测试前缀清单）")
    parser.add_argument("--min-age-hours", type=float, default=2.0,
                        help="超过这个年龄才算陈旧（默认 2 小时，避开并发跑次）")
    parser.add_argument("--apply", action="store_true",
                        help="真的删除（缺省只报表）")
    parser.add_argument("--purge-unmarked", action="append", default=[],
                        help="额外删除这些前缀下的**无标记**历史遗留（需人工确认后用）")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON（默认也是）")
    argv = parser.parse_args()

    root = Path(argv.root) if argv.root else tmpspace.temp_dir()
    if not root.is_dir():
        _emit({"ok": False, "error": "临时根不存在: %s" % root})
        return 2
    prefixes = tuple(argv.prefix) if argv.prefix else DEFAULT_PREFIXES
    older = argv.min_age_hours * 3600
    now = time.time()

    result = tmpspace.sweep(root=root, prefixes=prefixes,
                            older_than_seconds=older, apply=argv.apply)
    payload = {
        "ok": True, "root": str(root), "dry_run": not argv.apply,
        "prefixes": list(prefixes), "min_age_hours": argv.min_age_hours,
        # removed=这次真删了的；removable=按口径该删的（dry-run 时只有这个）
        "removed": result["removed"] if argv.apply else [],
        "removable": result["removed"],
        "failed": result["failed"],
        "skipped_young": result["skipped_young"],
    }

    # 无标记历史遗留：永远先给数字，删与不删由人决定
    unmarked_rows, unmarked_report = _unmarked_report(
        root, prefixes, argv.min_age_hours, now)
    payload["unmarked"] = unmarked_report
    if argv.purge_unmarked and argv.apply:
        gone = []
        for row in unmarked_rows:
            if any(row["name"].startswith(p) for p in argv.purge_unmarked):
                ok, _ = tmpspace.release(root / row["name"])
                if ok:
                    gone.append(row["name"])
                else:
                    payload.setdefault("failed", []).append(row["name"])
        payload["purged_unmarked"] = gone
    elif argv.purge_unmarked:
        payload["purge_unmarked_hint"] = (
            "已点名要删无标记目录，但没带 --apply——这一刀必须显式确认两次")
    _emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
