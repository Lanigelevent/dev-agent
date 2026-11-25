# -*- coding: utf-8 -*-
"""tests/test_scripts_precision_report.py — precision-report.py 纯函数契约（round-125）。

锁定两件事：
1. _load_real：judge JSON 抽取（recall/precision/claimed/grounded/valid_samples/weak）
   + per_sample 直查；samples.json 存在时按 defect_class 交叉统计覆盖矩阵
   （按 total 降序，同组保持稳定）；
2. _aggregate_real：多 repo 条目跨仓合计 recall/precision（分母为 0 → None）、
   class_coverage 合并、per_repo 列表透传、空 entries → None。
文件名匹配 test_scripts_*.py，自动进入覆盖率固定子集。
"""
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "precision-report.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "precision_report_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


class TestLoadReal(unittest.TestCase):
    """_load_real：judge 抽取 + defect_class 覆盖矩阵。"""

    def setUp(self):
        tmp = tmpspace.create(prefix="precision-load-")
        self.addCleanup(tmpspace.release, tmp)
        self.tmp = Path(tmp)
        self.judge_path = self.tmp / "judge.json"
        self.samples_path = self.tmp / "samples.json"
        self.judge = {
            "recall": 0.5, "precision": 0.75,
            "claimed": 2, "grounded": 1,
            "valid_samples": 4, "weak": 1,
            "per_sample": [
                {"sample_id": "a", "claimed": True},
                {"sample_id": "b", "claimed": False},
                {"sample_id": "c", "claimed": True},
            ],
        }
        self.samples = {
            "samples": [
                {"sample_id": 1, "defect_class": "X", "fix_commit": "a"},
                {"sample_id": 2, "defect_class": "Y", "fix_commit": "b"},
                {"sample_id": 3, "defect_class": "X", "fix_commit": "c"},
                {"sample_id": 4, "defect_class": "Z", "fix_commit": "d"},
            ],
        }
        _write(self.judge_path, self.judge)
        _write(self.samples_path, self.samples)

    def test_without_samples_returns_judge_fields(self):
        mod = _load()
        meta = mod._load_real(str(self.judge_path), None, "repoA")
        self.assertEqual(meta["repo"], "repoA")
        self.assertEqual(meta["judge"]["recall"], 0.5)
        self.assertEqual(meta["judge"]["precision"], 0.75)
        self.assertEqual(meta["judge"]["valid_samples"], 4)
        self.assertEqual(len(meta["per_sample"]), 3)
        self.assertNotIn("class_coverage", meta)

    def test_with_samples_builds_class_matrix_sorted(self):
        mod = _load()
        meta = mod._load_real(str(self.judge_path),
                              str(self.samples_path), "repoA")
        self.assertEqual(meta["class_coverage"], [
            {"defect_class": "X", "total": 2, "claimed": 2},
            {"defect_class": "Y", "total": 1, "claimed": 0},
            {"defect_class": "Z", "total": 1, "claimed": 0},
        ])


def _entry(repo, claimed, grounded, valid, weak, cls_rows):
    return {"repo": repo,
            "judge": {"recall": None, "precision": None,
                      "claimed": claimed, "grounded": grounded,
                      "valid_samples": valid, "weak": weak},
            "per_sample": [],
            "class_coverage": cls_rows}


class TestAggregateReal(unittest.TestCase):
    """_aggregate_real：跨仓合计 + class_coverage 合并 + 分母零口径。"""

    def test_empty_entries_returns_none(self):
        self.assertIsNone(_load()._aggregate_real([]))

    def test_merge_two_repos(self):
        mod = _load()
        e1 = _entry("repoA", 3, 2, 6, 0,
                    [{"defect_class": "X", "total": 2, "claimed": 1}])
        e2 = _entry("repoB", 1, 0, 2, 1,
                    [{"defect_class": "Y", "total": 1, "claimed": 1}])
        agg = mod._aggregate_real([e1, e2])
        self.assertEqual(agg["valid_samples"], 8)
        self.assertEqual(agg["claimed"], 4)
        self.assertEqual(agg["grounded"], 2)
        self.assertEqual(agg["weak"], 1)
        self.assertEqual(agg["recall"], 0.25)
        self.assertEqual(agg["precision"], 0.5)
        self.assertEqual(agg["class_coverage"], [
            {"defect_class": "X", "total": 2, "claimed": 1},
            {"defect_class": "Y", "total": 1, "claimed": 1},
        ])
        self.assertEqual([r["repo"] for r in agg["per_repo"]],
                         ["repoA", "repoB"])

    def test_zero_denominators_yield_none(self):
        agg = _load()._aggregate_real([_entry("r", 0, 0, 0, 0, [])])
        self.assertIsNone(agg["recall"])
        self.assertIsNone(agg["precision"])
        self.assertEqual(agg["valid_samples"], 0)


if __name__ == "__main__":
    unittest.main()
