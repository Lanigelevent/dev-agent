# -*- coding: utf-8 -*-
"""tests/test_scripts_mutation_sampler.py — mutation-sampler.py 契约（round-144）。

覆盖：位点计数确定性、单点翻转正确性（其余位点保持原样）、越界返回 None、
恢复保证（finally 后原文件逐字节一致）、killed/survived 判定（自测模块+测试对）。
反向验证（红线 6）：test_restore_guarantee 确认变异永不残留。
"""
import importlib.util
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "mutation-sampler.py"


def _load():
    spec = importlib.util.spec_from_file_location("mut_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SAMPLE = (
    "def f(a, b):\n"
    "    if a == b and a is True:\n"
    "        return 1\n"
    "    return 0\n"
)


class MutationSamplerTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="mut-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def test_count_sites_deterministic(self):
        n1 = self.mod.count_sites(SAMPLE)
        n2 = self.mod.count_sites(SAMPLE)
        self.assertEqual(n1, n2)
        self.assertGreaterEqual(n1, 4)

    def test_generate_mutant_single_site(self):
        gen = self.mod.generate_mutant(SAMPLE, 0)
        self.assertIsNotNone(gen)
        lineno, kind, mutated = gen
        self.assertIn("比较翻转", kind)
        self.assertIn("!=", mutated)
        self.assertIn(" and ", mutated)
        gen1 = self.mod.generate_mutant(SAMPLE, 1)
        # 位点序由 AST 遍历序决定（实测：site1 = True→False 常量翻转）；
        # 契约只断言「单点性」：与原文件不同、且其余位点未被翻转。
        self.assertNotEqual(gen1[2], SAMPLE)
        self.assertIn("a is False", gen1[2])
        self.assertIn(" == ", gen1[2])
        self.assertIsNone(self.mod.generate_mutant(SAMPLE, 9999))

    def test_restore_guarantee(self):
        target = self.tmp / "mod_target.py"
        target.write_text(SAMPLE, encoding="utf-8")
        tests = self.tmp / "test_dummy.py"
        tests.write_text("def test_noop():\n    assert True\n",
                         encoding="utf-8")
        rc, out = self._invoke(["run", "--target", str(target),
                                "--tests", str(tests),
                                "--max-mutants", "2"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), SAMPLE)

    def test_killed_detection(self):
        target = self.tmp / "mod_k.py"
        target.write_text(SAMPLE, encoding="utf-8")
        tests = self.tmp / "test_k.py"
        tests.write_text(
            "from mod_k import f\n\n\n"
            "def test_eq():\n"
            "    assert f(2, 2) == 1\n",
            encoding="utf-8")
        rc, out = self._invoke(["run", "--target", str(target),
                                "--tests", str(tests),
                                "--max-mutants", "1"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["killed"], 1)
        self.assertEqual(d["survived"], 0)

    def test_missing_target_returns_2(self):
        rc, out = self._invoke(["run", "--target", str(self.tmp / "no.py"),
                                "--tests", str(self.tmp / "no_test.py")])
        d = json.loads(out)
        self.assertEqual(rc, 2)


    def _invoke(self, argv):
        old = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["mutation-sampler.py"] + argv
            with contextlib.redirect_stdout(out):
                rc = self.mod.main()
        finally:
            sys.argv = old
        return rc, out.getvalue()
