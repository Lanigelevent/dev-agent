#!/usr/bin/env python3
"""外部基准桥接：把 prepared manifest / 样本转换为 reviewbench 用例格式。

用途:
    只做格式转换与结构校验，不负责执行外部基准。
    用例 id 一律取样本 sha（易错点 3），不生成序号主键。

用法:
    python reviewbench-bridge.py --input prepared/manifest.json --out cases.json
    python reviewbench-bridge.py --input samples.json --validate-only

退出码:
    0 = 正常
    1 = 输入结构不合格
    2 = 参数/环境错误
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


def convert(data):
    """接受 prepared manifest（含 diffs）或样本清单（含 files），输出 reviewbench 用例。"""
    cases = []
    if isinstance(data, dict) and isinstance(data.get("samples"), list):
        for s in data["samples"]:
            sha = s.get("fix_commit")
            if not sha:
                continue
            cases.append({
                "id": sha,
                "repo": s.get("repo", ""),
                "diff": "",
                "expect": {"defect_class": s.get("defect_class", ""),
                           "files": s.get("files", [])},
            })
        return cases
    if isinstance(data, list) and data and isinstance(data[0], dict) and "sample_id" in data[0]:
        for m in data:
            cases.append({
                "id": m.get("sample_id", ""),
                "repo": "",
                "diff": ";".join(m.get("diffs", [])),
                "expect": {"defect_class": "", "files": m.get("files", [])},
            })
        return cases
    return None


def main():
    parser = argparse.ArgumentParser(description="reviewbench 桥接")
    parser.add_argument("--input", required=True, help="manifest.json 或 samples.json")
    parser.add_argument("--out", help="转换结果输出路径（--validate-only 时可省）")
    parser.add_argument("--validate-only", action="store_true")
    argv = parser.parse_args()
    ip = Path(argv.input)
    if not ip.is_file():
        _emit({"ok": False, "error": "输入文件不存在: %s" % ip})
        return 2
    try:
        data = json.loads(ip.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "输入 JSON 非法: %s" % exc})
        return 2
    cases = convert(data)
    if cases is None:
        _emit({"ok": False, "error": "输入结构不合格：需 prepared manifest 或样本清单"})
        return 1
    if not cases:
        _emit({"ok": False, "error": "转换后无用例"})
        return 1
    if argv.validate_only:
        _emit({"ok": True, "mode": "validate-only", "cases": len(cases),
               "ids": [c["id"][:12] for c in cases[:10]]})
        return 0
    if not argv.out:
        _emit({"ok": False, "error": "缺 --out（或用 --validate-only）"})
        return 2
    payload = {"benchmark": "reviewbench", "version": 1, "cases": cases}
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit({"ok": True, "mode": "convert", "out": str(out), "cases": len(cases)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
