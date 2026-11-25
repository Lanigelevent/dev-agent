#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务流水线：模糊意图 → 拆解 → 派发 → 汇总（总监链路的机械骨干）。

三模式：
- --from-intent：吃 intent-parse.py 的输出 JSON（或 --request 原话，内部子进程
  调 intent-parse.py），拆成边界清晰、可独立执行、可验证的子任务。每个子任务
  带 kind（org-route 词表）、depends_on、produces（产出物）、dod（完成标准）。
  intent 里的 compound_clauses（复合子句，如「顺便把测试也补全」）在深度档
  模板之后追加为独立子任务，依赖最后一个 review 任务——搭车工作要先看到
  评审结果才知道改什么。意图阻塞（intent_level=C，questions 非空）时拒绝
  拆解，原样带回那个单问——意图不明不猜着拆。假设与待确认项原样带进
  plan，汇总时不得丢失。
- --dispatch：吃 --from-intent 落盘的 plan JSON，做重叠/遗漏闸（id 唯一、
  依赖可满足无环、kind 合法），再按拓扑序逐任务子进程调 org-route.py 拿
  指挥链与 RACI，附着回各任务。
- --collect：吃 plan + --results（各子任务回报 JSON）。回报合法形状只有
  两种：按键 dict（{"T1": {...}}）或 {"tasks": 按键 dict}；其余形状（列表等）
  exit 2 报错，不许静默当「全部未回报」零命中（round-35 消化坑
  791468dc0ca2）。--out 是汇总落盘的**文件**路径，传目录 exit 2。回报里
  出现对不上任何任务 id 的键时进 unmatched_results 显式列出。汇总成对用户
  的统一回复：overall / key_changes / remaining_risks / open_tasks。未回报、
  失败、阻塞的任务一律进遗留，不许在汇总里静默消失。

拆解规则（确定性，按深度档）：
- quick：1 任务（快速评审）
- standard：预检 → 评审 → 复盘
- deep：预检 → 评审 → 修复建议整理 → 复盘
依赖方向即拓扑序；kind 映射复用 org-route 的 KIND_TEAM 词表。

用法示例：
    py task-pipeline.py --from-intent --request "review PR #12" --out retro
    py task-pipeline.py --from-intent --intent-file intent.json --out retro
    py task-pipeline.py --dispatch --plan retro/plan-<id>.json
    py task-pipeline.py --collect --plan retro/plan-<id>.json --results results.json

退出码：0=成功；3=意图阻塞（带回单问，不拆解）；2=输入错误。
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
INTENT_PARSE = SCRIPT_DIR.parent.parent / "prompt-enhancement" / "scripts" / "intent-parse.py"
ORG_ROUTE = SCRIPT_DIR / "org-route.py"

VALID_KINDS = {"review", "fix", "approve", "retro", "research", "config-change"}

KIND_DOD = {
    "review": [
        "发现清单落盘且 findings 可解析",
        "每条发现带可定位证据（文件/标识符）",
        "recall 与 precision 两个口径同时上报，只报一个视为不合格",
    ],
    "fix": [
        "补丁包落盘且只经五道门闸 fix-apply.py 写入（sha256 绑定）",
        "修复分支不自动合并，留给独立审核人",
    ],
    "retro": [
        "事件与坑条目入台账，口径数字回写文档（新鲜度闸过）",
    ],
    "research": [
        "结论给出可落地三形态之一：配置扩展/测试补充/代码修改",
        "结论入案例库沉淀（case-archive）",
    ],
    "config-change": [
        "行为级改动过反向验证（变异锚点证明检查器有判别力）",
        "测试预算实测数字入册",
    ],
    "approve": [
        "批准书由独立审核人签发（不得自审自批）",
        "sha256 绑定与审批人令牌齐备",
    ],
}

