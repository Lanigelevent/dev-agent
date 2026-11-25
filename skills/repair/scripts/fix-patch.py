#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁生成：把修复工单批准的发现转成 unified diff 补丁（不写被审仓库）。

修复团队只按审核人签发的工单干活：唯一输入是 --order 指向的
work-order.json（闸 1 产物），写盘范围仅限 --out 产物目录
（补丁 + fix-manifest.json，manifest 携带 order_id 供闸 2 绑定）。
修复白名单 AUTO_RULES（与 fix-plan.py 的 FIXABLE_RULES 成对维护）：
lang-mutable-default / lang-empty-catch / lang-closure-late-bind /
lang-is-literal-misuse / dang-yaml-load，仅作用于 .py 文件。
同文件多个发现自下而上应用；行内容与发现行对不上时跳过该发现并给 reason。

用法示例：
    py fix-patch.py --order work-order.json --repo <被审仓库> --out <产物目录>

退出码：0=成功（含无可修复项，ok 仍为 true）；2=输入错误或仓库非 git。
"""
import argparse
import ast
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from engines.ruff_adapter import ruff_fix_text, ruff_scan_codes  # noqa: E402 - 引擎层（subprocess 隔离）
from engines.libcst_adapter import libcst_fix_text, libcst_scan_codes  # noqa: E402 - 引擎层（自举子进程到 .venv）
from engines.astgrep_adapter import astgrep_fix_text, astgrep_scan_codes  # noqa: E402 - 引擎层（自举子进程到 .venv）

AUTO_RULES = {
    "lang-mutable-default": "none-sentinel",
    "lang-empty-catch": "narrow-and-log",
    "lang-closure-late-bind": "default-arg-bind",
    "lang-is-literal-misuse": "identity-ops",
    "dang-yaml-load": "safe-load",
}

DEF_LINE_RE = re.compile(r"^(\s*)def\s+\w+\s*\((.*)\)\s*:\s*$")
MUTABLE_RE = re.compile(r"([A-Za-z_]\w*)(?:\s*:\s*[^=]+)?\s*=\s*(\[\]|\{\}|set\(\))")
EXC_PASS_RE = re.compile(r"^(\s*)except\b([^:]*)\s*:\s*pass\s*$")
YAML_RE = re.compile(r"\byaml\.load\s*\(\s*([^(),]+?)\s*\)")
LOG_LINE = 'sys.stderr.write("suppressed exception: %r\\n" % (%s,))'


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.returncode, proc.stdout.strip()


def _strip_eol(line):
    return line.rstrip("\r\n")


def _eol_of(line):
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _transform_mutable_default(line):
    """可变默认参数 -> None 哨兵 + 卫语句；返回替换行列表或 None。"""
    match = DEF_LINE_RE.match(line)
    if not match:
        return None
    indent, params = match.group(1), match.group(2)
    hits = list(MUTABLE_RE.finditer(params))
    if not hits:
        return None
    name_part = line[line.index("def "):].split("(")[0]
    new_params = MUTABLE_RE.sub(lambda m: "%s=None" % m.group(1), params)
    body_indent = indent + "    "
    out = ["%s%s(%s):" % (indent, name_part, new_params)]
    for hit in hits:
        out.append("%sif %s is None:" % (body_indent, hit.group(1)))
        out.append("%s    %s = %s" % (body_indent, hit.group(1), hit.group(2)))
    return out


def _exc_parts(cond):
    """解析 except 条件与别名：返回 (新条件, 别名)。"""
    alias_m = re.search(r"\bas\s+([A-Za-z_]\w*)\s*$", cond)
    if alias_m:
        return cond[:alias_m.start()].strip(), alias_m.group(1)
    return (cond or "Exception"), "exc"


def _transform_empty_catch(lines, idx):
    """空 except -> 收窄 + stderr 记录；返回 (start0, end0, 替换行, 模块) 或 None。

    扫描器两种口径都要接：行扫描命中的「except ...: pass」报在 except 行；
    AST 检查命中的「except 头 + 下一行 pass」报在 pass 行。
    """
    line = _strip_eol(lines[idx])
    m_same = EXC_PASS_RE.match(line)
    if m_same:
        indent = re.match(r"^\s*", line).group(0)
        cond, alias = _exc_parts(m_same.group(2).strip())
        body_indent = indent + "    "
        return (idx, idx + 1,
                ["%sexcept %s as %s:" % (indent, cond, alias),
                 "%s%s" % (body_indent, LOG_LINE.replace("%s", alias))], "sys")
    if _strip_eol(line).strip() == "pass" and idx > 0:
        header = _strip_eol(lines[idx - 1])
        m_block = re.match(r"^(\s*)except\b([^:]*)\s*:\s*$", header)
        if m_block:
            indent = m_block.group(1)
            cond, alias = _exc_parts(m_block.group(2).strip())
            body_indent = indent + "    "
            return (idx - 1, idx + 1,
                    ["%sexcept %s as %s:" % (indent, cond, alias),
                     "%s%s" % (body_indent, LOG_LINE.replace("%s", alias))], "sys")
    return None


def _loop_vars_at(tree, lineno):
    """返回指定行（1 基）lambda 所在 for 循环的循环变量名集合。"""
    result = set()
    if tree is None:
        return result
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        names = {t.id for t in ast.walk(node.target) if isinstance(t, ast.Name)}
        for child in ast.walk(node):
            if isinstance(child, ast.Lambda) and child.lineno == lineno:
                result.update(names)
    return result


def _lambda_expr_boundaries(src):
    """从 lambda 关键字起截出完整表达式文本（到括号失衡或顶层逗号为止）。"""
    depth = 0
    seen_colon = False
    for pos, ch in enumerate(src):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth < 0:
                return src[:pos]
        elif ch == ":" and depth == 0 and not seen_colon:
            seen_colon = True
        elif ch == "," and depth == 0 and seen_colon:
            return src[:pos]
    return src


def _transform_closure_late_bind(lines, idx, tree):
    """闭包延迟绑定 -> 循环变量默认参数绑定；返回替换行或 None。"""
    line = _strip_eol(lines[idx])
    if "lambda" not in line:
        return None
    loop_vars = _loop_vars_at(tree, idx + 1)
    if not loop_vars:
        return None
    src = _lambda_expr_boundaries(line[line.index("lambda"):])
    try:
        lam_ast = ast.parse(src.strip(), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    used = {n.id for n in ast.walk(lam_ast)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    binds = sorted(used & loop_vars)
    if not binds:
        return None
    bind_str = ", ".join("%s=%s" % (v, v) for v in binds)
    return re.sub(r"\blambda\b\s*", "lambda %s, " % bind_str, line, count=1)


def _transform_is_literal(line):
    """==None 改 is None、!=None 改 is not None、is 字面量改 ==；返回新行或 None。"""
    new = re.sub(r"(==|!=)\s*None\b",
                 lambda m: "is None" if m.group(1) == "==" else "is not None",
                 _strip_eol(line))
    new = re.sub(r"\bis\s+(\"[^\"]*\"|'[^']*'|\d+)", r"== \1", new)
    return new if new != _strip_eol(line) else None


def _transform_yaml_load(line):
    """yaml.load 单参单行调用 -> yaml.safe_load；返回新行或 None。"""
    new = YAML_RE.sub(r"yaml.safe_load(\1)", _strip_eol(line))
    return new if new != _strip_eol(line) else None


def _ensure_imports(lines, module):
    if module is None:
        return lines
    if re.search(r"^import\s+%s\b" % module, "".join(lines), re.M):
        return lines
    for i, line in enumerate(lines):
        if re.match(r"^(import|from)\s", _strip_eol(line)):
            return lines[:i] + ["import %s\n" % module] + lines[i:]
    return ["import %s\n" % module] + lines


def _build_file_edits(lines, file_findings, tree):
    """按发现行生成编辑操作；返回 (edits, skipped)。"""
    edits, skipped, taken = [], [], set()
    for finding in file_findings:
        rule_id = finding["rule_id"]
        lineno = finding.get("line")
        try:
            idx = int(lineno) - 1
        except (TypeError, ValueError):
            idx = -1
        if not 0 <= idx < len(lines):
            skipped.append({"rule_id": rule_id, "line": lineno, "reason": "行号越界"})
            continue
        if idx in taken:
            skipped.append({"rule_id": rule_id, "line": lineno,
                            "reason": "同行已有其他修复，避免行冲突跳过"})
            continue
        replacement, module, start0, end0 = None, None, idx, idx + 1
        if rule_id == "lang-mutable-default":
            replacement = _transform_mutable_default(_strip_eol(lines[idx]))
            if replacement is not None:
                replacement = [r + _eol_of(lines[idx]) for r in replacement]
        elif rule_id == "lang-empty-catch":
            span = _transform_empty_catch(lines, idx)
            if span is not None:
                start0, end0, replacement, module = span
                eol = _eol_of(lines[start0])
                replacement = [r + eol for r in replacement]
        elif rule_id == "lang-closure-late-bind":
            replacement = _transform_closure_late_bind(lines, idx, tree)
            if replacement is not None:
                replacement = [replacement + _eol_of(lines[idx])]
        elif rule_id == "lang-is-literal-misuse":
            replacement = _transform_is_literal(lines[idx])
            if replacement is not None:
                replacement = [replacement + _eol_of(lines[idx])]
        elif rule_id == "dang-yaml-load":
            replacement = _transform_yaml_load(lines[idx])
            if replacement is not None:
                replacement = [replacement + _eol_of(lines[idx])]
        if replacement is None:
            skipped.append({"rule_id": rule_id, "line": lineno,
                            "reason": "该行形态与策略不符（多行/结构变化），转人工"})
            continue
        taken.add(idx)
        taken.update(range(start0, end0))
        edits.append((start0, end0, replacement, module))
    return edits, skipped


def _patch_one_file(abs_path, rel, file_findings):
    """生成单文件补丁；返回 (patch_text, skipped) 或 (None, skipped)。

    自研变换先应用；文件含 ruff: 规则时，对变换后文本再跑引擎修复
    （engines/ruff_adapter.ruff_fix_text，subprocess 隔离），产物统一
    a/<rel> b/<rel> LF 补丁。
    """
    raw = abs_path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines(keepends=True)
    if not lines or not lines[-1].endswith("\n"):
        return None, [{"file": rel, "rule_id": "-", "line": None,
                       "reason": "文件末尾无换行符，diff 边界不安全，转人工"}]
    try:
        tree = ast.parse("".join(_strip_eol(l) + "\n" for l in lines))
    except SyntaxError:
        tree = None
    own_items = [f for f in file_findings
                 if not str(f["rule_id"]).startswith(("ruff:", "libcst:", "astgrep:"))]
    ruff_codes = sorted({str(f["rule_id"]).split(":", 1)[1]
                         for f in file_findings
                         if str(f["rule_id"]).startswith("ruff:")})
    libcst_codes = sorted({str(f["rule_id"]).split(":", 1)[1]
                           for f in file_findings
                           if str(f["rule_id"]).startswith("libcst:")})
    astgrep_codes = sorted({str(f["rule_id"]).split(":", 1)[1]
                           for f in file_findings
                           if str(f["rule_id"]).startswith("astgrep:")})
    if len([c for c in (ruff_codes, libcst_codes, astgrep_codes) if c]) > 1:
        # 同文件多引擎：闸五单引擎复扫口径不覆盖，保守转人工
        return None, [{"file": rel, "rule_id": "multi-engine", "line": None,
                       "reason": "同文件同时命中多个引擎，"
                                 "混合变换顺序无契约，转人工"}]
    edits, skipped = _build_file_edits(lines, own_items, tree)
    skipped = [dict(s, file=rel) for s in skipped]
    if not edits and not ruff_codes and not libcst_codes and not astgrep_codes:
        return None, skipped
    new_lines = list(lines)
    for start0, end0, replacement, _module in sorted(edits,
                                                     key=lambda e: e[0],
                                                     reverse=True):
        new_lines[start0:end0] = replacement
    modules = {m for _s, _e, _r, m in edits if m}
    for module in sorted(modules):
        new_lines = _ensure_imports(new_lines, module)
    if ruff_codes:
        fixed = ruff_fix_text("".join(new_lines), ",".join(ruff_codes))
        if fixed is None:
            return None, skipped + [{"file": rel, "rule_id": "ruff:*",
                                     "line": None,
                                     "reason": "ruff 引擎修复失败，转人工"}]
        new_lines = fixed.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
    if libcst_codes:
        fixed = libcst_fix_text("".join(new_lines), ",".join(libcst_codes))
        if fixed is None:
            return None, skipped + [{"file": rel, "rule_id": "libcst:*",
                                     "line": None,
                                     "reason": "libcst 引擎修复失败，转人工"}]
        new_lines = fixed.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
    if astgrep_codes:
        fixed = astgrep_fix_text("".join(new_lines), ",".join(astgrep_codes))
        if fixed is None:
            return None, skipped + [{"file": rel, "rule_id": "astgrep:*",
                                     "line": None,
                                     "reason": "astgrep 引擎修复失败，转人工"}]
        new_lines = fixed.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
    diff = difflib.unified_diff(lines, new_lines,
                                fromfile="a/" + rel, tofile="b/" + rel)
    patch_text = "".join(diff)
    if not patch_text.endswith("\n"):
        patch_text += "\n"
    return patch_text, skipped


def main():
    parser = argparse.ArgumentParser(description="补丁生成（被审仓库只读）")
    parser.add_argument("--order", required=True, help="审核人签发的修复工单 JSON")
    parser.add_argument("--repo", required=True, help="被审仓库根")
    parser.add_argument("--out", required=True, help="补丁产物目录")
    argv = parser.parse_args()
    fp = Path(argv.order)
    repo = Path(argv.repo).resolve()
    out = Path(argv.out)
    if not fp.is_file():
        _emit({"ok": False, "error": "工单文件不存在: %s" % fp})
        return 2
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库目录不存在: %s" % repo})
        return 2
    try:
        order = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "工单 JSON 非法: %s" % exc})
        return 2
    if not isinstance(order, dict) or not order.get("order_id"):
        _emit({"ok": False, "error": "工单需含 order_id 与 approved 清单"})
        return 2
    findings = order.get("approved")
    if not isinstance(findings, list):
        _emit({"ok": False, "error": "工单 approved 需为数组"})
        return 2
    rc, head = _git(repo, ["rev-parse", "HEAD"])
    if rc != 0:
        _emit({"ok": False, "error": "仓库非 git 或无提交: %s" % head[:200]})
        return 2

    by_file, out_of_repo = {}, []
    for item in findings:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id", ""))
        if rule_id not in AUTO_RULES and not rule_id.startswith(
                ("ruff:", "libcst:", "astgrep:")):
            continue
        raw = Path(str(item.get("file", "")))
        if raw.is_absolute():
            try:
                rel = raw.resolve().relative_to(repo).as_posix()
            except ValueError:
                out_of_repo.append({"file": str(item.get("file")), "rule_id": rule_id,
                                    "line": item.get("line"),
                                    "reason": "路径越出仓库根，拒绝处理"})
                continue
        else:
            rel = raw.as_posix()
        ext_ok = (rel.lower().endswith(".py")
                  or (rule_id.startswith("astgrep:") and rel.lower().endswith(
                      (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"))))
        if ext_ok:
            by_file.setdefault(rel, []).append(
                {"rule_id": rule_id, "line": item.get("line")})

    out.mkdir(parents=True, exist_ok=True)
    (out / "patches").mkdir(exist_ok=True)
    manifest_files, all_skipped = [], []
    all_skipped.extend(out_of_repo)
    for n, (rel, items) in enumerate(sorted(by_file.items()), 1):
        abs_path = (repo / rel).resolve()
        if not abs_path.is_relative_to(repo):
            all_skipped.append({"file": rel, "rule_id": "-", "line": None,
                                "reason": "路径越出仓库根，拒绝处理"})
            continue
        if not abs_path.is_file():
            all_skipped.append({"file": rel, "rule_id": "-", "line": None,
                                "reason": "源文件不存在"})
            continue
        patch_text, skipped = _patch_one_file(abs_path, rel, items)
        all_skipped.extend(skipped)
        if not patch_text:
            continue
        patch_name = "patch-%02d-%s.diff" % (n, Path(rel).name)
        # newline="\n"：补丁必须保持 LF，否则 git apply 因 CRLF 匹配失败
        (out / "patches" / patch_name).write_text(patch_text, encoding="utf-8",
                                                  newline="\n")
        has_ruff = any(str(i["rule_id"]).startswith("ruff:") for i in items)
        has_libcst = any(str(i["rule_id"]).startswith("libcst:")
                         for i in items)
        has_astgrep = any(str(i["rule_id"]).startswith("astgrep:")
                         for i in items)
        before_codes = None
        if has_ruff:
            scan = ruff_scan_codes(abs_path)
            before_codes = scan.get("codes") if isinstance(scan, dict) else None
        if has_libcst:
            scan = libcst_scan_codes(abs_path)
            before_codes = scan.get("codes") if isinstance(scan, dict) else None
        if has_astgrep:
            scan = astgrep_scan_codes(abs_path)
            before_codes = scan.get("codes") if isinstance(scan, dict) else None
        manifest_files.append({"path": rel, "patch_file": "patches/" + patch_name,
                               "rules": sorted({i["rule_id"] for i in items}),
                               "engine": ("astgrep" if has_astgrep
                                          else "libcst" if has_libcst
                                          else "ruff" if has_ruff else "builtin"),
                               "before_codes": before_codes,
                               "findings_count": len(items),
                               "bytes": len(patch_text.encode("utf-8"))})

    manifest = {"id": head[:12], "order_id": str(order.get("order_id")),
                "repo": str(repo), "base_sha": head,
                "files": manifest_files, "skipped": all_skipped}
    manifest_path = out / "fix-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                             encoding="utf-8", newline="\n")
    _emit({"ok": True, "manifest_path": str(manifest_path),
           "order_id": str(order.get("order_id")),
           "base_sha": head, "files": manifest_files,
           "skipped": all_skipped,
           "note": "补丁已生成到产物目录；落盘需审核人批准书 + fix-apply.py --apply"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
