#!/usr/bin/env python3
"""被审仓库团队规范文件发现与摘录注入（AB-22 rules 注入面，round-214）。

用途
    在被审仓库根按惯例名发现团队规范文件（AGENTS.md / CLAUDE.md /
    .cursorrules / .cursor/rules/*.mdc / CONVENTIONS.md /
    .github/copilot-instructions.md），输出有界摘录（默认 4000 字符）
    并统一脱敏（复用 audit-log 的 6 模式密钥形态脱敏）——供评审材料
    构造作为第 4 通道（前 3 通道：区域等级/已证事实/规则蒸馏文档）。

用法示例
    python skills/multi-agent-review/scripts/repo-rules-inject.py \
        --repo /path/to/audited/repo --max-chars 4000

退出码
    0 = 完成（发现 0 个也 ok，none_found=true）
    2 = 输入错误（--repo 不存在）
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

CONVENTION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    "CONVENTIONS.md",
    ".github/copilot-instructions.md",
)
CURSOR_RULES_DIR = ".cursor/rules"


def _load_redact():
    spec = importlib.util.spec_from_file_location(
        "audit_log", ROOT / "skills/production-guardrails/scripts/audit-log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.redact


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def discover(repo, max_chars):
    redact = _load_redact()
    found = []
    injected = 0
    for name in CONVENTION_FILES:
        path = repo / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        excerpt = text[:max_chars]
        truncated = len(text) > len(excerpt)
        excerpt = redact(excerpt)
        found.append({
            "name": name,
            "path": str(path),
            "chars": len(text),
            "excerpt": excerpt,
            "truncated": truncated,
        })
        injected += len(excerpt)
    rules_dir = repo / CURSOR_RULES_DIR
    if rules_dir.is_dir():
        for path in sorted(rules_dir.glob("*.mdc")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            excerpt = redact(text[:max_chars])
            truncated = len(text) > max_chars
            found.append({
                "name": ".cursor/rules/" + path.name,
                "path": str(path),
                "chars": 0 if truncated else len(text),
                "excerpt": excerpt,
                "truncated": truncated,
            })
            injected += len(excerpt)
    return found, injected


def main():
    parser = argparse.ArgumentParser(description="被审仓库团队规范文件发现与摘录注入")
    parser.add_argument("--repo", required=True, help="被审仓库根")
    parser.add_argument("--max-chars", type=int, default=4000,
                        help="单文件摘录上限（默认 4000）")
    argv = parser.parse_args()
    repo = Path(argv.repo)
    if not repo.is_dir():
        print(json.dumps({"ok": False, "error": "仓库根不存在: %s" % argv.repo},
                         ensure_ascii=False))
        return 2
    found, injected = discover(repo, argv.max_chars)
    result = {
        "ok": True,
        "repo": str(repo),
        "found": found,
        "injected_chars": injected,
        "none_found": not found,
    }
    _emit(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())