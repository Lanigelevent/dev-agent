#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_doc_drift_coverage.py — 行为覆盖问「扫 tests/ 全目录」的反向验证。

背景（v1.24.0 实踩 + 改进候选落地）：doc-drift 行为覆盖问曾只读
test_scripts 单文件，把「已被独立测试文件覆盖的脚本」误报为未覆盖。
本用例用最小假仓双向锁定：独立文件覆盖→过；零覆盖→红。
"""
import json
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import run

ROOT = Path(__file__).resolve().parents[1]
DOC_DRIFT = ROOT / "skills" / "self-iteration" / "scripts" / "doc-drift.py"


def _fake_repo(tmp, covered):
    root = Path(tmp)
    (root / "AGENTS.md").write_text(
        "## 脚本清单\n| demo | foo.py | 演示 | 主线 |\n", encoding="utf-8",
        newline="\n")
    (root / "BASELINE.md").write_text("# B\n", encoding="utf-8", newline="\n")
    (root / "agent.json").write_text('{"args": {}}', encoding="utf-8",
                                     newline="\n")
    skill = root / "skills" / "demo" / "scripts"
    skill.mkdir(parents=True)
    (skill / "foo.py").write_text(
        '"""demo.\n\n用法:\n    py foo.py\n\n退出码:\n    0 = 成功\n"""\n',
        encoding="utf-8", newline="\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    if covered:
        (tests_dir / "test_foo.py").write_text(
            "FOO = 'foo.py'\n", encoding="utf-8", newline="\n")
    return root


class TestDocDriftCoverage(unittest.TestCase):

    def test_covered_by_standalone_test_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp, covered=True)
            rc, data, _, _ = run(DOC_DRIFT, "--root", str(root))
            q4 = next(q for q in data["questions"] if q["id"] == 4)
            self.assertEqual(q4["status"], "ok",
                             "独立测试文件覆盖必须算覆盖（旧单文件口径会误报）")

    def test_uncovered_script_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _fake_repo(tmp, covered=False)
            rc, data, _, _ = run(DOC_DRIFT, "--root", str(root))
            self.assertEqual(rc, 1)
            q4 = next(q for q in data["questions"] if q["id"] == 4)
            self.assertEqual(q4["status"], "fail")
            self.assertIn("foo.py", q4["evidence"])


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
