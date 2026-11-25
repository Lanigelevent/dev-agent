# -*- coding: utf-8 -*-
"""tests/test_review_quality_gate.py — review-quality-gate.py 契约 + judge 前置校验（round-138，D-053）。

覆盖：四项检查（全空无依据抓得住/evidence 覆盖/unparsed 率/形状）、
run/check 双动词、退出码 0/1/2、judge 前置硬校验（empty_batch_no_evidence）。
反向验证（红线 6）：test_empty_batch_without_note / test_judge_blocks_empty_without_note。
"""
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "review-quality-gate.py"
SWR = ROOT / "skills" / "eval-harness" / "scripts" / "swrenbench-import.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ReviewQualityGateTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load(SCRIPT, "rqg_ut")
        self.swr = _load(SWR, "swr_ut2")
        self.tmp = Path(tmpspace.create(prefix="rqg-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def _findings(self, path, samples, note="", unparsed=None):
        data = {"reviewer": "host", "batch_note": note,
                "samples": samples,
                "unparsed": unparsed or [],
                "errors": []}
        Path(path).write_text(json.dumps(data, ensure_ascii=False),
                              encoding="utf-8")
        return str(path)

    def _invoke(self, mod, argv):
        old = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["review-quality-gate.py"] + argv
            with contextlib.redirect_stdout(out):
                rc = mod.main()
        finally:
            sys.argv = old
        return rc, out.getvalue()

    def test_empty_batch_without_note_fails(self):
        fd = self._findings(self.tmp / "a.json",
                            {"chg-1": [], "clean-1": []})
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertIn("empty_batch_note", d["failed"])

    def test_empty_batch_with_note_passes(self):
        fd = self._findings(self.tmp / "b.json",
                            {"chg-1": [], "clean-1": []},
                            note="本批 20 例全为文档/清理型 PR，gt 缺陷均为文本类，通用评审器无发现，逐条依据见批次报告。")
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["failed"], [])

    def test_low_evidence_coverage_fails(self):
        fd = self._findings(self.tmp / "c.json", {
            "chg-1": [{"loc": "a.py:1", "desc": "d", "evidence": "e"}],
            "chg-2": [{"loc": "a.py:2", "desc": "d", "evidence": ""}],
            "chg-3": [{"loc": "a.py:3", "desc": "d", "evidence": ""}],
            "chg-4": [{"loc": "a.py:4", "desc": "d", "evidence": ""}],
        })
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertIn("evidence_coverage", d["failed"])

    def test_high_evidence_coverage_passes(self):
        fd = self._findings(self.tmp / "d.json", {
            "chg-1": [{"loc": "a.py:1", "desc": "d", "evidence": "e"}],
            "chg-2": [{"loc": "a.py:2", "desc": "d", "evidence": "e"}],
            "clean-1": [],
        }, note="")
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["failed"], [])

    def test_unparsed_rate_fails(self):
        fd = self._findings(self.tmp / "e.json", {
            "s1": [], "s2": [], "s3": [], "s4": [], "s5": [],
        }, note="整批 unparsed 说明", unparsed=["s1", "s2"])
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertIn("unparsed_rate", d["failed"])

    def test_bad_shape_returns_2(self):
        p = self.tmp / "f.json"
        p.write_text("[1,2,3]", encoding="utf-8")
        rc, out_s = self._invoke(self.mod, ["check", "--findings", str(p)])
        d = json.loads(out_s)
        self.assertEqual(rc, 2)

    def test_run_verb_writes_report(self):
        fd = self._findings(self.tmp / "g.json", {
            "chg-1": [{"loc": "a.py:1", "desc": "d", "evidence": "e"}],
        })
        out = self.tmp / "rqg-report.json"
        rc, out_s = self._invoke(self.mod, ["run", "--findings", fd,
                                            "--out", str(out)])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertTrue(out.is_file())
        rep = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(rep["gate"], "review-quality-gate")

    def test_judge_blocks_empty_without_note(self):
        fd = self._findings(self.tmp / "h.json",
                            {"chg-1": []})
        rc, out_s = self._invoke(self.swr, ["judge", "--corpus",
                                            str(self.tmp / "no-such.jsonl"),
                                            "--findings", fd])
        self.assertEqual(rc, 2)
        self.assertIn("slim 语料不存在", out_s)

    def test_judge_empty_no_note_rc1(self):
        corpus = self.tmp / "slim.jsonl"
        row = {"instance_id": "chg-1", "repo": "r", "pr_title": "t",
               "change_introduced": True, "changes": [
                   {"change_type": "F.2", "snippet": "def f(x={}):"}],
               "diffs": [{"file": "m.py", "patch":
                          "diff --git a/m.py b/m.py" + chr(10)
                          + "--- a/m.py" + chr(10) + "+++ b/m.py" + chr(10)
                          + "@@ -1,2 +1,3 @@" + chr(10)
                          + " x = 1" + chr(10)
                          + "+def f(x={}):" + chr(10)}]}
        with corpus.open("w", encoding="utf-8", newline=chr(10)) as f:
            f.write(json.dumps(row, ensure_ascii=False) + chr(10))
        fd = self._findings(self.tmp / "i.json", {"chg-1": []})
        rc, out_s = self._invoke(self.swr, ["judge", "--corpus", str(corpus),
                                            "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertEqual(d["error"], "empty_batch_no_evidence")

    def test_judge_empty_with_note_proceeds(self):
        corpus = self.tmp / "slim2.jsonl"
        row = {"instance_id": "chg-1", "repo": "r", "pr_title": "t",
               "change_introduced": True, "changes": [
                   {"change_type": "F.2", "snippet": "def f(x={}):"}],
               "diffs": [{"file": "m.py", "patch":
                          "diff --git a/m.py b/m.py" + chr(10)
                          + "--- a/m.py" + chr(10) + "+++ b/m.py" + chr(10)
                          + "@@ -1,2 +1,3 @@" + chr(10)
                          + " x = 1" + chr(10) + "+def f(x={}):" + chr(10)}]}
        with corpus.open("w", encoding="utf-8", newline=chr(10)) as f:
            f.write(json.dumps(row, ensure_ascii=False) + chr(10))
        fd = self._findings(self.tmp / "j.json", {"chg-1": []},
                            note="本批为文档型 PR，gt 缺陷均为文本级，评审器无代码发现")
        rc, out_s = self._invoke(self.swr, ["judge", "--corpus", str(corpus),
                                            "--findings", fd])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["n_evaluated"], 1)

    def test_load_eval_config_schema(self):
        cfg = self.mod.load_eval_config()
        self.assertEqual(cfg.get("schema"), "eval-config/1")
        self.assertEqual(cfg["review_quality_gate"]["min_evidence"], 0.8)
        self.assertEqual(cfg["review_quality_gate"]["max_unparsed"], 0.1)
        self.assertEqual(cfg["review"]["max_chars"], 20000)

    def test_cli_overrides_config(self):
        fd = self._findings(self.tmp / "k.json", {
            "chg-1": [{"loc": "a.py:1", "desc": "d", "evidence": "e"}],
            "chg-2": [{"loc": "a.py:2", "desc": "d", "evidence": ""}],
            "chg-3": [{"loc": "a.py:3", "desc": "d", "evidence": ""}],
            "chg-4": [{"loc": "a.py:4", "desc": "d", "evidence": ""}],
        })
        rc, out_s = self._invoke(self.mod, ["check", "--findings", fd,
                                            "--min-evidence", "0.2"])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)

    def test_config_missing_falls_back(self):
        orig = self.mod.CONFIG
        try:
            self.mod.CONFIG = self.tmp / "no-such.toml"
            cfg = self.mod.load_eval_config()
            self.assertEqual(cfg, {})
        finally:
            self.mod.CONFIG = orig
