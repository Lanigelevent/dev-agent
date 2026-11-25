#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""变异采样器：AST 算子翻转 × 聚焦测试 → 杀手分数（round-144）。

用途:
    验证契约测试的杀伤力（手册维护红线 6 的量化延伸）。对目标模块做
    确定性变异（比较运算翻转 / and-or 翻转 / True-False 翻转 / 常量 ±1），
    逐个替换源文件后跑聚焦测试，统计 killed/survived：
    - killed   = 变异后聚焦测试失败（测试抓住了该变异）
    - survived = 变异后测试仍全绿（测试盲区，需补行为断言）
    原文件在 finally 中恢复（变异永不残留）。自研实现的原因：mutmut 3.x
    原生不支持 Windows（issue #397），且治理壳零依赖纪律（硬约束 1）
    更适配 stdlib AST 方案；第 105 条的 mutmut 路线据此修正。

用法示例:
    py mutation-sampler.py run --target skills/eval-harness/scripts/review-quality-gate.py \
        --tests tests/test_scripts_review_quality_gate.py --max-mutants 10 \
        --out reports/_work/mutation-rqg.json

退出码:
    0 = 完成报告（kill_rate 高低不改变退出码，判定留给阅读者/门禁）
    2 = 参数/输入错误（target/tests 不存在、AST 不可解析）
"""
import argparse
import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


_COMPARE_FLIP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt,
    ast.Gt: ast.LtE, ast.LtE: ast.Gt,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}
_BOOL_FLIP = {ast.And: ast.Or, ast.Or: ast.And}


class _Mutator(ast.NodeTransformer):
    """确定性算子翻转；kind 记录变异位点（行号 + 描述）。"""

    def __init__(self):
        self.mutations = []

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            flip = _COMPARE_FLIP.get(type(op))
            if flip:
                node.ops[i] = flip()
                self.mutations.append((node.lineno, "比较翻转"))
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        flip = _BOOL_FLIP.get(type(node.op))
        if flip:
            node.op = flip()
            self.mutations.append((node.lineno, "布尔翻转"))
        return node

    def visit_Constant(self, node):
        self.generic_visit(node)
        if node.value is True:
            node.value = False
            self.mutations.append((node.lineno, "True→False"))
        elif node.value is False:
            node.value = True
            self.mutations.append((node.lineno, "False→True"))
        elif isinstance(node.value, int) and not isinstance(node.value, bool):
            node.value = node.value + 1
            self.mutations.append((node.lineno, "常量+1"))
        return node



class _SingleMutator(ast.NodeTransformer):
    """只翻转第 target_index 个可翻转位点（先确定性遍历收集位点，再单独生成）。

    walk 顺序 = ast 的遍历序（确定）；flippable = 比较运算 / 布尔运算 /
    True-False 常量 / 非布尔 int 常量。
    """

    def __init__(self, target_index):
        self.target_index = target_index
        self._count = 0
        self.done = None

    def _hit(self, lineno, kind):
        if self._count == self.target_index:
            self.done = (lineno, kind)
        self._count += 1
        return self._count - 1 == self.target_index

    def visit_Compare(self, node):
        self.generic_visit(node)
        for i, op in enumerate(node.ops):
            flip = _COMPARE_FLIP.get(type(op))
            if flip:
                if self._hit(node.lineno, "比较翻转"):
                    node.ops[i] = flip()
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        flip = _BOOL_FLIP.get(type(node.op))
        if flip:
            if self._hit(node.lineno, "布尔翻转"):
                node.op = flip()
        return node

    def visit_Constant(self, node):
        self.generic_visit(node)
        if node.value is True:
            if self._hit(node.lineno, "True→False"):
                node.value = False
        elif node.value is False:
            if self._hit(node.lineno, "False→True"):
                node.value = True
        elif isinstance(node.value, int) and not isinstance(node.value, bool):
            if self._hit(node.lineno, "常量+1"):
                node.value = node.value + 1
        return node


def count_sites(source):
    tree = ast.parse(source)
    m = _SingleMutator(-1)
    m.visit(tree)
    return m._count


def generate_mutant(source, index):
    """源码 → (lineno, kind, mutated_source)；index 越界返回 None。"""
    if index >= count_sites(source):
        return None
    tree = ast.parse(source)
    m = _SingleMutator(index)
    m.visit(tree)
    ast.fix_missing_locations(tree)
    return (m.done[0], m.done[1], ast.unparse(tree))


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="变异采样器（杀手分数报告）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="对 target 生成变异并跑聚焦测试")
    p.add_argument("--target", required=True)
    p.add_argument("--tests", required=True)
    p.add_argument("--max-mutants", type=int, default=10)
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--out", default="")
    args = ap.parse_args()
    tp = Path(args.target)
    tspath = Path(args.tests)
    if not tp.is_file():
        _emit_error("target 不存在: %s" % tp)
        return 2
    if not tspath.is_file():
        _emit_error("tests 不存在: %s" % tspath)
        return 2
    source = tp.read_text(encoding="utf-8")
    try:
        total = count_sites(source)
    except SyntaxError as e:
        _emit_error("target AST 不可解析: %s" % e)
        return 2
    n = min(args.max_mutants, total)
    killed = survived = errored = 0
    detail = []
    backup = source + chr(10) + "# MUTATION-BACKUP-MARKER"
    tmpdir = tempfile.mkdtemp(prefix="mut-")
    try:
        shutil.copyfile(tp, Path(tmpdir) / "orig.py")
        for idx in range(n):
            gen = generate_mutant(source, idx)
            lineno, kind, mutated = gen
            tp.write_text(mutated, encoding="utf-8", newline="")
            try:
                p = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", str(tspath)],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=args.timeout)
                ok = (p.returncode == 0)
            except subprocess.TimeoutExpired:
                ok = False
                errored += 1
                kind = kind + "(超时)"
            if ok:
                survived += 1
            else:
                killed += 1
            detail.append({"index": idx, "lineno": lineno, "kind": kind,
                           "killed": not ok})
    finally:
        shutil.copyfile(Path(tmpdir) / "orig.py", tp)
        shutil.rmtree(tmpdir, ignore_errors=True)
    rate = (killed / (killed + survived)) if (killed + survived) else None
    result = {
        "ok": True, "mode": "mutation-sampler",
        "target": args.target, "tests": args.tests,
        "sites_total": total, "sampled": n,
        "killed": killed, "survived": survived,
        "kill_rate": None if rate is None else round(rate, 4),
        "survived_detail": [d for d in detail if not d["killed"]],
        "note": "killed=测试抓住变异；survived=测试盲区（补行为断言的候选点）；"
                "原文件已恢复（finally 保证）",
    }
    if args.out:
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        result["out"] = args.out
    _emit(result)
    return 0


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _emit_error(msg):
    _emit({"ok": False, "mode": "mutation-sampler", "error": msg})


if __name__ == "__main__":
    sys.exit(main())
