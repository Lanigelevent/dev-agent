#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代官轮报：把坑台账生成本轮复盘报告与下一轮改进候选（自我优化出口）。

输入 retro-ledger.py 维护的 pitfalls.json；产出：
- round-<N>-report.md：本轮坑的分类统计、明细（根因/对策/状态）、改进候选排序；
- round-<N>-candidates.md：机器口径的候选清单（按类别骨架，每条一行建议）；
- stdout 改进候选 JSON（ranked），供 pick-candidate 式消费。
- stdout 另报 open/closed/archived 三态计数；archived（从未是坑）不计入
  closed（真坑已填），轮报头条同样按三态分开写。

**next-round.md 不由本脚本写**（round-28 坑 0ec029ca74bf 的根治）：那份开局检查单是
人工维护的事实源，带验收口径与来源产物；脚本按类别骨架重写会把人工段整片覆盖掉。
机器候选与人工检查单从此分文件、分名字，谁也不再覆盖谁。脚本只在 stdout 里**如实报**
next-round.md 存不存在，不创建、不修改。

轮号：--round 显式指定；缺省取 out 目录下**已有轮号最大值 + 1**。
（不是「文件数 + 1」：归档里缺某一轮时按文件数会算出已存在的轮号，把历史轮报原地覆盖——
round-29 实踩，retro/ 缺 round-9-report.md，27 个文件算出 28，正好盖掉 round-28。）

防重跑护栏（round-156，r155 坑 a5ba44db35ee 对策）：out 目录存在 next-round.md
时（=真仓收官语境），缺省自动编号一律拒绝——自动编号正是 r154 收官被多跑两遍、
生成过早 round-155/156 预览并误入库的根因。真仓跑法必须显式 --round N；沙盒
（无 next-round.md，契约测试与旧流程）自动编号不受影响。确要用自动编号须
--confirm-next 显式确认（越窗生成会进 stdout JSON 的 auto_guard 供审计）。

用法示例：
    py retro-report.py --ledger retro/pitfalls.json --out retro --round 156
    py retro-report.py --ledger retro/pitfalls.json --out retro   # 沙盒（无 next-round.md）

退出码：0=成功；2=输入错误（台账缺失/JSON 非法/真仓缺省自动编号被护栏拒绝）。
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

CATEGORY_WEIGHT = {"回滚": 3, "补丁返工": 2, "误报": 2, "行为回归": 3,
                   "转人工": 1, "手工": 1}
CATEGORY_SUGGESTION = {
    "回滚": "缩小补丁粒度，一次只修一处；为被修行为补仓库测试",
    "行为回归": "修复前先读懂行为契约；有测试的行为变更需人工确认",
    "补丁返工": "出补丁前在本地预演闸 2 六项检查（工单绑定/导入白名单等）",
    "误报": "为该模式补阴性样例并入经验库，必要时收紧规则形态",
    "转人工": "核对机械修复策略盲区，评估是否扩展白名单",
    "手工": "纳入下一轮改进候选，明确责任与验收口径",
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


ROUND_RE = re.compile(r"^round-(\d+)-report\.md$")


def _next_round(out_dir):
    """缺省轮号 = 已有轮号最大值 + 1（round-29 根治）。

    旧口径是 `len(glob) + 1`，即「轮报文件数 + 1」。归档一旦缺轮就必然算出一个
    **已经存在**的轮号并把那一轮的历史轮报原地覆盖：retro/ 缺 round-9-report.md，
    27 个文件 → 28，正好盖掉 round-28。取最大值而不是个数，缺轮只影响连续性，
    不会再撞名。
    """
    nums = []
    for path in out_dir.glob("round-*-report.md"):
        m = ROUND_RE.match(path.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) + 1 if nums else 1


def _candidates(pitfalls):
    """按 权重×数量 排序的改进候选。"""
    by_cat = Counter(p["category"] for p in pitfalls if p.get("status") == "open")
    ranked = sorted(by_cat.items(),
                    key=lambda kv: (-CATEGORY_WEIGHT.get(kv[0], 0) * kv[1], kv[0]))
    out = []
    for category, count in ranked:
        out.append({
            "title": "%s：%d 个未结坑" % (category, count),
            "category": category, "count": count,
            "suggestion": CATEGORY_SUGGESTION.get(category, "纳入下一轮改进候选"),
            "pitfall_ids": [p["id"] for p in pitfalls
                            if p.get("status") == "open"
                            and p["category"] == category],
        })
    return out


def _render_markdown(round_no, pitfalls, candidates):
    open_items = [p for p in pitfalls if p.get("status") == "open"]
    archived = [p for p in pitfalls if p.get("status") == "archived"]
    closed = [p for p in pitfalls
              if p.get("status") not in ("open", "archived")]
    lines = ["# 复盘轮报 round-%d" % round_no, ""]
    lines.append("open %d / closed %d / archived %d"
                 % (len(open_items), len(closed), len(archived)))
    lines.append("")
    lines.append("## 分类统计")
    lines.append("")
    for category, count in sorted(Counter(p["category"] for p in pitfalls).items(),
                                  key=lambda kv: -kv[1]):
        lines.append("- %s：%d" % (category, count))
    lines.append("")
    lines.append("## 未结坑明细")
    lines.append("")
    lines.append("| ID | 类别 | 坑 | 根因 | 对策 | 来源 |")
    lines.append("|---|---|---|---|---|---|")
    for p in open_items:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            p["id"], p["category"], p["description"][:60].replace("|", "\\|"),
            (p.get("root_cause") or "-")[:40].replace("|", "\\|"),
            (p.get("countermeasure") or "-")[:40].replace("|", "\\|"),
            p.get("source", "-").replace("|", "\\|")))
    lines.append("")
    lines.append("## 改进候选（按 权重×数量 排序）")
    lines.append("")
    for cand in candidates:
        lines.append("- **%s** — %s" % (cand["title"], cand["suggestion"]))
    return "\n".join(lines) + "\n"


