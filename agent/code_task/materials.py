#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 材料装配：稳定前缀 + 历史压缩 + 记忆 few-shot。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import json
import os
import subprocess
from agent.repo_map import (build_map, render_material, extract_keywords, rank_candidates, render_candidates)  # noqa: E402


PROBE_FIRST_NOTE = (
    "\n## 建议姿势：先探针后编辑\n"
    "出第一个 edit 之前，先用 probe 观测怀疑对象的状态，看到证据再动手——"
    "根因靠观测确认，不靠猜。"
)


PROBE_TEMPLATE = (
    "\n## 行为探针（本任务已授权 probe）\n"
    "报错行只给症状，状态类缺陷要看对象状态才定位得到。怀疑此类问题时先发：\n"
    '  {"action":"probe","code":"from pkg.mod import X; o = X(...); '
    "print(sorted(vars(o))); print([len(v) for v in o._verts])\"}\n"
    "探针在当前工作区执行（PYTHONPATH 指向工作区根），输出截断 2000 字、"
    "超时 60 秒；先看状态，再出 edit。"
)


PROBE_DOCKER_NOTE = (
    "探针改在 Docker 容器内执行（镜像 %s）：工作区只读挂载到 /testbed，"
    "Python 环境用镜像自带的（与官方评测同一环境）；本地 import 不了的仓库"
    "也应照常发探针，先看容器内状态，再出 edit。\n"
)


