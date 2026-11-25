# -*- coding: utf-8 -*-
"""tests/test_report_adapter.py — report-adapter.py 契约（round-104）。

覆盖：三维度适配（detail_level/audience/industry）、preset 加载、
findings 过滤、术语映射、退出码、单 JSON stdout。
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "orchestrator" / "scripts" / "report-adapter.py"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("report_adapter_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _invoke(mod, argv):
    old = sys.argv
    out = io.StringIO()
    try:
        sys.argv = ["report-adapter.py"] + argv
        with contextlib.redirect_stdout(out):
            rc = mod.main()
    finally:
        sys.argv = old
    return rc, out.getvalue()


FINDINGS = [
    {"severity": "高", "confidence": "高", "loc": "a.py:1",
     "desc": "硬编码密码", "evidence": "password = 'x'" * 30,
     "fix": "改环境变量"},
    {"severity": "中", "confidence": "中", "loc": "a.py:2",
     "desc": "可变默认参数", "evidence": "def f(d={})", "fix": "None + init"},
    {"severity": "低", "confidence": "低", "loc": "a.py:3",
     "desc": "缺类型标注", "evidence": "", "fix": "加 hints"},
]


class ReportAdapterTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="radapter-"))
        self.addCleanup(tmpspace.release, self.tmp)
        fp = self.tmp / "findings.json"
        fp.write_text(json.dumps({"findings": FINDINGS}, ensure_ascii=False),
                      encoding="utf-8")
        self.fp = str(fp)

    def test_executive_filters_low(self):
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", "executive",
                                     "--out", str(self.tmp / "exec.md")])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["findings_out"], 1)  # 仅高严重度
        md = (self.tmp / "exec.md").read_text(encoding="utf-8")
        self.assertIn("摘要", md)  # management 受众有摘要段
        self.assertNotIn("缺类型标注", md)  # 低严重度被过滤

    def test_engineering_deep_keeps_all(self):
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", "engineering",
                                     "--out", str(self.tmp / "eng.md")])
        d = json.loads(out)
        self.assertEqual(d["findings_out"], 3)
        md = (self.tmp / "eng.md").read_text(encoding="utf-8")
        self.assertIn("缺类型标注", md)

    def test_audit_industry_terminology(self):
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", "audit",
                                     "--out", str(self.tmp / "aud.md")])
        self.assertEqual(rc, 0)
        md = (self.tmp / "aud.md").read_text(encoding="utf-8")
        self.assertIn("审计报告", md)
        self.assertIn("审计发现", md)
        self.assertNotIn("代码评审报告", md)

    def test_custom_spec_json(self):
        spec = self.tmp / "spec.json"
        spec.write_text(json.dumps({
            "schema": "report-style/1", "detail_level": "executive",
            "audience": "management", "industry": "finance",
            "max_findings": 1}), encoding="utf-8")
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", str(spec),
                                     "--out", str(self.tmp / "cust.md")])
        d = json.loads(out)
        self.assertEqual(d["findings_out"], 1)
        md = (self.tmp / "cust.md").read_text(encoding="utf-8")
        self.assertIn("审计", md)  # finance 术语映射

    def test_missing_findings_rc2(self):
        rc, out = _invoke(self.mod, ["--findings", str(self.tmp / "no.json"),
                                     "--style", "executive"])
        self.assertEqual(rc, 2)

    def test_bad_schema_rc2(self):
        spec = self.tmp / "bad.json"
        spec.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", str(spec)])
        self.assertEqual(rc, 2)
        self.assertIn("report-style/1", json.loads(out)["error"])

    def test_stdout_single_json(self):
        rc, out = _invoke(self.mod, ["--findings", self.fp,
                                     "--style", "executive",
                                     "--out", str(self.tmp / "o.md")])
        d = json.loads(out)  # 整个 stdout 必须是单个 JSON
        self.assertIn("out_path", d)


class WiringTests(unittest.TestCase):
    """r105：spec 校验增强 + runner/MCP 接线契约。"""

    def setUp(self):
        self.tmp = Path(tmpspace.create(prefix="rwiring-"))
        self.addCleanup(tmpspace.release, self.tmp)
        fp = self.tmp / "findings.json"
        fp.write_text(json.dumps({"findings": FINDINGS}, ensure_ascii=False),
                      encoding="utf-8")
        self.fp = str(fp)

    def test_custom_spec_bad_enum_rc2(self):
        mod = _load()
        spec = self._write_spec({"schema": "report-style/1",
                                 "detail_level": "bogus"})
        rc, out = _invoke(mod, ["--findings", self.fp, "--style", str(spec)])
        self.assertEqual(rc, 2)
        err = json.loads(out)["error"]
        self.assertIn("detail_level", err)
        self.assertIn("executive", err)

    def test_custom_spec_bad_max_findings_rc2(self):
        mod = _load()
        spec = self._write_spec({"schema": "report-style/1",
                                 "max_findings": 0})
        rc, out = _invoke(mod, ["--findings", self.fp, "--style", str(spec)])
        self.assertEqual(rc, 2)
        self.assertIn("max_findings", json.loads(out)["error"])

    def test_custom_spec_valid_enums_ok(self):
        mod = _load()
        spec = self._write_spec({"schema": "report-style/1",
                                 "detail_level": "standard",
                                 "audience": "auditor",
                                 "industry": "healthcare",
                                 "min_severity": "中"})
        rc, out = _invoke(mod, ["--findings", self.fp, "--style", str(spec)])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(d["findings_out"], 2)  # 高+中，低被过滤

    def test_runner_report_style_wiring(self):
        src = (ROOT / "skills" / "orchestrator" / "scripts" / "runner.py"
               ).read_text(encoding="utf-8")
        self.assertIn("--report-style", src)
        self.assertIn("_render_style_variant", src)
        self.assertIn("report-adapter.py", src)
        self.assertIn("\"styled\"", src)          # 结果含 styled 键
        self.assertIn("降级", src)                 # fail-soft 降级记录

    def test_mcp_report_style_schema(self):
        src = (ROOT / "mcp" / "review_mcp.py").read_text(encoding="utf-8")
        self.assertIn("report_style", src)
        self.assertIn("--report-style", src)

    def _write_spec(self, obj):
        fp = Path(tmpspace.create(prefix="rspec-")) / "spec.json"
        fp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return fp


if __name__ == "__main__":
    unittest.main()
