#!/usr/bin/env python3
"""代码图缓存增量维护：提取符号定义与 import 关系，mtime+size 预筛避免重复读文件。

用途:
    主流程步骤 2。build 全量建缓存；update 只重读变化的文件。
    单符号定义位置超过 64 个时只保留同目录的；relations 总量超 200000 截断并标 truncated。

用法:
    python graph-cache.py build --repo /path/to/repo --out /path/cache.json
    python graph-cache.py update --repo /path/to/repo --cache /path/cache.json

退出码:
    0 = 正常
    2 = 参数/环境错误（缺子命令/路径、repo 非目录、update 时缓存不存在）
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".c", ".cc",
             ".cpp", ".h", ".hpp", ".rb", ".rs", ".cs", ".php"}
MAX_DEFS_PER_SYMBOL = 64
MAX_RELATIONS = 200000
MAX_FILE_SIZE = 512 * 1024
DEF_PATTERNS = {
    ".py": re.compile(r"^\s*(?:def|class)\s+(\w+)"),
    ".js": re.compile(r"\bfunction\s+(\w+)|\bclass\s+(\w+)"),
    ".jsx": re.compile(r"\bfunction\s+(\w+)|\bclass\s+(\w+)"),
    ".ts": re.compile(r"\bfunction\s+(\w+)|\bclass\s+(\w+)"),
    ".tsx": re.compile(r"\bfunction\s+(\w+)|\bclass\s+(\w+)"),
    ".go": re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?(\w+)"),
    ".java": re.compile(r"\b(?:class|interface|enum)\s+(\w+)"),
    ".cs": re.compile(r"\b(?:class|interface|enum)\s+(\w+)"),
    ".c": re.compile(r"^\s*(?:\w+[\w*\s]+)?\s*(\w+)\s*\([^;]*\)\s*\{"),
    ".cc": re.compile(r"^\s*(?:\w+[\w*\s]+)?\s*(\w+)\s*\([^;]*\)\s*\{"),
    ".cpp": re.compile(r"^\s*(?:\w+[\w*\s]+)?\s*(\w+)\s*\([^;]*\)\s*\{"),
    ".h": re.compile(r"\b(?:class|struct)\s+(\w+)"),
    ".hpp": re.compile(r"\b(?:class|struct)\s+(\w+)"),
    ".rb": re.compile(r"^\s*def\s+(\w+)"),
    ".rs": re.compile(r"\bfn\s+(\w+)"),
    ".php": re.compile(r"\bfunction\s+(\w+)"),
}
IMPORT_PATTERNS = {
    ".py": re.compile(r"^\s*import\s+([\w.]+)|^\s*from\s+([\w.]+)\s+import"),
    ".js": re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ".jsx": re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ".ts": re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ".tsx": re.compile(r"from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    ".go": re.compile(r"import\s+\"([^\"]+)\"|^\s*\"([^\"]+)\""),
    ".java": re.compile(r"^\s*import\s+([\w.]+);"),
    ".rb": re.compile(r"^\s*require(?:_relative)?\s+[\"']([^\"']+)[\"']"),
}


def _git_ls_files(repo):
    p = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if p.returncode != 0:
        return None
    return [f for f in p.stdout.split("\0") if f.strip()]


def _parse_file(path):
    """提取单文件符号定义与 import 关系。超限大文件跳过。"""
    stat = path.stat()
    entry = {"mtime": stat.st_mtime, "size": stat.st_size, "defs": {}, "imports": []}
    if stat.st_size > MAX_FILE_SIZE:
        entry["skipped"] = "file_too_large"
        return entry
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        entry["skipped"] = "unreadable"
        return entry
    def_re = DEF_PATTERNS.get(ext)
    if def_re:
        for i, line in enumerate(text.splitlines(), 1):
            m = def_re.search(line)
            if m:
                sym = next((g for g in m.groups() if g), None)
                if sym:
                    entry["defs"].setdefault(sym, []).append(i)
    imp_re = IMPORT_PATTERNS.get(ext)
    if imp_re:
        for line in text.splitlines():
            m = imp_re.search(line)
            if m:
                mod = next((g for g in m.groups() if g), None)
                if mod:
                    entry["imports"].append(mod)
    return entry


def _build_symbols(files):
    """聚合符号 -> 定义位置；超 64 个只保留同目录的并标 truncated。"""
    symbols = {}
    for path, entry in files.items():
        for sym in entry.get("defs", {}):
            symbols.setdefault(sym, []).append(path)
    truncated_symbols = []
    for sym, paths in list(symbols.items()):
        if len(paths) > MAX_DEFS_PER_SYMBOL:
            dirs = {}
            for p in paths:
                dirs.setdefault(str(Path(p).parent), []).append(p)
            keep_dir = max(dirs, key=lambda d: len(dirs[d]))
            symbols[sym] = dirs[keep_dir]
            truncated_symbols.append(sym)
    return symbols, truncated_symbols


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _write_cache(path, repo, files, symbols, truncated_symbols, relations_total, truncated):
    cache = {
        "version": 1,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo": str(repo),
        "files": files,
        "symbols": symbols,
        "truncated_symbols": truncated_symbols,
        "relations_total": relations_total,
        "truncated": truncated,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def main():
    parser = argparse.ArgumentParser(description="代码图缓存")
    sub = parser.add_subparsers(dest="mode")
    p_build = sub.add_parser("build")
    p_build.add_argument("--repo", required=True)
    p_build.add_argument("--out", required=True)
    p_update = sub.add_parser("update")
    p_update.add_argument("--repo", required=True)
    p_update.add_argument("--cache", required=True)
    argv = parser.parse_args()
    if not argv.mode:
        _emit({"ok": False, "error": "缺少子命令 build|update"})
        return 2
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    listing = _git_ls_files(repo)
    if listing is None:
        _emit({"ok": False, "error": "git ls-files 失败（非 git 仓库?）"})
        return 2
    cache_path = argv.out if argv.mode == "build" else argv.cache
    if argv.mode == "build":
        files = {}
    else:
        cache_file = Path(argv.cache)
        if not cache_file.is_file():
            _emit({"ok": False, "error": "缓存不存在，请先 build: %s" % cache_file})
            return 2
        try:
            old = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "缓存不可读: %s" % exc})
            return 2
        files = dict(old.get("files") or {})
    reread = 0
    current = set()
    truncated = False
    for rel in listing:
        if Path(rel).suffix.lower() not in CODE_EXTS:
            continue
        current.add(rel)
        path = repo / rel
        if not path.is_file():
            continue
        stat = path.stat()
        old_entry = files.get(rel)
        if argv.mode == "update" and old_entry and \
                old_entry.get("mtime") == stat.st_mtime and old_entry.get("size") == stat.st_size:
            continue
        files[rel] = _parse_file(path)
        reread += 1
    for stale in set(files) - current:
        del files[stale]
    relations_total = 0
    for entry in files.values():
        for _ in entry.get("imports", []):
            if relations_total >= MAX_RELATIONS:
                truncated = True
                break
            relations_total += 1
        if truncated:
            break
    symbols, truncated_symbols = _build_symbols(files)
    _write_cache(cache_path, repo, files, symbols, truncated_symbols, relations_total, truncated)
    _emit(
        {
            "ok": True,
            "mode": argv.mode,
            "cache": str(cache_path),
            "files_scanned": len(current),
            "files_reread": reread,
            "symbols": len(symbols),
            "relations_total": relations_total,
            "truncated": truncated,
            "truncated_symbols": truncated_symbols[:20],
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
