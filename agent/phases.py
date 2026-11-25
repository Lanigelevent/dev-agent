#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子代理分解（阶段四 4.1）：定位/修复/验证三角色与主循环裁决。

用途：
    code-task.py 的 --phases 模式内核。把单循环拆成三个阶段，每阶段只暴露
    本角色需要的动作面，主循环只做裁决（accept / rework / escalate）：

      locate（定位，只读）：read / list / search / probe → 以 locate_done
          交结构化定位报告（files / root_cause / confidence）
      fix（修复，可写）：完整动作面（含 edit）→ 测试通过或 done 后交裁决
      verify（验证，只读）：read / list / search + verdict → 不执行代码，
          产出 {pass, reasons, checks}；裁决规则：**机械测试结果优先**——
          tests != pass 时 verdict.pass 一律不算数（防「自评绿」）

    预算：locate 有独立轮数上限（--locate-rounds，耗尽降级进 fix 并在裁决
    台账记 degrade）；verify 每次拒收消耗一次返工（--rework-max，耗尽升级
    ESCALATED）；全局轮数（--rounds）仍由 code-task 主循环扣减，任何阶段都
    不越界。

    裁决审计：每个决定写入 <out>/phases.json（seq/phase/decision/reason/
    round/tests）；跨 WAIT_HOST_LLM 由 task-meta.json 的 phases 块恢复，
    --resume 不重放已裁决的阶段。

用法示例（库，由 code-task.py 调用；本模块无退出码）：
    ph = PhaseState.load(state.data, out_dir, enabled=True,
                         locate_rounds=2, rework_max=2)
    ph.gate("edit")                       # -> None 或拒收说明
    ph.accept_locate(report, round_no=2)
    ph.request_verify(round_no=3, tests="pass")
    ph.register_verdict(action, tests="pass", round_no=4)
    ph.role_section(task=..., locate_report=..., diff=..., tests=...)
