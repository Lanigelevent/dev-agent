#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆检索层（步骤 1.4）：TF-IDF + cosine similarity，纯标准库。

用法：
    py skills/retro/scripts/memory_retrieval.py \
       --memory retro/agent-memory.jsonl \
       --query "ast-grep innerHTML XSS fix" \
       --top-k 3 \
       --max-chars 2000 \
       --min-score 0.25

输出 JSON：
    {"hits": [{"id": "...", "score": 0.xx, "snippet": "...", "task": "..."}]}

退出码：0=成功；1=有可处理的问题；2=输入/环境错误。
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path


def _tokenize(text: str) -> list[str]:
    """简单分词：小写 + 提取字母数字子串。"""
    return re.findall(r"[a-z0-9_]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    cnt = Counter(tokens)
    total = len(tokens) or 1
    return {w: c / total for w, c in cnt.items()}


def _idf(docs: list[dict]) -> dict[str, float]:
    """逆文档频率。"""
    n = len(docs)
    df = Counter()
    for doc in docs:
        for w in set(doc["_tokens"]):
            df[w] += 1
    return {w: math.log((n + 1) / (d + 1)) + 1 for w, d in df.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    common = set(a) & set(b)
    if not common:
        return 0.0
    num = sum(a[w] * b[w] for w in common)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def retrieve(memory_path: Path, query: str, top_k: int = 3,
             max_chars: int = 2000, min_score: float = 0.25) -> dict:
    """加载记忆 → TF-IDF → cosine Top-K。

    min_score：最小相似度阈值（缺省 0.25）。低于阈值的条目视为「只共享
    通用词」的噪声，不进 few-shot；数值按种子语料实测间隙标定——相关
    匹配 0.54–0.71、只共享通用词 ≤0.23（round-61，台账 93b028b2bc6f）。
    """
    # 加载
    docs = []
    with open(memory_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # 构建检索文本
            parts = [
                entry.get("task", ""),
                entry.get("summary", ""),
                entry.get("failure_category", ""),
                " ".join(entry.get("rule_codes", [])),
            ]
            text = " ".join(parts)
            entry["_tokens"] = _tokenize(text)
            entry["_text"] = text
            docs.append(entry)

    if not docs:
        return {"hits": []}

    # TF-IDF
    idf = _idf(docs)
    doc_tfidf = []
    for d in docs:
        tf = _tf(d["_tokens"])
        tfidf = {w: f * idf.get(w, 0) for w, f in tf.items()}
        doc_tfidf.append(tfidf)

    q_tokens = _tokenize(query)
    q_tf = _tf(q_tokens)
    q_tfidf = {w: f * idf.get(w, 0) for w, f in q_tf.items()}

    # 打分
    scored = []
    for d, tfidf_vec in zip(docs, doc_tfidf):
        score = _cosine(q_tfidf, tfidf_vec)
        if score >= min_score:
            scored.append((score, d))

    scored.sort(key=lambda x: -x[0])
    top = scored[:top_k]

    # 截断总字符
    hits = []
    total = 0
    for score, d in top:
        snippet = d.get("summary") or d.get("task", "")[:120]
        entry_chars = len(snippet) + 20
        if total + entry_chars > max_chars:
            break
        hits.append({
            "id": d.get("id", ""),
            "score": round(score, 4),
            "snippet": snippet[:200],
            "task": d.get("task", "")[:80],
            "rule_codes": d.get("rule_codes", []),
            "failure_category": d.get("failure_category", ""),
        })
        total += entry_chars

    return {"hits": hits, "query": query, "total_docs": len(docs)}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="记忆检索（TF-IDF + cosine）")
    p.add_argument("--memory", required=True, help="agent-memory.jsonl 路径")
    p.add_argument("--query", required=True, help="检索query")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--max-chars", type=int, default=2000)
    p.add_argument("--min-score", type=float, default=0.25,
                   help="最小 cosine 相似度（缺省 0.25，过滤只共享通用词的噪声）")
    args = p.parse_args()

    try:
        result = retrieve(Path(args.memory), args.query, args.top_k,
                          args.max_chars, args.min_score)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except FileNotFoundError:
        print(json.dumps({"error": "文件不存在: %s" % args.memory},
                         ensure_ascii=False, indent=2))
        sys.exit(2)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
