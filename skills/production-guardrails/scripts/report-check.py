#!/usr/bin/env python3
"""报告模板校验：七段齐全 + 补丁格式 + 阅读顺序说明，不过不交付。

用途:
    主流程步骤 10。报告文件或 stdin（-）传入，缺段/补丁格式不符即退出 1；
    stdin 与文件两条路都按 UTF-8 读，不跟宿主 ANSI locale 走。

用法:
    python report-check.py report.md
    cat report.md | python report-check.py -

退出码:
    0 = 校验通过
    1 = 校验失败（缺段/补丁格式/阅读顺序说明缺失）
    2 = 参数错误（文件不存在、目录不可读）
"""
import argparse
import json
import sys
from pathlib import Path

TITLE = "# 代码评审报告"
CALIBER = "【评审口径】"
SECTIONS = [
    "## 运行信息",
    "## 一、变更摘要",
    "## 二、风险评分",
    "## 三、测试建议",
    "## 四、优化步骤手册",
    "## 五、行内评论",
    "## 六、修复补丁建议",
]
READING_ORDER = "建议阅读顺序"
PATCH_SECTION = "## 六、修复补丁建议"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def check(text):
    missing = []
    if TITLE not in text:
        missing.append(TITLE)
    if CALIBER not in text:
        missing.append(CALIBER)
    for s in SECTIONS:
        if s not in text:
            missing.append(s)
    problems = []
    if READING_ORDER not in text:
        problems.append("缺阅读顺序说明（建议阅读顺序：先…后…）")
    idx = text.find(PATCH_SECTION)
    if idx >= 0:
        tail = text[idx + len(PATCH_SECTION):]
        nxt = tail.find("\n## ")
        section6 = tail[:nxt] if nxt >= 0 else tail
        has_note = "未生成补丁" in section6
        has_diff = ("```diff" in section6 or "diff --git" in section6 or "--- a/" in section6)
        if not has_note and not has_diff:
            problems.append("补丁段既无「未生成补丁」说明也无 unified diff 内容")
    else:
        problems.append("找不到补丁段：%s" % PATCH_SECTION)
    return missing, problems


def main():
    parser = argparse.ArgumentParser(description="报告模板校验")
    parser.add_argument("report", help="报告文件路径，或 - 读 stdin")
    argv = parser.parse_args()
    if argv.report == "-":
        # 与 findings-check 同口径：stdin 显式 UTF-8，不受宿主 ANSI locale 影响
        # （cp936 下中文报告会被解成代理对，校验结果变成「找不到章节」）。
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
        text = sys.stdin.read()
    else:
        p = Path(argv.report)
        if not p.is_file():
            _emit({"ok": False, "error": "报告文件不存在: %s" % p})
            return 2
        text = p.read_text(encoding="utf-8", errors="replace")
    missing, problems = check(text)
    _emit({"ok": not missing and not problems, "missing": missing, "problems": problems})
    return 0 if (not missing and not problems) else 1


if __name__ == "__main__":
    sys.exit(main())
