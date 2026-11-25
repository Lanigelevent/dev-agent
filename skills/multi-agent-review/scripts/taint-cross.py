#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨文件污点两遍分析（落地案例库 ed5c32b6187d 的业界方案）。

pass 1（摘要）：对目录内每个模块的顶层函数生成过程间污点摘要——
  参数污染 → 汇点（param→sink，附 rule_id）与 参数污染 → 返回值（param→return）。
pass 2（调用方）：解析 import 建立别名表，追踪调用方文件内的污点变量；
  跨模块调用的实参被污染且被调方摘要命中 → 在调用方行报跨文件流；
  命中 param→return 且对应实参被污染 → 返回值在调用方继续传播（链式流）。

范围与局限（如实声明）：仅顶层函数摘要（不含方法/闭包）；相对 import 按
同包解析；污点集为文件级近似（非精确数据流）；清洗点不建模。源/汇沿用
taint-config.json（与同文件引擎同源，总监治理）。

用法示例：
    py taint-cross.py --root <仓库或目录>
    py taint-cross.py --root <仓库> --diff <unified diff>   # 仅报变更文件内的流

退出码：0=成功（含零发现）；2=输入错误。
"""
import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES_SCRIPT = (ROOT / "skills" / "multi-agent-review" / "scripts"
                / "deterministic-rules.py")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}
MAX_FILE_BYTES = 200_000


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_engine():
    import importlib.util
    spec = importlib.util.spec_from_file_location("dr_engine", str(RULES_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _module_name(rel_path):
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _collect_files(root, max_files):
    files = []
    for path in sorted(Path(root).rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
        if len(files) >= max_files:
            break
    return files


def _import_aliases(tree, my_module):
    """local_name -> 被引全名（模块或 模块.符号），支持一级相对导入。"""
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                alias[name.asname or name.name.split(".")[0]] = name.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = my_module.split(".")
                prefix = base[:max(0, len(base) - node.level)]
                mod = ".".join(prefix + [node.module or ""]).strip(".")
            else:
                mod = node.module or ""
            for name in node.names:
                alias[name.asname or name.name] = (mod + "." + name.name).strip(".")
    return alias


def _call_target(call, alias):
    """解析调用目标为点路径；无法解析返回 None。"""
    parts = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    base = node.id
    if base in alias:
        full = alias[base]
    else:
        full = base
    if parts:
        full = full + "." + ".".join(parts)
    return full


def _seeds_of(node, tainted, sources):
    """表达式携带的污点种子集：被污染变量 + 外部 source 调用。"""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id in tainted:
            out |= tainted[sub.id]
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name) and sub.func.id in sources:
                out.add("<external>")
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in sources:
            out.add("<external>")
            break
        if isinstance(sub, ast.Name) and sub.id in sources:
            out.add("<external>")
            break
    return out


def _func_summary(func, sources, sinks):
    """pass 1：单函数摘要（param→sink 列表, param→return 参数集）。"""
    params = [a.arg for a in func.args.args]
    tainted = {p: {p} for p in params}
    sink_hits = []
    returns_taint = set()
    for node in ast.walk(func):
        targets, value = [], None
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            targets, value = [node.target], node.value
        for target in targets:
            seeds = _seeds_of(value, tainted, sources) if value is not None else set()
            if seeds:
                tainted[target.id] = seeds
        if isinstance(node, ast.Call):
            full = _call_target(node, {})
            if full in sinks:
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    hit = _seeds_of(arg, tainted, sources) & set(params)
                    if hit:
                        sink_hits.append((sinks[full], tuple(sorted(hit))))
        if isinstance(node, ast.Return) and node.value is not None:
            returns_taint |= _seeds_of(node.value, tainted, sources) & set(params)
    return sink_hits, returns_taint


def _split_target(full):
    if not full or "." not in full:
        return None
    module, _, func = full.rpartition(".")
    return (module, func)


def _pass_two(tree, alias, summaries, sources, sinks, tainted, lines_by_no, path):
    """pass 2：调用方文件内追踪跨模块流（两轮定点：先源，再跨模块返回值）。"""
    findings = []
    for _round in range(2):
        for node in ast.walk(tree):
            targets, value = [], None
            if isinstance(node, ast.Assign):
                targets = [t for t in node.targets if isinstance(t, ast.Name)]
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets, value = [node.target], node.value
            for target in targets:
                if value is None:
                    continue
                seeds = _seeds_of(value, tainted, sources)
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Call):
                        summary = summaries.get(_split_target(
                            _call_target(sub, alias)))
                        if summary and summary["returns_taint"]:
                            args = list(sub.args) + [kw.value
                                                     for kw in sub.keywords]
                            if any(_seeds_of(a, tainted, sources) for a in args):
                                seeds.add("<cross>")
                if seeds:
                    tainted[target.id] = seeds
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        full = _call_target(node, alias)
        args = list(node.args) + [kw.value for kw in node.keywords]
        arg_seeds = set()
        for arg in args:
            arg_seeds |= _seeds_of(arg, tainted, sources)
        if not arg_seeds or node.lineno in seen:
            continue
        summary = summaries.get(_split_target(full))
        if summary and summary["sink_hits"]:
            rule_id = summary["sink_hits"][0][0]
            reason = "跨文件污点流：实参经 %s 抵达汇点 %s" % (full, rule_id)
        elif full in sinks and "<cross>" in arg_seeds:
            # 链式流终点是本地汇点：仅当污染由跨模块调用引入时上报，
            # 纯同文件流交给 deterministic-rules，避免重复
            rule_id = sinks[full]
            reason = "跨文件污点流：跨模块引入的污染抵达本地汇点 %s" % full
        else:
            continue
        if node.lineno in seen:
            continue
        seen.add(node.lineno)
        findings.append({
            "rule_id": rule_id,
            "severity": "高",
            "file": str(path),
            "line": node.lineno,
            "snippet": _ENGINE[0].redact(lines_by_no.get(node.lineno, "").strip())[:160],
            "reason": reason,
        })
    return findings


_ENGINE = [None]


def main():
    parser = argparse.ArgumentParser(description="跨文件污点两遍分析（只读）")
    parser.add_argument("--root", required=True, help="仓库或目录根")
    parser.add_argument("--diff", default="", help="unified diff（仅报变更文件内的流）")
    parser.add_argument("--max-files", type=int, default=200, help="扫描文件上限")
    argv = parser.parse_args()
    root = Path(argv.root).resolve()
    if not root.is_dir():
        _emit({"ok": False, "error": "目录不存在: %s" % root})
        return 2
    engine = _load_engine()
    _ENGINE[0] = engine
    sources, sinks = engine._load_taint_config()
    files = _collect_files(root, max(1, argv.max_files))
    if not files:
        _emit({"ok": True, "engine": "taint-cross", "files_scanned": 0,
               "summaries": 0, "findings": [], "note": "目录无 Python 文件"})
        return 0
    summaries = {}
    alias_by_file = {}
    trees = {}
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, SyntaxError):
            continue
        trees[path] = tree
        module = _module_name(path.relative_to(root))
        alias_by_file[path] = _import_aliases(tree, module)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sink_hits, returns_taint = _func_summary(node, sources, sinks)
                if sink_hits or returns_taint:
                    summaries[(module, node.name)] = {
                        "sink_hits": sink_hits, "returns_taint": returns_taint}
    findings = []
    for path, tree in trees.items():
        lines_by_no = {i + 1: line for i, line in
                       enumerate(path.read_text(encoding="utf-8",
                                                errors="replace").splitlines())}
        findings.extend(_pass_two(tree, alias_by_file[path], summaries,
                                  sources, sinks, {}, lines_by_no, path))
    if argv.diff:
        diff_path = Path(argv.diff)
        if not diff_path.is_file():
            _emit({"ok": False, "error": "diff 文件不存在: %s" % diff_path})
            return 2
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
        changed = tuple(f["path"].replace("\\", "/")
                        for f in engine.parse_diff(diff_text))
        findings = [f for f in findings
                    if Path(f["file"]).as_posix().replace("\\", "/")
                    .endswith(changed)]
    dedup = {}
    for f in findings:
        dedup[(f["rule_id"], f["file"], f["line"])] = f
    ordered = sorted(dedup.values(), key=lambda f: (f["file"], f["line"]))
    _emit({"ok": True, "engine": "taint-cross",
           "files_scanned": len(files), "summaries": len(summaries),
           "findings": ordered})
    return 0


if __name__ == "__main__":
    sys.exit(main())
