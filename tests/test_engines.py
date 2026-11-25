#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_engines.py — Phase 2A：Ruff 引擎接入修复链的契约断言。

链路：adapter scan → fix-plan 引擎分诊 → approve-plan 工单 → fix-patch
引擎补丁（manifest 带 engine/before_codes）→ approve-patch 准出（结构
检查允许移动 import）→ fix-apply 五道闸（闸五按引擎复扫）→ 测试绿。
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
from _scripts_common import SCRIPTS

ROOT = Path(__file__).resolve().parents[1]
RUFF_ADAPTER = ROOT / "engines" / "ruff_adapter.py"
ASTGREP_ADAPTER = ROOT / "engines" / "astgrep_adapter.py"


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


class TestRuffAdapter(unittest.TestCase):
    """适配器三模式 + 引擎库函数。"""

    def test_scan_and_fix_dry(self):
        tmp = tmpspace.create(prefix="ruff-adapt-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "mod.py"
        target.write_text("import os\nimport json\n\n\ndef f(x):\n"
                          "    return x + 1\n",
                          encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(RUFF_ADAPTER, "scan",
                                          "--file", target)
        self.assertEqual(rc, 0)
        codes = {f["rule_id"] for f in data["findings"]}
        self.assertIn("ruff:F401", codes)
        self.assertTrue(all(f["engine"] == "ruff" for f in data["findings"]))
        rc, data, _, _ = test_scripts.run(RUFF_ADAPTER, "fix-dry",
                                          "--repo", tmp, "--rel", "mod.py",
                                          "--out", tmp / "p")
        self.assertEqual(rc, 0)
        self.assertGreater(data["patch_bytes"], 0)
        self.assertEqual(data["residual_codes"], [])
        patch = Path(data["patch_path"]).read_text(encoding="utf-8")
        self.assertIn("-import os", patch)
        self.assertIn("a/mod.py", patch)

    def test_matrix_file_contract(self):
        matrix_path = ROOT / "engines" / "ruff-matrix.json"
        self.assertTrue(matrix_path.is_file(), "能力矩阵应入仓")
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertGreater(matrix["total_rules"], 500)
        self.assertGreater(matrix["fixable_rules"], 100)
        self.assertIn("F401", matrix["fixable_codes"])


class TestEngineRepairChain(unittest.TestCase):
    """引擎发现走完整修复链（治理不因引擎而降级）。"""

    def _repo(self):
        tmp = tmpspace.create(prefix="ruff-chain-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "svc.py").write_text(
            "import os\nimport json\n\n\ndef calc(x):\n    return x * 2\n",
            encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_svc.py").write_text(
            "from svc import calc\n\n\ndef test_calc():\n    assert calc(3) == 6\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo, tmp

    def test_full_engine_chain(self):
        repo, tmp = self._repo()
        rc, scan, _, _ = test_scripts.run(RUFF_ADAPTER, "scan",
                                          "--file", repo / "svc.py",
                                          "--rel", "svc.py")
        self.assertEqual(rc, 0)
        findings = tmp / "findings.json"
        findings.write_text(json.dumps(scan, ensure_ascii=False),
                            encoding="utf-8", newline="\n")
        # 闸 1：fix-plan 引擎分诊 + approve-plan 工单
        rc, plan, _, _ = test_scripts.run(SCRIPTS["fix-plan.py"],
                                          "--findings", findings,
                                          "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertTrue(plan["fixable"], "ruff 码应引擎分诊为可修")
        self.assertEqual({e["engine"] for e in plan["fixable"]}, {"ruff"})
        rc, order, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"],
                                           "--findings", findings,
                                           "--repo", repo,
                                           "--out", tmp / "ap")
        self.assertEqual(rc, 0)
        # fix-patch：引擎补丁 + manifest 引擎字段
        rc, patch, _, _ = test_scripts.run(SCRIPTS["fix-patch.py"],
                                           "--order", tmp / "ap" / "work-order.json",
                                           "--repo", repo,
                                           "--out", tmp / "out")
        self.assertEqual(rc, 0, json.dumps(patch, ensure_ascii=False)[:300])
        entry = patch["files"][0]
        self.assertEqual(entry["engine"], "ruff")
        self.assertIsNotNone(entry["before_codes"])
        # 闸 2：准出（结构检查不得误杀 import 移动）
        rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"],
                                           "--order", tmp / "ap" / "work-order.json",
                                           "--manifest", tmp / "out" / "fix-manifest.json",
                                           "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 0, json.dumps(gate2, ensure_ascii=False)[:400])
        self.assertEqual(gate2["verdict"], "APPROVED")
        # 闸五 + 落盘
        rc, applied, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"],
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo, "--approval", tmp / "ap" / "approval.json",
            "--apply")
        self.assertEqual(rc, 0, json.dumps(applied, ensure_ascii=False)[:500])
        self.assertEqual(applied["state"], "APPLIED")
        self.assertEqual(applied["tests"]["status"], "pass")
        fixed = (repo / "svc.py").read_text(encoding="utf-8")
        self.assertNotIn("import os", fixed, "未用导入应被引擎清除")
        self.assertIn("def calc", fixed)
        # 复扫：ruff 默认集零残留
        rc, rescan, _, _ = test_scripts.run(RUFF_ADAPTER, "scan",
                                            "--file", repo / "svc.py")
        self.assertEqual(rescan["findings"], [])


def setUpModule():
    test_scripts.ensure_fixture()


LIBCST_ADAPTER = ROOT / "engines" / "libcst_adapter.py"
# CI（Linux）没有 .venv：回落到当前解释器（依赖由 workflow 安装）。
_VENV_PY = ROOT / ".venv" / (
    "Scripts/python.exe" if sys.platform == "win32" else "bin/python")
VENV_PY = _VENV_PY if _VENV_PY.is_file() else Path(sys.executable)


def _venv_run(script, *args, timeout=120, stdin=None, env_extra=None):
    env = dict(os.environ)
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    p = subprocess.run([str(VENV_PY), str(script)] + [str(a) for a in args],
                       shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       input=stdin, env=env)
    try:
        return p.returncode, json.loads(p.stdout), p.stdout, p.stderr
    except ValueError:
        return p.returncode, None, p.stdout, p.stderr


class TestLibcstAdapter(unittest.TestCase):
    """LibCST 重构引擎：scan/fix-text/fix-dry/clean-fp/matrix 契约。"""

    FIXTURE = ("def f(x, d, k):\n"
               "    if x == None:\n"
               "        return 1\n"
               "    if k in d.keys():\n"
               "        return x != None\n"
               "    return 0\n")
    CLEAN = ("def f(x, d, k):\n"
             "    if x is None:\n"
             "        return 1\n"
             "    if k in d:\n"
             "        return x is not None\n"
             "    return 0\n")

    def _fixture(self):
        import tempfile
        tmp = tmpspace.create(prefix="libcst-adapt-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "mod.py"
        target.write_text(self.FIXTURE, encoding="utf-8", newline="\n")
        return tmp, target

    def test_scan_finds_both_codemods(self):
        _tmp, target = self._fixture()
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "scan", "--file", target,
                                   "--rel", "mod.py")
        self.assertEqual(rc, 0, str(data)[:200])
        codes = {f["rule_id"] for f in data["findings"]}
        self.assertIn("libcst:ref-eq-none", codes)
        self.assertIn("libcst:ref-in-keys", codes)
        self.assertTrue(all(f["engine"] == "libcst" for f in data["findings"]))

    def test_scan_no_fp_on_clean_code(self):
        """反向验证：已是目标形态的代码零命中（clean-fp 口径）。"""
        tmp = tmpspace.create(prefix="libcst-clean-")
        self.addCleanup(tmpspace.release, tmp)
        clean = tmp / "clean.py"
        clean.write_text(self.CLEAN, encoding="utf-8", newline="\n")
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "clean-fp", "--file", clean)
        self.assertEqual(rc, 0)
        self.assertEqual(data["clean_fp"], 0, "干净样例发现即误报")

    def test_fix_text_transforms(self):
        _tmp, target = self._fixture()
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "fix-text",
                                   "--codes", "ref-eq-none,ref-in-keys",
                                   stdin=target.read_text(encoding="utf-8"))
        self.assertEqual(rc, 0, str(data)[:200])
        self.assertIn("x is None", data["text"])
        self.assertIn("k in d", data["text"])
        self.assertIn("x is not None", data["text"])
        self.assertNotIn("== None", data["text"])
        self.assertNotIn("in d.keys()", data["text"])

    def test_fix_text_keeps_cjk_comment_under_gbk_stdio(self):
        """fix-text 的 stdin 必须按 UTF-8 读：中文注释不能进 codemod 前就坏。

        复现与宿主 locale 无关——显式把孩子的 stdio 钉成 GBK（中文 Windows 桌面
        的默认态）；不 reconfigure stdin 的实现会把 UTF-8 字节解成乱码，注释进
        产物即损坏（round-31 同类排查：findings-check / report-check / score 同因）。
        """
        text = ("# \u652f\u4ed8\u56de\u8c03\u5e42\u7b49\u6027\n"
                "def f(x):\n    if x == None:\n        return 1\n    return 2\n")
        rc, data, out, err = _venv_run(LIBCST_ADAPTER, "fix-text",
                                       "--codes", "ref-eq-none", stdin=text,
                                       env_extra={"PYTHONIOENCODING": "gbk"})
        self.assertEqual(rc, 0, (err or "")[-200:] or str(data)[:200])
        self.assertIn("\u652f\u4ed8\u56de\u8c03\u5e42\u7b49\u6027", data["text"],
                      "注释被 stdio locale 解码损坏：修复产物会改掉无关字节")
        self.assertIn("x is None", data["text"])

    def test_fix_dry_patch(self):
        tmp, target = self._fixture()
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "fix-dry", "--repo", tmp,
                                   "--rel", "mod.py", "--out", tmp / "p")
        self.assertEqual(rc, 0, str(data)[:200])
        self.assertGreater(data["patch_bytes"], 0)
        self.assertEqual(data["residual_codes"], [])
        patch = Path(data["patch_path"]).read_text(encoding="utf-8")
        self.assertIn("a/mod.py", patch)
        self.assertIn("-    if x == None:", patch)
        self.assertIn("+    if x is None:", patch)

    def test_matrix_contract(self):
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "matrix")
        self.assertEqual(rc, 0)
        matrix = data["matrix"]
        self.assertEqual(matrix["engine"], "libcst")
        self.assertIn("ref-eq-none", matrix["fixable_codes"])
        self.assertIn("ref-in-keys", matrix["fixable_codes"])

    def test_fix_text_rejects_unknown_codemod(self):
        rc, data, _, _ = _venv_run(LIBCST_ADAPTER, "fix-text",
                                   "--codes", "no-such-codemod",
                                   stdin="x = 1\n")
        self.assertEqual(rc, 2)


