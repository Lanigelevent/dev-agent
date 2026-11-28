#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6 契约测试：变更感知测试选择器（round-235，unittest 兼容）。"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TS = ROOT / "skills" / "repair" / "scripts" / "test-select.py"


def _load():
    spec = importlib.util.spec_from_file_location("test_select", TS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSelectTests(unittest.TestCase):
    def _repo(self, root):
        root = Path(root)
        (root / "pkg").mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "pkg" / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\nMAX = 10\n", encoding="utf-8")
        (root / "pkg" / "other.py").write_text(
            "def unrelated():\n    pass\n", encoding="utf-8")
        (root / "tests" / "test_calc.py").write_text(
            "from pkg.calc import add\ndef test_a():\n    assert add(1, 2) == 3\n",
            encoding="utf-8")
        (root / "tests" / "test_other.py").write_text(
            "from pkg.other import unrelated\ndef test_b():\n    pass\n",
            encoding="utf-8")
        return root

    def test_affected_must_be_selected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td) / "repo")
            sel, chg = _load().select_tests(repo, ["pkg/calc.py"])
            self.assertTrue(any("test_calc" in s for s in sel))
            self.assertTrue(all("test_other" not in s for s in sel))
            self.assertEqual(chg, ["pkg/calc.py"])

    def test_unrelated_must_not_leak_in(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td) / "repo")
            sel, _c = _load().select_tests(repo, ["pkg/other.py"])
            self.assertTrue(any("test_other" in s for s in sel))
            self.assertTrue(all("test_calc" not in s for s in sel))

    def test_non_py_only_records(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td) / "repo")
            sel, chg = _load().select_tests(repo, ["docs/x.md"])
            self.assertEqual(sel, [])
            self.assertEqual(chg, [])

    def test_empty_changed_empty_selected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td) / "repo")
            sel, chg = _load().select_tests(repo, [])
            self.assertEqual(sel, [])
            self.assertEqual(chg, [])

    def test_cli_rc_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td) / "repo")
            r1 = subprocess.run(
                [sys.executable, str(TS), "select", "--repo", str(repo),
                 "--files", "pkg/calc.py"], capture_output=True, timeout=120)
            self.assertEqual(r1.returncode, 0)
            doc = json.loads(r1.stdout.decode("utf-8"))
            self.assertTrue(any("test_calc" in s for s in doc["selected"]))
            r2 = subprocess.run(
                [sys.executable, str(TS), "select", "--repo", str(repo)],
                capture_output=True, timeout=120)
            self.assertEqual(r2.returncode, 2)
            r3 = subprocess.run(
                [sys.executable, str(TS), "select", "--repo", str(Path(td) / "nope"),
                 "--files", "a.py"], capture_output=True, timeout=120)
            self.assertEqual(r3.returncode, 2)


if __name__ == "__main__":
    unittest.main()
