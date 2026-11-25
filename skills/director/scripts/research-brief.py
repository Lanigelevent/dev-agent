#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研究简报：把疑难杂症转成可执行的联网调研任务书（脚本不联网，检索由宿主执行）。

总监升级链的第三步：案例库未命中后，本脚本产出 brief-<id>.md 与
brief-<id>.json——问题定义、约束、检索词（中英）、验收口径、已知案例。
宿主（智能体）持简报用自身联网工具检索，结论经案例库入库沉淀。

检索词生成规则：问题描述词元化后，组合模板（"Python stdlib <词元>"、
"<词元> best practice site:docs / github" 等中英双语），保证可复现。

用法示例：
    py research-brief.py --description "跨文件污点分析如何只用标准库实现" \
        --out retro --case-dir retro
    py research-brief.py --description ... --out retro --from-pitfall <台账ID>

退出码：0=成功；2=输入错误。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

CONSTRAINTS = [
    "只用 Python 标准库，禁第三方依赖（硬约束 1）",
    "对被审仓库只读；产物只落复盘/研究目录（产物红线）",
    "改动需过反向验证 + synth 精度基线（行为级优化口径）",
]
QUERY_TEMPLATES = [
    "Python stdlib {kw} implementation",
    "{kw} static analysis without third-party libraries",
    "{kw} 最佳实践 站内:github",
    "{zh} 实现方案",
]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _tokens(text):
    import re
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_-]+", str(text))
    cjk = re.sub(r"[^\u4e00-\u9fff]", " ", str(text))
    bigrams = [chunk[i:i + 2] for chunk in cjk.split()
               for i in range(len(chunk) - 1)]
    return words[:6] + bigrams[:6]


def _pitfall_lookup(ledger, pitfall_id):
    try:
        data = json.loads(Path(ledger).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("台账不可读: %s" % exc)
    for p in data.get("pitfalls", []):
        if p.get("id") == pitfall_id:
            return p
    raise ValueError("台账无此坑: %s" % pitfall_id)


def main():
    parser = argparse.ArgumentParser(description="研究简报生成（脚本不联网）")
    parser.add_argument("--description", default="", help="疑难问题描述")
    parser.add_argument("--from-pitfall", default="", help="从台账坑 ID 生成")
    parser.add_argument("--ledger", default="", help="台账路径（配合 --from-pitfall）")
    parser.add_argument("--out", required=True, help="简报产物目录")
    parser.add_argument("--case-dir", default="", help="案例库目录（附已知对策）")
    argv = parser.parse_args()
    description = argv.description
    pitfall = None
    if argv.from_pitfall:
        if not argv.ledger or not Path(argv.ledger).is_file():
            _emit({"ok": False, "error": "--from-pitfall 需要有效 --ledger"})
            return 2
        try:
            pitfall = _pitfall_lookup(argv.ledger, argv.from_pitfall)
        except ValueError as exc:
            _emit({"ok": False, "error": str(exc)})
            return 2
        description = description or pitfall.get("description", "")
    if not description:
        _emit({"ok": False, "error": "需要 --description 或 --from-pitfall"})
        return 2

    brief_id = hashlib.sha256(description.encode("utf-8")).hexdigest()[:12]
    keywords = _tokens(description)
    queries = [t.format(kw=k, zh=description[:30])
               for k in keywords[:4] for t in QUERY_TEMPLATES][:8]
    known = []
    case_dir = Path(argv.case_dir) if argv.case_dir else None
    if case_dir and (case_dir / "cases.json").is_file():
        try:
            cases = json.loads((case_dir / "cases.json").read_text(encoding="utf-8"))
            for case in cases.get("cases", []):
                if case.get("category", "") in description or any(
                        k in str(case.get("description", "")) for k in keywords):
                    known.append({"id": case.get("id"),
                                  "countermeasure": case.get("countermeasure", "")})
        except (OSError, ValueError):
            known = []

    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    brief = {"id": brief_id, "description": description,
             "pitfall_id": pitfall.get("id") if pitfall else None,
             "constraints": CONSTRAINTS,
             "queries": queries,
             "known_cases": known,
             "acceptance": [
                 "检索来源可信（官方文档/权威仓库优先），记录 URL",
                 "结论必须给出可落地的三种形态之一：配置扩展/测试补充/代码修改",
                 "行为级改动必过反向验证 + synth 精度基线",
             ]}
    md = ["# 研究简报 %s" % brief_id, "",
          "**问题**：%s" % description, "",
          "## 约束", ""]
    md += ["- %s" % c for c in CONSTRAINTS]
    md += ["", "## 检索词（宿主联网执行）", ""]
    md += ["- `%s`" % q for q in queries]
    md += ["", "## 已知案例（先复用）", ""]
    md += (["- %s：%s" % (k["id"], k["countermeasure"][:80]) for k in known]
           or ["- （案例库未命中，本轮为首次研究）"])
    md += ["", "## 验收口径", ""]
    md += ["- %s" % a for a in brief["acceptance"]]
    md_path = out_dir / ("brief-%s.md" % brief_id)
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    brief_path = out_dir / ("brief-%s.json" % brief_id)
    brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2),
                          encoding="utf-8", newline="\n")
    _emit({"ok": True, "brief_id": brief_id, "brief_md": str(md_path),
           "brief_json": str(brief_path), "queries": queries,
           "known_cases": known,
           "note": "简报已签发；宿主持简报联网检索，结论入案例库沉淀"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
