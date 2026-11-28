#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补丁落盘（唯一允许写被审仓库的脚本）：五道闸 + 行为回归 + 失败自动回滚。

五道闸：审核人批准书（--approval，verdict=APPROVED 且 sha256 绑定当前补丁包）、
工作树干净（git status 无输出）、HEAD 与清单 base_sha 一致、git apply 预检通过、
行为回归（逐文件重扫原 rule_id 消失且无新增规则 + 发现仓库测试时执行，
测试失败等同验证失败）。任一道失败自动回滚（checkout 还原 + 删除修复分支）
并返回退出码 1；APPLIED 与 ROLLED_BACK 都写 apply-log.json（复盘角色采集）。
每次落盘同时追加 apply-log-history.jsonl（证据窗口，只留最近 50 次），溢出的按
「状态 + 错误前 200 字」签名压进 apply-log-history.archived.jsonl（一条形状一行，
带 occurrences）——活跃文件不会一路长，窗口外的回滚也不会被当成没发生过。
默认不带 --apply 只做预检（状态 PROPOSED，不写仓库，也不需批准书）；
--undo 撤销已落盘的修复分支（回到原分支并删除 review-fix 分支）。

用法示例：
    py fix-apply.py --manifest fix-manifest.json --repo <被审仓库>                      # 预检
    py fix-apply.py --manifest fix-manifest.json --repo <仓库> --approval approval.json --apply
    py fix-apply.py --manifest fix-manifest.json --repo <被审仓库> --undo               # 撤销

退出码：0=成功（PROPOSED/APPLIED/UNDONE）；1=验证失败已回滚（ROLLED_BACK）；
2=输入或前置条件不满足（含未持批准书）。
"""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES_SCRIPT = (ROOT / "skills" / "multi-agent-review" / "scripts"
                / "deterministic-rules.py")
CASE_MATCH = (ROOT / "skills" / "director" / "scripts" / "case-match.py")
CASE_DIR = ROOT / "retro"


def _reuse_hints(text):
    """主观能动性：回滚时主动查案例库，带复用建议回来（查不到即为空）。"""
    if not text or not CASE_MATCH.is_file():
        return []
    try:
        proc = subprocess.run(
            [sys.executable, str(CASE_MATCH), "--match", str(text)[:400],
             "--out", str(CASE_DIR)],
            shell=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)
        if proc.returncode != 0:
            return []
        hits = json.loads(proc.stdout).get("hits", [])
        return [{"title": h.get("title", ""), "takeaway": h.get("takeaway", ""),
                 "url": h.get("url", ""), "local_ref": h.get("local_ref", "")}
                for h in hits[:2]]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []  # 案例库不可用不阻塞回滚本身


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _scan_file(abs_path):
    """跑硬规则扫描；返回 (findings 列表, error 或 None)。"""
    proc = subprocess.run([sys.executable, str(RULES_SCRIPT), "--file",
                           str(abs_path)], shell=False, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=120)
    if proc.returncode != 0:
        return [], "扫描器退出码 %d: %s" % (proc.returncode, proc.stderr[:200])
    try:
        return json.loads(proc.stdout).get("findings", []), None
    except ValueError:
        return [], "扫描器输出非 JSON"


def _preconditions(repo, manifest):
    """四道闸的前两道 + 清单一致性；返回错误描述或 None。"""
    if Path(manifest.get("repo", "")).resolve() != repo.resolve():
        return "manifest.repo 与 --repo 不一致"
    rc, status = _git(repo, ["status", "--porcelain"])
    if rc != 0:
        return "git status 失败: %s" % status[:200]
    if status:
        return "工作树不干净，拒绝落盘（先提交或暂存）"
    rc, head = _git(repo, ["rev-parse", "HEAD"])
    if rc != 0:
        return "无法读取 HEAD: %s" % head[:200]
    if head != manifest.get("base_sha"):
        return "HEAD(%s) 与清单 base_sha(%s) 不一致，请重新生成补丁" % (
            head[:12], str(manifest.get("base_sha"))[:12])
    return None


def _patch_path(manifest, item):
    """补丁文件位于 manifest 所在产物目录，不位于被审仓库内。"""
    return (Path(manifest["__dir__"]) / item["patch_file"]).resolve()


def _apply_checks(repo, manifest, files):
    """第三道闸：git apply --check。返回错误描述或 None。"""
    for item in files:
        rc, out = _git(repo, ["apply", "--check", str(_patch_path(manifest, item))])
        if rc != 0:
            return "git apply --check 失败(%s): %s" % (item["path"], out[:300])
    return None


def _verify_ruff(repo, item):
    """闸五之引擎复扫（ruff）：修复码消失且默认集无新增码。

    before_codes 由 fix-patch 落 manifest（该文件修复前的默认集码集合）；
    after ⊆ before 且修复码不在 after 才算过闸。
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from engines.ruff_adapter import ruff_scan_codes
    abs_path = repo / item["path"]
    scan = ruff_scan_codes(abs_path)
    if scan is None:
        return "ruff 复扫失败: %s" % item["path"], []
    after = set(scan["codes"])
    fixed_codes = {str(r).split(":", 1)[1] for r in item.get("rules", [])
                   if str(r).startswith("ruff:")}
    before = set(item.get("before_codes") or [])
    remaining = sorted(fixed_codes & after)
    added = sorted(after - before) if before else []
    if remaining or added:
        return ("验证失败（ruff）: %s 残留 %s 新增 %s"
                % (item["path"], remaining, added)), []
    return None, {"path": item["path"], "engine": "ruff",
                  "after_codes": sorted(after), "remaining": [], "added": added}


