#!/usr/bin/env python3
"""审计日志：把关键决策追加写入 audit.jsonl，文本字段统一脱敏。

用途:
    主流程全程。记录步骤/执行者/输入引用/发现/输出摘要/依据/处置，
    disposition 枚举固定 {采纳,驳回,降级,重试,熔断,None}。

用法:
    python audit-log.py --log --step step4 --actor dispatcher \
        --input-ref diff.patch --finding-id AKIA-1 \
        --output-summary "启用 5 路" --basis "dispatch-plan 输出" --disposition 采纳 \
        --dir runs/run-20261024

退出码:
    0 = 写入成功
    2 = 参数错误（缺 --log/--step/--actor、disposition 越界、目录不可建）
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

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


DISPOSITIONS = {"采纳", "驳回", "降级", "重试", "熔断", "None"}
TEXT_FIELDS = ("input_ref", "finding_id", "output_summary", "basis")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="审计日志")
    parser.add_argument("--log", action="store_true", help="执行写日志动作")
    parser.add_argument("--step", required=True, help="主流程步骤标识，如 step4")
    parser.add_argument("--actor", required=True, help="执行者，如 dispatcher/verifier")
    parser.add_argument("--input-ref", dest="input_ref", help="输入产物引用")
    parser.add_argument("--finding-id", dest="finding_id", help="关联发现标识")
    parser.add_argument("--output-summary", dest="output_summary", help="输出摘要")
    parser.add_argument("--basis", help="判定依据")
    parser.add_argument("--disposition", help="处置：采纳/驳回/降级/重试/熔断/None")
    parser.add_argument("--dir", default="runs", help="审计目录（存放 audit.jsonl）")
    argv = parser.parse_args()
    if not argv.log:
        _emit({"ok": False, "error": "缺少 --log 动作"})
        return 2
    if argv.disposition is not None and argv.disposition not in DISPOSITIONS:
        _emit({"ok": False, "error": "disposition 越界: %s" % argv.disposition})
        return 2
    d = Path(argv.dir)
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _emit({"ok": False, "error": "目录不可建: %s (%s)" % (d, exc)})
        return 2
    entry = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "step": argv.step,
        "actor": argv.actor,
        "input_ref": argv.input_ref,
        "finding_id": argv.finding_id,
        "output_summary": argv.output_summary,
        "basis": argv.basis,
        "disposition": argv.disposition,
    }
    for key in TEXT_FIELDS:
        if entry[key]:
            entry[key] = redact(entry[key])
    out = d / "audit.jsonl"
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _emit({"ok": True, "file": str(out), "entry": entry})
    return 0


if __name__ == "__main__":
    sys.exit(main())
