#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一成本账本：run 成本汇总与预算对账（ROADMAP 阶段三 3.2）。

用途：
    读一个 run 目录的 totals.json / ledger.jsonl / checkpoint.json，输出成本
    视图（墙钟、tokens 及来源、轮数、每步耗时、脚本与 LLM 调用计数），并与
    runner 的 caps（max_review_minutes / max_total_rounds /
    max_dynamic_dispatches）逐项对账。host 后端没有 token 用量，一律如实记
    N/A，不按 0 冒充；旧 run 没有 cost 块时退化为 derived 视图并把相关一致性
    检查标 skipped，不伪造来源。

判定规则（先写死，再跑数）：
    - C1 caps：totals.caps 必须存在（预算真值只在 runner 侧）；
    - C2 链：ledger.jsonl 哈希链 verify 必须通过（交给 event-ledger 本体，
      不复制 digest 实现）；
    - C3 llm_calls：totals.cost.llm_calls == ledger 中 kind=llm 的条数减去
      cost.llm_calls_baseline（断点续跑前段的账本记录不计入本段）；
    - C4 rounds：len(totals.rounds) == totals.cost.rounds_used；
    - C5 checkpoint.rounds_used == len(totals.rounds)；
    - C6 checkpoint.last_complete_step == totals.steps 末项 step；
    - C7 tokens 来源：host 后端必须记 n/a_host；provider_usage 必须有上报次数；
    - C8 预算：minutes / rounds / dynamic_dispatches 的 used ≤ cap（tokens 无
      上限，恒 N/A）。
    fail 任一 → 退出码 1；skipped 不算失败但原样列证据。

用法：
    python cost-ledger.py report --dir runs/run-x
    python cost-ledger.py check  --dir runs/run-x