def _verify_libcst(repo, item):
    """闸五之引擎复扫（libcst）：修复码消失且 after ⊆ before。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from engines.libcst_adapter import libcst_scan_codes
    abs_path = repo / item["path"]
    scan = libcst_scan_codes(abs_path)
    if scan is None:
        return "libcst 复扫失败: %s" % item["path"], []
    after = set(scan["codes"])
    fixed_codes = {str(r).split(":", 1)[1] for r in item.get("rules", [])
                   if str(r).startswith("libcst:")}
    before = set(item.get("before_codes") or [])
    remaining = sorted(fixed_codes & after)
    added = sorted(after - before) if before else []
    if remaining or added:
        return ("验证失败（libcst）: %s 残留 %s 新增 %s"
                % (item["path"], remaining, added)), []
    return None, {"path": item["path"], "engine": "libcst",
                  "after_codes": sorted(after), "remaining": [], "added": added}


def _verify_astgrep(repo, item):
    """闸五之引擎复扫（astgrep）：修复码消失且 after ⊆ before。"""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from engines.astgrep_adapter import astgrep_scan_codes
    abs_path = repo / item["path"]
    scan = astgrep_scan_codes(abs_path)
    if scan is None:
        return "astgrep 复扫失败: %s" % item["path"], []
    after = set(scan["codes"])
    fixed_codes = {str(r).split(":", 1)[1] for r in item.get("rules", [])
                   if str(r).startswith("astgrep:")}
    before = set(item.get("before_codes") or [])
    remaining = sorted(fixed_codes & after)
    added = sorted(after - before) if before else []
    if remaining or added:
        return ("验证失败（astgrep）: %s 残留 %s 新增 %s"
                % (item["path"], remaining, added)), []
    return None, {"path": item["path"], "engine": "astgrep",
                  "after_codes": sorted(after), "remaining": [], "added": added}


def _verify(repo, files):
    """闸五之规则重扫：逐文件重扫（builtin 走确定性规则，ruff/libcst 走引擎）。"""
    details = []
    for item in files:
        if item.get("engine") == "ruff":
            error, detail = _verify_ruff(repo, item)
            if error:
                return error, details
            details.append(detail)
            continue
        if item.get("engine") == "libcst":
            error, detail = _verify_libcst(repo, item)
            if error:
                return error, details
            details.append(detail)
            continue
        if item.get("engine") == "astgrep":
            error, detail = _verify_astgrep(repo, item)
            if error:
                return error, details
            details.append(detail)
            continue
        abs_path = repo / item["path"]
        findings, error = _scan_file(abs_path)
        if error:
            return error, details
        new_ids = sorted({f.get("rule_id", "") for f in findings})
        old_ids = set(item.get("rules", []))
        remaining = sorted(old_ids & set(new_ids))
        added = sorted(set(new_ids) - old_ids)
        if remaining or added or len(findings) > item.get("findings_count", 0):
            details.append({"path": item["path"], "remaining": remaining,
                            "added": added, "count": len(findings)})
            return "验证失败: %s" % item["path"], details
        details.append({"path": item["path"], "remaining": [],
                        "added": [], "count": len(findings)})
    return None, details


def _load_test_select():
    """邻接装载 test-select.py（M6 选择器；连字符文件名走 importlib）。"""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("test_select", here / "test-select.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _detect_tests(repo):
    """发现仓库测试：tests/ 目录或根下 test_*.py。"""
    found = []
    tests_dir = repo / "tests"
    if tests_dir.is_dir():
        found.extend(sorted(tests_dir.glob("test_*.py")))
    found.extend(sorted(repo.glob("test_*.py")))
    return found


def _run_repo_tests(repo, selected=None):
    """闸五之行为回归：执行仓库测试。返回 (status: pass|fail|skip, detail)。

    selected=None/空 → 全量（fail-safe：选择器空集不冒充「无受影响测试」）；
    selected 非空 → 子集 pytest（M6 auto 档，失败语义不变）。
    """
    if not _detect_tests(repo):
        return "skip", "仓库未发现 test_*.py 测试"
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if selected:
        cmd = cmd + [str(s) for s in selected]
    else:
        cmd = cmd + [str(repo)]
    proc = subprocess.run(cmd,
                          shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600,
                          cwd=str(repo))
    if proc.returncode == 0:
        return "pass", (proc.stdout or "").strip().splitlines()[-1:] or ["ok"]
    if "No module named pytest" in (proc.stderr or ""):
        return "skip", "环境无 pytest，无法执行行为回归"
    tail = [l for l in (proc.stdout or "").strip().splitlines() if l][-12:]
    return "fail", tail or [(proc.stderr or "")[:300]]
HISTORY_LIVE_MAX = 50
HISTORY_ARCHIVE_NAME = "apply-log-history.archived.jsonl"


def _history_signature(entry):
    """归档合并键——与迭代官记账键同源，两侧不会各说各话。

    retro-ledger 的 pitfall id 由「回滚: error 前 200 字」算出，这里对 ROLLED_BACK
    用同一个形状（status + error[:200]）做键，于是**被压掉的重复证据恰好是它本来
    也会去重的那批**，轮转不丢账。成功态（APPLIED）迭代官不采，其权威记录在 git
    提交与 apply-log.json 里，归档只并成一条计数，不逐条留细节。
    """
    if entry.get("status") == "ROLLED_BACK":
        raw = "ROLLED_BACK|%s" % str(entry.get("error", ""))[:200]
    else:
        raw = str(entry.get("status", ""))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _utc_stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _archive_lines(archive_path):
    """读归档条目（容忍坏行——归档是账本，不该因为一行脏数据把落盘卡死）。"""
    items = []
    if not archive_path.is_file():
        return items
    for line in archive_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            items.append(parsed)
    return items


def _merge_into_archive(archive_path, overflow):
    """溢出行按签名并进归档（同形状只留一条，occurrences 计数）。"""
    by_sig = {}
    for item in _archive_lines(archive_path):
        by_sig[item.get("signature") or _history_signature(item)] = item
    for entry in overflow:
        sig = _history_signature(entry)
        at = entry.get("at") or _utc_stamp()
        item = by_sig.get(sig)
        if item is None:
            by_sig[sig] = {"signature": sig, "status": entry.get("status"),
                           "error": str(entry.get("error", ""))[:200],
                           "occurrences": 1, "first_at": at, "last_at": at}
        else:
            item["occurrences"] = int(item.get("occurrences", 0)) + 1
            item["first_at"] = min([item.get("first_at") or at, at])
            item["last_at"] = max([item.get("last_at") or at, at])
    ordered = sorted(by_sig.values(), key=lambda v: (str(v.get("last_at")),
                                                     str(v.get("signature"))))
    archive_path.write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in ordered),
        encoding="utf-8", newline="\n")


def _archive_summary(archive_path):
    """(归档条目数, 归档累计行数)——条目数由「不同形状的数量」决定，与重试次数无关。"""
    items = _archive_lines(archive_path)
    return len(items), sum(int(i.get("occurrences", 0)) for i in items)


def _write_log(manifest, payload):
    """落盘台账：`apply-log.json` 是**最新状态**，`apply-log-history.jsonl` 是**最近窗口**。

    round-30 同类排查第 7 项 R3：这里原本只有一个原地重写的 apply-log.json。
    同一产物目录里重试落盘（回滚一次再来一次）会把上一条 ROLLED_BACK 抹掉，
    而迭代官采集的正是「发生过回滚」这条事实——采集晚于重试就永久漏账。
    保留单文件语义（--undo 与 org-scorecard 都按「最新一次」读），
    另加 append-only 的 jsonl 历史；retro-ledger 两者都采，按 id 去重不会重复记账。

    round-31 第 7 项的后半段：只追加的历史**没有上限就是另一种漏账**（默默长）。
    口径 = 活跃文件只留最近 `HISTORY_LIVE_MAX` 次，溢出压进同目录的
    `apply-log-history.archived.jsonl`，按签名合并成「一种形状 × 发生次数」；
    归档长度由「不同失败形状的数量」决定而不是由重试次数决定，才真的关得住无界。
    这四个数字（live_lines / live_max / archive_entries / archived_lines）写进 apply-log.json，
    成功落盘时也回进 stdout，操作员看得见窗口在用。
    """
    payload["at"] = _utc_stamp()
    log_path = Path(manifest["__dir__"]) / "apply-log.json"
    hist_path = log_path.parent / "apply-log-history.jsonl"
    archive_path = log_path.parent / HISTORY_ARCHIVE_NAME
    with hist_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    live = [line for line in hist_path.read_text(
        encoding="utf-8").splitlines() if line.strip()]
    if len(live) > HISTORY_LIVE_MAX:
        overflow, live = live[:-HISTORY_LIVE_MAX], live[-HISTORY_LIVE_MAX:]
        hist_path.write_text("".join(line + "\n" for line in live),
                             encoding="utf-8", newline="\n")
        overflow_entries = []
        for line in overflow:
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                overflow_entries.append(parsed)
        _merge_into_archive(archive_path, overflow_entries)
    entries, archived_lines = _archive_summary(archive_path)
    payload["history"] = {"live_lines": len(live), "live_max": HISTORY_LIVE_MAX,
                          "archive_entries": entries,
                          "archived_lines": archived_lines}
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")
    return log_path


def _rollback(repo, files, branch, original):
    for item in files:
        _git(repo, ["checkout", "--", item["path"]])
    if original:
        _git(repo, ["checkout", original])
    if branch:
        _git(repo, ["branch", "-D", branch])


def _check_approval(approval_path, manifest):
    """第五道闸：审核人批准书核验。返回错误描述或 None。"""
    if approval_path is None:
        return "落盘必须持审核人批准书（--approval），任何一方不得自审自批"
    if not approval_path.is_file():
        return "批准书不存在: %s" % approval_path
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "批准书 JSON 非法: %s" % exc
    if approval.get("verdict") != "APPROVED":
        return "批准书状态非 APPROVED: %s（reasons: %s）" % (
            approval.get("verdict"), approval.get("reasons", []))
    manifest_sha = hashlib.sha256(
        Path(manifest["__path__"]).read_bytes()).hexdigest()
    if approval.get("manifest_sha256") != manifest_sha:
        return "批准书与当前补丁包不符（manifest sha256 变动，需重新送审）"
    if approval.get("order_id") != manifest.get("order_id"):
        return "批准书工单(%s)与补丁包工单(%s)不一致" % (
            approval.get("order_id"), manifest.get("order_id"))
    if approval.get("base_sha") != manifest.get("base_sha"):
        return "批准书基线与补丁包基线不一致"
    return None


def _do_apply(repo, manifest, approval_path, test_mode="full"):
    files = manifest.get("files", [])
    if not files:
        _emit({"ok": False, "state": "PROPOSED", "error": "清单无可应用补丁"})
        return 2
    error = _check_approval(approval_path, manifest)
    if error:
        _emit({"ok": False, "state": "PROPOSED", "error": error})
        return 2
    error = _preconditions(repo, manifest)
    if error:
        _emit({"ok": False, "state": "PROPOSED", "error": error})
        return 2
    error = _apply_checks(repo, manifest, files)
    if error:
        _emit({"ok": False, "state": "PROPOSED", "error": error})
        return 2
    rc, original = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = "review-fix/%s" % manifest.get("id", "local")
    if rc != 0:
        _emit({"ok": False, "state": "PROPOSED", "error": "无法读取当前分支"})
        return 2
    rc, out_branch = _git(repo, ["checkout", "-b", branch])
    if rc != 0:
        _emit({"ok": False, "state": "PROPOSED",
               "error": "创建分支失败: %s" % out_branch[:200]})
        return 2
    applied = []
    for item in files:
        rc, out_apply = _git(repo, ["apply", str(_patch_path(manifest, item))])
        if rc != 0:
            _rollback(repo, applied, branch, original)
            log_path = _write_log(manifest, {
                "status": "ROLLED_BACK", "branch": None, "files": files,
                "error": "git apply 失败(%s): %s" % (item["path"], out_apply[:300]),
                "approval": str(approval_path) if approval_path else ""})
            _emit({"ok": False, "state": "ROLLED_BACK",
                   "error": "git apply 失败(%s): %s" % (item["path"],
                                                       out_apply[:300]),
                   "apply_log": str(log_path)})
            return 1
        applied.append(item)
    error, details = _verify(repo, files)
    tests_status, tests_detail = ("skip", "未执行")
    if error is None:
        if test_mode == "auto":
            _ts = _load_test_select()
            sel, _chg = _ts.select_tests(repo, files)
            tests_status, tests_detail = _run_repo_tests(repo, selected=sel)
        else:
            tests_status, tests_detail = _run_repo_tests(repo)
        if tests_status == "fail":
            error = "行为回归失败：仓库测试未通过"
    if error:
        _rollback(repo, files, branch, original)
        # 回滚只还原**被跟踪**的文件；行为回归跑测试时 pytest 会在仓库里留下
        # __pycache__ 这类未跟踪产物。它们会让下一次落盘直接撞「工作树不干净」
        # 这道闸（fail-closed，闸门没坏），操作者若不知情会以为是补丁出了问题。
        rc_dirty, dirty = _git(repo, ["status", "--porcelain"])
        leftovers = [l.strip() for l in (dirty or "").splitlines() if l.strip()]
        hints = _reuse_hints(error)
        log_path = _write_log(manifest, {
            "status": "ROLLED_BACK", "branch": None, "files": files,
            "error": error, "details": details,
            "tests": {"status": tests_status, "detail": tests_detail},
            "reuse_hints": hints,
            "worktree_leftovers": leftovers,
            "approval": str(approval_path) if approval_path else ""})
        _emit({"ok": False, "state": "ROLLED_BACK", "error": error,
               "details": details, "tests": {"status": tests_status},
               "reuse_hints": hints,
               "worktree_leftovers": leftovers,
               "retry_hint": ("重试前先清掉这些未跟踪产物，否则「工作树不干净」闸会拦住下一次落盘"
                              if leftovers else ""),
               "apply_log": str(log_path)})
        return 1
    add_args = ["add"] + [item["path"] for item in files]
    rc, out_add = _git(repo, add_args)
    if rc != 0:
        _rollback(repo, files, branch, original)
        log_path = _write_log(manifest, {
            "status": "ROLLED_BACK", "branch": None, "files": files,
            "error": "git add 失败: %s" % out_add[:200],
            "approval": str(approval_path) if approval_path else ""})
        _emit({"ok": False, "state": "ROLLED_BACK",
               "error": "git add 失败: %s" % out_add[:200],
               "apply_log": str(log_path)})
        return 1
    rule_ids = sorted({r for item in files for r in item.get("rules", [])})
    msg = "fix(review): auto-fix %s" % ",".join(rule_ids)
    rc, out_commit = _git(repo, ["-c", "user.name=dev-agent",
                                 "-c", "user.email=review@local",
                                 "commit", "-m", msg])
    if rc != 0:
        _rollback(repo, files, branch, original)
        log_path = _write_log(manifest, {
            "status": "ROLLED_BACK", "branch": None, "files": files,
            "error": "git commit 失败: %s" % out_commit[:300],
            "approval": str(approval_path) if approval_path else ""})
        _emit({"ok": False, "state": "ROLLED_BACK",
               "error": "git commit 失败: %s" % out_commit[:300],
               "apply_log": str(log_path)})
        return 1
    rc, commit_sha = _git(repo, ["rev-parse", "HEAD"])
    applied_entry = {
        "status": "APPLIED", "branch": branch, "original_branch": original,
        "commit": commit_sha if rc == 0 else "", "files": files,
        "verified": True, "message": msg,
        "verification": details,
        "tests": {"status": tests_status, "detail": tests_detail},
        "approval": str(approval_path) if approval_path else ""}
    log_path = _write_log(manifest, applied_entry)
    _emit({"ok": True, "state": "APPLIED", "branch": branch,
           "commit": commit_sha if rc == 0 else "", "verification": details,
           "tests": {"status": tests_status, "detail": tests_detail},
           "apply_log": str(log_path),
           "apply_log_history": applied_entry["history"],
           "note": "修复分支未合并；合并或撤销由人工决定（--undo 可撤销）"})
    return 0


def _do_undo(repo, manifest):
    log_path = Path(manifest["__dir__"]) / "apply-log.json"
    if not log_path.is_file():
        _emit({"ok": False, "state": "PROPOSED", "error": "无 apply-log.json，未落盘过"})
        return 2
    log = json.loads(log_path.read_text(encoding="utf-8"))
    rc, current = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if rc == 0 and current == log.get("branch"):
        _git(repo, ["checkout", log.get("original_branch", "")])
    rc, _ = _git(repo, ["branch", "-D", log.get("branch", "")])
    if rc != 0:
        _emit({"ok": False, "state": "PROPOSED", "error": "删除修复分支失败"})
        return 2
    log["undone"] = True
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    _emit({"ok": True, "state": "UNDONE", "branch": log.get("branch"),
           "original_branch": log.get("original_branch")})
    return 0


def main():
    parser = argparse.ArgumentParser(description="补丁落盘（写仓库的唯一入口）")
    parser.add_argument("--manifest", required=True, help="fix-manifest.json 路径")
    parser.add_argument("--repo", required=True, help="被审仓库根")
    parser.add_argument("--approval", default="",
                        help="审核人批准书 approval.json（--apply 时必填）")
    parser.add_argument("--apply", action="store_true", help="真正落盘（缺省仅预检）")
    parser.add_argument("--undo", action="store_true", help="撤销已落盘的修复分支")
    parser.add_argument("--test-mode", choices=["full", "auto"], default="full",
                    help="闸五测试面：full=全量（缺省）；auto=变更感知子集（空集回退全量）")
    argv = parser.parse_args()
    repo = Path(argv.repo).resolve()
    mp = Path(argv.manifest)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库目录不存在: %s" % repo})
        return 2
    if not mp.is_file():
        _emit({"ok": False, "error": "manifest 不存在: %s" % mp})
        return 2
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "manifest JSON 非法: %s" % exc})
        return 2
    manifest["__dir__"] = str(mp.resolve().parent)
    manifest["__path__"] = str(mp.resolve())
    approval_path = Path(argv.approval) if argv.approval else None
    if argv.undo:
        return _do_undo(repo, manifest)
    if not argv.apply:
        error = _preconditions(repo, manifest)
        if error:
            _emit({"ok": False, "state": "PROPOSED", "error": error})
            return 2
        error = _apply_checks(repo, manifest, manifest.get("files", []))
        if error:
            _emit({"ok": False, "state": "PROPOSED", "error": error})
            return 2
        _emit({"ok": True, "state": "PROPOSED",
               "files": manifest.get("files", []),
               "note": "预检通过；落盘需审核人批准书 + --apply"})
        return 0
    return _do_apply(repo, manifest, approval_path,
                    test_mode=argv.test_mode)


if __name__ == "__main__":
    sys.exit(main())
