#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_delivery.py — PR 交付包（pr-kit）契约断言。"""

import json
import unittest
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import SCRIPTS

RESULT = {
    "ok": True,
    "state": "DONE",
    "run_dir": "runs/r1",
    "rounds_used": 5,
    "tests": {"status": "pass", "detail": ["1 passed"]},
    "inline": [
        {"file": "a.py", "line": 10, "severity": "高",
         "message": "出现了硬规则命中", "suggestion": "改为环境变量读取"},
        {"file": "b.py", "line": 22, "severity": "中",
         "message": "可变默认参数", "suggestion": "None 哨兵"},
    ],
}


class TestPrKit(unittest.TestCase):
    """pr-kit：标题/正文/行内评论三件套，只读转换，不联网。"""

    def _write_result(self, tmp):
        report = tmp / "report.md"
        report.write_text("# 评审报告\n\n正文内容", encoding="utf-8", newline="\n")
        result = tmp / "result.json"
        payload = dict(RESULT, report_path=str(report))
        result.write_text(json.dumps(payload, ensure_ascii=False),
                          encoding="utf-8", newline="\n")
        return result

    def test_bundle_generation(self):
        tmp = test_scripts.FIXTURE["tmp"] / "prkit"
        tmp.mkdir(exist_ok=True)
        result = self._write_result(tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["pr-kit.py"], "--result",
                                          result, "--out", tmp / "bundle",
                                          "--approval", "ap/approval.json")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        title = (tmp / "bundle" / "pr-title.txt").read_text(encoding="utf-8")
        self.assertIn("发现 2 项", title)
        self.assertIn("高 1", title)
        body = (tmp / "bundle" / "pr-body.md").read_text(encoding="utf-8")
        for token in ("## 评审摘要", "行为回归", "ap/approval.json",
                      "完整评审报告", "五道闸"):
            self.assertIn(token, body)
        comments = json.loads((tmp / "bundle" / "review-comments.json")
                              .read_text(encoding="utf-8"))
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["path"], "a.py")
        self.assertIn("[高]", comments[0]["body"])
        self.assertIn("建议", comments[0]["body"])

    def test_missing_result_exit_2(self):
        tmp = test_scripts.FIXTURE["tmp"] / "prkit-missing"
        tmp.mkdir(exist_ok=True)
        rc, data, _, _ = test_scripts.run(SCRIPTS["pr-kit.py"], "--result",
                                          tmp / "nope.json", "--out", tmp / "b")
        self.assertEqual(rc, 2)

    def test_prkit_self_scan_zero(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", SCRIPTS["pr-kit.py"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["findings"], [])


class TestPrPublish(unittest.TestCase):
    """PR 发布器：回环 stub 创建 PR、token/远端校验、失败如实。"""

    def setUp(self):
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server 接口固定命名
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    body = b'{"message": "Bad credentials"}'
                    self.send_response(401)
                else:
                    body = json.dumps({"html_url": "https://github.com/me/p/pull/7",
                                       "number": 7}).encode("utf-8")
                    self.send_response(201)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)

    def _bundle(self, tmp):
        bundle = tmp / "bundle"
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "pr-title.txt").write_text("评审发现 2 项", encoding="utf-8",
                                             newline="\n")
        (bundle / "pr-body.md").write_text("## 摘要\n正文", encoding="utf-8",
                                           newline="\n")
        return bundle

    def test_publish_creates_pr(self):
        tmp = test_scripts.FIXTURE["tmp"] / "pub-ok"
        self._bundle(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["pr-publish.py"], "--bundle", tmp / "bundle",
            "--repo", "me/proj", "--head", "review-fix/x", "--base", "main",
            "--remote", "http://127.0.0.1:%d" % self.port,
            env_extra={"PUBLISH_GIT_TOKEN": "t0ken"})
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["pr_url"], "https://github.com/me/p/pull/7")
        self.assertEqual(data["number"], 7)

    def test_publish_requires_token(self):
        tmp = test_scripts.FIXTURE["tmp"] / "pub-notoken"
        self._bundle(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["pr-publish.py"], "--bundle", tmp / "bundle",
            "--repo", "me/proj", "--head", "h", "--base", "main",
            "--remote", "http://127.0.0.1:%d" % self.port)
        self.assertEqual(rc, 2)
        self.assertIn("PUBLISH_GIT_TOKEN", data.get("error", ""))

    def test_publish_rejects_private_remote(self):
        tmp = test_scripts.FIXTURE["tmp"] / "pub-private"
        self._bundle(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["pr-publish.py"], "--bundle", tmp / "bundle",
            "--repo", "me/proj", "--head", "h", "--base", "main",
            "--remote", "http://10.0.0.1:8000",
            env_extra={"PUBLISH_GIT_TOKEN": "t0ken"})
        self.assertEqual(rc, 2)
        self.assertIn("仅允许 https 公网或 http 回环", data.get("error", ""))


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
