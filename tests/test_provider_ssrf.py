# -*- coding: utf-8 -*-
"""tests/test_provider_ssrf.py — llm/provider.py SSRF 加固契约（round-118）。

锁定四件事：
1. _endpoint_error：公网 https 放行、回环豁免、内网/保留段（含 IPv6 映射
   IPv4 漏网形态）拒绝、.internal/.local 域名拒绝、空 host 拒绝；
   resolve=True 时对域名做 DNS 解析逐 IP 复核（解析失败不误报）；
2. _SSRFRedirectHandler.redirect_request：302 跳内网/保留段抛 _SSRFRejected
   （不跟进），跳公网放行——逐跳复验堵住「公网 302 内网」绕过；
3. _read_capped：分块读取累计封顶，超限抛 ValueError 且立即止读；
4. _openai_complete：内网 BASE_URL 在联网前被白名单拦截（urlopen 不被调用）。

离线用例：DNS 解析一律打桩，不触网。
"""
import io
import json
import os
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import llm.provider as prov  # noqa: E402

_ENV_KEYS = ("REVIEW_LLM_BASE_URL", "REVIEW_LLM_MODEL",
             "REVIEW_LLM_API_KEY", "CRA_LLM_PROVIDER")


def _fake_getaddrinfo(ips):
    """构造 getaddrinfo 打桩：返回 (family, type, proto, canonname, sockaddr)。"""
    return [(2, 1, 6, "", (ip, 0)) for ip in ips]


class TestEndpointError(unittest.TestCase):
    """_endpoint_error：初连与重定向逐跳共用的白名单判定。"""

    def test_public_https_allowed(self):
        self.assertIsNone(prov._endpoint_error("https://api.example.com/v1"))
        self.assertIsNone(prov._endpoint_error("https://8.8.8.8/"))
        self.assertIsNone(prov._endpoint_error("https://172.32.0.1/"),
                          "172.32/12 不在保留段（仅 172.16-31）")

    def test_loopback_exempt(self):
        for url in ("http://localhost:8123/", "http://127.0.0.1:8123/",
                    "https://127.1.2.3/", "http://[::1]:8123/",
                    "https://localhost/"):
            self.assertIsNone(prov._endpoint_error(url), url)

    def test_non_https_public_rejected(self):
        err = prov._endpoint_error("http://api.example.com/")
        self.assertIsNotNone(err)
        self.assertIn("白名单拒绝", err)

    def test_private_ip_literal_rejected(self):
        for url in ("https://10.1.2.3/", "https://192.168.1.9/",
                    "https://172.16.0.5/", "https://172.31.255.255/",
                    "https://169.254.3.4/", "https://0.0.0.0/"):
            self.assertIsNotNone(prov._endpoint_error(url), url)

    def test_ipv6_mapped_ipv4_rejected(self):
        # IPv4 映射 IPv6（如 ::ffff:192.168.1.1）绕过字符串前缀匹配，
        # 必须由 ipaddress 字面量复核拦截。
        err = prov._endpoint_error("https://[::ffff:192.168.1.1]/")
        self.assertIsNotNone(err)
        self.assertIn("白名单拒绝", err)

    def test_internal_domain_suffix_rejected(self):
        for url in ("https://gitea.internal/", "https://nas.local/",
                    "https://GITEA.INTERNAL/"):
            self.assertIsNotNone(prov._endpoint_error(url), url)

    def test_empty_host_rejected(self):
        self.assertIsNotNone(prov._endpoint_error("https://"))

    def test_resolve_dns_private_rejected(self):
        orig = prov.socket.getaddrinfo
        prov.socket.getaddrinfo = lambda host, port: _fake_getaddrinfo(
            ["93.184.216.34", "10.9.9.9"])
        try:
            err = prov._endpoint_error("https://evil.example.com/", resolve=True)
        finally:
            prov.socket.getaddrinfo = orig
        self.assertIsNotNone(err)
        self.assertIn("白名单拒绝", err)

    def test_resolve_dns_public_allowed(self):
        orig = prov.socket.getaddrinfo
        prov.socket.getaddrinfo = lambda host, port: _fake_getaddrinfo(
            ["93.184.216.34"])
        try:
            err = prov._endpoint_error("https://api.example.com/", resolve=True)
        finally:
            prov.socket.getaddrinfo = orig
        self.assertIsNone(err)

    def test_resolve_dns_failure_not_false_positive(self):
        orig = prov.socket.getaddrinfo

        def boom(host, port):
            raise OSError("name resolution failed")

        prov.socket.getaddrinfo = boom
        try:
            err = prov._endpoint_error("https://gone.example.com/", resolve=True)
        finally:
            prov.socket.getaddrinfo = orig
        self.assertIsNone(err, "DNS 解析失败交由真实请求自然失败，不误报 SSRF")

    def test_resolve_scoped_ipv6_link_local_rejected(self):
        orig = prov.socket.getaddrinfo
        prov.socket.getaddrinfo = lambda host, port: _fake_getaddrinfo(
            ["fe80::1%eth0"])
        try:
            err = prov._endpoint_error("https://v6.example.com/", resolve=True)
        finally:
            prov.socket.getaddrinfo = orig
        self.assertIsNotNone(err)


