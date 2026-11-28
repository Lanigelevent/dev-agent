#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2/M3 契约测试：trim/熔断/complete_json 回填重试（round-233 行为级反向验证，unittest 兼容）。"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm import provider  # noqa: E402


class TestTrim(unittest.TestCase):
    def test_exact_boundary_not_trimmed(self):
        head, trimmed, tc, tl = provider.trim_tool_result(
            "x" * 20000, 20000, 500)
        self.assertFalse(trimmed)
        self.assertEqual(tc, 20000)

    def test_over_chars_trimmed_to_cap(self):
        head, trimmed, tc, tl = provider.trim_tool_result(
            "x" * 25000, 20000, 500)
        self.assertTrue(trimmed)
        self.assertEqual(len(head), 20000)
        self.assertEqual(tc, 25000)

    def test_over_lines_trimmed_to_cap(self):
        head, trimmed, tc, tl = provider.trim_tool_result(
            chr(10).join("L%d" % i for i in range(555)), 20000, 500)
        self.assertTrue(trimmed)
        self.assertEqual(len(head.splitlines()), 500)

    def test_empty_passthrough(self):
        head, trimmed, tc, tl = provider.trim_tool_result("", 20000, 500)
        self.assertFalse(trimmed)
        self.assertEqual(head, "")

    def test_both_caps(self):
        head, trimmed, tc, tl = provider.trim_tool_result(
            chr(10).join("x" * 100 for i in range(600)), 300, 10)
        self.assertTrue(trimmed)
        self.assertLessEqual(len(head), 300)
        self.assertLessEqual(len(head.splitlines()), 10)


