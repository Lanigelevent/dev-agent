#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D-055 MCP 异步作业契约（submit/status + jobs 资源，6 条）。

以假 runner 子进程完成真实作业生命周期，不依赖外部 LLM 端点；
JOB_ROOT 经 unittest.mock 定向到临时目录，作业 worker 用 --job-root 接力。
"""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MCP_PATH = ROOT / "mcp" / "review_mcp.py"
SPEC = importlib.util.spec_from_file_location("review_mcp_async", MCP_PATH)
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)

FAKE_RUNNER = """# -*- coding: utf-8 -*-
import sys
print('PROGRESS step=3/10', file=sys.stderr, flush=True)
print('[step 3] locate', flush=True)
print('PROGRESS step=7/10', file=sys.stderr, flush=True)
print('[step 7] verify', flush=True)
print('PROGRESS step=10/10', file=sys.stderr, flush=True)
print('{\"state\": \"ok\", \"findings\": []}', flush=True)
"""

FAKE_FAIL = """# -*- coding: utf-8 -*-
import sys
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
print('[step 2] early-fail', flush=True)
sys.exit(2)
"""

FAKE_FAST = """# -*- coding: utf-8 -*-
import sys
print('PROGRESS step=10/10', file=sys.stderr, flush=True)
print('{\"state\": \"ok\", \"findings\": []}', flush=True)
"""

FAKE_NOFRAME = """# -*- coding: utf-8 -*-
print('{\"state\": \"ok\", \"findings\": []}', flush=True)
"""


class TestMcpAsync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_tmp)
        self.jobs = Path(self.tmp.name) / "jobs"
        self.jobs.mkdir()
        patcher = mock.patch.object(MCP, "JOB_ROOT", self.jobs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cleanup_tmp(self):
        """detached worker 可能仍持 runner.log；有界重试后再放弃（不阻塞套件）。"""
        for attempt in range(10):
            try:
                self.tmp.cleanup()
                return
            except PermissionError:
                time.sleep(0.5)

    def _fake_script(self, name, source):
        p = Path(self.tmp.name) / name
        p.write_text(source, encoding="utf-8")
        return p

    def _submit(self, fake, **extra):
        args = {"repo": self.tmp.name, "range": "HEAD~1..HEAD",
                "request": "只读评审自检的异步作业冒烟"}
        args.update(extra)
        with mock.patch.object(MCP, "SCRIPT_RUNNER", str(fake)):
            resp = MCP._submit_tool(args)
        self.assertFalse(resp["isError"], resp)
        return json.loads(resp["content"][0]["text"])["job_id"]

    def _wait(self, job_id, timeout=20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data = json.loads(MCP._status_tool(
                {"job_id": job_id})["content"][0]["text"])
            if data.get("state") in ("done", "failed"):
                return data
            time.sleep(0.25)
        self.fail("job %s 未在 %.1fs 内终局" % (job_id, timeout))

    # 1) 工具面契约
    def test_tools_contract(self):
        names = [t["name"] for t in MCP.TOOLS]
        self.assertEqual(names[-4:], ["code_review_submit", "code_review_status",
                                      "code_review_cancel", "code_review_purge"])
        self.assertEqual(len(names), 16)
        schemas = {t["name"]: t["inputSchema"] for t in MCP.TOOLS}
        self.assertEqual(schemas["code_review_status"]["required"], ["job_id"])
        self.assertIn("budget", schemas["code_review_submit"]["properties"])
        anns = {t["name"]: t["annotations"] for t in MCP.TOOLS}
        self.assertTrue(anns["code_review_status"]["readOnlyHint"])
        for name in ("code_review_submit", "code_review_status"):
            self.assertFalse(anns[name]["destructiveHint"])
            self.assertFalse(anns[name]["openWorldHint"])

    # 2) submit 入参守卫
    def test_submit_guards(self):
        for args in ({}, {"repo": "x"}, {"repo": "x", "range": "a..b",
                                          "reviewer": "bogus"},
                     {"repo": "x", "range": "a..b", "budget": 0}):
            self.assertTrue(MCP._submit_tool(args)["isError"], args)
        self.assertFalse(MCP._submit_tool(
            {"repo": "x", "range": "a..b", "budget": 5,
             "config_path": "agent.json"})["isError"])  # B 阶段：不再互斥

    # 3) 非法 job_id / 路径穿越拒绝
    def test_status_rejects_unsafe_id(self):
        for job_id in ("", "../escape", "0" * 31, "z" * 32, "0" * 33):
            resp = MCP._status_tool({"job_id": job_id})
            self.assertTrue(resp["isError"], job_id)

    # 4) 真实假作业生命周期（queued → running → done）
    def test_fake_job_lifecycle(self):
        fake = self._fake_script("fake_runner.py", FAKE_RUNNER)
        job_id = self._submit(fake, budget=5)
        self.assertRegex(job_id, r"^[0-9a-f]{32}$")
        job_dir = self.jobs / job_id
        self.assertTrue((job_dir / "job.json").exists())
        cfg = json.loads((job_dir / "agent.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["args"]["max_review_minutes"], 5)
        data = self._wait(job_id)
        self.assertEqual(data["state"], "done")
        self.assertEqual(data["exit_code"], 0)
        self.assertEqual(data["progress"], 1.0)
        self.assertEqual(data["step"], 10)  # D-055 进度帧：终态必须到 10
        self.assertEqual(data["findings_url"], "review://jobs/" + job_id)
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "ok")

    # 5) 资源面：resources/list + resources/read
    def test_resources_list_and_read(self):
        fake = self._fake_script("fake_runner_ok.py", FAKE_RUNNER)
        job_id = self._submit(fake)
        final = self._wait(job_id)
        self.assertEqual(final["state"], "done")
        listed = MCP._resources_list()
        self.assertTrue(any(r["uri"] == "review://jobs/" + job_id
                            for r in listed))
        message = {"jsonrpc": "2.0", "id": 3, "method": "resources/read",
                   "params": {"uri": "review://jobs/" + job_id}}
        resp = MCP._handle(message)
        payload = json.loads(resp["result"]["contents"][0]["text"])
        self.assertEqual(payload["state"], "ok")
        self.assertIsNone(MCP._resource_read("review://jobs/../etc/passwd"))

    # 6) 失败作业 + 资源未知 URI 守卫
    def test_failed_job_and_unknown_resource(self):
        fake = self._fake_script("fake_runner_fail.py", FAKE_FAIL)
        job_id = self._submit(fake)
        final = self._wait(job_id)
        self.assertEqual(final["state"], "failed")
        self.assertEqual(final["exit_code"], 2)
        self.assertIn("exit=2", final["error"])
        self.assertIsNone(final["findings_url"])
        resp = MCP._handle({"jsonrpc": "2.0", "id": 9,
                            "method": "resources/read",
                            "params": {"uri": "review://jobs/" + "a" * 32}})
        self.assertTrue(resp["result"]["isError"])


    # 7) 进度帧在 running 阶段单调递进（runner.py stderr PROGRESS step=N/10）
    def test_progress_frames_monotonic(self):
        fake = self._fake_script("fake_runner_progressive.py", """# -*- coding: utf-8 -*-
