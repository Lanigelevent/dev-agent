#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_eval_metrics.py — AB-02 质量指标 pytest 化（r201）。

DeepEval「指标写成 pytest 断言进 CI」的方案复用（导入不可行：41 包依赖面
+ live LLM 需求；确定性形态）。三指标格进标准套件 = nightly CI 指标网格：
①precision 地板（round65 固定 judge 产物 → precision-gate check）
②trace 评测集分数（Tracer fixture → trace-export → 阈值断言；AB-01 评测集
  的套件内消费者——r199 勘误闭环）
③评审质量门（D-053 四项检查在合成 findings 上正反双验）

产物缺失时 SKIP（不假红）；阈值随基线演进。
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRECISION_GATE = ROOT / "skills" / "eval-harness" / "scripts" / "precision-gate.py"
TRACE_EXPORT = ROOT / "skills" / "eval-harness" / "scripts" / "trace-export.py"
QUALITY_GATE = ROOT / "skills" / "eval-harness" / "scripts" / "review-quality-gate.py"
JUDGE_ARTIFACT = ROOT / "reports" / "precision-gate-round65" / "judge.json"
PRECISION_FLOOR = 0.65
TRACE_SCORE_FLOOR = 0.7


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_gate(script, args):
    proc = subprocess.run(
        [sys.executable, str(script)] + args, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=120)
    return proc


class PrecisionFloorMetric(unittest.TestCase):
    """指标格①：precision 地板（固定 judge 产物对账，含提示面指纹检查）。"""

    def setUp(self):
        if not JUDGE_ARTIFACT.is_file():
            self.skipTest("precision judge 产物缺失（round65）")

    def test_precision_floor_and_prompt_regression(self):
        proc = _run_gate(PRECISION_GATE,
                         ["check", "--judge", str(JUDGE_ARTIFACT)])
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)
        precision = (payload.get("metrics") or {}).get("precision")
        self.assertIsNotNone(precision)
        self.assertGreaterEqual(float(precision), PRECISION_FLOOR)


class TraceEvalSetMetric(unittest.TestCase):
    """指标格②：trace 评测集分数（AB-01 导出器套件内消费者 + 阈值断言）。"""

    def test_trace_eval_set_score_floor(self):
        trace_mod = _load(
            "trace_mod_metric", ROOT / "agent" / "trace.py")
        with tempfile.TemporaryDirectory(prefix="eval-metric-") as tmp:
            tmp = Path(tmp)
            tr = trace_mod.Tracer("sess-eval-metric", trace_dir=str(tmp))
            tr.span("llm", "call_end", duration_ms=5,
                    token_input=3, token_output=5, cost_usd=0.001)
            tr.score("review_precision", 0.83, comment="AB-02 指标格回灌")
            proc = _run_gate(TRACE_EXPORT,
                             ["--trace", str(tr.path), "--require-score",
                              "--out", str(tmp / "eval-set.json")])
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            data = json.loads((tmp / "eval-set.json").read_text(
                encoding="utf-8"))
            self.assertEqual(data["schema"], "trace-eval-set/1")
            scores = [s for s in data["scores"]
                      if s["name"] == "review_precision"]
            self.assertTrue(scores, "评测集应含 review_precision 分数")
            self.assertGreaterEqual(float(scores[0]["value"]),
                                    TRACE_SCORE_FLOOR)


class ReviewQualityGateMetric(unittest.TestCase):
    """指标格③：评审质量门（D-053 四项检查正反双验）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="eval-quality-")

    def _findings(self, empty_no_evidence=False):
        # 形状：顶层 {"samples": {样本id: [findings]}}（load_findings 契约）
        if empty_no_evidence:
            # 反向样例：零样本且无依据（D-053 必抓形态）
            return {"samples": {}, "batch_note": ""}
        return {"samples": {"sample-1": [
            {"id": "f1", "dimension": "安全",
             "evidence": "L42 使用 eval() 执行外部输入",
             "severity": "high", "confidence": "high",
             "reason": "注入面", "fix_hint": "改 ast.literal_eval"}]},
            "batch_note": "单文件评审，证据齐备"}

    def test_quality_gate_pass_on_good_findings(self):
        fpath = Path(self.tmp) / "good.json"
        fpath.write_text(json.dumps(self._findings(), ensure_ascii=False),
                         encoding="utf-8")
        proc = _run_gate(QUALITY_GATE, ["check", "--findings", str(fpath)])
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"], payload)

    def test_quality_gate_catches_empty_no_evidence(self):
        # 反向验证：全 [] 无依据批次必红（D-053 前置硬校验）
        fpath = Path(self.tmp) / "bad.json"
        fpath.write_text(json.dumps(self._findings(empty_novidence := True),
                                    ensure_ascii=False), encoding="utf-8")
        proc = _run_gate(QUALITY_GATE, ["check", "--findings", str(fpath)])
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"], payload)


if __name__ == "__main__":
    unittest.main()
