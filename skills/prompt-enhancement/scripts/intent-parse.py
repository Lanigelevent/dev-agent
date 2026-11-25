#!/usr/bin/env python3
"""意图解析：从用户原话机械提取评审对象、范围、深度档与意图分级。

用途:
    主流程步骤 1。解析 --request 文本，判定 sha/分支/PR/整个仓库四类对象，
    输出深度档（quick/standard/deep）与意图分级（A/B/C），供后续派发与材料构造使用。
    v1.33.0 起同时输出模糊意图三件套（均为附加键，老调用方零改动）：
    ambiguity（同维度多个候选信号与裁决规则）、assumptions（本次解析采用的
    假设：假设 + 依据 + 错了的代价）、confirmations（非阻塞待确认项，供调用方
    随回复带给用户核对）。阻塞式追问仍走 questions（最多 1 条）与退出码 3，
    单问制纪律不变——能用假设顶住的就不问，问就只问最关键的那件事。
    v1.36.0 起再附 compound_clauses（复合子句检测，「顺便把测试也补全」这类
    搭车请求拆解线索，任务流水线 task-pipeline 拆解时据此追加子任务）；且对象
    维度 ambiguity 收录悬空指代的多解读——「评审那块」这类指代在单轮输入里
    解析不了，不确定性不许只被 B 级默认假设吸收，被拒备选必须显式列出
    （round-35 消化坑 791468dc0ca2）。

用法:
    python intent-parse.py --request "review PR #12，快速看下" --repo /path/to/repo

退出码:
    0 = 可开审（A/B 级）
    3 = 需追问（C 级：对象无法确定或请求自相矛盾）
    2 = 参数错误（缺 --request）
"""
import argparse
import json
import re
import sys

SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
HEAD_RE = re.compile(r"\bHEAD(?:~\d+)?\b")
RANGE_RE = re.compile(r"\b([\w./~-]+)\.\.([\w./~-]+)\b")
BRANCH_RE = re.compile(r"(?:分支|branch)\s+([\w./~-]+)", re.I)
PR_RE = re.compile(r"(?:\bPR\s*#?|#)(\d+)\b", re.I)
WHOLE_RE = re.compile(r"整个仓库|全部代码|whole\s+repo|all\s+code", re.I)
QUICK_RE = re.compile(r"快速|大概|粗略|大致|quick", re.I)
DEEP_RE = re.compile(r"仔细|全面|深入|详细|thorough|deep", re.I)
PATH_RE = re.compile(r"\b[\w./-]+\.(?:py|js|ts|go|java|c|cpp|h|rb|rs|md|json|ya?ml|toml|sql)\b")
VALUE_WORDS = {"str", "int", "bool", "bytes", "object", "none", "null", "true", "false", "float", "list", "dict"}

# 悬空指代（坑 791468dc0ca2 ①）：「评审那块」的所指依赖上下文，单轮输入
# 拿不到。只收多字指示词，不收「这/那」单字——「这个 PR」里指代词贴着显式
# 对象时由对象优先级裁决，不算悬空。
DANGLING_RE = re.compile(
    r"那块|那个|那些|这个|这些|那段|那部分|这一块|该文件|该模块|该函数|该类|"
    r"刚才|上次|那里|这里|相关代码|相关部分")

# 复合子句（坑 791468dc0ca2 ②）：「然后顺便把测试也补全」这类搭车请求要
# 拆成子任务，不能只按深度档套模板。机械规则：非首子句同时命中标记词与
# 目标词表才算——只认目标词会误伤「注意测试覆盖」，只认标记词拿不到该干什么。
CLAUSE_SPLIT_RE = re.compile(r"[，。；,;！!？?\n]+")
COMPOUND_MARKER_RE = re.compile(r"顺便|顺带|另外|此外|同时|然后|还要|再帮|也")
COMPOUND_TARGETS = (
    (re.compile(r"测试|单测|用例"), "补全测试", "fix"),
    (re.compile(r"文档|readme", re.I), "更新文档", "fix"),
    (re.compile(r"注释"), "补充注释", "fix"),
    (re.compile(r"类型标注|类型提示"), "补类型标注", "fix"),
    (re.compile(r"重构"), "重构相关代码", "fix"),
    (re.compile(r"性能"), "性能优化", "config-change"),
    (re.compile(r"安全"), "安全专项审查", "review"),
)
MAX_COMPOUND = 3

MAX_ASSUMPTIONS = 4
MAX_CONFIRMATIONS = 3


