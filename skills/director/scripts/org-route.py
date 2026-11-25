#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总监调度台：按组织架构分派任务、给出指挥链与 RACI 签字权（只读，不代执行）。

org.json 是唯一组织事实源（v2 科层制，对标大公司实践）：
- 三层管理：总监 → 各团队首席（lead）→ 成员技能（members）；
- RACI 矩阵：每类交付物 R=负责执行 / A=唯一签字人 / C=咨询 / I=知会；
- error_budget：SRE 式质量预算（超限整队进入整改冻结，由 org-scorecard 结算）；
- initiatives：成员主观能动性注册表（事件 → 主动动作，无需上级指示）。

本脚本负责"分派与升级"，不代替任何团队干活。

用法示例：
    py org-route.py --kind fix --payload 补丁包在 runs/r1/out
    py org-route.py --kind research --payload "跨文件污点分析怎么做"

退出码：0=分派成功；2=输入或组织架构错误。
"""
import argparse
import json
import sys
from pathlib import Path

KIND_TEAM = {
    "review": "review",
    "fix": "repair",
    "approve": "approval",
    "retro": "retro",
    "research": "research",
    "config-change": "director",
}

KIND_DELIVERABLE = {
    "review": "发现清单与报告",
    "fix": "补丁包",
    "approve": "批准书",
    "retro": "坑台账与轮报",
    "research": "案例入库",
    "config-change": "行为级优化（配置/代码）",
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_org(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    org = data.get("org")
    if not isinstance(org, list) or not org:
        raise ValueError("org.org 需为非空数组")
    roles = {}
    for role in org:
        if not isinstance(role, dict) or not role.get("role"):
            raise ValueError("org 条目缺 role")
        roles[role["role"]] = role
    if "director" not in roles:
        raise ValueError("组织架构缺 director（上级）")
    for role in roles.values():
        reports_to = role.get("reports_to")
        if reports_to is not None and reports_to not in roles:
            raise ValueError("reports_to 指向不存在的角色: %s" % reports_to)
    return data, roles


def _raci_for(data, kind):
    raci = data.get("raci", {})
    return raci.get(KIND_DELIVERABLE[kind], {})


def _escalation(data):
    esc = data.get("escalation", {})
    if isinstance(esc, dict):
        return esc.get("levels", []), esc.get("research_flow", "")
    return list(esc or []), ""  # v1 兼容


def main():
    parser = argparse.ArgumentParser(description="总监调度台（分派与 RACI）")
    parser.add_argument("--kind", required=True,
                        help="review|fix|approve|retro|research|config-change")
    parser.add_argument("--payload", default="", help="任务上下文/交接物路径")
    parser.add_argument("--org", default=str(Path(__file__).resolve().parents[1]
                                             / "org.json"),
                        help="组织架构 JSON")
    argv = parser.parse_args()
    org_path = Path(argv.org)
    if not org_path.is_file():
        _emit({"ok": False, "error": "组织架构文件不存在: %s" % org_path})
        return 2
    if argv.kind not in KIND_TEAM:
        _emit({"ok": False, "error": "未知任务类型: %s（支持 %s）"
                                      % (argv.kind, ",".join(sorted(KIND_TEAM)))})
        return 2
    try:
        data, roles = _load_org(org_path)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "组织架构非法: %s" % exc})
        return 2
    team_role = KIND_TEAM[argv.kind]
    team = roles.get(team_role)
    if team is None:
        _emit({"ok": False, "error": "组织架构缺团队角色: %s" % team_role})
        return 2
    skill_root = Path(__file__).resolve().parents[2]
    # 技能可位于角色自己的 scripts/，也可挂靠 director/scripts/（如资料员）
    search_dirs = [skill_root / team_role / "scripts",
                   skill_root / "director" / "scripts"]
    missing = [s for s in team.get("members", team.get("skills", []))
               if not any((d / s).is_file() or (skill_root / s).exists()
                          for d in search_dirs)]
    if missing and team_role != "director":
        _emit({"ok": False, "error": "团队技能失联: %s" % missing})
        return 2

    chain = [team_role]
    walker = team
    while walker.get("reports_to"):
        walker = roles[walker["reports_to"]]
        chain.append(walker["role"])
    levels, research_flow = _escalation(data)
    if argv.kind == "research":
        order = ["director", "research"]
    elif argv.kind == "config-change":
        order = ["director"]
    else:
        order = ["director", team_role, "approval"]
    assignment = {
        "ok": True,
        "kind": argv.kind,
        "assignee": {"role": team_role, "title": team.get("title", team_role),
                     "lead": team.get("lead", ""),
                     "error_budget": team.get("error_budget", {})},
        "chain_of_command": chain,
        "raci": _raci_for(data, argv.kind),
        "initiatives": team.get("initiatives", []),
        "expected_artifacts": team.get("handoff", ""),
        "payload": argv.payload,
        "escalation_levels": levels,
        "research_flow": research_flow,
        "supervision_order": order,
        "note": "总监只分派与验收，不代替团队执行；审核人独立，不得自审自批；"
                "成员按 initiatives 在职能内主动调用组织能力",
    }
    _emit(assignment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
