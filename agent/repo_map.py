#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库地图（agent 层：tree-sitter，运行于项目 .venv Python）。

借鉴 Aider 的 repo map 思路：符号定义（函数/类）+ 引用计数 + 按被引用
热度排序，在字符预算内给 LLM 最高效的仓库上下文。v1 仅 Python；
round-59（阶段四 4.2）扩到 TS/TSX/JS 与 Go（语法包依赖见 pyproject）。

用法示例（.venv/Scripts/python agent/repo_map.py）：
    python agent/repo_map.py --repo <仓库> --max-chars 6000

退出码：0=成功；2=输入错误。
"""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

import tree_sitter_go
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules",
             "llm-tasks", "runs", "reports", "retro"}
# 多语言（round-59，阶段四 4.2）：语法对象按语言缓存；扩展名 → 语言名。
# 三个语法包（python/ts/go）都是 MIT，已在 pyproject 与许可证登记。
_GRAMMARS = {
    "python": Language(tree_sitter_python.language()),
    "ts": Language(tree_sitter_typescript.language_typescript()),
    "tsx": Language(tree_sitter_typescript.language_tsx()),
    "go": Language(tree_sitter_go.language()),
}
EXT_LANG = {".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "ts",
            ".jsx": "tsx", ".mjs": "ts", ".cjs": "ts", ".go": "go"}
_TS_KINDS = {"function_declaration": "func", "method_definition": "func",
             "class_declaration": "class", "interface_declaration": "class",
             "enum_declaration": "class", "type_alias_declaration": "class",
             "abstract_class_declaration": "class"}
_DEF_KINDS = {
    "python": {"function_definition": "func", "class_definition": "class"},
    "ts": _TS_KINDS,
    "tsx": _TS_KINDS,
    "go": {"function_declaration": "func", "method_declaration": "func",
           "type_spec": "class"},
}
# TS 常量式函数：const foo = () => {...} / const foo = function () {...}
_TS_FUNC_VALUES = {"arrow_function", "function_expression", "function"}
_IDENT_KINDS = {"identifier", "type_identifier", "field_identifier",
                "property_identifier"}
LANG = _GRAMMARS["python"]   # 兼容旧引用（单语言时代的公开常量）
DEF_KINDS = set(_DEF_KINDS["python"])


def _walk(node):
    """深度优先遍历（tree-sitter 0.26：grammar_name 取语法名）。"""
    yield node
    for child in node.children:
        yield from _walk(child)


def _lang_for(path):
    """路径 → 语言名（EXT_LANG）；不支持的扩展名返回 None。"""
    return EXT_LANG.get(Path(path).suffix.lower())


def _def_name(node):
    """定义节点 → 名字：优先 name 字段，兜底首个标识符子节点。"""
    field = node.child_by_field_name("name")
    if field is not None:
        return field.text.decode("utf-8", "replace")
    for child in node.children:
        if child.grammar_name in _IDENT_KINDS:
            return child.text.decode("utf-8", "replace")
    return None


def _source_files(repo):
    """仓库内受支持的源码文件 → [(Path, 相对 posix 路径)]（按路径排序）。

    目录级剪枝 SKIP_DIRS（node_modules 里 .ts 很多，不能遍历完再逐文件过滤）；
    但**只剪子目录**，仓库根本身即使位于 reports/node_modules 等同名目录下
    也不会被整体跳过（round-58 实踩）。
    """
    root = Path(repo)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        base = Path(dirpath)
        for name in sorted(filenames):
            if Path(name).suffix.lower() not in EXT_LANG:
                continue
            path = base / name
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            out.append((path, rel))
    out.sort(key=lambda item: item[1])
    return out


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def build_map(repo, max_files=300):
    parsers = {}
    files = {}
    symbol_defs = {}   # name -> [{file, kind, line}]
    symbol_refs = {}   # name -> total_refs
    scanned = 0
    for path, rel in _source_files(repo):
        lang = _lang_for(path)
        parser = parsers.get(lang)
        if parser is None:
            parser = parsers[lang] = Parser(_GRAMMARS[lang])
        scanned += 1
        if scanned > max_files:
            break
        try:
            tree = parser.parse(path.read_bytes())
        except OSError:
            continue
        kinds = _DEF_KINDS[lang]
        defs, refs = [], {}
        for node in _walk(tree.root_node):
            kind = node.grammar_name
            if kind in kinds:
                name = _def_name(node)
                if name:
                    defs.append({"name": name, "kind": kinds[kind],
                                 "line": node.start_point[0] + 1})
            elif kind == "variable_declarator" and lang in ("ts", "tsx"):
                value = node.child_by_field_name("value")
                if value is not None and value.grammar_name in _TS_FUNC_VALUES:
                    name = _def_name(node)
                    if name:
                        defs.append({"name": name, "kind": "func",
                                     "line": node.start_point[0] + 1})
            elif kind in _IDENT_KINDS:
                name = node.text.decode("utf-8", "replace")
                refs[name] = refs.get(name, 0) + 1
        for d in defs:
            symbol_defs.setdefault(d["name"], []).append(
                {"file": rel, "kind": d["kind"], "line": d["line"]})
            refs.pop(d["name"], None)
        for name, count in refs.items():
            symbol_refs[name] = symbol_refs.get(name, 0) + count
        if defs:
            files[rel] = {"loc": len(tree.root_node.text.decode(
                "utf-8", "replace").splitlines()), "defs": defs}
    ranked = sorted(
        ({"name": name, "kind": locs[0]["kind"], "defs": len(locs),
          "files": sorted({l["file"] for l in locs}),
          "total_refs": symbol_refs.get(name, 0),
          "first_def": locs[0]}
         for name, locs in symbol_defs.items()),
        key=lambda s: (-s["total_refs"], -s["defs"], s["name"]))
    return {"files": files, "ranked_symbols": ranked, "scanned": scanned}


def render_material(repo_map, max_chars):
    """把地图渲染成给 LLM 的紧凑材料（预算内）。"""
    lines = ["## 仓库符号地图（按被引用热度排序）"]
    used = len(lines[0])
    for sym in repo_map["ranked_symbols"]:
        entry = "- %s %s（refs=%d, defs=%d, 如 %s:%d）" % (
            sym["kind"], sym["name"], sym["total_refs"], sym["defs"],
            sym["first_def"]["file"], sym["first_def"]["line"])
        if used + len(entry) > max_chars:
            lines.append("…（预算截断，共 %d 个符号）"
                         % len(repo_map["ranked_symbols"]))
            break
        lines.append(entry)
        used += len(entry) + 1
    lines.append("")
    lines.append("## 文件与顶层定义")
    for rel, info in list(repo_map["files"].items())[:80]:
        entry = "- %s（%d 行）：%s" % (
            rel, info["loc"],
            ", ".join("%s:%s" % (d["name"], d["line"]) for d in info["defs"][:8]))
        if used + len(entry) > max_chars * 2:
            break
        lines.append(entry)
        used += len(entry) + 1
    return "\n".join(lines)


# ---------------------------------------------------------------- 任务关键词
# 动机（round-19）：材料里的「文件与顶层定义」按路径字母序截断，django 这类
# 仓库里目标文件（django/db/...）永远排在被截断的区段之外——模型只能靠先验
# 知识猜文件。按任务文本的关键词匹配符号/路径，把候选文件顶到材料最前面。

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TOKEN_PATTERNS = (
    re.compile(r"[`'\"]+([^`'\"]+)[`'\"]+"),          # 反引号/引号内代码
    re.compile(r"\b([A-Z][A-Za-z0-9_]*)\b"),          # 首字母大写的标识符
    re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b"),
    re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b"),  # 含下划线
    re.compile(r"\b([a-z]{4,})\b"),                   # 普通小写词（仅路径段匹配）
)


def extract_keywords(text, max_tokens=120):
    """从任务文本抽取候选关键词（按特异性排序：代码片段 > 驼峰 > 点号 > 下划线）。

    只做「抽取」，是否命中由 rank_candidates 判定——抽错的词自然落选。
    每类单独限额，避免某一类刷屏挤掉其他类（round-19 实测：sqlite 标题里的
    小写词「sqlmigrate」只能靠普通小写词这一类命中）。
    """
    tokens = []

    def add(tok):
        tok = (tok or "").strip()
        if len(tok) < 3:
            return
        if tok not in tokens:
            tokens.append(tok)

    for pi, pat in enumerate(_TOKEN_PATTERNS):
        added = 0
        for m in pat.finditer(text or ""):
            body = m.group(1)
            if pi == 0:
                head = _IDENT_RE.match(body.strip())
                if head:
                    add(head.group(0))
            elif pi == 2:
                add(body)
                add(body.rsplit(".", 1)[-1])
            else:
                add(body)
            added += 1
            if added >= 30:
                break
    return tokens[:max_tokens]


def rank_candidates(repo_map, keywords, limit=8, min_score=2):
    """按关键词给候选文件打分排序。

    打分：3=文件里定义了该符号；2=关键词精确等于路径段；1=子串命中（噪声大，
    默认不入榜）。返回 [{file, score, hits, loc}]。
    """
    def_index = {}
    for rel, info in repo_map.get("files", {}).items():
        for d in info.get("defs", []):
            def_index.setdefault(d["name"], set()).add(rel)
    files = repo_map.get("files", {})
    scored = {}
    for kw in keywords:
        if not kw:
            continue
        hit_defs = def_index.get(kw)
        if hit_defs:
            for rel in hit_defs:
                item = scored.setdefault(rel, {"score": 0, "hits": []})
                item["score"] += 3
                item["hits"].append(kw)
            continue
        for rel in files:
            parts = rel.split("/")
            stem = parts[-1]
            suffix = Path(stem).suffix.lower()
            if suffix in EXT_LANG:
                stem = stem[:-len(suffix)]
            if kw in parts or kw == stem:
                item = scored.setdefault(rel, {"score": 0, "hits": []})
                item["score"] += 2
                item["hits"].append(kw)
            elif kw in rel:
                item = scored.setdefault(rel, {"score": 0, "hits": []})
                item["score"] += 1
                item["hits"].append(kw)
    out = []
    for rel, item in scored.items():
        if item["score"] < min_score:
            continue
        out.append({"file": rel, "score": item["score"],
                    "hits": sorted(set(item["hits"]))[:6],
                    "loc": files.get(rel, {}).get("loc", 0)})
    out.sort(key=lambda c: (-c["score"], -len(c["hits"]), c["file"]))
    return out[:limit]


def render_candidates(candidates):
    """候选文件段落（放在材料最前，绕开按字母序的截断）。"""
    if not candidates:
        return ""
    lines = ["## 候选文件（按任务关键词匹配，优先看这些）"]
    for c in candidates:
        lines.append("- %s（%d 行；命中 %s）"
                     % (c["file"], c["loc"], "、".join(c["hits"])))
    lines.append("")
    return "\n".join(lines)


STOPWORDS = {
    "import", "from", "the", "and", "for", "not", "with", "this", "that",
    "returns", "return", "same", "whereas", "does", "doesn", "work", "works",
    "correctly", "given", "upon", "example", "description", "last", "even",
    "changed", "behavior", "now", "true", "false", "add", "adds", "adding",
    "changing", "wrap", "wraps", "outpout", "expect", "expected", "should",
    "would", "could", "must", "have", "has", "are", "was", "were", "been",
    "its", "his", "her", "their", "there", "here", "when", "what", "which",
    "while", "because", "however", "also", "only", "more", "most", "some",
    "such", "each", "both", "into", "than", "then", "them", "they", "your",
}


def scan_candidates(repo, keywords, limit=8, max_files=4000, min_len=4,
                    generic_files=40):
    """按关键词直扫仓库找候选文件（不依赖符号地图的 300 文件上限）。

    动机（round-19 实测）：build_map 只扫前 300 个 .py（django 的
    django/db/...、astropy 的 astropy/modeling/... 全在截断外），靠地图找
    候选文件必然漏（基线实测 0/7）。这里改为按关键词全文扫描 + 路径段匹配。

    打分（定义信号主导，避免通用词/测试文件淹没真目标）：
      定义了该符号（def/class）  +10
      关键词精确命中路径段/文件名  +2
      具体词命中文件内容          +3（命中文件数 > generic_files 视为通用词 → +1）
      测试目录/测试文件           ×0.7（真目标通常在源码侧）
    """
    tokens = sorted({k for k in keywords
                     if k and len(k) >= min_len and k.lower() not in STOPWORDS},
                    key=len, reverse=True)
    if not tokens:
        return []
    pattern = re.compile("|".join(re.escape(t) for t in tokens))
    def_pat = re.compile(
        r"(?:^|\n)\s*(?:(?:export|default|async|public|private|protected|"
        r"static|abstract)\s+)*(?:def|class|function|interface|type|func)\s+"
        r"(\w+)")
    path_tokens = {t for t in tokens if len(t) >= 4}
    scanned = 0
    per_file = {}        # rel -> {token: count}
    per_token_files = {} # token -> 文件数
    for path, rel in _source_files(repo):
        scanned += 1
        if scanned > max_files:
            break
        hits = {}
        # 路径段/文件名命中（内容里可能根本没有这个名字，如 sqlmigrate.py）
        parts = rel.split("/")
        stem = parts[-1]
        suffix = Path(stem).suffix.lower()
        if suffix in EXT_LANG:
            stem = stem[:-len(suffix)]
        for tok in path_tokens:
            if tok in parts or tok == stem:
                hits.setdefault(tok, 0)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pattern.finditer(text):
            tok = m.group(0)
            if tok in tokens:
                hits[tok] = hits.get(tok, 0) + 1
        if not hits:
            continue
        defined = {d.group(1) for d in def_pat.finditer(text)} & set(hits)
        per_file[rel] = {"hits": hits, "defined": defined}
        for tok in hits:
            per_token_files[tok] = per_token_files.get(tok, 0) + 1
    out = []
    for rel, info in per_file.items():
        score = 0
        for tok, count in info["hits"].items():
            if tok in info["defined"]:
                score += 10
                continue
            generic = per_token_files.get(tok, 0) > generic_files
            in_path = count == 0        # 路径段命中（内容里没有）
            if in_path:
                score += 2
            else:
                score += 1 if generic else 3
        if not info["hits"]:
            continue
        name = rel.split("/")[-1]
        if ("/tests/" in rel or rel.startswith("tests/") or "/test_" in rel
                or name.startswith("test_") or ".test." in name
                or ".spec." in name or name.endswith("_test.go")):
            score *= 0.7
        loc = 0
        try:
            loc = len((Path(repo) / rel).read_text(
                encoding="utf-8", errors="replace").splitlines())
        except OSError:
            pass
        out.append({"file": rel, "score": round(score, 2),
                    "hits": sorted(info["hits"])[:6], "loc": loc})
    out.sort(key=lambda c: (-c["score"], -len(c["hits"]), c["file"]))
    return out[:limit]


def merge_candidates(*groups, limit=8):
    """合并多路候选（地图命中 + 全文扫描），按分数去重排序。"""
    merged = {}
    for group in groups:
        for c in group or []:
            cur = merged.get(c["file"])
            if cur is None:
                merged[c["file"]] = {"file": c["file"], "score": c["score"],
                                    "hits": list(c["hits"]), "loc": c["loc"]}
            else:
                cur["score"] += c["score"]
                cur["hits"] = sorted(set(cur["hits"] + c["hits"]))[:6]
    out = sorted(merged.values(),
                 key=lambda c: (-c["score"], -len(c["hits"]), c["file"]))
    return out[:limit]


# ---------------------------------------------------------------- 依赖图排序
# 阶段二 2.1（round-53）：文件级 import 图 + 个性化 PageRank。动机是「目标
# 文件不在关键词命中里，但它的依赖/被依赖方在」——把图上的邻居作为补充候选。
# 默认关（roadmap 要求）：构造样本上不劣于现路径但收益依赖任务形状，暂不
# 改变默认材料；code-task 用 --rank graph 显式开启。
GRAPH_MAX_FILE_BYTES = 512 * 1024


def _package_dotted(root, rel):
    """文件所在包的点分名列表（向上走 __init__.py 链；无包则为空）。"""
    p = Path(rel)
    cur = (Path(root) / p).parent
    names = []
    while (cur / "__init__.py").is_file():
        names.append(cur.name)
        cur = cur.parent
    return list(reversed(names))


def _module_names(root, rel):
    """一个文件可能被 import 的点分名（包名链 + 仓库根相对名兜底）。"""
    p = Path(rel)
    names = set()
    pkg = _package_dotted(root, rel)
    if p.stem == "__init__":
        if pkg:
            names.add(".".join(pkg))
    elif pkg:
        names.add(".".join(pkg + [p.stem]))
    parts = list(p.parent.parts) + ([] if p.stem == "__init__" else [p.stem])
    if parts and parts != ["."]:
        names.add(".".join(parts))
    return names


def build_import_graph(repo, max_files=4000,
                       max_file_bytes=GRAPH_MAX_FILE_BYTES):
    """扫仓库构建文件级 import 图（无向）→ {files, adj, edges, scanned}。

    只取模块顶层 import（函数内 import 罕见且不影响「文件相关性」判断），
    解析失败的文件跳过（不改写、不报错）；`from a.b import c` 同时尝试
    `a.b` 与 `a.b.c` 两种解析，取最长可解析前缀——否则 django 风格的
    `from django.db import models` 只会连到 `django/db/__init__.py`。
    """
    root = Path(repo)
    files = []
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root).parts
        if SKIP_DIRS & set(parts):
            continue
        files.append(path.relative_to(root).as_posix())
        if len(files) >= max_files:
            break
    index = {}
    for rel in files:
        for name in _module_names(root, rel):
            index.setdefault(name, rel)
    adj = {rel: set() for rel in files}
    edges = 0
    for rel in files:
        path = root / rel
        try:
            if path.stat().st_size > max_file_bytes:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8",
                                            errors="replace"))
        except (OSError, SyntaxError, ValueError):
            continue
        pkg = _package_dotted(root, rel)
        imports = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = None
                if node.level:
                    keep = len(pkg) - (node.level - 1)
                    if keep < 0:
                        continue
                    base = ".".join(pkg[:keep])
                target = ".".join(x for x in (base, node.module) if x)
                if target:
                    imports.append(target)
                for alias in node.names[:10]:
                    if target:
                        imports.append("%s.%s" % (target, alias.name))
        for mod in imports:
            hit = None
            parts = mod.split(".")
            for i in range(len(parts), 0, -1):
                cand = ".".join(parts[:i])
                if cand in index:
                    hit = index[cand]
                    break
            if hit and hit != rel:
                if hit not in adj[rel]:
                    edges += 1
                adj[rel].add(hit)
                adj[hit].add(rel)
    return {"files": files, "root": str(root),
            "adj": {rel: sorted(nbrs) for rel, nbrs in adj.items()},
            "edges": edges, "scanned": len(files)}


def personalized_pagerank(graph, seeds, alpha=0.85, iters=30, tol=1e-8):
    """个性化 PageRank（seed 分布为重启分布），返回 {file: mass}。"""
    files = graph.get("files") or []
    adj = graph.get("adj") or {}
    seed_set = [s for s in (seeds or []) if s in adj]
    if not files or not seed_set:
        return {}
    share0 = 1.0 / len(seed_set)
    seed = {s: share0 for s in seed_set}
    r = {f: seed.get(f, 0.0) for f in files}
    for _ in range(iters):
        new = {f: (1 - alpha) * seed.get(f, 0.0) for f in files}
        dangling = 0.0
        for f in files:
            nbrs = adj.get(f) or []
            if not nbrs:
                dangling += r[f]
                continue
            per = alpha * r[f] / len(nbrs)
            for nbr in nbrs:
                new[nbr] += per
        if dangling:
            for f in files:
                if f in seed:
                    new[f] += alpha * dangling * seed[f]
        diff = sum(abs(new[f] - r[f]) for f in files)
        r = new
        if diff < tol:
            break
    return r


def graph_rank(graph, candidates, keywords=None, limit=6, score_scale=6.0,
               test_penalty=0.7, min_ratio=0.02):
    """按图传播质量补充候选文件 → [{file, score, hits:["图传播"], loc}]。

    种子 = 现有候选文件 + 路径段精确命中关键词的文件（后者让「扫描零命中但
    路径里有线索」的仓库仍有权重扩散的起点）。已候选文件不重复返回（它们
    已有自己的关键词分数）；测试文件乘惩罚系数，避免测试目录淹没源码。
    """
    seeds = {c["file"] for c in (candidates or [])
             if c.get("file") in graph.get("adj", {})}
    files = graph.get("files") or []
    parts_cache = {rel: rel.split("/") for rel in files}
    stems = {rel: (parts_cache[rel][-1][:-3]
                   if parts_cache[rel][-1].endswith(".py")
                   else parts_cache[rel][-1]) for rel in files}
    for kw in (keywords or []):
        if not kw:
            continue
        matched = [rel for rel in files
                   if kw == stems[rel] or kw in parts_cache[rel]]
        # 目录级泛词（如任务文本里的仓库名 django）会把半棵树变成种子，
        # PPR 退化成均匀分布——超过阈值的关键词不作为路径种子。
        if len(matched) > 30:
            continue
        seeds.update(matched)
    if not seeds:
        return []
    masses = personalized_pagerank(graph, sorted(seeds))
    if not masses:
        return []
    peak = max(masses.values()) or 1.0
    known = {c["file"] for c in (candidates or [])}
    out = []
    for rel, mass in masses.items():
        if rel in known:
            continue
        ratio = mass / peak
        if ratio < min_ratio:
            continue
        score = score_scale * ratio
        if "/tests/" in rel or rel.startswith("tests/") \
                or rel.split("/")[-1].startswith("test_"):
            score *= test_penalty
        try:
            loc = len((Path(graph.get("root", ".")) / rel).read_text(
                encoding="utf-8", errors="replace").splitlines())
        except OSError:
            loc = 0
        out.append({"file": rel, "score": round(score, 2),
                    "hits": ["图传播"], "loc": loc})
    out.sort(key=lambda c: (-c["score"], c["file"]))
    return out[:limit]


# ---------------------------------------------------------------- 语法校验
# 阶段二 2.5（round-53）：编辑后做语法树级最小校验。ast.parse 也能判语法，
# 但 tree-sitter 是仓库地图已有的依赖，且对「局部破坏」给出精确行号；这里
# 只判根节点 has_error，不做风格/类型检查（那会变成另一套评审器）。
_TS_PARSERS = {}


def _parser_for(lang):
    """按语言名取（并缓存）tree-sitter 解析器。"""
    parser = _TS_PARSERS.get(lang)
    if parser is None:
        parser = _TS_PARSERS[lang] = Parser(_GRAMMARS[lang])
    return parser


def _py_parser():
    """Python 解析器（兼容旧引用；新代码用 _parser_for(lang)）。"""
    return _parser_for("python")


def _first_error_node(node):
    if node.type == "ERROR" or getattr(node, "is_missing", False):
        return node
    for child in node.children:
        if child.has_error:
            hit = _first_error_node(child)
            if hit is not None:
                return hit
    return None


def syntax_issues(worktree, rel_paths):
    """编辑过的源码文件语法树校验 → [{code:"syntax_error", detail}]。

    支持 .py/.ts/.tsx/.js/.jsx/.mjs/.cjs/.go（round-59 起），其余扩展名跳过。
    双网仅 Python：tree-sitter 抓结构破损（括号/引号/缩进，报精确行），再用
    `ast.parse` 补一遍——round-53 变异语料实测 tree-sitter 的 ERROR 恢复
    会放过「多个空格缩进」与「缩进不齐的截断 def」两类（10 个坏样本只抓
    8 个），而 CPython 解析器对它们必报 SyntaxError。TS/Go 只有 tree-sitter
    一张网（离线环境没有 tsc/go vet 的保证金），语义级错误交给测试引擎兜底。
    文件不存在或读失败跳过（由补丁校验的 file_missing 负责）。返回列表便于
    与 _validate_patch 的 issues 合并。

    版本口径：ast.parse 用的是编码循环所在解释器（.venv 3.12）；被审仓库
    若要求更老的 Python，个别老语法（如以 async 作标识符）会误报——只查
    **本次编辑过的文件**，影响面限于模型刚改的内容。
    """
    issues = []
    for rel in rel_paths or []:
        rel = str(rel).replace("\\", "/")
        lang = _lang_for(rel)
        if lang is None:
            continue
        path = Path(worktree) / rel
        try:
            data = path.read_bytes()
        except OSError:
            continue
        root = _parser_for(lang).parse(data).root_node
        if root.has_error:
            hit = _first_error_node(root)
            line = (hit.start_point[0] + 1) if hit is not None else 1
            issues.append({"code": "syntax_error",
                           "detail": "%s:%d 语法树含 ERROR 节点（括号/引号/缩进"
                                     "未闭合，或 REPLACE 写坏了结构）" % (rel, line)})
            continue
        if lang != "python":
            continue
        try:
            ast.parse(data)
        except SyntaxError as exc:
            issues.append({"code": "syntax_error",
                           "detail": "%s:%d CPython 解析失败：%s"
                                     % (rel, exc.lineno or 1,
                                        (exc.msg or "SyntaxError")[:120])})
        except ValueError as exc:  # 空字节等
            issues.append({"code": "syntax_error",
                           "detail": "%s:0 CPython 解析失败：%s"
                                     % (rel, str(exc)[:120])})
    return issues


def extract_window(text, keywords, max_chars=3000, context=80):
    """按关键词提取文件窗口（命中行 ±context 行），并附模块 docstring。

    动机（round-19）：read 动作此前只给文件头 3000 字，目标函数常常在
    3000 字之外（django 的 RenameModel 在 ~320 行、sympy 的 bell 类在
    ~320 行），模型看不到要改的代码，也看不到 docstring 里的语义约束。

    定位策略：**优先取定义点**（class/def <关键词>），退而取首次提及——
    首次提及常在别处的注释/引用里（round-19 实测：django models.py 里
    "RenameModel" 首次出现在 129 行，类定义在 289 行，按提及取窗会切掉
    真正的目标代码）。
    """
    lines = (text or "").splitlines()
    if not lines:
        return ""
    head = []
    for line in lines:
        if re.match(r"^(def |class |@)", line):
            break
        head.append(line)
    doc = "\n".join(head).strip()
    idx = None
    for kw in keywords:
        if not kw or len(kw) < 3:
            continue
        # 1) 定义点优先
        defpat = re.compile(r"^\s*(?:class|def)\s+%s\b" % re.escape(kw))
        for i, line in enumerate(lines):
            if defpat.match(line):
                idx = i
                break
        if idx is not None:
            break
        # 2) 退而求其次：首次提及
        for i, line in enumerate(lines):
            if kw in line:
                idx = i
                break
        if idx is not None:
            break
    if idx is None:
        return text[:max_chars]
    start = max(0, idx - 3)
    end = min(len(lines), idx + context * 2)
    parts = []
    if doc and start > 0:
        parts.append("（模块 docstring）\n%s" % doc[:600])
    parts.append("（行 %d-%d）\n%s" % (start + 1, end, "\n".join(lines[start:end])))
    return "\n".join(parts)[:max_chars]


SPAN_MAX_LINES = 400


def slice_lines(text, start, end=None):
    """按 1 基闭区间行号取切片，逐行带行号前缀（模型可据此再取相邻段）。

    round-69 结构改造（open 坑：read 取窗恒取文件头，深文件段不可达）：
    `path:start-end` / `path:start-`（到 EOF）直接取指定行区间；单段上限
    SPAN_MAX_LINES 行，超出截断并标注。start/end 非法（NaN、0、负数、
    start>end）按整段可用范围钳制，不抛错。
    """
    try:
        start = int(start)
        end = int(end) if end is not None else None
    except (TypeError, ValueError):
        return ""
    lines = (text or "").splitlines()
    total = len(lines)
    if total == 0:
        return ""
    start = max(1, min(start, total))
    if end is None or end < start:
        end = total
    end = min(max(start, end), total)
    truncated = end - start + 1 > SPAN_MAX_LINES
    if truncated:
        end = start + SPAN_MAX_LINES - 1
    body = "\n".join("%5d| %s" % (i, lines[i - 1])
                     for i in range(start, end + 1))
    if truncated:
        body += "\n（截断：单段上限 %d 行，可用 read 路径:%d- 续取）" % (
            SPAN_MAX_LINES, end + 1)
    return body


def extract_symbol_span(text, symbol):
    """按符号锚定取窗：class/def <symbol> 定义行起，到同级或更低缩进为止。

    round-69 结构改造：词法缩进法（Python 语义；无 tree-sitter 依赖），
    逐行带行号前缀，单段上限 SPAN_MAX_LINES 行。找不到定义返回空串。
    """
    lines = (text or "").splitlines()
    pat = re.compile(r"^(\s*)(?:async\s+)?(?:class|def)\s+%s\b"
                     % re.escape(symbol or ""))
    start = None
    indent = ""
    for i, line in enumerate(lines):
        m = pat.match(line)
        if m:
            start = i
            indent = m.group(1)
            break
    if start is None:
        return ""
    depth = len(indent) - len(indent.lstrip())
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if not line.strip():
            continue  # 空行属于符号体内
        cur = len(line) - len(line.lstrip())
        if cur <= depth:
            end = j
            break
    clipped = end - start > SPAN_MAX_LINES
    end = min(end, start + SPAN_MAX_LINES)
    body = "\n".join("%5d| %s" % (i + 1, lines[i])
                     for i in range(start, end))
    if clipped:
        body += "\n（截断：单段上限 %d 行）" % SPAN_MAX_LINES
    return body


def _stem_matches(stem, file_stem):
    """测试文件名与目标模块名的命中判定（test_x / x_test / tests 同名）。"""
    return (stem in file_stem
            or file_stem.replace("test_", "").replace("_test", "") == stem)


def module_ref(repo, rel_path):
    """模块的**引用形状**：(点分路径, 所在包点分路径, 模块名)；无模块名时 None。

    为什么要向上走 `__init__.py` 链而不是拿仓库根当包根：matplotlib 的包在 `lib/`
    下，按仓库根拼出来是 `lib.matplotlib.axes`，而测试里写的是 `matplotlib.axes`
    （round-30 真实仓库实测的取样域就是靠这一点才没被样本形状骗过去）。走不通
    （目录树里没有 `__init__.py`，如小仓库/合成语料）就退回「仓库根即包根」，
    保证旧形状仍可判。
    """
    p = Path(rel_path)
    stem = p.stem
    if not stem or stem.startswith("__"):
        return None
    root = Path(repo)
    pkg = []
    cur = (root / p).parent
    while (cur / "__init__.py").is_file():
        pkg.append(cur.name)
        cur = cur.parent
    parts = [s for s in p.parts[:-1] if s not in (".", root.name)]
    head = ".".join(reversed(pkg)) if pkg else ".".join(parts)
    if not head:
        return None
    return "%s.%s" % (head, stem), head, stem


def _root_tests_dir(repo):
    """仓库的测试根：优先根下 tests/，其次最浅的 <pkg>/tests/。

    django 的布局是 `tests/<app>/test_*.py`，模块路径（django/db/migrations/
    operations/base.py）与测试目录不同名——只按文件名命中在这里一律取不到
    （round-28 检查单第 6 项）。
    """
    root = Path(repo)
    if (root / "tests").is_dir():
        return root / "tests"
    best = None
    for d in sorted(root.rglob("tests")):
        if not d.is_dir() or (SKIP_DIRS & set(d.parts)):
            continue
        depth = len(d.relative_to(root).parts)
        if best is None or depth < len(best.relative_to(root).parts):
            best = d
    return best


def _snippet(path, root, max_chars, marker=""):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "（邻近测试 %s%s）\n%s" % (path.relative_to(root).as_posix(), marker,
                                     text[:max_chars])


def find_sibling_test_paths(repo, rel_path, limit=2, content_fallback=True):
    """三路取邻近测试的**路径**，返回 [(Path, marker)]（不读片段）。

    与 `find_sibling_tests` 共用同一套取舍（A 名字 / B 路径段 / C 内容兜底，
    详见后者 docstring）。单独暴露路径版是为了让编码循环的「测试子集」复用
    同一口径，而不是再写一份映射。`content_fallback=False` 跳过 C 路：C 要
    扫 tests/ 下的文件，编码循环每轮都做太贵，调用方以「全量回退」兜底。
    """
    p = Path(rel_path)
    stem = p.stem
    if stem.startswith("__"):
        return []
    root = Path(repo)
    segments = [s for s in p.parent.parts if s not in (".", root.name)]
    out, seen = [], set()

    def _push(cand, marker=""):
        key = cand.as_posix()
        if key in seen or not cand.is_file():
            return False
        seen.add(key)
        out.append((cand, marker))
        return len(out) >= limit

    # A：模块同级 tests/（sympy/astropy 包内布局）与仓库根 tests/。
    #    这里**先收全候选再判具不具体**：同名测试散落在 ≥2 个测试目录，说明模块名
    #    是泛化名（base / utils / test 这类词根），命中不代表「这个模块的测试」。
    #    round-29 实测（scripts/sibling-test-bench.py）：让 A 直接返回时，django 形
    #    用例交回来的是 tests/migrations/test_base.py + tests/urlpatterns/test_base.py
    #    两个无关文件，真值 tests/migrations/test_operations.py 连出场机会都没有——
    #    「前一路命中即停」在泛化名上等于「用噪声把后面两路短路」。
    sibling_tests = root / p.parent / "tests"
    a_hits, a_specific = [], False
    for d in (sibling_tests, root / "tests"):
        if not d.is_dir():
            continue
        found = [t for t in sorted(d.rglob("test_*.py")) if _stem_matches(stem, t.stem)]
        a_hits.extend(found)
        if d == sibling_tests and found:
            a_specific = True   # 包内同级 tests/ 是最具体的证据，不再看根 tests/
            break

    # A 的命中散落在 ≥2 个测试目录 = 泛化名，不是「这个模块自己的测试」
    a_ambiguous = (not a_specific) and len({t.parent for t in a_hits}) >= 2

    # B：路径段 ↔ tests/<段>/（django：…/migrations/operations/base.py
    #    → tests/migrations/test_operations.py）
    rtests = _root_tests_dir(root)
    b_hits = []
    if rtests is not None:
        matched = [s for s in segments if (rtests / s).is_dir()]
        if matched:
            app_dir = rtests / matched[-1]
            others = [s for s in segments if s != matched[-1]]
            scored = []
            for t in sorted(app_dir.rglob("test_*.py")):
                name_score = 3 if _stem_matches(stem, t.stem) else 0
                seg_score = sum(1 for s in others if s in t.stem)
                if not (name_score or seg_score):
                    continue
                # 泛化名下，「同 app 目录里的同名测试」不是证据（段名才是）——
                # 否则 A 让位给 B，B 又把同一批噪声捞回来。
                if a_ambiguous and not seg_score:
                    continue
                scored.append((seg_score, name_score, t))
            scored.sort(key=lambda x: (-x[0], -x[1], x[2].as_posix()))
            b_hits = [t for _seg, _name, t in scored]

    def _emit_all(paths, marker=""):
        for cand in paths:
            if _push(cand, marker):
                return True
        return False

    # 取舍次序：具体名字命中 → 目录段映射 → 内容兜底 → 泛化名（必须带标注）
    if a_hits and not a_ambiguous:
        if _emit_all(a_hits):
            return out
    elif b_hits:
        if _emit_all(b_hits):
            return out

    # C：内容兜底——tests/ 里**以引用形状**提到该模块的测试文件（有界）。
    #    round-30 真实仓库实测（`scripts/sibling-test-realbench.py`，3 仓 300 模块，
    #    判据=返回的测试是否真的引用了这个模块）：旧口径按裸词 `\b<stem>\b` 检索，
    #    C 路 132 条返回里只有 46 条是真引用（0.348），噪声 86 条的主要形状是
    #    「别的模块里的同名变量/函数」与「同名不同模块的 import」。改成检索
    #    点分路径 / `from <包> import <模块>` ——**用判真的口径去检索**，
    #    裸词不再有机会伪装成该模块的测试。
    if content_fallback and not out and rtests is not None:
        ref = module_ref(root, rel_path)
        pats = []
        if ref:
            dotted, head, stem_ = ref
            pats.append(re.compile(re.escape(dotted)))
            pats.append(re.compile(r"^\s*from\s+%s\s+import\s[^\n]*\b%s\b"
                                   % (re.escape(head), re.escape(stem_)), re.MULTILINE))
        else:
            pats.append(re.compile(r"\b%s\b" % re.escape(stem)))
        scanned = 0
        for t in sorted(rtests.rglob("test_*.py")):
            if scanned >= 1200 or len(out) >= limit:
                break
            scanned += 1
            try:
                text = t.read_text(encoding="utf-8", errors="replace")[:20000]
            except OSError:
                continue
            if any(pat.search(text) for pat in pats):
                seen.add(t.as_posix())
                out.append((t, "，按内容命中"))
        if out:
            return out

    # 三路都给不出具体证据时返回空（无证据不编）。round-33 前曾有「泛化名兜底」
    # （a_hits 带「按名字泛化命中」标注入材料），真实语料定案后移除：300 模块
    # 抽样里该兜底 36 次出场 0 次判真——带标注的纯噪声仍占 limit 槽位、仍会被
    # 模型读进上下文，不如无材料（scripts/sibling-test-realbench.py 的
    # A_GENERIC_RULE，判定先于数字写死）。
    return out


def find_sibling_tests(repo, rel_path, limit=2, max_chars=1500):
    """找目标模块的邻近测试文件，返回片段（供材料附在代码窗口后）。

    动机（round-20）：issue 文本常不含「非法入参该抛错还是该求值」这类边界
    语义，而这些语义往往写在模块自己的测试里——把测试片段一并给模型，能
    少几轮「靠 harness 反馈逐条补语义」的返工。

    三路取法与取舍全部在 `find_sibling_test_paths`（A 名字 / B 路径段 /
    C 内容引用）；这里只负责把选中的文件读成片段。
    """
    root = Path(repo)
    snippets = []
    for cand, marker in find_sibling_test_paths(repo, rel_path, limit=limit):
        snippet = _snippet(cand, root, max_chars, marker)
        if snippet:
            snippets.append(snippet)
    return "\n".join(snippets)


def main():
    parser = argparse.ArgumentParser(description="仓库地图（tree-sitter）")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--max-chars", dest="max_chars", type=int, default=6000)
    parser.add_argument("--material", action="store_true",
                        help="输出 LLM 材料文本而非 JSON")
    parser.add_argument("--task-text", dest="task_text", default="",
                        help="任务文本（给出时按关键词出候选文件）")
    parser.add_argument("--rank", choices=("refs", "graph"), default="refs",
                        help="候选排序：refs=关键词打分（默认）；graph=叠加 "
                             "import 图个性化 PageRank 补充邻居文件")
    argv = parser.parse_args()
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库不存在: %s" % repo})
        return 2
    repo_map = build_map(repo)
    candidates, rank_info = None, None
    if argv.task_text:
        keywords = extract_keywords(argv.task_text)
        candidates = merge_candidates(rank_candidates(repo_map, keywords),
                                      scan_candidates(repo, keywords))
        rank_info = {"mode": argv.rank, "candidates": len(candidates)}
        if argv.rank == "graph":
            graph = build_import_graph(repo)
            extra = graph_rank(graph, candidates, keywords)
            candidates = merge_candidates(candidates, extra)
            rank_info.update({"graph_files": len(graph["files"]),
                              "graph_edges": graph["edges"],
                              "graph_candidates": len(extra),
                              "candidates": len(candidates)})
    if argv.material:
        sys.stdout.reconfigure(encoding="utf-8")
        text = render_material(repo_map, argv.max_chars)
        if candidates:
            text = render_candidates(candidates) + text
        print(text)
        return 0
    out = {"ok": True, "scanned": repo_map["scanned"],
           "files": len(repo_map["files"]),
           "symbols": len(repo_map["ranked_symbols"]),
           "repo_map": repo_map}
    if candidates is not None:
        out["candidates"] = candidates
        out["rank"] = rank_info
    _emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