# 深度档 → 子任务模板（kind, 标题, depends_on 索引相对本档序列）
DECOMPOSE = {
    "quick": [("review", "快速评审：只报高置信发现")],
    "standard": [
        ("review", "预检与材料构造（diff/范围/夹具）"),
        ("review", "正式评审"),
        ("retro", "复盘：事件与坑入台账"),
    ],
    "deep": [
        ("review", "预检与材料构造（diff/范围/夹具）"),
        ("review", "深入评审"),
        ("fix", "修复建议整理为补丁包（不落被审仓库）"),
        ("retro", "复盘：事件与坑入台账"),
    ],
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _run_intent_parse(request, repo):
    """子进程调 intent-parse.py，返回 (rc, data)。"""
    cmd = [sys.executable, str(INTENT_PARSE), "--request", request]
    if repo:
        cmd += ["--repo", repo]
    p = subprocess.run(cmd, capture_output=True, timeout=60)
    out = p.stdout.decode("utf-8", errors="replace")
    try:
        return p.returncode, json.loads(out)
    except ValueError:
        return p.returncode, {"ok": False, "error": "intent-parse 输出非 JSON: %r" % out[:200]}


def _decompose(intent):
    """意图 JSON → 子任务列表。深度档缺省按 standard（进假设，不进猜测执行）。

    compound_clauses（intent-parse 检出的复合子句，round-35 消化坑
    791468dc0ca2 ②）在模板任务之后追加：kind 由 intent-parse 词表给出，
    depends_on 指向最后一个 review 任务——补测试/改文档要先看到评审结果。
    """
    depth = intent.get("depth") or "standard"
    templates = DECOMPOSE.get(depth, DECOMPOSE["standard"])
    tasks = []
    for i, (kind, title) in enumerate(templates):
        tasks.append({
            "id": "T%d" % (i + 1),
            "kind": kind,
            "title": title,
            "depends_on": ["T%d" % i] if i else [],
            "produces": KIND_DELIVERABLE(kind),
            "dod": list(KIND_DOD[kind]),
        })
    last_review = next((t["id"] for t in reversed(tasks)
                        if t["kind"] == "review"), tasks[-1]["id"])
    for clause in intent.get("compound_clauses") or []:
        kind = clause.get("kind")
        if kind not in VALID_KINDS:
            continue
        tasks.append({
            "id": "T%d" % (len(tasks) + 1),
            "kind": kind,
            "title": "%s（复合子句：%s）"
                     % (clause.get("suggested_task", "附加工作"),
                        clause.get("clause", "")),
            "depends_on": [last_review],
            "produces": KIND_DELIVERABLE(kind),
            "dod": list(KIND_DOD[kind]),
            "origin": "compound_clause",
        })
    return tasks


def KIND_DELIVERABLE(kind):
    return {
        "review": "发现清单与报告",
        "fix": "补丁包",
        "approve": "批准书",
        "retro": "坑台账与轮报",
        "research": "案例入库",
        "config-change": "行为级优化（配置/代码）",
    }[kind]


def _topo_ok(tasks):
    """返回 (是否通过, 问题列表)。检查 id 唯一、依赖存在、无环、kind 合法。"""
    problems = []
    ids = [t["id"] for t in tasks]
    if len(ids) != len(set(ids)):
        problems.append("任务 id 重复（重叠风险）")
    idset = set(ids)
    for t in tasks:
        if t["kind"] not in VALID_KINDS:
            problems.append("%s kind 非法: %s" % (t["id"], t["kind"]))
        for dep in t.get("depends_on", []):
            if dep not in idset:
                problems.append("%s 依赖不存在的任务: %s" % (t["id"], dep))
            elif dep == t["id"]:
                problems.append("%s 依赖自身" % t["id"])
    # Kahn 判环
    indeg = {t["id"]: 0 for t in tasks}
    for t in tasks:
        for dep in t.get("depends_on", []):
            if dep in indeg:
                indeg[t["id"]] += 1
    queue = [i for i, d in indeg.items() if d == 0]
    seen = 0
    dependents = {}
    for t in tasks:
        for dep in t.get("depends_on", []):
            dependents.setdefault(dep, []).append(t["id"])
    while queue:
        node = queue.pop()
        seen += 1
        for nxt in dependents.get(node, []):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen != len(ids):
        problems.append("依赖成环，拓扑序不存在")
    return not problems, problems


def mode_from_intent(argv):
    if argv.intent_file:
        try:
            intent = json.loads(Path(argv.intent_file).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "intent 文件不可读: %s" % exc})
            return 2
    elif argv.request:
        rc, intent = _run_intent_parse(argv.request, argv.repo)
        if rc not in (0, 3):
            _emit({"ok": False, "error": "intent-parse 异常 rc=%d: %s"
                    % (rc, json.dumps(intent, ensure_ascii=False)[:200])})
            return 2
    else:
        _emit({"ok": False, "error": "需要 --intent-file 或 --request"})
        return 2

    if intent.get("intent_level") == "C" and intent.get("questions"):
        _emit({"ok": False, "blocked": True,
               "question": intent["questions"][0],
               "note": "意图阻塞，不拆解；请先回答这个单问再重跑"})
        return 3

    tasks = _decompose(intent)
    plan_id = hashlib.sha256(json.dumps(intent, ensure_ascii=False, sort_keys=True)
                             .encode("utf-8")).hexdigest()[:12]
    plan = {
        "id": plan_id,
        "goal": intent.get("scope", "未指明范围"),
        "object": intent.get("object"),
        "object_ref": intent.get("object_ref"),
        "depth": intent.get("depth") or "standard（默认，见 assumptions）",
        "assumptions": intent.get("assumptions", []),
        "confirmations": intent.get("confirmations", []),
        "tasks": tasks,
    }
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / ("plan-%s.json" % plan_id)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    _emit({"ok": True, "plan_id": plan_id, "plan": str(plan_path),
           "tasks": tasks,
           "note": "假设与待确认项已随 plan 落盘；--dispatch 前先向用户过一遍 confirmations"})
    return 0