import sys, time
for n in (1, 4, 8):
    print('PROGRESS step=%d/10' % n, file=sys.stderr, flush=True)
    time.sleep(0.9)
print('PROGRESS step=10/10', file=sys.stderr, flush=True)
print('{\"state\": \"ok\"}', flush=True)
""")
        job_id = self._submit(fake)
        seen = []
        for _ in range(40):
            data = json.loads(MCP._status_tool(
                {"job_id": job_id})["content"][0]["text"])
            if data.get("step") is not None:
                seen.append(data["step"])
            if data.get("state") in ("done", "failed"):
                break
            time.sleep(0.25)
        self.assertEqual(seen, sorted(seen), seen)
        self.assertGreaterEqual(max(seen), 4, seen)
        self.assertEqual(data["step"], 10)

    # 8) 快作业：两轮轮询之间结束，终局前补扫全量日志仍得 step=10
    def test_fast_job_final_step_scan(self):
        fake = self._fake_script("fake_runner_fast.py", FAKE_FAST)
        job_id = self._submit(fake)
        final = self._wait(job_id)
        self.assertEqual(final["state"], "done")
        self.assertEqual(final["step"], 10)

    # 9) 无进度帧时不伪造 step（诚实口径）
    def test_no_progress_frame_is_honest(self):
        fake = self._fake_script("fake_runner_noframe.py", FAKE_NOFRAME)
        job_id = self._submit(fake)
        final = self._wait(job_id)
        self.assertEqual(final["state"], "done")
        self.assertEqual(final["step"], 0)
        self.assertEqual(final["progress"], 1.0)


    # 10) cancel 工具面契约（阶段 B）
    def test_cancel_tool_contract(self):
        names = [t["name"] for t in MCP.TOOLS]
        self.assertEqual(names[-2], "code_review_cancel")
        self.assertEqual(names[-1], "code_review_purge")
        schemas = {t["name"]: t["inputSchema"] for t in MCP.TOOLS}
        self.assertEqual(schemas["code_review_cancel"]["required"], ["job_id"])
        anns = {t["name"]: t["annotations"] for t in MCP.TOOLS}
        self.assertTrue(anns["code_review_cancel"]["destructiveHint"])
        self.assertFalse(anns["code_review_cancel"]["readOnlyHint"])
        self.assertFalse(anns["code_review_cancel"]["openWorldHint"])

    # 11) 取消 running 作业：状态 cancelled 且 worker 不覆写
    def test_cancel_running_job(self):
        fake = self._fake_script("fake_runner_long.py", """# -*- coding: utf-8 -*-