class TestLibcstEngineChain(unittest.TestCase):
    """libcst 发现走完整修复链（fix-plan 分诊 → 闸 2 → 闸五引擎复扫）。"""

    def _repo(self):
        tmp = tmpspace.create(prefix="libcst-chain-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "svc.py").write_text(
            "def calc(x, d, k):\n"
            "    if x == None:\n"
            "        return 0\n"
            "    if k in d.keys():\n"
            "        return 1\n"
            "    return 2\n",
            encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_svc.py").write_text(
            "from svc import calc\n\n\ndef test_calc():\n"
            "    assert calc(None, {}, 'a') == 0\n"
            "    assert calc(1, {'a': 1}, 'a') == 1\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo, tmp

    def test_full_libcst_chain(self):
        repo, tmp = self._repo()
        rc, scan, _, _ = _venv_run(LIBCST_ADAPTER, "scan",
                                   "--file", repo / "svc.py",
                                   "--rel", "svc.py")
        self.assertEqual(rc, 0)
        findings = tmp / "findings.json"
        findings.write_text(json.dumps(scan, ensure_ascii=False),
                            encoding="utf-8", newline="\n")
        rc, plan, _, _ = test_scripts.run(SCRIPTS["fix-plan.py"],
                                          "--findings", findings,
                                          "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertTrue(plan["fixable"], "libcst 码应引擎分诊为可修")
        self.assertEqual({e["engine"] for e in plan["fixable"]}, {"libcst"})
        rc, order, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"],
                                           "--findings", findings,
                                           "--repo", repo,
                                           "--out", tmp / "ap")
        self.assertEqual(rc, 0)
        rc, patch, _, _ = test_scripts.run(
            SCRIPTS["fix-patch.py"],
            "--order", tmp / "ap" / "work-order.json",
            "--repo", repo, "--out", tmp / "out")
        self.assertEqual(rc, 0, json.dumps(patch, ensure_ascii=False)[:300])
        entry = patch["files"][0]
        self.assertEqual(entry["engine"], "libcst")
        self.assertIsNotNone(entry["before_codes"])
        rc, gate2, _, _ = test_scripts.run(
            SCRIPTS["approve-patch.py"],
            "--order", tmp / "ap" / "work-order.json",
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 0, json.dumps(gate2, ensure_ascii=False)[:400])
        self.assertEqual(gate2["verdict"], "APPROVED")
        rc, applied, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"],
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo, "--approval", tmp / "ap" / "approval.json",
            "--apply")
        self.assertEqual(rc, 0, json.dumps(applied, ensure_ascii=False)[:500])
        self.assertEqual(applied["state"], "APPLIED")
        self.assertEqual(applied["tests"]["status"], "pass")
        fixed = (repo / "svc.py").read_text(encoding="utf-8")
        self.assertNotIn("== None", fixed)
        self.assertNotIn("in d.keys()", fixed)
        self.assertIn("x is None", fixed)
        self.assertIn("k in d", fixed)
        # 复扫：libcst 码零残留
        rc, rescan, _, _ = _venv_run(LIBCST_ADAPTER, "scan",
                                     "--file", repo / "svc.py")
        self.assertEqual(rescan["findings"], [])


