#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP stdio 服务器：把代码评审能力暴露为 Model Context Protocol 工具。

传输形态：stdin/stdout 上的换行分隔 JSON-RPC 2.0（MCP stdio 规范）。
协议版本：2025-06-18；serverInfo.name = dev-agent；16 个工具均声明 annotations（readOnlyHint/destructiveHint/openWorldHint，2025-06-18 口径）。
只读保证：所有工具最终只调用评审脚本（对被审仓库只读），不写入仓库。

工具（16 个）：评审四工具 + 审核人一工具 + 修复两工具 + 迭代官一工具 + 总监一
工具 + 测试生成一工具 + 编码循环一工具；落盘必须持审核人批准书且显式
confirm（任何一方不得自审自批）。
- code_review_run     编排评审  -> runner.py            （--repo/--range 或 --resume）
- code_review_scan    硬规则快扫 -> deterministic-rules.py（--file 或 --diff-file 二选一）
- code_review_plan    维度规划  -> dispatch-plan.py       （--diff）
- code_review_feedback 反馈入库  -> feedback-close.py      （--findings/--experience）
- code_review_approve 审核人裁定 -> approve-plan.py / approve-patch.py
                       （mode=scope 范围裁定→工单；mode=patch 补丁准出→批准书）
- code_review_fix     修复出补丁 -> fix-patch.py（只吃工单，只写产物目录）
- code_review_apply   补丁落盘  -> fix-apply.py（--apply 需 confirm=true 且持
                       批准书；五道闸含行为回归，验证失败自动回滚；--undo 撤销）
- code_review_retro   迭代官复盘 -> retro-ledger.py / retro-report.py
                       （mode=collect 坑台账；mode=report 轮报+改进候选）
- code_review_director 总监调度 -> org-route.py / case-match.py /
                       org-scorecard.py / research-brief.py / case-archive.py
                       （mode=route 分派与 RACI；mode=match 案例复用匹配；
                        mode=brief 疑难杂症研究简报，检索由宿主联网执行；
                        mode=scorecard 错误预算结算；mode=archive 档案员
                        发布成败双轨案例档案仓，可选推送 Git 远端）
- code_review_testgen 测试生成 -> testgen.py
                       （mode=skeleton 确定性骨架 style=loop|hypothesis；
                        mode=llm 宿主协议真用例 WAIT→填→重跑；
                        mode=verify 生成物验收；mode=patch 新文件补丁）
- code_review_coding  编码循环  -> code-task.py（agent 层 .venv Python；
                       任务→repo_map→SEARCH/REPLACE→worktree 测试→补丁；
                       宿主协议；不直接写被审仓库，补丁走修复链）
- code_review_submit  异步提交评审作业 -> runs/jobs/<uuid4>（立即返回 job_id）
- code_review_status  轮询作业状态 -> {state, step, progress, findings_url}
- code_review_cancel  取消 queued/running 作业 -> 杀进程树 + cancelled + 账本摘要
- code_review_purge   清理终态作业目录 -> confirm + 单 id + 终态三重闸 + 中央账本摘要
                       （作业独立于 stdio 连接存活；重连凭 job_id 续查）
资源：review://jobs/{job_id}（只读作业产物 result.json / status.json）

isError 语义：除 code_review_apply 外，退出码 2 视为工具错误（approve 退出码
1 = REJECTED 裁定结论、run 退出码 1 = NEED_HUMAN，均不算错误，结论在结果里）；
code_review_apply 非 0 退出码均视为错误（含回滚态 ROLLED_BACK）。
超时：run 600 秒，异步作业 3600 秒（D-052 600s 语义放大版），apply 300 秒，其余 60 秒。

宿主接入：
- DeepSeek Harness：@deepseek-ai/dsh-mcp-client（stdio），工具名 mcp__<server>__<name>；
  详见 interop/deepseek-harness/README.md。
- ZCode：.zcode-plugin/plugin.json 的 mcpServers 已指向本文件。

