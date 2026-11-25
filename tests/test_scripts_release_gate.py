# -*- coding: utf-8 -*-
"""tests/test_scripts_release_gate.py — release-gate._parse_suite 契约（round-152，F1 测试债清偿）。

覆盖：unittest 格式解析、pytest 格式解析（xdist 路径，r141 收官补丁的红线 6 反向验证）、
pytest 红/失败判绿语义、未知格式返回不可信、ran 计数含 skipped（与 unittest 发现数对齐）。
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "release-gate.py"

UNITTEST_GREEN = "Ran 739 tests in 443.20s\n\nOK (skipped=1)\n"
UNITTEST_FAILED = "Ran 739 tests in 10.00s\n\nFAILED (failures=2, skipped=1)\n"
PYTEST_GREEN = "738 passed, 1 skipped in 443.20s\n"
PYTEST_RED = "700 passed, 2 failed, 1 error, 30 skipped in 500.00s\n"


def _load():
    spec = importlib.util.spec_from_file_location("rg_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ParseSuiteTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()

    def test_unittest_green(self):
        d = self.mod._parse_suite(UNITTEST_GREEN)
        self.assertTrue(d["green"])
        self.assertEqual(d["ran"], 739)
        self.assertEqual(d["skipped"], 1)
        self.assertAlmostEqual(d["duration_sec"], 443.20)

    def test_unittest_failed_not_green(self):
        d = self.mod._parse_suite(UNITTEST_FAILED)
        self.assertFalse(d["green"])

    def test_pytest_green_ran_includes_skipped(self):
        # 与 unittest 发现数对齐：738 passed + 1 skipped = 739
        d = self.mod._parse_suite(PYTEST_GREEN)
        self.assertTrue(d["green"])
        self.assertEqual(d["ran"], 739)
        self.assertEqual(d["skipped"], 1)
        self.assertAlmostEqual(d["duration_sec"], 443.20)

    def test_pytest_red_counts(self):
        d = self.mod._parse_suite(PYTEST_RED)
        self.assertFalse(d["green"])
        self.assertEqual(d["ran"], 700 + 2 + 1 + 30)

    def test_unknown_format_not_trusted(self):
        d = self.mod._parse_suite("hello world\nno markers here\n")
        self.assertFalse(d["green"])
        self.assertIsNone(d["ran"])

    def test_pytest_branch_not_shadowed_by_unittest(self):
        # 反向验证：pytest 日志不得被 unittest 分支误吞（RAN_RE 匹配
        # "Ran (\d+) tests"——pytest 摘要无该行，双分支互斥可判）
        self.assertIsNone(self.mod.RAN_RE.search(PYTEST_GREEN))
        d = self.mod._parse_suite(PYTEST_GREEN)
        self.assertEqual(d["ran"], 739)


class GitStateSelfExclusionTests(unittest.TestCase):
    """r191：git_state 对闸自身 --out 证据路径自豁免——重跑场景下闸不再被
    自己的产物绊倒（r190 三次闸拦截的结构性教训）；其他脏项仍判红（反向
    验证，红线 6）。"""

    def setUp(self):
        self.mod = _load()

    def _git_repo(self):
        import shutil
        import subprocess as sp
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="rg-gitstate-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        def g(*args):
            return sp.run(["git", "-C", str(tmp)] + list(args),
                          capture_output=True, text=True)

        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@local")
        g("config", "user.name", "t")
        (tmp / "seed.txt").write_text("seed", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "seed")
        return tmp, g

    def test_out_evidence_dirty_excluded(self):
        tmp, g = self._git_repo()
        out = tmp / "reports" / "rg" / "evidence.json"
        out.parent.mkdir(parents=True)
        out.write_text('{"ok": true}', encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "track evidence")
        out.write_text('{"ok": false}', encoding="utf-8")  # 模拟重跑改写证据面
        res = self.mod.check_git_state(tmp, "1.0.0", "v1.0.0", "main",
                                       out_path=str(out))
        self.assertEqual(res["status"], "PASS", res.get("errors"))
        self.assertEqual(res["out_evidence_excluded"], 1)

    def test_other_dirty_still_fails(self):
        tmp, g = self._git_repo()
        out = tmp / "evidence.json"
        out.write_text("{}", encoding="utf-8")
        g("add", "-A")
        g("commit", "-q", "-m", "track")
        out.write_text("rewritten", encoding="utf-8")
        (tmp / "other.txt").write_text("dirty", encoding="utf-8")
        res = self.mod.check_git_state(tmp, "1.0.0", "v1.0.0", "main",
                                       out_path=str(out))
        self.assertEqual(res["status"], "FAIL")
        self.assertTrue(any("不干净" in e for e in res["errors"]),
                        res["errors"])
        self.assertEqual(res["out_evidence_excluded"], 1,
                         "out 证据被豁免，但 other.txt 仍须判红")


if __name__ == "__main__":
    unittest.main()
