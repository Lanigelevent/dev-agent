#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_dual_reviewer.py — 双意见评审器（--reviewer both）契约断言。

用回环 OpenAI 兼容 stub 服务器做端到端（SSRF 白名单允许 loopback）：
both = 确定性 + LLM 去相关双意见合并（确定性优先、loc 去重、source 标注）；
LLM 未配置/不可用/私网端点 → 降级纯确定性不阻塞。
"""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import SCRIPTS

LLM_FINDING = [{
    "loc": "svc/payment.py:9",
    "desc": "LLM 双意见样例：可疑边界",
    "evidence": "def charge",
    "severity": "低",
    "confidence": "中",
    "cause": "stub 第二意见验证",
    "fix": "人工复核该处边界",
}]


class _StubHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - http.server 接口固定命名
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({
            "choices": [{"message": {"content": json.dumps(LLM_FINDING)}}],
            "usage": {"total_tokens": 37},
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默
        pass


class TestDualReviewer(unittest.TestCase):
    """双意见：回环合并、未配置降级、私网端点拦截。"""

    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), _StubHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)

    def _run(self, reviewer, extra_env):
        out = test_scripts.FIXTURE["tmp"] / ("dual-%s" % reviewer)
        cmd = [sys.executable, str(SCRIPTS["runner.py"]),
               "--repo", str(test_scripts.FIXTURE["repo"]),
               "--range", "HEAD~2..HEAD~1", "--out", out,
               "--reviewer", reviewer, "--skip-probe"]
        env = dict(os.environ)
        for key, value in extra_env.items():
            env[key] = value
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60,
                           env=env)
        data = None
        try:
            data = json.loads(p.stdout)
        except ValueError:
            pass
        return p.returncode, data

    def test_both_merges_llm_and_deterministic(self):
        rc, data = self._run("both", {
            "REVIEW_LLM_BASE_URL": "http://127.0.0.1:%d" % self.port,
            "REVIEW_LLM_MODEL": "stub-model",
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:600])
        self.assertEqual(data["state"], "DONE")
        sources = {f.get("source") for f in data.get("findings", [])}
        self.assertIn("llm", sources, "双意见必须并入 LLM 发现")
        self.assertIn("deterministic", sources, "确定性发现必须保留")
        totals = json.loads((Path(data["run_dir"]) / "totals.json")
                            .read_text(encoding="utf-8"))
        self.assertGreater(totals.get("tokens", 0), 0, "stub 调用必须计入 token")
        # 成本账本（ROADMAP 3.2）：openai 兼容后端有真实 usage → provider_usage
        cost = totals.get("cost") or {}
        self.assertEqual(cost.get("tokens_status"), "provider_usage")
        self.assertGreaterEqual(cost.get("tokens_reported_calls", 0), 1)
        rc_c, chk, _, _ = test_scripts.run(SCRIPTS["cost-ledger.py"], "check",
                                           "--dir", data["run_dir"])
        self.assertEqual(rc_c, 0, json.dumps(chk, ensure_ascii=False)[:400])
        self.assertEqual(chk["state"], "PASS")
        self.assertEqual(chk["cost"]["tokens"], totals["tokens"])

    def test_both_degrades_without_llm_config(self):
        rc, data = self._run("both", {})
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["state"], "DONE")
        sources = {f.get("source") for f in data.get("findings", [])}
        self.assertNotIn("llm", sources)
        totals = json.loads((Path(data["run_dir"]) / "totals.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(totals.get("tokens", 0), 0, "未配置不得发起调用")

    def test_both_blocks_private_endpoint(self):
        rc, data = self._run("both", {
            "REVIEW_LLM_BASE_URL": "http://10.0.0.1:8000",
            "REVIEW_LLM_MODEL": "stub-model",
        })
        self.assertEqual(rc, 0)
        self.assertEqual(data["state"], "DONE")
        totals = json.loads((Path(data["run_dir"]) / "totals.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(totals.get("tokens", 0), 0, "私网端点必须被白名单拦截")

    def test_reviewer_llm_alone_still_works(self):
        """原有 llm 单选路径回归保护。"""
        rc, data = self._run("llm", {
            "REVIEW_LLM_BASE_URL": "http://127.0.0.1:%d" % self.port,
            "REVIEW_LLM_MODEL": "stub-model",
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:600])
        self.assertEqual(data["state"], "DONE")
        sources = {f.get("source") for f in data.get("findings", [])}
        self.assertEqual(sources, {"llm"})

    def test_host_mode_pause_and_resume(self):
        """宿主模型后端（CRA_LLM_PROVIDER=host）：等待→假宿主填响应→续跑合并。

        契约（BASELINE「LLM 提供者契约」）：无响应时退出码 1、state
        WAIT_HOST_LLM、写 prompt.md；宿主填 response.md 后 --resume（不带
        --reviewer，从 run_meta 恢复 both）幂等续跑，LLM 发现并入双意见。
        """
        out = test_scripts.FIXTURE["tmp"] / "dual-host"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        env.pop("REVIEW_LLM_API_KEY", None)
        cmd = [sys.executable, str(SCRIPTS["runner.py"]),
               "--repo", str(test_scripts.FIXTURE["repo"]),
               "--range", "HEAD~2..HEAD~1", "--out", out,
               "--reviewer", "both", "--skip-probe"]
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        prompt = Path(data["llm_task"])
        self.assertTrue(prompt.is_file(), "等待态必须落 prompt 文件")
        self.assertIn("评审员", prompt.read_text(encoding="utf-8"))
        # 硬约束 5：送 LLM 的材料必须脱敏（fixture 缺陷态含明文口令）
        self.assertNotIn(test_scripts.SECRET,
                         prompt.read_text(encoding="utf-8"),
                         "LLM 材料出现明文凭据形态")
        # 假宿主循环：host 协议每维度各一问（提示词含维度名），逐个填答
        # 直至 DONE（上限 8 次防死循环）；响应带代码栅栏也应被解析。
        last = data
        for _ in range(8):
            resp_path = Path(last["llm_response"])
            if not resp_path.exists():
                resp_path.write_text(
                    "```json\n" + json.dumps(LLM_FINDING) + "\n```",
                    encoding="utf-8", newline="\n")
            # 续跑：不带 --reviewer，验证 run_meta 恢复 both；同材料幂等命中
            cmd2 = [sys.executable, str(SCRIPTS["runner.py"]),
                    "--resume", last["run_dir"]]
            p2 = subprocess.run(cmd2, shell=False, capture_output=True,
                                text=True, encoding="utf-8",
                                errors="replace", timeout=120, env=env)
            last = json.loads(p2.stdout)
            if last.get("state") == "DONE":
                break
            self.assertEqual(last.get("state"), "WAIT_HOST_LLM",
                             json.dumps(last, ensure_ascii=False)[:300])
        self.assertEqual(p2.returncode, 0)
        self.assertEqual(last.get("state"), "DONE")
        sources = {f.get("source") for f in last.get("findings", [])}
        self.assertIn("llm", sources, "宿主响应必须并入双意见")
        self.assertIn("deterministic", sources, "确定性发现必须保留")

    def test_host_mode_idempotent_task_id(self):
        """幂等契约：同一提示词（同材料）重算 id 不变，续跑命中同一响应。"""
        from llm import provider
        tid1 = provider.task_id("sys", "user-content")
        tid2 = provider.task_id("sys", "user-content")
        tid3 = provider.task_id("sys", "user-content-CHANGED")
        self.assertEqual(tid1, tid2)
        self.assertNotEqual(tid1, tid3)
        self.assertEqual(select_behavior(), "none")  # 无任何配置时保持降级


def select_behavior():
    from llm import provider
    return provider.select(env={})


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
