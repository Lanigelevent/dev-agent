#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AB-20 记忆三级管线：抽取→合并决策→检索（round-216，mem0 思想复用，不装库）。

用途
    对轮内事件/坑条目做记忆合并决策后写入 agent-memory.jsonl：
    - 抽取（extract）：事件 JSON → 候选事实（task/summary/failure_category/
      rule_codes/ts/namespace）。
    - 合并决策（merge）：与既有记忆做 TF-IDF cosine 对照——
      cosine ≥ 0.65 → UPDATE（刷新既有条目 ts/seen 计数）
      否则          → ADD（新知识）
      DELETE 不在本层（compact-memory 老化层已管，见 SKILL.md 分工）。
    - 决策臂：--decider llm 时生成自写决策提示（供宿主/LLM 消费），
      本机无 LLM key → arm_status=blocked_no_key，决策回退确定性臂
      （如实标注，不冒充 LLM 判过）。
    - 检索（retrieve）：委托 memory_retrieval.retrieve（TF-IDF Top-K）。

用法示例
    py skills/retro/scripts/memory-pipeline.py plan --store retro/agent-memory.jsonl \
        --events retro/events-round-N.json --namespace agent
    py skills/retro/scripts/memory-pipeline.py add --store retro/agent-memory.jsonl \
        --events retro/events-round-N.json --namespace agent
    py skills/retro/scripts/memory-pipeline.py retrieve --store retro/agent-memory.jsonl \
        --query "..." --top-k 3
    py skills/retro/scripts/memory-pipeline.py prompt --store retro/agent-memory.jsonl \
        --events retro/events-round-N.json   # 自写决策提示（宿主/LLM 消费面）

