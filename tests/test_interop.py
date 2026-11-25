#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Harness / MCP 互操作层验收（BASELINE「互操作契约」）。

端到端以子进程拉起 mcp/review_mcp.py，逐行喂 JSON-RPC；run 工具复用
test_scripts 的临时 git 仓库 FIXTURE。TS 原生插件不随仓库发布（本地安全
策略），相应断言只覆盖 cordis.yml.example 与 README 的契约文本。
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace
from _scripts_common import SCRIPTS

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp" / "review_mcp.py"
CORDIS_EXAMPLE = ROOT / "interop" / "deepseek-harness" / "cordis.yml.example"
INTEROP_README = ROOT / "interop" / "deepseek-harness" / "README.md"
PLUGIN_JSON = ROOT / ".zcode-plugin" / "plugin.json"

TOOL_NAMES = ["code_review_run", "code_review_scan",
              "code_review_plan", "code_review_feedback",
              "code_review_approve", "code_review_fix",
              "code_review_retro", "code_review_director",
              "code_review_testgen", "code_review_coding",
              "code_review_refactor", "code_review_apply",
               "code_review_submit", "code_review_status",
               "code_review_cancel", "code_review_purge"]

CLEAN_SRC = "def add(a, b):\n    return a + b\n"
DEFECT_SRC = ("import json\n\n\ndef load(data):\n"
              "    try:\n        return json.loads(data)\n"
              "    except:\n        pass\n")


