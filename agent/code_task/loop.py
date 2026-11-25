#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编码循环主流程（轮次预算/阶段状态机/收束裁决）。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import argparse
import json
import os
import re
import time
from agent.repo_map import (build_map, extract_keywords, rank_candidates, scan_candidates, merge_candidates, extract_window, slice_lines, extract_symbol_span, find_sibling_tests, build_import_graph, graph_rank, syntax_issues)  # noqa: E402
from llm import provider  # noqa: E402
from agent.edit_formats import apply_edits, parse_blocks  # noqa: E402
from agent.phases import PhaseState  # noqa: E402
from agent.trace import Tracer  # noqa: E402
from agent.workspace import open_workspace, WorkspaceError  # noqa: E402
from agent.review_loop import run_review, ReviewError  # noqa: E402
from agent.code_task.candidates import _rank_candidates, _save_candidate, _write_memory
from agent.code_task.materials import KEEP_RECENT_ENTRIES, _compress_history, _material_prefix, _material_suffix, _retro_few_shot, _truncate_for_history
from agent.code_task.protocol import _apply_protocol_notes, _emit, _parse_response, _progress_frame, _system_prompt
from agent.code_task.review_gate import _parse_review_cmds, _review_gate
from agent.code_task.search import _list_tree, _probe, _search_repo
from agent.code_task.selfcheck import _patch_selfcheck, _redact_snippet, _validate_patch
from agent.code_task.state import TaskState
from agent.code_task.testrun import _run_tests
from agent.code_task.tools import _git, _restore_paths, _snapshot_paths, _ws_diff


