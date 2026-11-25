#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PR 发布器：把 pr-kit 素材经 Git 托管 API 创建真正的 Pull Request。

输入 pr-kit.py 产物目录（pr-title.txt / pr-body.md），POST 到
{remote}/repos/{repo}/pulls（GitHub 兼容 REST）。远端白名单：https 公网或
本地回环（http 仅供测试）；内网/明文公网拒绝。token 从环境变量
PUBLISH_GIT_TOKEN 读取，缺失即拒绝（rc 2），绝不落盘。

创建成功返回 PR 的 html_url 与编号；API 拒绝（如已存在同 head 的 PR），
退出码 1 并附响应摘要。本脚本只创建 PR，不合并；合并仍由人工决定。

用法示例：
    py pr-publish.py --bundle pr-bundle --repo owner/proj --head review-fix/x --base main
    py pr-publish.py --bundle pr-bundle --repo o/p --head h --base b \
        --remote http://127.0.0.1:8123   # 测试用回环

退出码：0=创建成功；1=API 拒绝；2=输入/环境错误。
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _validate_remote(url):
    """API 远端校验：https 公网或 http 回环；内网/明文公网拒绝。"""
    parsed = urllib.parse.urlparse(str(url).strip())
    host = (parsed.hostname or "").lower()
    loopback = host in ("localhost", "::1") or host.startswith("127.")
    if not host:
        return None, "远端缺 host"
    if parsed.scheme != "https" and not loopback:
        return None, "仅允许 https 公网或 http 回环"
    if not loopback and (host.startswith("10.") or host.startswith("192.168.")
                         or host.startswith("169.254.")
                         or host.endswith((".internal", ".local"))
                         or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host)):
        return None, "拒绝内网地址: %s" % host
    return parsed, None


def _api_post(base_parsed, path, token, payload):
    port = base_parsed.port
    netloc = base_parsed.hostname + (":%d" % port if port else "")
    url = urllib.parse.urlunparse(
        (base_parsed.scheme, netloc, path, "", "", ""))
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + token,
               "Accept": "application/vnd.github+json"}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="PR 发布器（创建 Pull Request）")
    parser.add_argument("--bundle", required=True, help="pr-kit 产物目录")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--head", required=True, help="源分支（如 review-fix/x）")
    parser.add_argument("--base", required=True, help="目标分支（如 main）")
    parser.add_argument("--remote", default="https://api.github.com",
                        help="API 远端（缺省 GitHub）")
    argv = parser.parse_args()
    bundle = Path(argv.bundle)
    if not bundle.is_dir():
        _emit({"ok": False, "error": "bundle 目录不存在: %s" % bundle})
        return 2
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", argv.repo):
        _emit({"ok": False, "error": "repo 需为 owner/name 形式: %s" % argv.repo})
        return 2
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", argv.head) or \
            not re.fullmatch(r"[A-Za-z0-9._/-]+", argv.base):
        _emit({"ok": False, "error": "分支名含非法字符"})
        return 2
    parsed, err = _validate_remote(argv.remote)
    if err:
        _emit({"ok": False, "error": "远端校验失败: %s" % err})
        return 2
    token = os.environ.get("PUBLISH_GIT_TOKEN", "")
    if not token:
        _emit({"ok": False, "error": "缺少 PUBLISH_GIT_TOKEN 环境变量"
                                     "（token 只走环境变量，不落盘）"})
        return 2
    title_path = bundle / "pr-title.txt"
    body_path = bundle / "pr-body.md"
    if not title_path.is_file() or not body_path.is_file():
        _emit({"ok": False, "error": "bundle 缺 pr-title.txt 或 pr-body.md"
                                     "（先运行 pr-kit.py）"})
        return 2
    title = title_path.read_text(encoding="utf-8").strip()
    body = body_path.read_text(encoding="utf-8")
    if not title:
        _emit({"ok": False, "error": "PR 标题为空"})
        return 2
    try:
        status, resp = _api_post(parsed, "/repos/%s/pulls" % argv.repo,
                                 token, {"title": title, "body": body,
                                         "head": argv.head, "base": argv.base})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        _emit({"ok": False, "error": "API 拒绝（HTTP %d）: %s" % (exc.code, detail)})
        return 1
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "请求失败: %s" % exc})
        return 1
    if status not in (200, 201):
        _emit({"ok": False, "error": "API 返回 %d: %s" % (status, str(resp)[:200])})
        return 1
    _emit({"ok": True, "pr_url": resp.get("html_url", ""),
           "number": resp.get("number"),
           "note": "PR 已创建；合并由人工决定（本脚本不合并）"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
