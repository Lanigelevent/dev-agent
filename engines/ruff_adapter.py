#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ruff 引擎适配器（MIT 引擎；按 AGENTS 硬约束 1 以 subprocess+JSON 调用，
本适配器自身零第三方依赖，运行于全局 Python；ruff 二进制在项目 .venv）。

Ruff pip 包无 Python API（实测），CLI 三面：
- scan：ruff check --output-format json → 本仓 findings 形状
  （rule_id=ruff:<code>；F821 未定义名→高，其余→低）；
- fix-dry：临时副本真跑 ruff check --fix，difflib 产 a/<rel> b/<rel> 的
  LF 补丁（与 fix-patch 产物同格式，五道闸可直接 git apply），不写原文件；
- matrix：ruff rule --all --output-format json → 能力矩阵 ruff-matrix.json
  （规则总数/可修复数/按 linter 分布/版本），供总监治理与 fix-plan 分诊；
- clean-fp：默认规则集（E4,E7,E9,F）在干净语料的命中统计（启用分级依据）。

用法示例：
    py engines/ruff_adapter.py scan --file x.py
    py engines/ruff_adapter.py fix-dry --repo <仓库> --rel pkg/mod.py --out <dir>
    py engines/ruff_adapter.py matrix --out engines
    py engines/ruff_adapter.py clean-fp --corpus <干净语料目录>

