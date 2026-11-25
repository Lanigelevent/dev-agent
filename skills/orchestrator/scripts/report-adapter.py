#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告输出适配器：按风格 spec 重渲染评审报告（round-104）。

用途
----
读取评审 findings JSON + 风格 spec，按详细程度/受众/行业三维适配
产出新报告。与 runner step10 产物解耦——只要符合 findings JSON 形
状即可输入（不限于 runner 产出）。

三适配维度
----------
  detail_level: executive（仅高严重度、截断证据）/ standard（全量）/
                deep（全量 + 完整证据 + 修复步骤全文）
  audience:     management（管理层摘要，去技术细节）/ engineering
                （工程师全文）/ auditor（审计取证——完整证据链）
  industry:     术语映射（如 finance 把「评审发现」→「审计发现」）

风格 spec（JSON 文件或内置 preset 名）
--------------------------------------
  {"schema": "report-style/1", "detail_level": "...", "audience": "...",
   "industry": "...", "max_findings": N, "min_severity": "高|中|低"}

内置 preset：executive / engineering / audit

用法示例：
    python report-adapter.py --findings findings.json --style executive
    python report-adapter.py --findings f.json --style spec.json --out out.md

退出码：0=成功；1=适配失败（findings 形状非法）；2=参数错误。
stdout 输出单个 JSON 文档（含 out_path）。
"""
import argparse
import json
import sys
from pathlib import Path

SELF = Path(__file__).resolve().parent
STYLES_DIR = SELF / "styles"

SEV_ORDER = {"高": 0, "中": 1, "低": 2}
SEV_ORDER_INV = {0: "高", 1: "中", 2: "低"}

PRESETS = {
    "executive": {
        "detail_level": "executive", "audience": "management",
        "industry": "generic", "max_findings": 10, "min_severity": "高",
    },
    "engineering": {
        "detail_level": "deep", "audience": "engineering",
        "industry": "generic",
    },
    "audit": {
        "detail_level": "deep", "audience": "auditor",
        "industry": "finance", "max_findings": 50,
    },
}

INDUSTRY_TERMS = {
    "finance": {"评审发现": "审计发现", "评审报告": "审计报告",
                "严重度": "风险等级", "修复步骤": "整改建议"},
    "healthcare": {"评审发现": "合规发现", "严重度": "风险等级"},
    "gaming": {"评审发现": "QA 发现", "严重度": "Bug 级别"},
    "generic": {},
}


def _validate_spec(spec, origin):
    """自定义 spec 枚举校验（r105：非法枚举在加载期拒绝）。"""
    enums = {
        "detail_level": ("executive", "standard", "deep"),
        "audience": ("management", "engineering", "auditor"),
        "industry": tuple(INDUSTRY_TERMS),
        "min_severity": tuple(SEV_ORDER),
    }
    for key, allowed in enums.items():
        v = spec.get(key)
        if v is not None and v not in allowed:
            raise ValueError(
                "%s: %r 非法，%s 允许值 %s" % (origin, v, key, list(allowed)))
    mx = spec.get("max_findings")
    if mx is not None and (not isinstance(mx, int) or isinstance(mx, bool)
                           or mx < 1):
        raise ValueError("%s: max_findings 须为正整数: %r" % (origin, mx))
    return spec


def _load_style(style_arg):
    """从 preset 名或 JSON 文件路径加载风格 spec。"""
    if style_arg in PRESETS:
        return dict(PRESETS[style_arg])
    p = Path(style_arg)
    if not p.is_file():
        raise ValueError("风格文件不存在: %s" % p)
    spec = json.loads(p.read_text(encoding="utf-8"))
    if spec.get("schema") != "report-style/1":
        raise ValueError("schema 必须为 report-style/1: %s" % spec.get("schema"))
    return _validate_spec(spec, str(p))


def _filter_findings(findings, spec):
    """按 min_severity + max_findings 过滤。"""
    min_sev = spec.get("min_severity")
    min_rank = SEV_ORDER.get(min_sev, 3) if min_sev else 3
    filtered = [f for f in findings
                if SEV_ORDER.get(f.get("severity", "低"), 3) <= min_rank]
    max_n = spec.get("max_findings")
    if max_n is not None:
        filtered = filtered[:max_n]
    return filtered


def _truncate(text, spec):
    """按 detail_level 截断证据文本。"""
    if not text:
        return text
    dl = spec.get("detail_level", "standard")
    if dl == "executive":
        return str(text)[:60] + ("…" if len(str(text)) > 60 else "")
    return text


def _apply_terminology(text, industry):
    """行业术语映射。"""
    for old, new in INDUSTRY_TERMS.get(industry, {}).items():
        text = text.replace(old, new)
    return text


def render(findings, meta, spec):
    """按风格 spec 渲染 markdown 报告。"""
    industry = spec.get("industry", "generic")
    audience = spec.get("audience", "engineering")
    detail = spec.get("detail_level", "standard")
    title = _apply_terminology("代码评审报告", industry)
    sev_label = _apply_terminology("严重度", industry)

    lines = ["# " + title, ""]
    if meta:
        lines.append("【评审口径】%s" % _apply_terminology(meta, industry))
        lines.append("")

    if audience == "management":
        lines.append("## 摘要")
        sev_counts = {}
        for f in findings:
            sev_counts[f.get("severity", "低")] = sev_counts.get(
                f.get("severity", "低"), 0) + 1
        summary = "、".join("%s %d 项" % (k, v)
                           for k, v in sorted(sev_counts.items(),
                                              key=lambda x: SEV_ORDER.get(x[0], 3)))
        lines.append("共发现 %d 项：%s" % (len(findings), summary or "无"))
        lines.append("")

    lines.append("## " + _apply_terminology("评审发现", industry))
    lines.append("")
    if not findings:
        lines.append("（无结论产出）")
        return "\n".join(lines)

    show_evidence = detail in ("standard", "deep")
    show_fix = detail in ("standard", "deep") or audience != "management"
    for i, f in enumerate(findings, 1):
        loc = f.get("loc", "%s:%s" % (f.get("file", "?"), f.get("line", "?")))
        lines.append("### %d. [%s] %s" % (i, f.get("severity", "中"),
                                          _apply_terminology(
                                              f.get("desc", ""), industry)))
        lines.append("- 定位：%s" % loc)
        if show_evidence:
            ev = _truncate(f.get("evidence", f.get("snippet", "")), spec)
            if ev:
                lines.append("- 证据：%s" % ev)
        if show_fix:
            fix = _truncate(f.get("fix", ""), spec)
            if fix:
                lines.append("- 修复：%s" % _apply_terminology(fix, industry))
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="报告输出适配器")
    parser.add_argument("--findings", required=True,
                        help="findings JSON 文件路径")
    parser.add_argument("--style", required=True,
                        help="风格 preset 名或 spec JSON 文件路径")
    parser.add_argument("--meta", default=None,
                        help="评审元信息 JSON（可选）")
    parser.add_argument("--out", default=None, help="输出 markdown 路径")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    fp = Path(args.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "findings 文件不存在: %s" % fp})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except ValueError as exc:
        _emit({"ok": False, "error": "findings JSON 解析失败: %s" % exc})
        return 2
    findings = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(findings, list):
        _emit({"ok": False, "error": "findings 必须为 JSON 数组"})
        return 2

    try:
        spec = _load_style(args.style)
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2

    meta = None
    if args.meta:
        mp = Path(args.meta)
        if mp.is_file():
            meta = json.loads(mp.read_text(encoding="utf-8")).get("meta")

    filtered = _filter_findings(findings, spec)
    rendered = render(filtered, meta, spec)

    out_path = Path(args.out) if args.out else fp.parent / "report-adapted.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8", newline="\n")
    _emit({"ok": True, "out_path": str(out_path), "style": spec,
           "findings_in": len(findings), "findings_out": len(filtered)})
    return 0


def _emit(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