def main():
    parser = argparse.ArgumentParser(description="编码循环 v1（agent 层）")
    parser.add_argument("--repo", help="目标仓库")
    parser.add_argument("--task", help="任务描述")
    parser.add_argument("--out", required=True, help="任务产物目录")
    parser.add_argument("--resume", action="store_true",
                        help="续跑（读 out/task-meta.json）")
    # round-58 实踩：--resume 不带 --rounds 时旧实现回退默认 6，宿主多轮
    # 驱动会在第 6 轮被腰斩；预算持久化，显式参数优先。
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--max-chars", dest="max_chars", type=int, default=6000)
    parser.add_argument("--allow-probe", dest="allow_probe", action="store_true",
                        help="允许 probe 动作（在工作区执行模型给的探针代码；"
                             "默认关闭——属于扩大权限，由宿主显式授权）")
    parser.add_argument("--probe-docker", dest="probe_docker", default="",
                        help="探针改在该 Docker 镜像内执行（工作区只读挂载 "
                             "/testbed，镜像环境=官方评测环境）；"
                             "必须与 --allow-probe 同用")
    parser.add_argument("--workspace", default="",
                        help="工作区后端（阶段四 4.3）：local（默认）/ "
                             "container:<image> / remote:<target>。容器档把"
                             "测试/探针/补丁自检放进容器执行（工作区仍是同一"
                             "份挂载）；remote 档接口在 agent/workspace.py，"
                             "编码循环不接（无真实远端时不假跑）")
    parser.add_argument("--memory-file", dest="memory_file", default="",
                        help="编码记忆 JSONL 路径（缺省读环境变量 "
                             "CRA_MEMORY_FILE；两者都为空则关闭记忆读写，"
                             "避免测试/临时任务污染长期记忆）")
    parser.add_argument("--protocol-notes", dest="protocol_notes", default="",
                        help="协议提示附录文件路径：内容追加到任务文本尾部，"
                             "随任务进 state（--resume 持久化）；用于对探索"
                             "节奏偏慢的 openai 兼容端点下发预算压力与先编辑"
                             "指引（round-77/78 实跑验证；样例见 "
                             "agent/protocol-notes-example.md）")
    parser.add_argument("--rank", choices=("refs", "graph"), default="refs",
                        help="候选文件排序：refs=关键词打分（默认）；"
                             "graph=叠加 import 图个性化 PageRank 的邻居补充")
    parser.add_argument("--phases", action="store_true",
                        help="三角色分解模式（阶段四 4.1）：定位→修复→验证，"
                             "主循环只做裁决（accept/rework/escalate）")
    parser.add_argument("--locate-rounds", dest="locate_rounds", type=int,
                        default=2,
                        help="locate 子代理的轮数上限（耗尽降级进修复；"
                             "默认 2）")
    parser.add_argument("--rework-max", dest="rework_max", type=int, default=2,
                        help="verify 拒收后的最大返工次数（超过即 ESCALATED；"
                             "默认 2）")
    parser.add_argument("--test-cmd", dest="test_cmd", default="",
                        help="显式测试命令（覆盖引擎自动识别；cwd=worktree；"
                             "阶段四 4.2：go.mod/package.json 自动识别）")
    parser.add_argument("--review", default="",
                        help="评审闭环（阶段四 4.4）：逗号分隔的评审器"
                             "（self,ruff,astgrep,ocr 或 --review-cmd 自定义"
                             "名）；空=关闭。差异率超阈值转 NEED_HUMAN、"
                             "不写 manifest")
    parser.add_argument("--review-threshold", dest="review_threshold",
                        type=float, default=0.5,
                        help="自评/他评差异率阈值（默认 0.5）")
    parser.add_argument("--review-cmd", dest="review_cmd", action="append",
                        default=[], help="name=command 外部评审器（可重复；"
                                         "stdout 需为 {\"findings\":[...]}）")
    parser.add_argument("--review-ocr", dest="review_ocr", default="",
                        help="Open Code Review 可执行路径（只取 delegate "
                             "文件覆盖，不调 LLM）")
    parser.add_argument("--shadow-checkpoints", dest="shadow_checkpoints",
                        default="on",
                        help="影子检查点开关（AB-11，缺省 on=仅 local 档 "
                             "fix 每轮全树快照；off=关闭。r204 init 延迟"
                             "修复后恢复缺省 on）")
    parser.add_argument("--rollback-to", dest="rollback_to", default="",
                        help="还原 worktree 到指定影子检查点（label 如 "
                             "round-1）后退出——不进入编码循环")
    argv = parser.parse_args()
    # 绝对化：worktree 经 git -C <repo> 创建，相对路径会被 git 解释到
    # 仓内（round-18 实踩：wt 建到 prep 仓的 datasets/ 下，编辑全报文件不存在）
    out_dir = Path(argv.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    state = TaskState(out_dir).load()
    state.begin_session()
    if argv.resume:
        state.data["shadow_checkpoints"] = argv.shadow_checkpoints
        state.save()
        manifest_path = out_dir / "task-manifest.json"
        # AB-11（r202）：--rollback-to 还原 worktree 到指定影子检查点后退出
        # （工具性动作：失败运行的工作区可回滚到任意轮起点，不进入循环）。
        if argv.rollback_to:
            from agent.shadow_git import ShadowGit
            sg = ShadowGit(worktree)
            res = sg.rollback(argv.rollback_to)
            _emit({"ok": bool(res.get("ok")),
                   "restored_to": argv.rollback_to,
                   "sha": res.get("sha"), "error": res.get("error")})
            return 0 if res.get("ok") else 1
        if manifest_path.is_file():
            # 幂等续跑：已收束的任务直接回放结果——不再进循环（否则会重建
            # worktree 并可能改写已产出的补丁，round-18 实踩）。
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = {}
            patch_name = manifest.get("patch") or ""
            replay = {"ok": True, "state": "DONE",
                      "patch": str(out_dir / patch_name) if patch_name else "",
                      "tests": manifest.get("tests", state.data.get("tests")),
                      "test_engine": manifest.get(
                          "test_engine", state.data.get("test_engine")),
                      "rounds": manifest.get("rounds",
                                             state.data.get("round")),
                      "edits": manifest.get("edits",
                                            state.data.get("edits_applied")),
                      "elapsed_sec": manifest.get("elapsed_sec",
                                                  state.data.get("elapsed_sec")),
                      "patch_validation": manifest.get(
                          "patch_validation", {"ok": True, "issues": []}),
                      "note": "已收束：幂等回放（未重建 worktree）"}
            if "resolved" in manifest:
                replay["resolved"] = manifest["resolved"]
                replay["phases"] = manifest.get("phases")
            if "review" in manifest:
                replay["review"] = manifest["review"]
            _emit(replay)
            return 0
        repo = Path(state.data.get("repo", ""))
        task = state.data.get("task", "")
    else:
        if not argv.repo or not argv.task:
            _emit({"ok": False, "error": "需要 --repo + --task，或 --resume"})
            return 2
        if argv.probe_docker and not argv.allow_probe:
            _emit({"ok": False,
                   "error": "--probe-docker 必须与 --allow-probe 同用"
                            "（权限闸只有一个：--allow-probe）"})
            return 2
        repo, task = Path(argv.repo), argv.task
        if argv.protocol_notes:
            try:
                task = _apply_protocol_notes(task, argv.protocol_notes)
            except ValueError as exc:
                _emit({"ok": False, "error": str(exc)}, 2)
        state.data.update({"repo": str(repo.resolve()), "task": task,
                           "round": 0, "history": [], "edits_applied": 0,
                           "tests": "skip", "blocks": [], "attempted": [],
                           "rounds_budget": (-1 if argv.rounds is None
                                             else int(argv.rounds)),
                           "allow_probe": bool(argv.allow_probe),
                           "probe_docker": argv.probe_docker,
                           "rank": argv.rank,
                           "shadow_checkpoints": argv.shadow_checkpoints,
                           "phases_mode": bool(argv.phases),
                           "locate_rounds": argv.locate_rounds,
                           "rework_max": argv.rework_max,
                           "memory_file": argv.memory_file or
                           os.environ.get("CRA_MEMORY_FILE", ""),
                           "test_cmd": (argv.test_cmd or "").strip()})
    # 动作面随任务固定：--resume 用持久化的授权态，不用 CLI 重算
    # （provider 的幂等 id = sha256(system+user)，改了 system 会让同一材料
    #  重新进等待态）
    allow_probe = bool(state.data.get("allow_probe"))
    probe_docker = state.data.get("probe_docker") or ""
    # 阶段四 4.3：工作区后端（显式参数优先，其次 --resume 持久化值）
    ws_spec = str(argv.workspace or state.data.get("workspace") or "").strip()
    # --resume 沿用首次运行持久化的记忆路径（环境变量变了也不中途换档）
    memory_file = (state.data.get("memory_file") or argv.memory_file or
                   os.environ.get("CRA_MEMORY_FILE", ""))
    # 阶段四 4.2：测试引擎显式覆盖；--resume 沿用持久化值（中途换命令会让
    # 「通过」不再可比）
    test_cmd = (state.data.get("test_cmd") or argv.test_cmd or "").strip()
    # 阶段四 4.1：三角色分解状态机（--phases）；单循环模式 enabled=False，
    # 所有 gate/role_section 都退化为空操作。
    # 轮数预算：显式 --rounds 优先，否则用任务创建时持久化的值（缺省 6）
    persisted_rounds = int(state.data.get("rounds_budget") or 0)
    if persisted_rounds <= 0:
        persisted_rounds = int(argv.rounds or 6)
        state.data["rounds_budget"] = persisted_rounds
    rounds_budget = (persisted_rounds if argv.rounds is None
                     else int(argv.rounds))
    phases_mode = bool(state.data.get("phases_mode"))
    ph = PhaseState.load(state.data, out_dir, enabled=phases_mode,
                         locate_rounds=int(
                             state.data.get("locate_rounds") or 2),
                         rework_max=int(state.data.get("rework_max") or 2))
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库不存在: %s" % repo})
        return 2
    # --repo 必须是「仓库本身」：git -C 会向上找到顶层仓，worktree 于是建在
    # 外层仓的 HEAD 上。本轮实踩过一次——一个没 git init 的临时目录当
    # --repo，`git worktree add` 静默把 dev-agent 自己的工作树挂了出来。
    # 宁可 exit 2，也不能默默动到别的仓库。
    rc, top, _err = _git(repo, ["rev-parse", "--show-toplevel"])
    if rc != 0:
        _emit({"ok": False,
               "error": "--repo 不是 git 仓库（需已 git init 并可解析到顶层）: %s"
                       % repo})
        return 2
    if Path(top.strip()).resolve() != repo.resolve():
        _emit({"ok": False,
               "error": "--repo 不是仓库顶层：git 会向上找到 %s，"
                        "worktree 将建在外层仓上" % top.strip(),
               "repo": str(repo.resolve())})
        return 2

    ws = None
    if ws_spec:
        state.data["workspace"] = ws_spec
        try:
            ws = open_workspace(ws_spec, repo, out_dir)
        except WorkspaceError as exc:
            _emit({"ok": False, "error": str(exc), "workspace": ws_spec})
            return 2
        if ws.backend == "remote":
            _emit({"ok": False,
                   "error": "remote 档接口已就绪（agent/workspace.py "
                            "--backend remote:<target>），编码循环接线待真实"
                            "远端环境；本轮不以本地假壳冒充真机",
                   "workspace": ws_spec})
            return 2
        state.save()

    llm_dir = out_dir / "llm-tasks"
    worktree = out_dir / "wt"
    history = state.data["history"]
    blocks_log = state.data.setdefault("blocks", [])
    # AB-11（r202→r203 修正）：影子检查点——本地 worktree 档 fix 每轮开始
    # 全树快照。r203 根因链闭合：init 必须延迟到 wt 物理存在后（首个 fix
    # 轮），否则 GIT_DIR env 无 work tree → bare init → add 拒绝。
    shadow = None
    keywords = extract_keywords(task)
    # 候选文件扫一次即可（关键词与任务绑定，不随轮次变）。round-53：--rank
    # graph 时叠加 import 图邻居（默认 refs，材料与旧路径一致）。
    rank_mode = str(state.data.get("rank") or "refs")
    repo_map = build_map(repo)
    candidates = merge_candidates(
        rank_candidates(repo_map, keywords),
        scan_candidates(repo, keywords))
    rank_info = {"mode": rank_mode, "candidates": len(candidates)}
    if rank_mode == "graph":
        t_graph = time.monotonic()
        graph = build_import_graph(repo)
        extra = graph_rank(graph, candidates, keywords)
        candidates = merge_candidates(candidates, extra)
        rank_info.update({"graph_files": len(graph["files"]),
                          "graph_edges": graph["edges"],
                          "graph_candidates": len(extra),
                          "build_sec": round(time.monotonic() - t_graph, 3),
                          "candidates": len(candidates)})
    # v1.43.0：稳定前缀循环外计算一次，每轮只拼动态后缀（prompt caching 友好）
    material_prefix = _material_prefix(repo, task, argv.max_chars,
                                       candidates, allow_probe, probe_docker,
                                       repo_map=repo_map)
    # 记忆检索同样与轮次无关：一次任务算一次，注入稳定前缀之后
    retro_section, retro_hits = ("", 0)
    if memory_file:
        retro_section, retro_hits = _retro_few_shot(task, memory_file)
    # v1.43.0：轻量 Trace 埋点（JSONL，兼容 Langfuse 数据模型）
    # gen_ai_system=provider.select()：llm span 的 gen_ai.system 取值来自
    # provider 后端模式（批次 B1-06）；select() 只读环境、无副作用。
    tracer = Tracer(session_id=out_dir.name,
                    trace_dir=str(out_dir / "traces"),
                    gen_ai_system=provider.select())
    tracer.span("init", "start", repo=str(repo), task=task[:200],
                rounds=rounds_budget, allow_probe=allow_probe)
    tracer.span("rank", "done", **rank_info)
    try:
        while state.data["round"] < rounds_budget:
            # 阶段四 4.1：裁决闸——已 resolved/escalated 不再进 LLM；
            # locate 轮数用尽在此降级（决定入 phases.json）
            if phases_mode:
                if ph.resolved or ph.escalated:
                    break
                if (ph.phase == "locate"
                        and int(ph.data.get("locate_rounds_used") or 0)
                        >= int(ph.data.get("locate_rounds_max") or 0)):
                    ph.degrade_locate(
                        round_no=state.data["round"],
                        why="定位轮数用尽（%d 轮）" % int(
                            ph.data.get("locate_rounds_max") or 0))
                    history.append("定位轮数用尽，主循环降级进入修复阶段"
                                   "（裁决记入 phases.json）")
                    state.save()
            # v1.44.0 步骤 1.7：流式进度帧 — 节点 1：轮次开始
            _progress_frame(state.data["round"], "round_start",
                            total_rounds=rounds_budget,
                            history_len=len(history),
                            phase=ph.phase if phases_mode else "")
            # AB-11（r202→r203 修正）：fix 阶段每轮开始全树影子快照。
            # r203 根因：init 在 wt 创建前运行 → bare init → add 拒绝。
            # 修正：延迟到首个 fix 轮（此时 wt 已由 worktree add 物理创建），
            # 首次调用 _ensure_init（wt 存在 → core.bare=false+work-tree 生效）。
            _is_fix_round = ((not phases_mode) or ph.phase == "fix")
            if _is_fix_round and shadow is None \
                    and getattr(ws, "backend", "local") == "local" \
                    and str(state.data.get("shadow_checkpoints", "")) != "off" \
                    and worktree.is_dir():
                try:
                    from agent.shadow_git import ShadowGit
                    shadow = ShadowGit(worktree)
                    init = shadow._ensure_init()
                    if not init.get("ok"):
                        history.append("影子检查点不可用（不阻断）: %s"
                                       % str(init.get("error", ""))[:120])
                        shadow = None
                except (OSError, ImportError) as exc:
                    history.append("影子检查点不可用（不阻断）: %s"
                                   % str(exc)[:120])
                    shadow = None
            if shadow and _is_fix_round:
                snap = shadow.snapshot("round-%d" % state.data["round"])
                if not snap.get("ok"):
                    history.append("影子快照失败（不阻断）: %s"
                                   % str(snap.get("error", ""))[:240])

            # v1.43.0：每轮开始前检查 history 是否需要压缩
            if len(history) > KEEP_RECENT_ENTRIES:
                history[:] = _compress_history(history)
            suffix = _material_suffix(history)
            material = material_prefix
            if retro_section:
                material += "\n" + retro_section
            if phases_mode:
                # verify 角色要看补丁与测试结果；fix 角色要看定位报告与退回理由
                diff_now = ""
                if ph.phase == "verify" and worktree.is_dir():
                    rc_d, d_now, _ = _ws_diff(ws, worktree)
                    if rc_d == 0:
                        diff_now = d_now
                material += "\n\n" + ph.role_section(
                    diff=diff_now, tests=state.data.get("tests", "skip"))
            if suffix:
                material += "\n" + suffix
            # 阶段提示随角色切换（单循环模式为空，prompt 与旧版逐字一致）
            sys_prompt = _system_prompt(allow_probe,
                                        ph.phase if phases_mode else "")
            _t0 = time.monotonic()
            # v1.44.0 步骤 1.7：流式进度帧 — 节点 2：LLM 调用前
            _progress_frame(state.data["round"], "llm_call_start",
                            material_chars=len(material),
                            history_entries=len(history))
            tracer.span("llm", "call_start", round=state.data["round"])
            try:
                raw, meta = provider.complete(
                    sys_prompt, material, base_dir=llm_dir,
                    on_tokens=lambda n: tracer.span(
                        "llm", "token_count", token_output=n))
            except provider.HostLLMPending as pending:
                tracer.span("llm", "call_end",
                            duration_ms=int((time.monotonic() - _t0) * 1000),
                            status="wait_host")
                state.save()
                # round-72 结构改造：稳定指针文件——prompt id 随材料逐跳变化，
                # 宿主凭记忆复用上一跳 id 会把响应写进已消费的旧文件（本会话
                # 连续多轮实踩）；每跳覆写 PENDING 指针，宿主只需读这一个文件。
                pending_ptr = Path(llm_dir) / "PENDING"
                pending_ptr.write_text(
                    "prompt=%s\nresponse=%s\n" % (pending.prompt_path,
                                                  pending.response_path),
                    encoding="utf-8", newline="\n")
                _emit({"ok": False, "state": "WAIT_HOST_LLM",
                       "llm_task": pending.prompt_path,
                       "llm_response": pending.response_path,
                       "pending_ptr": str(pending_ptr),
                       "out_dir": str(out_dir),
                       "note": "宿主模型：读 llm_task（或 out_dir/llm-tasks/PENDING "
                               "指针，逐跳覆写），按 system 约定仅输出动作 JSON "
                               "写入 llm_response——id 随材料逐跳变化，勿复用"
                               "上一跳的响应路径——然后 --resume %s 续跑"
                               % out_dir})
                return 1
            _ms = int((time.monotonic() - _t0) * 1000)
            tracer.span("llm", "call_end", duration_ms=_ms,
                        status="ok" if raw else "fail",
                        model=(meta or {}).get("model", ""))
            if raw is None:
                history.append("LLM 不可用：%s" % meta)
                state.save()
                break
            action = _parse_response(raw)
            # v1.44.0 步骤 1.7：流式进度帧 — 节点 3：解析响应后
            _progress_frame(state.data["round"], "parsed",
                            action=action.get("action", "") if action else "none",
                            raw_len=len(raw or ""),
                            parse_ok=bool(action))
            tracer.span("parse", "done",
                        status="ok" if action else "fail",
                        action=action.get("action", "") if action else "",
                        round=state.data["round"])
            if not action:
                history.append("LLM 响应不可解析（截断 80 字）：%s"
                               % (raw or "")[:80])
                state.data["round"] += 1
                state.save()
                continue
            act = str(action.get("action", ""))
            # 阶段四 4.1：角色动作面门禁——locate/verify 只读，编辑一律拒收；
            # 拒收也扣一轮（预算不失控），并写进历史让模型下一轮改动作
            if phases_mode:
                reject = ph.gate(act)
                if reject:
                    history.append(reject)
                    if ph.phase == "locate":
                        ph.note_locate_round()
                    state.data["round"] += 1
                    state.save()
                    continue
                if ph.phase == "locate":
                    ph.note_locate_round()
            if phases_mode and act == "locate_done":
                # locate 子代理交结构化定位报告 → 裁决 accept/degrade → fix
                ph.accept_locate(action, round_no=state.data["round"])
                files = [f for f in (action.get("files") or []) if f]
                history.append("定位完成：%d 个文件（confidence=%s），"
                               "进入修复阶段"
                               % (len(files),
                                  action.get("confidence") or "?"))
                state.data["round"] += 1
                state.save()
                continue
            if phases_mode and act == "verdict":
                # verify 子代理裁决；机械测试结果优先（tests != pass 时
                # pass=true 无效），拒收退回 fix 并附理由
                ph.register_verdict(action, tests=state.data.get("tests",
                                                                 "skip"),
                                    round_no=state.data["round"])
                state.data["round"] += 1
                state.save()
                if ph.resolved:
                    history.append("验证通过：resolved")
                    break
                if ph.escalated:
                    history.append("验证连续拒收，升级 ESCALATED")
                    break
                history.append("验证退回（第 %d 次返工）：%s"
                               % (int(ph.data.get("rework_count") or 0),
                                  "；".join(ph.data.get("last_reasons")
                                           or [])[:300]))
                continue
            if act == "search":
                src = worktree if worktree.is_dir() else repo
                ok, obs = _search_repo(
                    src, str(action.get("query", "")),
                    str(action.get("glob", "") or ""),
                    near=[c.get("file", "") for c in candidates[:8]])
                tracer.span("search", "done",
                            status="ok" if ok else "fail",
                            round=state.data["round"],
                            query=_redact_snippet(
                                str(action.get("query", "")))[:80])
                history.append(_truncate_for_history(
                    "仓库搜索（%s）：\n%s" % ("rc=0" if ok else "未执行", obs),
                    out_dir, state.data["round"], "search"))
                state.data["round"] += 1
                state.save()
                continue
            if act == "read":
                files = [str(f) for f in (action.get("files") or [])[:5]]
                for rel in files:
                    # round-69 结构改造：支持 路径:起-止 行区间与 路径#符号 锚定
                    # （open 坑：默认取窗只覆盖文件头，深文件段不可达）
                    m_range = re.match(r"^(.*?):(\d+)\s*-\s*(\d*)$", rel)
                    m_sym = re.match(r"^(.*?)#([\w.]+)$", rel)
                    plain_rel = rel
                    range_req = sym_req = None
                    if m_range:
                        plain_rel = m_range.group(1)
                        range_req = (int(m_range.group(2)),
                                     int(m_range.group(3))
                                     if m_range.group(3) else None)
                    elif m_sym:
                        plain_rel = m_sym.group(1)
                        sym_req = m_sym.group(2)
                    # 读 worktree（已有编辑时以自己的版本为准），否则读基线仓
                    src = worktree if worktree.is_dir() else repo
                    target = src / plain_rel
                    if target.is_file():
                        text = target.read_text(encoding="utf-8",
                                                errors="replace")
                        if range_req is not None:
                            shown = "（行区间 %d-%s）\n%s" % (
                                range_req[0],
                                range_req[1] if range_req[1] else "EOF",
                                slice_lines(text, range_req[0], range_req[1]))
                        elif sym_req is not None:
                            span = extract_symbol_span(text, sym_req)
                            if span:
                                shown = "（符号 %s）\n%s" % (sym_req, span)
                            else:
                                shown = ("（未找到符号 %s，退回关键词取窗）\n%s"
                                         % (sym_req, extract_window(
                                             text, keywords, max_chars=3000)))
                        else:
                            # 按任务关键词取窗（round-19）：目标函数常在文件头
                            # 3000 字之外，且 docstring 里的语义约束看不到
                            shown = extract_window(text, keywords,
                                                   max_chars=3000)
                            # 附上邻近测试片段（round-20）：边界语义常只写在
                            # 模块自己的测试里
                            tests_ctx = find_sibling_tests(repo, plain_rel)
                            if tests_ctx:
                                shown = "%s\n%s" % (shown, tests_ctx)
                        _entry = "文件 %s：\n%s" % (plain_rel, shown)
                        history.append(_truncate_for_history(
                            _entry, out_dir, state.data["round"],
                            "read_%s" % plain_rel.replace("/", "_")[:40]))
                    else:
                        history.append("文件 %s 不存在" % plain_rel)
                state.data["round"] += 1
                state.save()
                continue
            if act == "list":
                # 2.3：只读目录观察（限深限宽、剪运行产物、路径不得越界）
                src = worktree if worktree.is_dir() else repo
                try:
                    wanted_depth = int(action.get("depth", 2) or 2)
                except (TypeError, ValueError):
                    wanted_depth = 2
                ok, obs = _list_tree(src, str(action.get("path", "") or ""),
                                     depth=wanted_depth)
                tracer.span("list", "done",
                            status="ok" if ok else "fail",
                            round=state.data["round"],
                            path=str(action.get("path", ""))[:120])
                history.append(_truncate_for_history(
                    "目录列表（%s）：\n%s" % ("rc=0" if ok else "未执行", obs),
                    out_dir, state.data["round"], "list"))
                state.data["round"] += 1
                state.save()
                continue
            if act == "probe":
                if not allow_probe:
                    history.append("probe 动作未授权：本任务未带 --allow-probe，"
                                   "探针不执行（读文件与测试观察仍可用）")
                else:
                    ok, obs = _probe(worktree, repo,
                                     str(action.get("code", "")),
                                     docker_image=probe_docker, ws=ws)
                    _entry = "行为探针（%s）：\n%s" % (
                        "rc=0" if ok else "非零退出", obs)
                    history.append(_truncate_for_history(
                        _entry, out_dir, state.data["round"], "probe"))
                state.data["round"] += 1
                state.save()
                continue
            if act == "edit":
                edits = action.get("edits") or []
                if not isinstance(edits, list) or not edits:
                    history.append("edit 动作缺 edits 数组")
                    state.data["round"] += 1
                    state.save()
                    continue
                # worktree：首编辑时建立（HEAD 基线），后续轮复用
                if not worktree.is_dir():
                    if ws is not None:
                        try:
                            ws.prepare()
                        except WorkspaceError as exc:
                            history.append("工作区准备失败（%s）: %s"
                                           % (ws_spec, str(exc)[:200]))
                            state.data["round"] += 1
                            state.save()
                            continue
                    else:
                        rc, _, err = _git(repo, ["worktree", "add",
                                                 "--detach",
                                                 str(worktree), "HEAD"])
                        if rc != 0:
                            history.append("worktree 建立失败: %s"
                                           % err.strip()[:120])
                            state.data["round"] += 1
                            state.save()
                            continue
                blocks_text = "\n\n".join(
                    "%s\n<<<<<<< SEARCH\n%s\n=======\n%s\n>>>>>>> REPLACE"
                    % (b.get("path"), b.get("search", ""), b.get("replace", ""))
                    for b in edits if isinstance(b, dict))
                try:
                    blocks = parse_blocks(blocks_text)
                except ValueError as exc:
                    history.append("编辑块格式错误: %s" % exc)
                    state.data["round"] += 1
                    state.save()
                    continue
                pre_snapshot = _snapshot_paths(
                    worktree, [str(b.get("path", "")) for b in blocks
                               if isinstance(b, dict)])
                blocks_before = list(blocks_log)
                result = apply_edits(worktree, blocks)
                applied_paths = [a["path"] for a in result["applied"]]
                # 记录「模型声称要改哪些文件」，与「实际改成的」分开：
                # 全部编辑都没命中时补丁为空，收束仍要据声称过的东西判定
                # 这是没交付物（NO_PATCH），而不是「无需改动」的假 DONE。
                attempted = state.data.setdefault("attempted", [])
                for b in blocks:
                    rel = str(b.get("path", "")).replace("\\", "/")
                    if rel and rel not in attempted:
                        attempted.append(rel)
                for err in result["errors"]:
                    history.append("编辑失败 %s: %s" % (err["path"],
                                                        err["error"]))
                if result["applied"]:
                    state.data["edits_applied"] += len(result["applied"])
                    # 补丁自检：基线对比式导入冒烟（round-20）——把「补丁把
                    # 模块弄坏」拦在本地，不必等容器才发现
                    broken = _patch_selfcheck(repo, worktree, applied_paths,
                                              docker_image=probe_docker, ws=ws)
                    for path, err in broken:
                        history.append("补丁自检：%s 导入失败（补丁前可导入）"
                                       "——补丁破坏了模块：%s" % (path, err))
                    # 记录本轮生效的编辑（同路径后写覆盖前写），供即时校验与
                    # 收束时复核「关键改动确实进了补丁」
                    for b in blocks:
                        if b.get("path") in applied_paths:
                            blocks_log[:] = [x for x in blocks_log
                                             if x.get("path") != b["path"]]
                            blocks_log.append({
                                "path": b["path"],
                                "search": str(b.get("search", ""))[:2000],
                                "replace": str(b.get("replace", ""))[:2000]})
                    rc_now, diff_now, _ = _ws_diff(ws, worktree)
                    check = _validate_patch(
                        diff_now, [b for b in blocks_log
                                   if b["path"] in applied_paths],
                        applied_paths)
                    # 2.5：语法树级校验——diff 正则看不出括号不闭合，tree-sitter
                    # 的 ERROR 节点能；与补丁校验合并后同样走「非末轮退回重做」
                    syn = syntax_issues(worktree, applied_paths)
                    if syn:
                        check["issues"].extend(syn)
                        check["ok"] = False
                    if not check["ok"] and state.data["round"] + 1 < rounds_budget:
                        for it in check["issues"]:
                            history.append("补丁即时校验未过[%s]：%s"
                                           % (it["code"], it["detail"]))
                        history.append("请先 read 当前文件的真实内容，再出与之一字"
                                       "不差的 SEARCH；补丁里不要写中文注释。")
                        restored = _restore_paths(worktree, pre_snapshot)
                        state.data["edits_applied"] -= len(result["applied"])
                        blocks_log[:] = blocks_before
                        history.append("本轮编辑已回滚 %d 个文件（校验未过的改动"
                                       "不得留在工作树）" % restored)
                        state.data["round"] += 1
                        state.save()
                        continue
                test_info = {}
                status, detail = _run_tests(
                    worktree, applied_paths,
                    audit_seed="%s|%s" % (state.data["round"],
                                          "|".join(applied_paths)),
                    test_cmd=test_cmd, info=test_info, ws=ws)
                state.data["test_engine"] = test_info.get("engine", "")
                tracer.span("test", "done", status=status,
                            round=state.data["round"],
                            detail_len=len("; ".join(detail)))
                state.data["tests"] = status
                state.data["test_scope"] = detail[0] if detail else ""
                # v1.44.0 步骤 1.7：流式进度帧 — 节点 5：测试后
                _progress_frame(state.data["round"], "test_done",
                                status=status,
                                detail="; ".join(detail)[:200],
                                tests_count=state.data.get("tests", 0))
                if result["applied"]:
                    tracer.span("edit", "applied",
                                count=len(result["applied"]),
                                files=[a["path"] for a in result["applied"]],
                                round=state.data["round"])
                # 候选快照（round-37，借 Agentless 多候选排序）：每次成功
                # edit + 测试后保存补丁快照，收束时排序选最优
                    rc_snap, diff_snap, _ = _ws_diff(ws, worktree)
                    _save_candidate(out_dir, state.data["round"],
                                    diff_snap, status, detail,
                                    state.data["edits_applied"],
                                    check, broken,
                                    applied_paths)
                    # 步骤 1.5：写入记忆
                    _write_memory(
                        out_dir, repo, task,
                        files=applied_paths,
                        edit_summary="; ".join(
                            "%s: %s" % (b.get("path", ""),
                                        str(b.get("replace", ""))[:80])
                            for b in blocks_log
                            if b.get("path") in applied_paths),
                        rule_codes=[],
                        result="pass" if status == "pass" else "fail",
                        failure_category="",
                        trace_file=tracer.path,
                        retrieval_count=retro_hits,
                        memory_file=memory_file,
                        round_num=state.data["round"])
                    # v1.44.0 步骤 1.7：流式进度帧 — 节点 4：edit 应用后
                    _progress_frame(state.data["round"], "edit_applied",
                                    files=applied_paths,
                                    edits_count=len(result["applied"]),
                                    test_status=status)
                history.append("编辑 %d 项（失败 %d）；测试 %s：%s"
                               % (len(result["applied"]),
                                  len(result["errors"]), status,
                                  "; ".join(detail)[-200:]))
                state.data["round"] += 1
                state.save()
                if phases_mode:
                    # 测试绿即交验证（不直接收束：resolved 只有 verify 能签）
                    if status == "pass":
                        ph.request_verify(round_no=state.data["round"],
                                          tests=status, why="仓库测试通过")
                    continue
                if status == "pass":
                    break
                continue
            if act == "done":
                history.append("LLM 声明完成: %s"
                               % str(action.get("summary", ""))[:80])
                state.data["round"] += 1
                state.save()
                if phases_mode:
                    # fix 阶段 done = 提前交验证；verify 阶段的 done 已被门禁拒
                    ph.request_verify(round_no=state.data["round"],
                                      tests=state.data.get("tests", "skip"),
                                      why="修复子代理声明完成")
                    continue
                break
            history.append("未知动作: %s" % act)
            state.data["round"] += 1
            state.save()

        # 阶段四 4.1：循环没收敛（轮数用尽）→ 升级，不静默当完成
        if phases_mode and not ph.resolved and not ph.escalated:
            ph.exhaust(round_no=state.data["round"],
                       why="全局轮数用尽（%d 轮）" % rounds_budget)
            history.append("全局轮数用尽：三角色未收敛，升级 ESCALATED")
            state.save()
        # 收束：产出补丁与报告（以 worktree 与 HEAD 的 diff）
        patch_text, report_lines = "", ["# 编码任务报告", "",
                                        "- 任务：%s" % task,
                                        "- 轮数：%d / %d" % (
                                            state.data["round"], rounds_budget),
                                        "- 编辑应用：%d 项" % state.data[
                                            "edits_applied"],
                                        "- 仓库测试：%s" % state.data["tests"]]
        if ws is not None:
            report_lines.append("- 工作区：%s（%s）" % (
                ws.backend, ws.image or ws.target or "本机"))
        final_syntax = []
        ws_info = None
        if worktree.is_dir():
            rc, diff_out, diff_err = _ws_diff(ws, worktree)
            if rc != 0:
                history.append("补丁生成失败（git diff rc=%d）：%s"
                               % (rc, diff_err.strip()[:200]))
            elif diff_out.strip():
                patch_text = diff_out
                (out_dir / "edits.patch").write_text(
                    patch_text, encoding="utf-8", newline="\n")
            # 2.5：收束前最后一次语法树校验（worktree 移除后就查不到了）。
            # 只查真正落过编辑的文件——attempted 里可能含编辑失败的路径，
            # 那些文件还是基线内容，拿它们的旧语法判交付物是误报。
            final_syntax = syntax_issues(
                worktree, [b["path"] for b in blocks_log])
            if ws is not None:
                try:
                    ws_info = ws.describe(probe=True)
                except WorkspaceError as exc:
                    ws_info = {"backend": ws.backend,
                               "error": str(exc)[:200]}
                try:
                    ws.close()
                except WorkspaceError as exc:
                    history.append("工作区清理失败: %s" % str(exc)[:200])
            else:
                _git(repo, ["worktree", "remove", "--force", str(worktree)])
        # 候选排序（round-37，借 Agentless 回归过滤+投票排序）
        cands, best = _rank_candidates(out_dir)
        selected_source = "last_edit"
        if best and best.get("has_patch"):
            best_tests = best.get("tests", "skip")
            cur_tests = state.data.get("tests", "skip")
            best_patch = best.get("patch_text", "")
            # 最优候选测试通过而当前未通过 → 用最优候选
            if best_tests == "pass" and cur_tests != "pass":
                patch_text = best_patch
                state.data["tests"] = best_tests
                selected_source = "candidate_round_%d" % best.get("round", 0)
                (out_dir / "edits.patch").write_text(
                    patch_text, encoding="utf-8", newline="\n")
            # 都通过但最优候选补丁更小 → 用最小补丁原则
            elif (best_tests == "pass" and cur_tests == "pass"
                  and best.get("patch_chars", 0) > 0
                  and best.get("patch_chars", 0) < len(patch_text or "")):
                patch_text = best_patch
                selected_source = "candidate_round_%d" % best.get("round", 0)
                (out_dir / "edits.patch").write_text(
                    patch_text, encoding="utf-8", newline="\n")
            # 当前无补丁但最优候选有 → 用最优候选
            elif not (patch_text or "").strip() and best_patch.strip():
                patch_text = best_patch
                state.data["tests"] = best_tests
                selected_source = "candidate_round_%d" % best.get("round", 0)
                (out_dir / "edits.patch").write_text(
                    patch_text, encoding="utf-8", newline="\n")
        report_lines.append("- 补丁来源：%s" % selected_source)
        # 收束复核：补丁非空 + 每处编辑的关键改动都在补丁里 + 新增行纯 ASCII
        claimed = [b["path"] for b in blocks_log] or state.data.get(
            "attempted", [])
        validation = _validate_patch(patch_text, blocks_log, claimed)
        # 收束语法校验只对「最后一次编辑」的补丁成立；若交付的是候选快照，
        # 该快照在其轮次已带语法校验（见编辑分支），不再套用工作树状态。
        if final_syntax and selected_source == "last_edit":
            validation["issues"] = list(validation["issues"]) + final_syntax
            validation["ok"] = False
        if not validation["ok"] and not patch_text:
            # 声称改了但拿不出补丁 = 没有可交付物。如实报 NO_PATCH（退出码 1），
            # 不写 manifest——下游收集器因此不会拿到一份「看起来正常」的产物，
            # 也就不会静默回评上一版补丁（round-28 检查单第 7 项的根因）。
            report_lines += ["", "## 补丁即时校验未过"] + [
                "- [%s] %s" % (i["code"], i["detail"])
                for i in validation["issues"]]
            (out_dir / "task-report.md").write_text(
                "\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
            state.save()
            _emit({"ok": False, "state": "NO_PATCH", "patch": "",
                   "tests": state.data["tests"],
                   "rounds": state.data["round"],
                   "edits": state.data["edits_applied"],
                   "patch_validation": validation,
                   "note": "编辑未落到补丁：read 当前文件真实内容后重出 "
                           "SEARCH，或加大 --rounds 续跑 %s" % out_dir})
            return 1
        # 阶段四 4.1：三角色未收敛 → ESCALATED（不写 manifest，下游不收）
        if phases_mode and ph.escalated and not ph.resolved:
            report_lines += ["", "## 阶段裁决（phases.json）"]
            for d in ph.data.get("decisions") or []:
                report_lines.append(
                    "- [%s] %s：%s（round %s，tests=%s）"
                    % (d.get("decision"), d.get("phase"), d.get("reason"),
                       d.get("round"), d.get("tests")))
            report_lines += ["", "## 历史"] + ["- %s" % h for h in history]
            (out_dir / "task-report.md").write_text(
                "\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
            state.save()
            _emit({"ok": False, "state": "ESCALATED",
                   "resolved": False,
                   "patch": str(out_dir / "edits.patch") if patch_text else "",
                   "tests": state.data["tests"],
                   "rounds": state.data["round"],
                   "edits": state.data["edits_applied"],
                   "phases": ph.summary(),
                   "reason": ph.data.get("reason", ""),
                   "note": "三角色未收敛：不写 manifest、补丁不交付；"
                           "可加大 --rounds / --rework-max 续跑 %s" % out_dir})
            return 1
        # 阶段四 4.4：评审闭环（可选）——自评与他评差异量化，超阈值转人工
        review_spec = str(argv.review or state.data.get("review") or "").strip()
        review_result = None
        if review_spec:
            state.data["review"] = review_spec
            report_lines += ["", "## 评审闭环（4.4）"]
            if not (patch_text or "").strip():
                review_result = {"decision": "NEED_HUMAN",
                                 "reasons": ["无补丁可评审"],
                                 "metrics": {}, "external_status": [],
                                 "coverage": None}
            else:
                try:
                    review_result = _review_gate(
                        repo, out_dir, patch_text,
                        reviewers=[r.strip() for r in review_spec.split(",")
                                   if r.strip()],
                        threshold=float(argv.review_threshold),
                        cmds=_parse_review_cmds(argv.review_cmd),
                        ocr_exe=argv.review_ocr,
                        self_tests=state.data.get("tests", "skip"),
                        self_issues=list(validation.get("issues") or []))
                except ReviewError as exc:
                    review_result = {"decision": "NEED_HUMAN",
                                     "reasons": ["评审闭环执行失败：%s"
                                                 % str(exc)[:300]],
                                     "metrics": {}, "external_status": [],
                                     "coverage": None}
            metrics = review_result.get("metrics") or {}
            report_lines += [
                "- 判定：%s（差异率 %s / 阈值 %.2f）"
                % (review_result.get("decision"),
                   metrics.get("diff_rate", "N/A"),
                   float(argv.review_threshold)),
                "- 评审器：%s" % ", ".join(
                    "%s=%s" % (s.get("name"), s.get("status"))
                    for s in review_result.get("external_status") or []) or "无"]
            for reason in review_result.get("reasons") or []:
                report_lines.append("- 转人工原因：%s" % reason)
            if review_result.get("decision") != "PASS":
                report_lines += ["", "## 历史"] + ["- %s" % h for h in history]
                (out_dir / "task-report.md").write_text(
                    "\n".join(report_lines) + "\n", encoding="utf-8",
                    newline="\n")
                state.save()
                _emit({"ok": False, "state": "NEED_HUMAN",
                       "patch": str(out_dir / "edits.patch")
                                if patch_text else "",
                       "tests": state.data["tests"],
                       "rounds": state.data["round"],
                       "edits": state.data["edits_applied"],
                       "review": review_result,
                       "reason": "; ".join(review_result.get("reasons") or []),
                       "note": "评审闭环差异超阈值/无法量化：不写 manifest、"
                               "转人工复核；明细见 %s"
                               % (out_dir / "review.json")})
                return 1
        report_lines += ["", "## 历史"] + ["- %s" % h for h in history]
        if not validation["ok"]:
            report_lines += ["", "## 补丁即时校验（有告警，交付方需知悉）"] + [
                "- [%s] %s" % (i["code"], i["detail"])
                for i in validation["issues"]]
        (out_dir / "task-report.md").write_text(
            "\n".join(report_lines) + "\n", encoding="utf-8", newline="\n")
        # 精简候选列表写入 manifest（不含补丁文本，只保留排序元数据）
        cand_meta = [{k: v for k, v in c.items() if k != "patch_text"}
                     for c in cands]
        manifest_obj = {
            "engine": "agent", "repo": str(repo.resolve()), "task": task,
            "rounds": state.data["round"], "edits": state.data["edits_applied"],
            "tests": state.data["tests"],
            "test_scope": state.data.get("test_scope", ""),
            "test_engine": state.data.get("test_engine", ""),
            "elapsed_sec": state.elapsed_now(),
            "patch": "edits.patch" if patch_text else "",
            "patch_validation": validation,
            "selected_source": selected_source,
            "rank": rank_mode,
            "candidates": cand_meta,
        }
        if ws_info is not None:
            manifest_obj["workspace"] = ws_info
        if review_result is not None:
            manifest_obj["review"] = {
                "decision": review_result.get("decision"),
                "threshold": float(argv.review_threshold),
                "metrics": review_result.get("metrics") or {},
                "external_status": review_result.get("external_status") or [],
                "coverage": review_result.get("coverage"),
                "reasons": review_result.get("reasons") or [],
                "file": "review.json",
            }
        if phases_mode:
            # resolved 只有 verify 子代理 + 机械测试双绿才为真（4.1 裁决口径）
            manifest_obj["resolved"] = bool(ph.resolved)
            manifest_obj["phases"] = ph.summary()
        (out_dir / "task-manifest.json").write_text(
            json.dumps(manifest_obj, ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
        state.save()
        done_obj = {"ok": True, "state": "DONE",
                    "patch": str(out_dir / "edits.patch") if patch_text else "",
                    "tests": state.data["tests"],
                    "rounds": state.data["round"],
                    "edits": state.data["edits_applied"],
                    "patch_validation": validation,
                    "note": "补丁产出；落盘走修复链（工单/批准书/五道闸）"
                            + ("" if validation["ok"] else
                               "（补丁即时校验有告警，见 patch_validation）")}
        if phases_mode:
            done_obj["resolved"] = bool(ph.resolved)
            done_obj["phases"] = ph.summary()
        if ws_info is not None:
            done_obj["workspace"] = ws_info
        if review_result is not None:
            done_obj["review"] = {
                "decision": review_result.get("decision"),
                "threshold": float(argv.review_threshold),
                "metrics": review_result.get("metrics") or {},
                "file": "review.json",
            }
        _emit(done_obj)
        return 0
    finally:
        # 仅在已收束（manifest 落盘）时清理 worktree；WAIT_HOST_LLM 暂停
        # 必须保留（编辑成果在里面，--resume 依赖它续跑）
        if worktree.is_dir() and (out_dir / "task-manifest.json").is_file():
            if ws is not None:
                try:
                    ws.close()
                except WorkspaceError:
                    pass
            else:
                _git(repo, ["worktree", "remove", "--force", str(worktree)])
