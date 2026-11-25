#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_scripts_precision_gate.py — AB-03 提示面回归门契约（r198）。

record-baseline 固化指纹 → check PASS；声明文件变更 → PROMPT_DRIFT 必抓
（反向验证）；未声明面 SKIPPED 不误伤；基线缺指纹段 FAIL 并指路。
"""
import importlib.util
import json
import shutil
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "precision-gate.py"

JUDGE = {"ok": True, "precision": 0.7, "valid_samples": 10,
         "reviewer": "deterministic"}


def _load():
    spec = importlib.util.spec_from_file_location("pg_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PromptRegressionTests(unittest.TestCase):
    """AB-03：提示面回归门（声明式变更即红的确定性形态）。"""

    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tempfile.mkdtemp(prefix="pg-r198-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.watch = self.tmp / "prompt-watch.json"
        self.baseline_path = self.tmp / "precision-baseline.json"
        self.mod.PROMPT_WATCH = self.watch
        self.mod.ROOT = self.tmp  # 声明面相对声明根（测试=临时根）
        self.baseline = {"floor": 0.65, "tolerance": 0.01,
                         "precision": 0.7, "valid_samples": 10,
                         "reviewer": "deterministic"}

    def _argv(self, judge_path):
        return types.SimpleNamespace(judge=str(judge_path),
                                     baseline=str(self.baseline_path))

    def test_skip_when_undeclared(self):
        self.baseline_path.write_text(json.dumps(self.baseline), encoding="utf-8")
        out = json.loads(self.mod._prompt_regression_check(self.baseline) and
                         json.dumps(self.mod._prompt_regression_check(
                             self.baseline)))
        self.assertEqual(out["status"], "SKIPPED")

    def test_fail_when_baseline_lacks_fingerprints(self):
        self.watch.write_text(json.dumps(
            {"watched": ["agent/repo_map.py"]}), encoding="utf-8")
        self.baseline_path.write_text(json.dumps(self.baseline), encoding="utf-8")
        check = self.mod._prompt_regression_check(self.baseline)
        self.assertEqual(check["status"], "FAIL")
        self.assertIn("record-baseline", check["note"])

    def test_record_then_pass_then_drift_caught(self):
        # 反向验证：声明文件被改后 check 必红（PROMPT_DRIFT），changed 列出文件
        watched = self.tmp / "watched_prompt.py"
        watched.write_text("PROMPT_V1 = 'judge prompt'\n", encoding="utf-8")
        rel = "watched_prompt.py"
        self.watch.write_text(json.dumps({"watched": [rel]}), encoding="utf-8")
        self.baseline_path.write_text(json.dumps(self.baseline), encoding="utf-8")
        judge_path = self.tmp / "judge.json"
        judge_path.write_text(json.dumps(JUDGE), encoding="utf-8")
        self.mod.cmd_record_baseline(self._argv(judge_path))
        base = json.loads(self.baseline_path.read_text(encoding="utf-8"))
        self.assertIn(rel, base.get("prompt_fingerprints", {}))
        check = self.mod._prompt_regression_check(base)
        self.assertEqual(check["status"], "PASS", check)
        watched.write_text("PROMPT_V2 = 'changed judge prompt'\n",
                           encoding="utf-8")
        check = self.mod._prompt_regression_check(base)
        self.assertEqual(check["status"], "FAIL")
        self.assertEqual(check["changed"], [rel])


if __name__ == "__main__":
    unittest.main()
