#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F2P 数据质量预检：verified 批次选批前的机械闸（round-106）。

用途
----
对 SWE-bench verified 任务 JSONL 做纯静态 F2P 质量预检 + 10880 模式
选批过滤，避免烧评测轮才发现 F2P 数据质量问题（r103 3/3 blocked_data
教训）。只读任务 JSONL，不 checkout 仓库、不跑测试。

检查项
------
  C1 label_shape      F2P/P2P 标签须命中已知节点格式（django
                      `test_x (mod.C)` / pytest `path::node` /
                      unittest 点分 `mod.C.test_x`），否则判描述文本。
  C2 test_patch_touch 每个标签的候选测试文件（模块路径 .py + tests/
                      前缀变体）必须被 test_patch 触及——F2P 测试由
                      test_patch 添加/修改，未触及即数据疑点。
  C3 patch_shape      10880 模式选批：gold patch 触及文件数与 F2P
                      数不超过阈值（--max-patch-files / --max-f2p）。
  C4 fields           instance_id / test_patch / F2P 字段存在。

输出：单 JSON 文档（per-instance verdict + 汇总 + 可选 selected）；
--select-out 把过筛行写 JSONL（保留原始行全字段）。

用法示例：
    python f2p-quality.py --tasks batch.jsonl
    python f2p-quality.py --tasks pool.jsonl --select         --select-out candidates.jsonl --max-patch-files 3 --max-f2p 5

退出码：0=扫描完成（blocked 是数据结论不是脚本故障）；
2=参数/输入错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


RE_DJANGO = re.compile(r"^test_\w+ \(([\w.]+)\)$")
RE_PYTEST = re.compile(r"^(\S+\.py)::(\S+)$")
RE_DOTTED = re.compile(r"^([\w.]+)\.test_\w+$")

F2P_KEYS = ("fail_to_pass", "FAIL_TO_PASS")
PATCH_KEYS = ("patch", "gold_patch", "PATCH")


def _first(d, keys):
    for k in keys:
        if d.get(k) not in (None, "", []):
            return d[k]
    return None


def _label_file_candidates(label):
    """标签 → 候选测试文件相对路径（模块路径 .py + tests/ 变体）。"""
    m = RE_DJANGO.match(label)
    if m:
        mod = m.group(1)
        # 尾段若是类名（首字母大写），去掉类段
        parts = mod.split(".")
        if parts and parts[-1][:1].isupper():
            parts = parts[:-1]
        mod = ".".join(parts)
        rel = mod.replace(".", "/") + ".py"
        return [rel, "tests/" + rel]
    m = RE_PYTEST.match(label)
    if m:
        return [m.group(1)]
    m = RE_DOTTED.match(label)
    if m:
        rel = m.group(1).replace(".", "/") + ".py"
        return [rel, "tests/" + rel]
    return []


def _label_shape_ok(label):
    return bool(RE_DJANGO.match(label) or RE_PYTEST.match(label)
                or RE_DOTTED.match(label))


def _diff_files(patch):
    """unified diff 触及文件（a/ 侧路径，去重保序）。"""
    out = []
    for m in re.finditer(r"^diff --git a/(\S+) b/\S+", patch, re.M):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def check_instance(row, max_patch_files, max_f2p):
    """单实例四项检查 → verdict dict。"""
    reasons = []
    iid = row.get("instance_id", "?")
    labels = _first(row, F2P_KEYS)
    if isinstance(labels, str):
        # 官方 parquet schema：FAIL_TO_PASS 为 JSON 编码字符串
        try:
            labels = json.loads(labels)
        except ValueError:
            labels = [labels]  # 裸串单标签交给 C1 判形
    if not isinstance(labels, list) or not labels:
        reasons.append("f2p_missing_or_empty")
        labels = []
    tpatch = row.get("test_patch") or ""
    if not tpatch:
        reasons.append("test_patch_missing")
    touched = _diff_files(tpatch) if tpatch else []
    resolved, bad_shape, orphan = {}, [], []
    for lb in labels:
        if not isinstance(lb, str) or not _label_shape_ok(lb):
            bad_shape.append(lb)
            continue
        cands = _label_file_candidates(lb)
        hit = next((c for c in cands
                    if c in touched or any(t.endswith("/" + c) or t == c
                                           for t in touched)), None)
        resolved[lb] = hit
        if hit is None and touched:
            orphan.append(lb)
    if bad_shape:
        reasons.append("label_not_node_id x%d" % len(bad_shape))
    if orphan:
        reasons.append("f2p_file_not_in_test_patch x%d" % len(orphan))
    patch = _first(row, PATCH_KEYS)
    patch_files = len(_diff_files(patch)) if isinstance(patch, str) else None
    # patch 字段缺失不算质量否决（batch 文件可合法缺省）；
    # 但 10880 形状无法判定 → shape_10880=False，不进选批。
    shape_ok = (patch_files is not None and patch_files <= max_patch_files
                and len(labels) <= max_f2p)
    return {
        "instance_id": iid,
        "verdict": "ok" if not reasons else "blocked_quality",
        "reasons": reasons,
        "f2p_count": len(labels),
        "patch_files": patch_files,
        "shape_10880": shape_ok,
        "resolved_files": [v for v in resolved.values() if v],
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="F2P 数据质量预检 + 选批")
    ap.add_argument("--tasks", required=True, help="任务 JSONL（官方或 batch）")
    ap.add_argument("--select", action="store_true", help="输出 10880 形状过筛集")
    ap.add_argument("--select-out", help="过筛 JSONL 输出路径（配合 --select）")
    ap.add_argument("--max-patch-files", type=int, default=3)
    ap.add_argument("--max-f2p", type=int, default=5)
    args = ap.parse_args()
    tp = Path(args.tasks)
    if not tp.is_file():
        _emit({"ok": False, "error": "任务文件不存在: %s" % tp})
        return 2
    rows = []
    with tp.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    if not rows:
        _emit({"ok": False, "error": "任务文件为空或不可解析: %s" % tp})
        return 2
    verdicts = [check_instance(r, args.max_patch_files, args.max_f2p)
                for r in rows]
    blocked_by = {}
    for v in verdicts:
        for r in v["reasons"]:
            key = r.split(" x")[0]
            blocked_by[key] = blocked_by.get(key, 0) + 1
    selected = [v for v in verdicts
                if v["verdict"] == "ok" and v["shape_10880"]]
    out = {
        "ok": True,
        "tasks": str(tp),
        "n": len(rows),
        "summary": {
            "ok_count": sum(1 for v in verdicts if v["verdict"] == "ok"),
            "blocked_count": sum(1 for v in verdicts
                                 if v["verdict"] != "ok"),
            "blocked_by": blocked_by,
            "selected_10880": len(selected),
        },
        "verdicts": verdicts,
    }
    if args.select:
        ok_ids = {v["instance_id"] for v in selected}
        sel_rows = [r for r in rows if r.get("instance_id") in ok_ids]
        out["selected_ids"] = sorted(ok_ids)
        if args.select_out:
            with Path(args.select_out).open("w", encoding="utf-8",
                                            newline="\n") as f:
                for r in sel_rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out["select_out"] = str(args.select_out)
            out["selected_written"] = len(sel_rows)
    _emit(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