def _repair_plan_note(repo, max_chars=600, plans_path=None):
    """同仓库家族的蒸馏修复计划（round-34，升级计划阶段1-A，借 ConRAD）。

    数据来自 retro/repair-plans.json（plan-distill.py 从已 resolved 实例的
    补丁与 manifest 蒸馏，规则：未过实例不进原料）。命中仓库家族才附带；
    只读参考——它说「这类仓库的修复通常长什么样」，不说「这次该怎么修」。
    """
    if plans_path is None:
        plans_path = (Path(__file__).resolve().parent.parent
                      / "retro" / "repair-plans.json")
    try:
        data = json.loads(plans_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    plans = data.get("plans") or {}
    repo_str = str(repo).replace("\\", "/").lower()
    hit = None
    for name in plans:
        if name.lower() in repo_str:
            hit = name
            break
    if not hit:
        return ""
    p = plans[hit]
    tops = "、".join("%s×%d" % (k, n) for k, n in (p.get("top_file_prefixes") or [])[:3])
    parts = ["## 修复计划蒸馏（本仓库家族 %d 例已 resolved 修复的形状，仅供参考）"
             % len(p.get("instances") or [])]
    if tops:
        parts.append("高频触及位置：%s" % tops)
    if p.get("added_lines_minmax"):
        parts.append("补丁规模（新增行）：%s–%s" % tuple(p["added_lines_minmax"]))
    if p.get("rounds_minmax"):
        parts.append("收敛轮数：%s–%s" % tuple(p["rounds_minmax"]))
    return "\n".join(parts)[:max_chars]


def _material_prefix(repo, task, max_chars, candidates=None,
                     allow_probe=False, probe_docker="", repo_map=None):
    """装配材料的稳定前缀（不随轮次变化）：任务 → 候选 → 仓库地图 → 探针说明 → 修复计划。

    前缀在循环外计算一次，每轮只拼动态后缀（history），让 API prompt caching
    命中稳定前缀（TokenPilot 实测前缀稳定可提升缓存命中率 38.7%→79.2%）。
    repo_map 可由调用方传入复用（同一任务只扫一次仓库）。
    """
    if repo_map is None:
        repo_map = build_map(repo)
    parts = ["## 任务\n%s" % task, ""]
    if candidates is None:
        candidates = rank_candidates(repo_map, extract_keywords(task))
    if candidates:
        parts.append(render_candidates(candidates))
    parts.append(render_material(repo_map, max_chars))
    if allow_probe:
        parts.append(PROBE_FIRST_NOTE)
        parts.append(PROBE_TEMPLATE)
        if probe_docker:
            parts.append(PROBE_DOCKER_NOTE % probe_docker)
    plan_note = _repair_plan_note(repo)
    if plan_note:
        parts += ["", plan_note]
    return "\n".join(parts)


def _material_suffix(history):
    """装配材料的动态后缀（随轮次变化）：历史。

    从 history 取最近 12 条，加标题分隔符——与稳定前缀拼接时，稳定前缀在
    前面、动态后缀在后面，API prompt caching 只需命中前面的稳定部分。
    """
    if not history:
        return ""
    parts = ["", "## 历史（读文件与上轮观察）"]
    parts += ["- %s" % h for h in history[-12:]]
    return "\n".join(parts)


MAX_INLINE_CHARS = 20000


MAX_INLINE_LINES = 500


COMPRESS_TRIGGER_CHARS = 280000 * 4


KEEP_RECENT_ENTRIES = 12


def _compress_history(history):
    """当 history 总字符数超过阈值时，旧条目截断为首行摘要。

    确定性压缩（不调 LLM）：保留最近 KEEP_RECENT_ENTRIES 条原文，更旧的
    条目截断为首行 100 字符 + "..."，并在开头插入压缩标记。参考 LongCodeBench
    的拐点数据（256K 后编程能力崩塌）与 Novel Memory Forgetting Techniques
    的发现（无控累积性能 0.455→0.05）。
    """
    total = sum(len(h) for h in history)
    if total <= COMPRESS_TRIGGER_CHARS or len(history) <= KEEP_RECENT_ENTRIES:
        return history
    keep = KEEP_RECENT_ENTRIES
    old_count = len(history) - keep
    compressed = ["[已压缩 %d 条旧历史，仅保留首行]" % old_count]
    for i, h in enumerate(history):
        if i >= len(history) - keep:
            compressed.append(h)
        else:
            first_line = h.split("\n", 1)[0][:100]
            compressed.append(first_line + ("..." if len(h) > 100 else ""))
    return compressed


def _truncate_for_history(text, out_dir, round_num, step):
    """当输出超过阈值时写入临时文件，返回截断版 + 文件路径引用。

    参考 arXiv:2603.20432 的「外置而非压缩」策略：大输出写文件让 Agent 用
    工具读取，不占上下文窗口、不触发压缩、天然缓存友好。
    """
    if not text or (len(text) <= MAX_INLINE_CHARS
                    and len(text.splitlines()) <= MAX_INLINE_LINES):
        return text
    tool_dir = Path(out_dir) / "tool-outputs"
    tool_dir.mkdir(parents=True, exist_ok=True)
    fname = "r%d_%s.txt" % (round_num, step)
    fpath = tool_dir / fname
    fpath.write_text(text, encoding="utf-8", errors="replace")
    lines = text.splitlines()
    head = "\n".join(lines[:50])
    return "%s\n...完整输出见 %s" % (head, fpath)


def _material(repo, task, history, max_chars, candidates=None,
              allow_probe=False, probe_docker="", memory_file=None):
    """装配 LLM 材料：稳定前缀 + 动态后缀（history）+ 记忆检索 few-shot。

    记忆检索只在显式给出 memory_file 时执行（默认关闭）；返回纯文本，
    few-shot 注入上限 2000 字符。
    """
    prefix = _material_prefix(repo, task, max_chars, candidates,
                              allow_probe, probe_docker)
    retro_section, _hits = _retro_few_shot(task, memory_file,
                                           max_injection=2000)
    suffix = _material_suffix(history)
    parts = [prefix]
    if retro_section:
        parts.append(retro_section)
    if suffix:
        parts.append(suffix)
    return "\n".join(parts)


def _retro_few_shot(task, memory_file=None, max_injection=2000):
    """从记忆 JSONL 检索相似案例，返回 (few-shot 文本段, 命中数)。

    记忆路径取参数或环境变量 CRA_MEMORY_FILE；为空或缺文件时返回 ("", 0)。
    """
    path = memory_file or os.environ.get("CRA_MEMORY_FILE", "")
    if not path:
        return "", 0
    try:
        memory_path = Path(path)
        if not memory_path.exists():
            return "", 0
        retrieval_script = (AGENT_ROOT / "skills" / "retro" / "scripts" /
                            "memory_retrieval.py")
        if not retrieval_script.exists():
            return "", 0
        result = subprocess.run(
            [sys.executable, str(retrieval_script),
             "--memory", str(memory_path),
             "--query", task[:200],
             "--top-k", "3",
             "--max-chars", str(max_injection)],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace")
        if result.returncode != 0:
            return "", 0
        data = json.loads(result.stdout or "{}")
        hits = data.get("hits", [])
        if not hits:
            return "", 0
        lines = ["", "## 历史相似案例（供参考，非强制）"]
        for hit in hits:
            cid = hit.get("id", "?")
            score = hit.get("score", 0)
            snippet = hit.get("snippet", "")[:150]
            task_ref = hit.get("task", "")[:60]
            fc = hit.get("failure_category", "")
            parts_fc = " [失败类型: %s]" % fc if fc else ""
            lines.append("- [案例 #%s 相似度 %.2f]%s %s" % (
                cid, score, parts_fc, snippet))
            if task_ref:
                lines.append("  任务: %s" % task_ref)
        return "\n".join(lines), len(hits)
    except Exception:
        return "", 0
