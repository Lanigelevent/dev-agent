# -*- coding: utf-8 -*-
"""tests/test_github_poster.py — github-poster.py 契约（round-113，P0-3）。

覆盖：载荷构造（path/line/body/commit_id）、dry-run 不联网、422 如实计
失败、环回假服务器真实 POST、token 只走环境变量、端点白名单。
"""
import contextlib
import importlib.util
import io
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "orchestrator" / "scripts" / "github-poster.py"


def _load():
    spec = importlib.util.spec_from_file_location("gp_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


COMMENTS = [
    {"path": "a.py", "line": 3, "body": "[高] 硬编码密码"},
    {"path": "b.py", "line": 7, "body": "[中] 可变默认参数"},
]


class _FakeHub(BaseHTTPRequestHandler):
    posted = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(n).decode("utf-8"))
        _FakeHub.posted.append({"url": self.path, "payload": payload,
                                "auth": self.headers.get("Authorization",
                                                         "")})
        status = 201
        if payload.get("path") == "b.py":
            status = 422
        body = json.dumps({"id": len(_FakeHub.posted)}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class GithubPosterTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = Path(tmpspace.create(prefix="gposter-"))
        self.addCleanup(tmpspace.release, self.tmp)
        cp = self.tmp / "review-comments.json"
        cp.write_text(json.dumps(COMMENTS, ensure_ascii=False),
                      encoding="utf-8")
        self.cp = str(cp)

    def test_payload_and_422_accounting(self):
        srv = HTTPServer(("127.0.0.1", 0), _FakeHub)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        self.addCleanup(srv.shutdown)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        _FakeHub.posted = []
        rc, out = self._invoke([
            "--repo", "o/r", "--pr", "7", "--comments", self.cp,
            "--commit-id", "abc123", "--base-url", base,
            "--token-env", "GP_TEST_TOKEN"], env={"GP_TEST_TOKEN": "t"})
        d = json.loads(out)
        self.assertEqual(rc, 1)          # b.py 422 如实计失败
        self.assertEqual(d["posted"], 1)
        self.assertEqual(d["failed"][0]["status"], 422)
        self.assertEqual(d["failed"][0]["path"], "b.py")
        self.assertEqual(len(_FakeHub.posted), 2)
        p0 = _FakeHub.posted[0]["payload"]
        self.assertEqual(p0["path"], "a.py")
        self.assertEqual(p0["line"], 3)
        self.assertEqual(p0["commit_id"], "abc123")
        self.assertTrue(_FakeHub.posted[0]["auth"].startswith("Bearer "),
                        "token 须以 Bearer 头发送")

    def test_dry_run_no_network(self):
        rc, out = self._invoke([
            "--repo", "o/r", "--pr", "7", "--comments", self.cp,
            "--commit-id", "abc", "--dry-run"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertTrue(d["dry_run"])
        self.assertEqual(d["posted"], 2)

    def test_missing_token_rc2(self):
        rc, out = self._invoke([
            "--repo", "o/r", "--pr", "7", "--comments", self.cp,
            "--commit-id", "abc"], env={})
        self.assertEqual(rc, 2)

    def test_bad_base_rc2(self):
        rc, out = self._invoke([
            "--repo", "o/r", "--pr", "7", "--comments", self.cp,
            "--base-url", "http://evil.example.com", "--dry-run"])
        self.assertEqual(rc, 2)

    def test_intranet_https_host_rejected(self):
        """https 内网/保留段默认拒绝（ipaddress 三判；口径对齐 provider）。"""
        mod = self.mod
        for base in ("https://10.1.2.3", "https://192.168.1.9",
                     "https://172.16.0.5", "https://169.254.3.4",
                     "https://127.0.0.1", "https://[::1]",
                     "https://gitea.internal", "https://gitea.local"):
            self.assertFalse(mod._allowed_base(base), base)
        # 反向对照（正常样例零误报）：公网域名与 http 回环不受影响
        self.assertTrue(mod._allowed_base("https://api.github.com"))
        self.assertTrue(mod._allowed_base("http://127.0.0.1:8123"))

    def test_allowlisted_intranet_host_allowed(self):
        """显式登记的内网 https host 放行；未登记仍拒、非 https 仍拒。"""
        mod = self.mod
        base = "https://gitea.lan.internal:8443"
        self.assertFalse(mod._allowed_base(base))
        old = mod.EXTRA_ALLOWED_HOSTS
        mod.EXTRA_ALLOWED_HOSTS = frozenset({"gitea.lan.internal"})
        try:
            self.assertTrue(mod._allowed_base(base))
        finally:
            mod.EXTRA_ALLOWED_HOSTS = old
        self.assertFalse(mod._allowed_base("http://gitea.lan.internal"),
                         "allowlist 仅作用于 https；非 https 仍回环白名单")

    def _invoke(self, argv, env=None):
        import os
        old = dict(os.environ)
        for k in list(os.environ):
            if k.startswith("GP_TEST"):
                del os.environ[k]
        os.environ.update(env or {})
        mod = _load()
        out = io.StringIO()
        try:
            sys.argv = ["github-poster.py"] + argv
            with contextlib.redirect_stdout(out):
                rc = mod.main()
        finally:
            sys.argv = old
            os.environ.clear()
            os.environ.update(old)
        return rc, out.getvalue()


if __name__ == "__main__":
    unittest.main()
