# -*- coding: utf-8 -*-
"""tests/test_scripts_engines.py — 引擎与采样：TestAgentSampleStaleLedger / TestScannerFalsePositives / TestAstgrepSecurity / TestAstgrepQuality / TestAstgrepPractice（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestAgentSampleStaleLedger(unittest.TestCase):
    """agent-sample 复评去冗（round-64 实踩的假红/假绿同源缺陷）。

    反向验证锚点：补丁摘要变了必须清 DONE 行重跑；摘要没变的 DONE 行必须
    保留（断点续跑语义）；摘要文件缺失按「变了」处理，不吃陈旧判分；
    非 DONE 行（ERROR 等）本来就会重跑，不受去冗影响。
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "agent_sample_stale", S / "eval-harness" / "scripts" / "agent-sample.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)

    def _ledger(self, tmp, rows, digests=None):
        out = Path(tmp)
        (out / "gold-sample-ledger.json").write_text(
            json.dumps({"results": rows}, ensure_ascii=False), encoding="utf-8")
        if digests is not None:
            (out / "_patch-digests.json").write_text(
                json.dumps(digests, ensure_ascii=False), encoding="utf-8")
        return out

    def _rows(self, out):
        return json.loads((out / "gold-sample-ledger.json").read_text(
            encoding="utf-8"))["results"]

    def test_changed_patch_prunes_only_stale_done_row(self):
        with tempfile.TemporaryDirectory() as td:
            out = self._ledger(td, [
                {"instance_id": "a__a-1", "state": "DONE", "resolved": False},
                {"instance_id": "b__b-2", "state": "DONE", "resolved": True},
                {"instance_id": "c__c-3", "state": "ERROR", "resolved": False},
            ], {"a__a-1": "old", "b__b-2": "same"})
            pruned = self.m.prune_stale_ledger(out, {
                "a__a-1": "new", "b__b-2": "same", "c__c-3": "x"})
            self.assertEqual(pruned, ["a__a-1"])
            self.assertEqual([r["instance_id"] for r in self._rows(out)],
                             ["b__b-2", "c__c-3"])
            state = json.loads((out / "_patch-digests.json").read_text(
                encoding="utf-8"))
            self.assertEqual(state["a__a-1"], "new",
                             "送评摘要必须更新，否则下次复评又会误清")

    def test_missing_digest_state_is_treated_as_stale(self):
        with tempfile.TemporaryDirectory() as td:
            out = self._ledger(td, [
                {"instance_id": "a__a-1", "state": "DONE", "resolved": True},
            ])
            pruned = self.m.prune_stale_ledger(out, {"a__a-1": "x"})
            self.assertEqual(pruned, ["a__a-1"],
                             "没有摘要记录的 DONE 行不可信，必须重跑")
            self.assertEqual(self._rows(out), [])

    def test_untouched_instances_keep_resume_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            out = self._ledger(td, [
                {"instance_id": "a__a-1", "state": "DONE", "resolved": True},
                {"instance_id": "b__b-2", "state": "DONE", "resolved": False},
            ], {"a__a-1": "same"})
            pruned = self.m.prune_stale_ledger(out, {"a__a-1": "same"})
            self.assertEqual(pruned, [])
            self.assertEqual([r["instance_id"] for r in self._rows(out)],
                             ["a__a-1", "b__b-2"],
                             "未送评实例的台账行不因去冗被动，续跑照旧")
            state = json.loads((out / "_patch-digests.json").read_text(
                encoding="utf-8"))
            self.assertNotIn("b__b-2", state,
                             "只登记本轮实际送评的实例摘要")


