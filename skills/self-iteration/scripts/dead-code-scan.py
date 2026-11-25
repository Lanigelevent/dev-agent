#!/usr/bin/env python3
"""死代码扫描：未用 import、死形参、死开关（argparse 定义了但从未读取的参数）。

用途:
    自迭代链路。基于 ast 的静态检查，扫描 skills/ 下全部 Python 脚本。

用法:
    python dead-code-scan.py --root /path/dev-agent

退出码:
    0 = 无死代码
    1 = 有发现
    2 = 参数/环境错误
"""
import argparse
import ast
import json
import sys
from pathlib import Path

SKIP_PARAMS = {"self", "cls"}


def _imported_names(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.append(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    names.append(a.asname or a.name)
    return names


def _argparse_dests(tree):
    dests = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            flag = None
            dest = None
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str) \
                    and node.args[0].value.startswith("-"):
                flag = node.args[0].value
            for kw in node.keywords:
                if kw.arg == "dest" and isinstance(kw.value, ast.Constant):
                    dest = kw.value.value
            if flag:
                dests[dest or flag.lstrip("-").replace("-", "_")] = flag
    return dests


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def scan_file(path):
    findings = []
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return findings
    name_usage = {}
    attr_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name_usage[node.id] = name_usage.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            attr_names.add(node.attr)
    for name in _imported_names(tree):
        if name_usage.get(name, 0) == 0:
            findings.append({"kind": "unused_import", "detail": name})
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_names = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id != node.name:
                    body_names.add(sub.id)
            a = node.args
            params = [p.arg for p in (a.posonlyargs + a.args + a.kwonlyargs)
                      if p.arg not in SKIP_PARAMS]
            if a.vararg:
                params = [p for p in params if p != a.vararg.arg]
            if a.kwarg:
                params = [p for p in params if p != a.kwarg.arg]
            for pname in params:
                if pname not in body_names:
                    findings.append({"kind": "dead_param",
                                     "detail": "%s(): %s" % (node.name, pname)})
    for dest, flag in _argparse_dests(tree).items():
        if dest not in attr_names and dest not in name_usage:
            findings.append({"kind": "dead_switch", "detail": "%s (dest=%s)" % (flag, dest)})
    return findings


def main():
    parser = argparse.ArgumentParser(description="死代码扫描")
    parser.add_argument("--root", required=True, help="项目根目录")
    argv = parser.parse_args()
    root = Path(argv.root)
    skills = root / "skills"
    if not root.is_dir() or not skills.is_dir():
        _emit({"ok": False, "error": "root 需含 skills/ 目录"})
        return 2
    results = []
    for p in sorted(skills.glob("*/scripts/*.py")):
        for f in scan_file(p):
            results.append({"file": p.relative_to(root).as_posix(), **f})
    _emit({
        "ok": not results,
        "scanned": len(list(skills.glob("*/scripts/*.py"))),
        "findings": results,
        "kinds": ["unused_import", "dead_param", "dead_switch"],
    })
    return 1 if results else 0


if __name__ == "__main__":
    sys.exit(main())
