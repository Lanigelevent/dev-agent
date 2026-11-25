#!/usr/bin/env python3
"""误报模式库：read/record，条目上限 50 按 last_hit 淘汰，单条计数上限 50。

用途:
    主流程步骤 4（下发已知误报模式）与步骤 10（用户驳回项入库）。
    三档举证：rejected_count >=5 严格、>=2 加强、=1 常规。

用法:
    python experience.py record --dir runs --pattern "npe-optional" --dimension "边界与空值"
    python experience.py read --dir runs --dimension "边界与空值"

退出码:
    0 = 正常
    2 = 参数错误（缺子命令/必填项、库文件不可读写）
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

MAX_ENTRIES = 50
MAX_COUNT = 50
SECRET_PATTERNS = [
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|authorization)\s*\"?\s*[:=]\s*)([^\s,;#]{3,})"), r"\1<redacted>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"mysql://[^\s/:]+:[^@\s]+@"), "mysql://<redacted>@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted>"),
]


def redact(text):
    """密钥形态统一脱敏为 <redacted>。"""
    if not text:
        return text
    t = str(text)
    for pat, rep in SECRET_PATTERNS:
        t = pat.sub(rep, t)
    return t


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _load(path):
    if not path.is_file():
        return {"entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def evidence_level(count):
    if count >= 5:
        return "严格"
    if count >= 2:
        return "加强"
    if count >= 1:
        return "常规"
    return "无"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="误报模式库")
    sub = parser.add_subparsers(dest="mode")
    p_read = sub.add_parser("read")
    p_read.add_argument("--dir", default="runs")
    p_read.add_argument("--dimension", help="按维度过滤")
    p_record = sub.add_parser("record")
    p_record.add_argument("--dir", default="runs")
    p_record.add_argument("--pattern", required=True, help="误报模式标识")
    p_record.add_argument("--dimension", required=True, help="所属维度")
    p_record.add_argument("--scenario", default="", help="档位/场景")
    p_record.add_argument("--count", type=int, default=1, help="本次驳回次数")
    argv = parser.parse_args()
    if not argv.mode:
        _emit({"ok": False, "error": "缺少子命令 read|record"})
        return 2
    d = Path(argv.dir)
    d.mkdir(parents=True, exist_ok=True)
    db = d / "experience.json"
    data = _load(db)
    if argv.mode == "read":
        entries = [e for e in data["entries"]
                   if not argv.dimension or e.get("dimension") == argv.dimension]
        for e in entries:
            e["evidence_level"] = evidence_level(e.get("rejected_count", 0))
        _emit({"ok": True, "db": str(db), "entries": entries})
        return 0
    if argv.count <= 0:
        _emit({"ok": False, "error": "--count 必须为正整数"})
        return 2
    pattern = redact(argv.pattern)
    hit = None
    for e in data["entries"]:
        if e.get("pattern") == pattern and e.get("dimension") == argv.dimension \
                and e.get("scenario", "") == argv.scenario:
            hit = e
            break
    if hit:
        hit["rejected_count"] = min(MAX_COUNT, hit.get("rejected_count", 0) + argv.count)
        hit["last_hit"] = _now()
        entry = hit
    else:
        entry = {"pattern": pattern, "dimension": argv.dimension, "scenario": argv.scenario,
                 "rejected_count": min(MAX_COUNT, argv.count), "last_hit": _now()}
        data["entries"].append(entry)
    if len(data["entries"]) > MAX_ENTRIES:
        data["entries"].sort(key=lambda e: e.get("last_hit", ""), reverse=True)
        data["entries"] = data["entries"][:MAX_ENTRIES]
    db.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    out = dict(entry)
    out["evidence_level"] = evidence_level(entry["rejected_count"])
    _emit({"ok": True, "db": str(db), "entry": out})
    return 0


if __name__ == "__main__":
    sys.exit(main())
