#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1/M4 契约测试：mcp-selfscan pin/check 与 tools-policy 执行层拦截（round-233，unittest 兼容）。"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELFSCAN = ROOT / "skills" / "production-guardrails" / "scripts" / "mcp-selfscan.py"


def _load_selfscan():
    spec = importlib.util.spec_from_file_location("mcp_selfscan", SELFSCAN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_repo(root):
    """最小仓形状：2 工具 review_mcp.py + tools-policy.json。"""
    root = Path(root)
    (root / "mcp").mkdir(parents=True, exist_ok=True)
    tools = ",\n    ".join(
        json.dumps({"name": "code_review_tool%d" % i,
                    "description": "工具 %d" % i,
                    "inputSchema": {"type": "object", "properties": {}}})
        for i in range(2))
    server = ("# -*- coding: utf-8 -*-\n"
              "SERVER_INFO = {\"name\": \"x\", \"version\": \"0\"}\n"
              "TOOLS = [\n    " + tools + ",\n]\n")
    (root / "mcp" / "review_mcp.py").write_text(server, encoding="utf-8")
    policy = {"schema": "tools-policy/v1", "tools": {
        "code_review_tool0": "auto", "code_review_tool1": "gated"}}
    (root / "mcp" / "tools-policy.json").write_text(
        json.dumps(policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return root


class TestSelfscan(unittest.TestCase):
    def test_pin_then_check_green(self):
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td) / "repo")
            mod = _load_selfscan()
            doc = mod.pin_verb(root)
            self.assertEqual(len(doc["tools"]), 2)
            ok, drifts, computed = mod.check(root)
            self.assertTrue(ok)
            self.assertEqual(drifts, [])

    def test_tamper_tool_hash_flips_red(self):
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td) / "repo")
            mod = _load_selfscan()
            mod.pin_verb(root)
            pin_path = root / "mcp" / "tools-pin.json"
            d = json.loads(pin_path.read_text(encoding="utf-8"))
            d["tools"]["code_review_tool0"] = "0" * 64
            pin_path.write_text(json.dumps(d), encoding="utf-8")
            ok, drifts, _c = mod.check(root)
            self.assertFalse(ok)
            self.assertTrue(any(x["id"] == "tool_hash_mismatch" for x in drifts))

    def test_tamper_policy_bytes_flips_red(self):
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td) / "repo")
            mod = _load_selfscan()
            mod.pin_verb(root)
            p = root / "mcp" / "tools-policy.json"
            p.write_text(
                p.read_text(encoding="utf-8").replace("auto", "deny"),
                encoding="utf-8")
            ok, drifts, _c = mod.check(root)
            self.assertFalse(ok)
            self.assertTrue(any(x["id"] == "policy_drift" for x in drifts))

    def test_policy_hash_canonical_across_eol(self):
        """r238 回归：CRLF 工作树与 LF 检出同哈希（公开 CI 拒服务根因）；篡改仍必命中。"""
        mod = _load_selfscan()
        with tempfile.TemporaryDirectory() as td:
            crlf = Path(td) / "crlf.json"
            lf = Path(td) / "lf.json"
            body = chr(123) + chr(34) + "k" + chr(34) + ": " + chr(34) + "v" + chr(34) + chr(125)
            crlf.write_bytes((body + chr(10)).replace(chr(10), chr(13) + chr(10)).encode("utf-8"))
            lf.write_bytes((body + chr(10)).encode("utf-8"))
            self.assertEqual(mod._policy_hash_bytes(crlf), mod._policy_hash_bytes(lf))
            lf.write_bytes((body + chr(10) + chr(125)).replace(chr(123), chr(91), 1).encode("utf-8"))
            self.assertNotEqual(mod._policy_hash_bytes(crlf), mod._policy_hash_bytes(lf))

    def test_missing_pin_rc1(self):
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td) / "repo")
            mod = _load_selfscan()
            ok, drifts, _c = mod.check(root)
            self.assertFalse(ok)
            self.assertEqual(drifts[0]["id"], "pin_missing")

    def test_main_rc_mapping(self):
        """rc 映射经子进程面验证（与 CI 同构；进程内 argparse 受全量套件污染，r233）。"""
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td) / "repo")
            r1 = subprocess.run(
                [sys.executable, str(SELFSCAN), "--root", str(root), "pin"],
                capture_output=True, timeout=120)
            self.assertEqual(r1.returncode, 0)
            r2 = subprocess.run(
                [sys.executable, str(SELFSCAN), "--root", str(root), "check"],
                capture_output=True, timeout=120)
            self.assertEqual(r2.returncode, 0)
            pin_path = root / "mcp" / "tools-pin.json"
            d = json.loads(pin_path.read_text(encoding="utf-8"))
            d["tools"]["code_review_tool1"] = "0" * 64
            pin_path.write_text(json.dumps(d), encoding="utf-8")
            r3 = subprocess.run(
                [sys.executable, str(SELFSCAN), "--root", str(root), "check"],
                capture_output=True, timeout=120)
            self.assertEqual(r3.returncode, 1)


class TestPolicyEnforcement(unittest.TestCase):
    def _load_mcp(self):
        spec = importlib.util.spec_from_file_location(
            "rm_t", ROOT / "mcp" / "review_mcp.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def _call(self, name, arguments=None):
        return {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name,
                           "arguments": arguments if arguments is not None else {}}}

    def test_deny_refuses_before_handler(self):
        m = self._load_mcp()
        try:
            m._POLICY_CACHE["code_review_scan"] = "deny"
            r = m._handle(self._call("code_review_scan", {"path": "x"}))
            text = r["result"]["content"][0]["text"]
            self.assertIn("工具分级门控拒绝", text)
        finally:
            m._POLICY_CACHE.clear()

    def test_auto_falls_through_to_handler(self):
        m = self._load_mcp()
        try:
            m._POLICY_CACHE["code_review_scan"] = "auto"
            r = m._handle(self._call("code_review_scan", {"path": "x"}))
            text = r["result"]["content"][0]["text"]
            self.assertNotIn("工具分级门控拒绝", text)
        finally:
            m._POLICY_CACHE.clear()

    def test_unknown_tool_fail_closed(self):
        m = self._load_mcp()
        r = m._handle(self._call("code_review_ghost_tool"))
        self.assertTrue(r["result"]["isError"])

    def test_levels_loaded_from_policy_file(self):
        m = self._load_mcp()
        self.assertEqual(m._policy_level("code_review_scan"), "auto")
        self.assertEqual(m._policy_level("code_review_apply"), "gated")
        self.assertEqual(m._policy_level("code_review_purge"), "gated")
