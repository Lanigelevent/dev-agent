# -*- coding: utf-8 -*-
"""tests/test_scripts_latency_bench.py — latency-bench.py 契约（r154 基准 / r155 SLO 门禁）。

覆盖：合成 diff 确定性且含规则命中形态、分档结果结构与档名字段、
run 退出码 2（rules 缺失）、check 三态（PASS rc=0 / SLO 超限 rc=1 / 输入错误 rc=2）。
红线 6 反向验证：假 rules 实跑计时链路；造 p95 超限报告确认 check 抓得住。
"""
import argparse
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "latency-bench.py"


def _load():
    spec = importlib.util.spec_from_file_location("lb_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class LatencyBenchTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="lbench-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def test_synth_diff_deterministic_with_hits(self):
        d1 = self.mod._synth_diff(100)
        d2 = self.mod._synth_diff(100)
        self.assertEqual(d1, d2)
        self.assertIn("def f(x={}, y=None):", d1)
        self.assertIn("x == None", d1)
        self.assertIn("@@", d1)

    def test_run_tier_structure(self):
        # 假 rules：真子进程、立即输出固定 findings（红线 6 计时链路实跑）
        rules = self.tmp / "fake_rules.py"
        rules.write_text(
            "import json, sys\n"
            "sys.stdout.write(json.dumps({'findings': [1, 2]}))\n",
            encoding="utf-8")
        r = self.mod.run_tier(rules, "S", 50, 2, 30, str(self.tmp))
        self.assertEqual(r["name"], "S")
        self.assertEqual(r["lines"], 50)
        self.assertEqual(r["runs"], 2)
        self.assertEqual(r["findings"], 2)
        self.assertGreater(r["min"], 0)
        self.assertGreaterEqual(r["p95"], r["p50"])

    def test_missing_rules_rc2(self):
        old = sys.argv
        out = io.StringIO()
        try:
            sys.argv = ["latency-bench.py", "run", "--rules",
                        str(self.tmp / "no.py")]
            with contextlib.redirect_stdout(out):
                rc = self.mod.main()
        finally:
            sys.argv = old
        self.assertEqual(rc, 2)

    def _check(self, report, slo=""):
        ns = argparse.Namespace(report=str(report), slo=slo)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = self.mod.cmd_check(ns)
        return rc, json.loads(out.getvalue())

    def test_check_pass_rc0(self):
        rep = self.tmp / "rep.json"
        rep.write_text(json.dumps({
            "mode": "latency-bench",
            "tiers": [{"name": "S", "lines": 100, "p95": 0.2},
                      {"name": "M", "lines": 500, "p95": 0.2},
                      {"name": "L", "lines": 2000, "p95": 0.3}],
        }), encoding="utf-8")
        rc, out = self._check(rep)
        self.assertEqual(rc, 0)
        self.assertTrue(out["ok"])
        self.assertTrue(all(v["verdict"] == "PASS" for v in out["verdicts"]))

    def test_check_fail_rc1(self):
        # 红线 6 反向验证：造超限样例确认抓得住
        rep = self.tmp / "rep-fail.json"
        rep.write_text(json.dumps({
            "mode": "latency-bench",
            "tiers": [{"name": "S", "lines": 100, "p95": 0.2},
                      {"name": "M", "lines": 500, "p95": 3.5},
                      {"name": "L", "lines": 2000, "p95": 0.3}],
        }), encoding="utf-8")
        rc, out = self._check(rep)
        self.assertEqual(rc, 1)
        self.assertFalse(out["ok"])
        verdicts = {v["tier"]: v["verdict"] for v in out["verdicts"]}
        self.assertEqual(verdicts["M"], "FAIL")
        self.assertEqual(verdicts["S"], "PASS")

    def test_check_missing_report_rc2(self):
        rc, out = self._check(self.tmp / "no.json")
        self.assertEqual(rc, 2)
        self.assertFalse(out["ok"])

    def test_check_malformed_report_rc2(self):
        rep = self.tmp / "bad.json"
        rep.write_text("{not json", encoding="utf-8")
        rc, out = self._check(rep)
        self.assertEqual(rc, 2)
        self.assertFalse(out["ok"])

    def test_check_legacy_report_by_lines(self):
        # 旧格式报告（无 name，按 lines 反查档名）仍可判
        rep = self.tmp / "legacy.json"
        rep.write_text(json.dumps({
            "mode": "latency-bench",
            "tiers": [{"lines": 100, "p95": 0.2},
                      {"lines": 500, "p95": 0.2},
                      {"lines": 2000, "p95": 0.3}],
        }), encoding="utf-8")
        rc, out = self._check(rep)
        self.assertEqual(rc, 0)
        names = [v["tier"] for v in out["verdicts"]]
        self.assertEqual(names, ["S", "M", "L"])

    def test_load_slo_real_config(self):
        # 入仓 SLO 单一事实源完整性（防配置文件损坏悄悄放宽阈值）
        slo = self.mod.load_slo()
        self.assertEqual(set(slo["tiers"]), {"S", "M", "L"})
        self.assertTrue(all(
            t["p95_max_s"] > 0 for t in slo["tiers"].values()))


if __name__ == "__main__":
    unittest.main()
