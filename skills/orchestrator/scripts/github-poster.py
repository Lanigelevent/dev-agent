#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub 行内评论海报：pr-kit 评论包 → PR 行内评论（round-113，P0-3）。

用途
----
读 pr-kit.py 产出的 review-comments.json（path/line/body，与 GitHub
REST 同形），逐条 POST /repos/{o}/{r}/pulls/{n}/comments 行内评论。
token 只走环境变量（不落盘、不打日志）；端点白名单=公网 https 或本地
回环（与 LLM 端点纪律同款），内网/保留段默认拒绝，局域网自建端点须在
EXTRA_ALLOWED_HOSTS 显式登记；--dry-run 只打印载荷不联网。

commit_id 缺省自动取 PR 头提交（GET /pulls/{n} 的 head.sha）；422（行
不在 diff 上）如实计失败不静默；429/5xx 一次重试。

用法示例：
    python github-poster.py --repo owner/name --pr 42 \
        --comments review-comments.json --dry-run
    python github-poster.py --repo owner/name --pr 42 \
        --comments review-comments.json --token-env GITHUB_TOKEN

退出码：0=全部发出（或 dry-run）；1=有失败（明细列出）；2=参数错误。
stdout 输出单个 JSON 文档。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://api.github.com"

# 局域网自建端点（如局域网 Gitea）的显式放行名单：登记条目后内网 https
# 主机才放行；默认拒绝内网/保留段（口径对齐 llm/provider.py 白名单——
# 公网 https 或回环，内网/私有/保留地址拒绝）。
EXTRA_ALLOWED_HOSTS = frozenset()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _allowed_base(base):
    import ipaddress
    import urllib.parse
    p = urllib.parse.urlparse(base)
    host = (p.hostname or "").lower()
    if p.scheme != "https":
        return host in ("localhost", "::1") or host.startswith("127.")
    if host in EXTRA_ALLOWED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        # 保留段拒绝（SSRF）：私有/回环/链路本地三判覆盖 10/8、192.168/16、
        # 172.16/12、169.254/16、127/8、::1 等全部保留段。
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    if host.endswith((".internal", ".local")):
        return False  # 内网域名口径对齐 llm/provider.py:110-113
    return True


def _request(url, method, token, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") \
        if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("User-Agent", "dev-agent-poster")
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", "replace")
    return resp.status, (json.loads(body) if body.strip() else {})


def _request_retry(url, method, token, payload=None, attempts=2):
    last = None
    for i in range(attempts):
        try:
            return _request(url, method, token, payload)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and i + 1 < attempts:
                time.sleep(2)
                last = (exc.code, str(exc)[:160])
                continue
            return exc.code, str(exc)[:200]
        except (OSError, ValueError) as exc:
            return 0, str(exc)[:200]
    return last or (0, "unknown")


def post_comments(base, repo, pr, comments, commit_id, token, dry_run):
    """逐条 POST；返回 (posted, failed)。422 如实计失败。"""
    posted, failed = [], []
    url = "%s/repos/%s/pulls/%d/comments" % (base, repo, pr)
    for c in comments:
        payload = {"body": c.get("body", ""), "commit_id": commit_id,
                   "path": c.get("path", ""), "line": c.get("line")}
        if not payload["path"]:
            failed.append({"path": "", "line": c.get("line"),
                           "status": 0, "detail": "path 缺失"})
            continue
        if dry_run:
            posted.append({"path": payload["path"],
                           "line": payload["line"], "dry_run": True})
            continue
        status, detail = _request_retry(url, "POST", token, payload)
        if status in (200, 201):
            posted.append({"path": payload["path"],
                           "line": payload.get("line")})
        else:
            failed.append({"path": payload["path"],
                           "line": payload.get("line"),
                           "status": status, "detail": str(detail)[:160]})
    return posted, failed


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="GitHub 行内评论海报")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--comments", required=True,
                    help="pr-kit 产出的 review-comments.json")
    ap.add_argument("--commit-id", default="",
                    help="评论锚定的头提交 SHA（缺省自动取 PR head）")
    ap.add_argument("--token-env", default="GITHUB_TOKEN",
                    help="token 所在环境变量名（缺省 GITHUB_TOKEN）")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印将发送的载荷，不联网")
    args = ap.parse_args()
    if not _allowed_base(args.base_url):
        _emit({"ok": False, "error": "端点不在白名单（公网 https 或回环；"
                                     "内网须在 EXTRA_ALLOWED_HOSTS 显式登记）: %s"
               % args.base_url})
        return 2
    cp = Path(args.comments)
    if not cp.is_file():
        _emit({"ok": False, "error": "评论包不存在: %s" % cp})
        return 2
    try:
        comments = json.loads(cp.read_text(encoding="utf-8"))
    except ValueError as exc:
        _emit({"ok": False, "error": "评论包不可解析: %s" % exc})
        return 2
    if not isinstance(comments, list):
        comments = comments.get("comments") or []
    token = os.environ.get(args.token_env, "")
    if not args.dry_run and not token:
        _emit({"ok": False, "error": "环境变量 %s 未设置（token 只走环境变量）"
               % args.token_env})
        return 2
    commit_id = args.commit_id
    if not commit_id and not args.dry_run:
        status, detail = _request_retry(
            "%s/repos/%s/pulls/%d" % (args.base_url, args.repo, args.pr),
            "GET", token)
        if status != 200:
            _emit({"ok": False, "error": "取 PR head 失败: %s %s"
                   % (status, str(detail)[:120])})
            return 1
        commit_id = (detail.get("head") or {}).get("sha", "")
        if not commit_id:
            _emit({"ok": False, "error": "PR head.sha 为空"})
            return 1
    posted, failed = post_comments(args.base_url, args.repo, args.pr,
                                   comments, commit_id, token,
                                   args.dry_run)
    _emit({"ok": not failed and (args.dry_run or bool(comments)),
           "dry_run": args.dry_run, "total": len(comments),
           "posted": len(posted), "failed": failed,
           "commit_id": commit_id or None})
    return 0 if not failed else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