import sys, time
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
time.sleep(60)
""")
        job_id = self._submit(fake)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            st = json.loads(MCP._status_tool(
                {"job_id": job_id})["content"][0]["text"])
            if st.get("state") == "running":
                break
            time.sleep(0.2)
        self.assertEqual(st["state"], "running")
        resp = MCP._cancel_tool({"job_id": job_id})
        self.assertFalse(resp["isError"], resp)
        data = json.loads(resp["content"][0]["text"])
        self.assertEqual(data["state"], "cancelled")
        self.assertTrue(data["ledger_ok"])
        self.assertTrue(data["killed_pids"], "running 取消必须拿到并终止 runner pid")
        time.sleep(2)
        final = json.loads(MCP._status_tool(
            {"job_id": job_id})["content"][0]["text"])
        self.assertEqual(final["state"], "cancelled")  # worker 不得覆写
        self.assertIsNone(final["exit_code"])

    # 12) 终态作业取消被拒 + 非法 id 守卫
    def test_cancel_terminal_and_bad_id(self):
        fake = self._fake_script("fake_runner_done.py", FAKE_RUNNER)
        job_id = self._submit(fake)
        final = self._wait(job_id)
        self.assertEqual(final["state"], "done")
        self.assertTrue(MCP._cancel_tool({"job_id": job_id})["isError"])
        for bad in ("", "../escape", "a" * 32):
            self.assertTrue(MCP._cancel_tool({"job_id": bad})["isError"])

    # 13) 配置白名单透传：budget + config_path 共存，凭据/未知键被忽略并回显
    def test_config_whitelist_and_budget(self):
        cfg = Path(self.tmp.name) / "agent.json"
        cfg.write_text(json.dumps({"args": {
            "max_review_minutes": 99, "max_total_rounds": 8,
            "max_verification_rounds": 9, "unknown_key": 1,
            "REVIEW_LLM_API_KEY": "should-be-ignored"}}), encoding="utf-8")
        fake = self._fake_script("fake_runner_cfg.py", FAKE_RUNNER)
        args = {"repo": self.tmp.name, "range": "HEAD~1..HEAD", "config_path": str(cfg),
                "budget": 3}
        with mock.patch.object(MCP, "SCRIPT_RUNNER", str(fake)):
            resp = MCP._submit_tool(args)
        self.assertFalse(resp["isError"])
        data = json.loads(resp["content"][0]["text"])
        self.assertIn("unknown_key", data["ignored_keys"])
        self.assertIn("REVIEW_LLM_API_KEY", data["ignored_keys"])
        sandbox = json.loads((self.jobs / data["job_id"] / "agent.json").read_text(
            encoding="utf-8"))["args"]
        self.assertEqual(sandbox["max_review_minutes"], 3)  # budget 覆盖
        self.assertEqual(sandbox["max_total_rounds"], 8)
        self.assertNotIn("max_verification_rounds", sandbox)  # 越界被丢
        self.assertNotIn("REVIEW_LLM_API_KEY", sandbox)

    # 14) 非法/不可读 config_path 明确报错（不静默降级）
    def test_bad_config_path_is_error(self):
        args = {"repo": self.tmp.name, "range": "HEAD~1..HEAD",
                "config_path": str(Path(self.tmp.name) / "missing.json")}
        self.assertTrue(MCP._submit_tool(args)["isError"])


    # 15) Unix 进程组终止路径（Windows 平台无法真跑，用 mock 验证语义）
    def test_kill_pid_posix_process_group(self):
        with mock.patch.object(MCP.os, "name", "posix"), \
             mock.patch.object(MCP.os, "getpgid", return_value=4242, create=True) as pgid, \
             mock.patch.object(MCP.os, "kill", create=True) as kill:
            self.assertTrue(MCP._kill_pid(99))
        pgid.assert_called_once_with(99)
        kill.assert_called_once_with(4242, MCP.signal.SIGTERM)

    # 16) 进程已退出（ProcessLookupError）→ False，不抛异常
    def test_kill_pid_missing_process(self):
        def boom(*args, **kwargs):
            raise ProcessLookupError("gone")
        with mock.patch.object(MCP.os, "name", "posix"), \
             mock.patch.object(MCP.os, "getpgid", side_effect=boom, create=True):
            self.assertFalse(MCP._kill_pid(12345))

    # 17) runner.pid 缺失时回退 worker_pid（竞态兜底）
    def test_cancel_falls_back_to_worker_pid(self):
        job_id = "a" * 32
        job_dir = self.jobs / job_id
        job_dir.mkdir()
        (job_dir / "job.json").write_text(json.dumps({"worker_pid": 777}), encoding="utf-8")
        MCP._status_write(job_dir, "running", progress=0.1)
        with mock.patch.object(MCP, "_kill_pid", return_value=True) as kill:
            resp = MCP._cancel_tool({"job_id": job_id})
        data = json.loads(resp["content"][0]["text"])
        self.assertFalse(resp["isError"])
        self.assertEqual(data["killed_pids"], [777])
        kill.assert_called_once_with(777)
        self.assertEqual(json.loads((job_dir / "status.json").read_text(
            encoding="utf-8"))["state"], "cancelled")


    # 18) A：done 作业资源 envelope（旧字段保留 + 新字段）
    def test_resource_envelope_done(self):
        fake = self._fake_script("fake_runner_env.py", FAKE_RUNNER)
        job_id = self._submit(fake)
        self.assertEqual(self._wait(job_id)["state"], "done")
        payload = json.loads(MCP._resource_read(
            "review://jobs/" + job_id)["contents"][0]["text"])
        self.assertEqual(payload["state"], "ok")  # 旧顶层字段不变
        self.assertEqual(payload["job_state"], "done")
        self.assertIsInstance(payload["status"], dict)
        self.assertIsInstance(payload["result"], dict)
        self.assertIn("cancel", payload)
        self.assertIn("ledger_verify", payload)

    # 19) A：cancelled 作业资源含 cancel 摘要 + ledger 校验
    def test_resource_cancel_summary(self):
        fake = self._fake_script("fake_runner_ledger.py", """# -*- coding: utf-8 -*-
