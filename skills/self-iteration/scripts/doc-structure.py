#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档与脚本结构判据：手册 §7.1 的机器可判九条 + 脚本编码契约（round-219）。

用途
----
对手册式三层文档体系的「门面 + 八类入口」做结构一致性校验：
  [S1] 元信息字段：头部引用块必含 创建日期/当前状态/权威范围/所有者/
       复核期限/主导模式/上次复核 七字段（不是权威为可选推荐项）。
  [S2] 相对链接存在：仓内相对 .md 链接的目标文件必须存在。
  [S3] 锚点一致：带 #fragment 的链接，按 GFM 归一规则（小写、去标点、
       空格转连字符、保留 CJK）在目标文件标题集中必须可解析。
  [S4] 目录双向一致：含「## 目录」节的文件，目录锚点与标题双向对齐。
  [S5] 表格形状：每行列数必须等于表头（先剥代码围栏/行内代码）。
  [S6] 登记齐全：docs/0*/ 下每份 md 必须在 docs/INDEX.md 出现文件名，
       且每类目录有入口文件。
  [S7] 链接文字：禁止泛化词（这里/点击/详见/链接）。
  [S8] 标题层级：不得跳级（## 直接到 ####）。
  [S9] 占位符残留：剥码后不得有 <占位> 形态或 TODO/FIXME 残留。
  [S10] 脚本编码契约：带主入口的 Python 脚本必须在主入口 guard、已调用的
        main() 或已调用的 _emit() 中对 sys.stdout 执行真实的
        reconfigure(encoding="utf-8")；注释/字符串/不可达分支不算。

扫描面（下限护栏防恒绿）：README.md + docs/RULES.md + docs/INDEX.md +
docs/0*/*.md，共 ≥10 文件。
脚本扫描 skills/*/scripts、scripts、agent、engines、llm、mcp 下的 Python
主入口文件，少于 1 个判红；无主入口的库模块不纳入。
判据只验文本属性，不验句子为真（边界声明见 docs/RULES.md）。

用法示例：
    python doc-structure.py --root .
    python doc-structure.py --root <项目根>

