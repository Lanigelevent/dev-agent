#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trace-export.py — trace JSONL → 评测集导出器（AB-01，r199；第 87 号脚本）。

用途：
    把 agent/trace.py 落盘的会话 JSONL（span + score 记录）聚合为评测集
    JSON：逐会话统计（span 数/llm 调用/token/成本/状态）+ score 明细
    （Langfuse score 模型的本地形态：name/value/data_type/comment）。
    评测集消费者 = judge 重跑路径（AB-02 集成）与人工回放对账；
    run-samples.py 的评审缺陷样本 schema 与 trace 会话不同构（r199 勘误，
    见 reports/absorb-list-r194.md AB-01 注记）。

用法示例：
    py trace-export.py --trace reports/traces/<session>.jsonl --out eval-set.json
    py trace-export.py --trace a.jsonl b.jsonl --out eval-set.json

退出码：
    0 = 成功；1 = 有可处理的问题（trace 文件无 score 且 --require-score）；
    2 = 输入/环境错误（文件缺失/JSON 非法）。

stdout 只有一个 JSON 文档；诊断走 stderr。
"""
import argparse
import json
import sys
from pathlib import Path


def _read_records(path):
    records, bad = [], 0
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                bad += 1
    return records, bad


def _aggregate(path, records):
    spans = [r for r in records if r.get("type") != "score"]
    scores = [r for r in records if r.get("type") == "score"]
    llm = [r for r in spans if r.get("step") == "llm"]
    sess = {
        "trace_file": str(Path(path).as_posix()),
        "trace_id": (records[0].get("trace_id") if records else None),
        "session_id": (records[0].get("session_id") if records else None),
        "spans": len(spans),
        "llm_calls": len(llm),
        "token_input": sum(r.get("token_input") or 0 for r in llm),
        "token_output": sum(r.get("token_output") or 0 for r in llm),
        "cost_usd": round(sum(r.get("cost_usd") or 0.0 for r in llm), 6),
        "status_fail_spans": sum(1 for r in spans if r.get("status") == "fail"),
        "scores": [
            {"name": s.get("name"), "value": s.get("value"),
             "data_type": s.get("data_type"), "comment": s.get("comment"),
             "observation_id": s.get("observation_id")}
            for s in scores],
    }
    return sess, scores


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(
        description="trace JSONL → 评测集导出器（AB-01）")
    parser.add_argument("--trace", nargs="+", required=True,
                        help="trace JSONL 路径（一个或多个会话）")
    parser.add_argument("--out", required=True, help="评测集 JSON 输出路径")
    parser.add_argument("--require-score", action="store_true",
                        help="任一会话无 score 记录即 rc=1（回归集质检）")
    argv = parser.parse_args()

    sessions, errors = [], []
    for raw in argv.trace:
        p = Path(raw)
        if not p.is_file():
            errors.append("trace 文件不存在: %s" % p)
            continue
        try:
            records, bad = _read_records(p)
        except OSError as exc:
            errors.append("trace 不可读: %s (%s)" % (p, exc))
            continue
        if not records:
            errors.append("trace 为空: %s" % p)
            continue
        sess, scores = _aggregate(p, records)
        if argv.require_score and not scores:
            errors.append("会话无 score 记录: %s" % p)
        sessions.append(sess)

    if errors and len(sessions) == 0:
        sys.stderr.write("[trace-export] %s\n" % "；".join(errors))
        _emit({"ok": False, "error": errors})
        return 2

    all_scores = [dict(s, session_id=sess["session_id"])
                  for sess in sessions for s in sess["scores"]]
    eval_set = {
        "schema": "trace-eval-set/1",
        "sessions": sessions,
        "scores": all_scores,
        "summary": {
            "sessions": len(sessions),
            "scored_sessions": sum(1 for s in sessions if s["scores"]),
            "score_records": len(all_scores),
            "errors": errors,
        },
    }
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(eval_set, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    _emit({"ok": True, "sessions": len(sessions),
           "score_records": len(all_scores),
           "errors": errors, "out": str(out)})
    return 1 if (argv.require_score and errors) else 0


def _emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
