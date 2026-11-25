#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""候选补丁存档/收敛排序与记忆 JSONL 写入。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import json
import os


CAND_TIER_PASS = 0       # 测试通过：最高优先


CAND_TIER_FAIL = 1       # 测试失败但有补丁


CAND_TIER_SKIP = 2       # 测试跳过（无可用测试引擎或无测试文件）


CAND_TIER_EMPTY = 3      # 无补丁：最低


def _save_candidate(out_dir, round_num, patch_text, tests, test_detail,
                    edits_applied, validation, broken, files):
    """Save a patch snapshot to candidates/ for ranking at convergence.

    Each successful edit round produces a snapshot; convergence picks the
    best by test outcome + validation + minimal-patch principle.
    Returns the snapshot path (or None if patch is empty and round 0).
    """
    cdir = out_dir / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    has_patch = bool((patch_text or "").strip())
    cand = {
        "round": round_num,
        "tests": tests,
        "test_detail": test_detail,
        "edits_applied": edits_applied,
        "patch_validation": validation,
        "selfcheck_broken": [f for f, _ in (broken or [])],
        "files": files or [],
        "patch_chars": len(patch_text or ""),
        "has_patch": has_patch,
        "patch_text": patch_text or "",
    }
    path = cdir / ("candidate-%02d.json" % round_num)
    path.write_text(json.dumps(cand, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
    return path


def _write_memory(out_dir, repo, task, files, edit_summary,
                  rule_codes, result, failure_category, trace_file,
                  retrieval_count=0, memory_file=None, round_num=0):
    """步骤 1.5：将本轮编码经验写入记忆 JSONL（默认关闭）。

    记忆路径取 --memory-file 或环境变量 CRA_MEMORY_FILE；两者都为空时不写。
    默认关闭的理由：编码循环在测试与临时任务里高频运行，若默认写仓库内
    retro/agent-memory.jsonl，跑一次套件就会把临时仓库路径灌进长期记忆。

    条目字段：id / timestamp / task / repo / files / edit_format /
    rule_codes / result / failure_category / trace_file / retrieval_count
    """
    path = memory_file or os.environ.get("CRA_MEMORY_FILE", "")
    if not path:
        return
    try:
        memory_file = Path(path)
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        entry = {
            "id": "mem-%s-r%02d" % (
                datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                round_num),
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S"),
            "task": task[:200],
            "repo": str(repo),
            "files": files or [],
            "edit_format": edit_summary[:200],
            "rule_codes": rule_codes or [],
            "result": result,
            "failure_category": failure_category or "",
            "trace_file": str(trace_file) if trace_file else "",
            "retrieval_count": retrieval_count,
        }
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 记忆写入失败不阻塞编码循环


def _rank_candidates(out_dir):
    """Rank patch snapshots by test outcome + validation + minimal-patch.

    Returns (sorted_list, best_candidate_or_None). Ranking is deterministic
    and reproducible (provenance baked into each candidate's rank_reason).
    """
    cdir = out_dir / "candidates"
    if not cdir.is_dir():
        return [], None
    cands = []
    for path in sorted(cdir.glob("candidate-*.json")):
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cands.append(c)
    if not cands:
        return [], None

    def _tier(c):
        has_patch = bool(c.get("has_patch") or
                          (c.get("patch_text") or "").strip())
        if not has_patch:
            return CAND_TIER_EMPTY
        tests = c.get("tests", "skip")
        if tests == "pass":
            return CAND_TIER_PASS
        if tests == "fail":
            return CAND_TIER_FAIL
        return CAND_TIER_SKIP

    def _sort_key(c):
        tier = _tier(c)
        val_ok = 1 if c.get("patch_validation", {}).get("ok", True) else 0
        size = c.get("patch_chars", 0)
        return (tier, 1 - val_ok, size)

    cands.sort(key=_sort_key)
    for i, c in enumerate(cands):
        c["rank"] = i
        c["rank_reason"] = {
            "tier": _tier(c),
            "tier_name": ("pass", "fail", "skip", "empty")[_tier(c)],
            "validation_ok": c.get("patch_validation", {}).get("ok", True),
            "patch_chars": c.get("patch_chars", 0),
        }
    best = cands[0] if cands[0].get("has_patch") else None
    return cands, best
