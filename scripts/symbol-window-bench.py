#!/usr/bin/env python3
"""AB-18 符号级取窗 vs 整文件取窗对照实验（round-212）。

用途
    在 r197 同源真实语料（datasets/swe-out resolved 实例，n≈11）上，
    对每例真实任务的补丁目标文件（base_commit 快照）量化两种取窗策略：

    - 整文件臂（whole）：整个目标文件文本（Serena 要规避的「整读」形态）。
    - 符号臂（symbol）：改动行所在最小包围 def/class 的并集窗（Serena 式
      符号粒度；实现用 stdlib ast，与 repo_map.extract_window 的「定义点
      优先」同一思想族）。

    指标：字符成本比 symbol/whole、改动行覆盖率（无包围符号 → 该任务
    整文件兜底，如实计 fallback）、逐例明细。

判据（预注册，r197 方法先例）
    ratio <= 0.5 且 coverage == 1.0   → 符号级取窗已实现且显著省成本
                                        → AB-18 终局=已对齐（已有超出）
    ratio in (0.5, 0.8] 且 coverage=1.0 → 已对齐（优化空间有限，登记）
    coverage < 1.0                    → 兜底面如实登记（定性结论不受影响：
                                        定义点优先取窗已存在）

用法示例
    python scripts/symbol-window-bench.py --out reports/_work/symbol-window-r212.json

退出码
    0 = 实验完成；1 = 有可处理问题（语料缺失）；2 = 输入/环境错误
"""
import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "scripts" / "aci-retrieval-bench.py"


def _load_bench():
    spec = importlib.util.spec_from_file_location("aci_bench", BENCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _changed_lines(patch_text):
    """unified diff → {文件: 改动行号集合}（新文件行号；上下文+新增行计入）。"""
    out = {}
    cur = None
    newline = 0
    fname = None
    for line in patch_text.splitlines():
        if line.startswith("diff --git"):
            fname = None
            cur = None
            continue
        if line.startswith("--- "):
            continue
        if line.startswith("+++ "):
            fname = line[4:].strip()
            if fname.startswith("b/"):
                fname = fname[2:]
            cur = out.setdefault(fname, set())
            continue
        if line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            newline = int(m.group(1)) if m else 0
            continue
        if fname is None:
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            cur.add(newline)
            newline += 1
        elif line.startswith("-"):
            continue
        else:
            cur.add(newline)
            newline += 1
    return out


def _enclosing_symbol_span(tree, line):
    """包含 line 的最小包围 def/class 节点 → (start, end)；无则 None。"""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            if node.lineno <= line <= node.end_lineno:
                size = node.end_lineno - node.lineno
                if best is None or size < best[1] - best[0]:
                    best = (node.lineno, node.end_lineno)
    return best


def _symbol_window(lines, line_set):
    """改动行并集 → 包围符号窗文本与覆盖数；返回 (text, covered, total)。"""
    tree = ast.parse("\n".join(lines))
    spans = []
    for line in line_set:
        span = _enclosing_symbol_span(tree, line)
        if span is None:
            continue
        spans.append(span)
    if not spans:
        return "", 0, len(line_set)
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    text = "\n".join("\n".join(lines[s - 1:e]) for s, e in merged)
    covered = sum(1 for line in line_set
                  if any(s <= line <= e for s, e in merged))
    return text, covered, len(line_set)


def _git_show(repo, rev, path):
    """git show <rev>:<path> 取快照文本；失败返回 None。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "show", "%s:%s" % (rev, path)],
            capture_output=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", errors="replace")


def _read_patch(sample):
    """读实例任一 run 目录的 edits.patch（同实例多版本目标一致）。"""
    swe_out = ROOT / "datasets" / "swe-out" / "agent-sample"
    for run_dir in sorted(swe_out.glob(str(sample["id"]) + "*")):
        patch = run_dir / "edits.patch"
        if patch.is_file():
            return patch.read_text(encoding="utf-8", errors="replace")
    return ""


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="AB-18 符号级取窗 vs 整文件取窗对照实验")
    parser.add_argument("--out", help="JSON 明细写入文件，同时打印摘要")
    argv = parser.parse_args()
    bench = _load_bench()
    samples, err = bench._load_real_samples()
    if err:
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False))
        return 1
    if not samples:
        print(json.dumps({"ok": False, "error": "语料为空"}, ensure_ascii=False))
        return 1
    rows = []
    for sample in samples:
        task_rows = []
        for target in sample["targets"]:
            content = _git_show(sample["repo"], sample["base_commit"],
                                target)
            if content is None:
                continue
            lines = content.splitlines()
            patch = _read_patch(sample)
            line_set = _changed_lines(patch).get(target) or set()
            if not line_set:
                continue
            whole = len(content)
            try:
                sym_text, covered, total = _symbol_window(lines, line_set)
            except SyntaxError:
                sym_text, covered, total = "", 0, len(line_set)
            covered_ratio = (covered / total) if total else 0.0
            fallback = covered_ratio < 1.0
            task_rows.append({
                "file": target,
                "whole_chars": whole,
                "symbol_chars": len(sym_text),
                "ratio": round(len(sym_text) / whole, 4) if whole else 0.0,
                "coverage": round(covered_ratio, 4),
                "fallback": fallback,
            })
        if task_rows:
            rows.append({"id": sample["id"], "rows": task_rows})
    all_rows = [r for task in rows for r in task["rows"]]
    whole_sum = sum(r["whole_chars"] for r in all_rows)
    symbol_sum = sum(r["symbol_chars"] for r in all_rows)
    ratio = symbol_sum / whole_sum if whole_sum else 0.0
    coverage = (sum(1 for r in all_rows if r["coverage"] >= 1.0)
                / len(all_rows) if all_rows else 0.0)
    verdict = ("symbol_window_superior"
               if ratio <= 0.5 and coverage >= 1.0
               else "aligned_limited_gain"
               if ratio <= 0.8 and coverage >= 1.0
               else "fallback_face_documented")
    result = {
        "ok": True,
        "tasks": len(rows),
        "files": len(all_rows),
        "whole_chars_total": whole_sum,
        "symbol_chars_total": symbol_sum,
        "ratio": round(ratio, 4),
        "coverage": round(coverage, 4),
        "fallback_files": sum(1 for r in all_rows if r["fallback"]),
        "verdict": verdict,
        "detail": rows,
    }
    if argv.out:
        out_path = ROOT / argv.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "detail"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())