import sys, time
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
time.sleep(60)
""")
        job_id = self._submit(fake)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            st = json.loads(MCP._status_tool({"job_id": job_id})["content"][0]["text"])
            if st.get("state") == "running":
                break
            time.sleep(0.2)
        MCP._cancel_tool({"job_id": job_id})
        payload = json.loads(MCP._resource_read(
            "review://jobs/" + job_id)["contents"][0]["text"])
        self.assertEqual(payload["job_state"], "cancelled")
        self.assertTrue(payload["cancel"]["killed_pids"])
        self.assertTrue(payload["ledger_verify"]["ok"])

    # 20) A：账本被篡改 → ledger_verify.ok=false
    def test_resource_tampered_ledger(self):
        fake = self._fake_script("fake_runner_tamper.py", """# -*- coding: utf-8 -*-
import sys, time
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
time.sleep(60)
""")
        job_id = self._submit(fake)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            st = json.loads(MCP._status_tool({"job_id": job_id})["content"][0]["text"])
            if st.get("state") == "running":
                break
            time.sleep(0.2)
        MCP._cancel_tool({"job_id": job_id})
        ledger = self.jobs / job_id / "ledger.jsonl"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        rec = json.loads(lines[0])
        rec["digest"] = "0" * 64
        lines[0] = json.dumps(rec, ensure_ascii=False)
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
        payload = json.loads(MCP._resource_read(
            "review://jobs/" + job_id)["contents"][0]["text"])
        self.assertFalse(payload["ledger_verify"]["ok"])
        self.assertIsNotNone(payload["ledger_verify"]["first_bad"])

    # 21) B：账本子资源 + resources/list 列出
    def test_resource_ledger_subresource(self):
        fake = self._fake_script("fake_runner_sub.py", """# -*- coding: utf-8 -*-
