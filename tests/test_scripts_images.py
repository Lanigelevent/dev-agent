# -*- coding: utf-8 -*-
"""tests/test_scripts_images.py — 镜像与取数：TestMirrorProbe / TestImageFetch（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestMirrorProbe(unittest.TestCase):
    """docker-mirror-probe.py 离线反向验证（stub registry，零网络）。"""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "mirror_probe", ROOT / "scripts" / "docker-mirror-probe.py")
        cls.mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mp)

    class _Resp:
        def __init__(self, data, delay=0.0):
            self._data, self._pos, self._delay = data, 0, delay
            self.headers = {}

        def read(self, n=-1):
            if self._delay:
                import time as _t
                _t.sleep(self._delay)
            if n is None or n < 0:
                n = len(self._data) - self._pos
            chunk = self._data[self._pos:self._pos + n]
            self._pos += len(chunk)
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Opener:
        """按 URL 形态路由的假 opener（v2 认证→token→manifest→blob）。"""

        def __init__(self, blob_bytes=8 * 1048576, chunk_delay=0.0,
                     manifest_error=False, auth_realm=True):
            self.blob_bytes, self.chunk_delay = blob_bytes, chunk_delay
            self.manifest_error, self.auth_realm = manifest_error, auth_realm
            self.seen = []

        def open(self, req, timeout=None):
            url = getattr(req, "full_url", str(req))
            self.seen.append(url)
            if url.endswith("/v2/"):
                if not self.auth_realm:
                    raise urllib.error.HTTPError(url, 401, "No", {}, None)
                raise urllib.error.HTTPError(url, 401, "Unauthorized", {
                    "WWW-Authenticate": 'Bearer realm="https://stub.test/token",'
                                        ' service="stub.test", scope="r:p"'},
                    None)
            if "/token" in url:
                return TestMirrorProbe._Resp(b'{"token": "t0k"}')
            if "/manifests/" in url:
                if self.manifest_error:
                    raise urllib.error.HTTPError(url, 404, "No such", {}, None)
                manifest = {"schemaVersion": 2, "layers": [
                    {"digest": "sha256:" + "0" * 60,
                     "size": self.blob_bytes}]}
                return TestMirrorProbe._Resp(json.dumps(manifest).encode())
            if "/blobs/" in url:
                return TestMirrorProbe._Resp(
                    b"\x01" * self.blob_bytes, delay=self.chunk_delay)
            raise AssertionError("stub 不认识的 URL: " + url)

    def test_usable_fast_blob(self):
        r = self.mp.probe_mirror("stub.test", "demo/img", 5.0, 100.0,
                                 opener=self._Opener(),
                                 check_host=lambda m: None)
        self.assertEqual(r["status"], "usable", r)
        self.assertEqual(r["phase"], "blob")
        self.assertGreater(r["kbps"], 0)

    def test_tag_reaches_manifest_url(self):
        """按实例打 tag 的仓库（Pro）测速必须打到指定 tag，不能永远是 latest。"""
        op = self._Opener()
        r = self.mp.probe_mirror("stub.test", "demo/img", 5.0, 100.0,
                                 opener=op, check_host=lambda m: None,
                                 tag="instance_abc")
        self.assertEqual(r["status"], "usable", r)
        self.assertTrue(any(url.endswith("/manifests/instance_abc")
                            for url in op.seen), op.seen)

    def test_slow_blob_judged_dead(self):
        # 每块 64KB 延时 0.5s → 2s 内只读 4 块 ≈ 128KB/s 阈值 500 → slow
        r = self.mp.probe_mirror("stub.test", "demo/img", 2.0, 500.0,
                                 opener=self._Opener(chunk_delay=0.5),
                                 check_host=lambda m: None)
        self.assertEqual(r["status"], "slow", r)
        self.assertEqual(r["phase"], "blob")

    def test_manifest_fail_phase(self):
        r = self.mp.probe_mirror("stub.test", "demo/img", 5.0, 100.0,
                                 opener=self._Opener(manifest_error=True),
                                 check_host=lambda m: None)
        self.assertEqual(r["status"], "unusable")
        self.assertEqual(r["phase"], "manifest")

    def test_no_auth_realm_fails_at_token(self):
        r = self.mp.probe_mirror("stub.test", "demo/img", 5.0, 100.0,
                                 opener=self._Opener(auth_realm=False),
                                 check_host=lambda m: None)
        self.assertEqual(r["status"], "unusable")
        self.assertEqual(r["phase"], "token")

    def test_ssrf_guard_rejects_loopback_and_badname(self):
        for mirror in ("localhost", "bad name!", "127.0.0.1"):
            with self.assertRaises(ValueError):
                self.mp._check_mirror_host(mirror)


class TestImageFetch(unittest.TestCase):
    """docker-image-fetch.py 离线反向验证（本地 stub registry，真 HTTP 流）。"""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "image_fetch", ROOT / "scripts" / "docker-image-fetch.py")
        cls.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.m)
        # 存类属性必须包 staticmethod，否则经 self. 访问会被绑定成方法
        cls.m_check_real = staticmethod(cls.m.check_mirror_host)
        cls.m.check_mirror_host = lambda host: None  # 本地回环 stub 放行
        cls.m.BASE_SCHEME = "http"  # stub registry 是明文 http

    def _start_registry(self, blob_overrides=None, redirect_port=None):
        """起本地 stub registry；返回 (server, port, digests)。"""
        import hashlib
        import http.server
        import threading
        layer_payload = b"LAYERDATA" * 1024  # 9KB
        layer_digest = "sha256:" + hashlib.sha256(layer_payload).hexdigest()
        config_payload = json.dumps({"os": "linux"}).encode()
        config_digest = "sha256:" + hashlib.sha256(config_payload).hexdigest()
        manifest = {"schemaVersion": 2,
                    "mediaType": "application/vnd.docker.distribution."
                                 "manifest.v2+json",
                    "config": {"mediaType": "application/vnd.docker.container."
                                             "image.v1+json",
                               "digest": config_digest,
                               "size": len(config_payload)},
                    "layers": [{"mediaType": "application/vnd.docker.image."
                                             "rootfs.diff.tar.gzip",
                                "digest": layer_digest,
                                "size": len(layer_payload)}]}
        manifest_bytes = json.dumps(manifest).encode()
        manifest_digest = "sha256:" + hashlib.sha256(manifest_bytes).hexdigest()
        list_payload = json.dumps({"schemaVersion": 2, "manifests": [
            {"mediaType": manifest["mediaType"], "digest": manifest_digest,
             "size": len(manifest_bytes),
             "platform": {"architecture": "amd64", "os": "linux"}},
            {"mediaType": manifest["mediaType"], "digest": manifest_digest,
             "size": len(manifest_bytes),
             "platform": {"architecture": "arm64", "os": "linux"}}]}).encode()
        blobs = {config_digest: config_payload, layer_digest: layer_payload,
                 manifest_digest: manifest_bytes}
        if blob_overrides:
            blobs.update(blob_overrides)

        class Handler(http.server.BaseHTTPRequestHandler):
            def _send(self, code, body, headers=None):
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.server.seen.append(self.path)
                if self.path == "/v2/":
                    self._send(401, b"auth required", {
                        "WWW-Authenticate": 'Bearer realm="http://127.0.0.1:'
                                            '%d/token", service="stub"' % self.server.server_address[1]})
                elif self.path.startswith("/token"):
                    self._send(200, b'{"token": "t0k"}')
                elif self.path.endswith("/manifests/latest"):
                    self._send(200, list_payload, {"Content-Type":
                                                   "application/vnd.docker."
                                                   "distribution.manifest."
                                                   "list.v2+json"})
                elif "/manifests/" in self.path:
                    self._send(200, manifest_bytes)
                elif "/blobs/" in self.path and redirect_port:
                    host = "localhost" if self.headers.get("Host", "").startswith("127.0.0.1") else "127.0.0.1"
                    loc = "http://%s:%d/real%s" % (host, redirect_port, self.path)
                    self._send(307, b"", {"Location": loc})
                else:
                    dg = self.path.rsplit("/", 1)[-1]  # 末段即完整 digest
                    body = blobs.get(dg)
                    if body is None:
                        self._send(404, b"no blob")
                        return
                    rng = self.headers.get("Range", "")
                    if rng.startswith("bytes="):
                        a, b = rng[6:].split("-", 1)
                        start = int(a)
                        end = int(b) if b else len(body) - 1
                        self._send(206, body[start:end + 1],
                                   {"Content-Range": "bytes %d-%d/%d"
                                    % (start, end, len(body))})
                    else:
                        self._send(200, body)

            def log_message(self, *a):  # 静音
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.seen = []
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server, server.server_address[1], {"layer": layer_digest,
                                                  "config": config_digest,
                                                  "manifest": manifest_digest}

    def test_plan_uses_explicit_tag(self):
        """Pro 按实例打 tag：plan 必须请求 /manifests/<tag>，不能写死 latest。"""
        server, port, _ = self._start_registry()
        try:
            out = Path(self.tmpdir) / "cache"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img:inst-7",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertTrue(any(path.endswith("/manifests/inst-7")
                                for path in server.seen), server.seen)
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["image"], "demo/img:inst-7")
        finally:
            server.shutdown()

    def test_plan_selects_amd64(self):
        server, port, digests = self._start_registry()
        try:
            out = Path(self.tmpdir) / "cache"
            # 带 tag 的镜像（回归锁定：tag 不得进 manifest 路径，否则 404）
            rc, data, _, _ = self._run(["plan", "--image", "demo/img:latest",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertEqual(data["layers"], 1)
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["config_digest"], digests["config"])
            self.assertEqual(plan["manifest_digest"], digests["manifest"])
            self.assertEqual(plan["image"], "demo/img:latest")
        finally:
            server.shutdown()

    def test_fetch_resume_and_full_rerun(self):
        server, port, digests = self._start_registry()
        try:
            out = Path(self.tmpdir) / "cache"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            hexl = digests["layer"].split(":")[1]
            # 预置半个 .part 模拟中断续传
            bdir = out / "blobs" / "sha256"
            bdir.mkdir(parents=True)
            half = b"LAYERDATA" * 512
            (bdir / (hexl + ".part")).write_bytes(half)
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out)])
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertTrue(data["resumed"] >= 1, "应命中续传")
            body = (bdir / hexl).read_bytes()
            self.assertEqual(len(body), 9 * 1024)
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(all(not r["resumed"] for r in data["results"]),
                            "二次全量应全 skip")
        finally:
            server.shutdown()

    def test_fetch_redirect_strips_auth(self):
        # B 先起（真实 blob 源），A 起为 307 → B 的重定向门（跨主机名剥 Auth）
        server_b, port_b, _ = self._start_registry()
        server_a, port_a, digests = self._start_registry(redirect_port=port_b)
        try:
            # 收窄放行：测试用 http 回环重定向（真实 https 校验由守卫测试覆盖），
            # redirect_request 本体（含剥 Auth）不动
            class _LoopbackRedirect(self.m._RedirectDropAuth):
                def _validate_target(self, newurl):
                    return urllib.parse.urlparse(newurl)

            real_make = self.m.make_opener
            self.m.make_opener = lambda: urllib.request.build_opener(
                _LoopbackRedirect())
            try:
                out = Path(self.tmpdir) / "cache-r"
                rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                            "--mirror",
                                            f"127.0.0.1:{port_a}",
                                            "--out", str(out)])
                self.assertEqual(rc, 0)
                rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                            "--mirror",
                                            f"127.0.0.1:{port_a}",
                                            "--plan", str(out / "plan.json"),
                                            "--out", str(out)])
                self.assertEqual(rc, 0, str(data)[:300])
                hexl = digests["layer"].split(":")[1]
                body = (out / "blobs" / "sha256" / hexl).read_bytes()
                self.assertEqual(body, b"LAYERDATA" * 1024,
                                 "跨主机重定向剥离 Auth 后应取到 blob")
            finally:
                self.m.make_opener = real_make
        finally:
            server_a.shutdown()
            server_b.shutdown()

    def test_fetch_digest_mismatch_fails(self):
        import hashlib as _h
        bad = b"CORRUPT" * 512
        bad_digest = "sha256:" + _h.sha256(b"NOT-THE-SAME").hexdigest()
        server, port, _ = self._start_registry(
            blob_overrides={bad_digest: bad})
        try:
            out = Path(self.tmpdir) / "cache-bad"
            rc, _, _, _ = self._run(["plan", "--image", "demo/img",
                                     "--mirror", f"127.0.0.1:{port}",
                                     "--out", str(out)])
            self.assertEqual(rc, 0)
            # 把 plan 的 layer digest 换成坏 blob（内容 sha ≠ digest）
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            plan["layers"][0]["digest"] = bad_digest
            (out / "plan.json").write_text(json.dumps(plan),
                                           encoding="utf-8")
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out),
                                        "--retries", "0"])
            self.assertEqual(rc, 1)
            self.assertIn(data.get("state"),
                          ("DIGEST_MISMATCH", "FETCH_ERROR"))
        finally:
            server.shutdown()

    def test_fetch_retries_after_reset(self):
        """blob 首次硬断连 → 重试续传成功（红线 6：重试闸要能从失败转真）。"""
        server, port, _ = self._start_registry()
        fails = {"n": 1}

        # 在 stub 的 blob 路由上做一次性断连
        orig_handler = server.RequestHandlerClass
        outer = self

        class FlakyHandler(orig_handler):
            def do_GET(self):
                if "/blobs/" in self.path and fails["n"] > 0:
                    fails["n"] -= 1
                    self.close_connection = True
                    try:
                        self.wfile.close()
                    except OSError:
                        pass
                    return
                orig_handler.do_GET(self)

        server.RequestHandlerClass = FlakyHandler
        try:
            out = Path(self.tmpdir) / "cache-retry"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out),
                                        "--retries", "3"])
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertEqual(data["blobs"], 3)  # config + layer + manifest
        finally:
            server.shutdown()

    def test_assemble_oci_layout(self):
        server, port, digests = self._start_registry()
        try:
            out = Path(self.tmpdir) / "cache-a"
            for phase in ("plan", "fetch"):
                rc, data, _, _ = self._run([phase, "--image", "demo/img",
                                            "--mirror", f"127.0.0.1:{port}",
                                            "--out", str(out)] if phase == "plan"
                    else ["fetch", "--image", "demo/img",
                          "--mirror", f"127.0.0.1:{port}",
                          "--plan", str(out / "plan.json"), "--out", str(out)])
                self.assertEqual(rc, 0, str(data)[:200])
            tar_path = Path(self.tmpdir) / "img.tar"
            rc, data, _, _ = self._run(["assemble", "--plan",
                                        str(out / "plan.json"),
                                        "--blobs", str(out),
                                        "--out", str(tar_path),
                                        "--image", "demo/img:latest"])
            self.assertEqual(rc, 0, str(data)[:300])
            import tarfile as _tf
            with _tf.open(tar_path) as tar:
                names = set(tar.getnames())
            self.assertIn("oci-layout", names)
            self.assertIn("index.json", names)
            self.assertTrue(any("blobs/sha256/" in n for n in names))
            index = json.loads(_tf.open(tar_path).extractfile(
                "index.json").read().decode("utf-8"))
            self.assertEqual(index["manifests"][0]["annotations"][
                "org.opencontainers.image.ref.name"], "demo/img:latest")
        finally:
            server.shutdown()

    def test_fetch_parallel_segments_and_resume(self):
        """并行 Range 分段：注入断连 → seg 持久化 → 重试续传 → 重组 sha 通过。"""
        import hashlib as _h
        old_segmin = self.m.SEG_MIN
        self.m.SEG_MIN = 2048
        self.addCleanup(setattr, self.m, "SEG_MIN", old_segmin)
        payload = b"PARALLEL-DATA-" * 1500  # 21KB
        digest = "sha256:" + _h.sha256(payload).hexdigest()
        server, port, _ = self._start_registry(
            blob_overrides={digest: payload})
        fails = {"n": 2}  # 前两个非零起点的分段请求硬断连
        orig_handler = server.RequestHandlerClass

        class FlakyRange(orig_handler):
            def do_GET(self):
                if "/blobs/" in self.path:
                    rng = self.headers.get("Range", "")
                    if rng and not rng.startswith("bytes=0-") \
                            and fails["n"] > 0:
                        fails["n"] -= 1
                        self.close_connection = True
                        try:
                            self.wfile.close()
                        except OSError:
                            pass
                        return
                orig_handler.do_GET(self)

        server.RequestHandlerClass = FlakyRange
        try:
            out = Path(self.tmpdir) / "cache-par"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            plan["layers"] = [{"digest": digest, "size": len(payload)}]
            (out / "plan.json").write_text(json.dumps(plan),
                                           encoding="utf-8")
            fetch_args = ["fetch", "--image", "demo/img",
                          "--mirror", f"127.0.0.1:{port}",
                          "--plan", str(out / "plan.json"),
                          "--out", str(out)]
            rc, data, _, _ = self._run(fetch_args + ["--retries", "0",
                                                     "--segments", "4"])
            self.assertEqual(rc, 1, "注入断连应失败")
            rc, data, _, _ = self._run(fetch_args + ["--retries", "3",
                                                     "--segments", "4"])
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertTrue(data["resumed"] >= 1, "seg 持久化应命中续传")
            hexl = digest.split(":")[1]
            final = out / "blobs" / "sha256" / hexl
            self.assertEqual(final.read_bytes(), payload, "重组须逐字节一致")
            self.assertEqual(list(out.glob("blobs/sha256/*.seg*")), [],
                             "seg 文件应清理")
        finally:
            server.shutdown()

    def test_fetch_work_files_are_process_unique(self):
        """工作文件按进程命名：并发会话各写各的（round-28 纪律 8 的正式修法）。

        背景（round-23 起就在检查单上）：两个会话并行拉同一镜像时共用
        blobs/sha256/<hex>.part，Windows 上 os.replace 撞 WinError 32，
        POSIX 上交叉写入污染。名字里带进程令牌后，共享只剩「成品名」，
        而成品是 os.replace 原子产出且内容寻址，撞不上。
        """
        import hashlib as _h
        old_segmin = self.m.SEG_MIN
        self.m.SEG_MIN = 2048  # 压到 KB 级，让并行分段路径真被走到
        self.addCleanup(setattr, self.m, "SEG_MIN", old_segmin)
        payload = b"UNIQUE-DATA-" * 2100  # 21KB
        digest = "sha256:" + _h.sha256(payload).hexdigest()
        server, port, _ = self._start_registry(
            blob_overrides={digest: payload})
        real_serial = self.m._fetch_serial
        real_span = self.m._dl_span
        seen = []

        def spy_serial(opener, base, repo_path, dg, hex_part, final, part,
                       token):
            seen.append(part.name)
            return real_serial(opener, base, repo_path, dg, hex_part, final,
                               part, token)

        def spy_span(opener, base, repo_path, dg, token, path, start, end):
            seen.append(path.name)
            return real_span(opener, base, repo_path, dg, token, path,
                             start, end)

        self.m._fetch_serial = spy_serial
        self.m._dl_span = spy_span
        self.addCleanup(setattr, self.m, "_fetch_serial", real_serial)
        self.addCleanup(setattr, self.m, "_dl_span", real_span)
        try:
            out = Path(self.tmpdir) / "cache-uid"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            plan["layers"] = [{"digest": digest, "size": len(payload)}]
            (out / "plan.json").write_text(json.dumps(plan),
                                           encoding="utf-8")
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out),
                                        "--segments", "4"])
            self.assertEqual(rc, 0, str(data)[:300])
            uid = self.m._uid()
            self.assertTrue(seen, "两个下载原语都应被记录到")
            self.assertTrue(all(n.endswith(uid) for n in seen),
                            "工作文件必须带本进程令牌: %s" % sorted(set(seen)))
            self.assertTrue(any(".seg" in n for n in seen),
                            "并行分段命名路径应被覆盖")
            # 反向验证：旧语义的共享名一个都不许出现（出现了就等于没修）
            legacy = re.compile(r"^[0-9a-f]{64}\.(part|assembling|seg\d+)$")
            self.assertFalse([n for n in seen if legacy.match(n)],
                             "仍在用共享工作文件名: %s" % sorted(set(seen)))
            bdir = out / "blobs" / "sha256"
            self.assertEqual((bdir / digest.split(":")[1]).read_bytes(),
                             payload)
            self.assertEqual([p.name for p in bdir.glob("*.*")], [],
                             "成功后不应留任何工作文件")
        finally:
            server.shutdown()

    def test_prior_progress_is_claimed_by_rename(self):
        """中断进度靠「改名认领」回收，而不是两个进程共用同一份半成品。"""
        bdir = Path(self.tmpdir)
        hexl = "b" * 64
        legacy = bdir / (hexl + ".part")
        legacy.write_bytes(b"X" * 4096)
        self.assertEqual(self.m._claim_prior(bdir, hexl, "part"), 4096)
        self.assertFalse(legacy.is_file(), "认领必须是改名，原共享名不得留下")
        mine = self.m.work_path(bdir, hexl, "part")
        self.assertEqual(mine.read_bytes(), b"X" * 4096, "进度字节要搬过来")
        # 反向验证：再认领一次走「本进程已有」分支（不是每次改名/清零）
        self.assertEqual(self.m._claim_prior(bdir, hexl, "part"), 4096)
        self.assertEqual(mine.read_bytes(), b"X" * 4096)
        # 别的角色不受影响：seg 与 part 各认各的
        self.assertEqual(self.m._claim_prior(bdir, hexl, "seg1"), 0)

    def test_discard_work_spares_peers_and_final(self):
        """sha 失配的清理只删自己的半成品（对端的和成品名一律不碰）。"""
        bdir = Path(self.tmpdir)
        hexl = "c" * 64
        mine = bdir / ("%s.part.p%d" % (hexl, os.getpid()))
        peer = bdir / ("%s.seg1.p%d" % (hexl, os.getpid() + 1))
        final = bdir / hexl
        reused = bdir / ("%s.assembling.p%d" % (hexl, os.getpid()))
        legacy = bdir / (hexl + ".part")
        for p in (mine, peer, final, reused, legacy):
            p.write_bytes(b"z")
        # PID 复用：同名但写于本进程启动之前 → 不算自己的
        os.utime(reused, (1, 1))
        self.assertEqual(self.m.discard_work(bdir, hexl), [mine.name])
        for p in (peer, final, reused, legacy):
            self.assertTrue(p.is_file(), "%s 不该被本进程删" % p.name)
        self.assertEqual(self.m._work_owner(reused, hexl, "assembling"),
                         "foreign")
        self.assertEqual(self.m._role_of("x" * 64 + ".seg12.p5", "x" * 64),
                         "seg12")
        self.assertEqual(self.m._role_of("x" * 64 + ".part", "x" * 64), "part")
        self.assertIsNone(self.m._role_of("x" * 64, "x" * 64),
                          "成品名不是工作文件")

    def test_fetch_serial_fallback_on_200(self):
        """服务端忽略 Range（200）→ 回退单流，sha 仍须通过。"""
        import hashlib as _h
        payload = b"FALLBACK" * 4096  # 32KB
        digest = "sha256:" + _h.sha256(payload).hexdigest()
        server, port, _ = self._start_registry(
            blob_overrides={digest: payload})
        # 让 stub 对该 blob 忽略 Range（去掉 206 分支）：包装 handler
        orig_handler = server.RequestHandlerClass

        class _NoRangeHandler(orig_handler):
            def do_GET(self):
                if "/blobs/" in self.path:
                    dg = self.path.rsplit("/", 1)[-1]
                    body = self._blobs.get(dg) if hasattr(
                        self, "_blobs") else None
                    if body is not None:
                        self.send_response(200)
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        return
                orig_handler.do_GET(self)

        _NoRangeHandler._blobs = {digest: payload}
        server.RequestHandlerClass = _NoRangeHandler
        try:
            out = Path(self.tmpdir) / "cache-fb"
            rc, data, _, _ = self._run(["plan", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--out", str(out)])
            self.assertEqual(rc, 0)
            plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            plan["layers"] = [{"digest": digest, "size": len(payload)}]
            (out / "plan.json").write_text(json.dumps(plan),
                                           encoding="utf-8")
            rc, data, _, _ = self._run(["fetch", "--image", "demo/img",
                                        "--mirror", f"127.0.0.1:{port}",
                                        "--plan", str(out / "plan.json"),
                                        "--out", str(out)])
            self.assertEqual(rc, 0, str(data)[:300])
            hexl = digest.split(":")[1]
            self.assertEqual(
                (out / "blobs" / "sha256" / hexl).read_bytes(), payload)
        finally:
            server.shutdown()

    def test_load_docker_gate(self):
        rc, data, _, _ = self._run(["load", "--archive", "Z:/no.tar",
                                    "--docker", "Z:/no/docker.exe"])
        self.assertEqual(rc, 2, "归档不存在应判参数错误")
        Path(self.tmpdir, "empty.tar").write_bytes(b"")
        rc, data, _, _ = self._run(["load", "--archive",
                                    str(Path(self.tmpdir, "empty.tar")),
                                    "--docker", "Z:/no/docker.exe"])
        self.assertEqual(rc, 1)
        self.assertEqual(data.get("state"), "DOCKER_UNAVAILABLE")

    def test_ssrf_guard_cross_check_with_mirror_probe(self):
        """机械交叉比对（唯一权威源原则）：两份 SSRF 守卫行为一致。"""
        spec = importlib.util.spec_from_file_location(
            "mirror_probe_x", ROOT / "scripts" / "docker-mirror-probe.py")
        mp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mp)
        for host in ("localhost", "127.0.0.1", "10.0.0.1", "bad name!"):
            for guard in (self.m_check_real, mp._check_mirror_host):
                raised = False
                try:
                    guard(host)
                except ValueError:
                    raised = True
                self.assertTrue(raised, "%s 未拒绝 %r" % (guard, host))
        for guard in (self.m_check_real, mp._check_mirror_host):
            try:
                guard("docker.1ms.run")
            except ValueError:
                self.fail("合法域名被误拒")

    def _run(self, args):
        """进程内走真实 main()（argparse/dest/异常映射全真）；返回 (rc, json, out, err)。"""
        import contextlib
        import io
        old_argv = sys.argv
        sys.argv = ["docker-image-fetch.py"] + list(args)
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = self.m.main()
        finally:
            sys.argv = old_argv
        text = buf.getvalue()
        try:
            return rc, json.loads(text), text, ""
        except ValueError:
            return rc, None, text, ""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


