# -*- coding: utf-8 -*-
"""tests/test_f2p_quality.py — f2p-quality.py 契约（round-106）。

覆盖：标签形状判别、django 标签→文件解析（含 tests/ 变体）、
test_patch 触及交叉核对、10880 选批过滤、JSONL 进出、退出码。
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
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "f2p-quality.py"


def _load():
    spec = importlib.util.spec_from_file_location("f2p_quality_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _invoke(argv):
    mod = _load()
    old = sys.argv
    out = io.StringIO()
    try:
        sys.argv = ["f2p-quality.py"] + argv
        with contextlib.redirect_stdout(out):
            rc = mod.main()
    finally:
        sys.argv = old
    return rc, out.getvalue()


GOOD_LABEL = "test_count_distinct_expression (aggregation.tests.AggregateTestCase)"
TEST_PATCH = "diff --git a/tests/aggregation/tests.py b/tests/aggregation/tests.py\n--- a/tests/aggregation/tests.py\n+++ b/tests/aggregation/tests.py\n"


def _row(iid="demo__demo-1", labels=None, tpatch=TEST_PATCH, patch=None):
    row = {"instance_id": iid, "test_patch": tpatch,
           "fail_to_pass": labels if labels is not None else [GOOD_LABEL]}
    if patch is not None:
        row["patch"] = patch
    return row


def _write_tasks(tmp, rows):
    fp = tmp / "tasks.jsonl"
    with fp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(fp)


class F2pQualityTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="f2pq-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def test_label_shape_prose_rejected(self):
        rc, out = _invoke(["--tasks", _write_tasks(self.tmp, [
            _row(labels=["this patch fixes the ordering bug in queries"])])])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        v = d["verdicts"][0]
        self.assertEqual(v["verdict"], "blocked_quality")
        self.assertTrue(any("label_not_node_id" in r for r in v["reasons"]))

    def test_django_label_resolves_tests_variant(self):
        cands = self.mod._label_file_candidates(GOOD_LABEL)
        self.assertIn("aggregation/tests.py", cands)
        self.assertIn("tests/aggregation/tests.py", cands)

    def test_f2p_file_not_in_test_patch_blocked(self):
        orphan = "test_x (mismod.tests.SomeTests)"
        rc, out = _invoke(["--tasks", _write_tasks(self.tmp, [
            _row(labels=[GOOD_LABEL, orphan])])])
        d = json.loads(out)
        v = d["verdicts"][0]
        self.assertEqual(v["verdict"], "blocked_quality")
        self.assertTrue(any("f2p_file_not_in_test_patch" in r
                            for r in v["reasons"]))

    def test_ok_instance_and_select_10880(self):
        patch = ("diff --git a/django/a.py b/django/a.py\n"
                 "diff --git a/django/b.py b/django/b.py\n")
        rc, out = _invoke(["--tasks",
                           _write_tasks(self.tmp, [_row(patch=patch)]),
                           "--select",
                           "--select-out", str(self.tmp / "sel.jsonl")])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["summary"]["selected_10880"], 1)
        self.assertEqual(d["selected_written"], 1)
        sel = json.loads((self.tmp / "sel.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(sel["instance_id"], "demo__demo-1")

    def test_select_rejects_big_patch(self):
        patch = "".join("diff --git a/f%d.py b/f%d.py\n" % (i, i)
                        for i in range(5))
        rc, out = _invoke(["--tasks",
                           _write_tasks(self.tmp, [_row(patch=patch)]),
                           "--select"])
        d = json.loads(out)
        self.assertEqual(d["summary"]["selected_10880"], 0)

    def test_missing_tasks_rc2(self):
        rc, out = _invoke(["--tasks", str(self.tmp / "no.jsonl")])
        self.assertEqual(rc, 2)

    def test_official_f2p_json_string_accepted(self):
        # 官方 parquet schema：FAIL_TO_PASS 为 JSON 编码字符串
        row = _row()
        row["FAIL_TO_PASS"] = json.dumps([GOOD_LABEL])
        del row["fail_to_pass"]
        rc, out = _invoke(["--tasks",
                           _write_tasks(self.tmp, [row]), "--select"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["summary"]["ok_count"], 1)


if __name__ == "__main__":
    unittest.main()