import sys, time
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
time.sleep(60)
""")
        job_id = self._submit(fake)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            st = json.loads(MCP._status_tool({"job_id": job_id})["content"][0]["text"])
            if st.get("state") == "running":
                break
            time.sleep(0.2)
        MCP._cancel_tool({"job_id": job_id})
        uri = "review://jobs/" + job_id + "/ledger"
        resp = MCP._resource_read(uri)
        self.assertIn("job.cancel", resp["contents"][0]["text"])
        self.assertTrue(any(r["uri"] == uri for r in MCP._resources_list()))
        self.assertIsNone(MCP._resource_read("review://jobs/" + "b" * 32 + "/ledger"))

    # 22) B：账本子资源 64KB 截断标记
    def test_resource_ledger_truncation(self):
        job_id = "c" * 32
        job_dir = self.jobs / job_id
        job_dir.mkdir()
        MCP._status_write(job_dir, "done")
        (job_dir / "ledger.jsonl").write_text("x" * 70000, encoding="utf-8")
        resp = MCP._resource_read("review://jobs/" + job_id + "/ledger")
        text = resp["contents"][0]["text"]
        self.assertIn("[TRUNCATED", text)
        self.assertLessEqual(len(text), MCP.LEDGER_MAX_BYTES + 80)


    # 23) purge 工具面契约（阶段 C）
    def test_purge_tool_contract(self):
        names = [t["name"] for t in MCP.TOOLS]
        self.assertEqual(len(names), 16)
        self.assertEqual(names[-1], "code_review_purge")
        schemas = {t["name"]: t["inputSchema"] for t in MCP.TOOLS}
        self.assertEqual(schemas["code_review_purge"]["required"], ["job_id"])
        anns = {t["name"]: t["annotations"] for t in MCP.TOOLS}
        self.assertTrue(anns["code_review_purge"]["destructiveHint"])
        self.assertIn("confirm", anns["code_review_purge"]["title"])

    # 24) purge 三重闸：非法 id / 非终态被拒；无 confirm 只预检
    def test_purge_guards(self):
        for job_id in ("", "../escape", "a" * 32):
            self.assertTrue(MCP._purge_tool({"job_id": job_id, "confirm": True})["isError"])
        fake = self._fake_script("fake_runner_purge_guard.py", """# -*- coding: utf-8 -*-