class _FakeReader:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        out, self._b = self._b, b""
        return out

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestCircuit(unittest.TestCase):
    def setUp(self):
        provider._CIRCUIT["fails"] = 0
        provider._CIRCUIT["opened_at"] = 0.0

    def _env(self):
        return mock.patch.dict(os.environ, {
            "REVIEW_LLM_BASE_URL": "https://unit-test.invalid",
            "REVIEW_LLM_MODEL": "probe"})

    def _fail_always(self):
        def fail(req, timeout=None):
            raise OSError("boom")
        return fail

    def test_threshold_opens_and_fast_fails(self):
        env = self._env()
        env.start()
        self.addCleanup(env.stop)
        with mock.patch.object(provider, "CIRCUIT_COOLDOWN_SECONDS", 300), \
                mock.patch("urllib.request.urlopen", self._fail_always()), \
                mock.patch("time.sleep", lambda s: None), \
                redirect_stderr(io.StringIO()) as err:
            for _i in range(3):
                out, meta = provider._openai_complete("s", "u", {}, None)
                self.assertEqual(meta.get("error"), "boom")
            self.assertEqual(provider._CIRCUIT["fails"], 3)
            self.assertIn("熔断开启", err.getvalue())
            calls = {"n": 0}

            def fast_probe(req, timeout=None):
                calls["n"] += 1
                raise OSError("must-not-be-called")
            with mock.patch("urllib.request.urlopen", fast_probe):
                out, meta = provider._openai_complete("s", "u", {}, None)
            self.assertEqual(meta.get("circuit"), "open")
            self.assertEqual(calls["n"], 0)

    def test_success_resets(self):
        env = self._env()
        env.start()
        self.addCleanup(env.stop)
        provider._CIRCUIT["fails"] = 2
        ok_resp = {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        def ok(req, timeout=None):
            return _FakeReader(ok_resp)
        with mock.patch("urllib.request.urlopen", ok):
            out, meta = provider._openai_complete("s", "u", {}, None)
        self.assertEqual(out, "ok")
        self.assertEqual(provider._CIRCUIT["fails"], 0)

    def test_cooldown_zero_recovers(self):
        env = self._env()
        env.start()
        self.addCleanup(env.stop)
        with mock.patch.object(provider, "CIRCUIT_COOLDOWN_SECONDS", 0), \
                mock.patch("urllib.request.urlopen", self._fail_always()), \
                mock.patch("time.sleep", lambda s: None), \
                redirect_stderr(io.StringIO()):
            for _i in range(3):
                provider._openai_complete("s", "u", {}, None)
            self.assertGreaterEqual(provider._CIRCUIT["fails"], 1)
            provider._CIRCUIT["fails"] = 0
            out, meta = provider._openai_complete("s", "u", {}, None)
            self.assertNotIn("circuit", meta)


class TestCompleteJson(unittest.TestCase):
    def setUp(self):
        provider._CIRCUIT["fails"] = 0

    def _stub_complete(self, responses):
        seq = list(responses)
        seen = []

        def stub(system, _user, base_dir=None, args=None, on_tokens=None):
            seen.append(_user)
            r = seq.pop(0) if seq else "[]"
            return r, {"provider": "host"}
        return mock.patch.object(provider, "complete", side_effect=stub), seen

    def test_valid_json_passthrough(self):
        p, _s = self._stub_complete(["[1,2]"])
        with p:
            obj, meta = provider.complete_json("s", "u")
        self.assertEqual(obj, [1, 2])
        self.assertNotIn("unparsed", meta)

    def test_repair_round_with_backfill(self):
        p, seen = self._stub_complete(["corrupt {", "[3]"])
        with p:
            obj, meta = provider.complete_json("s", "user-original")
        self.assertEqual(obj, [3])
        self.assertTrue(meta.get("repaired"))
        self.assertIn("上次响应未通过校验", seen[-1])

    def test_validate_fail_repairs(self):
        p, _s = self._stub_complete([{"a": 1}, [7]])
        with p:
            obj, meta = provider.complete_json(
                "s", "u", validate=lambda o: isinstance(o, list))
        self.assertEqual(obj, [7])
        self.assertTrue(meta.get("repaired"))

    def test_still_bad_honest_unparsed(self):
        p, _s = self._stub_complete(["corrupt {", "corrupt {"])
        with p:
            obj, meta = provider.complete_json("s", "u")
        self.assertIsNone(obj)
        self.assertTrue(bool(meta.get("unparsed")))

    def test_d053_empty_list_honest(self):
        p, _s = self._stub_complete(["[]"])
        with p:
            obj, meta = provider.complete_json("t", "u")
        self.assertEqual(obj, [])
        self.assertNotIn("unparsed", meta)

    def test_d053_extract_clean(self):
        body = provider._extract_json(
            "```json" + chr(10) + "[]" + chr(10) + "```")
        self.assertEqual(body, ([], None))

    def test_hostllm_propagates(self):
        def boom(system, _user, base_dir=None, args=None, on_tokens=None):
            raise provider.HostLLMPending("tid", "p", "r")
        with mock.patch.object(provider, "complete", side_effect=boom):
            with self.assertRaises(provider.HostLLMPending):
                provider.complete_json("s", "u")



class TestFallbackChain(unittest.TestCase):
    def setUp(self):
        provider._CIRCUIT["fails"] = 0
        provider._CIRCUIT["opened_at"] = 0.0

    def _chain(self, monkey_env):
        return mock.patch.dict(os.environ, monkey_env)

    def test_primary_fail_backup_hits(self):
        chain = json.dumps([
            {"base_url": "https://unit-bad.invalid", "model": "m1"},
            {"base_url": "http://127.0.0.1:9/v1", "model": "m2"}])
        class _OK:
            def __init__(self):
                self._b = json.dumps({"choices": [{"message": {"content": "from-backup"}}],
                                      "usage": {}}).encode("utf-8")
            def read(self, n=-1):
                out, self._b = self._b, b""
                return out
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake(req, timeout=None):
            url = req.full_url
            if "unit-bad" in url:
                raise OSError("boom-bad")
            return _OK()
        env = self._chain({"CRA_LLM_PROVIDER": "openai",
                           "REVIEW_LLM_ENDPOINTS": chain})
        env.start(); self.addCleanup(env.stop)
        with mock.patch("urllib.request.urlopen", fake), \
                mock.patch("time.sleep", lambda s: None):
            text, meta = provider._openai_fallback("s", "u", {}, None)
        self.assertEqual(text, "from-backup")
        self.assertEqual(meta.get("endpoint_used"), 1)

    def test_all_down_honest_degraded(self):
        chain = json.dumps([
            {"base_url": "https://unit-bad.invalid", "model": "m1"},
            {"base_url": "https://unit-worse.invalid", "model": "m2"}])
        def fail(req, timeout=None):
            raise OSError("boom")
        env = self._chain({"CRA_LLM_PROVIDER": "openai",
                           "REVIEW_LLM_ENDPOINTS": chain})
        env.start(); self.addCleanup(env.stop)
        err = io.StringIO()
        with mock.patch("urllib.request.urlopen", fail), \
                mock.patch("time.sleep", lambda s: None), \
                redirect_stderr(err):
            text, meta = provider._openai_fallback("s", "u", {}, None)
        self.assertIsNone(text)
        self.assertTrue(meta.get("degraded"))
        self.assertIn("失败降级", err.getvalue())

    def test_ssrf_endpoint_skipped(self):
        chain = json.dumps([
            {"base_url": "http://10.0.0.5/v1", "model": "m1"},
            {"base_url": "https://unit-ok.invalid", "model": "m2"}])
        class _OK:
            def __init__(self):
                self._b = json.dumps({"choices": [{"message": {"content": "ok"}}],
                                      "usage": {}}).encode("utf-8")
            def read(self, n=-1):
                out, self._b = self._b, b""
                return out
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake(req, timeout=None):
            url = req.full_url
            if "10.0.0.5" in url:
                raise OSError("must-not-be-called")
            return _OK()
        env = self._chain({"CRA_LLM_PROVIDER": "openai",
                           "REVIEW_LLM_ENDPOINTS": chain})
        env.start(); self.addCleanup(env.stop)
        with mock.patch("urllib.request.urlopen", fake), \
                mock.patch("time.sleep", lambda s: None):
            text, meta = provider._openai_fallback("s", "u", {}, None)
        self.assertEqual(text, "ok")
