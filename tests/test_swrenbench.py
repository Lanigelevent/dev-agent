# -*- coding: utf-8 -*-
"""tests/test_swrenbench.py — swrenbench-import.py 契约（round-112，P0-2）。

覆盖：字段容错映射、diff + 行解析（新文件行号）、ground-truth 片段定位、
确定性打分桥（point recall / clean 噪声）、import 计数与坏行。
"""
import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "swrenbench-import.py"


def _load():
    spec = importlib.util.spec_from_file_location("swr_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DIFF1 = (
    "diff --git a/m.py b/m.py" + chr(10)
    + "--- a/m.py" + chr(10)
    + "+++ b/m.py" + chr(10)
    + "@@ -1,2 +1,3 @@" + chr(10)
    + " x = 1" + chr(10)
    + "+def f(x={}):" + chr(10)
    + "+    pass" + chr(10)
    + " y = 2" + chr(10)
)


class SwrenbenchTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="swr-"))
        self.addCleanup(tmpspace.release, self.tmp)
        self._saved_provider = os.environ.get("CRA_LLM_PROVIDER")
        self.addCleanup(self._restore_provider)

    def test_map_instance_tolerant(self):
        raw = {
            "instance_id": "x__repo-1", "repo": "x/repo",
            "pr_title": "fix bug", "change_introduced": True,
            "pr_commits": [{"files": [{"filename": "m.py",
                                       "patch": DIFF1}]}],
            "changes": [{"change_type": "F.2 Logic",
                         "change_introducing": {
                             "code_snippet": "def f(x={}):" + chr(10)
                             + "    pass"}}],
        }
        s = self.mod.map_instance(raw)
        self.assertEqual(s["instance_id"], "x__repo-1")
        self.assertTrue(s["change_introduced"])
        self.assertEqual(len(s["diffs"]), 1)
        self.assertEqual(s["changes"][0]["change_type"], "F.2 Logic")
        self.assertIn("def f(x={})", s["changes"][0]["snippet"])

    def test_added_lines_new_numbering(self):
        added = self.mod._added_lines(DIFF1)
        self.assertEqual(added[0], (2, "def f(x={}):"))
        self.assertEqual(added[1], (3, "    pass"))

    def test_snippet_spans_locate(self):
        spans = self.mod._snippet_spans(DIFF1, "def f(x={}):" + chr(10)
                                        + "    pass")
        self.assertEqual(spans, {2, 3})

    def test_score_point_recall_and_clean_noise(self):
        corpus = self.tmp / "slim.jsonl"
        rows = [
            {"instance_id": "chg-1", "repo": "r", "pr_title": "t",
             "change_introduced": True,
             "changes": [{"change_type": "F.2 Logic",
                          "snippet": "def f(x={}):"}],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
            {"instance_id": "clean-1", "repo": "r", "pr_title": "t",
             "change_introduced": False, "changes": [],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
        ]
        with corpus.open("w", encoding="utf-8", newline=chr(10)) as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + chr(10))
        mod = _load()
        rc, out = self._invoke(["score", "--corpus", str(corpus)])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["samples"], 2)
        self.assertEqual(d["changes_total"], 1)
        self.assertEqual(d["caught"], 1)
        self.assertEqual(d["point_recall"], 1.0)
        self.assertEqual(d["clean_prs"], 1)
        # clean PR 上同一 diff 有 1 条 mutable-default 命中 → 零噪声占比 0
        self.assertEqual(d["clean_zero_noise"], 0.0)
        self.assertEqual(d["clean_noise_findings"], 1)

    def test_import_counts_and_bad_lines(self):
        data = self.tmp / "raw.jsonl"
        good = json.dumps({
            "instance_id": "a__b-1", "repo": "a/b", "pr_title": "t",
            "change_introduced": True,
            "pr_commits": [{"files": [{"filename": "m.py",
                                       "patch": DIFF1}]}],
            "changes": []}, ensure_ascii=False)
        with data.open("w", encoding="utf-8", newline=chr(10)) as f:
            f.write(good + chr(10))
            f.write("{broken" + chr(10))
            f.write(chr(10))
        rc, out = self._invoke(["import", "--data", str(data),
                                "--out", str(self.tmp / "corp")])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["change"], 1)
        self.assertEqual(d["clean"], 0)
        self.assertEqual(d["bad"], 1)
        slim = (self.tmp / "corp" / "swr-slim.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(slim), 1)

    def _restore_provider(self):
        if self._saved_provider is None:
            os.environ.pop("CRA_LLM_PROVIDER", None)
        else:
            os.environ["CRA_LLM_PROVIDER"] = self._saved_provider

    def test_review_pending_writes_all_prompts(self):
        corpus, _ = self._corpus2()
        out = self.tmp / "rev"
        rc, out_s = self._invoke(["review", "--corpus", str(corpus),
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertTrue(d["wait_host_llm"])
        self.assertEqual(d["pending_count"], 2)
        self.assertEqual(len(d["tasks"]), 2)
        prompts = list((out / "llm-tasks").glob("*.prompt.md"))
        self.assertEqual(len(prompts), 2)
        fp = out / "findings.json"
        self.assertTrue(fp.is_file())
        data = json.loads(fp.read_text(encoding="utf-8"))
        self.assertEqual(data["reviewer"], "host")
        self.assertEqual(data["samples"], {})
    def test_review_cache_hit_completes(self):
        corpus, rows = self._corpus2()
        out = self.tmp / "rev"
        sys.path.insert(0, str(ROOT))
        from llm import provider
        for s in rows:
            system, user, _ = self.mod.build_review_prompt(s, 20000)
            tid = provider.task_id(system, user)
            resp = out / "llm-tasks" / (tid + ".response.md")
            resp.parent.mkdir(parents=True, exist_ok=True)
            body = "[]"
            if s["change_introduced"]:
                body = json.dumps([{"loc": "m.py:2", "desc": "d",
                                    "evidence": "e", "severity": "中",
                                    "confidence": "中", "cause": "c",
                                    "fix": "f"}], ensure_ascii=False)
            resp.write_text(body, encoding="utf-8")
        rc, out_s = self._invoke(["review", "--corpus", str(corpus),
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["samples"], 2)
        self.assertEqual(d["findings"], 1)
        data = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        self.assertIn("chg-1", data["samples"])
        self.assertEqual(len(data["samples"]["chg-1"]), 1)
        self.assertEqual(data["samples"]["clean-1"], [])
    def test_review_unparseable_records(self):
        corpus, rows = self._corpus2()
        out = self.tmp / "rev"
        sys.path.insert(0, str(ROOT))
        from llm import provider
        for s in rows:
            system, user, _ = self.mod.build_review_prompt(s, 20000)
            tid = provider.task_id(system, user)
            (out / "llm-tasks").mkdir(parents=True, exist_ok=True)
            (out / "llm-tasks" / (tid + ".response.md")).write_text(
                "不是JSON的乱文本", encoding="utf-8")
        rc, out_s = self._invoke(["review", "--corpus", str(corpus),
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["unparsed"], 2)
        data = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["unparsed"]), 2)
        self.assertEqual(data["samples"]["chg-1"], [])
        self.assertEqual(data["samples"]["clean-1"], [])
    def test_judge_metrics_math(self):
        corpus, _ = self._corpus3()
        out = self.tmp / "j1"
        out.mkdir(parents=True)
        fd = out / "findings.json"
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py:2", "desc": "d"}],
                "chg-2": [{"loc": "m.py:99", "desc": "d"}],
                "clean-1": [],
            }}, ensure_ascii=False), encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd)])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["n_evaluated"], 3)
        self.assertEqual(d["pr_level"]["tp"], 2)
        self.assertEqual(d["pr_level"]["fp"], 0)
        self.assertEqual(d["pr_level"]["fn"], 0)
        self.assertEqual(d["pr_level"]["f1"], 1.0)
        self.assertEqual(d["point_level"]["tp"], 1)
        self.assertEqual(d["point_level"]["fp"], 1)
        self.assertEqual(d["point_level"]["fn"], 2)
        self.assertEqual(d["point_level"]["precision"], 0.5)
        self.assertEqual(d["point_level"]["recall"], 0.3333)
        self.assertEqual(d["point_level"]["f1"], 0.4)
        self.assertEqual(d["point_level"]["gt_points"], 3)
        self.assertEqual(d["point_level"]["macro_f1_mean"], 0.5)

    def test_judge_skips_unreviewed(self):
        corpus, _ = self._corpus3()
        out = self.tmp / "j2"
        out.mkdir(parents=True)
        fd = out / "findings.json"
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py:2", "desc": "d"}],
            }}, ensure_ascii=False), encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd)])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["n_evaluated"], 1)
        self.assertEqual(d["n_change"], 1)
        self.assertEqual(d["n_clean"], 0)

    def test_judge_unparseable_loc_counts_fp(self):
        corpus, _ = self._corpus3()
        out = self.tmp / "j3"
        out.mkdir(parents=True)
        fd = out / "findings.json"
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py", "desc": "d"}],
            }}, ensure_ascii=False), encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd)])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["point_level"]["unparseable_loc"], 1)
        self.assertEqual(d["point_level"]["fp"], 1)
        self.assertEqual(d["pr_level"]["tp"], 1)

    def _corpus2(self):
        rows = [
            {"instance_id": "chg-1", "repo": "r", "pr_title": "t",
             "change_introduced": True,
             "changes": [{"change_type": "F.2 Logic",
                          "snippet": "def f(x={}):"}],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
            {"instance_id": "clean-1", "repo": "r", "pr_title": "t",
             "change_introduced": False, "changes": [],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
        ]
        corpus = self.tmp / "slim2.jsonl"
        with corpus.open("w", encoding="utf-8", newline=chr(10)) as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + chr(10))
        return corpus, rows

    def _corpus3(self):
        rows = [
            {"instance_id": "chg-1", "repo": "r", "pr_title": "t",
             "change_introduced": True,
             "changes": [{"change_type": "F.2 Logic",
                          "snippet": "def f(x={}):"}],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
            {"instance_id": "chg-2", "repo": "r", "pr_title": "t",
             "change_introduced": True,
             "changes": [{"change_type": "F.2 Logic",
                          "snippet": "def f(x={}):"},
                         {"change_type": "F.3 Structure",
                          "snippet": "pass"}],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
            {"instance_id": "clean-1", "repo": "r", "pr_title": "t",
             "change_introduced": False, "changes": [],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
            {"instance_id": "clean-1", "repo": "r", "pr_title": "t",
             "change_introduced": False, "changes": [],
             "diffs": [{"file": "m.py", "patch": DIFF1}]},
        ]
        corpus = self.tmp / "slim3.jsonl"
        with corpus.open("w", encoding="utf-8", newline=chr(10)) as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + chr(10))
        return corpus, rows
    def test_judge_semantic_pending_writes_prompts(self):
        corpus, _ = self._corpus2()
        out = self.tmp / "js1"
        fd = out / "findings.json"
        out.mkdir(parents=True)
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py:99", "desc": "d"}],
                "clean-1": [],
            }}, ensure_ascii=False), encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd), "--match", "semantic",
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 1)
        self.assertTrue(d["wait_host_llm"])
        self.assertEqual(d["pending_count"], 1)
        prompts = list(out.glob("llm-tasks/*.prompt.md"))
        self.assertEqual(len(prompts), 1)

    def test_judge_semantic_cache_hit_completes(self):
        corpus, rows = self._corpus3()
        out = self.tmp / "js2"
        fd = out / "findings.json"
        out.mkdir(parents=True)
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py:99", "desc": "mutable default",
                           "evidence": "def f(x={})"}],
                "chg-2": [],
            }}, ensure_ascii=False), encoding="utf-8")
        sys.path.insert(0, str(ROOT))
        from llm import provider
        row = rows[0]
        system, user, _, _ = self.mod.build_judge_prompt(
            row, [{"loc": "m.py:99", "desc": "mutable default",
                   "evidence": "def f(x={})"}], 20000)
        tid = provider.task_id(system, user)
        (out / "llm-tasks").mkdir(parents=True, exist_ok=True)
        (out / "llm-tasks" / (tid + ".response.md")).write_text(
            json.dumps({"matches": [{"gt": 0, "findings": [0]}]}),
            encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd), "--match", "semantic",
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(d["n_judged"], 1)
        self.assertEqual(d["point_level_semantic"]["tp"], 1)
        self.assertEqual(d["point_level_semantic"]["fp"], 0)

    def test_judge_semantic_unparseable_counts(self):
        corpus, rows = self._corpus3()
        out = self.tmp / "js3"
        fd = out / "findings.json"
        out.mkdir(parents=True)
        fd.write_text(json.dumps({
            "reviewer": "host", "samples": {
                "chg-1": [{"loc": "m.py:2", "desc": "d"}],
            }}, ensure_ascii=False), encoding="utf-8")
        sys.path.insert(0, str(ROOT))
        from llm import provider
        row = rows[0]
        system, user, _, _ = self.mod.build_judge_prompt(
            row, [{"loc": "m.py:2", "desc": "d"}], 20000)
        tid = provider.task_id(system, user)
        (out / "llm-tasks").mkdir(parents=True, exist_ok=True)
        (out / "llm-tasks" / (tid + ".response.md")).write_text(
            "乱文本不是JSON", encoding="utf-8")
        rc, out_s = self._invoke(["judge", "--corpus", str(corpus),
                                  "--findings", str(fd), "--match", "semantic",
                                  "--out", str(out), "--all-pending"])
        d = json.loads(out_s)
        self.assertEqual(rc, 0)
        self.assertEqual(len(d["unparsed"]), 1)
        self.assertEqual(d["point_level_semantic"]["tp"], 0)
        self.assertEqual(d["point_level_semantic"]["fp"], 1)

    def test_judge_prompt_build_shape(self):
        corpus, rows = self._corpus3()
        system, user, truncated, groups = self.mod.build_judge_prompt(
            rows[1], [{"loc": "m.py:2", "desc": "x"}], 20000)
        self.assertEqual(len(groups), 2)
        self.assertEqual([len(g["members"]) for g in groups], [1, 1])
        self.assertEqual(groups[0]["type"], "F.2 Logic")
        self.assertFalse(truncated)
        self.assertIn("[0] 类型 F.2 Logic", user)
        self.assertIn("[1] 类型 F.3 Structure", user)
        self.assertIn("[0] loc: m.py:2", user)
    def test_dedupe_gt_merges_duplicates(self):
        row = {
            "instance_id": "x", "change_introduced": True,
            "changes": [
                {"change_type": "E.1.1", "snippet": "def f(x={}):"},
                {"change_type": "F.1", "snippet": "def f(x={}):"},
                {"change_type": "F.2", "snippet": "    pass"},
            ],
            "diffs": [{"file": "m.py", "patch": DIFF1}],
        }
        groups = self.mod._dedupe_gt(row)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]["members"]), 2)
        self.assertEqual(groups[0]["members"], [0, 1])
        self.assertEqual(groups[1]["members"], [2])
        self.assertEqual(groups[0]["type"], "E.1.1")
    def _invoke(self, argv):
        old = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["swrenbench-import.py"] + argv
            with contextlib.redirect_stdout(out):
                rc = self.mod.main()
        finally:
            sys.argv = old
        return rc, out.getvalue()


if __name__ == "__main__":
    unittest.main()
