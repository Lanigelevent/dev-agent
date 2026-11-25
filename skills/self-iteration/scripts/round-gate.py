#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轮次工作流闸：开局门与收官门的机械校验（P1 剩余项，round-87）。

背景
----
reports/project-review-r85.md 总体结论指出短板「会话驱动的工作方式沉淀
不足」：runner.py 代码化了评审主流程 0-10 步，但每轮真正执行的**轮次
工作流**（开局探针/真值对账/复盘产物/文档约定/全量双跑）散落在
AGENTS.md 散文与下一轮检查单里，靠会话记忆执行，无机器校验。本脚本把它
代码化为与 release-gate.py（发布签核同构的轮次闸，与发布闸互补不重复：
发布闸管版本/密钥/许可证/双跑对账，本闸管轮次产物与文档约定。

两动词：
  open   开局门：干净树 + session-probe 全绿 + doc-freshness 零漂移 +
         next-round.md 可读 + 收官行台账计数与 retro/pitfalls.json 对账。
  close  收官门（--round N）：round-N 复盘产物齐（events/report/
         candidates，events 须可解析）+ 轮报头部/收官行/台账三方计数
         对账 + 收官行是 round-N + 「下一轮（round-N+1）」指针与编号
         条目 + ROADMAP §5 回填 + logs/suite-rN-run1/2.log 两跑均绿
         且计数一致 + 收官行「测试 A→B」终值与双跑实测对账（r159）+
         SRE 错误预算结算（WARN 关注不阻断、EXCEEDED 判红，r164）。

探针子进程环境净化：剥离 PYTHONUTF8 / PYTHONIOENCODING（坑
8cfbcaf7d227），防宿主注入漂移进轮次门。

用法示例：
    python round-gate.py --root . open
    python round-gate.py --root . close --round 87

退出码：0 = 全部检查 PASS；
        1 = 有检查 FAIL（轮次产物/约定缺口，可处理）；
        2 = 参数或环境错误（项目根/关键文件缺失、--round 缺失或非法）。
stdout 输出单个 JSON 文档。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SELF = Path(__file__).resolve().parent
SESSION_PROBE = SELF / "session-probe.py"
DOC_FRESHNESS = SELF / "doc-freshness.py"
SCORECARD = SELF.parents[1] / "director" / "scripts" / "org-scorecard.py"

PROBE_TIMEOUT = 300

TOP_RE = re.compile(r"> round-(\d+) 收官（")
ITEM_RE = re.compile(r"(?m)^\d+\.\s")
NEXT_ROUND_RE = re.compile(r"下一轮（round-(\d+)）")
COUNTS_RE = re.compile(r"(\d+) / open (\d+) / closed (\d+)")
REPORT_HEADER_RE = re.compile(r"open (\d+) / closed (\d+) / archived (\d+)")
ROADMAP_SECTION_RE = re.compile(r"### 5\.\d+ round-(\d+)（v")
ITEM_ROUND_RE = re.compile(r"round-(\d+)(?!\d)")
# 收官行测试计数声明：r154 误计坑 2122392940fc 对策（r159 close 门新检查）
TESTS_CLAIM_RE = re.compile(r"测试\s*\*{0,2}\s*(\d+)\s*(?:→\s*\*{0,2}\s*(\d+)|不变)")

