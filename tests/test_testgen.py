#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_testgen.py — Phase 3A：测试生成引擎契约断言。

覆盖：loop/hypothesis 两风格骨架生成并 verify 通过；未类型化函数出
skip+TODO；LLM 宿主模式（WAIT→stub 填答→幂等续跑→verify）；patch 产出
git apply 可建新文件的补丁。Pynguin 基线对照（LGPL subprocess 隔离）。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace

ROOT = Path(__file__).resolve().parents[1]
TESTGEN = ROOT / "engines" / "testgen.py"
VENV_PY = next(
    (p for p in (ROOT / ".venv" / "Scripts" / "python.exe",
                 ROOT / ".venv" / "bin" / "python") if p.is_file()),
    Path(sys.executable))
PYNGUIN = ROOT / ".venv" / "Scripts" / "pynguin.exe"

CALC_SRC = ("def add(a: int, b: int) -> int:\n"
            "    return a + b\n\n\n"
            "def greet(name: str) -> str:\n"
            "    return \"hi \" + name\n\n\n"
            "def make(opts=None):\n    return opts or {}\n\n\n"
            "def mystery(x):\n    return x\n")

LLM_TEST_CODE = ("import calc\n\n\n"
                 "def test_add_real():\n    assert calc.add(2, 3) == 5\n\n\n"
                 "def test_greet_real():\n    assert calc.greet('a') == 'hi a'\n")


class TestTestgen(unittest.TestCase):
    """skeleton 两风格 / verify / patch / llm 宿主协议。"""

    def setUp(self):
        self.tmp = tmpspace.create(prefix="testgen-t-")
        self.addCleanup(tmpspace.release, self.tmp)
        (self.tmp / "calc.py").write_text(CALC_SRC, encoding="utf-8",
                                          newline="\n")

    def _skeleton(self, style):
        out = self.tmp / ("test_gen_%s.py" % style)
        rc, data, _, _ = test_scripts.run(TESTGEN, "skeleton",
                                          "--file", self.tmp / "calc.py",
                                          "--out", out, "--style", style)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        return out

    def test_loop_style_verified(self):
        out = self._skeleton("loop")
        text = out.read_text(encoding="utf-8")
        self.assertIn("def test_add_smoke", text)
        self.assertIn("@pytest.mark.skip", text, "未类型化函数应出 skip+TODO")
        rc, data, _, _ = test_scripts.run(TESTGEN, "verify",
                                          "--file", self.tmp / "calc.py",
                                          "--test", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertTrue(data["ok"])

    def test_hypothesis_style_verified(self):
        out = self._skeleton("hypothesis")
        text = out.read_text(encoding="utf-8")
        self.assertIn("@given(a=st.integers(), b=st.integers())", text)
        rc, data, _, _ = test_scripts.run(TESTGEN, "verify",
                                          "--file", self.tmp / "calc.py",
                                          "--test", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertTrue(data["ok"])

    def test_patch_creates_new_file_via_git_apply(self):
        out = self._skeleton("loop")
        patches = self.tmp / "p"
        rc, data, _, _ = test_scripts.run(TESTGEN, "patch", "--test", out,
                                          "--rel", "tests/test_gen_calc.py",
                                          "--out", patches)
        self.assertEqual(rc, 0)
        repo = self.tmp / "repo"
        repo.mkdir()
        (repo / "calc.py").write_text(CALC_SRC, encoding="utf-8",
                                      newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "i"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        proc = subprocess.run(["git", "-C", str(repo), "apply",
                               data["patch_path"]],
                              shell=False, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr[:200])
        self.assertTrue((repo / "tests" / "test_gen_calc.py").is_file(),
                        "git apply 必须创建新文件")
        # 命名口径的锚（round-30 同类排查）：补丁名键于**整条相对路径**，
        # 不同目录的同名文件不得共用一个补丁名——取适配器自己回传的路径，
        # 不在测试里复刻命名（复刻会把「两份实现分叉」藏成绿色）。
        self.assertTrue(str(data["patch_path"]).startswith(
            str(patches / "testgen-test_gen_calc.py")),
            "补丁名应可读地带上模块名：%s" % data["patch_path"])

    def test_llm_host_mode_roundtrip(self):
        out = self.tmp / "test_llm_calc.py"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [sys.executable, str(TESTGEN), "llm",
               "--file", str(self.tmp / "calc.py"), "--out", str(out)]
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env, cwd=str(ROOT))
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
        self.assertIn("calc", prompt)
        # stub 宿主：写真测试代码（LLM 的义务是具体断言，不是冒烟）
        Path(data["llm_response"]).write_text(
            "```python\n" + LLM_TEST_CODE + "```",
            encoding="utf-8", newline="\n")
        p2 = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120,
                            env=env, cwd=str(ROOT))
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0,
                         json.dumps(data2, ensure_ascii=False)[:300])
        self.assertTrue(out.is_file())
        rc, vdata, _, _ = test_scripts.run(TESTGEN, "verify",
                                           "--file", self.tmp / "calc.py",
                                           "--test", out)
        self.assertEqual(rc, 0, "LLM 生成测试必须 verify 通过")
        self.assertIn("assert calc.add(2, 3) == 5",
                      out.read_text(encoding="utf-8"))

    def test_verify_rejects_failing_test(self):
        bad = self.tmp / "test_bad.py"
        bad.write_text("import calc\n\n\ndef test_wrong():\n"
                       "    assert calc.add(1, 1) == 3\n",
                       encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(TESTGEN, "verify",
                                          "--file", self.tmp / "calc.py",
                                          "--test", bad)
        self.assertEqual(rc, 1)
        self.assertFalse(data["ok"], "错误断言必须被 verify 拒绝")


@unittest.skipUnless(PYNGUIN.is_file(), "Pynguin 未安装（LGPL 隔离层，可选）")
class TestPynguinBaseline(unittest.TestCase):
    """Pynguin 基线对照（subprocess 隔离；仅评估，不进产品链）。"""

    def test_pynguin_generates_on_sample(self):
        tmp = tmpspace.create(prefix="pynguin-t-")
        self.addCleanup(tmpspace.release, tmp)
        (tmp / "target.py").write_text(
            "def clamp(v: int, lo: int, hi: int) -> int:\n"
            "    return max(lo, min(hi, v))\n",
            encoding="utf-8", newline="\n")
        import os as _os
        env = dict(_os.environ)
        # Pynguin 会执行被测代码（正是 LGPL 引擎只做 subprocess 隔离的原因）
        env["PYNGUIN_DANGER_AWARE"] = "yes"
        proc = subprocess.run(
            [str(PYNGUIN), "--project-path", str(tmp),
             "--module-name", "target", "--output-path", str(tmp / "out"),
             "--assertion-generation", "NONE"],
            shell=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=180, env=env)
        generated = list((tmp / "out").glob("test_*.py")) if \
            (tmp / "out").is_dir() else []
        self.assertEqual(proc.returncode, 0,
                         (proc.stdout + proc.stderr)[-300:])
        self.assertTrue(generated, "Pynguin 应产出至少一个测试文件")


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