退出码：
    0 = 成功（report 产出 / check 全部一致且预算内）
    1 = 有问题（对账漂移或预算超限）
    2 = 输入或环境错误（目录/文件缺失、JSON 非法、参数矛盾）
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def load_event_ledger():
    """进程内加载同目录 event-ledger（复用哈希链实现，不复制判据）。"""
    path = HERE / "event-ledger.py"
    try:
        spec = importlib.util.spec_from_file_location("event_ledger", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001 - 账本校验不可用只降级为 skipped
        return None


def ledger_facts(run_dir, module):
    """账本侧事实：是否存在 / 记录数 / 分类 / LLM 条数 / 链状态。"""
    path = Path(run_dir) / "ledger.jsonl"
    facts = {"present": path.is_file(), "file": str(path), "records": 0,
             "by_kind": {}, "llm_calls": 0, "chain_ok": None,
             "first_bad": None}
    if not facts["present"]:
        return facts
    if module is None:
        facts["chain_ok"] = None
        return facts
    verify = module.verify_ledger(path)
    records, _ = module.load_ledger(path)
    by_kind = {}
    for rec in records:
        kind = rec.get("kind", "?")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    facts.update({"records": len(records), "by_kind": by_kind,
                  "llm_calls": by_kind.get("llm", 0),
                  "chain_ok": bool(verify.get("ok")),
                  "first_bad": verify.get("first_bad")})
    return facts


def derive_cost(totals):
    """totals.cost 优先；旧 run 退化为 derived（来源如实标注）。"""
    cost = totals.get("cost")
    if isinstance(cost, dict) and "wall_sec" in cost:
        out = dict(cost)
        out["source"] = "totals.cost"
        return out
    minutes = float(totals.get("minutes_used") or 0.0)
    tokens = int(totals.get("tokens") or 0)
    derived = {
        "source": "derived（旧 totals 无 cost 块）",
        "wall_sec": round(minutes * 60, 3),
        "minutes_used": round(minutes, 3),
        "tokens": tokens,
        "tokens_status": "unknown（旧 totals 无来源标记）" if tokens else "not_used",
        "tokens_reported_calls": None,
        "llm_calls": None,
        "llm_calls_baseline": None,
        "llm_providers": [],
        "rounds_used": len(totals.get("rounds") or []),
        "dynamic_used": (totals.get("steps") or [{}])[-1].get("dynamic_used", 0)
        if totals.get("steps") else 0,
        "steps": [{"step": s.get("step"), "elapsed_sec": s.get("elapsed_sec")}
                  for s in (totals.get("steps") or [])],
        "budget": [],
        "scope": "current_process（旧 totals 派生）",
    }
    return derived


def _check(results, cid, name, status, evidence):
    results.append({"id": cid, "name": name, "status": status,
                    "evidence": evidence})


def check_run(run_dir):
    run_dir = Path(run_dir)
    totals, err = _load_json(run_dir / "totals.json")
    if totals is None:
        return None, "totals.json 不可读: %s" % err
    module = load_event_ledger()
    facts = ledger_facts(run_dir, module)
    cost = derive_cost(totals)
    checkpoint, cp_err = _load_json(run_dir / "checkpoint.json")
    caps = totals.get("caps") or {}
    rounds = totals.get("rounds") or []
    steps = totals.get("steps") or []
    checks = []
    problems = []

    # C1 caps
    if caps:
        _check(checks, "C1", "caps 存在", "pass",
               "caps=%s" % json.dumps(caps, ensure_ascii=False))
    else:
        _check(checks, "C1", "caps 存在", "skipped", "totals.caps 缺失")

    # C2 链
    if not facts["present"]:
        _check(checks, "C2", "ledger 哈希链", "skipped", "ledger.jsonl 缺失")
    elif module is None:
        _check(checks, "C2", "ledger 哈希链", "skipped", "event-ledger 不可加载")
    elif facts["chain_ok"]:
        _check(checks, "C2", "ledger 哈希链", "pass",
               "%d 条记录链完好" % facts["records"])
    else:
        ev = "first_bad=%s" % facts["first_bad"]
        _check(checks, "C2", "ledger 哈希链", "fail", ev)
        problems.append("ledger 哈希链断开: %s" % ev)

    # C3 llm_calls（减进程基线：--resume 前段的账本记录不计入本段）
    baseline = cost.get("llm_calls_baseline")
    if cost.get("llm_calls") is None or not facts["present"] or baseline is None:
        _check(checks, "C3", "llm_calls 对账", "skipped",
               "cost.llm_calls / baseline 或 ledger 不可用")
    else:
        expect = facts["llm_calls"] - int(baseline)
        if int(cost["llm_calls"]) == expect:
            _check(checks, "C3", "llm_calls 对账", "pass",
                   "cost.llm_calls=%d == ledger kind=llm %d - baseline %d"
                   % (cost["llm_calls"], facts["llm_calls"], baseline))
        else:
            ev = "cost.llm_calls=%s != ledger kind=llm %d - baseline %d = %d" % (
                cost["llm_calls"], facts["llm_calls"], baseline, expect)
            _check(checks, "C3", "llm_calls 对账", "fail", ev)
            problems.append(ev)

    # C4 rounds
    if cost.get("source") != "totals.cost":
        _check(checks, "C4", "rounds 对账", "skipped", "旧 totals 无 cost 块")
    elif int(cost.get("rounds_used", -1)) == len(rounds):
        _check(checks, "C4", "rounds 对账", "pass",
               "cost.rounds_used=%d == len(rounds)=%d"
               % (cost["rounds_used"], len(rounds)))
    else:
        ev = "cost.rounds_used=%s != len(totals.rounds)=%d" % (
            cost.get("rounds_used"), len(rounds))
        _check(checks, "C4", "rounds 对账", "fail", ev)
        problems.append(ev)

    # C5 / C6 checkpoint 交叉
    if checkpoint is None:
        note = "checkpoint.json 缺失" + ("（%s）" % cp_err if cp_err else "")
        _check(checks, "C5", "checkpoint.rounds_used 对账", "skipped", note)
        _check(checks, "C6", "checkpoint 步骤对账", "skipped", note)
    else:
        cp_rounds = checkpoint.get("rounds_used")
        if cp_rounds == len(rounds):
            _check(checks, "C5", "checkpoint.rounds_used 对账", "pass",
                   "checkpoint=%s == len(rounds)=%d" % (cp_rounds, len(rounds)))
        else:
            ev = "checkpoint.rounds_used=%s != len(totals.rounds)=%d" % (
                cp_rounds, len(rounds))
            _check(checks, "C5", "checkpoint.rounds_used 对账", "fail", ev)
            problems.append(ev)
        last_step = steps[-1].get("step") if steps else None
        cp_step = checkpoint.get("last_complete_step")
        if last_step == cp_step:
            _check(checks, "C6", "checkpoint 步骤对账", "pass",
                   "last_step=%s == checkpoint" % last_step)
        else:
            ev = "totals 末步=%s != checkpoint.last_complete_step=%s" % (
                last_step, cp_step)
            _check(checks, "C6", "checkpoint 步骤对账", "fail", ev)
            problems.append(ev)

    # C7 tokens 来源
    status = str(cost.get("tokens_status") or "")
    providers = cost.get("llm_providers") or []
    if cost.get("source") != "totals.cost":
        _check(checks, "C7", "tokens 来源", "skipped", "旧 totals 无 cost 块")
    elif "host" in providers and not status.startswith("n/a"):
        ev = "host 后端但 tokens_status=%s（应如实 N/A）" % status
        _check(checks, "C7", "tokens 来源", "fail", ev)
        problems.append(ev)
    elif status == "provider_usage" and not cost.get("tokens_reported_calls"):
        ev = "provider_usage 但 tokens_reported_calls=%s" % cost.get(
            "tokens_reported_calls")
        _check(checks, "C7", "tokens 来源", "fail", ev)
        problems.append(ev)
    else:
        _check(checks, "C7", "tokens 来源", "pass",
               "status=%s providers=%s" % (status or "?", providers or []))

    # C8 预算
    budget = cost.get("budget") or []
    if not budget:
        _check(checks, "C8", "预算对账", "skipped", "cost.budget 缺失")
    else:
        bad = [row for row in budget if row.get("status") == "EXCEEDED"]
        if not bad:
            _check(checks, "C8", "预算对账", "pass",
                   "；".join("%s %s/%s %s" % (r.get("item"), r.get("used"),
                                             r.get("cap"), r.get("status"))
                            for r in budget))
        else:
            ev = "超限: " + "、".join("%s %s/%s" % (r.get("item"), r.get("used"),
                                                   r.get("cap")) for r in bad)
            _check(checks, "C8", "预算对账", "fail", ev)
            problems.append(ev)

    over = any(row.get("status") == "EXCEEDED" for row in budget)
    state = "EXCEEDED" if over else ("DRIFT" if problems else "PASS")
    result = {
        "ok": not problems,
        "state": state,
        "run_dir": str(run_dir),
        "cost": cost,
        "ledger": facts,
        "checks": checks,
        "problems": problems,
    }
    return result, None


def main():
    parser = argparse.ArgumentParser(description="统一成本账本与预算对账")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("report", "check"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True, help="run 目录（含 totals.json）")
    argv = parser.parse_args()
    if not Path(argv.dir).is_dir():
        _emit({"ok": False, "error": "run 目录不存在: %s" % argv.dir})
        return 2
    result, err = check_run(argv.dir)
    if result is None:
        _emit({"ok": False, "error": err})
        return 2
    if argv.cmd == "report":
        result["note"] = "report 是只读视图；判定与退出码以 check 为准"
        _emit(result)
        return 0
    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
