#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shadow_git.py — 编码循环影子检查点（AB-11，r202；Cline 影子 git 方案复用）。

用途：
    本地 worktree 的持久多检查点：fix 每轮开始对全树快照（独立 shadow
    git 目录，与用户 .git 解耦），校验失败/评审退回/多轮失败时可一键
    还原到任意轮起点。与 tools._snapshot_paths/_restore_paths 互补：
    后者=本轮触及文件的内存级精确回滚；本模块=全树持久历史+审计。

    方案出处：Cline 影子 git（独立影子仓库解耦用户 git）与落地指南 3
    （写文件前影子 commit）；`git --git-dir` + `--work-tree` 实现。

用法示例（code-task.py 集成形态）：
    from agent.shadow_git import ShadowGit
    sg = ShadowGit(worktree)          # 缺省 shadow 目录 <worktree>/.git-shadow
    sg.snapshot("round-1")            # 每轮开始
    ...
    sg.rollback("round-1")            # 还原到该轮起点（含清理新增文件）

退出码：类方法异常经 _git 捕获返回 ok=False，不抛（观测/检查点层失败
只告警不拖垮编码循环——与 trace.py 同纪律）。
"""
import subprocess
import sys
from pathlib import Path


class ShadowGit:
    """影子检查点：独立 git 目录对本地 worktree 做持久多检查点。"""

    def __init__(self, worktree, shadow_dir=None):
        self.worktree = Path(worktree).resolve()
        # 缺省放 worktree 兄弟目录（不进用户仓——放里面会以 ?? 目录污染
        # 用户 git status，解耦承诺自破）；code-task 场景 = out_dir/wt-shadow。
        self.shadow = Path(shadow_dir) if shadow_dir else \
            self.worktree.parent / (self.worktree.name + "-shadow")
        self._available = None  # 惰性探测 git 可用性

    def _git(self, *args):
        import os
        # r203 上游补研结论：旗标式 --git-dir/--work-tree 在嵌套子进程上下文
        # （code-task → git）会被 bare 判定——git 自身 worktree 机制同款用
        # env 传递（剥继承 GIT_* 再显式设），消除旗标/环境交互面。
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("GIT_")}
        env["GIT_DIR"] = str(self.shadow / ".git")
        env["GIT_WORK_TREE"] = str(self.worktree)
        return subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, env=env)


    def _ensure_init(self):
        if self.shadow.is_dir() and (self.shadow / ".git" / "HEAD").exists():
            return {"ok": True}
        try:
            self.shadow.mkdir(parents=True, exist_ok=True)
            proc = self._git("init", "-q")
            if proc.returncode != 0:
                return {"ok": False, "error": proc.stderr or "git init 失败"}
            # r202 co-run 实弹防护：显式钉非 bare + work-tree
            # （"must be run in a work tree" 只在 bare 判定时出现）。
            self._git("config", "core.bare", "false")
            self._git("config", "core.worktree", str(self.worktree))
            self._git("config", "user.email", "shadow@local")
            self._git("config", "user.name", "shadow-checkpoint")
            self._available = True
            return {"ok": True}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def available(self):
        """git 可用且影子仓库已初始化。"""
        if self._available is None:
            self._available = self.shadow.is_dir() and \
                (self.shadow / ".git" / "HEAD").exists()
        return bool(self._available)

    def snapshot(self, label):
        """全树快照（-A 含新增/删除）；返回 {"ok", "sha", "label"}。"""
        init = self._ensure_init()
        if not init.get("ok"):
            return init
        import os
        proc = self._git("add", "-A")
        if proc.returncode != 0:
            diag = self._git("rev-parse", "--is-bare-repository")
            return {"ok": False,
                    "error": "add: %s | is_bare=%s | GIT_DIR=%r GIT_WORK_TREE=%r"
                    % ((proc.stderr or "git add 失败")[:100],
                       (diag.stdout or "").strip(),
                       os.environ.get("GIT_DIR"),
                       os.environ.get("GIT_WORK_TREE"))}
        proc = self._git("commit", "-q", "--allow-empty", "-m", label)
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr or "git commit 失败"}
        sha = self._git("rev-parse", "--short", "HEAD")
        return {"ok": True, "label": label,
                "sha": (sha.stdout or "").strip()}

    def rollback(self, label):
        """还原到指定检查点（硬还原：tracked 重置 + untracked 清理）。"""
        if not self.available():
            return {"ok": False, "error": "影子仓库未初始化"}
        sha_proc = self._git("rev-list", "-n", "1", "--grep", label, "HEAD")
        sha = (sha_proc.stdout or "").strip()
        if not sha:
            return {"ok": False, "error": "检查点不存在: %s" % label}
        proc = self._git("reset", "--hard", sha)
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr or "reset 失败"}
        self._git("clean", "-fd")
        return {"ok": True, "label": label, "sha": sha}

    def checkpoints(self):
        """检查点清单（label+sha，按时间正序）。"""
        if not self.available():
            return []
        proc = self._git("log", "--reverse", "--pretty=%h %s")
        out = []
        for line in (proc.stdout or "").splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                out.append({"sha": parts[0], "label": parts[1]})
        return out