class TestScannerFalsePositives(unittest.TestCase):
    """阴性对照：扫描器对「像缺陷但不是」与「正确惯用法」必须零命中。"""

    def _scan(self, name, src):
        f = FIXTURE["tmp"] / ("fp-" + name)
        f.write_text(src, encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"], "--file", f)
        self.assertEqual(rc, 0)
        return data["findings"]

    def test_self_scan_zero_hits(self):
        """批扫口径（D-049 C）：一次子进程扫全部脚本，按文件逐段断言。"""
        files = [str(p) for p in SCRIPTS.values()]
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"],
                             *sum((["--file", f] for f in files), []))
        self.assertEqual(rc, 0)
        self.assertTrue(data.get("batch"), "必须是批扫输出")
        by_file = {r["file"]: r for r in data["results"]}
        for name, path in SCRIPTS.items():
            with self.subTest(script=name):
                r = by_file.get(str(path))
                self.assertIsNotNone(r, "缺结果段: %s" % name)
                self.assertEqual(r["rc"], 0, name)
                self.assertEqual(r["findings"], [], "%s 自扫出现命中" % name)

    def test_clean_code_per_rule(self):
        pickle_doc = '"""示例：pickle.' + 'loads(blob) 会反序列化不可信数据。"""\n'
        cases = {
            "cred-1-env.py": "import os\npassword = os.environ['DB_PASS']\n",
            "cred-2-placeholder.py": "password = '***'\napi_key = '<redacted>'\ntoken = 'your_key_here'\n",
            "cred-3-comment.py": "# 不要写 password=xxx，也不要提交 api_key=yyy\n",
            "cred-4-shape-placeholder.py": "k = 'sk-' + 'x'\nj = 'ghp_' + 'y'\n",
            "danger-1-comment.py": "# eval() 很危险，不要在生产代码使用 eval\nx = 1\n",
            "danger-2-string.py": "MODE = 'shell=True 只是字符串常量，不是参数'\n",
            "danger-3-docstring.py": pickle_doc,
            "lang-1-lambda-outside-loop.py": "f = lambda x: x + 1\nprint(f(1))\n",
            "lang-2-closed-handle.py": "f = open('a.txt')\ndata = f.read()\nf.close()\n",
            "lang-4-lambda-default-capture.py": "def f(paths):\n    out = []\n"
                                               "    for path in paths:\n"
                                               "        out.append(lambda _m, p=str(path): p)\n"
                                               "    return out\n",
            "lang-3-err-checked.go": 'package main\nimport "os"\n'
                                     "func main() {\n    f, err := os.Open('x')\n"
                                     "    if err != nil {\n        panic(err)\n    }\n"
                                     "    defer f.Close()\n}\n",
        }
        for name, src in cases.items():
            findings = self._scan(name, src)
            self.assertEqual(findings, [], "%s 干净样例被误报" % name)

    def test_closure_default_capture_diff_mode(self):
        """diff 行扫描：默认参数绑定循环变量不报，裸闭包仍报（正反双向）。"""
        d = FIXTURE["tmp"] / "fp-closure-diff"
        d.mkdir(exist_ok=True)
        head = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
                "@@ -1,2 +1,4 @@\n def f(paths):\n     out = []\n"
                "+    for path in paths:\n+        out.append(lambda%s)\n")
        safe = d / "safe.diff"
        safe.write_text(head % " _m, p=str(path): p", encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"],
                             "--diff-file", safe)
        self.assertEqual(rc, 0)
        self.assertEqual([f for f in data["findings"]
                          if f["rule_id"] == "lang-closure-late-bind"], [],
                         "默认参数绑定循环变量属于安全写法，不得报延迟绑定")
        bad = d / "bad.diff"
        bad.write_text(head % ": path", encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"],
                             "--diff-file", bad)
        self.assertEqual(rc, 0)
        self.assertTrue([f for f in data["findings"]
                         if f["rule_id"] == "lang-closure-late-bind"],
                        "裸用循环变量仍必须判延迟绑定")

    def test_idiom_not_flagged(self):
        cases = {
            "java-null.java": "class A {\n    void m(String s) {\n"
                              "        if (s == null) {\n            return;\n        }\n    }\n}\n",
            "php-email.php": "<?php\n$x = 'contact@example.com';\necho $x;\n",
            "ruby-compare.rb": "if a == b\n  puts 1\nend\n",
            "go-nil-check.go": 'package main\n'
                               'func load(v map[string]int, k string) int {\n'
                               "    x, ok := v[k]\n"
                               "    if !ok {\n        return 0\n    }\n"
                               "    _ = x\n    return x\n}\n",
        }
        for name, src in cases.items():
            findings = self._scan(name, src)
            self.assertEqual(findings, [], "%s 惯用法被误报" % name)


