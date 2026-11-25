#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_taint.py — 污点流引擎契约断言（3 条流 + 反向验证 + 自扫零）。

fixture 全部运行时拼接危险调用原文（红线：源码不落危险调用字面量）。
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace
from _scripts_common import SCRIPTS

ROOT = Path(__file__).resolve().parents[1]

EVAL_CALL = "ev" + "al(%s)"
EXEC_CALL = "ex" + "ec(%s)"
OS_SHELL_CALL = "os." + "system(%s)"
OS_POPEN_CALL = "os." + "popen(%s)"


def _engine():
    spec = importlib.util.spec_from_file_location(
        "dr_engine", SCRIPTS["deterministic-rules.py"])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scan(engine, code):
    return sorted((f["rule_id"], f["line"])
                  for f in engine._taint_findings(
                      "t.py", code,
                      {i + 1: line for i, line in enumerate(code.splitlines())}))


class TestTaint(unittest.TestCase):
    """污点流：直线传播抓得住，无污点不误报。"""

    def setUp(self):
        self.engine = _engine()

    def test_input_to_eval(self):
        code = 'name = input("n?")\nquery = name + "!"\n' + EVAL_CALL % "query" + "\n"
        self.assertEqual(_scan(self.engine, code), [("taint-eval", 3)])

    def test_environ_to_os_shell(self):
        code = "cmd = os.environ['CMD']\n" + OS_SHELL_CALL % "cmd" + "\n"
        self.assertEqual(_scan(self.engine, code), [("taint-os-shell", 2)])

    def test_environ_to_exec(self):
        code = "blob = os.environ.get('B')\n" + EXEC_CALL % "blob" + "\n"
        self.assertEqual(_scan(self.engine, code), [("taint-exec", 2)])

    def test_clean_code_no_finding(self):
        cases = [
            'q = "SELECT 1"\n' + EVAL_CALL % "q" + "\n",   # 常量入汇点
            "name = input()\nprint(name)\n",                # source 未入汇点
            OS_SHELL_CALL % "'ls'" + "\n",                  # 常量命令
        ]
        for code in cases:
            with self.subTest(code=code[:30]):
                self.assertEqual(_scan(self.engine, code), [])

    def test_request_chain_counts_as_source(self):
        code = "payload = request.args.get('p')\n" + EVAL_CALL % "payload" + "\n"
        self.assertEqual(_scan(self.engine, code), [("taint-eval", 2)])

    def test_output_contract_unchanged(self):
        """38 条硬规则口径不变；污点流单独计数（等于配置汇点数）。"""
        cfg = json.loads((ROOT / "skills" / "multi-agent-review" /
                          "taint-config.json").read_text(encoding="utf-8"))
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", SCRIPTS["score.py"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["rule_count"], 38)
        self.assertEqual(data["taint_rules"], len(cfg["sinks"]))
        self.assertEqual(data["findings"], [])


