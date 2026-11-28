#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M7 契约测试：pii-scan 出站脱敏闸（round-234，unittest 兼容）。"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PII = ROOT / "skills" / "production-guardrails" / "scripts" / "pii-scan.py"


def _load():
    spec = importlib.util.spec_from_file_location("pii_scan", PII)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestScanText(unittest.TestCase):
    def test_cn_id_valid_hits_and_invalid_skips(self):
        mod = _load()
        r1 = mod.scan_text("证件号 11010519491231002X 请核对")
        self.assertTrue(any(h["rule"] == "cn_id" for h in r1["hits"]))
        r2 = mod.scan_text("证件号 110105194912310021 请核对")
        self.assertFalse(any(h["rule"] == "cn_id" for h in r2["hits"]))

    def test_phone_and_email_hit(self):
        mod = _load()
        r = mod.scan_text("联系 13812345678 或 reviewer@example.com")
        rules = {h["rule"] for h in r["hits"]}
        self.assertIn("cn_phone", rules)
        self.assertIn("email", rules)

    def test_luhn_gate(self):
        mod = _load()
        r1 = mod.scan_text("卡号 4111111111111111 有效")
        r2 = mod.scan_text("卡号 4111111111111112 无效")
        self.assertTrue(any(h["rule"] == "bank_card" for h in r1["hits"]))
        self.assertFalse(any(h["rule"] == "bank_card" for h in r2["hits"]))

    def test_redaction_placeholder(self):
        mod = _load()
        r = mod.scan_text("联系 13812345678")
        self.assertIn("<pii:cn_phone>", r["hits"][0]["snippet"])
        self.assertNotIn("13812345678", r["hits"][0]["snippet"])

    def test_boundary_no_false_positive(self):
        mod = _load()
        r = mod.scan_text("电话 1381234567812345（长数字段不吃）")
        self.assertFalse(any(h["rule"] == "cn_phone" for h in r["hits"]))

    def test_secret_scan_semantics_untouched(self):
        """凭据归 secret-scan：凭据样例文本不含 PII 规则形态（各管各面）。"""
        mod = _load()
        r = mod.scan_text("key = <redacted-aws-key-样例形态>")
        self.assertEqual([h for h in r["hits"] if h["rule"] != "entropy"], [])


class TestCli(unittest.TestCase):
    def test_selftest_verb_green(self):
        r = subprocess.run(
            [sys.executable, str(PII), "selftest"],
            capture_output=True, timeout=120)
        self.assertEqual(r.returncode, 0)
        doc = json.loads(r.stdout.decode("utf-8"))
        self.assertTrue(doc["ok"])

    def test_scan_rc_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            pii_file = Path(td) / "sample.txt"
            pii_file.write_text("联系 13812345678", encoding="utf-8")
            r1 = subprocess.run(
                [sys.executable, str(PII), "scan",
                 "--file", str(pii_file)], capture_output=True, timeout=120)
            self.assertEqual(r1.returncode, 1)
            clean = Path(td) / "clean.txt"
            clean.write_text("纯代码文本 no pii here", encoding="utf-8")
            r2 = subprocess.run(
                [sys.executable, str(PII), "scan",
                 "--file", str(clean)], capture_output=True, timeout=120)
            self.assertEqual(r2.returncode, 0)
            r3 = subprocess.run(
                [sys.executable, str(PII), "scan",
                 "--file", str(Path(td) / "nope.txt")],
                capture_output=True, timeout=120)
            self.assertEqual(r3.returncode, 2)


if __name__ == "__main__":
    unittest.main()
