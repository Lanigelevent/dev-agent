#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记忆压缩与老化（步骤 1.6）。

用法：
    py skills/retro/scripts/compact-memory.py \
       --input retro/agent-memory.jsonl \
       --output retro/agent-memory-compact.jsonl \
       --similarity 0.8 \
       --max-age-days 30

逻辑：
1. 加载所有记忆条目，计算 age（当前时间 - timestamp）。
2. TF-IDF + cosine 相似度聚类：相似度 > --similarity 的条目归为一类，
   每类保留最详细的一条（summary/task 最长），其余标记 merged_into。
3. 删除 retrieval_count==0 且 age > --max-age-days 的冷记忆。
4. 输出压缩后 JSONL。

退出码：0=成功；1=有可处理的问题；2=输入/环境错误。
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _parse_ts(ts_str: str) -> datetime:
    """解析 ISO 8601 时间戳，始终返回 timezone-aware datetime。"""
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _tf(tokens: list[str]) -> dict[str, float]:
    cnt = Counter(tokens)
    total = len(tokens) or 1
    return {w: c / total for w, c in cnt.items()}


def _idf(docs: list[dict]) -> dict[str, float]:
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
    da = math.sqrt(sum(v * v for v in a.values()))
    db = math.sqrt(sum(v * v for v in b.values()))
    return num / (da * db) if da and db else 0.0


def _detail_score(entry: dict) -> int:
    """条目详细度：task + summary + edit_format 总字符数。"""
    return len(entry.get("task", "")) + len(entry.get("summary", "")) + \
           len(entry.get("edit_format", ""))


def compact(input_path: Path, output_path: Path,
            similarity: float = 0.8, max_age_days: int = 30) -> dict:
    """执行压缩与老化。"""
    now = datetime.now(timezone.utc)
    docs = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry["_ts"] = _parse_ts(entry.get("timestamp", ""))
            entry["_age_days"] = (now - entry["_ts"]).total_seconds() / 86400
            text = " ".join([
                entry.get("task", ""),
                entry.get("summary", ""),
                entry.get("failure_category", ""),
                " ".join(entry.get("rule_codes", [])),
            ])
            entry["_tokens"] = _tokenize(text)
            docs.append(entry)

    if not docs:
        return {"kept": 0, "merged": 0, "deleted_aged": 0, "total": 0}

    # TF-IDF
    idf = _idf(docs)
    tfidf_vecs = []
    for d in docs:
        tf = _tf(d["_tokens"])
        tfidf = {w: f * idf.get(w, 0) for w, f in tf.items()}
        tfidf_vecs.append(tfidf)

    # 聚类：贪心分簇（以簇首个未分配条目为种子，相似度 > threshold 入簇），
    # 簇内保留最详细的一条作代表，其余标记 merged_into 指向代表。
    n = len(docs)
    cluster_id = [-1] * n
    clusters = []
    for i in range(n):
        if cluster_id[i] != -1:
            continue
        cid = len(clusters)
        members = [i]
        cluster_id[i] = cid
        for j in range(i + 1, n):
            if cluster_id[j] != -1:
                continue
            if _cosine(tfidf_vecs[i], tfidf_vecs[j]) > similarity:
                cluster_id[j] = cid
                members.append(j)
        clusters.append(members)

    kept_ids = set()          # 簇代表（输出中保留完整内容）
    merged_into = {}          # 被合并 index -> 代表 index
    for members in clusters:
        rep = max(members, key=lambda idx: _detail_score(docs[idx]))
        kept_ids.add(rep)
        for idx in members:
            if idx != rep:
                merged_into[idx] = rep

    # 老化删除：retrieval_count==0 且 age > max_age_days
    to_delete = set()
    for i, d in enumerate(docs):
        if d.get("retrieval_count", 0) == 0 and d["_age_days"] > max_age_days:
            to_delete.add(i)
    # 簇代表被删除时，簇内被合并条目一并删除，避免 merged_into 指向不存在条目
    for idx, rep in merged_into.items():
        if rep in to_delete:
            to_delete.add(idx)

    # 输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        for i, d in enumerate(docs):
            if i in to_delete:
                continue
            out = {k: v for k, v in d.items() if not k.startswith("_")}
            if i in merged_into:
                target = merged_into[i]
                out["merged_into"] = docs[target].get("id", "?")
                out["merged_count"] = sum(
                    1 for v in merged_into.values() if v == target) + 1
            f.write(json.dumps(out, ensure_ascii=False) + "\n")

    return {
        "total": n,
        "kept": n - len(to_delete),
        "merged": len(merged_into),
        "deleted_aged": len(to_delete),
        "output": str(output_path),
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="记忆压缩与老化")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--similarity", type=float, default=0.8)
    p.add_argument("--max-age-days", type=int, default=30)
    args = p.parse_args()
    try:
        result = compact(Path(args.input), Path(args.output),
                         args.similarity, args.max_age_days)
    except FileNotFoundError:
        print(json.dumps({"error": "文件不存在: %s" % args.input},
                         ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
