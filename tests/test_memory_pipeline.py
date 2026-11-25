# -*- coding: utf-8 -*-
"""tests/test_memory_pipeline.py — AB-20 记忆三级管线契约（round-216）。

反向验证面（红线 6）：近重复必须判 UPDATE（不重复入库）、llm 臂无 key
必须 blocked 不写 store（不冒充决策已判）、事件形状错误必须 rc=1。
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/retro/scripts/memory-pipeline.py"


def _run(args, env_extra=None):
    import os
    env = dict(os.environ)
    env.pop("CRA_LLM_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, timeout=60, env=env)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


class TestMemoryPipeline(unittest.TestCase):
    """ADD/UPDATE/blocked/retrieve/坏事件五面。"""

    def test_add_then_readd_updates(self):
        with tempfile.TemporaryDirectory() as td:
            store = str(Path(td) / "mem.jsonl")
            ev = [{"type": "correction", "title": "GBK stdout 自防御缺失",
                   "description": "裸子进程 stdout 走 GBK，CJK JSON 解码错位翻红"}]
            evf = str(Path(td) / "ev.json")
            Path(evf).write_text(json.dumps(ev), encoding="utf-8")
            rc, out = _run(["add", "--store", store, "--events", evf])
            d = json.loads(out)
            self.assertEqual((rc, d["decisions"][0]["action"]), (0, "ADD"))
            rc, out = _run(["add", "--store", store, "--events", evf])
            d = json.loads(out)
            self.assertEqual(d["decisions"][0]["action"], "UPDATE")
            self.assertEqual(d["store_entries"], 1, "近重复必须合并不重复入库")

    def test_llm_arm_blocked_no_write(self):
        with tempfile.TemporaryDirectory() as td:
            store = str(Path(td) / "mem.jsonl")
            ev = [{"type": "correction", "title": "T", "description": "D"}]
            evf = str(Path(td) / "ev.json")
            Path(evf).write_text(json.dumps(ev), encoding="utf-8")
            rc, out = _run(["add", "--store", store, "--events", evf,
                            "--decider", "llm"])
            d = json.loads(out)
            self.assertEqual((rc, d["arm_status"]), (0, "blocked_no_key"))
            self.assertFalse(d["written"], "blocked 臂不得写 store")
            self.assertFalse(Path(store).exists())

    def test_llm_arm_ready_with_key(self):
        with tempfile.TemporaryDirectory() as td:
            store = str(Path(td) / "mem.jsonl")
            ev = [{"type": "correction", "title": "T2", "description": "D2"}]
            evf = str(Path(td) / "ev.json")
            Path(evf).write_text(json.dumps(ev), encoding="utf-8")
            rc, out = _run(["add", "--store", store, "--events", evf,
                            "--decider", "llm"],
                           env_extra={"CRA_LLM_KEY": "dummy"})
            d = json.loads(out)
            self.assertEqual(d["arm_status"], "ready",
                             "有 key 时 llm 臂 ready（决策仍走确定性对照，"
                             "LLM 判卷为宿主侧后续面）")
            self.assertTrue(d["written"])

    def test_retrieve_delegation(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "mem.jsonl"
            rows = [
                {"id": "a1", "namespace": "agent",
                 "task": "ast-grep innerHTML XSS fix",
                 "summary": "innerHTML 赋值导致跨站脚本",
                 "failure_category": "correction", "rule_codes": [],
                 "ts": "2026-01-01", "seen": 1},
                {"id": "b2", "namespace": "agent",
                 "task": "pytest xdist 并行超时",
                 "summary": "xdist 并行下超时阈值不足",
                 "failure_category": "correction", "rule_codes": [],
                 "ts": "2026-01-02", "seen": 1},
                {"id": "c3", "namespace": "run",
                 "task": "release-gate 双跑对账",
                 "summary": "发布闸双跑日志格式与顺序",
                 "failure_category": "confirmation", "rule_codes": [],
                 "ts": "2026-01-03", "seen": 1},
            ]
            store.write_text(
                "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                encoding="utf-8")
            rc, out = _run(["retrieve", "--store", str(store),
                            "--query", "innerHTML XSS 跨站脚本",
                            "--top-k", "2"])
            d = json.loads(out)
            self.assertEqual(rc, 0)
            self.assertTrue(d["hits"], "相关查询必须命中")
            self.assertEqual(d["hits"][0]["id"], "a1")

    def test_bad_events_rc1(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text("[]", encoding="utf-8")
            rc, out = _run(["plan", "--store", str(Path(td) / "m.jsonl"),
                            "--events", str(bad)])
            self.assertEqual(rc, 0, "空数组合法（零事实零决策）")
            notlist = Path(td) / "n.json"
            notlist.write_text('{"events": 42}', encoding="utf-8")
            rc, out = _run(["plan", "--store", str(Path(td) / "m.jsonl"),
                            "--events", str(notlist)])
            self.assertEqual(rc, 1, "events 键非数组必须 rc=1")


if __name__ == "__main__":
    unittest.main()