def mode_dispatch(argv):
    plan_path = Path(argv.plan)
    if not plan_path.is_file():
        _emit({"ok": False, "error": "plan 不存在: %s" % plan_path})
        return 2
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "plan 不可读: %s" % exc})
        return 2
    tasks = plan.get("tasks", [])
    ok, problems = _topo_ok(tasks)
    if not ok:
        _emit({"ok": False, "error": "拆解闸未过（重叠/遗漏/环）", "problems": problems})
        return 2
    # 拓扑序派发
    done = set()
    dispatched = []
    pending = list(tasks)
    while pending:
        progress = False
        for t in list(pending):
            if all(d in done for d in t.get("depends_on", [])):
                p = subprocess.run(
                    [sys.executable, str(ORG_ROUTE), "--kind", t["kind"],
                     "--payload", "%s|%s" % (t["title"], plan_path.name)],
                    capture_output=True, timeout=60)
                out = p.stdout.decode("utf-8", errors="replace")
                try:
                    assignment = json.loads(out)
                except ValueError:
                    _emit({"ok": False, "error": "org-route 输出非 JSON（任务 %s）: %r"
                            % (t["id"], out[:200])})
                    return 2
                if p.returncode != 0:
                    _emit({"ok": False, "error": "org-route 拒绝任务 %s: %s"
                            % (t["id"], assignment.get("error", ""))})
                    return 2
                t["assignment"] = {
                    "assignee": assignment.get("assignee"),
                    "chain_of_command": assignment.get("chain_of_command"),
                    "raci": assignment.get("raci"),
                    "input": {"goal": plan.get("goal"), "task": t["title"],
                              "produces": t["produces"]},
                    "output_format": "JSON 回报：status/summary/artifacts/risks",
                    "deadline": "plan 级截止；逾期回报 blocked 而不是静默拖延",
                    "report_via": "--collect 汇总时并入 --results",
                }
                dispatched.append(t["id"])
                done.add(t["id"])
                pending.remove(t)
                progress = True
        if not progress:
            break  # 环已在 _topo_ok 拦截，这里只作防御
    plan["tasks"] = tasks
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    _emit({"ok": True, "plan": str(plan_path), "dispatched": dispatched,
           "note": "派发只到指挥链；总监不代替执行。回报经 --collect 汇总"})
    return 0


def _normalize_results(raw, source):
    """回报 JSON 形状校验（round-35 消化坑 791468dc0ca2 ③）。

    合法形状只有两种：按键 dict（{"T1": {...}}）或 {"tasks": 按键 dict}。
    其余形状 exit 2 报错——列表形状静默零命中会让汇总显示 0/N 完成却
    不给原因，违背「不吞遗留」口径。
    """
    if isinstance(raw, dict):
        tasks = raw.get("tasks", raw)
        if isinstance(tasks, dict):
            return tasks, None
        return None, ("--results 形状错误：%s 的 tasks 键是 %s 而非按键 dict"
                      % (source, type(tasks).__name__))
    if isinstance(raw, list):
        hint = ""
        if raw and isinstance(raw[0], dict) and "id" in raw[0]:
            hint = "（列表元素自带 id 键：改成 {%s: 元素} 的按键形状即可）" \
                   % raw[0]["id"]
        return None, ("--results 形状错误：%s 顶层是列表（%d 项），期望按键 dict，"
                      "如 {\"T1\": {\"status\": ...}} 或 {\"tasks\": {...}}%s"
                      % (source, len(raw), hint))
    return None, ("--results 形状错误：%s 顶层是 %s，期望 JSON 对象（按键 dict）"
                  % (source, type(raw).__name__))


