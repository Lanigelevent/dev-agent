#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开精度报告生成器：把评测链结果整理为可对外发布的精度报告。

对标业界"敢公开 precision 数字"的实践：报告含方法论（判分口径/weak 剔除）、
合成基线结果、可选前向基准双指标、可选真实语料口径（与合成基线并排 +
缺陷类覆盖表——规则边界由真实数据测量，不粉饰）、引擎指纹与污点配置摘要、
如实声明的局限与复现命令。

编排方式：内部调用 forward-bench.py synth + fp（子进程，参数列表），
可选 --judge（前向基准双指标）、--real/--real-samples（真实语料口径，
如 run-samples + judge 在真实仓库历史上的输出）。

用法示例：
    py precision-report.py --count 120 --out reports
    py precision-report.py --count 120 --out reports \
        --real judge.json --real-samples samples.json --real-repo urllib3
    py precision-report.py --count 120 --out reports \
        --cost-report eval-cost-report-agent.json \
        --merge-audit reports/swebench/merge-audit-r48.json

--cost-report 接 eval-cost-report.py 的 JSON（成本归一章节）；
--merge-audit 接合并率抽检 JSON（评审人/人工复核状态原样随附，不拔高为人工评审）。

产物名按日期（precision-report-<date>.md/.json），**同一天再跑默认被拒**：报告里的数字
是结案证据引用的对象（如 round-6 引的 reports/precision-report-2026-10-24.md），
同日被下一份数字盖掉就等于把证据改了。确要重写当天那份加 --force。

退出码：0=成功；2=输入错误、评测链失败、或拒绝覆盖当日已有报告。
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BENCH = ROOT / "skills" / "eval-harness" / "scripts" / "forward-bench.py"
TAINT_CONFIG = ROOT / "skills" / "multi-agent-review" / "taint-config.json"
FINGERPRINT = ROOT / "skills" / "eval-harness" / "scripts" / "fingerprint.py"

