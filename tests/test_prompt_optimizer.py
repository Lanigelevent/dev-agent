# -*- coding: utf-8 -*-
"""tests/test_prompt_optimizer.py — AB-06 提示优化循环契约（round-217）。

反向验证面（红线 6）：precision 下降必须 REJECTED（不许降红线）、无评审
臂必须 blocked 不冒充已评、基线缺失必须 REJECTED（blocked_no_baseline）。
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/eval-harness/scripts/prompt-optimizer.py"


def _run(args, env_extra=None):
    env = dict(os.environ)
    env.pop("CRA_LLM_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, timeout=60, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


class TestPromptOptimizer(unittest.TestCase):
    """plan/adopt 闸/blocked 评估五面。"""

    def test_plan_matrix_from_watch(self):
        rc, out = _run(["plan"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertGreater(d["surfaces"], 0, "prompt-watch 监视面必须非空")
        self.assertGreater(len(d["variants"]), d["surfaces"],
                           "变体矩阵必须按维度展开")
        self.assertTrue(all("surface" in v and "dimension" in v
                            for v in d["variants"]))

    def test_adopt_gate_allows_no_regression(self):
        with tempfile.TemporaryDirectory() as td:
            pf = Path(td) / "p.md"
            pf.write_text("评审提示变体内容", encoding="utf-8")
            mf = Path(td) / "m.json"
            mf.write_text(json.dumps({"precision": 0.70,
                                      "baseline_precision": 0.6667}),
                          encoding="utf-8")
            rc, out = _run(["adopt", "--variant", "v1",
                            "--metrics", str(mf),
                            "--prompt-file", str(pf),
                            "--out", td])
            d = json.loads(out)
            self.assertEqual((rc, d["verdict"]), (0, "ADOPTED"))
            self.assertTrue(d.get("fingerprint"), "采纳必须落指纹")
            self.assertTrue(Path(d["exported_to"]).is_file())

    def test_adopt_gate_rejects_regression(self):
        with tempfile.TemporaryDirectory() as td:
            mf = Path(td) / "m.json"
            mf.write_text(json.dumps({"precision": 0.60,
                                      "baseline_precision": 0.6667}),
                          encoding="utf-8")
            rc, out = _run(["adopt", "--variant", "v2",
                            "--metrics", str(mf)])
            d = json.loads(out)
            self.assertEqual((rc, d["verdict"]), (0, "REJECTED"))
            self.assertTrue(any("不许降" in r for r in d["reasons"]),
                            "下降必须给不许降理由")
            self.assertTrue(any("0.65" in r for r in d["reasons"]),
                            "低于地板必须给地板理由")

    def test_adopt_blocked_no_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            mf = Path(td) / "m.json"
            mf.write_text("{}", encoding="utf-8")
            rc, out = _run(["adopt", "--variant", "v3",
                            "--metrics", str(mf)])
            d = json.loads(out)
            self.assertEqual(rc, 1)
            self.assertIn("blocked_no_baseline", d["reasons"])

    def test_evaluate_blocked_no_judge(self):
        with tempfile.TemporaryDirectory() as td:
            pf = Path(td) / "p.md"
            pf.write_text("x", encoding="utf-8")
            rc, out = _run(["evaluate", "--variant", "v1",
                            "--prompt-file", str(pf)])
            d = json.loads(out)
            self.assertEqual((rc, d["arm_status"]), (0, "blocked_no_judge"))
            self.assertFalse(d["scored"], "无评审臂不得冒充已评")


if __name__ == "__main__":
    unittest.main()
