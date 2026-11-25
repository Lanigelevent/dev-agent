#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评测成本归一报告：把一次评测产物整理成「样本量 / resolved / 成本」并列的
可复算报告（ROADMAP 阶段一 1.5）。

输入三类产物（按结构自动识别，不重算判分——判分口径由原产物的台账负责）：
    agent-sample-summary.json   agent 侧口径（deepswe 同名同义字段）
    gold-sample-ledger.json     gold/agent 共用的评测台账
    deepswe-sample 结果 JSON     DeepSWE 批量跑分输出（有 results/elapsed_sec）

成本口径：
    - elapsed_sec 是所记链路的墙钟秒：agent-summary 只含编码循环，
      gold/deepswe 结果含环境准备与评测开销；两者都不等于模型算力；
    - 中位数只描述这一批样本，样本量小不构成稳定性结论；
    - token 仅当产物带用量时汇总；host 后端不暴露 token 用量时标 N/A，
      不按字符数估算（估算值会伪装成测量值）。

用法示例:
    py eval-cost-report.py --input datasets/swe-out/agent-sample/eval/agent-sample-summary.json --out reports/evals --label agent-r48
    py eval-cost-report.py --input reports/deepswe/runs/r48.json --out reports/evals --label deepswe-r48

退出码: 0 = 报告已生成；2 = 输入非法、无法识别结构、或拒绝覆盖当日同名报告。
stdout 单 JSON 文档。
"""
import argparse
import datetime
import json
import re
import statistics
import sys
from pathlib import Path

LIMITATIONS = [
    "elapsed_sec 是所记链路的墙钟秒（agent-summary 只含编码循环；gold/deepswe 含环境准备与评测开销），不等于模型算力",
    "中位数只描述这一批样本；样本量小，不构成稳定性或跨模型结论",
    "token 仅当产物带用量时汇总；host 后端标 N/A，不用字符数估算",
    "本报告不重算判分：resolved 直接取原台账/汇总的判定",
    "integrity_flagged 与 malformed_patch 不计入 resolved 分母，单列计数",
]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _detect(data):
    """按结构识别输入类型 → (kind, rows)。"""
    if isinstance(data, dict) and isinstance(data.get("details"), list):
        return "agent-summary", data["details"]
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None, None
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        return None, None
    if "instance_id" in rows[0]:
        return "gold-ledger", rows
    if "id" in rows[0] and ("status" in rows[0] or "elapsed_sec" in rows[0]):
        return "deepswe", rows
    return None, None


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _median(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(statistics.median(vals), 3)


def _normalize(kind, row):
    """统一成 {instance,status,resolved,elapsed,rounds,edits,integrity}。"""
    stats = row.get("code_task") if isinstance(row.get("code_task"), dict) else {}
    if kind == "agent-summary":
        integ = row.get("patch_integrity")
        integ_ok = None
        if isinstance(integ, dict):
            integ_ok = bool(integ.get("ok", True))
        return {
            "instance": row.get("instance_id"),
            "status": row.get("status"),
            "resolved": row.get("resolved"),
            "elapsed": _num(row.get("elapsed_sec")),
            "rounds": _num(row.get("rounds")),
            "edits": _num(row.get("edits")),
            "integrity_flagged": (row.get("status") == "integrity_flagged"
                                  or integ_ok is False),
            "malformed": row.get("status") == "malformed_patch",
        }
    if kind == "gold-ledger":
        return {
            "instance": row.get("instance_id"),
            "status": row.get("state"),
            "resolved": row.get("resolved"),
            "elapsed": _num(row.get("elapsed_sec")),
            "rounds": _num(stats.get("rounds")),
            "edits": _num(stats.get("edits")),
            "integrity_flagged": False,
            "malformed": False,
        }
    status = row.get("status")
    return {
        "instance": row.get("id"),
        "status": status,
        "resolved": (True if status == "resolved"
                     else (False if status in ("unresolved", "integrity_flagged",
                                               "malformed_patch")
                           else None)),
        "elapsed": _num(row.get("elapsed_sec")),
        "rounds": _num(stats.get("rounds") if stats else row.get("rounds")),
        "edits": _num(stats.get("edits") if stats else row.get("edits")),
        "integrity_flagged": status == "integrity_flagged",
        "malformed": status == "malformed_patch",
    }


def _tokens(data, rows):
    top = data.get("tokens") if isinstance(data, dict) else None
    if isinstance(top, dict) and top.get("available") is False:
        return {"available": False,
                "reason": top.get("reason") or "产物声明不可得"}
    vals = []
    for row in rows:
        val = _num(row.get("tokens"))
        if val is not None:
            vals.append(val)
            continue
        usage = row.get("usage")
        if isinstance(usage, dict):
            val = _num(usage.get("total_tokens"))
            if val is not None:
                vals.append(val)
    if not vals:
        return {"available": False,
                "reason": "产物未带 token 用量（host 后端不暴露）"}
    return {"available": True, "total": round(sum(vals), 3),
            "median_per_instance": _median(vals), "instances": len(vals)}


def _summarize(kind, data, rows):
    norm = [_normalize(kind, r) for r in rows]
    resolved = [n for n in norm if n["resolved"] is True]
    unresolved = [n for n in norm
                  if n["resolved"] is False and not n["integrity_flagged"]
                  and not n["malformed"]]
    flagged = [n for n in norm if n["integrity_flagged"]]
    malformed = [n for n in norm if n["malformed"]]
    elapsed_all = [n["elapsed"] for n in norm if n["elapsed"] is not None]
    total_elapsed = round(sum(elapsed_all), 3) if elapsed_all else None
    return {
        "samples": len(norm),
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "undetermined": len(norm) - len(resolved) - len(unresolved)
                        - len(flagged) - len(malformed),
        "integrity_flagged": len(flagged),
        "malformed_patch": len(malformed),
        "resolved_rate": (round(len(resolved) / len(norm), 4)
                          if norm else None),
        "median_elapsed_sec": _median(elapsed_all),
        "median_elapsed_resolved_sec": _median(
            [n["elapsed"] for n in resolved]),
        "median_elapsed_unresolved_sec": _median(
            [n["elapsed"] for n in unresolved]),
        "total_elapsed_sec": total_elapsed,
        "elapsed_per_resolved_sec": (
            round(total_elapsed / len(resolved), 3)
            if total_elapsed is not None and resolved else None),
        "median_rounds": _median([n["rounds"] for n in norm]),
        "median_edits": _median([n["edits"] for n in norm]),
        "tokens": _tokens(data, rows),
        "rows": norm,
    }


def _slug(text):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text or "").strip("-")
    return cleaned or "input"


def _render_md(report):
    m = report["metrics"]
    md = ["# 评测成本归一报告（%s · %s）" % (report["date"],
                                              report["kind"]), "",
          "输入：`%s`" % report["input"], "",
          "## 结果", "",
          "| 指标 | 值 |", "|---|---|"]
    for key, label in (
            ("samples", "样本数"),
            ("resolved", "resolved"),
            ("unresolved", "unresolved"),
            ("undetermined", "未判定（失败/未评）"),
            ("integrity_flagged", "完整性拦截"),
            ("malformed_patch", "补丁结构损坏（截断/无法应用）"),
            ("resolved_rate", "resolved 率")):
        md.append("| %s | %s |" % (label, m.get(key)))
    md += ["", "## 成本（墙钟秒）", "",
           "| 指标 | 值 |", "|---|---|",
           "| 单次中位耗时（全样本） | %s |" % m.get("median_elapsed_sec"),
           "| 单次中位耗时（resolved） | %s |"
           % m.get("median_elapsed_resolved_sec"),
           "| 单次中位耗时（unresolved） | %s |"
           % m.get("median_elapsed_unresolved_sec"),
           "| 总耗时 | %s |" % m.get("total_elapsed_sec"),
           "| 每个 resolved 的墙钟成本 | %s |"
           % m.get("elapsed_per_resolved_sec"),
           "| 中位编码轮数 | %s |" % m.get("median_rounds"),
           "| 中位编辑数 | %s |" % m.get("median_edits")]
    tokens = m.get("tokens") or {}
    md += ["", "## token", ""]
    if tokens.get("available"):
        md.append("- 总用量：%s（%s 例有用量）"
                  % (tokens.get("total"), tokens.get("instances")))
        md.append("- 单例中位：%s" % tokens.get("median_per_instance"))
    else:
        md.append("- N/A：%s" % tokens.get("reason"))
    rows = m.get("rows") or []
    if rows:
        md += ["", "## 逐例", "",
               "| 实例 | 状态 | resolved | 耗时(s) | 轮数 | 编辑数 |",
               "|---|---|---|---|---|---|"]
        for row in rows[:100]:
            md.append("| %s | %s | %s | %s | %s | %s |" % (
                row.get("instance"), row.get("status"), row.get("resolved"),
                row.get("elapsed"), row.get("rounds"), row.get("edits")))
        if len(rows) > 100:
            md.append("")
            md.append("（仅列前 100 例，完整明细见 JSON）")
    md += ["", "## 局限（如实声明）", ""]
    md += ["- %s" % item for item in LIMITATIONS]
    md += ["", "## 复现", "", "```", report["repro"], "```", ""]
    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="评测成本归一报告")
    parser.add_argument("--input", required=True, help="评测产物 JSON")
    parser.add_argument("--out", required=True, help="报告产物目录")
    parser.add_argument("--label", default="",
                        help="报告名标签（默认 input）；同日同名默认拒绝覆盖")
    parser.add_argument("--force", action="store_true",
                        help="允许重写同日同名报告")
    argv = parser.parse_args()

    input_path = Path(argv.input)
    if not input_path.is_file():
        return _param_error("输入不存在: %s" % input_path)
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _param_error("输入 JSON 非法: %s" % exc)
    kind, rows = _detect(data)
    if not kind:
        return _param_error("无法识别输入结构（需 agent-sample-summary / "
                            "gold-sample-ledger / deepswe results）")

    today = datetime.date.today().isoformat()
    slug = _slug(argv.label)
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / ("eval-cost-report-%s-%s.json" % (slug, today))
    md_path = out_dir / ("eval-cost-report-%s-%s.md" % (slug, today))
    existing = [str(p) for p in (json_path, md_path) if p.is_file()]
    if existing and not argv.force:
        return _param_error("当日同名报告已存在，拒绝覆盖历史: %s（确要重写加 "
                            "--force）" % "; ".join(existing))

    metrics = _summarize(kind, data, rows)
    report = {
        "date": today,
        "kind": kind,
        "label": slug,
        "input": str(input_path),
        "metrics": {k: v for k, v in metrics.items() if k != "rows"},
        "limitations": LIMITATIONS,
        "repro": "py skills/eval-harness/scripts/eval-cost-report.py "
                 "--input %s --out %s --label %s" % (
                     input_path, out_dir, slug),
    }
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    md_path.write_text(_render_md(report), encoding="utf-8", newline="\n")
    _emit({"ok": True, "kind": kind, "report_md": str(md_path),
           "report_json": str(json_path),
           "metrics": report["metrics"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
