#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""案例库（v2 链接型档案）：本地只存轻索引，完整内容存公开链接或本仓库档案。

减小本地索引成本、便于文档整理：案例条目只保留 id/title/category/takeaway/
verification/status 与链接（url=公开档案/仓库/官方文档，或 local_ref=本仓库
档案路径如轮报与测试）；根因/对策全文放链接指向的档案，本地不复制。

入库三路：
- --from-ledger：台账中 status=closed 的坑批量转索引（local_ref 指向台账与
  轮报，对策长文留在台账/轮报档案中）；
- --ingest：手工入库，必须提供 --url 或 --local-ref（公开档案优先），
  --takeaway 一句话对策供匹配；
- --match：词元重合 + 类别命中计分，返回轻索引与链接。

兼容读：v1 旧字段（description/countermeasure）自动映射为 title/takeaway。

用法示例：
    py case-match.py --match "审核人拒绝后仍然落盘了" --out retro
    py case-match.py --ingest --title "..." --takeaway "..." --url <公开链接> --out retro
    py case-match.py --from-ledger retro/pitfalls.json --out retro

退出码：0=成功（含零命中）；2=输入错误。
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _tokens(text):
    """中文二元组 + 英文/数字词元。"""
    text = str(text)
    out = set()
    for word in re.findall(r"[A-Za-z_][A-Za-z0-9_-]+", text):
        out.add(word.lower())
    cjk = re.sub(r"[^\u4e00-\u9fff]", " ", text)
    for chunk in cjk.split():
        for i in range(len(chunk) - 1):
            out.add(chunk[i:i + 2])
    return out


def _case_id(title, category):
    raw = "%s|%s" % (category, title)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _normalize(case):
    """v1 → v2 字段兼容映射（旧文件不必重写也能用）。"""
    out = dict(case)
    if "description" in out and "title" not in out:
        out["title"] = out.pop("description")
    if "countermeasure" in out and "takeaway" not in out:
        out["takeaway"] = out.pop("countermeasure")
    out.setdefault("url", "")
    out.setdefault("local_ref", "")
    out.setdefault("sources", [])
    out.setdefault("kind", "success")  # success 优秀案例 / failure 失败案例
    return out


def _load_cases(out_dir):
    path = Path(out_dir) / "cases.json"
    if not path.is_file():
        return path, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return path, [_normalize(c) for c in data.get("cases", [])]
    except (OSError, ValueError) as exc:
        raise ValueError("案例库 JSON 非法: %s" % exc)


def _save_cases(path, cases):
    path.write_text(json.dumps({"cases": cases}, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")


def _match(cases, problem, top):
    probe = _tokens(problem)
    scored = []
    for case in cases:
        score = 0.0
        case_tokens = _tokens("%s %s" % (case.get("title", ""),
                                         case.get("takeaway", "")))
        if case.get("category") and case["category"] in str(problem):
            score += 3
        overlap = probe & case_tokens
        score += len(overlap)
        if score > 0:
            scored.append((score, case, sorted(overlap)[:8]))
    scored.sort(key=lambda s: -s[0])
    hits = [{"score": round(score, 1),
             "id": case.get("id"),
             "kind": case.get("kind", "success"),
             "title": case.get("title", ""),
             "takeaway": case.get("takeaway", ""),
             "url": case.get("url", ""),
             "local_ref": case.get("local_ref", ""),
             "matched_tokens": tokens}
            for score, case, tokens in scored[:top]]
    for hit in hits:
        if hit["kind"] == "failure":
            hit["note"] = "失败案例：避免同样路径，详见链接档案"
    return hits


def main():
    parser = argparse.ArgumentParser(description="案例库 v2（链接型轻索引）")
    parser.add_argument("--out", required=True, help="案例库目录（cases.json）")
    parser.add_argument("--match", default="", help="待匹配的问题描述")
    parser.add_argument("--top", type=int, default=3, help="返回条数")
    parser.add_argument("--from-ledger", default="",
                        help="把台账中已结案的坑批量转索引")
    parser.add_argument("--ingest", action="store_true", help="手工入库一条")
    parser.add_argument("--category", default="手工", help="案例类别")
    parser.add_argument("--title", default="", help="案例标题（问题/结论一句话）")
    parser.add_argument("--takeaway", default="", help="一句话对策（供匹配复用）")
    parser.add_argument("--verification", default="", help="验收口径或指向")
    parser.add_argument("--url", default="", help="公开档案/仓库/文档链接")
    parser.add_argument("--local-ref", dest="local_ref", default="",
                        help="本仓库档案路径（如 retro/round-1-report.md）")
    argv = parser.parse_args()
    try:
        cases_path, cases = _load_cases(argv.out)
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    Path(argv.out).mkdir(parents=True, exist_ok=True)

    if argv.match:
        hits = _match(cases, argv.match, max(1, argv.top))
        _emit({"ok": True, "mode": "match", "problem": argv.match,
               "hits": hits, "cases_total": len(cases),
               "note": "命中即按链接取档案复用；未命中走总监升级链签发研究简报"})
        return 0

    if argv.ingest:
        if not argv.title or not argv.takeaway:
            _emit({"ok": False, "error": "入库需要 title 与 takeaway"})
            return 2
        if not argv.url and not argv.local_ref:
            _emit({"ok": False, "error": "链接型档案要求 --url 或 --local-ref "
                                         "至少一项（完整内容不入本地索引）"})
            return 2
        case = {"id": _case_id(argv.title, argv.category),
                "title": argv.title[:400], "category": argv.category,
                "takeaway": argv.takeaway[:400],
                "verification": argv.verification[:200],
                "url": argv.url.strip(), "sources": [],
                "local_ref": argv.local_ref.strip(), "status": "verified"}
        cases = [c for c in cases if c.get("id") != case["id"]]
        cases.append(case)
        _save_cases(cases_path, cases)
        _emit({"ok": True, "mode": "ingest", "id": case["id"],
               "cases_total": len(cases),
               "archive": case["url"] or case["local_ref"]})
        return 0

    if argv.from_ledger:
        ledger = Path(argv.from_ledger)
        if not ledger.is_file():
            _emit({"ok": False, "error": "台账不存在: %s" % ledger})
            return 2
        try:
            data = json.loads(ledger.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "台账 JSON 非法: %s" % exc})
            return 2
        added = 0
        known = {c.get("id") for c in cases}
        for pitfall in data.get("pitfalls", []):
            if pitfall.get("status") != "closed":
                continue
            case = {"id": pitfall.get("id") or _case_id(
                pitfall.get("category", "手工"),
                pitfall.get("description", "")),
                "title": pitfall.get("description", ""),
                "category": pitfall.get("category", "手工"),
                "takeaway": pitfall.get("countermeasure", ""),
                "verification": pitfall.get("verification", "已结案，详见台账"),
                "url": "", "sources": [],
                "local_ref": str(ledger), "status": "verified"}
            if case["id"] not in known:
                cases.append(_normalize(case))
                known.add(case["id"])
                added += 1
        _save_cases(cases_path, cases)
        _emit({"ok": True, "mode": "from-ledger", "added": added,
               "cases_total": len(cases),
               "note": "长文留在台账/轮报档案，本地仅入轻索引"})
        return 0

    _emit({"ok": False, "error": "需要 --match / --ingest / --from-ledger 之一"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
