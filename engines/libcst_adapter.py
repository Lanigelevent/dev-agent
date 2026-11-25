#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LibCST codemod/重构引擎（engines 层，.venv 运行；Phase 2A 计划项）。

结构保序重构：LibCST 保留全部格式与注释，只做确定性、语义等价的机械变换。
能力矩阵见 engines/libcst-matrix.json；发现 rule_id 形如 libcst:<code>，
修复产物与机械补丁同链经五道闸落盘（repair/scripts/fix-apply.py）。

codemods（v1，全部语义等价的保守变换）:
    ref-eq-none   x == None → x is None；x != None → x is not None（PEP 8）
    ref-in-keys   k in d.keys() → k in d（dict.keys() 视图成员等价）

用途:
    .venv python libcst_adapter.py scan --file m.py [--rel svc.py] [--codes c1,c2]
    .venv python libcst_adapter.py fix-text --codes ref-eq-none < m.py   # JSON: {"ok","text"}
    .venv python libcst_adapter.py fix-dry --repo <repo> --rel <rel> --out <dir>
    .venv python libcst_adapter.py matrix
    .venv python libcst_adapter.py clean-fp --file a.py --file b.py

库函数（供 skills 层在全局解释器下 import；自举子进程到 .venv）:
    libcst_scan_codes(path) -> {"codes": [...], "count": n} | None
    libcst_fix_text(text, codes) -> 修复后文本 | None

退出码:
    0 = 成功；1 = 可处理问题（解析失败/引擎错误）；2 = 参数错误。

说明：fix-text 输出 JSON 信封（{"ok","text"}）——机器可读约定优先，
消费方为 fix-patch（经子进程管道）。
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENGINES_DIR = Path(__file__).resolve().parent
if str(_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINES_DIR))
from artifact_names import patch_artifact_name  # noqa: E402 - 三引擎共用命名口径
MATRIX_PATH = ROOT / "engines" / "libcst-matrix.json"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fail(state, error):
    _emit({"ok": False, "state": state, "error": error})
    return 1


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _libcst():
    """惰性导入：本模块顶层保持纯标准库（skills 层全局解释器可安全 import）。"""
    import libcst as cst
    return cst


# ---------------------------------------------------------------- 变换器

def _is_none_literal(node):
    cst = _libcst()
    return isinstance(node, cst.Name) and node.value == "None"


def _ref_eq_none_cls():
    """工厂：_libcst() 导入后再构造变换器类（顶层保持无 libcst 依赖）。"""
    cst = _libcst()

    class _RefEqNone(cst.CSTTransformer):
        """x == None → x is None；x != None → x is not None（保序）。"""

        def leave_Comparison(self, original, updated):
            changed = False
            new_targets = []
            prev_comparator = updated.left
            for target in updated.comparisons:
                op = target.operator
                if isinstance(op, (cst.Equal, cst.NotEqual)) and (
                        _is_none_literal(target.comparator)
                        or _is_none_literal(prev_comparator)):
                    new_op = (cst.Is() if isinstance(op, cst.Equal)
                              else cst.IsNot())
                    new_targets.append(cst.ComparisonTarget(
                        operator=new_op, comparator=target.comparator))
                    changed = True
                else:
                    new_targets.append(target)
                prev_comparator = target.comparator
            if not changed:
                return updated
            return updated.with_changes(comparisons=new_targets)

    return _RefEqNone()


def _ref_in_keys_cls():
    cst = _libcst()

    class _RefInKeys(cst.CSTTransformer):
        """k in d.keys() → k in d（单目标比较；.keys() 无参调用才变换）。"""

        def leave_Comparison(self, original, updated):
            if len(updated.comparisons) != 1:
                return updated
            target = updated.comparisons[0]
            if not isinstance(target.operator, (cst.In, cst.NotIn)):
                return updated
            right = target.comparator
            if isinstance(right, cst.Call) and not right.args \
                    and isinstance(right.func, cst.Attribute) \
                    and right.func.attr.value == "keys":
                return updated.with_changes(comparisons=[cst.ComparisonTarget(
                    operator=target.operator, comparator=right.func.value)])
            return updated

    return _RefInKeys()