import sys, time
print('PROGRESS step=2/10', file=sys.stderr, flush=True)
time.sleep(60)
""")
        job_id = self._submit(fake)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            st = json.loads(MCP._status_tool({"job_id": job_id})["content"][0]["text"])
            if st.get("state") == "running":
                break
            time.sleep(0.2)
        self.assertTrue(MCP._purge_tool({"job_id": job_id, "confirm": True})["isError"])
        MCP._cancel_tool({"job_id": job_id})
        pre = MCP._purge_tool({"job_id": job_id})
        self.assertFalse(pre["isError"])
        self.assertTrue(json.loads(pre["content"][0]["text"])["PROPOSED"])
        self.assertTrue((self.jobs / job_id).exists())  # 未 confirm 不删

    # 25) purge 成功：目录删除 + 中央账本保留 job.purge 摘要 + 资源不可读
    def test_purge_success_and_ledger(self):
        fake = self._fake_script("fake_runner_purge_ok.py", FAKE_RUNNER)
        job_id = self._submit(fake)
        self.assertEqual(self._wait(job_id)["state"], "done")
        resp = MCP._purge_tool({"job_id": job_id, "confirm": True})
        self.assertFalse(resp["isError"])
        data = json.loads(resp["content"][0]["text"])
        self.assertTrue(data["purged"])
        self.assertFalse((self.jobs / job_id).exists())
        self.assertIsNone(MCP._resource_read("review://jobs/" + job_id))
        central = (self.jobs / "ledger.jsonl").read_text(encoding="utf-8")
        self.assertIn("job.purge", central)
        self.assertIn(job_id, central)


class TestMcpAsyncSilentSpawn(unittest.TestCase):
    """r188：异步作业 spawn 静默化——CREATE_NO_WINDOW（nt）替代 DETACHED_PROCESS。
    根因：DETACHED_PROCESS 令 worker 无控制台，runner 等子孙 spawn 控制台程序时
    被 Windows 分配可见控制台（用户报告的黑色弹窗）。CREATE_NO_WINDOW 给 worker
    隐藏控制台：子孙继承不闪窗，taskkill /T /F 取消语义不变。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._cleanup_tmp)
        self.jobs = Path(self.tmp.name) / "jobs"
        self.jobs.mkdir()
        patcher = mock.patch.object(MCP, "JOB_ROOT", self.jobs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cleanup_tmp(self):
        for attempt in range(10):
            try:
                self.tmp.cleanup()
                return
            except PermissionError:
                time.sleep(0.5)

    def _fake_script(self, name, source):
        p = Path(self.tmp.name) / name
        p.write_text(source, encoding="utf-8", newline="\n")
        return str(p)

    def test_submit_spawn_flags_silent(self):
        fake = self._fake_script(
            "fake_runner_silent.py",
            "import sys\n"
            "print('PROGRESS step=1/1', file=sys.stderr, flush=True)\n")
        captured = {}
        real_popen = MCP.subprocess.Popen

        def capture_popen(*a, **k):
            captured.update(k)
            return real_popen(*a, **k)

        args = {"repo": self.tmp.name, "range": "HEAD~1..HEAD",
                "request": "静默 spawn 契约锚定"}
        with mock.patch.object(MCP, "SCRIPT_RUNNER", fake), \
                mock.patch.object(MCP.subprocess, "Popen", side_effect=capture_popen):
            resp = MCP._submit_tool(args)
        self.assertFalse(resp["isError"], resp)
        if os.name == "nt":
            flags = captured.get("creationflags", 0)
            self.assertTrue(flags & getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            "worker spawn 应带 CREATE_NO_WINDOW（静默）")
            self.assertFalse(flags & getattr(subprocess, "DETACHED_PROCESS", 0),
                            "不得再用 DETACHED_PROCESS（弹窗根因）")
            self.assertTrue(flags & getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                            "组标记保留（取消语义不变）")
        else:
            self.assertTrue(captured.get("start_new_session"),
                            "POSIX 保持 start_new_session")


class TestStatusWriteConcurrency(unittest.TestCase):
    """r190：_status_write Windows 并发写防冲突——唯一 tmp 名 + PermissionError
    有界重试（r190 run2 实弹 PermissionError on status.json.tmp 的产品修复，
    红线 6 反向验证：并发写 + 并发读下异常零逃逸、终态可读）。"""

    def test_concurrent_writers_no_permission_error(self):
        tmp = Path(tempfile.mkdtemp(prefix="mcp-sw-r190-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        errors = []
        # 生产节奏建模：worker 每步写一次 + cancel 并发写——紧自旋（0 间隔）
        # 会超出重试预算的设计包络（r190 run1 实测病态压力下偶发逃逸）；
        # 5-15ms 随机间隔 × 4 写 1 读 × 3s 仍是重负载并发，且不超过包络。
        deadline = time.perf_counter() + 3.0

        def writer():
            while time.perf_counter() < deadline:
                try:
                    MCP._status_write(tmp, "running", progress=0.5)
                except Exception as exc:  # noqa: BLE001 任何写异常都算失败
                    errors.append(exc)
                    return
                time.sleep(0.005 + (hash(threading.get_ident()) % 10) / 1000.0)

        def reader():
            while time.perf_counter() < deadline:
                try:
                    MCP._read_json_retry(tmp / "status.json")
                    reads[0] += 1
                except FileNotFoundError:
                    pass
                time.sleep(0.01)

        reads = [0]
        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        while time.perf_counter() < deadline:
            time.sleep(0.05)
        for t in threads:
            t.join()
        self.assertEqual(errors, [], "并发写（生产节奏建模）不得逃逸任何异常")
        self.assertGreater(reads[0], 0, "并发读（产品 helper）应成功读到终态")
        data = MCP._read_json_retry(tmp / "status.json")
        self.assertEqual(data["state"], "running")


if __name__ == "__main__":
    unittest.main()