def parse_request(text):
    """机械解析请求文本，返回对象/深度/矛盾证据与全部对象命中。"""
    object_type, object_ref, evidence = "未知", None, []
    object_hits = []
    pr = PR_RE.search(text)
    sha = SHA_RE.search(text) or HEAD_RE.search(text)
    rng = RANGE_RE.search(text)
    branch = BRANCH_RE.search(text)
    if WHOLE_RE.search(text):
        object_type, object_ref = "整个仓库", None
        evidence.append("命中整个仓库表述")
        object_hits.append({"kind": "整个仓库", "value": None})
    if pr:
        object_type, object_ref = "PR", pr.group(1)
        evidence.append("命中 PR 编号 #%s" % pr.group(1))
        object_hits.append({"kind": "PR", "value": pr.group(1)})
    if branch:
        object_type, object_ref = "提交", branch.group(1)
        evidence.append("命中分支引用 %s" % branch.group(1))
        object_hits.append({"kind": "分支", "value": branch.group(1)})
    if rng and not WHOLE_RE.search(text):
        object_type, object_ref = "范围", "%s..%s" % (rng.group(1), rng.group(2))
        evidence.append("命中范围 %s..%s" % (rng.group(1), rng.group(2)))
        object_hits.append({"kind": "范围",
                            "value": "%s..%s" % (rng.group(1), rng.group(2))})
    if sha and object_type in ("未知", "整个仓库"):
        object_type, object_ref = "提交", sha.group(0)
        evidence.append("命中提交标识 %s" % sha.group(0))
        object_hits.append({"kind": "提交标识", "value": sha.group(0)})
    quick = QUICK_RE.search(text)
    deep = DEEP_RE.search(text)
    depth = "standard"
    if quick and deep:
        depth = "contradiction"
        evidence.append("同时命中快速与深入表述，自相矛盾")
    elif quick:
        depth = "quick"
        evidence.append("命中快速档表述")
    elif deep:
        depth = "deep"
        evidence.append("命中深入档表述")
    paths = sorted(set(PATH_RE.findall(text)))
    scope = paths if paths else "全部改动"
    return object_type, object_ref, depth, scope, evidence, object_hits


def detect_compound_clauses(text):
    """按标点切子句；非首子句同时命中标记词与目标词表，记一条复合子句。

    首子句是主意图，永不判复合——「搭车」必须有主句可搭。返回条目带
    clause（原句）/ suggested_task（任务标题）/ kind（org-route 词表），
    供 task-pipeline --decompose 直接追加子任务。
    """
    clauses = [c.strip() for c in CLAUSE_SPLIT_RE.split(text or "") if c.strip()]
    out = []
    for clause in clauses[1:]:
        if not COMPOUND_MARKER_RE.search(clause):
            continue
        for target_re, task_title, kind in COMPOUND_TARGETS:
            if target_re.search(clause):
                out.append({"clause": clause, "suggested_task": task_title,
                            "kind": kind})
                break
        if len(out) >= MAX_COMPOUND:
            break
    return out


def build_ambiguity(object_hits, depth, scope, object_type, request=""):
    """把「同一维度命中多个信号但被优先级裁决」的情况显式列出来。

    规则先写死再看数字（round-30 检查单第 4 条的同款纪律）：每个维度只有
    真的命中了 >=2 个互相竞争的信号才算 ambiguous，默认值不算歧义
    （默认值进 assumptions，不进 ambiguity——两者混在一起会让人分不清
    「我猜的」和「有信号但被裁决掉的」）。

    例外（round-35 消化坑 791468dc0ca2 ①）：对象维度没有任何显式信号、
    原话却含悬空指代时，指代本身就是竞争解读——「整个仓库」默认与
    「上下文里的那块」是两个候选，被拒备选必须列进 readings，不许被
    B 级默认假设静默吸收。
    """
    ambiguity = []
    if depth == "contradiction":
        ambiguity.append({
            "dimension": "depth",
            "readings": [{"value": "quick", "evidence": "命中快速档关键词"},
                         {"value": "deep", "evidence": "命中深入档关键词"}],
            "chosen": None,
            "rule": "快深同提，无法裁决，阻塞（退出码 3）",
        })
    kinds = {h["kind"] for h in object_hits}
    if len(kinds) > 1:
        ambiguity.append({
            "dimension": "object",
            "readings": [{"value": h["kind"], "evidence": h["value"]}
                         for h in object_hits],
            "chosen": object_type,
            "rule": "按对象优先级裁决（范围 > 分支 > PR > 提交标识 > 整个仓库），"
                    "落选信号保留在 readings 供人工复核",
        })
    if isinstance(scope, list) and len(scope) > 1:
        ambiguity.append({
            "dimension": "scope",
            "readings": [{"value": p, "evidence": "命中文件路径"} for p in scope],
            "chosen": scope,
            "rule": "多点名多个文件，全部纳入范围",
        })
    dangling = DANGLING_RE.search(request or "")
    if dangling and not object_hits:
        ambiguity.append({
            "dimension": "object",
            "readings": [
                {"value": "悬空指代「%s」" % dangling.group(0),
                 "evidence": "原话含指代词，所指对象依赖上下文，本轮输入不可得"},
                {"value": "整个仓库",
                 "evidence": "对象未指明，按 --repo 参数默认"},
            ],
            "chosen": "整个仓库",
            "rule": "悬空指代单轮内无法解析：按 --repo 默认整个仓库（B 级），"
                    "指代备选保留在此供复核；用户回话指认即重解析",
        })
    return ambiguity


