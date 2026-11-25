#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码循环 v1（agent 层：tree-sitter 仓库地图 + SEARCH/REPLACE + 宿主 LLM）。

架构抄作业（许可证已核实）：OpenHands 事件流（动作→观察回馈）、
SWE-agent ACI（精简工具面）、Aider（repo map + SEARCH/REPLACE）。
差异化：产出补丁后走既有修复链（工单/批准书/五道闸），本脚本不直接
写被审仓库——编辑在临时 worktree 上进行，测试通过才收束。

流程（每轮，上限 --rounds）：
  1. 材料 = 任务 + 仓库地图 + 历史（读文件/上轮观察）
  2. LLM（llm/provider，宿主协议）回 JSON：
     {"action":"search","query":"符号名","glob":"*.py"} → 有界字面搜索
     {"action":"read","files":[...]} → 下一轮附文件内容
     {"action":"edit","edits":[SEARCH/REPLACE 块]} → worktree 应用 + 跑
       仓库测试（pytest/go 测试/npm 脚本，按仓库自动识别）→ 观察回馈 →
       失败可继续修
  3. 测试通过即收束（不强问 LLM）；超轮数取最后一次编辑态产出补丁。

产物（--out）：edits.patch（a/ b/ 头 LF）、task-report.md、
task-manifest.json（engine=agent，接修复链）。宿主模式：
CRA_LLM_PROVIDER=host → WAIT_HOST_LLM（退出码 1）→ 宿主填 llm-tasks
响应 → --resume <out 目录> 续跑。

补丁即时校验（round-28，见 retro/next-round.md 第 7/9 项）：编辑轮次与收束
时各校验一次「补丁非空 + 关键改动确实在补丁里 + 新增行纯 ASCII」。未过则把
问题写进历史让模型当轮重做；收束仍无补丁即 NO_PATCH（退出码 1），不再让
下游收集器静默回退到上一版补丁（v1.28.0 实踩：SEARCH 写成上一版补丁的代码
→ 编辑未命中 → 补丁为空 → 评的是旧补丁，全程无报错）。

行为探针（round-28 第 3 项，需 --allow-probe 显式开启）：模型可发
{"action":"probe","code":"..."} 在临时 worktree 里跑一段 Python 观察对象
状态（顶点数 / extent / __dict__ 这类），把「状态类缺陷」从猜变成看。

用法示例（.venv/Scripts/python）：
    python agent/code-task.py --repo <仓库> --task "修复 add 的符号错误" --out <目录>

退出码：0=完成（含未收敛）；1=WAIT_HOST_LLM 或 NO_PATCH；2=输入错误。

实现已拆分到 agent/code_task/ 包（materials/loop/selfcheck/search/testrun/tools/candidates/state/protocol/review_gate）：本文件保留 CLI 入口与
对外符号再导出（tests 与既有引用按原命名访问不变）。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

# 对外再导出：拆分为 agent/code_task/ 后，tests 与既有引用按原命名访问
import subprocess  # noqa: F401 - 既有 tests 以 mod.subprocess 打桩
from agent.code_task.protocol import SYSTEM_PROMPT, PROBE_CLAUSE, PHASE_SYSTEM, _system_prompt, _emit, _progress_frame, _parse_response, _apply_protocol_notes
from agent.code_task.tools import _worktree_diff, _ws_diff, _git, _pytest_exe, _snapshot_paths, _restore_paths
from agent.code_task.selfcheck import _module_name, _no_bytecode_env, _SECRET_KV_RE, _SECRET_SHAPE_RES, _import_probe, _import_probe_docker, _ws_import_probe, _patch_selfcheck, _added_lines, _novel_lines, _match_change, _validate_patch, _redact_snippet
from agent.code_task.search import SEARCH_SKIP_DIRS, SEARCH_TEXT_EXTS, _DEF_NAME_RE, _search_kind, _path_distance, _search_repo, _list_tree, _probe
from agent.code_task.testrun import _discover_test_paths, _pytest_run, _find_exe, _NODE_TEST_RE, ENGINE_SKIP_DIRS, _discover_node_tests, _split_cmdline, _detect_test_engine, _engine_run, _select_test_paths, _run_tests
from agent.code_task.candidates import CAND_TIER_PASS, CAND_TIER_FAIL, CAND_TIER_SKIP, CAND_TIER_EMPTY, _save_candidate, _rank_candidates, _write_memory
from agent.code_task.state import TaskState
from agent.code_task.materials import PROBE_FIRST_NOTE, PROBE_TEMPLATE, PROBE_DOCKER_NOTE, MAX_INLINE_CHARS, MAX_INLINE_LINES, COMPRESS_TRIGGER_CHARS, KEEP_RECENT_ENTRIES, _repair_plan_note, _material_prefix, _material_suffix, _compress_history, _truncate_for_history, _material, _retro_few_shot
from agent.code_task.review_gate import _review_gate, _parse_review_cmds
from agent.code_task.loop import main
from llm import provider
from agent.edit_formats import apply_edits, parse_blocks
from agent.phases import PhaseState
from agent.trace import Tracer
from agent.repo_map import (build_map, render_material, extract_keywords,
                            rank_candidates, render_candidates, scan_candidates,
                            merge_candidates, extract_window,
                            slice_lines, extract_symbol_span,
                            find_sibling_tests, find_sibling_test_paths,
                            build_import_graph, graph_rank,
                            syntax_issues)
from agent.workspace import open_workspace, WorkspaceError
from agent.review_loop import run_review, ReviewError


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
