#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Docker 镜像 curl 式逐层下载器（绕开 docker 客户端在慢 CDN 下的假启动路径）。

背景（台账 round-8/10）：docker pull 对 307→CDN 的慢速 blob 会无限挂起
（假启动），而 curl 分段请求可正常流动。本工具按镜像源判定纪律（硬约束 8）
分四阶段拉取：plan（token+manifest 解析，选 amd64）→ fetch（逐 blob 断点
续传，sha256 强制验证）→ assemble（组装 OCI image layout tar）→
load（docker load 入库并打 tag）。纯标准库。

用法示例:
    py docker-image-fetch.py plan --image swebench/sweb.eval...:latest \
        --mirror docker.1ms.run --out datasets/imagecache
    py docker-image-fetch.py fetch --image <同上> --mirror <同上> \
        --plan datasets/imagecache/plan.json --out datasets/imagecache
    py docker-image-fetch.py assemble --plan datasets/imagecache/plan.json \
        --blobs datasets/imagecache --out datasets/imagecache/django-11039.tar
    py docker-image-fetch.py load --archive datasets/imagecache/django-11039.tar

退出码:
    0 = 成功；1 = 可处理问题（blob 不可达 / sha256 失配 / docker 缺席）；
    2 = 参数或输入错误。

断点续传语义：blob 的下载中间名按进程隔离（blobs/sha256/<hex>.part.p<pid>
与 <hex>.seg<i>.p<pid>），同一缓存目录允许多个会话并行拉同一镜像而不互踩
（round-23 起 WinError 32 的正式修法）；成品仍是内容寻址的 <hex>，由
os.replace 原子产出。同进程重跑从自己的中间名现长起 Range 续传；跨进程
的历史进度按认领规则回收（旧版无 PID 的 .part、以及「无人持有」的他人半成品才
认领，活跃并发会话的文件留给对方，改名撞占用即放弃认领）；服务端忽略
Range 返 200 时丢弃重下。完成后 sha256
校验（registry digest 即内容 sha256），通过才去掉中间名。跨主机重定向
（307 → CDN）自动剥离 Authorization（curl 同款安全语义）。
"""
import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_SCHEME = "https"  # 测试可注入 http（stub registry）
BLOB_TIMEOUT = 120  # blob 流读超时（慢链路 10KB/s 级：64KB 块 6.4s 内必到）
SEG_MIN = 1 << 20  # 并行分段最小跨度（小于 2×此值走单流）
# CDN/WAF 对 Python-urllib UA 有 bot 403 过滤（v1.22.0 实测），需带常规 UA
DEFAULT_UA = "dev-agent-image-fetch/1.22.0"
TIMEOUT = 30
CHUNK = 1 << 16
MANIFEST_ACCEPT = ("application/vnd.docker.distribution.manifest.list.v2+json,"
                   "application/vnd.oci.image.index.v1+json,"
                   "application/vnd.docker.distribution.manifest.v2+json,"
                   "application/vnd.oci.image.manifest.v1+json")
IPV6_BRACKET_RE = re.compile(r"^\[(.+)\]$")
PROC_START = time.time()  # 本进程起点，用于识破 PID 复用
UID_RE = re.compile(r"^p(\d+)$")  # 工作文件尾缀：<hex>.<role>.p<pid>


def split_image(name):
    """owner/repo[:tag] -> (repo 路径, tag)；API 路径不含 tag。"""
    if ":" in name:
        repo, tag = name.rsplit(":", 1)
        return repo, tag
    return name, "latest"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fail(state, error, **extra):
    _emit(dict({"ok": False, "state": state, "error": error}, **extra))
    return 1


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def check_mirror_host(mirror):
    """SSRF 边界：域名白名单形态 + 解析 IP 禁私网/环回/链路本地/保留。"""
    if not re.match(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", mirror or ""):
        raise ValueError("镜像源域名形态非法: %r" % mirror)
    import ipaddress
    import socket
    for info in socket.getaddrinfo(mirror, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local \
                or ip.is_reserved or ip.is_multicast:
            raise ValueError("镜像源解析到受限地址 %s" % ip)


class _RedirectDropAuth(urllib.request.HTTPRedirectHandler):
    """跟随重定向；跨主机时剥离 Authorization（CDN 签名 URL 的安全语义）。"""

    def _validate_target(self, newurl):
        """校验重定向目标：仅 https + SSRF 边界（测试子类可收窄放行）。"""
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https":
            raise ValueError("重定向到非 https: %s" % newurl[:80])
        check_mirror_host(parsed.hostname or "")
        return parsed

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = self._validate_target(newurl)
        old = urllib.parse.urlparse(req.full_url)
        if (parsed.hostname or "") != (old.hostname or ""):
            req.headers.pop("Authorization", None)
            req.unredirected_hdrs.pop("Authorization", None)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener():
    return urllib.request.build_opener(_RedirectDropAuth())


def http_get(opener, url, headers=None, timeout=TIMEOUT):
    merged = {"User-Agent": DEFAULT_UA}
    merged.update(headers or {})
    req = urllib.request.Request(url, headers=merged)
    with opener.open(req, timeout=timeout) as resp:
        return resp.status, resp.headers, resp.read()


def get_token(opener, mirror, image):
    """匿名 Bearer 流程：按 WWW-Authenticate 的 realm 指引取 token。"""
    try:
        http_get(opener, "%s://%s/v2/" % (BASE_SCHEME, mirror))
        return None
    except urllib.error.HTTPError as exc:
        auth = exc.headers.get("WWW-Authenticate", "")
    m = re.search(r'realm="([^"]+)"', auth)
    if not m:
        raise ValueError("无可解析的认证 realm: %s" % auth[:80])
    params = {"service": mirror, "scope": "repository:%s:pull" % image}
    _, _, body = http_get(opener, m.group(1) + "?" + urllib.parse.urlencode(params))
    data = json.loads(body.decode("utf-8"))
    return data.get("token") or data.get("access_token")


def resolve_amd64_manifest(opener, base, image, token, tag="latest"):
    """manifest list/index 取 amd64 子 manifest；返回 (manifest dict, digest)。

    tag 必须来自 --image 的 tag 段：Pro 系列镜像按实例打 tag，写死 latest
    会 404（round-50 实踩：测速可达而 plan 失败）。
    """
    headers = {"Accept": MANIFEST_ACCEPT}
    if token:
        headers["Authorization"] = "Bearer " + token
    status, _, body = http_get(opener, base + image + "/manifests/" + tag,
                               headers=headers)
    manifest = json.loads(body.decode("utf-8"))
    if manifest.get("manifests"):
        chosen = None
        for sub in manifest["manifests"]:
            plat = sub.get("platform") or {}
            if plat.get("architecture") == "amd64" and plat.get("os") == "linux":
                chosen = sub
                break
            if plat.get("architecture") in ("amd64", None) and chosen is None:
                chosen = sub
        if chosen is None:
            raise ValueError("manifest list 无 amd64 条目")
        status, _, body = http_get(opener, base + image + "/manifests/"
                                   + chosen["digest"], headers=headers)
        return json.loads(body.decode("utf-8")), chosen["digest"]
    return manifest, None


def cmd_plan(argv):
    check_mirror_host(argv.mirror)
    opener = make_opener()
    repo_path, tag = split_image(argv.image)
    token = get_token(opener, argv.mirror, repo_path)
    base = "%s://%s/v2/" % (BASE_SCHEME, argv.mirror)
    manifest, m_digest = resolve_amd64_manifest(opener, base, repo_path,
                                                token, tag)
    layers = [{"digest": l["digest"], "size": l["size"]}
              for l in manifest.get("layers", [])]
    if not layers:
        return _fail("NO_LAYERS", "manifest 无 layers")
    plan = {
        "image": argv.image, "mirror": argv.mirror,
        "config_digest": manifest["config"]["digest"],
        "config_size": manifest["config"]["size"],
        "manifest_digest": m_digest, "manifest_media_type":
            manifest.get("mediaType", ""),
        "layers": layers,
        "total_bytes": sum(l["size"] for l in layers)
                       + manifest["config"]["size"],
    }
    out = Path(argv.out)
    out.mkdir(parents=True, exist_ok=True)
    plan_path = out / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    _emit({"ok": True, "phase": "plan", "plan": str(plan_path),
           "layers": len(layers), "total_mb": plan["total_bytes"] // 1048576,
           "config_digest": plan["config_digest"][:30]})
    return 0


def _blob_path(blobs_dir, digest):
    hex_part = digest.split(":", 1)[1]
    return blobs_dir / "blobs" / "sha256" / hex_part


def _uid():
    """本进程工作文件后缀令牌（round-28 纪律 8：并发会话不共享工作文件）。"""
    return "p%d" % os.getpid()


def work_path(bdir, hex_part, role):
    """某角色（part / seg1 / assembling）的本进程工作文件路径。

    形如 <hex>.part.p12345：<hex>（内容寻址的成品名）仍然全局共享，并由
    os.replace 原子产出；下载过程中的中间名按进程隔离，两个会话并行拉同一
    镜像时不再互相踩 .part / .segN（Windows 上是改名撞 WinError 32，POSIX
    上是交叉写入污染）。
    """
    return bdir / ("%s.%s.%s" % (hex_part, role, _uid()))


def _role_of(name, hex_part):
    """工作文件名 → 角色名（<hex>.<role>[.<uid>]）；非工作文件返回 None。"""
    if not name.startswith(hex_part + "."):
        return None
    rest = name[len(hex_part) + 1:]
    parts = rest.split(".")
    tok = parts[0]
    if tok.startswith("seg") and tok[3:].isdigit():
        return tok
    if tok in ("part", "assembling"):
        return tok
    return None


def _not_in_use(path):
    """best-effort「此刻无人握着它的句柄」探测（认领他人半成品前用）。

    Windows 不需要：改名本身会撞 WinError 32，由 _claim_prior 的 except 兜住。
    POSIX 上改名对活跃对端是有害的（它的 fd 会跟着文件搬到我们的名下继续
    追加），所以先试一下非阻塞独占 flock；探不到就保守放弃认领。
    """
    if os.name == "nt":
        return True
    try:
        import fcntl
    except ImportError:
        return False
    try:
        with open(path, "rb") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return True
    except OSError:
        return False


def _work_owner(path, hex_part, role):
    """工作文件归属 → "mine" | "legacy" | "foreign"。

    mine 只认「本进程 PID 且写于本进程启动之后」——PID 复用留下的同名旧文件按
    foreign 处理，否则新进程会把上一世的半成品当成自己的进度。
    """
    try:
        st = path.stat()
    except OSError:
        return "foreign"
    suffix = path.name[len("%s.%s." % (hex_part, role)):]
    m = UID_RE.match(suffix)
    if not m:
        return "legacy"  # 改进程唯一名之前的中断进度
    if int(m.group(1)) == os.getpid():
        return "mine" if st.st_mtime >= PROC_START - 1 else "foreign"
    return "foreign"


def _claim_prior(bdir, hex_part, role):
    """认领他人留下的同角色半成品（原子改名，不共享句柄）。返回认领到的字节数。

    本进程已有 → 直接用；legacy 无 PID 名与「无人持有」的他人 PID 名 → 认领
    最大的那份；活跃并发会话的文件留给对方（改名失败或 flock 拿不到即放弃，
    各下各的，最多浪费带宽，不会互相污染）。
    """
    mine = work_path(bdir, hex_part, role)
    if mine.is_file():
        return mine.stat().st_size
    cands = [bdir / (hex_part + "." + role)]  # legacy 名
    cands += [p for p in bdir.glob("%s.%s.*" % (hex_part, role))
              if p.name != mine.name]
    best, best_size = None, 0
    for cand in cands:
        if not cand.is_file():
            continue
        if _work_owner(cand, hex_part, role) == "mine":
            continue
        if not _not_in_use(cand):
            continue
        size = cand.stat().st_size
        if size > best_size:
            best, best_size = cand, size
    if best is None or best_size <= 0:
        return 0
    try:
        os.replace(best, mine)
    except OSError:
        return 0  # 被对端占用（WinError 32）：放弃认领，从零下
    return best_size


def discard_work(bdir, hex_part):
    """丢弃本进程在某个 blob 上的全部半成品（sha 失配后重下前的清理）。"""
    removed = []
    for path in bdir.glob("%s.*" % hex_part):
        if path.name == hex_part:
            continue  # 成品名（内容寻址）不动
        role = _role_of(path.name, hex_part)
        if role is None or _work_owner(path, hex_part, role) != "mine":
            continue  # 对端进程的工作文件不碰
        path.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def _fetch_serial(opener, base, repo_path, digest, hex_part, final, part,
                  token):
    """单流断点续传（Range 不可用或小 blob 的回退路径）。"""
    headers = {"User-Agent": DEFAULT_UA}
    if token:
        headers["Authorization"] = "Bearer " + token
    have = part.stat().st_size if part.is_file() else 0
    if have:
        headers["Range"] = "bytes=%d-" % have
    started = time.time()
    req = urllib.request.Request(base + repo_path + "/blobs/" + digest,
                                 headers=headers)
    with opener.open(req, timeout=BLOB_TIMEOUT) as resp:
        if have and resp.status != 206:
            have = 0  # 服务端忽略 Range，整体重下
            part.unlink(missing_ok=True)
        mode = "ab" if have else "wb"
        h = hashlib.sha256()
        if have:
            with part.open("rb") as fh:
                for chunk in iter(lambda: fh.read(CHUNK), b""):
                    h.update(chunk)
        with part.open(mode) as fh:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                h.update(chunk)
                fh.write(chunk)
    got = part.stat().st_size
    if h.hexdigest() != hex_part:
        raise ValueError("sha256 失配: %s（预期 %s…，实得 %s…）"
                         % (digest[:30], hex_part[:12], h.hexdigest()[:12]))
    os.replace(part, final)
    return got, time.time() - started, bool(have)


def _probe_range(opener, base, repo_path, digest, token):
    """bytes=0-0 探测：206 → (True, 总大小)；否则 (False, None)。"""
    headers = {"User-Agent": DEFAULT_UA, "Range": "bytes=0-0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + repo_path + "/blobs/" + digest,
                                 headers=headers)
    with opener.open(req, timeout=TIMEOUT) as resp:
        if resp.status == 206:
            cr = resp.headers.get("Content-Range", "")
            total = cr.rsplit("/", 1)[-1]
            return True, (int(total) if total.isdigit() else None)
        return False, None


def _dl_span(opener, base, repo_path, digest, token, path, start, end):
    """下载 [start, end] 闭区间到 path（从现有长度续传）。返回新增字节数。"""
    span_len = end - start + 1
    have = path.stat().st_size if path.is_file() else 0
    if have >= span_len:
        return 0
    headers = {"User-Agent": DEFAULT_UA,
               "Range": "bytes=%d-%d" % (start + have, end)}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(base + repo_path + "/blobs/" + digest,
                                 headers=headers)
    got = 0
    with opener.open(req, timeout=BLOB_TIMEOUT) as resp:
        if have and resp.status != 206:
            have = 0
            got = 0
            with path.open("wb") as fh:  # 服务端忽略 Range：整段重下
                pass
        mode = "ab" if have else "wb"
        expected = span_len - have
        with path.open(mode) as fh:
            while expected > 0:
                chunk = resp.read(min(CHUNK, expected))
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                expected -= len(chunk)
    if path.stat().st_size != span_len:
        raise ValueError("分段长度失配: %s 段 %d-%d（预期 %dB 实得 %dB）"
                         % (digest[:24], start, end, span_len,
                            path.stat().st_size))
    return got


def fetch_blob(opener, base, repo_path, digest, dest, token,
               segments=6, workers=4):
    """blob 下载：并行 Range 分段（可续传）+ sha256 强制验证。

    工作文件改进程唯一名（<hex>.part.p<pid> / .seg<i>.p<pid>），会话之间不
    共享半成品；中断进度按 _claim_prior 的规则认领回来（legacy 名直接认，
    他人 PID 名静默超 WORK_STALE_SEC 才认）。Range 不可用或小 blob 回退单流。
    返回 (bytes, elapsed, resumed)。
    """
    algo, hex_part = digest.split(":", 1)
    if algo != "sha256":
        raise ValueError("仅支持 sha256 digest: %s" % digest)
    final = dest.parent / hex_part
    part = work_path(dest.parent, hex_part, "part")
    if final.is_file():
        h = hashlib.sha256(final.read_bytes()).hexdigest()
        if h == hex_part:
            return final.stat().st_size, 0.0, False
        final.unlink()  # 落盘内容损坏，重下
    started = time.time()
    _claim_prior(dest.parent, hex_part, "part")
    range_ok, total = _probe_range(opener, base, repo_path, digest, token)
    have0 = part.stat().st_size if part.is_file() else 0
    # 边界只依赖 total（跨运行稳定，seg 文件语义不漂移）
    if range_ok and total and total >= SEG_MIN * 2 and total > have0:
        n = max(1, min(segments, max(1, total // SEG_MIN)))
        seg_len = -(-total // n)
        spans = []
        i = 0
        while i * seg_len < total:
            start = i * seg_len
            end = min((i + 1) * seg_len, total) - 1
            role = "part" if i == 0 else "seg%d" % i
            if i > 0:
                _claim_prior(dest.parent, hex_part, role)
            spans.append((work_path(dest.parent, hex_part, role), start, end))
            i += 1
    else:
        spans = []
    if len(spans) <= 1:
        got, elapsed, resumed = _fetch_serial(
            opener, base, repo_path, digest, hex_part, final, part, token)
        return got, elapsed, resumed
    # 段 0 基线超出首段跨度的部分 → 预填进后续段（进度不丢）
    if have0 > spans[0][2] + 1:
        with part.open("rb") as pf:
            for path, start, end in spans[1:]:
                if start >= have0:
                    break
                span_len = end - start + 1
                have = path.stat().st_size if path.is_file() else 0
                if have >= span_len:
                    continue
                pf.seek(start)
                data = pf.read(min(have0, end + 1) - start)
                with path.open("ab") as f:
                    f.write(data[have:])
    resumed = have0 > 0 or any(p.is_file() for p, _s, _e in spans[1:])
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(workers, len(spans))) as pool:
        futs = [pool.submit(_dl_span, opener, base, repo_path, digest,
                            token, path, start, end)
                for path, start, end in spans]
        for f in concurrent.futures.as_completed(futs):
            f.result()  # 任一分段异常即上抛（seg 文件保留，重试续传）
    # 顺序拼接（按段长截断）到 staging + 整体验证，通过才替换 final
    h = hashlib.sha256()
    got = 0
    staging = final.parent / (hex_part + ".assembling")
    with staging.open("wb") as out:
        for path, start, end in spans:
            span_len = end - start + 1
            with path.open("rb") as fh:
                copied = 0
                for chunk in iter(lambda: fh.read(CHUNK), b""):
                    take = min(len(chunk), span_len - copied)
                    h.update(chunk[:take])
                    out.write(chunk[:take])
                    copied += take
                    if copied >= span_len:
                        break
            got += span_len
    if h.hexdigest() != hex_part:
        staging.unlink(missing_ok=True)
        raise ValueError("sha256 失配: %s（预期 %s…，实得 %s…）"
                         % (digest[:30], hex_part[:12], h.hexdigest()[:12]))
    for path, _s, _e in spans[1:]:
        path.unlink(missing_ok=True)
    os.replace(staging, final)
    part.unlink(missing_ok=True)
    return got, time.time() - started, resumed


def cmd_fetch(argv):
    plan = json.loads(Path(argv.plan).read_text(encoding="utf-8"))
    if plan.get("image") != argv.image or plan.get("mirror") != argv.mirror:
        return _param_error("plan 与 --image/--mirror 不一致")
    check_mirror_host(argv.mirror)
    blobs_dir = Path(argv.out)
    blobs_dir.mkdir(parents=True, exist_ok=True)
    (blobs_dir / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
    opener = make_opener()
    repo_path, _ = split_image(argv.image)
    token = get_token(opener, argv.mirror, repo_path)
    base = "%s://%s/v2/" % (BASE_SCHEME, argv.mirror)
    jobs = ([("config", plan["config_digest"], plan["config_size"])]
            + [("layer", l["digest"], l["size"]) for l in plan["layers"]])
    if plan.get("manifest_digest"):
        jobs.append(("manifest", plan["manifest_digest"], 0))
    results, total_got, total_elapsed, resumed_n = [], 0, 0.0, 0
    for kind, digest, expect in jobs:
        dest = _blob_path(blobs_dir, digest)
        size = elapsed = resumed = None
        last_state = last_detail = None
        for attempt in range(argv.retries + 1):
            try:
                size, elapsed, resumed = fetch_blob(
                    opener, base, repo_path, digest, dest, token,
                    segments=argv.segments, workers=argv.workers)
                last_state = None
                break
            except ValueError as exc:
                # sha 失配：本进程半成品可能被污染，整份丢弃重下（计一次重试）
                last_state, last_detail = "DIGEST_MISMATCH", str(exc)[:120]
                dest.parent.mkdir(parents=True, exist_ok=True)
                discard_work(dest.parent, digest.split(":", 1)[1])
            except (urllib.error.URLError, TimeoutError, OSError,
                    http.client.HTTPException) as exc:
                # 停流/断连：工作文件保留，同进程重试原地续传
                last_state, last_detail = "BLOB_STALL", "%s: %s" % (
                    exc.__class__.__name__, str(exc)[:120])
            if attempt < argv.retries:
                time.sleep(min(5 * (attempt + 1), 30))
        if last_state:
            return _fail(last_state, "%s（重试 %d 次未成）: %s"
                         % (digest[:30], argv.retries, last_detail))
        if expect and size != expect:
            return _fail("SIZE_MISMATCH",
                         "%s 宣称 %dB 实得 %dB" % (digest[:30], expect, size))
        total_got += size
        total_elapsed += elapsed
        resumed_n += int(resumed)
        results.append({"kind": kind, "digest": digest[:20],
                        "bytes": size, "resumed": resumed})
    _emit({"ok": True, "phase": "fetch", "blobs": len(results),
           "resumed": resumed_n, "total_mb": total_got // 1048576,
           "elapsed_s": round(total_elapsed, 1),
           "kbps": round(total_got / 1024.0 / max(total_elapsed, 0.001), 1),
           "results": results})
    return 0


def cmd_assemble(argv):
    plan = json.loads(Path(argv.plan).read_text(encoding="utf-8"))
    blobs = Path(argv.blobs)
    sha_dir = blobs / "blobs" / "sha256"
    algo_hex = lambda d: d.split(":", 1)[1]  # noqa: E731
    for d in [plan["config_digest"]] + [l["digest"] for l in plan["layers"]]:
        if not (sha_dir / algo_hex(d)).is_file():
            return _fail("BLOB_MISSING", "缺 blob: %s（先跑 fetch）" % d[:30])
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tag = "%s:latest" % argv.image if ":" not in argv.image else argv.image
    index = {"schemaVersion": 2, "mediaType":
             "application/vnd.oci.image.index.v1+json",
             "manifests": [{"mediaType": "application/vnd."
                            "docker.distribution.manifest.v2+json",
                            "digest": plan["manifest_digest"]
                            or "sha256:" + _manifest_digest(plan),
                            "size": _manifest_size(plan, sha_dir, algo_hex),
                            "platform": {"architecture": "amd64",
                                         "os": "linux"},
                            "annotations": {
                                "org.opencontainers.image.ref.name": tag}}]}
    with tempfile.TemporaryDirectory(prefix="oci-assemble-") as td:
        root = Path(td)
        (root / "blobs" / "sha256").mkdir(parents=True)
        (root / "oci-layout").write_text(
            '{"imageLayoutVersion":"1.0.0"}', encoding="utf-8")
        mpath = root / "blobs" / "sha256" / (
            algo_hex(index["manifests"][0]["digest"]))
        if plan.get("manifest_digest"):
            shutil.copy(sha_dir / algo_hex(plan["manifest_digest"]), mpath)
        else:
            mpath.write_text(json.dumps(_plan_to_manifest(plan),
                                        ensure_ascii=False),
                             encoding="utf-8")
        for d in [plan["config_digest"]] + [l["digest"] for l in plan["layers"]]:
            shutil.copy(sha_dir / algo_hex(d),
                        root / "blobs" / "sha256" / algo_hex(d))
        (root / "index.json").write_text(json.dumps(index, ensure_ascii=False),
                                         encoding="utf-8")
        with tarfile.open(out, "w") as tar:
            for name in ("oci-layout", "index.json", "blobs"):
                tar.add(root / name, arcname=name)
    _emit({"ok": True, "phase": "assemble", "archive": str(out),
           "tag": tag, "mb": out.stat().st_size // 1048576})
    return 0


def _plan_to_manifest(plan):
    return {"schemaVersion": 2,
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {"mediaType": "application/vnd.docker.container."
                       "image.v1+json", "digest": plan["config_digest"],
                       "size": plan["config_size"]},
            "layers": [{"mediaType": "application/vnd.docker.image.rootfs."
                        "diff.tar.gzip", "digest": l["digest"],
                        "size": l["size"]} for l in plan["layers"]]}


def _manifest_digest(plan):
    body = json.dumps(_plan_to_manifest(plan), sort_keys=True).encode()
    return hashlib.sha256(body).hexdigest()


def _manifest_size(plan, sha_dir, algo_hex):
    if plan.get("manifest_digest"):
        return (sha_dir / algo_hex(plan["manifest_digest"])).stat().st_size
    return len(json.dumps(_plan_to_manifest(plan), sort_keys=True).encode())


def find_docker(explicit=""):
    if explicit:
        return explicit if Path(explicit).is_file() else None
    found = shutil.which("docker")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def cmd_load(argv):
    archive = Path(argv.archive)
    if not archive.is_file():
        return _param_error("归档不存在: %s" % archive)
    docker = find_docker(argv.docker_bin)
    if not docker:
        return _fail("DOCKER_UNAVAILABLE", "docker 不可执行")
    p = subprocess.run([docker, "load", "-i", str(archive)], shell=False,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=argv.timeout)
    if p.returncode != 0:
        return _fail("LOAD_FAILED", (p.stderr or p.stdout).strip()[-500:])
    _emit({"ok": True, "phase": "load", "archive": str(archive),
           "output": (p.stdout or "").strip()[-300:]})
    return 0


def main():
    parser = argparse.ArgumentParser(description="Docker 镜像逐层下载器")
    sub = parser.add_subparsers(dest="phase", required=True)

    p = sub.add_parser("plan", help="解析 manifest 并产出计划")
    p.add_argument("--image", required=True)
    p.add_argument("--mirror", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("fetch", help="逐 blob 断点续传下载")
    p.add_argument("--image", required=True)
    p.add_argument("--mirror", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--retries", type=int, default=8,
                   help="单 blob 重试次数（超时/断连续传重试；sha 失配丢弃重下）")
    p.add_argument("--segments", type=int, default=6,
                   help="并行 Range 分段数（0/1=单流；小 blob 自动回退）")
    p.add_argument("--workers", type=int, default=4,
                   help="分段并发线程上限")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("assemble", help="组装 OCI image layout 归档")
    p.add_argument("--plan", required=True)
    p.add_argument("--blobs", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--image", required=True, help="镜像 tag（owner/repo[:tag]）")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("load", help="docker load 入库")
    p.add_argument("--archive", required=True)
    p.add_argument("--docker", dest="docker_bin", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=cmd_load)

    argv = parser.parse_args()
    try:
        return argv.func(argv)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            ValueError, json.JSONDecodeError) as exc:
        return _fail("FETCH_ERROR", "%s: %s" % (exc.__class__.__name__,
                                                str(exc)[:200]))


if __name__ == "__main__":
    sys.exit(main())
