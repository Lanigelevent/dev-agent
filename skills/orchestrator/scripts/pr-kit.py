#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PR 交付包：把评审/修复结果转成平台 PR 素材（标题、正文、行内评论 JSON）。

业界评审工具的"最后一公里"：评审结论要能进入开发者的 PR 工作流，而不是
躺在终端里。本脚本只做产物转换（只读），不访问任何平台、不发网络请求；
PR 的实际创建与提交由人或宿主用这些素材完成。

输入 --result 为编排器 runner.py 的 stdout JSON（含 state/run_dir/inline/
report_path 等字段），--approval 可选附带批准书路径。

产出（--out 目录）：
- pr-title.txt：PR 标题（一行）；
- pr-body.md：PR 正文（摘要/发现表格/测试与验证记录/报告全文引用）；
- review-comments.json：行内评论数组（path/line/severity/message/suggestion），
  与主流平台的 review comment 结构对齐。

用法示例：
    py pr-kit.py --result run-output.json --out pr-bundle

退出码：0=成功；2=输入错误。
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


def _severity_rank(item):
    return {"高": 0, "中": 1, "低": 2}.get(item.get("severity", ""), 3)


def _findings_table(inline):
    if not inline:
        return "（无行内发现）"
    lines = ["| 文件 | 行 | 严重度 | 问题 | 建议 |",
             "|---|---|---|---|---|"]
    for item in sorted(inline, key=_severity_rank):
        lines.append("| %s | %s | %s | %s | %s |" % (
            str(item.get("file", "-")).replace("|", "\\|"),
            item.get("line", "-"),
            item.get("severity", "-"),
            str(item.get("message", "")).replace("|", "\\|")[:80],
            str(item.get("suggestion", "")).replace("|", "\\|")[:80]))
    return "\n".join(lines)


def _build_body(result, inline, approval):
    state = result.get("state", "-")
    run_dir = result.get("run_dir", "-")
    rounds = result.get("rounds_used", "-")
    lines = ["## 评审摘要", ""]
    lines.append("- 结论状态：%s；编排轮数：%s；run 目录：`%s`" % (state, rounds, run_dir))
    tests = result.get("tests") or {}
    if tests.get("status"):
        lines.append("- 行为回归测试：%s" % tests.get("status"))
    if approval:
        lines.append("- 审核人批准书：`%s`" % approval)
    lines.append("")
    lines.append("## 发现与建议")
    lines.append("")
    lines.append(_findings_table(inline))
    lines.append("")
    report = result.get("report_path")
    if report and Path(report).is_file():
        text = Path(report).read_text(encoding="utf-8", errors="replace")
        lines.append("<details>")
        lines.append("<summary>完整评审报告（report.md）</summary>")
        lines.append("")
        lines.append(text.strip())
        lines.append("")
        lines.append("</details>")
        lines.append("")
    lines.append("---")
    lines.append("*由 dev-agent 生成；修复走工单-批准书-五道闸流程，"
                 "合并前请确认仓库测试通过。*")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="PR 交付包生成（只读转换）")
    parser.add_argument("--result", required=True, help="编排器输出 JSON 文件")
    parser.add_argument("--out", required=True, help="PR 素材产物目录")
    parser.add_argument("--approval", default="", help="审核人批准书路径（可选）")
    argv = parser.parse_args()
    result_path = Path(argv.result)
    out_dir = Path(argv.out)
    if not result_path.is_file():
        _emit({"ok": False, "error": "结果文件不存在: %s" % result_path})
        return 2
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "结果 JSON 非法: %s" % exc})
        return 2
    if not isinstance(result, dict):
        _emit({"ok": False, "error": "结果需为 JSON 对象"})
        return 2
    inline = result.get("inline") or []
    if not isinstance(inline, list):
        inline = []
    out_dir.mkdir(parents=True, exist_ok=True)

    high = sum(1 for item in inline if item.get("severity") == "高")
    title = "Code Review：发现 %d 项（高 %d）— %s" % (
        len(inline), high, result.get("state", "-"))
    title_path = out_dir / "pr-title.txt"
    title_path.write_text(title, encoding="utf-8", newline="\n")
    body_path = out_dir / "pr-body.md"
    body_path.write_text(_build_body(result, inline, argv.approval),
                         encoding="utf-8", newline="\n")
    comments = [{"path": item.get("file", ""),
                 "line": item.get("line"),
                 "body": "[%s] %s\n\n建议：%s" % (
                     item.get("severity", "-"),
                     item.get("message", ""),
                     item.get("suggestion", ""))}
                for item in inline]
    comments_path = out_dir / "review-comments.json"
    comments_path.write_text(json.dumps(comments, ensure_ascii=False, indent=2),
                             encoding="utf-8", newline="\n")
    _emit({"ok": True, "title": title,
           "pr_title": str(title_path), "pr_body": str(body_path),
           "review_comments": str(comments_path),
           "inline_count": len(inline),
           "note": "素材已生成；PR 创建与提交由人或宿主完成（本脚本不联网）"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
