#!/usr/bin/env python3
"""材料完备性校验：校验材料是否含目标符号与必要上下文，输出 A/B/C 档。

用途:
    主流程步骤 4 派发前调用。needed_context A=符号命中且上下文充分；
    B=命中但上下文薄；C=未命中（材料不足）。剥 diff 前缀时只保留 + 行与上下文行。

用法:
    python material-check.py --diff-file change.diff --symbol charge
    python material-check.py --file svc/payment.py --pattern "charge\\("

退出码:
    0 = 正常（A/B 档）
    1 = 有可处理的问题（C 档：材料不含目标符号）
    2 = 参数错误（缺 --file/--diff-file 或缺 --symbol/--pattern，或正则非法）
"""
import argparse
import json
import re
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_to_material(text):
    """剥 diff 前缀为材料行：只保留 + 行与上下文行，丢弃 - 行（防符号计数翻倍）。

    仅当文本含 diff --git 或 @@ 头时才按 diff 处理；返回 [(lineno, text), dropped_minus]。
    """
    if "diff --git" not in text and "@@" not in text:
        return [(i, l) for i, l in enumerate(text.splitlines(), 1)], 0
    lines = []
    dropped = 0
    newln = 0
    in_hunk = False
    for raw in text.splitlines():
        if raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m:
                newln = int(m.group(2))
                in_hunk = True
            continue
        if raw.startswith(("diff --git", "index ", "--- ", "+++ ", "new file", "deleted file",
                           "old mode", "new mode", "similarity", "rename ", "Binary")):
            continue
        if not in_hunk:
            continue
        if raw.startswith("+"):
            lines.append((newln, raw[1:]))
            newln += 1
        elif raw.startswith("-"):
            dropped += 1
        else:
            lines.append((newln, raw[1:] if raw.startswith(" ") else raw))
            newln += 1
    return lines, dropped


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="材料完备性校验")
    parser.add_argument("--file", help="源文件")
    parser.add_argument("--diff-file", help="diff 文件")
    parser.add_argument("--symbol", help="目标符号名")
    parser.add_argument("--pattern", help="目标正则")
    argv = parser.parse_args()
    if bool(argv.file) == bool(argv.diff_file):
        _emit({"ok": False, "error": "必须且只能给 --file 或 --diff-file 之一"})
        return 2
    if bool(argv.symbol) == bool(argv.pattern):
        _emit({"ok": False, "error": "必须且只能给 --symbol 或 --pattern 之一"})
        return 2
    if argv.file:
        p = Path(argv.file)
        if not p.is_file():
            _emit({"ok": False, "error": "源文件不存在: %s" % p})
            return 2
        text = p.read_text(encoding="utf-8", errors="replace")
        lines, dropped = [(i, l) for i, l in enumerate(text.splitlines(), 1)], 0
    else:
        p = Path(argv.diff_file)
        if not p.is_file():
            _emit({"ok": False, "error": "diff 文件不存在: %s" % p})
            return 2
        text = p.read_text(encoding="utf-8", errors="replace")
        lines, dropped = diff_to_material(text)
    try:
        needle = re.compile(r"\b%s\b" % re.escape(argv.symbol)) if argv.symbol else re.compile(argv.pattern)
    except re.error as exc:
        _emit({"ok": False, "error": "正则非法: %s" % exc})
        return 2
    hits = [(ln, t) for ln, t in lines if needle.search(t)]
    context_lines = 0
    if hits:
        first = hits[0][0]
        linenos = {ln for ln, _ in lines}
        for around in range(first - 3, first + 4):
            if around in linenos:
                context_lines += 1
    level = "C"
    if hits and context_lines >= 3:
        level = "A"
    elif hits:
        level = "B"
    problems = []
    warnings = []
    if level == "C":
        problems.append("材料不含目标 %s（C 档，需扩充材料）" % (argv.symbol or argv.pattern))
    if level == "B":
        warnings.append("命中但上下文不足 3 行（B 档），建议按函数体 ±3 行扩窗")
    if dropped:
        warnings.append("已按规则丢弃 %d 行 - 行（防符号计数翻倍）" % dropped)
    _emit(
        {
            "ok": not problems,
            "problems": problems,
            "warnings": warnings,
            "needed_context": {
                "level": level,
                "symbol_hits": len(hits),
                "context_lines": context_lines,
                "material_lines": len(lines),
                "files_covered": 1,
            },
            "completeness_hints": [
                "逐 hunk 标注：已覆盖 / 未覆盖 / 材料不足",
                "调用方与被调方窗口须一并纳入材料",
                "材料外代码一律版本锚定：git show <rev>:<路径>",
                "结论须附证据行号与原文片段",
            ],
        }
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
