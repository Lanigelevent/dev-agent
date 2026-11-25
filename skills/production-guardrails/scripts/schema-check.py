#!/usr/bin/env python3
"""产物 schema 校验：按 references/schemas.md 校验 8 个产物并做脱敏兜底。

用途:
    主流程步骤 10。产物缺失、缺必填字段、枚举越界、未脱敏密钥形态均判失败。

用法:
    python schema-check.py --dir runs/run-20261024

退出码:
    0 = 全部通过
    1 = 有产物不合格
    2 = 参数错误（run 目录不存在、schemas.md 不可读）
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMAS_MD = Path(__file__).resolve().parents[1] / "references" / "schemas.md"
ARTIFACTS = [
    "step2_collect.json",
    "step3_risk.json",
    "step4_dispatch.json",
    "step5_findings.json",
    "step6_verification.json",
    "step7_summary.json",
    "step8_backverify.json",
    "checkpoint.json",
]
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


def load_schemas(path):
    """解析 schemas.md：## 节名 + ```json 块。"""
    text = path.read_text(encoding="utf-8")
    schemas = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## ") and line[3:].strip().endswith(".json"):
            current = line[3:].strip()
        elif line.startswith("```json") and current:
            schemas[current] = None
        elif line.startswith("```") and current and current in schemas \
                and schemas[current] is None:
            continue
        elif current in schemas and schemas[current] is None and line.strip() and \
                not line.startswith("```"):
            schemas[current] = line.strip()
    return {k: json.loads(v) for k, v in schemas.items() if v}


def _walk(node):
    """递归产出 (key, value) 与裸字符串。"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k, v
            for pair in _walk(v):
                yield pair
    elif isinstance(node, list):
        for v in node:
            for pair in _walk(v):
                yield pair


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def validate(data, schema):
    problems = []
    for key in schema.get("required", []):
        if key not in data:
            problems.append("缺必填字段: %s" % key)
    enums = schema.get("enums", {})
    for k, v in _walk(data):
        if k in enums and not isinstance(v, (dict, list)) and v not in enums[k]:
            problems.append("枚举越界: %s=%s" % (k, v))
    for s in _strings(data):
        if redact(s) != s:
            problems.append("存在未脱敏密钥形态")
            break
    return problems


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="产物 schema 校验")
    parser.add_argument("--dir", required=True, help="run 目录（含 8 个产物）")
    argv = parser.parse_args()
    d = Path(argv.dir)
    if not d.is_dir():
        _emit({"ok": False, "error": "run 目录不存在: %s" % d})
        return 2
    if not SCHEMAS_MD.is_file():
        _emit({"ok": False, "error": "schemas.md 不可读: %s" % SCHEMAS_MD})
        return 2
    schemas = load_schemas(SCHEMAS_MD)
    results = []
    failed = False
    for name in ARTIFACTS:
        problems = []
        f = d / name
        if not f.is_file():
            problems.append("产物缺失")
        else:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except ValueError as exc:
                problems.append("JSON 非法: %s" % exc)
                data = None
            if data is not None and name in schemas:
                problems.extend(validate(data, schemas[name]))
        failed = failed or bool(problems)
        results.append({"name": name, "problems": problems})
    _emit({"ok": not failed, "schema_source": str(SCHEMAS_MD), "artifacts": results})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