LIMITATIONS = [
    "本报告为确定性评审器口径（38 条硬规则 + 可配置污点引擎），不含真实模型评审",
    "合成语料证明「报出的都是真的」；真实语料测量「规则类覆盖了哪些真实缺陷」，两者互补",
    "污点引擎覆盖：同文件直线传播 + 跨文件两遍分析（顶层函数摘要）；无清洗点建模",
    "判分口径：命中 ground-truth ±1 行计入；单文件 gt 标识符不足的 weak 样本剔除分母",
]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _run_bench(args):
    proc = subprocess.run([sys.executable, str(BENCH)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=600, cwd=str(ROOT))
    return proc.returncode, proc.stdout, proc.stderr


def _load_real(real_path, samples_path, repo_name):
    """单仓真实口径指标与缺陷类覆盖。"""
    judge = json.loads(Path(real_path).read_text(encoding="utf-8"))
    meta = {"judge": {k: judge.get(k) for k in
                      ("recall", "precision", "claimed", "grounded",
                       "valid_samples", "weak")},
            "repo": repo_name,
            "per_sample": [p for p in judge.get("per_sample") or []
                           if isinstance(p, dict)]}
    if not samples_path:
        return meta
    data = json.loads(Path(samples_path).read_text(encoding="utf-8"))
    samples = data.get("samples") if isinstance(data, dict) else data
    per = {p.get("sample_id"): p for p in meta["per_sample"]}
    total_by_class, claimed_by_class = {}, {}
    for s in samples or []:
        if not isinstance(s, dict):
            continue
        cls = s.get("defect_class", "未知")
        total_by_class[cls] = total_by_class.get(cls, 0) + 1
        entry = per.get(s.get("fix_commit")) or {}
        if entry.get("claimed"):
            claimed_by_class[cls] = claimed_by_class.get(cls, 0) + 1
    meta["class_coverage"] = [
        {"defect_class": cls, "total": n,
         "claimed": claimed_by_class.get(cls, 0)}
        for cls, n in sorted(total_by_class.items(), key=lambda kv: -kv[1])]
    return meta


def _aggregate_real(entries):
    """多仓聚合：求和重算 recall/precision，合并类覆盖与 per-repo 表。"""
    if not entries:
        return None
    valid = sum((e.get("judge") or {}).get("valid_samples", 0) or 0
                for e in entries)
    claimed = sum((e.get("judge") or {}).get("claimed", 0) or 0
                  for e in entries)
    grounded = sum((e.get("judge") or {}).get("grounded", 0) or 0
                   for e in entries)
    weak = sum((e.get("judge") or {}).get("weak", 0) or 0 for e in entries)
    agg = {"recall": round(grounded / valid, 4) if valid else None,
           "precision": round(grounded / claimed, 4) if claimed else None,
           "claimed": claimed, "grounded": grounded,
           "valid_samples": valid, "weak": weak}
    merged_cls = {}
    for e in entries:
        for row in e.get("class_coverage") or []:
            cur = merged_cls.setdefault(row["defect_class"],
                                        {"total": 0, "claimed": 0})
            cur["total"] += row["total"]
            cur["claimed"] += row["claimed"]
    agg["class_coverage"] = [
        {"defect_class": cls, **vals}
        for cls, vals in sorted(merged_cls.items(), key=lambda kv: -kv[1]["total"])]
    agg["per_repo"] = [
        {"repo": e.get("repo"), "valid": (e.get("judge") or {}).get("valid_samples"),
         "claimed": (e.get("judge") or {}).get("claimed"),
         "grounded": (e.get("judge") or {}).get("grounded"),
         "recall": (e.get("judge") or {}).get("recall"),
         "precision": (e.get("judge") or {}).get("precision")}
        for e in entries]
    return agg


def main():
    parser = argparse.ArgumentParser(description="公开精度报告生成器")
    parser.add_argument("--count", type=int, default=120, help="合成语料样本数")
    parser.add_argument("--out", required=True, help="报告产物目录")
    parser.add_argument("--judge", default="", help="可选：judge 输出 JSON 文件")
    parser.add_argument("--real", action="append", default=[],
                        help="可选：真实语料 judge 输出 JSON（可多次，聚合）")
    parser.add_argument("--real-samples", action="append", default=[],
                        help="可选：与 --real 顺序对应的 samples.json")
    parser.add_argument("--real-repo", action="append", default=[],
                        help="可选：与 --real 顺序对应的来源仓库名")
    parser.add_argument("--cost-report", dest="cost_report", default="",
                        help="可选：eval-cost-report.py 产物 JSON（成本归一章节）")
    parser.add_argument("--merge-audit", dest="merge_audit", default="",
                        help="可选：合并率抽检 JSON（reports/swebench/"
                             "merge-audit-*.json，人工复核状态如实随附）")
    parser.add_argument("--force", action="store_true",
                        help="允许重写同日的精度报告（默认拒绝——报告是当天口径的历史记录）")
    argv = parser.parse_args()
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)

    # 覆盖闸门（round-30 同类排查第 7 项 R4）：产物名只带**日期**，同一天再跑一次
    # 就会把当天那份原地盖掉——而那份是结案证据引用的对象（round-6 的
    # d8c4b419a461 引的就是 reports/precision-report-<date>.md）。闸门放在跑分之前：
    # 合成语料 + 指纹要跑上百秒，不该为一次注定被拒的写入付这个钱。
    today = datetime.date.today().isoformat()
    json_path = out_dir / ("precision-report-%s.json" % today)
    md_path = out_dir / ("precision-report-%s.md" % today)
    existing = [str(p) for p in (json_path, md_path) if p.is_file()]
    if existing and not argv.force:
        _emit({"ok": False,
               "error": "当日报告已存在，拒绝覆盖历史: %s（确要重写加 --force）"
                        % "; ".join(existing)})
        return 2

    # 可选输入先校验再跑分（round-48）：与覆盖闸门同理，坏输入不该先付
    # 合成语料 + 指纹的上百秒
    cost_metrics = None
    if argv.cost_report:
        try:
            cost_data = json.loads(Path(argv.cost_report)
                                   .read_text(encoding="utf-8"))
            metrics = cost_data.get("metrics")
            if not isinstance(metrics, dict):
                raise ValueError("缺少 metrics 段")
            cost_metrics = dict(metrics)
            cost_metrics["kind"] = cost_data.get("kind")
            cost_metrics["label"] = cost_data.get("label")
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "成本报告非法: %s" % exc})
            return 2

    merge_audit = None
    if argv.merge_audit:
        try:
            audit_data = json.loads(Path(argv.merge_audit)
                                    .read_text(encoding="utf-8"))
            m_metrics = audit_data.get("metrics")
            if not isinstance(m_metrics, dict) or not audit_data.get("verdicts"):
                raise ValueError("缺少 metrics/verdicts 段")
            merge_audit = {
                "benchmark": audit_data.get("benchmark"),
                "reviewer": audit_data.get("reviewer"),
                "human_review": audit_data.get("human_review"),
                "metrics": m_metrics,
                "limitations": audit_data.get("limitations") or [],
            }
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "合并率抽检非法: %s" % exc})
            return 2

    rc, _, err = _run_bench(["synth", "--out", str(work / "corpus"),
                             "--count", str(argv.count)])
    if rc != 0:
        _emit({"ok": False, "error": "synth 失败: %s" % err[:300]})
        return 2
    rc, fp_out, err = _run_bench(["fp", "--corpus", str(work / "corpus")])
    if rc != 0:
        _emit({"ok": False, "error": "fp 失败: %s" % err[:300]})
        return 2
    try:
        fp = json.loads(fp_out)
    except ValueError:
        _emit({"ok": False, "error": "fp 输出非 JSON"})
        return 2

    judge_metrics = None
    if argv.judge:
        judge_path = Path(argv.judge)
        if not judge_path.is_file():
            _emit({"ok": False, "error": "judge 文件不存在: %s" % judge_path})
            return 2
        try:
            judge_metrics = json.loads(judge_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "judge JSON 非法: %s" % exc})
            return 2

    real_metrics = None
    if argv.real:
        real_entries = []
        for i, real_path in enumerate(argv.real):
            if not Path(real_path).is_file():
                _emit({"ok": False, "error": "真实口径 judge 不存在: %s" % real_path})
                return 2
            samples_path = (argv.real_samples[i] if i < len(argv.real_samples)
                            else "")
            repo_name = (argv.real_repo[i] if i < len(argv.real_repo)
                         else "repo-%d" % (i + 1))
            try:
                real_entries.append(_load_real(real_path, samples_path,
                                               repo_name))
            except (OSError, ValueError) as exc:
                _emit({"ok": False, "error": "真实口径数据非法: %s" % exc})
                return 2
        real_metrics = _aggregate_real(real_entries)

    fingerprint = _engine_fingerprint()
    taint_cfg = {}
    try:
        taint_cfg = json.loads(TAINT_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        taint_cfg = {}

    # 复现命令必须带全本轮实际用到的可选入参，否则照着它跑出来只有合成基线
    # （成本/合并率章节会消失），等于复现不到同一份报告。
    repro_args = ["--count %d" % argv.count, "--out <目录>"]
    if argv.judge:
        repro_args.append("--judge %s" % argv.judge)
    for i, real_path in enumerate(argv.real):
        repro_args.append("--real %s" % real_path)
        if i < len(argv.real_samples):
            repro_args.append("--real-samples %s" % argv.real_samples[i])
        if i < len(argv.real_repo):
            repro_args.append("--real-repo %s" % argv.real_repo[i])
    if argv.cost_report:
        repro_args.append("--cost-report %s" % argv.cost_report)
    if argv.merge_audit:
        repro_args.append("--merge-audit %s" % argv.merge_audit)

    report = {
        "date": today,
        "count": argv.count,
        "metrics": {k: fp.get(k) for k in
                    ("samples", "clean", "defective", "tp", "fp",
                     "precision", "recall_injected", "clean_fp")},
        "judge": judge_metrics,
        "real": real_metrics,
        "cost": cost_metrics,
        "merge_audit": merge_audit,
        "engine_fingerprint": fingerprint,
        "taint_sinks": len(taint_cfg.get("sinks", {})),
        "taint_sources": len(taint_cfg.get("sources", [])),
        "limitations": LIMITATIONS,
        "repro": "py skills/eval-harness/scripts/precision-report.py "
                 + " ".join(repro_args),
    }
    json_path = out_dir / ("precision-report-%s.json" % today)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")

    md = ["# dev-agent 精度报告（%s）" % today, "",
          "## 结果（合成语料 %d 样本）" % argv.count, "",
          "| 指标 | 值 |", "|---|---|"]
    for key, label in (("precision", "precision（报出的多少是真的）"),
                       ("recall_injected", "recall（注入缺陷的多少被抓到）"),
                       ("clean_fp", "干净样例误报数"),
                       ("tp", "真命中"), ("fp", "误报")):
        md.append("| %s | %s |" % (label, report["metrics"].get(key)))
    if judge_metrics:
        md.append("")
        md.append("## 前向基准双指标")
        md.append("")
        for key in ("recall", "precision", "valid_samples", "weak"):
            if key in judge_metrics:
                md.append("- %s：%s" % (key, judge_metrics[key]))
    if real_metrics:
        md += ["", "## 真实语料口径（多仓库聚合）", ""]
        md.append("- 真实修复提交样本：%s 个（weak %s）"
                  % (real_metrics.get("valid_samples", 0),
                     real_metrics.get("weak", 0)))
        md.append("- 聚合 recall %s / precision %s（claimed %s，grounded %s）"
                  % (real_metrics.get("recall"), real_metrics.get("precision"),
                     real_metrics.get("claimed"), real_metrics.get("grounded")))
        per_repo = real_metrics.get("per_repo") or []
        if per_repo:
            md += ["", "### 分仓库", "",
                   "| 仓库 | 样本 | claimed | grounded | recall | precision |",
                   "|---|---|---|---|---|---|"]
            for row in per_repo:
                md.append("| %s | %s | %s | %s | %s | %s |" % (
                    row.get("repo"), row.get("valid"), row.get("claimed"),
                    row.get("grounded"), row.get("recall"), row.get("precision")))
        coverage = real_metrics.get("class_coverage") or []
        if coverage:
            md += ["", "### 缺陷类覆盖（真实测量的规则边界）", "",
                   "| 缺陷类 | 样本数 | 被报（claimed） |", "|---|---|---|"]
            for row in coverage:
                md.append("| %s | %d | %d |" % (row["defect_class"],
                                                row["total"], row["claimed"]))
            md += ["", "覆盖边界解读：未覆盖类（claimed=0）即当前规则面的已知"
                      "盲区，是规则扩充的优先依据；本报告不粉饰该数字。"]
    if cost_metrics:
        md += ["", "## 成本归一（agent 侧）", "",
               "来源：`%s`（%s）" % (cost_metrics.get("label"),
                                    cost_metrics.get("kind")), "",
               "| 指标 | 值 |", "|---|---|"]
        for key, label in (
                ("samples", "样本数"),
                ("resolved", "resolved"),
                ("integrity_flagged", "完整性拦截"),
                ("malformed_patch", "补丁结构损坏"),
                ("median_elapsed_sec", "单次中位耗时（秒）"),
                ("median_rounds", "中位编码轮数"),
                ("median_edits", "中位编辑数"),
                ("elapsed_per_resolved_sec", "每个 resolved 墙钟成本（秒）")):
            if key in cost_metrics:
                md.append("| %s | %s |" % (label, cost_metrics.get(key)))
        tokens = cost_metrics.get("tokens") or {}
        if tokens.get("available"):
            md.append("| tokens | 总 %s / 单例中位 %s |"
                      % (tokens.get("total"), tokens.get("median_per_instance")))
        else:
            md.append("| tokens | N/A（%s） |" % (tokens.get("reason") or "产物未带"))
        md.append("")
        md.append("成本口径：agent-summary 的墙钟只含编码循环，gold/deepswe 含环境准备与评测开销；都不等于模型算力；"
                  "中位数只描述这一批样本。")
    if merge_audit:
        ma = merge_audit["metrics"]
        md += ["", "## 合并率抽检", "",
               "- 范围：%s" % (merge_audit.get("benchmark") or ""),
               "- 评审人：%s；人工复核：%s" % (
                   merge_audit.get("reviewer") or "未标注",
                   merge_audit.get("human_review") or "未标注"),
               "- 抽检 %s 例：resolved %s，可合并 %s（合并率 %s）" % (
                   ma.get("reviewed"), ma.get("resolved"), ma.get("mergeable"),
                   ma.get("merge_rate")),
               "- 测试通过且可合并：%s（%s）；测试通过但不可合并：%s" % (
                   ma.get("pass_and_mergeable"), ma.get("pass_and_merge_rate"),
                   ma.get("pass_but_unmergeable")),
               "- 驳回原因：%s" % json.dumps(ma.get("reason_counts") or {},
                                            ensure_ascii=False)]
        for item in merge_audit.get("limitations") or []:
            md.append("- 局限：%s" % item)
    md += ["", "## 引擎信息", "",
           "- 内容指纹：`%s`" % fingerprint,
           "- 污点汇点：%d 个 / source：%d 个（taint-config.json，总监治理）"
           % (report["taint_sinks"], report["taint_sources"]),
           "- 跨文件两遍分析：taint-cross.py（顶层函数摘要 + 调用方追踪）", "",
           "## 方法论", "",
           "- 判分：命中 ground-truth ±1 行计入；weak 样本（gt 标识符不足）"
           "剔除分母并单列",
           "- 正/负样例对称生成；clean 样例零误报为回归下限", "",
           "## 局限（如实声明）", ""]
    md += ["- %s" % item for item in LIMITATIONS]
    md += ["", "## 复现", "", "```", report["repro"], "```", ""]
    md_path = out_dir / ("precision-report-%s.md" % today)
    md_path.write_text("\n".join(md), encoding="utf-8", newline="\n")
    _emit({"ok": True, "report_md": str(md_path), "report_json": str(json_path),
           "metrics": report["metrics"],
           "real": bool(real_metrics)})
    return 0


def _engine_fingerprint():
    proc = subprocess.run([sys.executable, str(FINGERPRINT), "--root", "."],
                          shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120,
                          cwd=str(ROOT))
    try:
        return json.loads(proc.stdout).get("fingerprint", "")
    except ValueError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