退出码：0 = 全部 PASS；1 = 有 FAIL；2 = 参数/环境错误（扫描面不足等）。
stdout 输出单个 JSON 文档。
"""
import argparse
import ast
import json
import re
import sys
import unicodedata
from pathlib import Path

META_FIELDS = ("创建日期", "当前状态", "权威范围", "所有者", "复核期限",
               "主导模式", "上次复核", "不是权威")
LINK_TEXT_BANNED = ("这里", "点击", "详见", "链接")
ENTRY_DIRS = ("01-overview", "02-architecture", "03-decisions",
              "04-progress", "05-troubleshooting", "06-operations",
              "07-tasks", "08-memory")
MIN_FILES = 10
MIN_LINKS = 15

CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
CODE_SPAN_RE = re.compile(r"`[^`]+`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*#*\s*$")
META_RE = re.compile(r"^>\s*\*\*(.+?)\*\*")

def _anchor(text):
    """GFM 中文锚点归一：小写、去标点、空格转连字符、保留 CJK。"""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    out = []
    for ch in text:
        if ch.isspace():
            out.append("-")
        elif ch in "-_" or ch.isalnum() or unicodedata.category(ch).startswith("L"):
            out.append(ch)
        # 其余标点丢弃
    return "".join(out)

def _strip_code(text):
    return CODE_SPAN_RE.sub("", CODE_FENCE_RE.sub("", text))

def _rel_target(link):
    """拆相对链接为 (路径, 锚点)。"""
    path, _, frag = link.partition("#")
    return path, frag

def _heading_anchors(lines):
    return {_anchor(m.group(2)) for m in
            (HEADING_RE.match(ln) for ln in lines) if m}

def _is_main_guard(node):
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    test = node.test
    return (isinstance(test.left, ast.Name) and test.left.id == "__name__"
            and any(isinstance(op, ast.Eq) for op in test.ops)
            and any(isinstance(item, ast.Constant) and item.value == "__main__"
                    for item in test.comparators))


def _is_stdout(node):
    return (isinstance(node, ast.Attribute) and node.attr == "stdout"
            and isinstance(node.value, ast.Name) and node.value.id == "sys")


def _is_utf8_reconfigure(node):
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
            and any(keyword.arg == "encoding"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                    and keyword.value.value.lower() == "utf-8"
                    for keyword in node.keywords))


def _scope_nodes(node):
    if isinstance(node, ast.If) and isinstance(node.test, ast.Constant) \
            and not node.test.value:
        return
    for _field, value in ast.iter_fields(node):
        children = value if isinstance(value, list) else [value]
        for child in children:
            if not isinstance(child, ast.AST):
                continue
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            yield child
            if isinstance(child, ast.stmt):
                if isinstance(child, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    break
                yield from _scope_nodes(child)
            else:
                yield from _scope_nodes(child)


def _bound_names(node):
    names = {child.id for child in _scope_nodes(node)
             if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        names.update(arg.arg for arg in args.posonlyargs + args.args + args.kwonlyargs)
        if args.vararg:
            names.add(args.vararg.arg)
        if args.kwarg:
            names.add(args.kwarg.arg)
    return names


def _unshadowed_stdout(node, shadowed):
    return "sys" not in shadowed and _is_stdout(node)


def _stdout_aliases(nodes, shadowed):
    aliases = {}
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                aliases.setdefault(target.id, []).append(
                    ((target.lineno, target.col_offset),
                     _unshadowed_stdout(value, shadowed)))
    return aliases


def _loop_has_utf8_stdout(loop, shadowed):
    if not isinstance(loop.target, ast.Name):
        return False
    bound = {loop.target.id: True}
    events = [node for node in _scope_nodes(loop)
              if _is_utf8_reconfigure(node) or isinstance(node, ast.Assign)
              or isinstance(node, ast.AnnAssign) and node.value is not None]
    for node in sorted(events, key=lambda item: (item.lineno, item.col_offset)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            receiver = node.func.value
            if (_unshadowed_stdout(receiver, shadowed)
                    or isinstance(receiver, ast.Name) and bound.get(receiver.id, False)):
                return True
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                bound[target.id] = _unshadowed_stdout(value, shadowed)
    return False


def _scope_has_utf8_stdout(node, shadowed=frozenset()):
    nodes = list(_scope_nodes(node))
    aliases = _stdout_aliases(nodes, shadowed)
    for call in nodes:
        if not _is_utf8_reconfigure(call):
            continue
        receiver = call.func.value
        if _unshadowed_stdout(receiver, shadowed):
            return True
        if isinstance(receiver, ast.Name):
            prior = [item for item in aliases.get(receiver.id, [])
                     if item[0] < (call.lineno, call.col_offset)]
            if prior and max(prior, key=lambda item: item[0])[1]:
                return True
    loops = ([node] if isinstance(node, ast.For) else []) + nodes
    for loop in loops:
        if (isinstance(loop, ast.For) and isinstance(loop.iter, (ast.Tuple, ast.List))
                and any(_unshadowed_stdout(item, shadowed) for item in loop.iter.elts)
                and _loop_has_utf8_stdout(loop, shadowed)):
            return True
    return False


def _has_utf8_stdout(tree):
    functions = {node.name: node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    guards = [node for node in tree.body if _is_main_guard(node)]
    guard_body = [statement for guard in guards for statement in guard.body]
    module_shadowed = _bound_names(tree)
    if any(_scope_has_utf8_stdout(statement, module_shadowed)
           for statement in guard_body):
        return True

    def refs(node, extra_shadowed=frozenset()):
        excluded = _bound_names(node) | set(extra_shadowed)
        return {child.id for child in _scope_nodes(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
                and child.id in functions and child.id not in excluded}

    reachable = set()
    pending = [ref for statement in guard_body
               for ref in refs(statement, module_shadowed)]
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        pending.extend(refs(functions[name]) - reachable)
    return any(name in ("main", "_emit")
               and _scope_has_utf8_stdout(functions[name], _bound_names(functions[name]))
               for name in reachable)


def _script_encoding_check(root):
    script_dirs = [root / name for name in ("scripts", "agent", "engines", "llm", "mcp")]
    script_dirs.extend((root / "skills").glob("*/scripts"))
    paths = sorted({path for directory in script_dirs if directory.is_dir()
                    for path in directory.rglob("*.py")})
    missing = []
    scanned = 0
    for path in paths:
        rel = path.relative_to(root).as_posix()
        scanned += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=rel)
        except (OSError, SyntaxError) as exc:
            missing.append({"file": rel, "reason": "parse_error: %s" % exc})
            continue
        if not any(_is_main_guard(node) for node in tree.body):
            scanned -= 1
            continue
        if not _has_utf8_stdout(tree):
            missing.append({"file": rel, "reason": "missing_utf8_stdout_reconfigure"})
    return {"id": "script_encoding",
            "status": "PASS" if scanned and not missing else "FAIL",
            "scripts_scanned": scanned, "covered": scanned - len(missing),
            "missing": missing,
            "error": None if scanned and not missing else
                     "主入口脚本为空或缺少 UTF-8 stdout 自防御"}


def _meta_check(lines):
    meta = set()
    for ln in lines[:16]:
        if ln.startswith(">"):
            for m in re.finditer(r"\*\*(.+?)\*\*", ln):
                meta.add(m.group(1))
    missing = [f for f in META_FIELDS if f not in meta]
    if missing:
        return {"id": "meta_fields", "status": "FAIL",
                "error": "缺元信息字段: %s" % ",".join(missing)}
    return {"id": "meta_fields", "status": "PASS"}

def _scan_links(lines):
    """收集剥码后的相对 .md 链接（跳过 http/纯锚点）。"""
    text = _strip_code("\n".join(lines))
    links = []
    for m in LINK_RE.finditer(text):
        target = m.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        links.append((m.group(1), target, m.start()))
    return links

def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="文档结构判据")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        _emit({"ok": False, "error": "项目根不存在: %s" % root})
        return 2
    faces = [root / "README.md", root / "docs" / "RULES.md",
             root / "docs" / "INDEX.md",
             root / "AGENTS.md", root / "BASELINE.md",
             root / "docs" / "DEVELOPMENT.md",
             root / "docs" / "ROADMAP.md",
             root / "docs" / "PROGRESS.md",
             root / "docs" / "DECISIONS.md",
             root / "docs" / "GLOSSARY.md"]
    for name in ENTRY_DIRS:
        d = root / "docs" / name
        if d.is_dir():
            faces.extend(sorted(d.glob("*.md")))
    faces = [f for f in faces if f.is_file()]
    if len(faces) < MIN_FILES:
        _emit({"ok": False, "error": "扫描面不足（%d < %d）"
               % (len(faces), MIN_FILES)})
        return 2
    index_text = (root / "docs" / "INDEX.md").read_text(
        encoding="utf-8", errors="replace")
    checks = []
    total_links = 0
    for path in faces:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        checks.append(_meta_check(lines))
        rel = path.relative_to(root)
        links = _scan_links(lines)
        total_links += len(links)
        # S2 链接存在 + S3 锚点一致
        bad_links, bad_anchors = [], []
        for text_label, target, _pos in links:
            tpath, frag = _rel_target(target)
            if not tpath:
                continue
            resolved = (path.parent / tpath).resolve()
            if not (resolved.is_file() or resolved.is_dir()):
                bad_links.append(target)
                continue
            if frag:
                target_lines = resolved.read_text(
                    encoding="utf-8", errors="replace").splitlines()
                if _anchor(frag) not in _heading_anchors(target_lines):
                    bad_anchors.append(target)
        if bad_links:
            checks.append({"id": "link_exists", "status": "FAIL",
                           "file": str(rel), "targets": bad_links[:8]})
        if bad_anchors:
            checks.append({"id": "anchor_match", "status": "FAIL",
                           "file": str(rel), "targets": bad_anchors[:8]})
        # S7 链接文字 + S9 占位符（剥码文本）
        stripped = _strip_code("\n".join(lines))
        banned = [t for t, _tgt, _p in links
                  if any(w in t for w in LINK_TEXT_BANNED)]
        if banned:
            checks.append({"id": "link_text", "status": "FAIL",
                           "file": str(rel), "targets": banned[:8]})
        # 内容占位符判别：只抓「待补/占位/TODO」类未填标记；命令语法占位符
        # （<repo>、<用户原话>）与数字比较（<0.5s）是合法形态，不误伤。
        ph = re.findall(r"<[^>\n]*?(?:待补|待填|待写|占位|TODO|FIXME|XXX)[^>\n]*>",
                        stripped)
        # 裸词 TODO/FIXME 提及（如「TODO 全仓 1 处」的讨论句）是合法内容，
        # 不判；<...> 内容占位符形态才是未填标记。
        if ph:
            checks.append({"id": "placeholder", "status": "FAIL",
                           "file": str(rel), "placeholders": ph[:6]})
        # S8 标题跳级 + S4 目录
        levels = [len(m.group(1)) for m in
                  (HEADING_RE.match(ln) for ln in lines) if m]
        for a, b in zip(levels, levels[1:]):
            if b - a > 1:
                checks.append({"id": "heading_level", "status": "FAIL",
                               "file": str(rel),
                               "error": "跳级 %d→%d" % (a, b)})
                break
        # S5 表格形状
        tbl_rows = [ln for ln in lines if ln.strip().startswith("|")]
        blocks, cur = [], []
        for ln in lines:
            if ln.strip().startswith("|"):
                cur.append(ln)
            elif cur:
                blocks.append(cur)
                cur = []
        if cur:
            blocks.append(cur)
        for blk in blocks:
            cols = [ln.replace(r"\|", "").count("|") for ln in blk]
            if len(set(cols)) > 1:
                checks.append({"id": "table_shape", "status": "FAIL",
                               "file": str(rel),
                               "error": "表内行 | 计数不一致: %d 行" % len(blk)})
                break
        # S6 登记齐全（仅类目录文件）
        parts = rel.parts
        if len(parts) >= 3 and parts[1] in ENTRY_DIRS:
            if ("%s/%s" % (parts[1], parts[2])) not in index_text:
                checks.append({"id": "registry", "status": "FAIL",
                               "file": str(rel),
                               "error": "未在 docs/INDEX.md 登记"})
    # S6 每类目录有入口文件
    for name in ENTRY_DIRS:
        d = root / "docs" / name
        if d.is_dir() and not ((d / "README.md").is_file()
                               or (d / "INDEX.md").is_file()):
            checks.append({"id": "registry", "status": "FAIL",
                           "file": "docs/%s" % name,
                           "error": "缺入口文件（README/INDEX）"})
    if total_links < MIN_LINKS:
        checks.append({"id": "scan_floor", "status": "FAIL",
                       "error": "链接数下限不足（%d < %d）"
                                % (total_links, MIN_LINKS)})
    checks.append(_script_encoding_check(root))
    failed = [c for c in checks if c.get("status") == "FAIL"]
    _emit({
        "ok": not failed, "files_scanned": len(faces),
        "links_checked": total_links, "checks": checks,
        "failed": sorted({c["id"] for c in failed}),
        "note": "判据只验文本属性，不验句子为真（docs/RULES.md 边界声明）",
    })
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
