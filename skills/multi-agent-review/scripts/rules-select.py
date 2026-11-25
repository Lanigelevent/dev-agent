#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""规则文档选择器（round-34，升级计划阶段 1-B：规则文档体系，借 open-code-review）。

用途:
    按变更文件路径从 rules/index.json 选命中的规则文档，拼成评审材料块。
    规则即文档：评审员的判断锚定在版本化的蒸馏规则上，而非纯模型直觉。
    规则全部来自本仓真实坑/实例（各文档末尾有出处），不编造通用最佳实践。

用法:
    python rules-select.py --root /path/dev-agent --files a.py b/models.py
    git diff A..B > names.txt   # 用 git 的 name-only 形式逐行落文件名
    python rules-select.py --root . --stdin < names.txt
    python rules-select.py --root . --files a.py --names-only   # 只列命中文档名

退出码:
    0 = 正常（含零命中）
    1 = index.json 缺失或形状不合格
    2 = 参数/环境错误
"""
import argparse
import fnmatch
import json
import sys
from pathlib import Path

CAP_PER_DOC = 4000      # 单文档字符上限
CAP_TOTAL = 12000       # 规则块总字符上限（材料 MATERIAL_CAP 之前先自控）


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def load_index(root):
    """读 rules/index.json → [(pattern, [doc,...])]；不合格返回 None。"""
    ipath = root / "skills" / "multi-agent-review" / "rules" / "index.json"
    if not ipath.is_file():
        return None
    try:
        data = json.loads(ipath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    mappings = data.get("mappings") if isinstance(data, dict) else None
    if not isinstance(mappings, list):
        return None
    out = []
    for m in mappings:
        if isinstance(m, dict) and isinstance(m.get("pattern"), str) \
                and isinstance(m.get("docs"), list):
            out.append((m["pattern"], [d for d in m["docs"] if isinstance(d, str)]))
    return out


def select_docs(root, files):
    """files 命中 pattern 的文档名集合（去重，保序）。"""
    mappings = load_index(root)
    if mappings is None:
        return None
    picked = []
    for pattern, docs in mappings:
        hit = any(fnmatch.fnmatch(f, pattern) or
                  fnmatch.fnmatch(f.replace("\\", "/"), pattern)
                  for f in files)
        if hit:
            for d in docs:
                if d not in picked:
                    picked.append(d)
    return picked


def render_block(root, doc_names):
    """拼装规则文档材料块（脱敏在 runner 侧统一做，这里只做截断）。"""
    rules_dir = root / "skills" / "multi-agent-review" / "rules"
    parts, total = [], 0
    for name in doc_names:
        p = rules_dir / name
        if not p.is_file() or p.suffix != ".md" or "/" in name or "\\" in name:
            continue  # 防路径穿越 + 只收 md（易错点：索引可被手改，须白名单校验）
        text = p.read_text(encoding="utf-8")[:CAP_PER_DOC]
        if total + len(text) > CAP_TOTAL:
            break
        parts.append("### %s\n%s" % (name, text))
        total += len(text)
    return "\n\n".join(parts)


def main():
    ap = argparse.ArgumentParser(description="评审规则文档选择器")
    ap.add_argument("--root", required=True, help="dev-agent 项目根")
    ap.add_argument("--files", nargs="*", default=[], help="变更文件路径列表")
    ap.add_argument("--stdin", action="store_true", help="从 stdin 逐行读文件路径")
    ap.add_argument("--names-only", action="store_true", help="只输出命中文档名")
    argv = ap.parse_args()

    root = Path(argv.root).resolve()
    files = list(argv.files)
    if argv.stdin:
        files.extend(l.strip() for l in sys.stdin if l.strip())
    if not files:
        _emit({"ok": True, "matched": [], "block": ""})
        return 0

    picked = select_docs(root, files)
    if picked is None:
        _emit({"ok": False, "error": "rules/index.json 缺失或形状不合格"})
        return 1
    block = "" if argv.names_only else render_block(root, picked)
    _emit({"ok": True, "matched": picked, "block": block,
           "block_chars": len(block)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