class TestAstgrepSecurity(unittest.TestCase):
    """ast-grep 安全类规则（步骤 1.1）阳性/阴性对照。"""

    SEC_DIR = ROOT / "tests" / "fixtures" / "astgrep-security"
    ADAPTER = ROOT / "engines" / "astgrep_adapter.py"

    def test_problem_file_hits(self):
        """问题样例：5 条 JS 安全规则全命中。"""
        f = self.SEC_DIR / "problem-security.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        codes = set(data.get("codes", []))
        expected = {
            "astgrep:js-innerhtml-assignment",
            "astgrep:js-document-write",
            "astgrep:js-settimeout-string-arg",
            "astgrep:js-regex-injection-new",
            "astgrep:js-prototype-pollution",
        }
        self.assertTrue(expected.issubset(codes),
                        "missing: %s" % (expected - codes))

    def test_ts_any_cast_hits(self):
        """TypeScript 问题样例：ts-unsafe-any-cast 命中。"""
        f = self.SEC_DIR / "problem-security.ts"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        codes = set(data.get("codes", []))
        self.assertIn("astgrep:ts-unsafe-any-cast", codes)

    def test_clean_file_zero_hits(self):
        """干净样例：安全规则零命中。"""
        f = self.SEC_DIR / "clean-security.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        sec_codes = {c for c in data.get("codes", [])
                     if c.startswith("astgrep:js-")
                     or c.startswith("astgrep:ts-")}
        self.assertEqual(sec_codes, set(),
                         "干净样例不应命中安全规则: %s" % sec_codes)


class TestAstgrepQuality(unittest.TestCase):
    """ast-grep 代码质量类规则（步骤 1.2）阳性/阴性对照。"""

    SEC_DIR = ROOT / "tests" / "fixtures" / "astgrep-quality"
    ADAPTER = ROOT / "engines" / "astgrep_adapter.py"

    _QUALITY_CODES = {
        "astgrep:js-empty-catch",
        "astgrep:js-loose-equality",
        "astgrep:js-throw-string",
        "astgrep:js-typeof-undefined",
        "astgrep:js-with-statement",
        "astgrep:js-void-expr",
        "astgrep:js-delete-expr",
                "astgrep:js-double-not",
        "astgrep:js-new-array",
    }

    def test_quality_problem_hits(self):
        f = self.SEC_DIR / "problem-quality.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        codes = set(data.get("codes", []))
        missing = self._QUALITY_CODES - codes
        self.assertEqual(missing, set(),
                         "missing quality codes: %s" % missing)

    def test_quality_clean_zero_hits(self):
        f = self.SEC_DIR / "clean-quality.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        hit = [c for c in data.get("codes", []) if c.startswith("astgrep:js-")]
        self.assertEqual(hit, [], "clean-quality 误报: %s" % hit)


class TestAstgrepPractice(unittest.TestCase):
    """ast-grep 最佳实践类规则（步骤 1.3）阳性/阴性对照。"""

    SEC_DIR = ROOT / "tests" / "fixtures" / "astgrep-quality"
    ADAPTER = ROOT / "engines" / "astgrep_adapter.py"

    _PRACTICE_CODES = {
        "astgrep:js-new-object",
        "astgrep:js-parseint-no-radix",
        "astgrep:js-setinterval-no-clear",
        "astgrep:ts-empty-interface",
        "astgrep:ts-no-explicit-any",
        "astgrep:js-default-export-anonymous",
        "astgrep:js-label-statement",
        "astgrep:js-throw-new-error",
    }

    def test_practice_problem_hits(self):
        for fname in ["problem-practice.js", "problem-practice.ts"]:
            f = self.SEC_DIR / fname
            rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
            self.assertEqual(rc, 0, fname)
        f_js = self.SEC_DIR / "problem-practice.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f_js))
        codes = set(data.get("codes", []))
        f_ts = self.SEC_DIR / "problem-practice.ts"
        rc2, data2, _, _ = run(self.ADAPTER, "scan", "--file", str(f_ts))
        codes |= set(data2.get("codes", []))
        missing = self._PRACTICE_CODES - codes
        self.assertEqual(missing, set(),
                         "missing practice codes: %s" % missing)

    def test_practice_clean_zero_hits(self):
        f = self.SEC_DIR / "clean-practice.js"
        rc, data, _, _ = run(self.ADAPTER, "scan", "--file", str(f))
        self.assertEqual(rc, 0)
        hit = [c for c in data.get("codes", [])
               if c.startswith("astgrep:js-") or c.startswith("astgrep:ts-")]
        self.assertEqual(hit, [], "clean-practice 误报: %s" % hit)