class _Server:
    """一次会话一个 MCP 服务器子进程。"""

    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(MCP_SERVER)], shell=False,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def send_raw(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def recv(self):
        line = self.proc.stdout.readline()
        if not line:
            raise AssertionError("服务器无响应（疑似崩溃退出）")
        return json.loads(line)

    def rpc(self, method, params=None, mid=1):
        msg = {"jsonrpc": "2.0", "id": mid, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        return self.recv()

    def call_tool(self, name, arguments, mid=1):
        return self.rpc("tools/call",
                        {"name": name, "arguments": arguments}, mid=mid)

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait(timeout=15)


class TestInterop(unittest.TestCase):
    """互操作契约：协议、四工具、宿主清单、自扫。"""

    def setUp(self):
        self.server = _Server()
        self.addCleanup(self.server.close)

    def test_initialize_and_notification_silence(self):
        resp = self.server.rpc("initialize", {}, mid=7)
        self.assertEqual(resp["id"], 7)
        result = resp["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"]["name"], "dev-agent")
        self.assertIn("tools", result["capabilities"])
        # 通知帧（无 id）不回复：若服务器误回通知，这里 recv 到的会是
        # 通知应答（无 id）而非 ping 应答（id=8），断言即失败
        self.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        resp2 = self.server.rpc("ping", mid=8)
        self.assertEqual(resp2["id"], 8)
        self.assertEqual(resp2["result"], {})

    def test_tools_list_contract(self):
        tools = self.server.rpc("tools/list")["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], TOOL_NAMES)
        schemas = {t["name"]: t["inputSchema"] for t in tools}
        for name, schema in schemas.items():
            self.assertEqual(schema["type"], "object", name)
        self.assertEqual(schemas["code_review_plan"]["required"], ["diff_path"])
        self.assertEqual(schemas["code_review_feedback"]["required"],
                         ["findings_path", "experience_path"])
        self.assertIn("resume", schemas["code_review_run"]["properties"])
        self.assertIn("diff_path", schemas["code_review_scan"]["properties"])
        # annotations 契约（2025-06-18 口径）：12 个工具逐个声明；
        # 只读类 readOnlyHint=true，fix/apply destructiveHint=true +
        # openWorldHint=false，apply 注解说明 confirm 语义。
        anns = {t["name"]: t["annotations"] for t in tools}
        self.assertEqual(len(anns), len(TOOL_NAMES))
        for name in TOOL_NAMES:
            self.assertTrue(anns[name], name)
        for name in ("code_review_run", "code_review_scan",
                     "code_review_plan"):
            self.assertTrue(anns[name]["readOnlyHint"], name)
        for name in ("code_review_fix", "code_review_apply"):
            self.assertTrue(anns[name]["destructiveHint"], name)
            self.assertFalse(anns[name]["openWorldHint"], name)
        self.assertIn("confirm", anns["code_review_apply"]["title"])

    def test_scan_clean_and_defect(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean.py"
            defect = Path(tmp) / "defect.py"
            clean.write_text(CLEAN_SRC, encoding="utf-8")
            defect.write_text(DEFECT_SRC, encoding="utf-8")
            resp = self.server.call_tool("code_review_scan", {"path": str(clean)})
            self.assertFalse(resp["result"]["isError"])
            self.assertEqual(json.loads(resp["result"]["content"][0]["text"])["findings"], [])
            resp = self.server.call_tool("code_review_scan", {"path": str(defect)}, mid=2)
            self.assertFalse(resp["result"]["isError"])
            self.assertTrue(json.loads(resp["result"]["content"][0]["text"])["findings"])

    def test_scan_param_conflict_is_tool_error(self):
        resp = self.server.call_tool("code_review_scan", {})
        self.assertTrue(resp["result"]["isError"])
        resp = self.server.call_tool(
            "code_review_scan", {"path": "a.py", "diff_path": "b.diff"}, mid=2)
        self.assertTrue(resp["result"]["isError"])

    def test_refactor_scan_and_fix_dry(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "mod.py"
            src.write_text("def f(x, d, k):\n"
                           "    if x == None:\n        return 1\n"
                           "    if k in d.keys():\n        return 0\n",
                           encoding="utf-8")
            resp = self.server.call_tool(
                "code_review_refactor", {"mode": "scan", "file": str(src)})
            self.assertFalse(resp["result"]["isError"])
            data = json.loads(resp["result"]["content"][0]["text"])
            codes = {f["rule_id"] for f in data["findings"]}
            self.assertIn("libcst:ref-eq-none", codes)
            self.assertIn("libcst:ref-in-keys", codes)
            resp = self.server.call_tool(
                "code_review_refactor",
                {"mode": "fix-dry", "repo": tmp, "rel": "mod.py",
                 "out": str(Path(tmp) / "p")})
            self.assertFalse(resp["result"]["isError"])
            data = json.loads(resp["result"]["content"][0]["text"])
            self.assertGreater(data["patch_bytes"], 0)
            self.assertEqual(data["residual_codes"], [])
        resp = self.server.call_tool("code_review_refactor", {"mode": "nope"})
        self.assertTrue(resp["result"]["isError"])

    def test_unknown_tool_is_error_result(self):
        resp = self.server.call_tool("no_such_tool", {})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("未知工具", resp["result"]["content"][0]["text"])

    def test_unknown_method_and_bad_frame_recovery(self):
        resp = self.server.rpc("foo/bar", mid=3)
        self.assertEqual(resp["error"]["code"], -32601)
        self.server.send_raw("{not json")
        resp = self.server.recv()
        self.assertEqual(resp["error"]["code"], -32700)
        self.assertIsNone(resp["id"])
        resp = self.server.rpc("ping", mid=4)
        self.assertEqual(resp["result"], {})

    def test_run_end_to_end_on_temp_repo(self):
        out = test_scripts.FIXTURE["tmp"] / "mcp-run"
        resp = self.server.call_tool(
            "code_review_run",
            {"repo": str(test_scripts.FIXTURE["repo"]),
             "range": "%s..%s" % (test_scripts.FIXTURE["shaA"],
                                  test_scripts.FIXTURE["shaB"]),
             "out": str(out),
             "skip_probe": True})
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(data["ok"])
        self.assertEqual(data["state"], "DONE")
        self.assertTrue((Path(data["run_dir"]) / "totals.json").is_file())

    def test_run_param_guard(self):
        resp = self.server.call_tool("code_review_run", {"repo": "x"})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("repo + range", resp["result"]["content"][0]["text"])

    def test_manifest_mcp_and_version_sync(self):
        plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        # 版本真值只有 plugin.json 一处：这里过去抄了第二个字面量，升 1.32.0 后
        # 它成了全量套件里唯一漏网的一条（红在 '1.32.0' != '1.31.0'）。改成钉住
        # 真正的同步契约——README 头条的版本号必须等于 manifest 版本号，人工只需
        # 维护一处，抄件本身不会再漂移。
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        m = re.search(r"\*\*版本 (\d+\.\d+\.\d+)\*\*", readme)
        self.assertTrue(m, "README 头条缺少 **版本 x.y.z**")
        self.assertEqual(plugin["version"], m.group(1))
        self.assertGreaterEqual([int(x) for x in plugin["version"].split(".")],
                                 [1, 0, 0])
        mcp = plugin["mcpServers"]["code-review"]
        args = [a.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)) for a in mcp["args"]]
        self.assertTrue(any(a.endswith("review_mcp.py") for a in args))
        self.assertTrue(MCP_SERVER.is_file())

    def test_cordis_example_and_readme_contract(self):
        yml = CORDIS_EXAMPLE.read_text(encoding="utf-8")
        for token in ("@deepseek-ai/dsh-mcp-client", "serverName: code-review",
                      "transport: stdio", "review_mcp.py", "autoApprove"):
            self.assertIn(token, yml)
        readme = INTEROP_README.read_text(encoding="utf-8")
        for token in ("mcp__code-review__", "code_review_run", "2025-06-18",
                      "NEED_HUMAN", "shell=False"):
            self.assertIn(token, readme)

    def test_interop_self_scan_zero(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", MCP_SERVER)
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [], "MCP 服务器自扫出现命中")

    def _fix_repo(self):
        """含 1 类白名单缺陷的临时 git 仓库 + 其发现清单。"""
        tmp = tmpspace.create(prefix="mcp-fix-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "defect.py").write_text("def f(a=[]):\n    return a\n",
                                        encoding="utf-8", newline="\n")
        for args in (["init", "-q"],
                     ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", repo / "defect.py")
        self.assertEqual(rc, 0)
        findings = tmp / "findings.json"
        findings.write_text(json.dumps(data, ensure_ascii=False),
                            encoding="utf-8", newline="\n")
        return tmp, repo, findings

    def test_approve_fix_apply_full_chain(self):
        """MCP 三方链：闸1 工单 → 修复补丁 → 闸2 批准书 → 落盘。"""
        tmp, repo, findings = self._fix_repo()
        resp = self.server.call_tool(
            "code_review_approve",
            {"mode": "scope", "repo": str(repo), "findings_path": str(findings),
             "out_dir": str(tmp / "ap")})
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        gate1 = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(gate1["ok"])
        order = tmp / "ap" / "work-order.json"
        self.assertTrue(order.is_file())
        resp = self.server.call_tool(
            "code_review_fix",
            {"order_path": str(order), "repo": str(repo),
             "out_dir": str(tmp / "out")}, mid=2)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        fix_out = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(fix_out["ok"])
        self.assertEqual(fix_out["order_id"], gate1["order_id"])
        manifest = tmp / "out" / "fix-manifest.json"
        self.assertTrue(manifest.is_file())
        resp = self.server.call_tool(
            "code_review_approve",
            {"mode": "patch", "repo": str(repo), "order_path": str(order),
             "manifest_path": str(manifest), "out_dir": str(tmp / "ap")}, mid=3)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        gate2 = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(gate2["verdict"], "APPROVED")
        approval = tmp / "ap" / "approval.json"
        # confirm=true 但无批准书 → 拒绝（第五道闸）
        resp = self.server.call_tool(
            "code_review_apply",
            {"manifest_path": str(manifest), "repo": str(repo), "confirm": True},
            mid=4)
        self.assertTrue(resp["result"]["isError"])
        # 批准书 + confirm → APPLIED，复扫零发现
        resp = self.server.call_tool(
            "code_review_apply",
            {"manifest_path": str(manifest), "repo": str(repo),
             "approval_path": str(approval), "confirm": True}, mid=5)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        self.assertEqual(json.loads(resp["result"]["content"][0]["text"])["state"],
                         "APPLIED")
        rc, rescanned, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                               "--file", repo / "defect.py")
        self.assertEqual(rescanned["findings"], [])

    def test_approve_tool_rejects_bad_mode(self):
        tmp, repo, findings = self._fix_repo()
        resp = self.server.call_tool(
            "code_review_approve",
            {"mode": "nope", "repo": str(repo),
             "findings_path": str(findings), "out_dir": str(tmp / "ap")})
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("scope|patch", resp["result"]["content"][0]["text"])

    def test_retro_tool_ledger_and_report(self):
        """迭代官工具：collect 入台账，report 出轮报与候选。"""
        tmp = tmpspace.create(prefix="mcp-retro-")
        self.addCleanup(tmpspace.release, tmp)
        events = tmp / "events.json"
        events.write_text(json.dumps({"events": [
            {"category": "手工", "description": "上一轮演示坑：补丁未过行为回归",
             "countermeasure": "为被修行为补测试"}]},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        resp = self.server.call_tool(
            "code_review_retro",
            {"mode": "collect", "out_dir": str(tmp / "retro"),
             "events_path": str(events)}, mid=1)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        collect = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(collect["total"], 1)
        resp = self.server.call_tool(
            "code_review_retro",
            {"mode": "report", "out_dir": str(tmp / "retro"), "round": 1}, mid=2)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        report = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(report["round"], 1)
        self.assertTrue(Path(report["report"]).is_file())
        self.assertTrue(report["candidates"])

    def test_retro_tool_report_guard_refuses_real_repo_auto(self):
        """反向验证：真仓形态（out_dir 有 next-round.md）report 缺 round 必须
        被拒——护栏单点在脚本（r155 坑 a5ba44db35ee），MCP 透传错误面。"""
        tmp = tmpspace.create(prefix="mcp-retro-guard-")
        self.addCleanup(tmpspace.release, tmp)
        retro = tmp / "retro"
        retro.mkdir(parents=True)
        (retro / "pitfalls.json").write_text(json.dumps(
            {"pitfalls": [{"id": "m1", "category": "手工",
                           "description": "MCP 护栏用例", "status": "open"}]},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        (retro / "next-round.md").write_text(
            "# 下一轮开局检查单\n\n> round-154 收官（2026-11-14）。下一轮（round-155）。\n",
            encoding="utf-8", newline="\n")
        resp = self.server.call_tool(
            "code_review_retro",
            {"mode": "report", "out_dir": str(retro)}, mid=1)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("护栏", resp["result"]["content"][0]["text"])

    def test_director_tool_route_and_match(self):
        """总监工具：route 分派带指挥链；match 案例库复用。"""
        resp = self.server.call_tool(
            "code_review_director",
            {"mode": "route", "kind": "fix", "payload": "runs/r1/out"}, mid=1)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        route = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(route["assignee"]["role"], "repair")
        self.assertIn("director", route["chain_of_command"])
        resp = self.server.call_tool(
            "code_review_director",
            {"mode": "match", "problem": "审核人拒绝后补丁仍然落盘"}, mid=2)
        self.assertFalse(resp["result"]["isError"], resp["result"]["content"][0]["text"])
        match = json.loads(resp["result"]["content"][0]["text"])
        self.assertTrue(match["ok"])
        self.assertTrue(match["cases_total"] >= 1, "案例库应有已入库案例")

    def test_director_tool_rejects_bad_mode(self):
        resp = self.server.call_tool(
            "code_review_director", {"mode": "nope"}, mid=1)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("route|match|brief|scorecard",
                      resp["result"]["content"][0]["text"])

    def test_director_tool_rejects_bad_kind(self):
        resp = self.server.call_tool(
            "code_review_director", {"mode": "route", "kind": "hack"}, mid=1)
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("未知任务类型", resp["result"]["content"][0]["text"])


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
