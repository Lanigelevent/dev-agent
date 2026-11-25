#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量 Trace 埋点（agent 层，标准库）。

输出 JSONL 格式的 trace 文件，兼容 Langfuse trace 数据模型
（trace_id / observation_id / session_id），未来可直接导入 Langfuse。

gen_ai.* 对齐（批次 B1-06，OTel GenAI 语义约定，双写一版本过渡）：
- step="llm" 的 span 一律携带四键 gen_ai.system / gen_ai.request.model /
  gen_ai.usage.input_tokens / gen_ai.usage.output_tokens（值未知时为 null，
  键必须在——契约由 tests/test_trace_genai_contract.py 锁定）；
- 旧字段（step/phase/duration_ms/token_input/token_output/...）原样保留
  一版本，消费方不断裂；
- span_name 字段按 OTel GenAI 命名映射：llm→execute_agent_task，
  工具类 step→execute_tool；其余 step 退回原名。
落盘仍为 JSONL（不换后端只改 schema），全程标准库。

用法：
    from agent.trace import Tracer
    tracer = Tracer(session_id="task-20261027-001")
    tracer.span("llm", "call_start")
    # ... do work ...
    tracer.span("llm", "call_end", duration_ms=1234, token_output=500)
"""
import json
import time
from pathlib import Path

# OTel GenAI span 命名（批次 B1-06）：agent 任务执行与工具执行两个目标名。
SPAN_AGENT_TASK = "execute_agent_task"
SPAN_TOOL = "execute_tool"
# 工具类 step 集合（loop.py 实际产生的工具类 span：parse/edit/test/search/list）。
_TOOL_STEPS = ("parse", "edit", "test", "search", "list")


def span_name_for(step):
    """OTel GenAI span 命名映射（批次 B1-06）。

    llm → execute_agent_task（agent 任务执行，批次指名）；
    parse/edit/test/search/list → execute_tool（工具执行）；
    其余 step（init/rank/probe 等非映射覆盖面）退回 step 原名。
    """
    if step == "llm":
        return SPAN_AGENT_TASK
    if step in _TOOL_STEPS:
        return SPAN_TOOL
    return step


class Tracer:
    """JSONL trace 写入器：每条 span 一行 JSON。"""

    def __init__(self, session_id, trace_dir="reports/traces",
                 gen_ai_system=None):
        self.session_id = session_id
        self.trace_id = session_id
        # gen_ai.system 取值（批次 B1-06）：构造时注入 provider 模式
        # （llm/provider.select()），llm span 的 gen_ai.system 键由此取值。
        self.gen_ai_system = gen_ai_system
        self.path = Path(trace_dir) / ("%s.jsonl" % session_id)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # 观测层不可写不许拖垮编码循环
        self._obs_counter = 0

    def span(self, step, phase, duration_ms=None, token_input=None,
             token_output=None, cost_usd=None, status="ok", **extra):
        """写入一条 trace span。

        参数：
            step: 步骤类型（llm/parse/edit/test/loop/probe）
            phase: 阶段（call_start/call_end/done/applied/...）
            duration_ms: 耗时（毫秒，整数）
            token_input: 输入 token 数
            token_output: 输出 token 数
            cost_usd: 成本（美元）
            status: 状态（ok/fail/skip）
            gen_ai_system: llm span 的 gen_ai.system 覆盖值（可选）
            **extra: 额外字段（round/file/...）
        """
        self._obs_counter += 1
        # gen_ai_system 一律从 extra 摘出（防它以原键名漏进 JSONL）；
        # 仅 step=llm 时作为 gen_ai.system 的逐 span 覆盖值生效。
        gen_ai_system = extra.pop("gen_ai_system", None)
        record = {
            "trace_id": self.trace_id,
            "observation_id": "obs-%04d" % self._obs_counter,
            "session_id": self.session_id,
            "step": step,
            "phase": phase,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
            "duration_ms": duration_ms,
            "token_input": token_input,
            "token_output": token_output,
            "cost_usd": cost_usd,
            "status": status,
        }
        if step == "llm":
            # 批次 B1-06：gen_ai.* 四键双写（OTel GenAI 语义约定）。
            # 值未知时为 null，键必须在；旧字段同名不动（双写一版本）。
            record["gen_ai.system"] = (gen_ai_system
                                       or self.gen_ai_system)
            record["gen_ai.request.model"] = extra.get("model")
            record["gen_ai.usage.input_tokens"] = token_input
            record["gen_ai.usage.output_tokens"] = token_output
        record["span_name"] = span_name_for(step)
        record.update(extra)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 写失败只丢 trace，不抛
        return record

    def score(self, name, value, comment="", observation_id=None,
              data_type="numeric"):
        """写入一条评分记录（AB-01，Langfuse score 模型的本地 JSONL 形态）。

        Langfuse 的 score 经 API 回挂（POST /public/scores）；本地无服务时
        以同字段语义落 JSONL：trace_id/observation_id/name/value/data_type/
        comment/timestamp。value 为数值（numeric）或 "true"/"false"
        （boolean）；人工标注/评测器回灌均可写，导出器按 name 聚合。
        """
        record = {
            "trace_id": self.trace_id,
            "observation_id": observation_id,
            "session_id": self.session_id,
            "type": "score",
            "name": name,
            "value": value,
            "data_type": data_type,
            "comment": comment,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 写失败只丢 trace，不抛
        return record

    def timer(self, step, phase):
        """上下文管理器：自动记录 duration_ms。

        with tracer.timer("llm", "call"):
            # ... do work ...
        # 自动写入 span(step="llm", phase="call", duration_ms=...)
        """
        return _SpanTimer(self, step, phase)


class _SpanTimer:
    """辅助类：Tracer.timer() 返回的上下文管理器。"""

    def __init__(self, tracer, step, phase):
        self.tracer = tracer
        self.step = step
        self.phase = phase
        self._start = None

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.monotonic() - self._start) * 1000)
        status = "fail" if exc_type else "ok"
        self.tracer.span(self.step, self.phase,
                         duration_ms=duration_ms, status=status)
        return False  # 不吞异常
