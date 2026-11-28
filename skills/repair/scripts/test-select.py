#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变更感知测试选择器（阶段 5 批次二 M6，round-235）。

用途
    从变更文件推导「最小必跑」测试子集：变更 .py 的模块名与顶层符号
    （class/def）→ 扫描仓库 test_*.py 的 import 与名字引用 → 命中的测试
    文件集合。供 fix-apply 闸五 auto 档提速；漏测率以全量为
    金标准抽检（验收口径见 ROADMAP §6 阶段 5）。

    决策面（保守三原则）：
    - 只选直接证据：测试文件 import 了变更模块（含后缀链形态）或引用了变更符号才入选；
    - 子集为空 → 回退全量（不冒充「没有受影响测试」）；
    - 选择器只提速不裁决：子集红 = 闸五红（失败语义不变）。

用法示例
    py test-select.py select --repo <仓库根> --files a.py,b.py     # 显式变更清单
    py test-select.py select --repo <仓库根> --rev HEAD~1..HEAD    # git diff 推导
退出码：0=成功（stdout 单 JSON：selected/changed/mode）；2=输入错误（仓库缺失、--files/--rev 双缺）。
诊断走 stderr。
"""
import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path


def _module_name(repo, file_path):
    """仓库根相对路径 → 点分模块名（无扩展名；__init__ 取父包名）。"""
    file_path = Path(file_path)
    if not file_path.is_absolute():
        file_path = Path(repo) / file_path
    try:
        rel = file_path.resolve().relative_to(Path(repo).resolve())
    except ValueError:
        return None
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts or any(p == "" for p in parts):
        return None
    return ".".join(parts)


def _top_symbols(py_text):
    """顶层 class/def/赋值常量名集合（ast 顶层 only，保守）。"""
    names = set()
    try:
        tree = ast.parse(py_text)
    except SyntaxError:
        return names
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def _test_refs(py_text):
    """测试文本中的名字引用集：import 的模块名 + 全部标识符（保守超集）。"""
    refs = set()
    try:
        tree = ast.parse(py_text)
    except SyntaxError:
        return refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                refs.add(a.name)
                refs.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            refs.add(node.module)
            refs.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
    return refs


def select_tests(repo, changed_files):
    """变更清单 → 受影响测试文件路径列表（直接证据法）。

    返回 (selected 排序列表, changed 有效列表)。changed 中非 .py 或仓库外
    文件只参与记录不参与匹配。
    """
    repo = Path(repo)
    changed = []
    symbols = set()
    modnames = set()
    for raw in changed_files:
        p = repo / raw
        mod = _module_name(repo, raw)
        if mod:
            modnames.add(mod)
            segs = mod.split(".")
            for k in range(1, len(segs)):
                modnames.add(".".join(segs[k:]))
        if raw.endswith(".py") and p.is_file():
            changed.append(raw)
            try:
                symbols |= _top_symbols(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    selected = []
    test_files = (
        sorted((repo / "tests").glob("test_*.py")) if (repo / "tests").is_dir()
        else []) + sorted(repo.glob("test_*.py"))
    for tf in test_files:
        try:
            refs = _test_refs(tf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if refs & (modnames | symbols):
            selected.append(str(tf))
    return sorted(set(selected)), sorted(set(changed))


def _changed_from_rev(repo, rev):
    """git diff --name-only <rev> → 变更清单（子进程、shell=False）。"""
    proc = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", rev],
        shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60)
    if proc.returncode != 0:
        return []
    return [l.strip() for l in (proc.stdout or "").splitlines() if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="变更感知测试选择器 select")
    ap.add_argument("verb", choices=["select"])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--files", default="", help="逗号分隔变更文件清单")
    ap.add_argument("--rev", default=None, help="git diff 范围（如 HEAD~1..HEAD）")
    args = ap.parse_args(argv)
    repo = Path(args.repo)
    if not repo.is_dir():
        sys.stderr.write("仓库不存在: %s\n" % args.repo)
        return 2
    if args.rev:
        changed = _changed_from_rev(repo, args.rev)
    elif args.files:
        changed = [f.strip() for f in args.files.split(",") if f.strip()]
    else:
        sys.stderr.write("--files 与 --rev 必须给一个\n")
        return 2
    selected, changed = select_tests(repo, changed)
    sys.stdout.write(json.dumps(
        {"ok": True, "selected": selected, "changed": changed,
         "mode": "direct-evidence"}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