def build_assumptions(level, depth, scope):
    """列本次解析采用的假设：假设 + 依据 + 错了的代价。

    只在「真的用了默认/推断」时列——A 级对象明确且深度档明说时不编造假设。
    """
    assumptions = []
    if level == "B":
        assumptions.append({
            "assumption": "评审对象 = 整个仓库",
            "basis": "用户未指明对象，按 --repo 参数默认整个仓库",
            "risk_if_wrong": "若真实意图是某个 PR/提交，会扫全仓产出大量无关发现",
        })
    if depth == "standard":
        assumptions.append({
            "assumption": "深度档 = standard",
            "basis": "用户未提及深度档，取缺省档",
            "risk_if_wrong": "期望 quick 时时间预算超支；期望 deep 时覆盖不足",
        })
    if scope == "全部改动":
        assumptions.append({
            "assumption": "评审范围 = 全部改动",
            "basis": "用户未点名单个文件",
            "risk_if_wrong": "若只关心某个模块，无关文件的发现会稀释注意力",
        })
    return assumptions[:MAX_ASSUMPTIONS]


def build_confirmations(assumptions):
    """把假设转成非阻塞待确认项（供调用方随回复带给用户核对）。

    confirmations 与 questions 的分工写死：questions（≤1）是**不问不能开工**
    的阻塞项；confirmations 是「按假设继续干，但如果用户回话纠正就重解析」
    的非阻塞项——全部塞进 questions 会退回逐条确认式对答，违背单问制。
    """
    return ["%s？如不符请纠正（依据：%s；错了的代价：%s）"
            % (a["assumption"], a["basis"], a["risk_if_wrong"])
            for a in assumptions][:MAX_CONFIRMATIONS]


def main():
    parser = argparse.ArgumentParser(description="意图解析")
    parser.add_argument("--request", help="用户原话")
    parser.add_argument("--repo", help="仓库路径（用于 B 级默认对象）")
    argv = parser.parse_args()
    if not argv.request:
        _emit({"ok": False, "error": "缺少 --request"})
        return 2
    object_type, object_ref, depth, scope, evidence, object_hits = parse_request(
        argv.request)
    if depth == "contradiction":
        ambiguity = build_ambiguity(object_hits, depth, scope, object_type,
                                    argv.request)
        _emit(
            {
                "ok": False,
                "intent_level": "C",
                "object": object_type,
                "object_ref": object_ref,
                "scope": scope,
                "depth": None,
                "rationale": evidence,
                "ambiguity": ambiguity,
                "assumptions": [],
                "confirmations": [],
                "compound_clauses": [],
                "questions": ["请求同时要求快速与深入，请确认深度档"],
            }
        )
        return 3
    compound_clauses = detect_compound_clauses(argv.request)
    if object_type != "未知":
        level = "A"
        evidence.append("对象明确，判 A 级")
    elif argv.repo:
        level = "B"
        object_type, object_ref = "整个仓库", None
        evidence.append("对象未指明，按 --repo 默认整个仓库，判 B 级")
        if DANGLING_RE.search(argv.request):
            evidence.append("原话含悬空指代，被拒解读已列进 ambiguity.object")
    else:
        _emit(
            {
                "ok": False,
                "intent_level": "C",
                "object": "未知",
                "object_ref": None,
                "scope": scope,
                "depth": depth,
                "rationale": evidence + ["对象无法确定且未提供 --repo"],
                "ambiguity": [],
                "assumptions": [],
                "confirmations": [],
                "compound_clauses": compound_clauses,
                "questions": ["请提供评审对象（sha/分支/PR 号/仓库路径）"],
            }
        )
        return 3
    ambiguity = build_ambiguity(object_hits, depth, scope, object_type,
                                argv.request)
    assumptions = build_assumptions(level, depth, scope)
    _emit(
        {
            "ok": True,
            "intent_level": level,
            "object": object_type,
            "object_ref": object_ref,
            "scope": scope,
            "depth": depth,
            "rationale": evidence,
            "ambiguity": ambiguity,
            "assumptions": assumptions,
            "confirmations": build_confirmations(assumptions),
            "compound_clauses": compound_clauses,
            "questions": [],
        }
    )
    return 0


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
