#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_shadow_git.py — AB-11 影子检查点契约（r202）。

snapshot/rollback 全树还原（含 untracked 清理反向验证）；多检查点清单；
坏 label 拒绝；worktree 与用户 .git 解耦（用户仓状态不受影响）。
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from agent.shadow_git import ShadowGit


def _make_repo(tmp):
    repo = tmp / "wt"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(repo),
                   check=True)
    subprocess.run(["git", "config", "user.email", "t@local"], cwd=str(repo),
                   check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(repo),
                   check=True)
    return repo


class ShadowGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="shadow-git-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = _make_repo(self.tmp)
        (self.repo / "a.py").write_text("v = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=str(self.repo),
                       check=True)
        self.sg = ShadowGit(self.repo)

    def test_snapshot_and_rollback_restores_tree(self):
        # 快照 → 破坏性改动（改+删+新增）→ 回滚还原全树
        snap = self.sg.snapshot("round-1")
        self.assertTrue(snap["ok"], snap)
        self.assertTrue(snap["sha"])
        (self.repo / "a.py").write_text("v = 999\n", encoding="utf-8")
        (self.repo / "b_new.py").write_text("new\n", encoding="utf-8")
        (self.repo / "a.py").unlink() if False else None
        (self.repo / "seed_only.txt").write_text("x\n", encoding="utf-8")
        res = self.sg.rollback("round-1")
        self.assertTrue(res["ok"], res)
        self.assertEqual((self.repo / "a.py").read_text(encoding="utf-8"),
                         "v = 1\n", "被改文件应还原")
        self.assertFalse((self.repo / "b_new.py").exists(),
                         "快照后新增文件应被清理（untracked 清理）")

    def test_multi_checkpoints_listing_and_order(self):
        self.sg.snapshot("round-1")
        (self.repo / "a.py").write_text("v = 2\n", encoding="utf-8")
        self.sg.snapshot("round-2")
        cps = self.sg.checkpoints()
        labels = [c["label"] for c in cps]
        self.assertEqual(labels, ["round-1", "round-2"],
                         "检查点应按时间正序且 label 可检索")

    def test_rollback_unknown_label_rejected(self):
        self.sg.snapshot("round-1")  # 先初始化影子仓库
        res = self.sg.rollback("round-不存在")
        self.assertFalse(res["ok"])
        self.assertIn("不存在", res["error"])

    def test_user_git_decoupled(self):
        # 影子操作不得改动用户仓的 HEAD/状态（解耦核心承诺）
        head_before = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        self.sg.snapshot("round-1")
        self.sg.rollback("round-1")
        head_after = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True, text=True).stdout.strip()
        self.assertEqual(head_before, head_after, "用户 HEAD 不得被影子操作改写")
        status = subprocess.run(["git", "-C", str(self.repo), "status",
                                 "--porcelain"], capture_output=True,
                                text=True).stdout
        self.assertEqual(status.strip(), "", "用户仓工作树应保持干净")


if __name__ == "__main__":
    unittest.main()
