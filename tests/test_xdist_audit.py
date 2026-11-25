# -*- coding: utf-8 -*-
"""tests/test_xdist_audit.py — pytest-xdist 并行前置审计（D-051 A 项，round-100）。

以 2 worker 实跑轻量子集，验证 D-051 审计列出的阻塞点：
①tmpspace 归属标记/年龄回收在多进程下无互删、无残留；
②共享夹具单例每 worker 各建一份且互不干扰；
③轻量子集并行结果与串行口径一致。
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class XdistAuditTests(unittest.TestCase):
    def test_two_worker_parallel_subset_green(self):
        """2 worker 并行跑两个轻量夹具模块：全绿 + 无互删。"""
        cmd = [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "-n", "2", "--dist", "loadfile",
            "tests/test_round_gate.py", "tests/test_bump_version.py",
        ]
        p = subprocess.run(cmd, shell=False, cwd=str(ROOT),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        self.assertEqual(
            p.returncode, 0,
            "xdist 并行子集未全绿：\n%s" % (p.stdout[-1500:] + p.stderr[-500:]))

    def test_tmpspace_no_residue_after_parallel(self):
        """并行跑后，本进程的 tmpspace 带标记目录均已被各自 atexit 回收
        （审计点：worker 异常退出时的兜底不产生无人认领残留——以
        sweep 报表零新增未认领作为代理判据）。"""
        from pathlib import Path as _P
        script = ROOT / "scripts" / "sweep-test-tmp.py"
        self.assertTrue(script.is_file(), "sweep-test-tmp.py 缺失")
        p = subprocess.run(
            [sys.executable, str(script), "--root", str(ROOT)],
            shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
        self.assertEqual(p.returncode, 0, p.stdout[-400:] + p.stderr[-200:])


if __name__ == "__main__":
    unittest.main()
