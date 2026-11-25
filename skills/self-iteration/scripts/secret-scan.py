#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""凭据形态扫描门禁：仓库跟踪文件里出现密钥形态即失败。

用途：
    阶段三 3.4 门禁。用 git 跟踪清单（git ls-files）逐个读文本文件，按
    固定规则集找凭据形态（AWS access key / 私钥块 / GitHub 与 Slack 令牌 /
    JWT / Bearer 令牌 / 赋值型 api_key|secret|token|password）；命中即
    退出码 1。豁免只有两条路：文件级白名单（必须写理由，入库
    skills/self-iteration/secret-allowlist.json）与行内标记
    `secret-scan: allow`（同一行或上一行）。输出 snippet 一律经脱敏，
    不把命中的值原样打出来（硬约束 5）。

用法：
    python secret-scan.py --root .
    python secret-scan.py --root . --allowlist skills/self-iteration/secret-allowlist.json
    python secret-scan.py --root . --max-hits 200

退出码：
    0 = 无命中（或命中全部在白名单/行内豁免）
    1 = 存在未豁免的凭据形态
    2 = 输入或环境错误（不是 git 仓库、白名单 JSON 非法）
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".pdf",
    ".zip", ".gz", ".tar", ".whl", ".so", ".pyd", ".dll", ".exe", ".pyc",
    ".parquet", ".bin", ".mp4", ".woff", ".woff2", ".ttf", ".jar",
}
MAX_BYTES = 1_000_000
SNIPPET_CAP = 160
INLINE_MARK = "secret-scan: allow"
REDACT_RE = re.compile(
    r"(?i)((?:api[_-]?key|secret|token|password|passwd|authorization)"
    r"\s*\"?\s*[:=]\s*)([^\s,;#]{3,})")
TOKENISH_RE = re.compile(r"\b(AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|"
                         r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
                         r"\.[A-Za-z0-9_-]{8,})\b")
PLACEHOLDERS = ("<redacted>", "example", "dummy", "placeholder", "changeme",
                "your_", "your-", "xxx", "test-", "fake-", "fake_", "sample",
                "not-a-real", "redacted")
RULES = [
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key-block", re.compile(r"-----BEGIN [A-Z ]{0,20}PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
                       r"\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-token", re.compile(r"(?i)\bBearer\s+([A-Za-z0-9._\-+/=]{16,})")),
    ("assigned-credential", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|authorization)"
        r"\b\s*[:=]\s*[\"']?([A-Za-z0-9/+_\-]{16,})")),
]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _redact(text):
    out = REDACT_RE.sub(r"\1<redacted>", text)
    out = TOKENISH_RE.sub("<redacted>", out)
    return out[:SNIPPET_CAP]


def _value_of(match):
    groups = match.groups()
    return groups[0] if groups else ""


def _placeholder(value):
    low = value.lower()
    return any(low.startswith(p) or p in low for p in PLACEHOLDERS)


def _tracked_files(root):
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError("git ls-files 失败: %s"
                           % proc.stderr.decode("utf-8", "replace")[:200])
    names = proc.stdout.decode("utf-8", "replace").split("\0")
    return [n for n in names if n.strip()]


def _load_allowlist(path):
    if path is None:
        return {}, []
    p = Path(path)
    if not p.is_file():
        raise ValueError("白名单不存在: %s" % p)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError("白名单 JSON 非法: %s" % exc)
    entries = {}
    problems = []
    for item in data.get("allowlist") or []:
        name = str(item.get("path") or "").replace("\\", "/")
        reason = str(item.get("reason") or "").strip()
        rule = str(item.get("rule") or "*").strip()
        if not name or not reason:
            problems.append({"path": name, "problem": "缺 path 或 reason"})
            continue
        entries.setdefault(name, []).append({"rule": rule, "reason": reason})
    return entries, problems


def _allow_entry(entries, name, rule):
    for item in entries.get(name) or []:
        if item["rule"] in ("*", rule):
            return item
    return None


def scan(root, allowlist_path, max_hits):
    root = Path(root).resolve()
    allow, allow_problems = _load_allowlist(allowlist_path)
    started = time.monotonic()
    try:
        files = _tracked_files(root)
    except RuntimeError as exc:
        raise ValueError(str(exc))
    hits = []
    allowlisted = []
    skipped = {"suffix": 0, "binary": 0, "large": 0, "missing": 0}
    for name in files:
        path = root / name
        if path.suffix.lower() in SKIP_SUFFIXES:
            skipped["suffix"] += 1
            continue
        if not path.is_file():
            skipped["missing"] += 1
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                skipped["large"] += 1
                continue
            raw = path.read_bytes()
        except OSError:
            skipped["missing"] += 1
            continue
        if b"\x00" in raw[:4096]:
            skipped["binary"] += 1
            continue
        text = raw.decode("utf-8", "replace")
        prev = ""
        for lineno, line in enumerate(text.splitlines(), 1):
            inline_ok = INLINE_MARK in line or INLINE_MARK in prev
            prev = line
            for rule, pattern in RULES:
                m = pattern.search(line)
                if not m:
                    continue
                if rule == "assigned-credential" and _placeholder(_value_of(m)):
                    continue
                item = {"path": name.replace("\\", "/"), "line": lineno,
                        "rule": rule, "snippet": _redact(line.strip())}
                entry = _allow_entry(allow, name, rule)
                if entry is not None:
                    item["allow_reason"] = entry["reason"]
                    allowlisted.append(item)
                elif inline_ok:
                    item["inline_allow"] = True
                    allowlisted.append(item)
                elif len(hits) < max_hits:
                    hits.append(item)
                break
    hit_paths = {h["path"] for h in hits} | {h["path"] for h in allowlisted}
    stale = sorted(p for p in allow if p not in hit_paths)
    return {
        "ok": not hits and not allow_problems,
        "state": "PASS" if not hits and not allow_problems else "HIT",
        "root": str(root),
        "scanned_files": len(files) - sum(skipped.values()),
        "skipped": skipped,
        "rules": [r[0] for r in RULES],
        "hits": hits,
        "hits_truncated": len(hits) >= max_hits,
        "allowlisted": [{"path": a["path"], "line": a["line"],
                         "rule": a["rule"]} for a in allowlisted],
        "allowlist_problems": allow_problems,
        "allowlist_stale": stale,
        "elapsed_sec": round(time.monotonic() - started, 3),
    }


def main():
    parser = argparse.ArgumentParser(description="凭据形态扫描")
    parser.add_argument("--root", default=".")
    parser.add_argument("--allowlist",
                        default="skills/self-iteration/secret-allowlist.json")
    parser.add_argument("--max-hits", type=int, default=100)
    argv = parser.parse_args()
    allow = argv.allowlist
    if allow and not Path(allow).is_absolute():
        allow = str(Path(argv.root).resolve() / allow)
    try:
        result = scan(argv.root, allow, argv.max_hits)
    except ValueError as exc:
        _emit({"ok": False, "state": "ERROR", "error": str(exc)})
        return 2
    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