class TestAstgrepAdapter(unittest.TestCase):
    """ast-grep 多语言引擎适配器契约（round-38，阶段 2 第一枚）。

    与 ruff/libcst 同形状的五子命令，但这是引擎矩阵的第一枚**多语言**
    引擎（JS/TS），口径与 ruff_adapter 对齐。
    """

    def test_scan_finds_console_log_and_debugger(self):
        tmp = tmpspace.create(prefix="astgrep-scan-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "app.js"
        target.write_text(
            'console.log("debug")\ndebugger\nfunction empty() {}\n',
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target, "--rel", "app.js")
        self.assertEqual(rc, 0, str(data)[:300])
        codes = {f["rule_id"] for f in data["findings"]}
        self.assertIn("astgrep:no-console-log", codes)
        self.assertIn("astgrep:no-debugger", codes)
        self.assertIn("astgrep:no-empty-block", codes)
        self.assertTrue(all(f["engine"] == "astgrep" for f in data["findings"]))
        self.assertEqual(data["lang"], "JavaScript")

    def test_scan_clean_file_zero_findings(self):
        """反向验证：干净文件零诊断（不是「一律报」）。"""
        tmp = tmpspace.create(prefix="astgrep-clean-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "clean.js"
        target.write_text(
            'function add(a, b) {\n  return a + b;\n}\n',
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target)
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [])

    def test_fix_dry_removes_console_log(self):
        tmp = tmpspace.create(prefix="astgrep-fix-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "app.js").write_text(
            'console.log("hi")\nfunction f() {\n  return 1;\n}\n',
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "fix-dry",
                                          "--repo", repo, "--rel", "app.js",
                                          "--out", tmp / "p")
        self.assertEqual(rc, 0, str(data)[:300])
        self.assertGreater(data["patch_bytes"], 0,
                           "console.log 被删除后必须有补丁产出")
        self.assertEqual(data["residual_codes"], [],
                         "修复后残余诊断应为空")
        patch = Path(data["patch_path"]).read_text(encoding="utf-8")
        self.assertIn("-console.log", patch)
        self.assertIn("a/app.js", patch)

    def test_matrix_file_contract(self):
        """能力矩阵入仓且契约形状正确。"""
        matrix_path = ROOT / "engines" / "astgrep-matrix.json"
        self.assertTrue(matrix_path.is_file(), "astgrep-matrix.json 应入仓")
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(matrix["engine"], "astgrep")
        self.assertGreaterEqual(matrix["total_rules"], 2)
        self.assertGreaterEqual(matrix["fixable_rules"], 1)
        self.assertIn("no-console-log", matrix["fixable_codes"])
        self.assertIn("JavaScript", matrix["by_language"])

    def test_param_errors_exit_2(self):
        """文件不存在 → 退出码 2（与 ruff_adapter 同口径）。"""
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", "Z:/no/such/file.js")
        self.assertEqual(rc, 2)

    def test_unknown_lang_is_error(self):
        """无法推断语言且未指定 --lang → 退出码 2。"""
        tmp = tmpspace.create(prefix="astgrep-lang-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "data.xyz"
        target.write_text("whatever\n", encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target)
        self.assertEqual(rc, 2)
        self.assertIn("语言", data.get("error", ""))

    def test_scan_finds_var_and_eval(self):
        """新增 JS/TS 规则：no-var / no-eval（标注类，不可机械修复）。"""
        tmp = tmpspace.create(prefix="astgrep-v2-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "app.js"
        target.write_text(
            'var x = 1\n'
            'eval("alert(1)")\n'
            'let y = 2\n',
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target, "--rel", "app.js")
        self.assertEqual(rc, 0, str(data)[:300])
        codes = {f["rule_id"] for f in data["findings"]}
        self.assertIn("astgrep:no-var", codes)
        self.assertIn("astgrep:no-eval", codes)
        self.assertNotIn("astgrep:prefer-const", codes,
                         "let 不应被 no-var 匹配")

    def test_scan_python_print_debug(self):
        """Python 规则：print-debug 标注（与 console.log 对称）。"""
        tmp = tmpspace.create(prefix="astgrep-py-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "app.py"
        target.write_text(
            'print("debug")\n'
            'print(x)\n'
            'def add(a, b):\n'
            '    return a + b\n',
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target, "--rel", "app.py")
        self.assertEqual(rc, 0, str(data)[:300])
        codes = {f["rule_id"] for f in data["findings"]}
        self.assertIn("astgrep:print-debug", codes)
        self.assertEqual(data["lang"], "Python")

    def test_clean_python_zero_findings(self):
        """反向验证：干净 Python 文件零诊断。"""
        tmp = tmpspace.create(prefix="astgrep-clean-py-")
        self.addCleanup(tmpspace.release, tmp)
        target = tmp / "clean.py"
        target.write_text(
            'def add(a, b):\n'
            '    return a + b\n',
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", target)
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [])

    def test_matrix_v2_contract(self):
        """v2 矩阵：6 规则 / 2 可修复 / 含 Python 语言。"""
        matrix_path = ROOT / "engines" / "astgrep-matrix.json"
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        self.assertEqual(matrix["engine"], "astgrep")
        self.assertGreaterEqual(matrix["total_rules"], 5)
        self.assertGreaterEqual(matrix["fixable_rules"], 2)
        self.assertIn("no-console-log", matrix["fixable_codes"])
        self.assertIn("Python", matrix["by_language"])
        self.assertIn("JavaScript", matrix["by_language"])


class TestAstgrepEngineChain(unittest.TestCase):
    """ast-grep 发现走完整修复链（fix-plan 分诊 → 闸 2 → 闸五引擎复扫）。

    与 TestRuffEngineChain / TestLibcstEngineChain 对齐，但目标是 JS 文件
    （ast-grep 是引擎矩阵第一枚多语言引擎）。
    """

    def _repo(self):
        tmp = tmpspace.create(prefix="astgrep-chain-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "app.js").write_text(
            'console.log("debug")\n'
            'function add(a, b) {\n  return a + b;\n}\n',
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo, tmp

    def test_full_astgrep_chain(self):
        repo, tmp = self._repo()
        rc, scan, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                          "--file", repo / "app.js",
                                          "--rel", "app.js")
        self.assertEqual(rc, 0)
        self.assertTrue(scan["findings"], "应发现 console.log")
        findings = tmp / "findings.json"
        findings.write_text(json.dumps(scan, ensure_ascii=False),
                            encoding="utf-8", newline="\n")
        # 闸 1：fix-plan 引擎分诊 + approve-plan 工单
        rc, plan, _, _ = test_scripts.run(SCRIPTS["fix-plan.py"],
                                          "--findings", findings,
                                          "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertTrue(plan["fixable"], "astgrep 码应引擎分诊为可修")
        self.assertEqual({e["engine"] for e in plan["fixable"]}, {"astgrep"})
        rc, order, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"],
                                           "--findings", findings,
                                           "--repo", repo,
                                           "--out", tmp / "ap")
        self.assertEqual(rc, 0)
        # fix-patch：引擎补丁 + manifest 引擎字段
        rc, patch, _, _ = test_scripts.run(
            SCRIPTS["fix-patch.py"],
            "--order", tmp / "ap" / "work-order.json",
            "--repo", repo, "--out", tmp / "out")
        self.assertEqual(rc, 0, json.dumps(patch, ensure_ascii=False)[:300])
        entry = patch["files"][0]
        self.assertEqual(entry["engine"], "astgrep")
        self.assertIsNotNone(entry["before_codes"])
        # 闸 2：approve-patch 结构检查
        rc, gate2, _, _ = test_scripts.run(
            SCRIPTS["approve-patch.py"],
            "--order", tmp / "ap" / "work-order.json",
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 0, json.dumps(gate2, ensure_ascii=False)[:400])
        self.assertEqual(gate2["verdict"], "APPROVED")
        # 闸五预检（不带 --apply）
        rc, proposed, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"],
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo)
        self.assertEqual(rc, 0, json.dumps(proposed, ensure_ascii=False)[:500])
        self.assertEqual(proposed["state"], "PROPOSED")
        # 闸五落盘（带 --apply）
        rc, applied, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"],
            "--manifest", tmp / "out" / "fix-manifest.json",
            "--repo", repo, "--approval", tmp / "ap" / "approval.json",
            "--apply")
        self.assertEqual(rc, 0, json.dumps(applied, ensure_ascii=False)[:500])
        self.assertEqual(applied["state"], "APPLIED")
        # 测试跳过（JS 仓库无 test_*.py）
        self.assertEqual(applied["tests"]["status"], "skip")
        # 复扫：astgrep 码零残留
        rc, rescan, _, _ = test_scripts.run(ASTGREP_ADAPTER, "scan",
                                            "--file", repo / "app.js")
        self.assertEqual(rescan["findings"], [],
                         "console.log 应被删除，残余诊断应为空")


class TestArtifactNaming(unittest.TestCase):
    """补丁产物的命名键必须是**整条相对路径**（round-30 同类排查第 7 项）。

    旧形状：ruff / libcst / testgen 三个引擎都拿 `Path(rel).name` 当补丁名的键，
    于是 `services/util.py` 与 `tasks/util.py` 两路修复落进同一个 `--out` 目录时，
    **后写者原地吃掉前者的补丁**——而 fix-manifest 与批准书里的 sha256 已经和落盘
    内容不再对应：批准的是 A 的补丁，落盘的是 B 的补丁。这与 round-29 的轮号盖档
    同属一个缺陷类（按名字覆盖 / 按计数自增），只是这里丢掉的不是历史而是**已批准的产物**。
    """

    _TESTGEN = ROOT / "engines" / "testgen.py"

    def test_same_basename_different_dirs_do_not_collide(self):
        tmp = tmpspace.create(prefix="artifact-naming-")
        self.addCleanup(tmpspace.release, tmp)
        patches = tmp / "p"
        made = []
        for rel, body in (("services/util.py", "def a():\n    return 1\n"),
                          ("tasks/util.py", "def b():\n    return 2\n")):
            src = tmp / rel
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(body, encoding="utf-8", newline="\n")
            tag = rel.replace("/", "_").replace(".", "_")
            test_file = tmp / ("test_%s.py" % tag)
            test_file.write_text("def test_%s():\n    assert True\n" % tag,
                                 encoding="utf-8", newline="\n")
            rc, data, _, _ = test_scripts.run(self._TESTGEN, "patch",
                                              "--test", test_file, "--rel", rel,
                                              "--out", patches)
            self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:200])
            made.append(data["patch_path"])
        self.assertEqual(len(set(made)), 2,
                         "不同目录的同名文件撞同一个补丁名 = 后写者吃掉前者的补丁")
        self.assertEqual(len(list(patches.glob("*.patch"))), 2,
                         "两份补丁必须都在盘上")
        for rel, path in zip(("services/util.py", "tasks/util.py"), made):
            text = Path(path).read_text(encoding="utf-8")
            self.assertIn("b/%s" % rel, text,
                          "补丁内容必须对应它自己那条路径：%s" % path)

    def test_patch_artifact_name_is_stable_and_ascii(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "artifact_names", ROOT / "engines" / "artifact_names.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        name = mod.patch_artifact_name
        self.assertEqual(name("ruff", "a/b.py"), name("ruff", "a\\b.py"),
                         "同一模块的两种路径写法必须落在同一个产物名上")
        self.assertNotEqual(name("ruff", "services/util.py"),
                            name("ruff", "tasks/util.py"))
        self.assertNotEqual(name("ruff", "a/b_c.py"), name("ruff", "a_b/c.py"),
                            "把分隔符换成下划线也不能撞名（哈希后缀才是唯一性来源）")
        ascii_name = name("ruff", "services/模块.py")
        self.assertTrue(ascii_name.isascii(),
                        "产物文件名必须 ASCII 安全：%s" % ascii_name)



if __name__ == "__main__":
    unittest.main()
