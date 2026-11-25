#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_tmpspace.py — 临时快照自建自删生命周期契约（round-30 检查单第 12 项）。

本机 `%TEMP%` 下留了上千个 `cra-tests-*`：夹具只在**正常收尾**时删，Ctrl-C / 崩溃 /
超时任何一种中断都把目录永久留下，且没有任何路径回头认领。这里锚的是新绑定关系
「谁建的谁认领」：带归属标记才谈回收，回收只挑超龄的，没标记的一律不碰。
"""

import json
import tempfile
import time
import unittest
from pathlib import Path

import tmpspace


def _root(case):
    """每个用例一个独立临时根，收尾即删（本模块自己也得遵守自建自删）。"""
    root = Path(tempfile.mkdtemp(prefix="tmpspace-case-"))
    case.addCleanup(tmpspace._rmtree, root)
    return root


class TestTmpSpace(unittest.TestCase):
    def test_create_writes_owner_marker(self):
        root = _root(self)
        path = tmpspace.create(prefix="cra-tests-", root=root)
        self.assertTrue((path / tmpspace.MARKER).is_file())
        owner = json.loads((path / tmpspace.MARKER).read_text(encoding="utf-8"))
        self.assertEqual(owner["pid"], tmpspace._marker_payload()["pid"])
        self.assertIn("created", owner)
        removed, _ = tmpspace.release(path)
        self.assertTrue(removed, "release 说删了却没删=静默失败，正是这批残留的成因")
        self.assertFalse(path.exists())

    def test_release_is_idempotent(self):
        root = _root(self)
        path = tmpspace.create(prefix="cra-tests-", root=root)
        self.assertTrue(tmpspace.release(path)[0])
        # 已经被别处删掉：仍然算成功，不许抛
        self.assertTrue(tmpspace.release(path)[0])

    def test_abnormal_exit_still_removes(self):
        """中断收尾也要删：跑次崩在半路时，atexit 是唯一的认领者。

        这批残留的成因正是「只有正常 tearDown 才删」——这里用子进程抛未捕获异常
        模拟中断，断言临时根里什么都不剩。
        """
        import subprocess
        import sys
        root = _root(self)
        tests_dir = str(Path(__file__).resolve().parent)
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "import tmpspace\n"
            "p = tmpspace.create(prefix='cra-tests-', root=%r)\n"
            "print(p)\n"
            "raise RuntimeError('模拟跑次中断')\n"
            % (tests_dir, str(root)))
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(proc.returncode, 0, "用例本身要求子进程异常退出")
        self.assertIn("RuntimeError", proc.stderr)
        left = sorted(p.name for p in root.iterdir())
        self.assertEqual(left, [],
                         "异常退出后残留 = %s（中断的跑次不该往临时根里留东西）" % left)

    def test_release_removes_readonly_tree(self):
        """Windows 上 git 对象是只读的；rmtree(ignore_errors) 会静默留下半棵树。"""
        import os
        import stat
        root = _root(self)
        path = tmpspace.create(prefix="cra-tests-", root=root)
        locked = path / ".git" / "objects"
        locked.mkdir(parents=True)
        f = locked / "ab" / "cdef"
        f.parent.mkdir()
        f.write_text("x", encoding="utf-8")
        os.chmod(f, stat.S_IREAD)
        removed, _ = tmpspace.release(path)
        self.assertTrue(removed)
        self.assertFalse(path.exists(), "只读文件必须被清掉位再删，不能静默跳过")

    def test_sweep_skips_unmarked_directories(self):
        """反向验证：没有归属标记的目录一律不碰（历史遗留归人工决定）。"""
        root = _root(self)
        legacy = root / "cra-tests-legacy000"
        legacy.mkdir()
        (legacy / "keep.txt").write_text("x", encoding="utf-8")
        result = tmpspace.sweep(root=root, prefixes=("cra-tests-",),
                                older_than_seconds=0, apply=True)
        self.assertIn(legacy.name, result["skipped_unmarked"])
        self.assertEqual(result["removed"], [])
        self.assertTrue(legacy.is_dir(), "无标记就删=替用户做运维决定")

    def test_sweep_skips_young_and_other_prefixes(self):
        root = _root(self)
        fresh = tmpspace.create(prefix="cra-tests-", root=root)
        old = tmpspace.create(prefix="cra-tests-", root=root)
        (old / tmpspace.MARKER).write_text(json.dumps(
            {"pid": 1, "run": "then", "created": time.time() - 999999}),
            encoding="utf-8")
        other = tmpspace.create(prefix="repair-", root=root)
        (other / tmpspace.MARKER).write_text(json.dumps(
            {"pid": 1, "run": "then", "created": time.time() - 999999}),
            encoding="utf-8")
        result = tmpspace.sweep(root=root, prefixes=("cra-tests-",),
                                older_than_seconds=3600, apply=True)
        self.assertEqual(result["removed"], [old.name])
        self.assertIn(fresh.name, result["skipped_young"])
        self.assertTrue(fresh.is_dir(), "还在跑的并发跑次不能被删")
        self.assertTrue(other.is_dir(), "前缀不在清单里就不该被动")

    def test_sweep_dry_run_does_not_touch_disk(self):
        root = _root(self)
        old = tmpspace.create(prefix="cra-tests-", root=root)
        (old / tmpspace.MARKER).write_text(json.dumps(
            {"pid": 1, "run": "then", "created": time.time() - 999999}),
            encoding="utf-8")
        result = tmpspace.sweep(root=root, prefixes=("cra-tests-",),
                                older_than_seconds=3600, apply=False)
        self.assertEqual(result["removed"], [old.name])
        self.assertTrue(result["dry_run"])
        self.assertTrue(old.is_dir(), "dry-run 只是报表，不许动盘")


class TestSuiteWiring(unittest.TestCase):
    """夹具必须真的走 tmpspace，否则上面的契约都只是在测一个没人用的模块。"""

    def test_fixture_tmp_is_marker_owned(self):
        import _scripts_common as test_scripts
        test_scripts.ensure_fixture()
        self.addCleanup(lambda: None)  # 共享单例不在此释放（tmpspace atexit 兜底）
        tmp = test_scripts.FIXTURE["tmp"]
        self.assertTrue((tmp / tmpspace.MARKER).is_file(),
                        "全量夹具没挂归属标记=中断后又是一个无人认领的残留")
        self.assertEqual(tmpspace.owner_of(tmp)["run"], tmpspace.RUN_ID)

    def test_sweep_script_reports_without_deleting(self):
        import subprocess
        import sys
        script = Path(__file__).resolve().parents[1] / "scripts" / "sweep-test-tmp.py"
        self.assertTrue(script.is_file(), script)
        root = _root(self)
        old = tmpspace.create(prefix="cra-tests-", root=root)
        (old / tmpspace.MARKER).write_text(json.dumps(
            {"pid": 1, "run": "then", "created": time.time() - 999999}),
            encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, proc.stderr[:300])
        data = json.loads(proc.stdout)
        self.assertTrue(data["dry_run"], "缺省必须是只看不动盘")
        self.assertEqual(data["removable"], [old.name])
        self.assertTrue(old.is_dir())
        # 真删要明说 --apply
        proc = subprocess.run(
            [sys.executable, str(script), "--root", str(root), "--apply"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        data = json.loads(proc.stdout)
        self.assertEqual(data["removed"], [old.name])
        self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