CODEMODS = {"ref-eq-none": _ref_eq_none_cls, "ref-in-keys": _ref_in_keys_cls}


def _apply(text, codes):
    """按 codes 应用 codemod，返回 (新文本, 命中明细 [{code, count}])。"""
    cst = _libcst()
    tree = cst.parse_module(text)
    hits = []
    for code in codes:
        transformer = CODEMODS[code]()
        new_tree = tree.visit(transformer)
        if new_tree.code != tree.code:
            hits.append({"code": code, "changed": True})
        tree = new_tree
    return tree.code, hits


# ---------------------------------------------------------------- 核心

def scan_file(path, rel=None, codes=None):
    """扫描单文件：返回 findings（libcst:<code> 前缀）与 codes。"""
    cst = _libcst()
    import libcst.metadata as cmeta
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    wanted = set(codes or CODEMODS)
    findings = []

    class _Scan(cst.CSTTransformer):
        METADATA_DEPENDENCIES = (cmeta.PositionProvider,)

        def leave_Comparison(self, original, updated):
            pos = self.get_metadata(cmeta.PositionProvider, original)
            # ref-eq-none
            prev = updated.left
            for t in updated.comparisons:
                if isinstance(t.operator, (cst.Equal, cst.NotEqual)) and (
                        _is_none_literal(t.comparator)
                        or _is_none_literal(prev)):
                    code = "ref-eq-none"
                    if code in wanted:
                        findings.append({
                            "rule_id": "libcst:" + code, "engine": "libcst",
                            "file": rel or str(path),
                            "line": pos.start.line,
                            "column": pos.start.column,
                            "message": "与 None 比较应用 is/is not（PEP 8）"})
                prev = t.comparator
            # ref-in-keys
            if len(updated.comparisons) == 1:
                t = updated.comparisons[0]
                right = t.comparator
                if isinstance(t.operator, (cst.In, cst.NotIn)) \
                        and isinstance(right, cst.Call) and not right.args \
                        and isinstance(right.func, cst.Attribute) \
                        and right.func.attr.value == "keys" \
                        and "ref-in-keys" in wanted:
                    findings.append({
                        "rule_id": "libcst:ref-in-keys", "engine": "libcst",
                        "file": rel or str(path), "line": pos.start.line,
                        "column": pos.start.column,
                        "message": "in d.keys() 等价于 in d，可直接简化"})
            return updated

    wrapper = cst.metadata.MetadataWrapper(cst.parse_module(text))
    wrapper.visit(_Scan())
    codes_found = sorted({f["rule_id"].split(":", 1)[1] for f in findings})
    return {"ok": True, "engine": "libcst", "findings": findings,
            "codes": codes_found}


def cmd_scan(argv):
    if not Path(argv.file).is_file():
        return _param_error("文件不存在: %s" % argv.file)
    codes = argv.codes.split(",") if argv.codes else None
    data = scan_file(argv.file, rel=argv.rel, codes=codes)
    _emit(data)
    return 0


def cmd_fix_text(argv):
    codes = [c for c in (argv.codes or "").split(",") if c]
    unknown = [c for c in codes if c not in CODEMODS]
    if unknown:
        return _param_error("未知 codemod: %s" % ",".join(unknown))
    # stdin 显式 UTF-8：宿主 ANSI locale 为 cp936 时，sys.stdin 默认按 GBK 解码，
    # 带中文注释的源码会在进 codemod 之前就被解成代理对，修复产物随之损坏。
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    text = sys.stdin.read()
    try:
        fixed, hits = _apply(text, codes)
    except Exception as exc:  # libcst 解析/变换错误
        return _fail("PARSE_ERROR", "%s: %s" % (exc.__class__.__name__,
                                                str(exc)[:160]))
    _emit({"ok": True, "text": fixed, "hits": hits})
    return 0