def mode_collect(argv):
    plan_path = Path(argv.plan)
    if not plan_path.is_file():
        _emit({"ok": False, "error": "plan 不存在: %s" % plan_path})
        return 2
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        raw_results = json.loads(Path(argv.results).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "输入不可读: %s" % exc})
        return 2
    results, shape_err = _normalize_results(raw_results, argv.results)
    if shape_err:
        _emit({"ok": False, "error": shape_err})
        return 2
    key_changes, remaining_risks, open_tasks = [], [], []
    matched_ids = set()
    all_done = True
    for t in plan.get("tasks", []):
        matched_ids.add(t["id"])
        r = results.get(t["id"])
        if not isinstance(r, dict):
            all_done = False
            open_tasks.append({"id": t["id"], "title": t["title"],
                               "status": "未回报"})
            remaining_risks.append({"id": t["id"],
                                    "risk": "任务未回报，状态未知（不当作完成）"})
            continue
        status = r.get("status", "unknown")
        if status == "done":
            key_changes.append({"id": t["id"], "summary": r.get("summary", ""),
                                "artifacts": r.get("artifacts", [])})
            for risk in r.get("risks", []):
                remaining_risks.append({"id": t["id"], "risk": risk})
        else:
            all_done = False
            open_tasks.append({"id": t["id"], "title": t["title"], "status": status,
                               "summary": r.get("summary", "")})
            remaining_risks.append({"id": t["id"],
                                    "risk": "任务未完成（%s）：%s"
                                            % (status, r.get("summary", "无说明"))})
    unmatched = sorted(set(results) - matched_ids)
    if unmatched:
        remaining_risks.append({
            "id": "-",
            "risk": "回报里 %d 个键对不上任何任务 id（不静默丢弃）：%s"
                    % (len(unmatched), "、".join(unmatched))})
    summary = {
        "ok": True,
        "overall": ("全部 %d 个子任务完成" % len(plan.get("tasks", []))
                    if all_done else
                    "完成 %d/%d，其余见 open_tasks" % (len(key_changes),
                                                      len(plan.get("tasks", [])))),
        "key_changes": key_changes,
        "remaining_risks": remaining_risks,
        "open_tasks": open_tasks,
        "unmatched_results": unmatched,
        "assumptions_still_open": plan.get("confirmations", []),
        "note": "待确认项原样带回：用户未逐条确认前，不当作已澄清",
    }
    out_path = Path(argv.out) if argv.out else None
    if out_path:
        if out_path.is_dir():
            _emit({"ok": False, "error": "--out 需要文件路径，得到目录: %s"
                    % out_path})
            return 2
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
        summary["collect_file"] = str(out_path)
    _emit(summary)
    return 0


def main():
    parser = argparse.ArgumentParser(description="任务流水线（拆解/派发/汇总）")
    parser.add_argument("--from-intent", action="store_true")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--request", default="", help="用户原话（--from-intent）")
    parser.add_argument("--repo", default="", help="仓库路径（透传 intent-parse）")
    parser.add_argument("--intent-file", default="", help="intent-parse 输出 JSON")
    parser.add_argument("--plan", default="", help="plan JSON 路径")
    parser.add_argument("--results", default="", help="各子任务回报 JSON（--collect）")
    parser.add_argument("--out", default="", help="产物目录（--from-intent）或汇总落盘路径（--collect）")
    argv = parser.parse_args()
    flags = (("from_intent", argv.from_intent), ("dispatch", argv.dispatch),
             ("collect", argv.collect))
    modes = [name for name, flag in flags if flag]
    if len(modes) != 1:
        _emit({"ok": False, "error": "恰好指定一个模式：--from-intent / --dispatch / --collect"})
        return 2
    if modes[0] == "from_intent":
        if not argv.out:
            _emit({"ok": False, "error": "--from-intent 需要 --out"})
            return 2
        return mode_from_intent(argv)
    if modes[0] == "dispatch":
        if not argv.plan:
            _emit({"ok": False, "error": "--dispatch 需要 --plan"})
            return 2
        return mode_dispatch(argv)
    if not argv.plan or not argv.results:
        _emit({"ok": False, "error": "--collect 需要 --plan 与 --results"})
        return 2
    return mode_collect(argv)


if __name__ == "__main__":
    sys.exit(main())