# 全量双跑日志：unittest（Ran N tests … OK/FAILED）与 pytest
# （N passed … in Xs）双格式都认（本闸不指定跑法）。
SUITE_RAN_RE = re.compile(r"Ran (\d+) tests? in ([\d.]+)s")
SUITE_OK_RE = re.compile(r"^OK\b", re.M)
SUITE_FAILED_RE = re.compile(r"^FAILED\b", re.M)
SUITE_PASSED_RE = re.compile(r"(\d+) passed")
SUITE_FAILED_CNT_RE = re.compile(r"(\d+) failed")
SUITE_ERROR_CNT_RE = re.compile(r"(\d+) error")
SUITE_SKIPPED_CNT_RE = re.compile(r"(\d+) skipped")
SUITE_DUR_RE = re.compile(r"in ([\d.]+)s")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "verb": None, "error": error})
    return 2


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _git(root, *git_args):
    p = subprocess.run(["git", "-C", str(root)] + list(git_args),
                       shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def _probe_env():
    """探针子进程环境净化：剥离宿主注入的 PYTHONUTF8/PYTHONIOENCODING
    （坑 8cfbcaf7d227），防解码行为漂移。"""
    env = dict(os.environ)
    for key in ("PYTHONUTF8", "PYTHONIOENCODING"):
        env.pop(key, None)
    return env


def _run_probe(root, script):
    """跑一个探针子进程（env 净化 + utf-8 解码 + 超时护栏）。"""
    if not script.is_file():
        return {"rc": None, "summary": None,
                "error": "探针脚本缺失: %s" % script}
    try:
        p = subprocess.run(
            [sys.executable, str(script), "--root", str(root)], shell=False,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=PROBE_TIMEOUT, env=_probe_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"rc": None, "summary": None, "error": "执行失败: %s" % exc}
    summary = None
    try:
        summary = json.loads(p.stdout)
    except ValueError:
        pass
    return {"rc": p.returncode, "summary": summary, "error": None}


def _check_probe(label, script, result):
    """探针结果 → 检查项（rc 0=PASS，1=有信号，>=2=检查器故障）。"""
    check = {"id": label, "script": script.name, "status": "FAIL"}
    if result["error"]:
        check["error"] = result["error"]
        return check
    rc = result["rc"]
    if rc == 0:
        check["status"] = "PASS"
    elif rc == 1:
        check["note"] = "rc=1 有信号待分诊"
    else:
        check["error"] = "检查器故障（rc=%r）" % rc
    summary = result["summary"]
    if isinstance(summary, dict):
        for key in ("ok", "all_green", "drift_count"):
            if key in summary:
                check[key] = summary[key]
    return check


def _check_git_state(root):
    rc, status, err = _git(root, "status", "--porcelain")
    if rc != 0:
        return {"id": "git_state", "status": "FAIL",
                "error": "不是可读的 git 仓库: %s" % (err or rc)}
    dirty = [line for line in status.splitlines() if line.strip()]
    rc_b, branch, _ = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    rc_h, head, _ = _git(root, "rev-parse", "--short", "HEAD")
    check = {"id": "git_state",
             "status": "PASS" if not dirty else "FAIL",
             "branch": branch if rc_b == 0 else None,
             "head": head if rc_h == 0 else None,
             "clean": not dirty, "dirty_count": len(dirty),
             "dirty": dirty[:10]}
    if dirty:
        check["error"] = "工作树不干净（%d 项）" % len(dirty)
    return check


def _topline_block(text):
    """第一个收官行块：从首个「> round-N 收官（」到下一个完整收官行形态，
    并把换行折叠为空格（收官行的计数常被软换行截断）。"""
    m = TOP_RE.search(text)
    if not m:
        return None, None
    # 块边界必须命中完整收官行形态「> round-N 收官（」——收官行自身软
    # 换行（如「> round-90 专属…」折行）不得截断块（round-88 实战校准）。
    m2 = TOP_RE.search(text, m.start() + 1)
    end = m2.start() if m2 else len(text)
    block = re.sub(r"\s+", " ", text[m.start():end])
    block = block.replace("> ", "")  # 软换行处的块引用标记
    return int(m.group(1)), block


def _counts_actual(pitfalls_path):
    """pitfalls.json 实际计数（顶层 dict 含 pitfalls 键或纯数组都认）。"""
    data = json.loads(_read(pitfalls_path))
    items = data["pitfalls"] if isinstance(data, dict) else data
    counts = {"total": len(items), "open": 0, "closed": 0, "archived": 0}
    for item in items:
        status = item.get("status")
        if status in counts:
            counts[status] = counts[status] + 1
    return counts


def _check_next_round_readable(text):
    top_round, block = _topline_block(text)
    items = ITEM_RE.findall(text)
    check = {"id": "next_round_readable", "items": len(items),
             "topline_round": top_round, "status": "FAIL"}
    if not items:
        check["error"] = "无编号待办条目"
        return check
    if top_round is None:
        topline_missing = None
        check["error"] = "无「> round-N 收官（」收官行"
        return check
    check["status"] = "PASS"
    return check


def _check_pitfalls_reconcile_open(actual, top_round, block):
    check = {"id": "pitfalls_reconcile", "status": "FAIL", "actual": actual}
    if top_round is None:
        check["error"] = "无收官行，无对账源"
        return check
    m = COUNTS_RE.search(block or "")
    check["topline"] = {"total": int(m.group(1)), "open": int(m.group(2)),
                        "closed": int(m.group(3))} if m else None
    if check["topline"] is None:
        check["error"] = "收官行无「N / open N / closed N」计数"
        return check
    t = check["topline"]
    if t["total"] != actual["total"] or t["open"] != actual["open"] \
            or t["closed"] != actual["closed"]:
        check["error"] = "收官行计数 %r ≠ 台账实值 %r" % (t, actual)
        return check
    check["status"] = "PASS"
    return check


def _check_next_round_item(text, round_no):
    next_round = round_no + 1
    _, block = _topline_block(text)
    m = NEXT_ROUND_RE.search(block or "")
    check = {"id": "next_round_item", "status": "FAIL",
             "topline_pointer": bool(m and int(m.group(1)) == next_round),
             "item_found": False}
    for item in ITEM_RE.finditer(text):
        span = text.find("\n", item.start())
        span = len(text) if span < 0 else len(text)
        rm = ITEM_ROUND_RE.search(text[item.start():span])
        if rm and int(rm.group(1)) == next_round:
            check["item_found"] = True
            break
    if check["topline_pointer"] and check["item_found"]:
        check["status"] = "PASS"
    return check


def _check_next_round_topline(text, round_no):
    top_round, _ = _topline_block(text)
    ok = top_round == round_no
    return {"id": "next_round_topline",
            "status": "PASS" if ok else "FAIL",
            "round": top_round, "expected": round_no,
            "error": None if ok else
            ("无收官行" if top_round is None else
             "收官行是 round-%r ≠ round-%d" % (top_round, round_no))}


def _check_roadmap_section(roadmap_text, round_no, history_text=""):
    """§5 回填分卷后兼容回退两卷（v1.96.0 起查 ROADMAP-HISTORY 优先）。"""
    found = any(int(m.group(1)) == round_no
                for m in ROADMAP_SECTION_RE.finditer(history_text))         or any(int(m.group(1)) == round_no
               for m in ROADMAP_SECTION_RE.finditer(roadmap_text))
    return {"id": "roadmap_section", "status": "PASS" if found else "FAIL",
            "round": round_no,
            "error": None if found else
            "ROADMAP/ROADMAP-HISTORY 无「### 5.x round-N（v…）」节：round-%d"
            % round_no}


def _parse_suite_log(text):
    """全量日志解析（unittest/pytest 双格式）。"""
    m = SUITE_RAN_RE.search(text)
    if m:
        green = bool(SUITE_OK_RE.search(text)) \
            and not SUITE_FAILED_RE.search(text)
        return {"format": "unittest", "tests": int(m.group(1)),
                "duration_sec": float(m.group(2)), "green": green}
    m = SUITE_PASSED_RE.search(text)
    if m:
        passed = int(m.group(1))
        failed = SUITE_FAILED_CNT_RE.search(text)
        errors = SUITE_ERROR_CNT_RE.search(text)
        skipped = SUITE_SKIPPED_CNT_RE.search(text)
        failed_n = int(failed.group(1)) if failed else 0
        error_n = int(errors.group(1)) if errors else 0
        skipped_n = int(skipped.group(1)) if skipped else 0
        green = passed > 0 and failed_n == 0 and error_n == 0
        dur = SUITE_DUR_RE.search(text, m.end())
        return {"format": "pytest", "tests": passed + failed_n + error_n
                + skipped_n,
                "duration_sec": float(dur.group(1)) if dur else None,
                "green": green}
    return {"format": "unknown", "tests": None, "duration_sec": None,
            "green": False}


def _check_suite_logs(logs_dir, round_no, light=False):
    # round-142 分级收官：light 轮只要求 run1 单跑全绿（run2 可缺省），
    # 其余检查不减；full 轮维持双跑 + parity。
    names = ["suite-r%d-run1.log" % round_no]
    if not light:
        names.append("suite-r%d-run2.log" % round_no)
    check = {"id": "suite_logs", "status": "FAIL", "logs": [], "runs": [],
             "parity": None}
    missing = []
    for name in names:
        path = logs_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
            continue
        run = _parse_suite_log(_read(path))
        run["log"] = name
        check["logs"].append(name)
        check["runs"].append(run)
    if missing:
        check["error"] = "双跑日志缺失或为空: %s" % ", ".join(missing)
        return check
    greens = [run["green"] for run in check["runs"]]
    counts = [run["tests"] for run in check["runs"]]
    check["parity"] = None if len(counts) < 2 else counts[0] == counts[1]
    if not all(greens):
        check["error"] = "存在未全绿日志: %r" % [
            {"log": r["log"], "format": r["format"], "green": r["green"]}
            for r in check["runs"]]
        return check
    if check["parity"] is False:
        check["error"] = "两跑测试数不一致: %r" % (counts,)
        return check
    check["status"] = "PASS"
    return check


def _check_suite_count_claim(text, runs):
    """收官行测试计数声明 vs 双跑实测（r159，r154 误计坑 2122392940fc 对策）。

    r154 收官行写「测试 751→754」而真值 745→748——分母错了不会报错只会算错
    （易错点 4），当时 close 门只对台账三态对账、不管测试数声明。本检查把
    收官行「测试 A→B / A 不变」的终值与双跑日志实测值（passed+failed+errors
    +skipped）对账：不一致即 FAIL。无声明行（旧格式）不判漂移，note 如实
    记录，不给不存在的声明编造失败。
    """
    _, block = _topline_block(text)
    check = {"id": "suite_count_claim", "status": "FAIL"}
    m = TESTS_CLAIM_RE.search(block or "")
    if not m:
        check["status"] = "PASS"
        check["note"] = "收官行无测试计数声明（不判漂移）"
        return check
    claimed = int(m.group(2)) if m.group(2) else int(m.group(1))
    counts = [r.get("tests") for r in (runs or [])
              if r.get("tests") is not None]
    if not counts:
        check["error"] = "双跑日志无可用测试数，声明无法对账"
        return check
    if any(c != claimed for c in counts):
        check["error"] = ("收官行声明测试数 %d ≠ 双跑实测 %r"
                          "（r154 误计坑 2122392940fc 对策）" % (claimed, counts))
        return check
    check["status"] = "PASS"
    check["claimed"] = claimed
    check["measured"] = counts
    return check


def _check_scorecard(root):
    """SRE 错误预算结算进收官门（r164，125 条②：约定「每轮结算」机械化）。

    WARN 整改关注不阻断收官（AGENTS：WARN 关注、EXCEEDED 整改冻结）；
    EXCEEDED 即 FAIL——放行一个冻结中的轮次等于冻结失效。N/A（无数据）
    如实放行。反向验证：17 个 open 坑（>8×2）必须判红（契约锚定）。
    """
    check = {"id": "scorecard_budget", "status": "FAIL"}
    if not SCORECARD.is_file():
        check["error"] = "scorecard 脚本缺失: %s" % SCORECARD
        return check
    try:
        p = subprocess.run(
            [sys.executable, str(SCORECARD)], shell=False, cwd=str(root),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=PROBE_TIMEOUT, env=_probe_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        check["error"] = "scorecard 执行失败: %s" % exc
        return check
    try:
        data = json.loads(p.stdout)
    except ValueError:
        check["error"] = "scorecard 输出非 JSON（rc=%r）" % p.returncode
        return check
    if not data.get("ok"):
        check["error"] = "scorecard 结算未通过: %s" % json.dumps(
            data, ensure_ascii=False)[:200]
        return check
    entries = data.get("scorecard") or []
    exceeded = [e.get("metric") for e in entries
                if e.get("status") == "EXCEEDED"]
    warned = [e.get("metric") for e in entries if e.get("status") == "WARN"]
    if exceeded:
        check["error"] = "错误预算 EXCEEDED（整改冻结）: %r" % exceeded
        return check
    check["status"] = "PASS"
    if warned:
        check["note"] = "WARN 整改关注（不阻断）: %r" % warned
    return check


def _verb_open(root):
    """开局门：干净树 + 探针 + next-round 可读 + 台账对账。"""
    checks = []
    checks.append(_check_git_state(root))
    for label, script in (("session_probe", SESSION_PROBE),
                          ("doc_freshness", DOC_FRESHNESS)):
        checks.append(_check_probe(label, script, _run_probe(root, script)))
    next_round = root / "retro" / "next-round.md"
    pitfalls_path = root / "retro" / "pitfalls.json"
    for path, label in ((next_round, "retro/next-round.md"),
                        (pitfalls_path, "retro/pitfalls.json")):
        if not path.is_file():
            return checks, "%s 必须存在" % label
    text = _read(next_round)
    checks.append(_check_next_round_readable(text))
    actual = _counts_actual(pitfalls_path)
    top_round, block = _topline_block(text)
    checks.append(_check_pitfalls_reconcile_open(actual, top_round, block))
    return checks, None


def _verb_close(root, round_no, light=False):
    """收官门：复盘产物 + 三方对账 + 文档约定 + 双跑日志（light=单跑）。"""
    checks = []
    retro_dir = root / "retro"
    events = retro_dir / ("events-round-%d.json" % round_no)
    report = retro_dir / ("round-%d-report.md" % round_no)
    candidates = retro_dir / ("round-%d-candidates.md" % round_no)
    file_status = {}
    for name, path in (("events", events), ("report", report),
                       ("candidates", candidates)):
        if not path.is_file() or path.stat().st_size == 0:
            file_status[name] = "missing_or_empty"
            continue
        file_status[name] = "%d bytes" % path.stat().st_size
        if name == "events":
            try:
                json.loads(_read(path))
                file_status[name] = "valid_json"
            except ValueError as exc:
                file_status[name] = "invalid_json: %s" % exc
    artifacts_ok = all(v == "valid_json" or v.endswith("bytes")
                       for v in file_status.values())
    checks.append({"id": "retro_artifacts", "status":
                   "PASS" if artifacts_ok else "FAIL",
                   "files": file_status,
                   "error": None if artifacts_ok else
                   "复盘产物缺失/空/坏 JSON: %r" % file_status})
    next_round = root / "retro" / "next-round.md"
    pitfalls_path = root / "retro" / "pitfalls.json"
    road = root / "docs" / "ROADMAP.md"
    for path, label in ((next_round, "retro/next-round.md"),
                        (pitfalls_path, "retro/pitfalls.json"),
                        (road, "docs/ROADMAP.md")):
        if not path.is_file():
            return checks, "%s 必须存在" % label
    road_text = _read(road)
    next_text = _read(next_round)
    top_round, block = _topline_block(next_text)
    # ① 复盘产物齐（已入 checks）
    # ② 轮报头部 / 收官行 / pitfalls.json 三方对账
    report_text = _read(report)
    hm = REPORT_HEADER_RE.search(report_text)
    header_counts = {"open": int(hm.group(1)), "closed": int(hm.group(2)),
                     "archived": int(hm.group(3))} if hm else None
    actual = _counts_actual(pitfalls_path)
    topline_counts = None
    if block:
        cm = COUNTS_RE.search(block)
        topline_counts = {"total": int(cm.group(1)),
                          "open": int(cm.group(2)),
                          "closed": int(cm.group(3))} if cm else None
    rec = {"id": "pitfalls_reconcile", "status": "FAIL",
           "report_header": header_counts, "topline": topline_counts,
           "actual": actual}
    agree = (header_counts and topline_counts
             and header_counts["open"] == topline_counts["open"]
             and header_counts["closed"] == topline_counts["closed"]
             and header_counts["open"] == actual["open"]
             and header_counts["closed"] == actual["closed"])
    if agree:
        rec["status"] = "PASS"
    else:
        rec["error"] = "轮报头部/收官行/台账实值三方不一致: %r" % {
            "report_header": header_counts, "topline": topline_counts,
            "actual": actual}
    checks.append(rec)
    # ③④⑤⑥
    checks.append(_check_next_round_topline(next_text, round_no))
    checks.append(_check_next_round_item(next_text, round_no))
    checks.append(_check_roadmap_section(
        road_text, round_no, _read(root / "docs" / "ROADMAP-HISTORY.md")
        if (root / "docs" / "ROADMAP-HISTORY.md").is_file() else ""))
    suite_check = _check_suite_logs(root / "logs", round_no, light=light)
    checks.append(suite_check)
    checks.append(_check_suite_count_claim(next_text,
                                           suite_check.get("runs") or []))
    checks.append(_check_scorecard(root))
    # round-154（F4 结构收尾）：收官通过时自动向事件账本追加 round-summary
    # （best-effort：账本写入失败不改变收官判定，只记 warning 供迭代官追查）。
    ok_all = all(c["status"] == "PASS" for c in checks)
    if ok_all:
        warn = _append_ledger_record(root, round_no, True)
        if warn:
            checks.append({"id": "ledger_record", "status": "WARN",
                           "detail": warn})
    return checks, None


def _ledger_has_round_summary(ledger_file, round_no):
    """同轮 round-summary 是否已存在（r186 幂等守卫的扫描面，容坏行）。"""
    try:
        text = ledger_file.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        obs = rec.get("observation") or {}
        if rec.get("action") == "round-summary" and obs.get("round") == round_no:
            return True
    return False


def _append_ledger_record(root, round_no, ok_all):
    """收官通过 → 事件账本追加 round-summary（best-effort，失败返回告警文本）。
    r186 幂等守卫：同轮已有 round-summary 即跳过追加——close 重跑不得双记
    （r154 历史双记 11 秒间隔的机制修复）；账本读不了时保守放行（best-effort
    语义不变）。"""
    try:
        import subprocess as _sp
        ledger_dir = root / "runs" / "rounds-ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        ledger_file = ledger_dir / "ledger.jsonl"
        ledger_file.touch(exist_ok=True)
        if _ledger_has_round_summary(ledger_file, round_no):
            return None
        script = root / "skills" / "production-guardrails" / "scripts" / "event-ledger.py"
        if not script.is_file():
            return "event-ledger.py 不存在，账本未记录"
        p = _sp.run(
            [sys.executable, "-X", "utf8", str(script), "record",
             "--dir", str(ledger_dir), "--actor", "round-gate",
             "--action", "round-summary", "--kind", "note",
             "--replay", "opaque",
             "--argv-json", json.dumps(["round-%d" % round_no]),
             "--observation-json", json.dumps(
                 {"round": round_no, "outcome": "closed" if ok_all else "closed-with-fails"},
                 ensure_ascii=False)],
            shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60)
        if p.returncode != 0:
            return "账本 record rc=%d: %s" % (p.returncode, (p.stderr or "")[:200])
        return None
    except (OSError, ValueError) as exc:
        return "账本记录异常: %s" % str(exc)[:200]


def main():
    parser = argparse.ArgumentParser(description="轮次工作流闸")
    parser.add_argument("verb", choices=("open", "close"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--round-type", choices=("full", "light"),
                        default="full",
                        help="light=轻量收官（单跑 run1 全绿即可，round-142）")
    args = parser.parse_args()
    root = Path(args.root)
    if not root.is_dir():
        return _param_error("项目根不存在: %s" % root)
    if args.verb == "close" and (args.round is None or args.round < 1):
        return _param_error("close 需要 --round N（正整数）")
    if args.verb == "open":
        checks, env_error = _verb_open(root)
    else:
        checks, env_error = _verb_close(root, args.round,
                                  light=(args.round_type == "light"))
    if env_error:
        return _param_error(env_error)
    # WARN（如 ledger_record best-effort 失败）不阻断收官判定（round-154）。
    failed_ids = [c["id"] for c in checks
                  if c["status"] not in ("PASS", "WARN", "SKIPPED")]
    _emit({"ok": not failed_ids, "verb": args.verb, "round": args.round,
           "root": str(root), "checks": checks, "failed": failed_ids,
           "note": "与 release-gate 互补：发布闸管版本/密钥/许可证/双跑对账，"
                   "本闸管轮次产物与文档约定"})
    return 0 if not failed_ids else 1


if __name__ == "__main__":
    sys.exit(main())