def cmd_fix_dry(argv):
    repo = Path(argv.repo)
    src = repo / argv.rel
    if not src.is_file():
        return _param_error("源文件不存在: %s" % src)
    codes = [c for c in (argv.codes or "").split(",") if c] or list(CODEMODS)
    unknown = [c for c in codes if c not in CODEMODS]
    if unknown:
        return _param_error("未知 codemod: %s" % ",".join(unknown))
    text = src.read_text(encoding="utf-8", errors="replace")
    try:
        fixed, _hits = _apply(text, codes)
    except Exception as exc:
        return _fail("PARSE_ERROR", "%s: %s" % (exc.__class__.__name__,
                                                str(exc)[:160]))
    out = Path(argv.out)
    out.mkdir(parents=True, exist_ok=True)
    patch_name = patch_artifact_name("patch", argv.rel, ".diff")
    patch_path = out / patch_name
    diff = "".join(difflib.unified_diff(
        text.splitlines(keepends=True), fixed.splitlines(keepends=True),
        fromfile="a/" + argv.rel, tofile="b/" + argv.rel))
    patch_path.write_text(diff, encoding="utf-8", newline="\n")
    residual = sorted(set(scan_codes_of_text(fixed)) & set(codes))
    _emit({"ok": True, "patch_path": str(patch_path),
           "patch_bytes": len(diff.encode("utf-8")),
           "residual_codes": residual})
    return 0


def scan_codes_of_text(text):
    import tempfile
    fd, name = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return scan_file(name)["codes"]
    finally:
        os.unlink(name)


def cmd_matrix(argv):
    try:
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _fail("MATRIX_ERROR", str(exc)[:160])
    _emit({"ok": True, "matrix": matrix})
    return 0


def cmd_clean_fp(argv):
    if not argv.file:
        return _param_error("clean-fp 需 --file 至少一个")
    findings_total = 0
    scanned = 0
    for f in argv.file:
        if not Path(f).is_file():
            return _param_error("文件不存在: %s" % f)
        data = scan_file(f)
        findings_total += len(data["findings"])
        scanned += 1
    _emit({"ok": True, "scanned": scanned, "clean_fp": findings_total,
           "note": "干净样例上的发现数即误报数（红线 6 反向验证口径）"})
    return 0


# ------------------------------------------------ 库函数（全局解释器入口）

def venv_python():
    """定位 .venv 解释器；缺失时回退当前解释器（仅当其有 libcst 才可用）。"""
    root = Path(__file__).resolve().parents[1]
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    cand = root / ".venv" / sub
    if cand.is_file():
        return str(cand)
    return sys.executable


def _self_run(args, input_text=None):
    cmd = [venv_python(), str(Path(__file__).resolve())] + args
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input=input_text,
                       timeout=120)
    return p


def libcst_scan_codes(path, codes=""):
    """库函数：{"codes": [...], "count": n}；失败返回 None（子进程到 .venv）。"""
    args = ["scan", "--file", str(path)]
    if codes:
        args += ["--codes", codes]
    p = _self_run(args)
    if p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        return None
    return {"codes": data.get("codes", []),
            "count": len(data.get("findings", []))}


def libcst_fix_text(text, codes):
    """库函数：返回 codemod 修复后文本；失败返回 None（子进程到 .venv）。

    codes 接受逗号串或列表（ruff_fix_text 同款语义）。
    """
    if isinstance(codes, str):
        codes = [c for c in codes.split(",") if c]
    p = _self_run(["fix-text", "--codes", ",".join(codes)], input_text=text)
    if p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        return None
    return data.get("text")


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="LibCST codemod/重构引擎")
    sub = parser.add_subparsers(dest="phase", required=True)

    p = sub.add_parser("scan", help="扫描可重构点")
    p.add_argument("--file", required=True)
    p.add_argument("--rel", default="", help="findings 里的相对路径展示")
    p.add_argument("--codes", default="", help="限定 codemod（逗号分隔）")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("fix-text", help="stdin 文本 → 修复后文本（JSON 信封）")
    p.add_argument("--codes", required=True)
    p.set_defaults(func=cmd_fix_text)

    p = sub.add_parser("fix-dry", help="产出 unified diff（不落盘）")
    p.add_argument("--repo", required=True)
    p.add_argument("--rel", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--codes", default="")
    p.set_defaults(func=cmd_fix_dry)

    p = sub.add_parser("matrix", help="输出能力矩阵")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("clean-fp", help="干净样例误报自检")
    p.add_argument("--file", action="append")
    p.set_defaults(func=cmd_clean_fp)

    argv = parser.parse_args()
    return argv.func(argv)


if __name__ == "__main__":
    sys.exit(main())
