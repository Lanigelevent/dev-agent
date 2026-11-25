#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""git 操作、补丁取差、路径快照/恢复等底层工具。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import subprocess


def _worktree_diff(repo):
    """取 worktree 相对 HEAD 的完整补丁（含新建文件）。

    `git diff HEAD` 不含未跟踪文件；先把它们标记为 intent-to-add
    （`git add -A -N`），新建文件才会带上 `+++ b/...` 补丁头
    （round-46 实踩：新建 tomlkit/convert.py 未进补丁，即时校验报
    file_missing / missing_change，等于把正确的新建文件判成没改）。
    """
    _git(repo, ["add", "-A", "-N"])
    return _git(repo, ["diff", "HEAD"])


def _ws_diff(ws, worktree):
    """工作区补丁取数：三档统一接口；本地无 ws 时保持原 git 路径。"""
    if ws is not None:
        return ws.diff()
    return _worktree_diff(worktree)


def _git(repo, args):
    """跑 git 命令；返回 (rc, stdout, stderr) 三路分离。

    补丁内容只能取 stdout：git 的 CRLF/autocrlf 警告走 stderr，混入会让
    补丁不再是纯净 unified diff（round-18 实踩：edits.patch 末行是
    warning: ... LF will be replaced by CRLF）。实测 `git apply` 容忍尾部
    噪声（rc=0），故非功能性阻断；但 patch -p1 / git am / 严格评审器会判
    损坏补丁，故补丁一律只取 stdout。
    """
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _pytest_exe():
    """找可用的 pytest 解释器：当前解释器 > 全局 py。"""
    for cand in (sys.executable, "py"):
        try:
            probe = subprocess.run([cand, "-c", "import pytest"], shell=False,
                                   capture_output=True, timeout=30)
        except OSError:
            continue
        if probe.returncode == 0:
            return cand
    return None


def _snapshot_paths(worktree, rels):
    """记录编辑前的文件字节（None=不存在），供校验失败时精确回滚本轮改动。"""
    snap = {}
    root = Path(worktree)
    for rel in rels:
        rel = str(rel).replace("\\", "/")
        if not rel or ".." in rel.split("/") or rel in snap:
            continue
        target = root / rel
        try:
            snap[rel] = target.read_bytes() if target.is_file() else None
        except OSError:
            snap[rel] = None
    return snap


def _restore_paths(worktree, snap):
    """把快照里的文件恢复原字节；快照为 None 的（本轮新建）删除。

    动机（round-58 实踩）：即时校验未过时只 continue 不回滚，被拒的改动
    会留在工作树里——下一轮按基线文本出的 SEARCH 必然「未命中」，模型
    看到的补丁也仍是上一版被拒的内容。
    """
    root = Path(worktree)
    restored = 0
    for rel, data in snap.items():
        target = root / rel
        if data is None:
            if target.is_file():
                target.unlink()
                restored += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        restored += 1
    return restored