"""
import json
from pathlib import Path

PHASES = ("locate", "fix", "verify")

# 角色动作面：locate/verify 一律无 edit（只读），fix 才可写。
ALLOWED = {
    "locate": ("read", "list", "search", "probe", "locate_done"),
    "fix": ("read", "list", "search", "probe", "edit", "done"),
    "verify": ("read", "list", "search", "verdict"),
}

ROLE_TITLE = {
    "locate": "## 阶段：定位（locate 子代理，只读）",
    "fix": "## 阶段：修复（fix 子代理）",
    "verify": "## 阶段：验证（verify 子代理，只读）",
}

ROLE_TEXT = {
    "locate": (
        "\n本阶段只做定位，不改代码（edit 会被主循环拒绝）。用 read / list / "
        "search / probe 找出：要改哪些文件、每处为什么、根因是什么。\n"
        "完成时输出：\n"
        '{"action":"locate_done","files":[{"path":"相对路径","why":"为什么要改"},...],'
        '"root_cause":"一句话根因","confidence":"high|medium|low","notes":"可选"}\n'
        "files 至少一项；不确定时把候选列全并把 confidence 标 low（宁可多列，"
        "不要漏）。定位轮数用尽会自动降级进入修复阶段。"
    ),
    "fix": (
        "\n本阶段负责把改动落到工作区：edits 用 SEARCH/REPLACE，SEARCH 必须与"
        "当前文件实际内容逐字一致。仓库测试通过后本阶段自动交验证；也可用 "
        "done 提前交（测试未过时验证大概率退回）。若验证退回，材料里会附拒收"
        "理由，据此返工。"
    ),
    "verify": (
        "\n本阶段只做验证，不得编辑（edit 会被主循环拒绝）。核对任务要求是否"
        "真的满足（不只看测试通过），检查补丁是否覆盖定位报告里的每一处、是否"
        "引入无关改动。\n完成时输出：\n"
        '{"action":"verdict","pass":true|false,"reasons":["拒收或通过的具体理由"],'
        '"checks":[{"name":"检查项","status":"pass|fail","evidence":"证据"}]}\n'
        "机械事实：测试状态由主循环给出；tests 不是 pass 时 pass=true 无效。"
    ),
}


def _clip(text, max_chars):
    text = str(text or "")
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + "\n...（已截断 %d 字）" % (len(text) - max_chars)
    return text


def _render_report(report, max_files=30):
    if not isinstance(report, dict):
        return ""
    files = report.get("files") or []
    lines = ["## 定位报告（locate 子代理）"]
    for item in files[:max_files]:
        if isinstance(item, dict):
            lines.append("- %s：%s" % (item.get("path", "?"),
                                       str(item.get("why", ""))[:200]))
        else:
            lines.append("- %s" % item)
    for key, label in (("root_cause", "根因"), ("confidence", "置信度"),
                       ("notes", "备注")):
        val = str(report.get(key) or "").strip()
        if val:
            lines.append("- %s：%s" % (label, val[:400]))
    return "\n".join(lines)


class PhaseState:
    """三阶段状态机 + 裁决台账（可跨 --resume 持久化）。"""

    SCHEMA = 1

    def __init__(self, block, path):
        self.data = block
        self.path = Path(path)

    # ---- 构造与持久化 -------------------------------------------------
    @classmethod
    def load(cls, task_data, out_dir, enabled=False, locate_rounds=2,
             rework_max=2):
        block = task_data.get("phases")
        if not isinstance(block, dict) or block.get("_schema") != cls.SCHEMA:
            block = {
                "_schema": cls.SCHEMA,
                "enabled": bool(enabled),
                "current": PHASES[0],
                "locate_rounds_used": 0,
                "locate_rounds_max": max(1, int(locate_rounds)),
                "rework_count": 0,
                "rework_max": max(0, int(rework_max)),
                "decisions": [],
                "verdicts": [],
                "locate_report": None,
                "last_reasons": [],
                "resolved": False,
                "escalated": False,
                "reason": "",
            }
        task_data["phases"] = block
        return cls(block, Path(out_dir) / "phases.json")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False,
                                        indent=2),
                             encoding="utf-8", newline="\n")

    # ---- 查询 ---------------------------------------------------------
    @property
    def enabled(self):
        return bool(self.data.get("enabled"))

    @property
    def phase(self):
        return str(self.data.get("current") or PHASES[0])

    @property
    def resolved(self):
        return bool(self.data.get("resolved"))

    @property
    def escalated(self):
        return bool(self.data.get("escalated"))

    def gate(self, action):
        """动作面门禁：返回 None 表示放行，否则返回拒收说明。"""
        if not self.enabled:
            return None
        allowed = ALLOWED.get(self.phase, ())
        if action in allowed:
            return None
        return ("动作 %s 在 %s 阶段不可用（该阶段只允许：%s）"
                % (action, self.phase, " / ".join(allowed)))

    def role_section(self, task="", locate_report=None, diff="", tests="skip",
                     max_chars=6000):
        """当前阶段的材料补充段（拼在稳定前缀之后、历史之前）。"""
        if not self.enabled:
            return ""
        parts = [ROLE_TITLE[self.phase], ROLE_TEXT[self.phase]]
        report = locate_report if locate_report is not None else \
            self.data.get("locate_report")
        if self.phase == "fix":
            if report:
                parts.append(_render_report(report))
            reasons = self.data.get("last_reasons") or []
            if reasons:
                parts.append("## 验证退回理由（返工请逐条处理）\n"
                             + "\n".join("- %s" % str(r)[:300] for r in reasons))
            parts.append("- 当前测试状态：%s" % tests)
        if self.phase == "verify":
            if report:
                parts.append(_render_report(report))
            parts.append("- 补丁（git diff，工作区 vs 基线）：\n```diff\n%s\n```"
                         % _clip(diff or "（空——本阶段前没有生效编辑）",
                                 max_chars))
            parts.append("- 当前测试状态：%s" % tests)
        return "\n\n".join(parts)

    # ---- 裁决记录 -----------------------------------------------------
    def _record(self, phase, decision, reason, round_no=None, tests=None,
                save=True):
        seq = len(self.data.setdefault("decisions", [])) + 1
        self.data["decisions"].append({
            "seq": seq, "phase": phase, "decision": decision,
            "reason": str(reason or "")[:500], "round": round_no,
            "tests": tests,
        })
        if save:
            self.save()
        return seq

    def note_locate_round(self):
        self.data["locate_rounds_used"] = int(
            self.data.get("locate_rounds_used") or 0) + 1

    # ---- 阶段转移 -----------------------------------------------------
    def accept_locate(self, report, round_no=None):
        """locate_done → fix。报告为空时按降级处理并记 degrade。"""
        report = report if isinstance(report, dict) else {}
        files = [f for f in (report.get("files") or []) if f]
        self.data["locate_report"] = report
        if files:
            self._record("locate", "accept",
                         "定位报告 %d 个文件（confidence=%s）"
                         % (len(files), report.get("confidence") or "?"),
                         round_no=round_no, save=False)
            self.data["current"] = "fix"
        else:
            self._record("locate", "degrade",
                         "定位报告无 files，降级进修复", round_no=round_no,
                         save=False)
            self.data["current"] = "fix"
        self.save()

    def degrade_locate(self, round_no=None, why="定位轮数用尽"):
        if self.phase != "locate":
            return
        self._record("locate", "degrade", why, round_no=round_no, save=False)
        self.data["current"] = "fix"
        self.save()

    def request_verify(self, round_no=None, tests="skip", why="修复阶段结束"):
        """fix → verify（测试通过、done 或轮数用尽都走这里）。"""
        if self.phase != "fix":
            return
        self._record("fix", "accept", why, round_no=round_no, tests=tests,
                     save=False)
        self.data["current"] = "verify"
        self.save()

    def register_verdict(self, action, tests, round_no=None):
        """verify 裁决：机械测试结果优先；pass 且测试绿才算 resolved。"""
        verdict = action if isinstance(action, dict) else {}
        passed = bool(verdict.get("pass"))
        reasons = [str(r) for r in (verdict.get("reasons") or []) if str(r)]
        checks = verdict.get("checks") or []
        self.data.setdefault("verdicts", []).append({
            "round": round_no, "pass": passed, "reasons": reasons,
            "checks": checks, "tests": tests,
        })
        if tests != "pass":
            self._record("verify", "reject",
                         "机械测试未通过（tests=%s），verdict.pass=%s 不算数"
                         % (tests, passed), round_no=round_no, tests=tests,
                         save=False)
            self._rework(round_no, tests,
                         reasons or ["仓库测试未通过"])
            return
        if not passed:
            self._record("verify", "reject",
                         "验证拒收：%s" % ("；".join(reasons)[:400] or "未给理由"),
                         round_no=round_no, tests=tests, save=False)
            self._rework(round_no, tests, reasons or ["验证拒收（未给理由）"])
            return
        self._record("verify", "accept",
                     "验证通过且测试绿：%s"
                     % ("；".join(reasons)[:300] or "无附加理由"),
                     round_no=round_no, tests=tests, save=False)
        self.data["resolved"] = True
        self.data["last_reasons"] = []
        self.save()

    def _rework(self, round_no, tests, reasons):
        self.data["last_reasons"] = [str(r)[:300] for r in reasons][:8]
        self.data["rework_count"] = int(self.data.get("rework_count") or 0) + 1
        if self.data["rework_count"] > int(self.data.get("rework_max") or 0):
            self.data["escalated"] = True
            self.data["reason"] = "返工 %d 次仍被拒收" % (
                self.data["rework_count"] - 1)
            self.data["current"] = "verify"
            self._record("verify", "escalate", self.data["reason"],
                         round_no=round_no, tests=tests, save=False)
        else:
            self.data["current"] = "fix"
            self._record("verify", "rework",
                         "退回修复（第 %d 次）：%s"
                         % (self.data["rework_count"],
                            "；".join(reasons)[:300]),
                         round_no=round_no, tests=tests, save=False)
        self.save()

    def exhaust(self, round_no=None, why="全局轮数用尽"):
        """主循环无轮可扣时收束：未 resolved 一律升级，不静默当完成。"""
        if not self.enabled or self.resolved or self.escalated:
            return
        self.data["escalated"] = True
        self.data["reason"] = why
        self._record(self.phase, "escalate", why, round_no=round_no)

    # ---- 摘要 ---------------------------------------------------------
    def summary(self):
        if not self.enabled:
            return {"enabled": False}
        counts = {}
        for d in self.data.get("decisions") or []:
            counts[d.get("decision", "?")] = counts.get(
                d.get("decision", "?"), 0) + 1
        return {
            "enabled": True,
            "current": self.phase,
            "resolved": self.resolved,
            "escalated": self.escalated,
            "reason": self.data.get("reason", ""),
            "rework_count": int(self.data.get("rework_count") or 0),
            "rework_max": int(self.data.get("rework_max") or 0),
            "locate_rounds_used": int(self.data.get("locate_rounds_used") or 0),
            "locate_rounds_max": int(self.data.get("locate_rounds_max") or 0),
            "decisions": len(self.data.get("decisions") or []),
            "verdicts": len(self.data.get("verdicts") or []),
            "decision_counts": counts,
        }