class TestTaintCross(unittest.TestCase):
    """跨文件两遍分析（案例 ed5c32b6187d 落地）：直接流/链式流/阴性。"""

    def _run_cross(self, files):
        tmp = tmpspace.create(prefix="taint-cross-")
        self.addCleanup(tmpspace.release, tmp)
        for name, source in files.items():
            (tmp / name).write_text(source, encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["taint-cross.py"],
                                          "--root", tmp)
        return rc, data

    def test_direct_cross_file_flow(self):
        """lib.run_cmd(被污染实参) → os.system：在调用方行报 taint-os-shell。"""
        lib = ("import os\n\n\ndef run_cmd(cmd):\n"
               "    " + OS_SHELL_CALL % "cmd" + "\n")
        app = ("import lib\nimport os\n\n"
               "cmd = os.environ['X']\n"
               "lib.run_cmd(cmd)\n")
        rc, data = self._run_cross({"lib.py": lib, "app.py": app})
        self.assertEqual(rc, 0)
        flows = [(f["rule_id"], Path(f["file"]).name, f["line"])
                 for f in data["findings"]]
        self.assertIn(("taint-os-shell", "app.py", 5), flows)
        self.assertEqual(data["summaries"], 1)

    def test_chained_flow_via_return(self):
        """param→return 摘要：lib.wrap(污点) 返回值在调用方继续传到 eval。"""
        lib = "def wrap(x):\n    return x\n"
        app = ("import lib\nimport os\n\n"
               "raw = os.environ['Y']\n"
               "v = lib.wrap(raw)\n"
               + EVAL_CALL % "v" + "\n")
        rc, data = self._run_cross({"lib.py": lib, "app.py": app})
        self.assertEqual(rc, 0)
        flows = [(f["rule_id"], Path(f["file"]).name) for f in data["findings"]]
        self.assertIn(("taint-eval", "app.py"), flows)

    def test_clean_call_no_finding(self):
        """常量实参跨模块调用不报。"""
        lib = ("import os\n\n\ndef run_cmd(cmd):\n"
               "    " + OS_SHELL_CALL % "cmd" + "\n")
        app = "import lib\n\nlib.run_cmd('ls -la')\n"
        rc, data = self._run_cross({"lib.py": lib, "app.py": app})
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [])

    def test_from_import_alias_resolves(self):
        """from lib import run_cmd 的别名也能解析。"""
        lib = ("import os\n\n\ndef run_cmd(cmd):\n"
               "    " + OS_SHELL_CALL % "cmd" + "\n")
        app = ("from lib import run_cmd\nimport os\n\n"
               "run_cmd(os.environ['X'])\n")
        rc, data = self._run_cross({"lib.py": lib, "app.py": app})
        self.assertEqual(rc, 0)
        flows = [(f["rule_id"], Path(f["file"]).name) for f in data["findings"]]
        self.assertIn(("taint-os-shell", "app.py"), flows)

    def test_taint_cross_self_scan_zero(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", SCRIPTS["taint-cross.py"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [])


class TestRunnerTaintCross(unittest.TestCase):
    """taint-cross 接入评审主线：跨文件流在变更文件 → runner 报 taint-*。"""

    def test_runner_reports_cross_file_flow(self):
        repo = tmpspace.create(prefix="taint-runner-")
        self.addCleanup(tmpspace.release, repo)
        lib_code = ("import os\n\n\ndef run_cmd(cmd):\n"
                    "    " + OS_SHELL_CALL % "cmd" + "\n")
        app_v1 = "import lib\n\nlib.run_cmd('ls -la')\n"
        app_v2 = "import lib\nimport os\n\nlib.run_cmd(os.environ['X'])\n"
        (repo / "lib.py").write_text(lib_code, encoding="utf-8", newline="\n")
        (repo / "app.py").write_text(app_v1, encoding="utf-8", newline="\n")
        import subprocess
        for args in (["init", "-q"],
                     ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        (repo / "app.py").write_text(app_v2, encoding="utf-8", newline="\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], shell=False,
                       capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", "commit", "-q", "-m", "taint"],
                       shell=False, capture_output=True)
        out = repo.parent / "runner-out"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["runner.py"], "--repo", repo, "--range", "HEAD~1..HEAD",
            "--out", out, "--skip-probe")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertEqual(data["state"], "DONE")
        flows = [f for f in data.get("findings", [])
                 if f.get("rule_id") == "taint-os-shell"]
        self.assertTrue(flows, "runner 必须报告跨文件污点流")
        self.assertIn("app.py", flows[0].get("loc", "") + flows[0].get("file", ""))


class TestRealCorpusChain(unittest.TestCase):
    """真实语料评测链（collect→prepare→run-samples→judge）本地端到端。

    方向契约（1.13.0 锁定）：run-samples 必须评审「缺陷引入态」——
    即父提交里的缺陷代码（fix 的反向 diff 的 + 行 / 父版本工作区），
    而不是修复后的代码。fixture：缺陷态带污点流与硬编码口令，
    修复提交把它们清掉；若扫错方向，两个断言都会落空。
    """

    def test_full_chain_on_local_repo(self):
        repo = tmpspace.create(prefix="real-corpus-")
        self.addCleanup(tmpspace.release, repo)
        import subprocess
        lib_code = ("import os\n\n\ndef run_cmd(cmd):\n"
                    "    " + OS_SHELL_CALL % "cmd" + "\n")
        clean_app = "import lib\n\nlib.run_cmd('ls')\n"
        buggy_app = "import lib\nimport os\n\nlib.run_cmd(os.environ['X'])\n"
        buggy_cred = "import os\npassword = " + '"' + test_scripts.SECRET + '"\n'
        clean_cred = "import os\npassword = os.environ['PW']\n"

        def commit(message):
            for args in (["add", "-A"],
                         ["-c", "user.name=t", "-c", "user.email=t@t",
                          "commit", "-q", "-m", message]):
                subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                               capture_output=True)
            return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                  shell=False, capture_output=True,
                                  text=True).stdout.strip()

        # c1 缺陷态：污点流 + 硬编码口令
        subprocess.run(["git", "-C", str(repo), "init", "-q"], shell=False,
                       capture_output=True)
        (repo / "lib.py").write_text(lib_code, encoding="utf-8", newline="\n")
        (repo / "app.py").write_text(buggy_app, encoding="utf-8", newline="\n")
        (repo / "cred.py").write_text(buggy_cred, encoding="utf-8", newline="\n")
        commit("chore: 缺陷态")
        sha_bug = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                 shell=False, capture_output=True,
                                 text=True).stdout.strip()
        # c2 修复：清掉污点流与硬编码口令（修复后代码不含任何规则形态）
        (repo / "app.py").write_text(clean_app, encoding="utf-8", newline="\n")
        (repo / "cred.py").write_text(clean_cred, encoding="utf-8", newline="\n")
        sha_fix = commit("fix: 安全-移除环境变量命令与硬编码口令")
        # c3 纯重构
        (repo / "notes.md").write_text("docs: 说明", encoding="utf-8",
                                       newline="\n")
        sha_refactor = commit("fix: 逻辑-补充说明文档")
        samples = repo.parent / "samples.json"
        samples.write_text(json.dumps({"samples": [
            {"fix_commit": sha_fix, "parent_rev": sha_bug,
             "summary": "fix: 安全-移除环境变量命令与硬编码口令",
             "files": ["app.py", "cred.py"], "defect_class": "安全"},
            {"fix_commit": sha_refactor, "parent_rev": sha_fix,
             "summary": "fix: 逻辑-补充说明文档", "files": ["notes.md"],
             "defect_class": "逻辑"},
        ]}, ensure_ascii=False), encoding="utf-8", newline="\n")
        prepared = repo.parent / "prepared"
        rc, data, _, _ = test_scripts.run(SCRIPTS["forward-bench.py"],
                                          "prepare", "--samples", samples,
                                          "--repo", repo, "--out", prepared)
        self.assertEqual(rc, 0)
        findings = repo.parent / "findings.json"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["run-samples.py"], "--samples", samples, "--repo", repo,
            "--out", findings, "--cross")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        grouped = json.loads(findings.read_text(encoding="utf-8"))["samples"]
        rules = {f.get("rule_id") for f in grouped.get(sha_fix, [])}
        # 方向契约：缺陷态的形态必须被抓到（修复后代码不含这些形态，
        # 扫错方向则两条都拿不到）
        self.assertIn("taint-os-shell", rules,
                      "缺陷引入态的跨文件污点流必须被 run-samples 抓到")
        self.assertIn("cred-password", rules,
                      "缺陷引入态的硬编码口令必须被 run-samples 抓到")
        self.assertEqual(grouped.get(sha_refactor), [], "纯重构样本应零发现")
        judge_out = repo.parent / "judge.json"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["forward-bench.py"], "judge", "--findings", findings,
            "--prepared", prepared / "manifest.json", "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertEqual(data.get("claimed"), 1, "仅安全修复样本被报")
        self.assertEqual(data.get("grounded"), 1, "安全修复样本应命中 gt")


def _rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
