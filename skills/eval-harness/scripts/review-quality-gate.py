#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评审响应质量门禁：宿主评审批次的执行质量下限（round-138，D-053 对策）。

用途:
    防 round-132 型预算黑洞复发：宿主评审「全 [] 批次」若没有 per-PR 依据
    说明，judge 前拦截。对 findings.json（swrenbench review 产物）做四项
    检查：
    - empty_batch_note：全空批次（findings 总数=0）必须附顶层 batch_note
      非空说明——为什么这批 PR 全部无发现；缺失即护栏失败。
    - evidence_coverage：非空 finding 的 evidence 字段非空占比 ≥ 阈值
      （缺省 0.8）；无 findings 时跳过（记 skipped）。
    - unparsed_rate：unparsed 样本占比 ≤ 阈值（缺省 0.1）。
    - batch_shape：samples 非空字典且 evaluated ≥ 1（形状硬条件）。
    check 对既有 findings.json 复跑（含历史批次，如 r132 存档）；run 等价
    于 check 并把报告落 --out。与 D-053 配套：宿主臂全量评测预算恢复以
    本门禁通过为前提。

用法示例:
    py review-quality-gate.py check --findings <findings.json>
    py review-quality-gate.py run --findings <findings.json> --out reports/_work/rqg-r138.json

退出码:
    0 = PASS（四项检查全过）
    1 = 护栏失败（EMPTY_BATCH_NO_NOTE / LOW_EVIDENCE_COVERAGE / HIGH_UNPARSED / BAD_SHAPE）
    2 = 输入/环境错误（findings 缺失、不可解析、形状非字典）
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "skills" / "eval-harness" / "eval-config.toml"


def load_eval_config():
    """eval-config.toml → dict；缺失/坏文件回退空 dict（内置默认兜底）。"""
    try:
        return tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_findings(path):
    """findings.json → (data, error)；error 非 None 即 code=2。"""
    p = Path(path)
    if not p.is_file():
        return None, "findings 不存在: %s" % p
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, "findings 不可解析: %s" % e
    if not isinstance(data, dict) or not isinstance(data.get("samples"), dict):
        return None, "形状错误：期望顶层 {\"samples\": {样本: [...]}}"
    return data, None


def run_checks(data, min_evidence=0.8, max_unparsed=0.1):
    """四项检查 → (checks 列表, ok)。checks 每项 {id, status, value, ...}。"""
    samples = data.get("samples") or {}
    evaluated = len(samples)
    total_findings = sum(len(v or []) for v in samples.values())
    unparsed = len(data.get("unparsed") or [])
    checks = []
    # C4 batch_shape（形状硬条件）
    shape_ok = evaluated >= 1
    checks.append({"id": "batch_shape", "status": "PASS" if shape_ok else "FAIL",
                   "value": evaluated,
                   "detail": "samples 非空且 evaluated>=1"})
    # C1 empty_batch_note
    empty_batch = total_findings == 0
    note = data.get("batch_note") or ""
    note_ok = (not empty_batch) or bool(str(note).strip())
    checks.append({"id": "empty_batch_note", "status": "PASS" if note_ok else "FAIL",
                   "value": len(str(note)) if empty_batch else "n/a",
                   "detail": ("全空批次（findings=0）必须有 batch_note 说明"
                              if empty_batch else "非全空批次，不适用")})
    # C2 evidence_coverage
    if total_findings:
        all_f = [f for v in samples.values() for f in (v or [])]
        with_ev = sum(1 for f in all_f
                      if isinstance(f, dict) and str(f.get("evidence") or "").strip())
        cov = with_ev / len(all_f)
        checks.append({"id": "evidence_coverage", "status": "PASS" if cov >= min_evidence else "FAIL",
                       "value": round(cov, 4), "threshold": min_evidence,
                       "detail": "%d/%d findings 带非空 evidence" % (with_ev, len(all_f))})
    else:
        checks.append({"id": "evidence_coverage", "status": "SKIPPED",
                       "value": None, "detail": "无 findings，跳过"})
    # C3 unparsed_rate
    rate = (unparsed / evaluated) if evaluated else 1.0
    checks.append({"id": "unparsed_rate", "status": "PASS" if rate <= max_unparsed else "FAIL",
                   "value": round(rate, 4), "threshold": max_unparsed,
                   "detail": "unparsed %d / evaluated %d" % (unparsed, evaluated)})
    ok = all(c["status"] in ("PASS", "SKIPPED") for c in checks)
    return checks, ok


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="评审响应质量门禁（D-053 对策）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for verb in ("run", "check"):
        p = sub.add_parser(verb, help="对 findings.json 跑四项质量检查")
        p.add_argument("--findings", required=True)
        p.add_argument("--min-evidence", type=float, default=None)
        p.add_argument("--max-unparsed", type=float, default=None)
        if verb == "run":
            p.add_argument("--out", required=True)
        else:
            p.add_argument("--out", default="")
    args = ap.parse_args()
    cfg = load_eval_config().get("review_quality_gate", {})
    min_ev = args.min_evidence if args.min_evidence is not None else cfg.get("min_evidence", 0.8)
    max_up = args.max_unparsed if args.max_unparsed is not None else cfg.get("max_unparsed", 0.1)
    data, error = load_findings(args.findings)
    if error:
        _emit({"ok": False, "gate": "review-quality-gate", "error": error})
        return 2
    checks, ok = run_checks(data, min_ev, max_up)
    result = {"ok": ok, "gate": "review-quality-gate",
              "findings": args.findings,
              "checks": checks,
              "failed": [c["id"] for c in checks if c["status"] == "FAIL"],
              "note": "D-053 对策：全 [] 批次必须有 batch_note；"
                      "evidence 覆盖率与 unparsed 率为执行质量下限"}
    if getattr(args, "out", ""):
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        result["out"] = args.out
    _emit(result)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
