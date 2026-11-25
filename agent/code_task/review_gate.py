#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审查闭环入口（token 只过环境变量；委托 agent/review_loop）。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import subprocess
from agent.review_loop import run_review, ReviewError  # noqa: E402
from agent.code_task.tools import _git


def _review_gate(repo, out_dir, patch_text, reviewers, threshold, cmds,
                 ocr_exe, self_tests="skip", self_issues=None):
    """阶段四 4.4：把**交付补丁**检出到独立 worktree 后送评审器。

    评审对象是补丁本身（候选快照可能与工作树末态不同），故重建一次干净
    检出并 apply；静态评审器在宿主侧跑，容器档的环境差异不参与本项。
    检出/应用失败一律抛 ReviewError——评审跑不了不得静默当通过。
    """
    checkout = out_dir / "review-wt"
    patch_file = out_dir / "edits.patch"
    if not patch_file.is_file():
        raise ReviewError("缺少 edits.patch，无法评审")
    if checkout.is_dir():
        _git(repo, ["worktree", "remove", "--force", str(checkout)])
    rc, _out, err = _git(repo, ["worktree", "add", "--detach", "--force",
                                str(checkout), "HEAD"])
    if rc != 0:
        raise ReviewError("评审检出失败（git worktree rc=%d）：%s"
                          % (rc, err.strip()[:200]))
    try:
        proc = subprocess.run(
            ["git", "-C", str(checkout), "apply", "--whitespace=nowarn",
             str(patch_file)], shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        if proc.returncode != 0:
            raise ReviewError("交付补丁无法在干净检出上应用：%s"
                              % (proc.stderr or "").strip()[:300])
        return run_review(checkout, patch_text, reviewers=reviewers,
                          threshold=threshold, self_tests=self_tests,
                          self_issues=self_issues, ocr_exe=ocr_exe,
                          reviewer_cmds=cmds, out_dir=out_dir)
    finally:
        _git(repo, ["worktree", "remove", "--force", str(checkout)])
        _git(repo, ["worktree", "prune"])


def _parse_review_cmds(items):
    cmds = {}
    for item in items or []:
        if "=" not in item:
            raise ReviewError("--review-cmd 需 name=command：%r" % item)
        name, command = item.split("=", 1)
        cmds[name.strip()] = command.strip()
    return cmds