子进程纪律：显式参数列表 + shell=False；命令不拼接字符串。
"""

import importlib.util
import json
import atexit
import contextlib
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "dev-agent", "version": "2.108.0"}
RUN_TIMEOUT = 600
FAST_TIMEOUT = 60
APPLY_TIMEOUT = 300

SCRIPT_RUNNER = ROOT / "skills" / "orchestrator" / "scripts" / "runner.py"
SCRIPT_RULES = ROOT / "skills" / "multi-agent-review" / "scripts" / "deterministic-rules.py"
SCRIPT_PLAN = ROOT / "skills" / "multi-agent-review" / "scripts" / "dispatch-plan.py"
SCRIPT_FEEDBACK = ROOT / "skills" / "production-guardrails" / "scripts" / "feedback-close.py"
SCRIPT_APPROVE_PLAN = ROOT / "skills" / "approval" / "scripts" / "approve-plan.py"
SCRIPT_APPROVE_PATCH = ROOT / "skills" / "approval" / "scripts" / "approve-patch.py"
SCRIPT_FIX_PATCH = ROOT / "skills" / "repair" / "scripts" / "fix-patch.py"
SCRIPT_FIX_APPLY = ROOT / "skills" / "repair" / "scripts" / "fix-apply.py"
SCRIPT_RETRO_LEDGER = ROOT / "skills" / "retro" / "scripts" / "retro-ledger.py"
SCRIPT_RETRO_REPORT = ROOT / "skills" / "retro" / "scripts" / "retro-report.py"
SCRIPT_ORG_ROUTE = ROOT / "skills" / "director" / "scripts" / "org-route.py"
SCRIPT_CASE_MATCH = ROOT / "skills" / "director" / "scripts" / "case-match.py"
SCRIPT_RESEARCH_BRIEF = ROOT / "skills" / "director" / "scripts" / "research-brief.py"
SCRIPT_ORG_SCORECARD = ROOT / "skills" / "director" / "scripts" / "org-scorecard.py"
SCRIPT_CASE_ARCHIVE = ROOT / "skills" / "director" / "scripts" / "case-archive.py"
SCRIPT_TESTGEN = ROOT / "engines" / "testgen.py"
SCRIPT_CODE_TASK = ROOT / "agent" / "code-task.py"
SCRIPT_LIBCST = ROOT / "engines" / "libcst_adapter.py"
SCRIPT_EVENT_LEDGER = (ROOT / "skills" / "production-guardrails" / "scripts"
                       / "event-ledger.py")
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
JOB_ROOT = ROOT / "runs" / "jobs"
JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
JOB_TIMEOUT = 3600
CONFIG_WHITELIST = {"max_review_minutes": 120, "max_total_rounds": 64,
                    "max_verification_rounds": 5}
_DETACHED_JOBS = []


def _wait_bounded(proc, timeout):
    """有界收割；超时返回 False（不杀进程、不阻塞退出）。"""
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def _reap_detached():
    """已终局的异步作业 Popen 句柄回收（detached 作业不 wait，只清引用）。"""
    for proc in list(_DETACHED_JOBS):
        if proc.poll() is not None:
            _wait_bounded(proc, 1)
            _DETACHED_JOBS.remove(proc)


_POLICY_CACHE = {}


def _shutdown_detached():
    """进程退出时给短作业一个有界收割窗口；超时不杀进程（作业仍独立存活）。"""
    for proc in list(_DETACHED_JOBS):
        _wait_bounded(proc, 2)
    _DETACHED_JOBS.clear()


atexit.register(_shutdown_detached)


def _obj_schema(description, properties, required):
    return {"type": "object", "description": description,
            "properties": properties, "required": required}


def _str_prop(description):
    return {"type": "string", "description": description}


TOOLS = [
    {
        "name": "code_review_run",
        "description": (
            "对 Git 仓库的变更范围 A..B 执行 0-10 步编排评审（只读）。"
            "返回编排器 JSON：state/totals/checkpoint 等。"
            "预算（分钟/轮数）经 config_path 指向的 agent.json 配置；"
            "退出码 1 表示 NEED_HUMAN（需人工介入），不是工具故障。"
        ),
        "inputSchema": _obj_schema(
            "编排评审入参",
            {
                "repo": _str_prop("被审仓库路径"),
                "range": _str_prop("变更范围 A..B，如 HEAD~1..HEAD"),
                "request": _str_prop("用户原话（>=10 字符启用意图一致性）"),
                "config_path": _str_prop("agent.json 路径（预算等配置）"),
                "reviewer": {"type": "string", "enum": ["deterministic", "llm"],
                             "description": "评审器类型，默认 deterministic"},
                "resume": _str_prop("续跑的 run 目录（给出后忽略 repo/range）"),
                "report_style": _str_prop(
                    "报告风格变体：preset 名（executive/engineering/audit）或风格 spec JSON 路径；缺省不生成"),
                "skip_probe": {"type": "boolean", "description": "跳过会话探针"},
                "out": _str_prop("run 产物根目录（缺省为项目下 runs/）"),
            },
            [],
        ),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_scan",
        "description": (
            "38 条确定性硬规则快扫（只读）。path 与 diff_path 必须且只能给一个："
            "path 扫单个源文件；diff_path 扫 unified diff 中新增行。"
            "两参数同给或缺省 → 立即 rc=2 用法错误（防呆：无歧义执行）。"
            "命中凭据形态时 snippet 已脱敏为占位文本。"
        ),
        "inputSchema": _obj_schema(
            "硬规则快扫入参",
            {
                "path": _str_prop("单个源文件路径"),
                "diff_path": _str_prop("unified diff 文件路径"),
            },
            [],
        ),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_plan",
        "description": (
            "按 diff 机械划分 7 个评审维度（enabled/skipped），"
            "可带意图说明与误报模式库（输出各维度举证等级）。只读。"
        ),
        "inputSchema": _obj_schema(
            "维度规划入参",
            {
                "diff_path": _str_prop("unified diff 文件路径"),
                "intent": _str_prop("意图说明（>=10 字符启用意图一致性）"),
                "experience": _str_prop("误报模式库 JSON 路径或其目录"),
            },
            ["diff_path"],
        ),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_feedback",
        "description": (
            "把人工驳回清单写入误报模式库并聚合（写智能体自身经验库，不写被审仓库）。"
            "findings_path 指向数组或含 items 键的 JSON，条目含 pattern|rule_id 与 dimension。"
        ),
        "inputSchema": _obj_schema(
            "反馈入库入参",
            {
                "findings_path": _str_prop("驳回清单 JSON 文件"),
                "experience_path": _str_prop("经验库 JSON 路径或其目录"),
            },
            ["findings_path", "experience_path"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_approve",
        "description": (
            "审核人裁定（独立第三方，两道闸）。mode=scope：范围裁定，"
            "评审发现清单 -> 修复工单 work-order.json（白名单分类 + 严重度政策，"
            "拒绝项带原因）；mode=patch：补丁准出，工单+补丁包 -> 批准书 "
            "approval.json（五项独立核验：工单绑定/基线一致/可应用/新增行零命中/"
            "路径安全；REJECTED 时 reasons 列明，退出码 1 不算工具错误）。"
        ),
        "inputSchema": _obj_schema(
            "审核人裁定入参",
            {
                "mode": {"type": "string", "enum": ["scope", "patch"],
                         "description": "scope=范围裁定（闸 1）；patch=补丁准出（闸 2）"},
                "repo": _str_prop("被审仓库路径"),
                "findings_path": _str_prop("mode=scope：评审发现清单 JSON"),
                "order_path": _str_prop("mode=patch：工单 JSON；mode=scope 忽略"),
                "manifest_path": _str_prop("mode=patch：fix-manifest.json"),
                "out_dir": _str_prop("裁定产物目录（工单/批准书落这里）"),
                "severities": _str_prop("mode=scope：放行的严重度，逗号分隔，缺省全放行"),
            },
            ["mode", "repo", "out_dir"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_fix",
        "description": (
            "修复团队出补丁（只读被审仓库，只写 out_dir 产物目录）。"
            "只吃审核人闸 1 签发的工单（order_path），生成 unified diff 补丁与 "
            "fix-manifest.json；落盘需闸 2 批准书 + code_review_apply。"
        ),
        "inputSchema": _obj_schema(
            "修复出补丁入参",
            {
                "order_path": _str_prop("审核人工单 work-order.json"),
                "repo": _str_prop("被审仓库路径"),
                "out_dir": _str_prop("补丁产物目录"),
            },
            ["order_path", "repo", "out_dir"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": True,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_retro",
        "description": (
            "迭代官复盘（第四角色，每轮末尾运行）。mode=collect：收集本轮踩坑"
            "（手工事件 + 产物痕迹：REJECTED/ROLLED_BACK/skipped/误报）并入坑"
            "台账，按 id 去重、权重排序；结案（close_id）必须同时给 close_note"
            "（可验证验收口径），否则脚本拒绝结案；mode=report：生成轮报 round-<N>-report.md、"
            "机器候选清单 round-<N>-candidates.md 与改进候选 JSON（stdout）；"
            "人工维护的开局检查单 next-round.md 不由脚本写。"
        ),
        "inputSchema": _obj_schema(
            "迭代官复盘入参",
            {
                "mode": {"type": "string", "enum": ["collect", "report"],
                         "description": "collect=坑台账；report=轮报与候选"},
                "out_dir": _str_prop("复盘目录（pitfalls.json/轮报所在）"),
                "events_path": _str_prop("mode=collect：轮内手工事件 JSON"),
                "scan_paths": {"type": "array",
                               "items": {"type": "string"},
                               "description": "mode=collect：产物痕迹扫描路径"},
                "close_id": _str_prop("mode=collect：结案的坑 ID"),
                "close_note": _str_prop("mode=collect：结案的可验证验收口径"
                                        "（带 close_id 时必填）"),
                "round": {"type": "number",
                          "description": "mode=report：轮号（真仓必填——缺省自动编号"
                                         "被 r156 护栏拒绝；沙盒缺省自增仍可用）"},
            },
            ["mode", "out_dir"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_director",
        "description": (
            "总监调度（第五角色，统辖四团队与资料员）。mode=route：按 org.json "
            "分派任务并给出指挥链/升级链（kind=review|fix|approve|retro|research|"
            "config-change）；mode=match：案例库复用匹配（疑难杂症先查案例，"
            "命中即复用对策，命中失败案例会提示避免同样路径）；mode=brief：签发"
            "研究简报（约束/中英检索词/验收口径；检索由宿主联网执行，结论经"
            "案例入库沉淀）；mode=scorecard：SRE 错误预算结算（超限判红，"
            "整队整改冻结）；mode=archive：档案员发布成败双轨案例档案仓"
            "（详细摘抄渲染为 archive/*.md 并本地 git 提交，可选推送远端）。"
        ),
        "inputSchema": _obj_schema(
            "总监调度入参",
            {
                "mode": {"type": "string",
                         "enum": ["route", "match", "brief", "scorecard",
                                  "archive"],
                         "description": "route=分派；match=案例匹配；brief=研究简报；scorecard=错误预算结算；archive=档案员发布案例档案仓"},
                "kind": {"type": "string",
                         "enum": ["review", "fix", "approve", "retro",
                                  "research", "config-change"],
                         "description": "mode=route：任务类型"},
                "payload": _str_prop("mode=route：任务上下文/交接物路径"),
                "problem": _str_prop("mode=match：待匹配的问题描述"),
                "description": _str_prop("mode=brief：疑难问题描述"),
                "out_dir": _str_prop("mode=brief/match/archive：研究或案例目录"),
                "remote": _str_prop("mode=archive 推送：Git 远端 URL"),
                "top": {"type": "number", "description": "mode=match：返回条数"},
            },
            ["mode"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": True},
    },
    {
        "name": "code_review_testgen",
        "description": (
            "测试生成（质量线 Phase 3A）。mode=skeleton：确定性 AST 骨架"
            "（style=loop 零依赖纯 pytest 冒烟 / hypothesis 属性模板；"
            "未类型化函数出 skip+TODO 不假装覆盖）；mode=llm：宿主协议"
            "写真用例（WAIT_HOST_LLM 退出码 1 → 宿主填 llm_response → "
            "重跑本命令幂等续跑），模型义务=具体断言不是冒烟；mode=verify："
            "生成物复制临时目录跑 pytest，通过才算生成成功；mode=patch："
            "新文件补丁（git apply 可创建文件）。生成物落盘走修复链。"
        ),
        "inputSchema": _obj_schema(
            "测试生成入参",
            {
                "mode": {"type": "string",
                         "enum": ["skeleton", "llm", "verify", "patch"],
                         "description": "skeleton=骨架；llm=宿主真用例；"
                                        "verify=验收；patch=新文件补丁"},
                "file": _str_prop("被测模块路径（skeleton/llm/verify 必填）"),
                "out": _str_prop("skeleton/llm：测试输出路径；patch：补丁目录"),
                "test": _str_prop("verify/patch：测试文件路径"),
                "rel": _str_prop("patch：仓库相对路径"),
                "style": {"type": "string", "enum": ["loop", "hypothesis"],
                          "description": "skeleton 风格，缺省 loop"},
            },
            ["mode"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_coding",
        "description": (
            "编码循环（编码线 Phase 2B，治理差异化：不直接写被审仓库）。"
            "新任务需 repo+task（resume=true 续跑仅需 out——schema 因此不强制"
            "二者）；参数缺失 → 立即错误提示（不进入循环）。"
            "任务→repo_map（tree-sitter 符号地图）→LLM（宿主协议）决定 "
            "read/edit/done →SEARCH/REPLACE 唯一命中编辑→worktree 跑仓库"
            "测试（pass 即收束）→产出 edits.patch（标准 a/ b/ 补丁）。"
            "补丁落盘走修复链（工单/批准书/五道闸）。WAIT_HOST_LLM（退出码"
            " 1）→ 宿主按动作 JSON 填 llm_response → --resume 续跑。"
        ),
        "inputSchema": _obj_schema(
            "编码循环入参",
            {
                "repo": _str_prop("目标仓库路径"),
                "task": _str_prop("任务描述（如『修复 add 使测试通过』）"),
                "out": _str_prop("任务产物目录（edits.patch/task-report）"),
                "resume": {"type": "boolean",
                           "description": "续跑已有任务目录"},
                "rounds": {"type": "number",
                           "description": "循环上限，缺省 6"},
            },
            ["out"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_refactor",
        "description": (
            "重构引擎（LibCST codemod，结构保序语义等价）。mode=scan：扫描"
            "可重构点（ref-eq-none ==None→is None / ref-in-keys "
            "in d.keys()→in d，返回 libcst:<code> 发现）；mode=fix-dry："
            "产出 unified diff 补丁建议（不落盘）。落盘走修复链"
            "（工单→批准书→五道闸）。需项目 .venv（libcst 依赖）。"
        ),
        "inputSchema": _obj_schema(
            "重构引擎入参",
            {
                "mode": {"type": "string", "enum": ["scan", "fix-dry"],
                         "description": "scan=扫描发现；fix-dry=补丁建议"},
                "file": _str_prop("scan：目标 .py 文件路径"),
                "repo": _str_prop("fix-dry：仓库根"),
                "rel": _str_prop("fix-dry：仓库相对路径"),
                "out": _str_prop("fix-dry：补丁产物目录"),
                "codes": _str_prop("限定 codemod，逗号分隔（缺省全部）"),
            },
            ["mode"],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_apply",
        "description": (
            "补丁落盘（唯一写被审仓库的通道）。--apply 需同时满足："
            "confirm=true 且持审核人批准书（approval_path，verdict=APPROVED 且 "
            "sha256 绑定当前补丁包）；五道闸任一失败自动回滚"
            "（isError=true, state=ROLLED_BACK）。confirm 缺省只做预检"
            "（PROPOSED，不需批准书）。undo=true 撤销已落盘修复分支。"
            "APPLIED 后修复在 review-fix/<id> 分支上，不自动合并。"
        ),
        "inputSchema": _obj_schema(
            "补丁落盘入参",
            {
                "manifest_path": _str_prop("fix-manifest.json 路径"),
                "repo": _str_prop("被审仓库路径"),
                "approval_path": _str_prop("审核人批准书 approval.json（--apply 必填）"),
                "confirm": {"type": "boolean",
                            "description": "显式确认落盘；缺省仅预检"},
                "undo": {"type": "boolean", "description": "撤销已落盘的修复分支"},
            },
            ["manifest_path", "repo"],
        ),
        "annotations": {
            "title": "补丁落盘（需 confirm=true 且持审核人批准书；缺省仅预检）",
            "readOnlyHint": False, "destructiveHint": True,
            "openWorldHint": False,
        },
    },
    {
        "name": "code_review_submit",
        "description": (
            "提交异步编排评审作业：立即返回 job_id，不阻塞 MCP 会话。"
            "作业独立于 stdio 连接存活（subprocess 守护 + 文件 status.json）；"
            "用 code_review_status 轮询，或用 review://jobs/<job_id> 资源读产物。"
        ),
        "inputSchema": _obj_schema(
            "异步评审提交入参（repo+range 或 resume 二选一）",
            {
                "repo": _str_prop("被审仓库路径"),
                "range": _str_prop("变更范围 A..B，如 HEAD~1..HEAD"),
                "request": _str_prop("用户原话"),
                "config_path": _str_prop("agent.json 路径（预算等配置）"),
                "reviewer": {"type": "string", "enum": ["deterministic", "llm"],
                             "description": "评审器类型，默认 deterministic"},
                "resume": _str_prop("续跑的 run 目录（给出后忽略 repo/range）"),
                "skip_probe": {"type": "boolean", "description": "跳过会话探针"},
                "out": _str_prop("run 产物根目录（缺省为 runs/jobs/<job_id>/run）"),
                "report_style": _str_prop("报告风格 preset 或 spec JSON 路径"),
                "budget": {"type": "integer", "minimum": 1,
                           "description": "预算分钟；生成 agent.json 覆盖 max_review_minutes"},
            },
            [],
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_status",
        "description": (
            "按 job_id 只读轮询异步作业状态：state=queued|running|done|failed，"
            "step/progress 来自 runner 进度帧；done 时 findings_url 指向 jobs 资源。"
            "非法 job_id（非 32 位十六进制）或不存在均 isError=true。"
        ),
        "inputSchema": _obj_schema(
            "作业状态入参", {"job_id": _str_prop("submit 返回的 32 位十六进制 job_id")},
            ["job_id"],
        ),
        "annotations": {"readOnlyHint": True, "destructiveHint": False,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_cancel",
        "description": (
            "取消 queued/running 异步作业：终止 runner 子进程树并写 state=cancelled + "
            "event-ledger 摘要。仅接受 32 位十六进制 job_id；终态作业返回 isError。"
        ),
        "inputSchema": _obj_schema(
            "取消作业入参", {"job_id": _str_prop("submit 返回的 32 位十六进制 job_id")},
            ["job_id"],
        ),
        "annotations": {"title": "取消异步作业（仅 queued/running，带账本摘要）",
                        "readOnlyHint": False, "destructiveHint": True,
                        "openWorldHint": False},
    },
    {
        "name": "code_review_purge",
        "description": (
            "清理终态作业目录（三重闸：confirm=true + 32 位 hex job_id + 终态）。"
            "删除前把 status/result 摘要写入作业账本；不支持批量与通配。"
        ),
        "inputSchema": _obj_schema(
            "清理作业入参",
            {"job_id": _str_prop("submit 返回的 32 位十六进制 job_id"),
             "confirm": {"type": "boolean", "description": "显式确认删除（缺省仅预检）"}},
            ["job_id"],
        ),
        "annotations": {"title": "清理终态作业（需 confirm=true；三重闸 + 账本摘要）",
                        "readOnlyHint": False, "destructiveHint": True,
                        "openWorldHint": False},
    },
]


def _run_script(script, args, timeout):
    """以参数列表运行评审脚本，返回 (stdout, stderr, exit_code)。"""
    cmd = [sys.executable, str(script)]
    for a in args:
        cmd.append(str(a))
    proc = subprocess.run(cmd, shell=False, timeout=timeout, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    return proc.stdout, proc.stderr, proc.returncode


def _tool_text(stdout, stderr, exit_code):
    text = (stdout or "").strip()
    if not text:
        text = (stderr or "").strip()[:2000] or "脚本无输出"
    return {"content": [{"type": "text", "text": text}], "isError": exit_code == 2}


def _tool_error(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _build_run_args(args):
    """把 MCP 入参收敛成 runner.py 白名单参数列表；返回 (cli, error)。"""
    repo = str(args.get("repo", "")).strip()
    rev_range = str(args.get("range", "")).strip()
    resume = str(args.get("resume", "")).strip()
    if not resume and (not repo or not rev_range):
        return None, "需要 repo + range，或 resume（run 目录）"
    cli = []
    if resume:
        cli += ["--resume", resume]
    else:
        cli += ["--repo", repo, "--range", rev_range]
    if str(args.get("request", "")):
        cli += ["--request", str(args["request"])]
    if str(args.get("config_path", "")):
        cli += ["--config", str(args["config_path"])]
    reviewer = str(args.get("reviewer", "")).strip()
    if reviewer:
        if reviewer not in ("deterministic", "llm"):
            return None, "reviewer 仅支持 deterministic|llm"
        cli += ["--reviewer", reviewer]
    if args.get("skip_probe"):
        cli += ["--skip-probe"]
    if str(args.get("out", "")):
        cli += ["--out", str(args["out"])]
    if str(args.get("report_style", "")):
        cli += ["--report-style", str(args["report_style"])]
    return cli, None


def _run_tool(args):
    cli, err = _build_run_args(args)
    if err:
        return _tool_error(err)
    stdout, stderr, rc = _run_script(SCRIPT_RUNNER, cli, RUN_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _job_status_path(job_id):
    """job_id 仅允许 32 位十六进制——拒绝路径穿越与任意文件读取。"""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        return None
    return JOB_ROOT / job_id


def _read_json_retry(path, attempts=5):
    """读 JSON 并对 Windows 共享锁冲突做有界重试（r190：status.json 的
    replace 换窗期，并发读会撞 PermissionError——写读双侧都要容错）。"""
    for attempt in range(attempts):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
        except FileNotFoundError:
            raise
    raise AssertionError("unreachable")


def _status_write(job_dir, state, **extra):
    data = {"state": state, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "step": None, "progress": 0.0}
    data.update(extra)
    p = job_dir / "status.json"
    # r190：Windows 并发写防冲突——uuid4 唯一 tmp 名（消除跨进程/跨线程 tmp
    # 路径碰撞）+ PermissionError/FileNotFoundError 有界重试（写窗口期共享锁
    # 冲突与 replace 竞速的自愈）。
    tmp = job_dir / ("status.json.tmp.%s" % uuid.uuid4().hex)
    payload = json.dumps(data, ensure_ascii=False)
    for attempt in range(5):
        try:
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(p)
            return
        except (PermissionError, FileNotFoundError):
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))
            # FileNotFoundError 时 tmp 可能已被并发 replace 带走，属正常。
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)


def _job_cancelled(job_dir):
    """job worker 自查取消标志：取消后置位，worker 不得再覆写终态。"""
    try:
        state = json.loads((job_dir / "status.json").read_text(
            encoding="utf-8")).get("state")
        return state == "cancelled"
    except (OSError, ValueError):
        return False


def _job_worker(job_id):
    """独立子进程执行器：读 job.json → runner → 落 status/result。"""
    job_dir = _job_status_path(job_id)
    if job_dir is None or not (job_dir / "job.json").exists():
        return 2
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    cli = list(job["cli"])
    runner = job.get("runner", str(SCRIPT_RUNNER))
    out_log = job_dir / "runner.log"
    started = time.monotonic()
    with out_log.open("w", encoding="utf-8") as log:
        _worker_kwargs = {}
        if os.name == "nt":
            # r188 静默化：runner 由 worker spawn——带 CREATE_NO_WINDOW 保证
            # 即便 worker 链缺控制台也不被分配可见窗口（防御性双重保险）。
            _worker_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([sys.executable, runner] + cli, shell=False,
                                stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT),
                                **_worker_kwargs)
        (job_dir / "runner.pid").write_text(str(proc.pid), encoding="utf-8")
        _status_write(job_dir, "running", progress=0.01)  # pid 落盘后才报 running
        step_re = re.compile(r"PROGRESS\s+step=(\d+)/(\d+)", re.I)

        def scan_step(text):
            hits = step_re.findall(text[-20000:])
            if not hits:
                return None
            num, total = hits[-1]
            return min(int(num), int(total))

        last_step = 0
        while proc.poll() is None:
            if _job_cancelled(job_dir):
                return 130
            if time.monotonic() - started > JOB_TIMEOUT:
                proc.kill()
                if _job_cancelled(job_dir):
                    return 130
                _status_write(job_dir, "failed", progress=1.0, exit_code=None,
                              error="job timeout %ds" % JOB_TIMEOUT)
                return 1
            text = out_log.read_text(encoding="utf-8", errors="replace")
            step = scan_step(text)
            if step is not None and step > last_step:
                last_step = step
                _status_write(job_dir, "running", step=step,
                              progress=min(0.99, step / 10.0))
            time.sleep(0.5)
    rc = proc.returncode
    if _job_cancelled(job_dir):
        return 130
    stdout = out_log.read_text(encoding="utf-8", errors="replace")
    # 快作业可能在两轮轮询之间结束——终局前补扫全量日志，避免 step 停在 0
    step = scan_step(stdout)
    if step is not None and step > last_step:
        last_step = step
    result = {}
    try:
        result = json.loads(stdout[stdout.find("{"):])
    except (ValueError, IndexError):
        result = {"raw": stdout[-4000:]}
    (job_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # r197：cancel-vs-worker 终态竞速——worker 在「自查取消」与「写终态」之间
    # 有时间窗，cancel 写入的 cancelled 会被随后的 failed/done 覆写（r197
    # run1 实弹 test_resource_cancel_summary）。终态写前复查取消标志：已取消
    # 则 worker 放弃写终态，保持 cancel 的终态为最终事实。
    if _job_cancelled(job_dir):
        return rc
    _status_write(job_dir, "done" if rc == 0 else "failed", step=last_step,
                  progress=1.0, exit_code=rc,
                  error=None if rc == 0 else "runner exit=%s" % rc)
    return rc


def _submit_tool(args):
    budget = args.get("budget")
    if budget is not None and (isinstance(budget, bool)
                               or not isinstance(budget, int) or budget < 1):
        return _tool_error("budget 必须为正整数分钟")
    config_src = str(args.get("config_path", "")).strip()
    base = dict(args)
    base.pop("budget", None)
    base.pop("config_path", None)
    cli, err = _build_run_args(base)
    if err:
        return _tool_error(err)

    job_id = uuid.uuid4().hex
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    ignored = []
    cfg_args = {}
    if config_src:
        try:
            source = json.loads(Path(config_src).read_text(encoding="utf-8"))
            raw = source.get("args") or {}
        except (OSError, ValueError) as exc:
            return _tool_error("config_path 读取失败: %s" % str(exc)[:200])
        if not isinstance(raw, dict):
            return _tool_error("config_path 的 args 必须是对象")
        for key, value in raw.items():
            cap = CONFIG_WHITELIST.get(key)
            if (cap is not None and isinstance(value, int)
                    and not isinstance(value, bool) and 1 <= value <= cap):
                cfg_args[key] = value
            else:
                ignored.append(key)
    if budget is not None:
        cfg_args["max_review_minutes"] = budget
    sandbox_cfg = str(job_dir / "agent.json")
    (job_dir / "agent.json").write_text(
        json.dumps({"args": cfg_args}, ensure_ascii=False), encoding="utf-8")
    if cfg_args:
        cli += ["--config", sandbox_cfg]

    out = str(args.get("out", "")).strip()
    if not out:
        out = str(job_dir / "run")
        cli += ["--out", out]
    (job_dir / "job.json").write_text(json.dumps(
        {"cli": cli, "runner": str(SCRIPT_RUNNER), "created": time.time()},
        ensure_ascii=False), encoding="utf-8")
    _status_write(job_dir, "queued")
    kwargs = {"shell": False, "cwd": str(ROOT), "stdin": subprocess.DEVNULL,
              "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        # CREATE_NO_WINDOW（r188，用户报告黑色弹窗）：worker 带隐藏控制台——
        # 子孙 spawn 控制台程序继承之、不再被 Windows 分配可见控制台（根因是
        # DETACHED_PROCESS 令 worker 无控制台，runner 等子孙被迫新建可见窗）；
        # CTRL_BREAK 组投递与 taskkill /T /F 兜底不受影响。
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                             "--job-worker", job_id, "--job-root", str(JOB_ROOT)], **kwargs)
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    job["worker_pid"] = proc.pid
    (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False),
                                      encoding="utf-8")
    _reap_detached()  # 清掉已终局作业的 Popen 句柄，避免 ResourceWarning
    _DETACHED_JOBS.append(proc)
    return _tool_text(json.dumps(
        {"job_id": job_id, "state": "queued",
         "resource": "review://jobs/" + job_id,
         "ignored_keys": sorted(ignored)}, ensure_ascii=False), "", 0)


def _status_tool(args):
    job_id = str(args.get("job_id", "")).strip()
    job_dir = _job_status_path(job_id)
    if job_dir is None or not (job_dir / "status.json").exists():
        return _tool_error("未知或不合法 job_id: %s" % job_id[:64])
    data = _read_json_retry(job_dir / "status.json")
    data["findings_url"] = ("review://jobs/" + job_id
                            if data.get("state") == "done" else None)
    return _tool_text(json.dumps(data, ensure_ascii=False), "", 0)


def _kill_pid(pid):
    """终止 runner 子进程树（Windows taskkill /T /F；Unix 进程组 SIGTERM）。"""
    if os.name == "nt":
        proc = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                              capture_output=True, text=True, timeout=20)
        return proc.returncode == 0
    try:
        os.kill(os.getpgid(pid), signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


def _cancel_tool(args):
    """取消 queued/running 作业：杀进程树 + cancelled 状态 + 账本摘要。"""
    job_id = str(args.get("job_id", "")).strip()
    job_dir = _job_status_path(job_id)
    status_path = job_dir / "status.json" if job_dir is not None else None
    if status_path is None or not status_path.exists():
        return _tool_error("未知或不合法 job_id: %s" % job_id[:64])
    data = json.loads(status_path.read_text(encoding="utf-8"))
    if data.get("state") not in ("queued", "running"):
        return _tool_error("仅 queued/running 作业可取消，当前 state=%s"
                           % data.get("state"))
    killed = []
    pid_path = job_dir / "runner.pid"
    # 加固：status=running 后 pid 文件可能在跨进程/高并发下晚一瞬可见；
    # 有界等待 2s 再回退 worker_pid，避免误判「没有可终止的 runner」。
    if not pid_path.exists() and data.get("state") == "running":
        for _ in range(20):
            if pid_path.exists():
                break
            time.sleep(0.1)
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
        if pid is not None and _kill_pid(pid):
            killed.append(pid)
    if not killed:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        worker_pid = job.get("worker_pid")
        if isinstance(worker_pid, int) and _kill_pid(worker_pid):
            killed.append(worker_pid)
    _status_write(job_dir, "cancelled", step=data.get("step"),
                  progress=data.get("progress", 0.0), exit_code=None,
                  error="cancelled")
    _, _, ledger_rc = _run_script(SCRIPT_EVENT_LEDGER, [
        "record", "--dir", str(job_dir), "--actor", "mcp",
        "--action", "job.cancel", "--kind", "note", "--replay", "opaque",
        "--observation-json", json.dumps(
            {"job_id": job_id, "state": "cancelled", "killed_pids": killed},
            ensure_ascii=False)], 30)
    return _tool_text(json.dumps(
        {"job_id": job_id, "state": "cancelled", "killed_pids": killed,
         "ledger_ok": ledger_rc == 0}, ensure_ascii=False), "", 0)


def _purge_tool(args):
    """清理终态作业：confirm + 32hex + 终态三重闸；删前写账本摘要。"""
    job_id = str(args.get("job_id", "")).strip()
    job_dir = _job_status_path(job_id)
    status_path = job_dir / "status.json" if job_dir is not None else None
    if status_path is None or not status_path.exists():
        return _tool_error("未知或不合法 job_id: %s" % job_id[:64])
    status = json.loads(status_path.read_text(encoding="utf-8"))
    terminal = ("done", "failed", "cancelled")
    if status.get("state") not in terminal:
        return _tool_error("仅终态作业可清理，当前 state=%s" % status.get("state"))
    if not args.get("confirm"):
        return _tool_text(json.dumps(
            {"job_id": job_id, "state": status.get("state"), "PROPOSED": True,
             "note": "缺省仅预检；追加 confirm=true 才实际删除"}, ensure_ascii=False), "", 0)
    result_path = job_dir / "result.json"
    summary = {"job_id": job_id, "state": status.get("state"),
               "exit_code": status.get("exit_code"),
               "has_result": result_path.exists()}
    _, _, ledger_rc = _run_script(SCRIPT_EVENT_LEDGER, [
        "record", "--dir", str(JOB_ROOT), "--actor", "mcp",
        "--action", "job.purge", "--kind", "note", "--replay", "opaque",
        "--observation-json", json.dumps(summary, ensure_ascii=False)], 30)
    if ledger_rc != 0:
        return _tool_error("账本摘要写入失败，拒绝清理（避免无审计删除）")
    try:
        shutil.rmtree(job_dir)
    except OSError as exc:
        return _tool_error("清理失败: %s" % str(exc)[:200])
    return _tool_text(json.dumps(
        {"job_id": job_id, "purged": True, "ledger_ok": ledger_rc == 0},
        ensure_ascii=False), "", 0)


def _resources_list():
    resources = []
    if JOB_ROOT.exists():
        for d in sorted(JOB_ROOT.iterdir(), reverse=True)[:20]:
            if d.is_dir() and JOB_ID_RE.match(d.name):
                resources.append({"uri": "review://jobs/" + d.name,
                                  "name": "job-" + d.name[:8],
                                  "mimeType": "application/json"})
                if (d / "ledger.jsonl").exists():
                    resources.append({"uri": "review://jobs/" + d.name + "/ledger",
                                      "name": "job-" + d.name[:8] + "-ledger",
                                      "mimeType": "application/x-ndjson"})
    return resources


LEDGER_MAX_BYTES = 65536


def _read_cancel_summary(job_dir):
    """从作业账本读最后一条 job.cancel 摘要（无账本/无记录返回 None）。"""
    ledger = job_dir / "ledger.jsonl"
    if not ledger.exists():
        return None
    try:
        lines = ledger.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            rec = json.loads(line)
            if rec.get("action") == "job.cancel":
                obs = rec.get("observation") or {}
                return {"killed_pids": obs.get("killed_pids") or [],
                        "state": obs.get("state")}
    except (OSError, ValueError):
        return None
    return None


def _ledger_verify(job_dir):
    """只读校验作业账本哈希链；无账本返回 None，失败返回 ok=false。"""
    ledger = job_dir / "ledger.jsonl"
    if not ledger.exists():
        return None
    out, err, rc = _run_script(
        SCRIPT_EVENT_LEDGER, ["verify", "--ledger", str(ledger)], 30)
    try:
        data = json.loads(out)
    except ValueError:
        return {"ok": False, "error": (err or out)[:200]}
    return {"ok": bool(data.get("ok")) and rc == 0,
            "records": data.get("records"), "first_bad": data.get("first_bad")}


def _resource_read(uri):
    text = str(uri)
    ledger_match = re.fullmatch(r"review://jobs/([0-9a-f]{32})/ledger", text)
    if ledger_match:
        job_dir = JOB_ROOT / ledger_match.group(1)
        ledger = job_dir / "ledger.jsonl" if job_dir.is_dir() else None
        if ledger is None or not ledger.exists():
            return None
        raw = ledger.read_text(encoding="utf-8", errors="replace")
        truncated = len(raw.encode("utf-8")) > LEDGER_MAX_BYTES
        body = raw[:LEDGER_MAX_BYTES]
        if truncated:
            body += "\n[TRUNCATED at %d bytes]\n" % LEDGER_MAX_BYTES
        return {"contents": [{"uri": uri, "mimeType": "application/x-ndjson",
                              "text": body}]}

    match = re.fullmatch(r"review://jobs/([0-9a-f]{32})", text)
    if not match:
        return None
    job_id = match.group(1)
    job_dir = JOB_ROOT / job_id
    if not job_dir.is_dir():
        return None
    status = _read_json_retry(job_dir / "status.json")
    result_path = job_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))         if result_path.exists() else None
    # 向后兼容：旧顶层字段原样保留；新字段只增不改（job_state 表示作业状态）。
    payload = dict(result if result is not None else status)
    payload.update({"job_id": job_id, "job_state": status.get("state"),
                    "status": status, "result": result,
                    "cancel": _read_cancel_summary(job_dir),
                    "ledger_verify": _ledger_verify(job_dir)})
    return {"contents": [{"uri": uri, "mimeType": "application/json",
                          "text": json.dumps(payload, ensure_ascii=False)}]}


def _scan_tool(args):
    path = str(args.get("path", "")).strip()
    diff_path = str(args.get("diff_path", "")).strip()
    if bool(path) == bool(diff_path):
        return _tool_error("path 与 diff_path 必须且只能给一个")
    cli = ["--file", path] if path else ["--diff-file", diff_path]
    stdout, stderr, rc = _run_script(SCRIPT_RULES, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _plan_tool(args):
    diff_path = str(args.get("diff_path", "")).strip()
    if not diff_path:
        return _tool_error("diff_path 必填")
    cli = ["--diff", diff_path]
    if str(args.get("intent", "")):
        cli += ["--intent", str(args["intent"])]
    if str(args.get("experience", "")):
        cli += ["--experience", str(args["experience"])]
    stdout, stderr, rc = _run_script(SCRIPT_PLAN, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _feedback_tool(args):
    findings = str(args.get("findings_path", "")).strip()
    experience = str(args.get("experience_path", "")).strip()
    if not findings or not experience:
        return _tool_error("findings_path 与 experience_path 均必填")
    cli = ["--findings", findings, "--experience", experience]
    stdout, stderr, rc = _run_script(SCRIPT_FEEDBACK, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _approve_tool(args):
    mode = str(args.get("mode", "")).strip()
    repo = str(args.get("repo", "")).strip()
    out_dir = str(args.get("out_dir", "")).strip()
    if mode not in ("scope", "patch"):
        return _tool_error("mode 仅支持 scope|patch")
    if not repo or not out_dir:
        return _tool_error("repo 与 out_dir 均必填")
    if mode == "scope":
        findings = str(args.get("findings_path", "")).strip()
        if not findings:
            return _tool_error("mode=scope 需要 findings_path")
        cli = ["--findings", findings, "--repo", repo, "--out", out_dir]
        if str(args.get("severities", "")):
            cli += ["--severities", str(args["severities"])]
        stdout, stderr, rc = _run_script(SCRIPT_APPROVE_PLAN, cli, FAST_TIMEOUT)
    else:
        order = str(args.get("order_path", "")).strip()
        manifest = str(args.get("manifest_path", "")).strip()
        if not order or not manifest:
            return _tool_error("mode=patch 需要 order_path 与 manifest_path")
        cli = ["--order", order, "--manifest", manifest, "--repo", repo,
               "--out", out_dir]
        stdout, stderr, rc = _run_script(SCRIPT_APPROVE_PATCH, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _fix_tool(args):
    order = str(args.get("order_path", "")).strip()
    repo = str(args.get("repo", "")).strip()
    out_dir = str(args.get("out_dir", "")).strip()
    if not order or not repo or not out_dir:
        return _tool_error("order_path、repo、out_dir 均必填")
    stdout, stderr, rc = _run_script(
        SCRIPT_FIX_PATCH, ["--order", order, "--repo", repo, "--out", out_dir],
        FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _apply_tool(args):
    manifest = str(args.get("manifest_path", "")).strip()
    repo = str(args.get("repo", "")).strip()
    if not manifest or not repo:
        return _tool_error("manifest_path 与 repo 均必填")
    cli = ["--manifest", manifest, "--repo", repo]
    approval = str(args.get("approval_path", "")).strip()
    if approval:
        cli += ["--approval", approval]
    confirm = args.get("confirm")
    if args.get("undo"):
        cli += ["--undo"]
    elif isinstance(confirm, bool) and confirm:
        cli += ["--apply"]
    stdout, stderr, rc = _run_script(SCRIPT_FIX_APPLY, cli, APPLY_TIMEOUT)
    result = _tool_text(stdout, stderr, rc)
    if rc != 0:
        result["isError"] = True  # apply 语义：回滚/失败均视为错误
    return result


def _retro_tool(args):
    mode = str(args.get("mode", "")).strip()
    out_dir = str(args.get("out_dir", "")).strip()
    if mode not in ("collect", "report"):
        return _tool_error("mode 仅支持 collect|report")
    if not out_dir:
        return _tool_error("out_dir 必填")
    if mode == "collect":
        cli = ["--out", out_dir]
        events = str(args.get("events_path", "")).strip()
        if events:
            cli += ["--events", events]
        for scan_root in args.get("scan_paths") or []:
            if str(scan_root).strip():
                cli += ["--scan", str(scan_root)]
        close_id = str(args.get("close_id", "")).strip()
        if close_id:
            close_note = str(args.get("close_note", "")).strip()
            if not close_note:
                return _tool_error("结案要带可验证验收口径：close_id=%s 需要同时给 "
                                   "close_note（怎么验、验到什么程度才算填了坑）" % close_id)
            cli += ["--close", close_id, "--close-note", close_note]
        stdout, stderr, rc = _run_script(SCRIPT_RETRO_LEDGER, cli, FAST_TIMEOUT)
    else:
        cli = ["--ledger", str(Path(out_dir) / "pitfalls.json"), "--out", out_dir]
        if args.get("round"):
            cli += ["--round", str(args["round"])]
        stdout, stderr, rc = _run_script(SCRIPT_RETRO_REPORT, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _director_tool(args):
    mode = str(args.get("mode", "")).strip()
    if mode == "route":
        kind = str(args.get("kind", "")).strip()
        if not kind:
            return _tool_error("mode=route 需要 kind")
        cli = ["--kind", kind]
        if str(args.get("payload", "")):
            cli += ["--payload", str(args["payload"])]
        stdout, stderr, rc = _run_script(SCRIPT_ORG_ROUTE, cli, FAST_TIMEOUT)
    elif mode == "match":
        problem = str(args.get("problem", "")).strip()
        if not problem:
            return _tool_error("mode=match 需要 problem")
        cli = ["--match", problem, "--out", str(ROOT / "retro")]
        if args.get("top"):
            cli += ["--top", str(args["top"])]
        stdout, stderr, rc = _run_script(SCRIPT_CASE_MATCH, cli, FAST_TIMEOUT)
    elif mode == "brief":
        out_dir = str(args.get("out_dir", "")).strip() or str(ROOT / "retro")
        cli = ["--description", str(args.get("description", "")),
               "--out", out_dir, "--case-dir", str(ROOT / "retro")]
        stdout, stderr, rc = _run_script(SCRIPT_RESEARCH_BRIEF, cli, FAST_TIMEOUT)
    elif mode == "scorecard":
        cli = []
        for scan_root in args.get("scan_paths") or []:
            if str(scan_root).strip():
                cli += ["--scan", str(scan_root)]
        stdout, stderr, rc = _run_script(SCRIPT_ORG_SCORECARD, cli, FAST_TIMEOUT)
    elif mode == "archive":
        out_dir = str(args.get("out_dir", "")).strip() or str(ROOT / "retro")
        cli = ["--out", out_dir, "--publish"]
        if args.get("push"):
            remote = str(args.get("remote", "")).strip()
            if not remote:
                return _tool_error("mode=archive 推送需要 remote")
            cli += ["--push", "--remote", remote]
        stdout, stderr, rc = _run_script(SCRIPT_CASE_ARCHIVE, cli, FAST_TIMEOUT)
    else:
        return _tool_error("mode 仅支持 route|match|brief|scorecard|archive")
    return _tool_text(stdout, stderr, rc)


def _testgen_tool(args):
    mode = str(args.get("mode", "")).strip()
    out = str(args.get("out", "")).strip()
    src = str(args.get("file", "")).strip()
    if mode == "skeleton":
        if not src or not out:
            return _tool_error("skeleton 需要 file 与 out")
        cli = ["skeleton", "--file", src, "--out", out]
        if str(args.get("style", "")):
            cli += ["--style", str(args["style"])]
    elif mode == "llm":
        if not src or not out:
            return _tool_error("llm 需要 file 与 out")
        cli = ["llm", "--file", src, "--out", out]
    elif mode == "verify":
        test = str(args.get("test", "")).strip()
        if not src or not test:
            return _tool_error("verify 需要 file 与 test")
        cli = ["verify", "--file", src, "--test", test]
    elif mode == "patch":
        test = str(args.get("test", "")).strip()
        rel = str(args.get("rel", "")).strip()
        if not test or not rel or not out:
            return _tool_error("patch 需要 test、rel 与 out")
        cli = ["patch", "--test", test, "--rel", rel, "--out", out]
    else:
        return _tool_error("mode 仅支持 skeleton|llm|verify|patch")
    stdout, stderr, rc = _run_script(SCRIPT_TESTGEN, cli, FAST_TIMEOUT)
    return _tool_text(stdout, stderr, rc)


def _coding_tool(args):
    out = str(args.get("out", "")).strip()
    if not out:
        return _tool_error("out 必填（任务产物目录）")
    cli = ["--out", out]
    if args.get("resume"):
        cli += ["--resume"]
    else:
        repo = str(args.get("repo", "")).strip()
        task = str(args.get("task", "")).strip()
        if not repo or not task:
            return _tool_error("新任务需要 repo 与 task")
        cli += ["--repo", repo, "--task", task]
    if args.get("rounds"):
        cli += ["--rounds", str(args["rounds"])]
    if not VENV_PYTHON.is_file():
        return _tool_error("编码循环需要项目 .venv（tree-sitter 依赖）")
    proc = subprocess.run([str(VENV_PYTHON), str(SCRIPT_CODE_TASK)] + cli,
                          shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600,
                          cwd=str(ROOT))
    return _tool_text(proc.stdout, proc.stderr,
                      1 if proc.returncode == 1 else proc.returncode)


def _refactor_tool(args):
    mode = str(args.get("mode", "")).strip()
    codes = str(args.get("codes", "")).strip()
    if mode == "scan":
        src = str(args.get("file", "")).strip()
        if not src:
            return _tool_error("scan 需要 file")
        cli = ["scan", "--file", src]
        if str(args.get("rel", "")):
            cli += ["--rel", str(args["rel"])]
        if codes:
            cli += ["--codes", codes]
    elif mode == "fix-dry":
        repo = str(args.get("repo", "")).strip()
        rel = str(args.get("rel", "")).strip()
        out = str(args.get("out", "")).strip()
        if not repo or not rel or not out:
            return _tool_error("fix-dry 需要 repo、rel 与 out")
        cli = ["fix-dry", "--repo", repo, "--rel", rel, "--out", out]
        if codes:
            cli += ["--codes", codes]
    else:
        return _tool_error("mode 仅支持 scan|fix-dry")
    if not VENV_PYTHON.is_file():
        return _tool_error("重构引擎需要项目 .venv（libcst 依赖）")
    proc = subprocess.run([str(VENV_PYTHON), str(SCRIPT_LIBCST)] + cli,
                          shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60,
                          cwd=str(ROOT))
    return _tool_text(proc.stdout, proc.stderr,
                      1 if proc.returncode == 1 else proc.returncode)


_TOOL_HANDLERS = {
    "code_review_run": _run_tool,
    "code_review_scan": _scan_tool,
    "code_review_plan": _plan_tool,
    "code_review_feedback": _feedback_tool,
    "code_review_approve": _approve_tool,
    "code_review_fix": _fix_tool,
    "code_review_retro": _retro_tool,
    "code_review_director": _director_tool,
    "code_review_testgen": _testgen_tool,
    "code_review_coding": _coding_tool,
    "code_review_refactor": _refactor_tool,
    "code_review_apply": _apply_tool,
    "code_review_submit": _submit_tool,
    "code_review_status": _status_tool,
    "code_review_cancel": _cancel_tool,
    "code_review_purge": _purge_tool,
}


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _policy_level(name):
    """工具分级门控（tools-policy.json，批次一 M4）。

    返回 auto|gated|deny；未知工具与文件缺失/损坏一律 deny（fail-closed）。
    清单演进须与 TOOLS/pin 同轮刷新（mcp-selfscan.py pin 同 commit）。
    """
    if name not in _POLICY_CACHE:
        path = Path(__file__).resolve().parent / "tools-policy.json"
        try:
            d = json.load(open(path, encoding="utf-8"))
            levels = d.get("tools") or {}
        except (OSError, ValueError):
            levels = {}
        _POLICY_CACHE[name] = levels.get(name, "deny")
    return _POLICY_CACHE[name]


def _handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if mid is None:
        return None  # 通知帧：不回复（initialized 等生命周期通知）
    if method == "initialize":
        return _ok(mid, {"protocolVersion": PROTOCOL_VERSION,
                         "capabilities": {"tools": {}, "resources": {}},
                         "serverInfo": SERVER_INFO})
    if method == "ping":
        return _ok(mid, {})
    if method == "tools/list":
        return _ok(mid, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name", ""))
        handler = _TOOL_HANDLERS.get(name)
        if handler is None:
            return _ok(mid, _tool_error("未知工具: %s" % name))
        arguments = params.get("arguments") or {}

        level = _policy_level(name)
        if level == "deny":
            return _ok(mid, _tool_error("工具分级门控拒绝（deny/未知工具）: %s" % name))
        if not isinstance(arguments, dict):
            return _ok(mid, _tool_error("arguments 必须为对象"))
        try:
            return _ok(mid, handler(arguments))
        except subprocess.TimeoutExpired:
            return _ok(mid, _tool_error("工具执行超时: %s" % name))
        except OSError as exc:
            return _ok(mid, _tool_error("执行失败: %s" % exc))
    if method == "resources/list":
        return _ok(mid, {"resources": _resources_list()})
    if method == "resources/read":
        params = msg.get("params") or {}
        payload = _resource_read(params.get("uri"))
        if payload is None:
            return _ok(mid, _tool_error("未知资源 URI: %s"
                                        % str(params.get("uri"))[:120]))
        return _ok(mid, payload)
    if method == "prompts/list":
        return _ok(mid, {"prompts": []})
    return _err(mid, -32601, "method not found: %s" % method)


def _write(obj):
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        sys.stderr.write("stdout 管道已断开，停止写出响应\n")


def _startup_selfscan():
    """启动自扫描（批次一 M1）：TOOLS/policy 哈希漂移即拒服务（fail-closed）。

    自扫描脚本缺失或 pin 漂移均拒绝启动；job-worker 路径不经过此处。
    """
    root = Path(__file__).resolve().parents[1]
    script = root / "skills/production-guardrails/scripts/mcp-selfscan.py"
    try:
        spec = importlib.util.spec_from_file_location("mcp_selfscan", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except OSError:
        sys.stderr.write("MCP 自扫描脚本缺失，拒绝启动" + chr(10))
        raise SystemExit(1)
    ok, drifts, computed = mod.check(root)
    if not ok:
        for d in drifts:
            sys.stderr.write("MCP 自扫描漂移: %s %s" % (d.get("id"), d.get("tool", d.get("detail", ""))) + chr(10))
        raise SystemExit(1)


def serve():
    _startup_selfscan()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            _write(_err(None, -32700, "parse error"))
            continue
        if not isinstance(msg, dict):
            _write(_err(None, -32700, "parse error"))
            continue
        resp = _handle(msg)
        if resp is not None:
            _write(resp)
    return 0


def main():
    for stream in (sys.stdin, sys.stdout):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if "--job-worker" in sys.argv:
        global JOB_ROOT
        idx = sys.argv.index("--job-worker")
        job_id = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if "--job-root" in sys.argv:
            root_idx = sys.argv.index("--job-root")
            if root_idx + 1 < len(sys.argv):
                JOB_ROOT = Path(sys.argv[root_idx + 1])
        return _job_worker(job_id)
    return serve()


if __name__ == "__main__":
    sys.exit(main())