class TestSSRFRedirectHandler(unittest.TestCase):
    """重定向逐跳复验：违规跳转抛 _SSRFRejected，公网跳转放行。"""

    def _req(self, url):
        return urllib.request.Request(url, data=b"{}")

    def test_redirect_to_private_ip_rejected(self):
        handler = prov._SSRFRedirectHandler()
        with self.assertRaises(prov._SSRFRejected):
            handler.redirect_request(
                self._req("https://api.example.com/"), None,
                302, "Found", {"Location": "https://169.254.169.254/latest"},
                "https://169.254.169.254/latest")

    def test_redirect_to_internal_suffix_rejected(self):
        handler = prov._SSRFRedirectHandler()
        with self.assertRaises(prov._SSRFRejected):
            handler.redirect_request(
                self._req("https://api.example.com/"), None,
                302, "Found", {}, "https://metadata.internal/")

    def test_redirect_to_public_https_allowed(self):
        handler = prov._SSRFRedirectHandler()
        req = handler.redirect_request(
            self._req("https://api.example.com/a"), None,
            301, "Moved", {}, "https://cdn.example.com/b")
        self.assertIsNotNone(req)

    def test_ensure_ssrf_opener_idempotent(self):
        prov._ensure_ssrf_opener()
        prov._ensure_ssrf_opener()
        self.assertTrue(prov._SSRF_OPENER_INSTALLED)


class _CountingReader(io.BytesIO):
    """记录 read 调用次数的响应体替身。"""

    def __init__(self, blob):
        super().__init__(blob)
        self.reads = 0

    def read(self, n=-1):
        self.reads += 1
        return super().read(n)


class TestReadCapped(unittest.TestCase):
    """分块读取封顶：超限抛 ValueError 且立即止读。"""

    def test_normal_read_joins_chunks(self):
        r = _CountingReader(b"hello world")
        self.assertEqual(prov._read_capped(r, 1024), b"hello world")

    def test_empty_body(self):
        self.assertEqual(prov._read_capped(_CountingReader(b""), 1024), b"")

    def test_over_cap_raises_and_stops_early(self):
        reader = _CountingReader(b"x" * (10 * 1024))
        with self.assertRaises(ValueError):
            prov._read_capped(reader, 1024)
        self.assertEqual(reader.reads, 1,
                         "超限首块即止读，不再吞后续字节")


class TestOpenAICompleteEndpointGate(unittest.TestCase):
    """_openai_complete：内网 BASE_URL 在联网前被拦截，urlopen 不被调用。"""

    def setUp(self):
        self._backup = {k: os.environ.get(k) for k in _ENV_KEYS}
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        os.environ["REVIEW_LLM_MODEL"] = "test-model"

    def tearDown(self):
        for k, v in self._backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_internal_base_url_rejected_before_network(self):
        os.environ["REVIEW_LLM_BASE_URL"] = "https://10.1.2.3"
        called = []

        def fake_urlopen(req, timeout=None):
            called.append(req)
            raise AssertionError("内网端点不得发起请求")

        orig = prov.urllib.request.urlopen
        prov.urllib.request.urlopen = fake_urlopen
        self.addCleanup(setattr, prov.urllib.request, "urlopen", orig)
        text, meta = prov._openai_complete("s", "u", {}, None)
        self.assertIsNone(text)
        self.assertIn("白名单拒绝", meta["error"])
        self.assertEqual(called, [])

    def test_public_base_url_passes_gate(self):
        os.environ["REVIEW_LLM_BASE_URL"] = "https://api.example.com"
        payload = (b'{"choices":[{"message":{"content":"ok"}}],'
                   b'"usage":{"total_tokens":3}}')

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()
                return False

        def fake_urlopen(req, timeout=None):
            return _Resp(payload)

        orig = prov.urllib.request.urlopen
        prov.urllib.request.urlopen = fake_urlopen
        self.addCleanup(setattr, prov.urllib.request, "urlopen", orig)
        text, meta = prov._openai_complete("s", "u", {}, None)
        self.assertEqual(text, "ok")
        self.assertEqual(meta["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
