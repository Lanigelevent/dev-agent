#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Docker 镜像源测速器：并行实测候选源，2 分钟内速度慢即判死（不傻等）。

方法：对每个候选源先做 SSRF 边界校验（仅 https、域名白名单形态、解析
IP 禁私网/环回/链路本地），然后 manifest 连通 + 首层 blob 8MB 分段下载
实测速度；限时 --deadline 秒（默认 120）未达 --min-kbps 即判 unusable。
只报实测结论，不引用任何转载清单的"声称可用"。

用法示例：
    py scripts/docker-mirror-probe.py --image swebench/sweb.eval.x86_64.django_1776_django-14999
    py scripts/docker-mirror-probe.py --image library/alpine --deadline 60
    py scripts/docker-mirror-probe.py --image scaleapi/swe-bench_pro-v2 --tag <instance_id>

退出码：0=至少一个源可用；1=全部不可用；2=参数错误。
"""
import argparse
import concurrent.futures
import ipaddress
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_MIRRORS = [
    "docker.1ms.run",
    "docker.1panel.live",
    "hub.rat.dev",
    "docker.m.daocloud.io",
    "dockerproxy.net",
    "docker.xuanyuan.me",
    "dockerhub.icu",
    "registry.dockermirror.com",
]
TIMEOUT_CONNECT = 15
MIRROR_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$")
IPV6_BRACKET_RE = re.compile(r"^\[(.+)\]$")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _check_mirror_host(mirror):
    """SSRF 边界：域名白名单形态 + 解析 IP 禁私网/环回/链路本地/保留。"""
    if not MIRROR_NAME_RE.match(mirror):
        raise ValueError("镜像源域名形态非法: %r" % mirror)
    infos = socket.getaddrinfo(mirror, 443, proto=socket.IPPROTO_TCP)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local \
                or ip.is_reserved or ip.is_multicast:
            raise ValueError("镜像源解析到受限地址 %s" % ip)


def _fetch(opener, url, headers=None, timeout=TIMEOUT_CONNECT, read_bytes=None,
            deadline_ts=None):
    """受限下载：无重定向跟随（防 rebinding），可限时。"""
    req = urllib.request.Request(url, headers=headers or {})
    with opener.open(req, timeout=timeout) as resp:
        if read_bytes is None:
            return resp.read()
        chunks = []
        while True:
            if deadline_ts is not None and time.time() > deadline_ts:
                break
            chunk = resp.read(min(65536, read_bytes))
            if not chunk:
                break
            chunks.append(chunk)
            if sum(len(c) for c in chunks) >= read_bytes:
                break
        return b"".join(chunks)


def _get_token(opener, mirror, image):
    """标准 Docker registry 匿名 Bearer 流程（按 WWW-Authenticate 指引）。"""
    probe = urllib.request.Request("https://%s/v2/" % mirror)
    try:
        opener.open(probe, timeout=TIMEOUT_CONNECT).read(1)
        return None  # 无需认证
    except urllib.error.HTTPError as exc:
        auth = exc.headers.get("WWW-Authenticate", "")
    m = re.search(r'realm="([^"]+)"', auth)
    if not m:
        raise ValueError("无可解析的认证 realm: %s" % auth[:80])
    params = {"service": mirror, "scope": "repository:%s:pull" % image,
              "account": "anonymous"}
    token_url = m.group(1) + "?" + urllib.parse.urlencode(params)
    with opener.open(urllib.request.Request(token_url),
                     timeout=TIMEOUT_CONNECT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("token") or data.get("access_token")


class _SsrfSafeRedirect(urllib.request.HTTPRedirectHandler):
    """跟随重定向（镜像源常用 307 跳转），但逐跳校验目标主机。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        parsed = urllib.parse.urlparse(newurl)
        if parsed.scheme != "https":
            raise ValueError("重定向到非 https: %s" % newurl[:80])
        host = parsed.hostname or ""
        m = IPV6_BRACKET_RE.match(host)
        if m:
            host = m.group(1)
        try:
            infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        except OSError as exc:
            raise ValueError("重定向主机解析失败 %s: %s" % (host, exc))
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local \
                    or ip.is_reserved or ip.is_multicast:
                raise ValueError("重定向到受限地址 %s" % ip)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _make_opener():
    return urllib.request.build_opener(_SsrfSafeRedirect)