退出码：0=成功（含零诊断）；2=输入/引擎错误。
"""
import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENGINES_DIR = Path(__file__).resolve().parent
if str(_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINES_DIR))
from artifact_names import patch_artifact_name  # noqa: E402 - 三引擎共用命名口径
DEFAULT_SELECT = "E4,E7,E9,F"  # Ruff 官方默认集（精度优先的保守启用面）
SEVERITY_MAP = {"F821": "高", "F811": "中", "F841": "中"}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ruff_bin():
    for cand in (ROOT / ".venv" / "Scripts" / "ruff.exe",
                 ROOT / ".venv" / "bin" / "ruff", "ruff"):
        if str(cand) == "ruff" or cand.is_file():
            return str(cand)
    return "ruff"


def _run_ruff(args, timeout=300):
    proc = subprocess.run([_ruff_bin()] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def _finding(item, repo_rel=None):
    code = str(item.get("code", ""))
    loc = item.get("location") or {}
    snippet = (item.get("message") or "")[:160]
    return {
        "rule_id": "ruff:%s" % code,
        "severity": SEVERITY_MAP.get(code, "低"),
        "file": repo_rel or str(item.get("filename", "")),
        "line": int(loc.get("row") or 1),
        "snippet": snippet,
        "reason": "ruff %s: %s" % (code, snippet[:80]),
        "engine": "ruff",
    }


def cmd_scan(argv):
    target = Path(argv.file)
    if not target.is_file():
        _emit({"ok": False, "error": "文件不存在: %s" % target})
        return 2
    args = ["check", "--output-format", "json"]
    if argv.select:
        args += ["--select", argv.select]
    args.append(str(target))
    rc, out, err = _run_ruff(args)
    if rc not in (0, 1):  # ruff: 0=无诊断 1=有诊断
        _emit({"ok": False, "error": "ruff 退出码 %d: %s" % (rc, err[:300])})
        return 2
    try:
        items = json.loads(out or "[]")
    except ValueError:
        _emit({"ok": False, "error": "ruff 输出非 JSON"})
        return 2
    repo_rel = argv.rel or str(target)
    findings = [_finding(i, repo_rel) for i in items]
    _emit({"ok": True, "engine": "ruff", "select": argv.select or DEFAULT_SELECT,
           "findings": findings,
           "codes": sorted({f["rule_id"] for f in findings})})
    return 0


def cmd_fix_dry(argv):
    repo = Path(argv.repo).resolve()
    rel = Path(argv.rel).as_posix()
    src = repo / rel
    if not src.is_file():
        _emit({"ok": False, "error": "源文件不存在: %s" % src})
        return 2
    original = src.read_text(encoding="utf-8", errors="replace")
    tmp = Path(tempfile.mkdtemp(prefix="ruff-fix-"))
    try:
        copy = tmp / src.name
        copy.write_text(original, encoding="utf-8", newline="\n")
        args = ["check", "--fix", "--select",
                argv.select or DEFAULT_SELECT, str(copy)]
        rc, _, err = _run_ruff(args)
        if rc not in (0, 1):
            _emit({"ok": False, "error": "ruff --fix 退出码 %d: %s" % (rc, err[:300])})
            return 2
        fixed = copy.read_text(encoding="utf-8", errors="replace")
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            fixed.splitlines(keepends=True),
            fromfile="a/" + rel, tofile="b/" + rel)
        patch_text = "".join(diff)
        if patch_text and not patch_text.endswith("\n"):
            patch_text += "\n"
        out_dir = Path(argv.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        patch_path = out_dir / patch_artifact_name("ruff", rel, ".patch")
        if patch_text:
            patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
        rc2, out2, _ = _run_ruff(["check", "--output-format", "json",
                                  "--select", argv.select or DEFAULT_SELECT,
                                  str(copy)])
        try:
            residual = [i.get("code") for i in json.loads(out2 or "[]")]
        except ValueError:
            residual = []
        _emit({"ok": True, "engine": "ruff", "rel": rel,
               "patch_path": str(patch_path) if patch_text else "",
               "patch_bytes": len(patch_text.encode("utf-8")),
               "residual_codes": sorted(set(residual))})
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_matrix(argv):
    rc, out, err = _run_ruff(["rule", "--all", "--output-format", "json"])
    if rc != 0:
        _emit({"ok": False, "error": "ruff rule 失败: %s" % err[:300]})
        return 2
    rc_v, ver, _ = _run_ruff(["--version"])
    try:
        rules = json.loads(out)
    except ValueError:
        _emit({"ok": False, "error": "ruff rule 输出非 JSON"})
        return 2
    rules = [r for r in rules if r.get("code")]  # 部分规则无编号（如 preview 组），不计入
    # fix_availability: Always=确定性可修 / Sometimes=视上下文 / None=不可自动修
    fixable = {r["code"] for r in rules
               if r.get("fix_availability") in ("Always", "Sometimes")}
    safe_fixable = {r["code"] for r in rules
                    if r.get("fix_availability") == "Always"}
    by_linter = {}
    for r in rules:
        by_linter[r.get("linter", "?")] = by_linter.get(r.get("linter", "?"), 0) + 1
    matrix = {
        "engine": "ruff",
        "version": ver.strip(),
        "total_rules": len(rules),
        "fixable_rules": len(fixable),
        "safe_fixable_rules": len(safe_fixable),
        "fixable_codes": sorted(fixable),
        "safe_fixable_codes": sorted(safe_fixable),
        "by_linter": dict(sorted(by_linter.items(), key=lambda kv: -kv[1])),
        "default_select": DEFAULT_SELECT,
        "risk_policy": "fix-dry 仅在 --select 白名单上执行；产物过五道闸",
    }
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ruff-matrix.json"
    path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
    _emit({"ok": True, "matrix_path": str(path),
           "total_rules": matrix["total_rules"],
           "fixable_rules": matrix["fixable_rules"],
           "safe_fixable_rules": matrix["safe_fixable_rules"]})
    return 0


def cmd_clean_fp(argv):
    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        _emit({"ok": False, "error": "语料目录不存在: %s" % corpus})
        return 2
    total, by_code, files = 0, {}, 0
    for p in sorted(corpus.rglob("*.py")):
        files += 1
        rc, out, _ = _run_ruff(["check", "--output-format", "json",
                                "--select", DEFAULT_SELECT, str(p)])
        if rc not in (0, 1):
            continue
        try:
            items = json.loads(out or "[]")
        except ValueError:
            continue
        total += len(items)
        for i in items:
            code = "ruff:%s" % i.get("code", "?")
            by_code[code] = by_code.get(code, 0) + 1
    _emit({"ok": True, "engine": "ruff", "select": DEFAULT_SELECT,
           "files": files, "findings": total,
           "by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
           "note": "默认集在干净语料的命中=引擎启用分级的依据；"
                   "命中>0 的码不进评审管线，只进修复链（经五道闸）"})
    return 0


def ruff_fix_text(text, select):
    """库函数：在临时副本上跑 ruff --fix，返回修复后文本；失败返回 None。"""
    tmp = Path(tempfile.mkdtemp(prefix="ruff-lib-"))
    try:
        copy = tmp / "m.py"
        copy.write_text(text, encoding="utf-8", newline="\n")
        rc, _, _ = _run_ruff(["check", "--fix", "--select", select, str(copy)])
        if rc not in (0, 1):
            return None
        return copy.read_text(encoding="utf-8", errors="replace")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ruff_scan_codes(path, select=""):
    """库函数：返回 {"codes": 去重码列表, "count": 诊断条数}；失败返回 None。"""
    args = ["check", "--output-format", "json"]
    if select:
        args += ["--select", select]
    args.append(str(path))
    rc, out, _ = _run_ruff(args)
    if rc not in (0, 1):
        return None
    try:
        items = json.loads(out or "[]")
    except ValueError:
        return None
    return {"codes": sorted({str(i.get("code", "")) for i in items}),
            "count": len(items)}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ruff 引擎适配器")
    sub = parser.add_subparsers(dest="mode", required=True)
    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--file", required=True)
    p_scan.add_argument("--rel", default="", help="仓库相对路径（findings.file）")
    p_scan.add_argument("--select", default="", help="规则集（缺省 Ruff 默认集）")
    p_fix = sub.add_parser("fix-dry")
    p_fix.add_argument("--repo", required=True)
    p_fix.add_argument("--rel", required=True)
    p_fix.add_argument("--out", required=True)
    p_fix.add_argument("--select", default="")
    p_mat = sub.add_parser("matrix")
    p_mat.add_argument("--out", required=True)
    p_cf = sub.add_parser("clean-fp")
    p_cf.add_argument("--corpus", required=True)
    argv = parser.parse_args()
    if argv.mode == "scan":
        return cmd_scan(argv)
    if argv.mode == "fix-dry":
        return cmd_fix_dry(argv)
    if argv.mode == "matrix":
        return cmd_matrix(argv)
    return cmd_clean_fp(argv)


if __name__ == "__main__":
    sys.exit(main())
