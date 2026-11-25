#!/usr/bin/env python3
"""文档漂移十五问：对项目自身做 15 项可机械判定的一致性检查。

用途:
    自迭代链路。孤儿脚本/副本分叉/死代码/行为覆盖/主线接入/退出码说明/审计覆盖/
    问数表述/硬编码行数/参数漂移/孤儿 references/行数基线/基线常量/args 覆盖/README 引用。

用法:
    python doc-drift.py --root /path/dev-agent

退出码:
    0 = 全绿
    1 = 有待处理项
    2 = 根目录非法（缺 AGENTS.md/BASELINE.md/agent.json/skills）
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

QUESTION_NAMES = [
    "孤儿脚本", "副本分叉", "死代码", "行为覆盖", "主线接入", "退出码说明", "审计覆盖",
    "问数表述", "硬编码行数", "参数漂移", "孤儿 references", "行数基线", "基线常量",
    "args 覆盖", "README 引用",
]
SHARED_NAMES = {"SECRET_PATTERNS", "redact", "HUNK_RE", "parse_diff",
                "locate_agent_json", "load_args"}
CANON = {"rules": 38, "dimensions": 7, "edge_types": 11, "questions": 15}
MD_RECOUNT_PATTERNS = [
    (re.compile(r"(\d+)\s*条(?:硬)?规则"), CANON["rules"]),
    (re.compile(r"(\d+)\s*个(?:评审)?维度"), CANON["dimensions"]),
    (re.compile(r"(\d+)\s*类(?:边界|异常)"), CANON["edge_types"]),
]


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class Ctx:
    def __init__(self, root):
        self.root = root
        self.md_files = [p for p in [root / "AGENTS.md", root / "README.md", root / "BASELINE.md"]
                         if p.is_file()]
        self.md_files += sorted((root / "skills").glob("*/SKILL.md"))
        self.md_text = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8", errors="replace")
                        for p in self.md_files}
        self.all_md = "\n".join(self.md_text.values())
        self.scripts = sorted((root / "skills").glob("*/scripts/*.py"))
        self.baseline = (root / "BASELINE.md").read_text(encoding="utf-8", errors="replace") \
            if (root / "BASELINE.md").is_file() else ""
        # 行为覆盖问的口径：tests/ 全目录（测试可分散多文件，锚定单文件
        # 会把「已被独立测试文件覆盖的脚本」误报为未覆盖——v1.24.0 实踩）
        self.tests_text = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in sorted((root / "tests").glob("test_*.py"))
        ) if (root / "tests").is_dir() else ""
        try:
            self.args = json.loads((root / "agent.json").read_text(encoding="utf-8")).get("args") or {}
        except (OSError, ValueError):
            self.args = {}


def _def_blocks(path):
    """{name: [normalized 定义文本]}，函数与顶层赋值，基于 ast 行号切片。"""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return {}
    lines = src.splitlines()
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            block = "\n".join(lines[node.lineno - 1: node.end_lineno])
            out.setdefault(node.name, []).append(_norm(block))
        elif isinstance(node, ast.Assign):
            block = "\n".join(lines[node.lineno - 1: node.end_lineno])
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out.setdefault(t.id, []).append(_norm(block))
    return out


def _argparse_flags(path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    flags = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument":
            if node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str) \
                    and node.args[0].value.startswith("-"):
                flags.add(node.args[0].value)
    return flags


def _docstring(path):
    try:
        return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    except (OSError, SyntaxError):
        return ""


def _const(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return node.value
    return None


def _lit_list(node):
    if isinstance(node, ast.List):
        return [e.value for e in node.elts if isinstance(e, ast.Constant)]
    return None


def _lit_dict(node):
    if isinstance(node, ast.Dict):
        return {k.value: v.value for k, v in zip(node.keys, node.values)
                if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    return None


def run_checks(ctx):
    results = []

    def add(i, name, ok, evidence):
        results.append({"id": i, "name": name, "status": "ok" if ok else "fail",
                        "evidence": evidence})

    script_names = [p.name for p in ctx.scripts]
    orphans = [n for n in script_names if n not in ctx.all_md]
    add(1, QUESTION_NAMES[0], not orphans,
        "孤儿: %s" % orphans if orphans else "全部 %d 个脚本均被文档提及" % len(script_names))

    fork = {}
    for p in ctx.scripts:
        for name, blocks in _def_blocks(p).items():
            if name in SHARED_NAMES:
                for b in blocks:
                    fork.setdefault(name, {}).setdefault(b, []).append(p.name)
    diverged = {k: v for k, v in fork.items() if len(v) > 1}
    add(2, QUESTION_NAMES[1], not diverged,
        "分叉: %s" % {k: list(v.values()) for k, v in diverged.items()} if diverged
        else "共享定义 %s 无分叉" % sorted(fork.keys()))

    dead = []
    for p in ctx.scripts:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        used = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used[node.id] = used.get(node.id, 0) + 1
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and used.get(node.name, 0) == 0:
                dead.append("%s:%s" % (p.name, node.name))
    add(3, QUESTION_NAMES[2], not dead, dead if dead else "无死函数")

    untested = [n for n in script_names if n not in ctx.tests_text]
    add(4, QUESTION_NAMES[3], not untested,
        "未覆盖: %s" % untested if untested else
        ("tests/ 目录覆盖全部 %d 个脚本" % len(script_names)))

    off_main = [n for n in script_names if n not in ctx.md_text.get("AGENTS.md", "")]
    add(5, QUESTION_NAMES[4], not off_main,
        "不在 AGENTS.md: %s" % off_main if off_main else "全部脚本接入主流程文档")

    noexit = [p.name for p in ctx.scripts if "退出码" not in _docstring(p)]
    add(6, QUESTION_NAMES[5], not noexit, noexit if noexit else "全部脚本 docstring 含退出码说明")

    add(7, QUESTION_NAMES[6], "audit-log" in ctx.md_text.get("AGENTS.md", ""),
        "AGENTS.md 审计覆盖" if "audit-log" in ctx.md_text.get("AGENTS.md", "")
        else "AGENTS.md 未提及 audit-log")

    bad_counts = []
    for path, text in ctx.md_text.items():
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat, canon in MD_RECOUNT_PATTERNS:
                for m in pat.finditer(line):
                    if int(m.group(1)) != canon:
                        bad_counts.append("%s:%d %s" % (path, lineno, m.group(0)))
            for m in re.finditer(r"(?:十[一二三四五六七八九]|\d+)\s*问", line):
                if "第" in line[max(0, m.start() - 2):m.start()]:
                    continue
                n = m.group(0)
                if n.startswith("十"):
                    val = 10 if len(n) == 2 else 11 + "一二三四五六七八九".index(n[1])
                else:
                    val = int(re.sub(r"\D", "", n) or 0)
                if val != CANON["questions"]:
                    bad_counts.append("%s:%d %s" % (path, lineno, m.group(0)))
    add(8, QUESTION_NAMES[7], not bad_counts,
        bad_counts if bad_counts else "规则/维度/边界/问数表述与基线一致")

    claims = []
    for path, text in ctx.md_text.items():
        if path == "BASELINE.md":
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "SKILL.md" in line:
                for m in re.finditer(r"(\d+)\s*行", line):
                    claims.append("%s:%d %s" % (path, lineno, m.group(0)))
    add(9, QUESTION_NAMES[8], not claims, claims if claims else "无散落的 SKILL.md 行数断言")

    drift = []
    for p in ctx.scripts:
        defined = _argparse_flags(p)
        doc_flags = set(re.findall(r"--[\w][\w-]*", _docstring(p)))
        skill_flags = set()
        for sp in ctx.md_files:
            if sp.name == "SKILL.md" or sp.parent.name == p.parent.parent.name:
                for line in sp.read_text(encoding="utf-8", errors="replace").splitlines():
                    if p.name in line:
                        skill_flags |= set(re.findall(r"--[\w][\w-]*", line))
        unknown = (doc_flags | skill_flags) - defined
        if unknown:
            drift.append("%s 未定义: %s" % (p.name, sorted(unknown)))
    add(10, QUESTION_NAMES[9], not drift, drift if drift else "docstring 与 SKILL.md 的参数无漂移")

    orphan_refs = []
    for ref in (ctx.root / "skills").glob("*/references/*"):
        if ref.is_file() and ref.name not in ctx.all_md:
            orphan_refs.append(ref.name)
    add(11, QUESTION_NAMES[10], not orphan_refs,
        orphan_refs if orphan_refs else "references 文件均被文档引用")

    baseline_rows = {}
    for m in re.finditer(r"^-\s*([a-z-]+):\s*(\d+)\s*$", ctx.baseline, re.M):
        if (ctx.root / "skills" / m.group(1)).is_dir():
            baseline_rows[m.group(1)] = int(m.group(2))
    line_bad = []
    for skill, n in baseline_rows.items():
        sp = ctx.root / "skills" / skill / "SKILL.md"
        actual = len(sp.read_text(encoding="utf-8").splitlines()) if sp.is_file() else -1
        if actual != n:
            line_bad.append("%s: 基线 %d vs 实际 %d" % (skill, n, actual))
    if not baseline_rows:
        line_bad.append("BASELINE.md 缺 SKILL.md 行数基线表")
    add(12, QUESTION_NAMES[11], not line_bad, line_bad if line_bad else
        "行数基线核对通过: %s" % baseline_rows)

    const_bad = []
    if not re.search(r"规模\s*0\.3\s*/\s*耦合\s*0\.4\s*/\s*稳定\s*0\.3", ctx.baseline):
        const_bad.append("BASELINE 缺权重 0.3/0.4/0.3")
    for p in ctx.scripts:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        if p.name == "score.py":
            w = _lit_dict(_const(tree, "WEIGHTS")) or {}
            if w != {"scale": 0.3, "coupling": 0.4, "stability": 0.3}:
                const_bad.append("score.py WEIGHTS 与基线不符: %s" % w)
        if p.name == "dispatch-plan.py":
            dims = _lit_list(_const(tree, "DIMENSIONS")) or []
            if len(dims) != CANON["dimensions"]:
                const_bad.append("dispatch-plan 维度数 %d != %d" % (len(dims), CANON["dimensions"]))
        if p.name == "deterministic-rules.py":
            n = len(re.findall(r"(?<!def )_rule\(", p.read_text(encoding="utf-8")))
            if n != CANON["rules"]:
                const_bad.append("deterministic-rules 规则数 %d != %d" % (n, CANON["rules"]))
        if p.name == "edge-detect.py":
            edges = _lit_list(_const(tree, "EDGE_TYPES")) or []
            if len(edges) != CANON["edge_types"]:
                const_bad.append("edge-detect 边界类别 %d != %d" % (len(edges), CANON["edge_types"]))
    if len(QUESTION_NAMES) != CANON["questions"]:
        const_bad.append("doc-drift 问数 %d != %d" % (len(QUESTION_NAMES), CANON["questions"]))
    add(13, QUESTION_NAMES[12], not const_bad, const_bad if const_bad else "基线常量与脚本一致")

    args_bad = []
    if not ctx.args:
        args_bad.append("agent.json args 为空或不可解析")
    script_blob = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in ctx.scripts)
    for key in ctx.args:
        if key not in script_blob and key not in ctx.md_text.get("AGENTS.md", ""):
            args_bad.append("args.%s 无人消费" % key)
    if "oversized_diff_lines" in ctx.args:
        if str(ctx.args["oversized_diff_lines"]) not in script_blob:
            args_bad.append("oversized_diff_lines 字面量与脚本不一致")
    add(14, QUESTION_NAMES[13], not args_bad, args_bad if args_bad else
        "args %d 个键均被消费" % len(ctx.args))

    missing_refs = []
    for path in (ctx.md_text.get("README.md", "") + ctx.md_text.get("AGENTS.md", "")).splitlines():
        for m in re.finditer(r"skills/[\w./-]+\.py", path):
            if not (ctx.root / m.group(0)).is_file():
                missing_refs.append(m.group(0))
    add(15, QUESTION_NAMES[14], not missing_refs,
        missing_refs if missing_refs else "README/AGENTS 引用的脚本路径均存在")
    return results


def main():
    parser = argparse.ArgumentParser(description="文档漂移十五问")
    parser.add_argument("--root", required=True, help="项目根目录")
    argv = parser.parse_args()
    root = Path(argv.root)
    if not root.is_dir() or not (root / "AGENTS.md").is_file() \
            or not (root / "skills").is_dir() or not (root / "BASELINE.md").is_file():
        _emit({"ok": False, "error": "根目录非法：需含 AGENTS.md、BASELINE.md、skills/"})
        return 2
    ctx = Ctx(root)
    results = run_checks(ctx)
    failed = [r["id"] for r in results if r["status"] != "ok"]
    _emit({
        "ok": not failed,
        "root": str(root),
        "total": len(results),
        "failed": failed,
        "questions": results,
    })
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
