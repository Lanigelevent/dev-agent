#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_trace_export.py — AB-01 评测集导出器契约（r199）。

score 记录落盘 → 导出评测集含 scores 聚合；--require-score 对无 score 会话
质检红（反向验证）；坏行容错与文件缺失 rc=2。
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "eval-harness" / "scripts" / "trace-export.py"
AGENT_TRACE = ROOT / "agent" / "trace.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TraceScoreRecordTests(unittest.TestCase):
    """trace.py Tracer.score()：Langfuse score 模型的本地 JSONL 形态。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trace-export-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mod = _load("trace_mod", AGENT_TRACE)

    def test_score_record_fields(self):
        tr = self.mod.Tracer("sess-score-1", trace_dir=str(self.tmp))
        rec = tr.score("review_precision", 0.83, comment="judge 回灌",
                       observation_id="obs-0001")
        self.assertEqual(rec["type"], "score")
        self.assertEqual(rec["name"], "review_precision")
        self.assertEqual(rec["value"], 0.83)
        self.assertEqual(rec["data_type"], "numeric")
        self.assertEqual(rec["observation_id"], "obs-0001")
        self.assertTrue(self.mod.Path(tr.path).is_file())
        on_disk = json.loads(
            self.mod.Path(tr.path).read_text(encoding="utf-8").strip())
        self.assertEqual(on_disk["type"], "score")


class TraceExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trace-export-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mod = _load("trace_export_ut", SCRIPT)

    def _run(self, args):
        # 子进程驱动保持契约真实（真实 argparse/退出码面）
        import subprocess
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)] + args, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=60)
        return proc

    def _write_trace(self, path, with_score=True):
        tr = _load("trace_w", AGENT_TRACE).Tracer(
            "sess-" + path.stem, trace_dir=str(self.tmp))
        tr.span("llm", "call_end", duration_ms=10, token_input=5,
                token_output=7, cost_usd=0.01)
        if with_score:
            tr.score("review_precision", 0.9, comment="baseline")
        return tr

    def test_export_aggregates_scores(self):
        tr = self._write_trace(self.tmp / "t1.jsonl", with_score=True)
        out = self.tmp / "eval-set.json"
        proc = self._run(["--trace", str(tr.path), "--out", str(out)])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["score_records"], 1)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "trace-eval-set/1")
        self.assertEqual(len(data["scores"]), 1)
        self.assertEqual(data["scores"][0]["name"], "review_precision")
        self.assertEqual(data["summary"]["scored_sessions"], 1)

    def test_require_score_catches_scoreless_session(self):
        # 反向验证：无 score 会话在 --require-score 下 rc=1（质检红）
        tr = self._write_trace(self.tmp / "t2.jsonl", with_score=False)
        proc = self._run(["--trace", str(tr.path),
                          "--out", str(self.tmp / "es.json"),
                          "--require-score"])
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertTrue(any("score" in e for e in payload["errors"]))

    def test_missing_file_rc2(self):
        proc = self._run(["--trace", str(self.tmp / "nope.jsonl"),
                          "--out", str(self.tmp / "es.json")])
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    import types  # noqa: F401  _run 保留 SimpleNamespace 参数面备用
    unittest.main()
