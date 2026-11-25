#!/usr/bin/env python3
"""六视角反向验证扫描：对 findings 做可机械判定的六个视角检查。

用途:
    主流程步骤 8。视角：证据真实性/因果一致性/重复检测/范围越界/误报模式/完备性。
    --self-check 内置篡改样例做反向验证：检查器漏检即失败。

用法:
    python perspective-scan.py --findings findings.json --diff-file change.diff [--experience exp.json]
    python perspective-scan.py --self-check

退出码:
    0 = 无问题（含 self-check 通过）
    1 = 发现存在视角问题，或 self-check 检出检查器漏检
    2 = 参数错误
"""
import argparse
import json
import re
import sys
from pathlib import Path

PERSPECTIVES = ["证据真实性", "因果一致性", "重复检测", "范围越界", "误报模式", "完备性"]
LOC_RE = re.compile(r"^(.+):(\d+)$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _hunks(diff_text):
    out = {}
    cur = None
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            cur = path if path not in ("", "/dev/null") else None
        elif raw.startswith("@@") and cur:
            m = HUNK_RE.match(raw)
            if m:
                start = int(m.group(2))
                count = int(m.group(3) or 1)
                out.setdefault(cur, []).append((start, start + count - 1))
    return out


def scan(findings, diff_text, experience_entries):
    problems, warnings = [], []
    seen = {}
    hunks = _hunks(diff_text)
    diff_blob = diff_text
    for i, f in enumerate(findings):
        loc = str(f.get("loc", ""))
        evidence = str(f.get("evidence", "")).strip()
        cause = str(f.get("cause", "")).strip()
        desc = str(f.get("desc", ""))
        # 视角1 证据真实性
        if evidence and evidence not in diff_blob:
            problems.append({"finding": i, "perspective": PERSPECTIVES[0],
                             "reason": "证据片段不在 diff 原文中"})
        # 视角2 因果一致性
        if not cause or len(cause) < 6:
            problems.append({"finding": i, "perspective": PERSPECTIVES[1],
                             "reason": "原因缺失或过短，因果链不完整"})
        # 视角3 重复检测
        key = (loc, desc)
        if key in seen:
            problems.append({"finding": i, "perspective": PERSPECTIVES[2],
                             "reason": "与 finding #%d 定位与描述重复" % seen[key]})
        else:
            seen[key] = i
        # 视角4 范围越界
        m = LOC_RE.match(loc)
        if not m or m.group(1) not in hunks:
            problems.append({"finding": i, "perspective": PERSPECTIVES[3],
                             "reason": "定位不在本次 diff 范围内"})
        # 视角5 误报模式
        for e in experience_entries or []:
            pat = str(e.get("pattern", ""))
            if pat and (pat.lower() in (desc + evidence).lower()):
                warnings.append({"finding": i, "perspective": PERSPECTIVES[4],
                                 "reason": "命中误报模式 %s（历史驳回 %d 次）"
                                           % (pat, e.get("rejected_count", 0))})
        # 视角6 完备性（仅提示）
        if m and m.group(1) in hunks:
            line = int(m.group(2))
            if not any(s <= line <= t for s, t in hunks[m.group(1)]):
                warnings.append({"finding": i, "perspective": PERSPECTIVES[5],
                                 "reason": "定位行不在任何 hunk 内，覆盖存疑"})
    uncovered = 0
    for path, hs in hunks.items():
        locs = [str(f.get("loc", "")) for f in findings]
        lines_covered = set()
        for loc in locs:
            m = LOC_RE.match(loc)
            if m and m.group(1) == path:
                lines_covered.add(int(m.group(2)))
        for s, t in hs:
            if not any(s <= ln <= t for ln in lines_covered):
                uncovered += 1
    if uncovered:
        warnings.append({"finding": None, "perspective": PERSPECTIVES[5],
                         "reason": "存在 %d 个无结论指向的 hunk" % uncovered})
    return problems, warnings


def self_check():
    """内置篡改样例：干净项通过，伪造证据/越界/重复项必须被抓。"""
    diff = (
        "diff --git a/svc/rate.py b/svc/rate.py\n"
        "--- a/svc/rate.py\n"
        "+++ b/svc/rate.py\n"
        "@@ -1,3 +1,5 @@\n"
        " def charge(amount):\n"
        "+    rate = load_rate()\n"
        "+    password = \"x\" + \"y\"\n"
        "     return amount\n"
    )
    good = {"loc": "svc/rate.py:3", "desc": "硬编码口令", "evidence": "password",
            "cause": "凭据直接写入源码，入库即泄露"}
    fake_evidence = {"loc": "svc/rate.py:2", "desc": "费率逻辑", "evidence": "exec_evil(",
                     "cause": "证据片段在材料中不存在，属于编造"}
    out_of_scope = {"loc": "other/unrelated.py:1", "desc": "越界", "evidence": "x",
                    "cause": "定位文件不在本次 diff 内"}
    dup = dict(good)
    findings = [good, fake_evidence, out_of_scope, dup]
    problems, _ = scan(findings, diff, [])
    caught_fake = any(p["finding"] == 1 and p["perspective"] == PERSPECTIVES[0] for p in problems)
    caught_scope = any(p["finding"] == 2 and p["perspective"] == PERSPECTIVES[3] for p in problems)
    caught_dup = any(p["finding"] == 3 and p["perspective"] == PERSPECTIVES[2] for p in problems)
    clean_pass = not any(p["finding"] == 0 for p in problems)
    return {
        "caught_fabricated_evidence": caught_fake,
        "caught_out_of_scope": caught_scope,
        "caught_duplicate": caught_dup,
        "clean_finding_passes": clean_pass,
    }


def main():
    parser = argparse.ArgumentParser(description="六视角反向验证扫描")
    parser.add_argument("--findings", help="findings JSON 文件")
    parser.add_argument("--diff-file", help="diff 文件")
    parser.add_argument("--experience", help="误报模式库 JSON（可选）")
    parser.add_argument("--self-check", action="store_true", help="内置篡改反向验证")
    argv = parser.parse_args()
    if argv.self_check:
        result = self_check()
        ok = all(result.values())
        _emit({"ok": ok, "mode": "self-check", "checks": result})
        return 0 if ok else 1
    if not argv.findings or not argv.diff_file:
        _emit({"ok": False, "error": "常规模式需要 --findings 与 --diff-file（或用 --self-check）"})
        return 2
    fp, dp = Path(argv.findings), Path(argv.diff_file)
    if not fp.is_file() or not dp.is_file():
        _emit({"ok": False, "error": "findings 或 diff 文件不存在"})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        items = data.get("findings") if isinstance(data, dict) else data
        exp_entries = []
        if argv.experience:
            exp_entries = json.loads(Path(argv.experience).read_text(encoding="utf-8")).get("entries", [])
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "输入不可用: %s" % exc})
        return 2
    problems, warnings = scan(items or [], dp.read_text(encoding="utf-8", errors="replace"), exp_entries)
    _emit({
        "ok": not problems,
        "perspectives": PERSPECTIVES,
        "problems": problems,
        "warnings": warnings,
        "findings_seen": len(items or []),
    })
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
