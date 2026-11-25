#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_trace_genai_contract.py — trace.py 的 gen_ai.* 双写契约（批次 B1-06）。

锁定三件事（一版本过渡期同时成立，消费方不断裂）：
1. step=llm 的 span 一律携带 gen_ai.system / gen_ai.request.model /
   gen_ai.usage.input_tokens / gen_ai.usage.output_tokens 四键
   （值未知时为 null，键必须在）；
2. 旧字段（trace_id/observation_id/session_id/step/phase/timestamp/
   duration_ms/token_input/token_output/cost_usd/status）原样保留；
3. span_name 按 OTel GenAI 命名映射：llm→execute_agent_task；
   parse/edit/test/search/list→execute_tool；其余 step 退回原名；
   非 llm span 不得出现 gen_ai.* 键（四键是 llm 专属）。
独立文件（不 import test_agent.py），自身加载 agent/trace.py。
"""
import importlib.util
import json
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]

# OTel GenAI 四键（契约字面量：外部可见名，逐字锁定）。
GENAI_KEYS = (
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
)
# 旧 schema 字段（一版本过渡期必须原样保留）。
OLD_KEYS = (
    "trace_id", "observation_id", "session_id", "step", "phase",
    "timestamp", "duration_ms", "token_input", "token_output",
    "cost_usd", "status",
)


def _load_trace():
    """以模块形式加载 agent/trace.py（与 test_agent.load_agent_script 同法）。"""
    spec = importlib.util.spec_from_file_location(
        "agent_under_test_trace_genai", ROOT / "agent" / "trace.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestTraceGenAIContract(unittest.TestCase):
    """gen_ai.* 四键双写 + span_name 映射 + 旧字段并存的锁定。"""

    @classmethod
    def setUpClass(cls):
        cls.trace = _load_trace()

    def _write_and_read(self, *spans):
        """写 spans 后回读 JSONL 记录列表。spans: (step, phase, kwargs) 元组。"""
        tmp = tmpspace.create(prefix="trace-genai-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s1",
                                   trace_dir=str(tmp / "traces"))
        for step, phase, kwargs in spans:
            tracer.span(step, phase, **kwargs)
        path = tmp / "traces" / "s1.jsonl"
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_llm_span_has_genai_keys_and_old_fields(self):
        """llm span：四键必须在，旧字段原样保留，双写值一致。"""
        recs = self._write_and_read(
            ("llm", "call_start", {"round": 0}),
            ("llm", "call_end", {"duration_ms": 12, "token_input": 100,
                                 "token_output": 7, "model": "m1",
                                 "gen_ai_system": "openai", "status": "ok"}),
            ("llm", "token_count", {"token_output": 3}),
        )
        self.assertEqual([r["step"] for r in recs], ["llm"] * 3)
        for rec in recs:
            for key in GENAI_KEYS:
                self.assertIn(key, rec, "llm span 缺 gen_ai 键 %s" % key)
            for key in OLD_KEYS:
                self.assertIn(key, rec, "旧字段丢失 %s" % key)
        end = recs[1]
        self.assertEqual(end["gen_ai.system"], "openai")
        self.assertEqual(end["gen_ai.request.model"], "m1")
        self.assertEqual(end["gen_ai.usage.input_tokens"], 100)
        self.assertEqual(end["gen_ai.usage.output_tokens"], 7)
        # 旧字段同名不动（双写，不是改名）。
        self.assertEqual(end["model"], "m1")
        self.assertEqual(end["token_input"], 100)
        self.assertEqual(end["token_output"], 7)
        self.assertEqual(recs[2]["gen_ai.usage.output_tokens"], 3)

    def test_llm_span_without_values_still_has_keys(self):
        """值未知（call_start 无 tokens/model）时四键仍必须在，值为 null。"""
        rec = self._write_and_read(
            ("llm", "call_start", {"round": 0}))[0]
        for key in GENAI_KEYS:
            self.assertIn(key, rec, "值未知的 llm span 仍须携带 %s" % key)
        self.assertIsNone(rec["gen_ai.system"])
        self.assertIsNone(rec["gen_ai.request.model"])
        self.assertIsNone(rec["gen_ai.usage.input_tokens"])
        self.assertIsNone(rec["gen_ai.usage.output_tokens"])

    def test_non_llm_spans_have_no_genai_keys(self):
        """四键是 llm 专属：非 llm span 不得出现 gen_ai.* 键。"""
        recs = self._write_and_read(
            ("edit", "applied", {"file": "a.py"}),
            ("init", "start", {"repo": "."}),
        )
        for rec in recs:
            for key in GENAI_KEYS:
                self.assertNotIn(key, rec,
                                 "非 llm span 不应携带 %s" % key)
        self.assertEqual(recs[0]["span_name"], "execute_tool")
        self.assertEqual(recs[1]["span_name"], "init")

    def test_span_name_mapping(self):
        """llm→execute_agent_task；工具类 step→execute_tool；其余退回原名。"""
        spans = [("llm", "call_end", {}),
                 ("parse", "done", {}), ("edit", "applied", {}),
                 ("test", "done", {}), ("search", "done", {}),
                 ("list", "done", {}),
                 ("init", "start", {})]
        recs = self._write_and_read(*spans)
        expect = ["execute_agent_task"] + ["execute_tool"] * 5 + ["init"]
        self.assertEqual([r["span_name"] for r in recs], expect)

    def test_genai_system_constructor_and_per_span_override(self):
        """gen_ai.system：构造值兜底、逐 span gen_ai_system 覆盖优先。"""
        tmp = tmpspace.create(prefix="trace-genai-sys-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s2",
                                   trace_dir=str(tmp / "traces"),
                                   gen_ai_system="host")
        tracer.span("llm", "call_start")
        tracer.span("llm", "call_end", gen_ai_system="openai")
        recs = [json.loads(line) for line in
                (tmp / "traces" / "s2.jsonl").read_text(
                    encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(recs[0]["gen_ai.system"], "host")
        self.assertEqual(recs[1]["gen_ai.system"], "openai")

    def test_timer_llm_span_duration_caliber(self):
        """timer 产生的 llm span：duration_ms 口径=毫秒整数，四键与 span_name 同在。"""
        tmp = tmpspace.create(prefix="trace-genai-timer-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s3",
                                   trace_dir=str(tmp / "traces"),
                                   gen_ai_system="openai")
        with tracer.timer("llm", "call"):
            pass
        rec = json.loads((tmp / "traces" / "s3.jsonl").read_text(
            encoding="utf-8").splitlines()[0])
        self.assertEqual(rec["span_name"], "execute_agent_task")
        for key in GENAI_KEYS:
            self.assertIn(key, rec, "timer llm span 缺 %s" % key)
        self.assertIsInstance(rec["duration_ms"], int)
        self.assertGreaterEqual(rec["duration_ms"], 0)

    def test_timer_failure_keeps_schema_and_propagates(self):
        """timer 异常路径：status=fail、异常照抛、新 schema 字段同在。"""
        tmp = tmpspace.create(prefix="trace-genai-fail-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s4",
                                   trace_dir=str(tmp / "traces"),
                                   gen_ai_system="openai")
        with self.assertRaises(RuntimeError):
            with tracer.timer("llm", "call"):
                raise RuntimeError("boom")
        rec = json.loads((tmp / "traces" / "s4.jsonl").read_text(
            encoding="utf-8").splitlines()[0])
        self.assertEqual(rec["status"], "fail")
        self.assertEqual(rec["span_name"], "execute_agent_task")
        for key in GENAI_KEYS:
            self.assertIn(key, rec)
        self.assertIsNotNone(rec["duration_ms"])