退出码：0=成功；1=有可处理问题（store/事件文件不可读）；2=输入错误。
"""
import argparse
import importlib.util
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UPDATE_THRESHOLD = 0.65


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_store(path):
    entries = []
    if not path.is_file():
        return entries
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _extract_facts(events, namespace):
    """事件 JSON → 候选事实（completion 类型过滤与台账入册口径一致）。"""
    facts = []
    for ev in events:
        etype = str(ev.get("type", "")).strip().lower()
        if etype in ("feature", "test", "doc", "confirmation"):
            continue
        title = str(ev.get("title") or "")
        desc = str(ev.get("description") or "")
        if not title and not desc:
            continue
        facts.append({
            "id": uuid.uuid4().hex[:12],
            "namespace": namespace,
            "task": title,
            "summary": desc[:500],
            "failure_category": etype or "uncategorized",
            "rule_codes": ev.get("rule_codes") or [],
            "ts": str(ev.get("ts") or ""),
            "seen": 1,
        })
    return facts


def _decide_arm_status(argv_decider):
    """决策臂状态：llm 臂需 key（CRA_LLM_KEY/OPENAI_API_KEY），缺省确定性臂。"""
    if argv_decider == "llm":
        import os
        if os.environ.get("CRA_LLM_KEY") or os.environ.get("OPENAI_API_KEY"):
            return "llm", "ready"
        return "llm", "blocked_no_key"
    return "deterministic", "ready"


def _merge_decide(facts, entries):
    """确定性合并决策：同 namespace 内 TF-IDF cosine 对照。

    需 memory_retrieval 的分词/TF-IDF/cosine（importlib 复用，单一事实源）。
    """
    if not facts:
        return []
    spec = importlib.util.spec_from_file_location(
        "memory_retrieval",
        ROOT / "skills/retro/scripts/memory_retrieval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    decisions = []
    ns_entries = {}
    for e in entries:
        ns_entries.setdefault(str(e.get("namespace") or "agent"),
                              []).append(e)
    for fact in facts:
        cand = ns_entries.get(fact["namespace"], [])
        best_score = 0.0
        best_entry = None
        fact_tokens = mod._tokenize(fact["task"] + " " + fact["summary"])
        for e in cand:
            e_tokens = mod._tokenize(
                str(e.get("task", "")) + " " + str(e.get("summary", "")))
            score = mod._cosine(mod._tf(fact_tokens),
                                mod._tf(e_tokens)) \
                if fact_tokens and e_tokens else 0.0
            if score > best_score:
                best_score = score
                best_entry = e
        if best_entry is not None and best_score >= UPDATE_THRESHOLD:
            decisions.append({
                "fact_id": fact["id"],
                "action": "UPDATE",
                "target_id": best_entry.get("id"),
                "cosine": round(best_score, 4),
                "reason": "cosine>=0.65 近重复，合并刷新既有条目",
            })
        else:
            decisions.append({
                "fact_id": fact["id"],
                "action": "ADD",
                "target_id": None,
                "cosine": round(best_score, 4),
                "reason": "无近重复（best=%.2f<0.65），新知识入库"
                          % best_score,
            })
    return decisions


def _merge_apply(entries, facts, decisions):
    """按决策落写：ADD 追加，UPDATE 刷新 target 条目（ts/seen/摘要取新）。"""
    fact_by_id = {f["id"]: f for f in facts}
    for d in decisions:
        fact = fact_by_id.get(d["fact_id"])
        if fact is None:
            continue
        if d["action"] == "UPDATE" and d.get("target_id"):
            for e in entries:
                if e.get("id") == d["target_id"]:
                    e["seen"] = int(e.get("seen") or 1) + 1
                    e["ts"] = fact.get("ts") or e.get("ts")
                    e["summary"] = fact["summary"] or e.get("summary")
                    break
        elif d["action"] == "ADD":
            entries.append(dict(fact))
    return entries


def _decision_prompt(facts, entries):
    """自写 LLM 决策提示（mem0 add() 决策面同型；供宿主协议消费）。"""
    lines = [
        "你是记忆合并决策器。对每条新事实判定动作：",
        "- UPDATE：与某条既有记忆讲同一件事（近重复，给出 target_id）",
        "- ADD：新知识",
        "- DELETE：新事实否定既有记忆（矛盾更正，给出 target_id）",
        "只输出 JSON 数组：[{\"fact_id\":..., \"action\":..., \"target_id\":..., \"reason\":...}]",
        "",
        "既有记忆：",
    ]
    for e in entries[:20]:
        lines.append("- [%s/%s] %s | %s" % (
            e.get("namespace"), e.get("id"),
            str(e.get("task"))[:80], str(e.get("summary"))[:160]))
    lines.append("")
    lines.append("新事实：")
    for f in facts:
        lines.append("- [%s] %s | %s" % (
            f["id"], f["task"][:80], f["summary"][:200]))
    return "\n".join(lines)


def _store_write(path, entries):
    """原子写 store（uuid4 tmp + replace，对齐 _status_write 惯例）。"""
    import os
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".%s.tmp" % uuid.uuid4().hex[:8])
    tmp.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8")
    os.replace(tmp, path)


def _load_events(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("events") or []
    if not isinstance(data, list):
        raise ValueError("events 必须是 JSON 数组或含 events 键的对象")
    return data


def main():
    parser = argparse.ArgumentParser(description="AB-20 记忆三级管线")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, extra in (("plan", False), ("add", True)):
        sp = sub.add_parser(name)
        sp.add_argument("--store", required=True)
        sp.add_argument("--events", required=True)
        sp.add_argument("--namespace", default="agent")
        sp.add_argument("--decider", choices=("deterministic", "llm"),
                        default="deterministic")
    rp = sub.add_parser("retrieve")
    rp.add_argument("--store", required=True)
    rp.add_argument("--query", required=True)
    rp.add_argument("--top-k", type=int, default=3)
    rp.add_argument("--min-score", type=float, default=0.25)
    pp = sub.add_parser("prompt")
    pp.add_argument("--store", required=True)
    pp.add_argument("--events", required=True)
    pp.add_argument("--namespace", default="agent")
    argv = parser.parse_args()
    store = Path(argv.store)
    if argv.cmd in ("plan", "add"):
        try:
            events = _load_events(Path(argv.events))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _emit({"ok": False, "error": "events 不可读: %s" % exc})
            return 1
        entries = _load_store(store)
        facts = _extract_facts(events, argv.namespace)
        arm, status = _decide_arm_status(argv.decider)
        decisions = _merge_decide(facts, entries)
        result = {
            "ok": True,
            "cmd": argv.cmd,
            "arm": arm,
            "arm_status": status,
            "facts": len(facts),
            "decisions": decisions,
            "store": str(store),
        }
        if argv.cmd == "add" and status != "blocked_no_key":
            _merge_apply(entries, facts, decisions)
            _store_write(store, entries)
            result["written"] = True
            result["store_entries"] = len(entries)
        elif argv.cmd == "add":
            result["written"] = False
            result["note"] = "llm 臂 blocked，未写 store（不冒充决策已判）"
        _emit(result)
        return 0
    if argv.cmd == "prompt":
        try:
            events = _load_events(Path(argv.events))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _emit({"ok": False, "error": "events 不可读: %s" % exc})
            return 1
        facts = _extract_facts(events, argv.namespace)
        prompt_text = _decision_prompt(facts, _load_store(store))
        _emit({"ok": True, "cmd": "prompt", "facts": len(facts),
               "prompt": prompt_text,
               "note": "自写决策提示（宿主/LLM 消费面；结果经 "
                       "add --decider llm 臂回灌）"})
        return 0
    if argv.cmd == "retrieve":
        spec = importlib.util.spec_from_file_location(
            "memory_retrieval",
            ROOT / "skills/retro/scripts/memory_retrieval.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.retrieve(store, argv.query, top_k=argv.top_k,
                              min_score=argv.min_score)
        _emit(result)
        return 0
    _emit({"ok": False, "error": "未知子命令: %s" % argv.cmd})
    return 2


if __name__ == "__main__":
    sys.exit(main())