def probe_mirror(mirror, image, deadline, min_kbps, opener=None,
                 check_host=None, tag="latest"):
    """单源实测：SSRF 校验 → token → manifest → 首 blob 8MB 分段测速。

    opener/check_host 可注入（离线反向验证用）；phase 记录实测终止阶段
    （token/manifest/blob）——manifest 可达 ≠ blob 可达（v1.22.0 实测：
    manifest 2s 返回而 blob CDN 0.1MB/s，判死依据必须在 blob 段）。
    """
    check_host = check_host or _check_mirror_host
    opener = opener if opener is not None else _make_opener()
    result = {"mirror": mirror, "status": "?", "kbps": 0.0, "detail": "",
              "phase": "token"}
    started = time.time()
    deadline_ts = started + deadline
    try:
        check_host(mirror)
        token = _get_token(opener, mirror, image)
        auth_headers = {"Authorization": "Bearer " + token} if token else {}
        base = "https://%s/v2/" % mirror
        result["phase"] = "manifest"
        # manifest（manifest list/index 时取首个 amd64 子 manifest）
        accept = ("application/vnd.docker.distribution.manifest.list.v2+json,"
                  "application/vnd.oci.image.index.v1+json,"
                  "application/vnd.docker.distribution.manifest.v2+json,"
                  "application/vnd.oci.image.manifest.v1+json")
        headers = dict(auth_headers)
        headers["Accept"] = accept
        manifest = json.loads(_fetch(
            opener, base + image + "/manifests/" + tag,
            headers=headers).decode("utf-8"))
        layers = manifest.get("layers") or []
        if not layers:
            subs = manifest.get("manifests") or []
            chosen = None
            for sub in subs:
                plat = sub.get("platform") or {}
                if plat.get("architecture") in ("amd64", "x86_64", None):
                    chosen = sub
                    if plat.get("architecture") == "amd64":
                        break
            if chosen is None and subs:
                chosen = subs[0]
            if chosen is not None:
                headers["Accept"] = accept
                manifest = json.loads(_fetch(
                    opener, base + image + "/manifests/" + chosen["digest"],
                    headers=headers).decode("utf-8"))
                layers = manifest.get("layers") or []
        if not layers:
            result["status"] = "unusable"
            result["detail"] = "manifest 无 layers"
            return result
        # 首 blob 拉 8MB 测速
        result["phase"] = "blob"
        blob_url = base + image + "/blobs/" + layers[0]["digest"]
        headers = dict(auth_headers)
        headers["Range"] = "bytes=0-8388607"
        data = _fetch(opener, blob_url, headers=headers,
                      timeout=max(int(deadline), 30), read_bytes=8388608,
                      deadline_ts=deadline_ts)
        elapsed = max(time.time() - started, 0.001)
        kbps = len(data) / 1024.0 / elapsed
        result["kbps"] = round(kbps, 1)
        result["downloaded_mb"] = round(len(data) / 1048576.0, 1)
        if len(data) < 65536:
            result["status"] = "unusable"
            result["detail"] = "blob 几乎无数据（%.0fKB/%.0fs）" % (
                len(data) / 1024.0, elapsed)
        elif kbps < min_kbps:
            result["status"] = "slow"
            result["detail"] = "%.1f KB/s 低于阈值 %d KB/s" % (kbps, min_kbps)
        else:
            result["status"] = "usable"
    except urllib.error.HTTPError as exc:
        result["status"] = "unusable"
        result["detail"] = "HTTP %d: %s" % (exc.code, str(exc.reason)[:80])
    except (urllib.error.URLError, OSError, TimeoutError, ValueError,
            json.JSONDecodeError) as exc:
        result["status"] = "unusable"
        result["detail"] = "%s: %s" % (exc.__class__.__name__, str(exc)[:80])
    result["elapsed_s"] = round(time.time() - started, 1)
    return result


def main():
    parser = argparse.ArgumentParser(description="Docker 镜像源实测速（不傻等）")
    parser.add_argument("--image", required=True,
                        help="目标镜像（owner/repo 形式，如 swebench/sweb.eval... 或 library/alpine）")
    parser.add_argument("--tag", default="latest",
                        help="镜像 tag（Pro 等按实例打 tag 的仓库必须显式给）")
    parser.add_argument("--mirrors", default=",".join(DEFAULT_MIRRORS),
                        help="逗号分隔候选源列表")
    parser.add_argument("--deadline", type=float, default=120.0,
                        help="单源总时限秒（默认 120：两分钟慢即判死）")
    parser.add_argument("--min-kbps", dest="min_kbps", type=float, default=100.0,
                        help="可用阈值 KB/s（默认 100）")
    argv = parser.parse_args()
    mirrors = [m.strip() for m in argv.mirrors.split(",") if m.strip()]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(mirrors)) as pool:
        futures = {pool.submit(probe_mirror, m, argv.image,
                               argv.deadline, argv.min_kbps,
                               tag=argv.tag): m
                   for m in mirrors}
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    results.sort(key=lambda r: (-r["kbps"], r["mirror"]))
    usable = [r for r in results if r["status"] == "usable"]
    _emit({"ok": bool(usable), "image": argv.image, "tag": argv.tag,
           "deadline_s": argv.deadline, "min_kbps": argv.min_kbps,
           "results": results,
           "usable_rank": [r["mirror"] for r in usable],
           "note": "实测口径：SSRF 边界校验 + manifest 连通 + 首 blob 8MB "
                   "分段下载速度；慢于时限/阈值即判死，不引用转载清单"})
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())