def _render_candidates(round_no, candidates):
    """机器口径的候选清单 —— 名字带轮号，与人工维护的 next-round.md 永不同名。"""
    lines = ["# round-%d 改进候选（机器产出）" % round_no, "",
             "本文件由 `retro-report.py` 每次重写，**只落类别骨架**；",
             "开局检查单 `next-round.md` 归人工维护（带验收口径与来源），"
             "本脚本不创建也不修改它。", "",
             "排序口径：类别权重 × 未结坑数（回滚/行为回归 3，补丁返工/误报 2，其余 1）。",
             ""]
    for i, cand in enumerate(candidates, 1):
        lines.append("%d. [%s] %s —— %s" % (
            i, cand["category"], cand["title"], cand["suggestion"]))
        lines.append("   未结坑：%s" % "、".join(cand["pitfall_ids"]))
    if not candidates:
        lines.append("（无未结坑，本轮可全新开工）")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="迭代官轮报（复盘与候选排序）")
    parser.add_argument("--ledger", required=True, help="pitfalls.json 路径")
    parser.add_argument("--out", required=True, help="复盘目录")
    parser.add_argument("--round", type=int, default=0, help="轮号（缺省自增）")
    parser.add_argument("--force", action="store_true",
                        help="允许重写已存在的同轮产物（默认拒绝——轮报是历史记录）")
    parser.add_argument("--confirm-next", action="store_true", dest="confirm_next",
                        help="真仓（out 目录有 next-round.md）确认使用缺省自动编号"
                             "（默认拒绝——r155 坑 a5ba44db35ee）")
    argv = parser.parse_args()
    ledger = Path(argv.ledger)
    out_dir = Path(argv.out)
    if not ledger.is_file():
        _emit({"ok": False, "error": "台账不存在: %s" % ledger})
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(ledger.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "台账 JSON 非法: %s" % exc})
        return 2
    pitfalls = data.get("pitfalls", [])
    round_no = argv.round or _next_round(out_dir)
    round_source = "explicit" if argv.round else "auto"
    # 防重跑护栏（round-156，r155 坑 a5ba44db35ee）：真仓（out 目录有
    # next-round.md）缺省自动编号一律拒绝——r154 收官被多跑两遍生成过早
    # round-155/156 预览并误入库的根因就是无 --round 自动编号。沙盒（无
    # next-round.md）保留自动编号（契约测试与旧流程兼容）。
    auto_guard = None
    if not argv.round:
        next_path = out_dir / "next-round.md"
        if next_path.is_file():
            auto_guard = {"topline_file": str(next_path),
                          "confirm_next": bool(argv.confirm_next)}
            if not argv.confirm_next:
                _emit({"ok": False,
                       "error": "真仓缺省自动编号已被护栏拒绝（out 目录存在 "
                                "next-round.md）：%s（请显式 --round N；确要用"
                                "自动编号加 --confirm-next，r155 坑 "
                                "a5ba44db35ee）" % next_path})
                return 2
    candidates = _candidates(pitfalls)
    report_path = out_dir / ("round-%d-report.md" % round_no)
    candidates_path = out_dir / ("round-%d-candidates.md" % round_no)
    # 覆盖闸门（round-30 同类排查第 7 项）：`_next_round` 改成「最大轮号 + 1」之后，
    # 缺省路径不会再撞号，但**显式 --round 给号**仍能绕过它原地盖掉另一轮的历史
    # ——round-29 就是这样把已归档的 round-28-report.md 重写了一遍（靠 git 才还原）。
    # 轮报与候选是历史记录，不是可重算的缓存：默认拒绝，重写要明说 --force。
    if report_path.is_file() and not argv.force:
        _emit({"ok": False,
               "error": "轮报已存在，拒绝覆盖历史: %s（确要重写这一轮加 --force）"
                        % report_path})
        return 2
    report_path.write_text(_render_markdown(round_no, pitfalls, candidates),
                           encoding="utf-8", newline="\n")
    candidates_path.write_text(_render_candidates(round_no, candidates),
                               encoding="utf-8", newline="\n")
    # 人工检查单：只读存在性，绝不写。写它的是人，不是脚本。
    next_path = out_dir / "next-round.md"
    _emit({"ok": True, "round": round_no, "report": str(report_path),
           "round_source": round_source,
           "auto_guard": auto_guard,
           "forced_overwrite": bool(argv.force),
           "candidates_file": str(candidates_path),
           "next_round": str(next_path) if next_path.is_file() else None,
           "next_round_untouched": True,
           "open": sum(1 for p in pitfalls if p.get("status") == "open"),
           "closed": sum(1 for p in pitfalls if p.get("status") == "closed"),
           "archived": sum(1 for p in pitfalls if p.get("status") == "archived"),
           "candidates": candidates})
    return 0


if __name__ == "__main__":
    sys.exit(main())
