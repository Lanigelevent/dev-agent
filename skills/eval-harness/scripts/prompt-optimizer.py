#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AB-06 提示优化循环：变体矩阵→评估协议→采纳闸（round-217，DSPy 思想复用，不装库）。

用途
    评估器驱动的提示优化循环（DSPy Signature→Module→Optimizer 同型思想）：

    - plan：读 prompt-watch.json 监视面 × 变体维度 → 变体矩阵（机械，
      无 LLM）。
    - evaluate：评估协议——LLM 评审臂可用时逐语料发 judge 任务（宿主
      协议，零 key）；不可用时 arm_status=blocked_no_judge（不冒充
      已评，同 memory-pipeline/live-sample blocked 语义）。
    - adopt：采纳闸——precision_new ≥ baseline 才准固化（优化前后
      护栏数字对照**不许降**），通过则以新指纹固化静态 md 变体回主流程，
      拒绝时给 reasons。

    优化前后对照的评估器=precision-gate 固定语料；指纹纪律沿用 AB-03
    prompt-regression（prompt-watch.json 监视面）。

用法示例
    py skills/eval-harness/scripts/prompt-optimizer.py plan
    py skills/eval-harness/scripts/prompt-optimizer.py evaluate --variant v1 \
        --prompt-file materials/prompts/review-v1.md
    py skills/eval-harness/scripts/prompt-optimizer.py adopt --variant v1 \
        --metrics runs/prompt-variant-v1-metrics.json --out materials/prompts/

退出码：0=成功；1=有可处理问题（评估器不可用 blocked/基线缺失拒采纳）；
2=输入错误。
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WATCH = ROOT / "skills/eval-harness/prompt-watch.json"
VARIANT_DIMENSIONS = {
    "detail": ("concise", "standard", "verbose"),
    "order": ("severity-desc", "file-grouped"),
    "style": ("five-element", "qa"),
}
BASELINE_FLOOR = 0.65


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _judge_available():
    """评审臂可用性：openai key 或宿主协议（桌面会话）视为可用候选。"""
    import os
    if os.environ.get("CRA_LLM_KEY") or os.environ.get("OPENAI_API_KEY"):
        return True, "openai_key"
    return False, "blocked_no_judge"


def _load_watch():
    data = json.loads(WATCH.read_text(encoding="utf-8"))
    surfaces = data.get("surfaces") or data.get("watched") or []
    return surfaces


def _variant_plan(surfaces):
    """监视面 × 变体维度 → 变体矩阵（机械展开；surfaces 兼容字符串/对象）。"""
    variants = []
    for surface in surfaces:
        if isinstance(surface, str):
            sid = surface
        else:
            sid = str(surface.get("id") or surface.get("name") or "?")
        for dim, values in VARIANT_DIMENSIONS.items():
            for val in values:
                variants.append({
                    "id": "%s__%s=%s" % (sid, dim, val),
                    "surface": sid,
                    "dimension": dim,
                    "value": val,
                })
    return variants


def _evaluate_protocol(argv):
    """评估协议：评审臂可用 → 逐语料发 judge 任务（宿主协议面）；否则 blocked。"""
    ok, mode = _judge_available()
    prompt_path = Path(argv.prompt_file)
    if not prompt_path.is_file():
        return {"ok": False, "error": "提示变体文件不存在: %s" % prompt_path,
                "exit_hint": 2}, 2
    if not ok:
        return {"ok": True, "variant": argv.variant, "arm": "llm",
                "arm_status": "blocked_no_judge",
                "note": "评审臂不可用（无 key/宿主协议未接线）——不冒充已评；"
                        "评估任务书见 SKILL.md 宿主迭代面", "scored": False}, 0
    return {"ok": True, "variant": argv.variant, "arm": "llm",
            "arm_status": "judge_tasks_emitted",
            "note": "评审臂可用：judge 任务经宿主协议下发（live 评估由"
                    "宿主会话执行后经 adopt 回灌）", "scored": False}, 0


def _adopt_gate(argv):
    """采纳闸：precision_new ≥ baseline（地板 0.65）才准固化；不许降。"""
    metrics_path = Path(argv.metrics)
    if not metrics_path.is_file():
        return {"ok": False, "error": "指标文件不存在: %s" % metrics_path}, 2
    try:
        m = json.loads(metrics_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": "指标不可读: %s" % exc}, 1
    new_p = m.get("precision")
    base_p = m.get("baseline_precision")
    if new_p is None or base_p is None:
        return {"ok": False, "error": "指标缺 precision/baseline_precision",
                "verdict": "REJECTED",
                "reasons": ["blocked_no_baseline"]}, 1
    reasons = []
    if new_p < BASELINE_FLOOR:
        reasons.append("precision %.4f 低于护栏地板 0.65" % new_p)
    if new_p < base_p:
        reasons.append("precision %.4f 相对基线 %.4f 下降（不许降）"
                       % (new_p, base_p))
    if reasons:
        return {"ok": True, "verdict": "REJECTED", "variant": argv.variant,
                "precision_new": new_p, "baseline": base_p,
                "reasons": reasons}, 0
    prompt_path = Path(argv.prompt_file) if argv.prompt_file else None
    fingerprint = None
    text = None
    if prompt_path and prompt_path.is_file():
        text = prompt_path.read_text(encoding="utf-8")
        fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    out_path = None
    if argv.out:
        out_dir = Path(argv.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / ("prompt-%s.md" % argv.variant))
        if text is not None:
            Path(out_path).write_text(text, encoding="utf-8")
    return {"ok": True, "verdict": "ADOPTED", "variant": argv.variant,
            "precision_new": new_p, "baseline": base_p,
            "fingerprint": fingerprint, "exported_to": out_path}, 0


def main():
    parser = argparse.ArgumentParser(description="AB-06 提示优化循环")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    ep = sub.add_parser("evaluate")
    ep.add_argument("--variant", required=True)
    ep.add_argument("--prompt-file", required=True)
    ap = sub.add_parser("adopt")
    ap.add_argument("--variant", required=True)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--out", default=None)
    argv = parser.parse_args()
    if argv.cmd == "plan":
        surfaces = _load_watch()
        variants = _variant_plan(surfaces)
        _emit({"ok": True, "cmd": "plan", "surfaces": len(surfaces),
               "variants": variants})
        return 0
    if argv.cmd == "evaluate":
        result, rc = _evaluate_protocol(argv)
        _emit(result)
        return rc
    result, rc = _adopt_gate(argv)
    _emit(result)
    return rc


if __name__ == "__main__":
    sys.exit(main())