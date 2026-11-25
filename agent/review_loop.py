#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评审闭环（阶段四 4.4）：把 agent 补丁送第三方评审器，量化自评/他评差异。

两臂：
- 自评（self）：作者侧机械核验——补丁结构、编辑文件语法树、测试状态；
- 他评（external）：第三方工具对同一补丁的报告——ruff（Python 规则）、
  ast-grep（JS/TS/Python 规则集）、Open Code Review delegate（文件覆盖），
  以及通用 --reviewer-cmd（stdout 输出 {"findings":[...]} 的任意评审器）。

差异口径（可复算）：按「同文件 + 行号邻近（±2）」配对两臂发现，未配对
即差异；diff_rate = (external_only + self_only) / union。diff_rate 超过
阈值 → NEED_HUMAN（转人工），不静默放行；外部臂全部不可用同样转人工
（差异无法量化时不得假装通过）。

用法示例：
    py agent/review_loop.py --repo <补丁工作树> --patch <edits.patch> \
        --reviewers self,ruff,astgrep --ocr <ocr 可执行> --threshold 0.5 \
        --out <报告目录>

退出码：0=PASS；1=NEED_HUMAN（差异超阈值/覆盖缺口/外部臂不可用）；
2=输入或环境错误。
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
from agent.repo_map import syntax_issues  # noqa: E402

SCHEMA = "review-loop/1"
SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go",
               ".java", ".rs"}
ASTGREP_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


class ReviewError(Exception):
    """评审器输入/环境错误（exit 2）。"""


# ------------------------------------------------------------------ 补丁解析
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_patch(patch_text):
    """unified diff → {rel: {"added": [行号...], "removed": n}}（只认 +++ b/）。

    行号是**新文件**侧的行号；删除文件（+++ /dev/null）跳过；重命名按新
    路径记。解析失败不抛异常——补丁结构问题由调用方另行记录。
    """
    files = {}
    current = None
    new_line = 0
    in_hunk = False
    for raw in (patch_text or "").splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            if target.startswith("b/"):
                current = target[2:]
                files.setdefault(current, {"added": [], "removed": 0})
            elif target == "/dev/null":
                current = None
            else:
                current = None
            in_hunk = False
            continue
        if raw.startswith("--- "):
            in_hunk = False
            continue
        m = _HUNK_RE.match(raw)
        if m:
            new_line = int(m.group(1))
            in_hunk = bool(current)
            continue
        if not in_hunk or current is None:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            files[current]["added"].append(new_line)
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            files[current]["removed"] += 1
        elif raw.startswith(" ") or raw == "":
            new_line += 1
    return files


def _changed_files(files):
    return sorted(files)


def _rel_in_repo(repo, rel):
    return (Path(repo) / rel).is_file()


# ------------------------------------------------------------------ 评审器
def reviewer_self(repo, files, patch_text, self_tests="skip", self_issues=None):
    """作者侧核验：补丁结构 + 语法树 + 测试状态。"""
    findings = []
    if not (patch_text or "").strip():
        findings.append({"file": "*", "line": 0, "rule": "self:empty-patch",
                         "severity": "high", "message": "补丁为空"})
    rels = [r for r in _changed_files(files) if _rel_in_repo(repo, r)]
    for item in syntax_issues(repo, rels):
        detail = str(item.get("detail", ""))
        line = 0
        m = re.search(r":(\d+)", detail)
        if m:
            line = int(m.group(1))
        findings.append({"file": detail.split(":", 1)[0],
                         "line": line, "rule": "self:syntax",
                         "severity": "high", "message": detail[:300]})
    for item in (self_issues or []):
        detail = str(item.get("detail", ""))
        findings.append({"file": "*", "line": 0,
                         "rule": "self:patch:%s" % item.get("code", ""),
                         "severity": str(item.get("severity") or "medium"),
                         "message": detail[:300]})
    if self_tests == "fail":
        findings.append({"file": "*", "line": 0, "rule": "self:tests",
                         "severity": "high", "message": "仓库测试未通过"})
    return {"status": "ok", "findings": findings}


def _ruff_exe():
    cand = (os.environ.get("CRA_RUFF") or "").strip()
    if cand and Path(cand).is_file():
        return cand
    found = shutil.which("ruff")
    if found:
        return found
    for rel in (".venv/Scripts/ruff.exe", ".venv/bin/ruff"):
        path = AGENT_ROOT / rel
        if path.is_file():
            return str(path)
    return ""


def reviewer_ruff(repo, files, patch_text):
    """第三方静态规则（ruff）。只统计落在补丁新增行上的命中。"""
    rels = [r for r in _changed_files(files)
            if r.endswith(".py") and _rel_in_repo(repo, r)]
    if not rels:
        return {"status": "skipped", "findings": [],
                "note": "补丁无 Python 文件"}
    exe = _ruff_exe()
    if not exe:
        return {"status": "error", "findings": [],
                "note": "找不到 ruff（CRA_RUFF / PATH / .venv）"}
    proc = subprocess.run(
        [exe, "check", "--output-format", "json", "--select", "E,F,W,B"]
        + rels, shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180, cwd=str(repo))
    try:
        items = json.loads(proc.stdout or "[]")
    except ValueError:
        return {"status": "error", "findings": [],
                "note": "ruff 输出不是 JSON（rc=%d）：%s"
                        % (proc.returncode, (proc.stderr or "")[:200])}
    findings = []
    for item in items:
        rel = str(item.get("filename", "")).replace("\\", "/")
        try:
            rel = Path(rel).resolve().relative_to(
                Path(repo).resolve()).as_posix()
        except (ValueError, OSError):
            rel = rel.rsplit("/", 1)[-1]
        line = int((item.get("location") or {}).get("row") or 0)
        added = files.get(rel, {}).get("added") or []
        if added and line and line not in added:
            continue
        findings.append({"file": rel, "line": line,
                         "rule": "ruff:%s" % item.get("code", ""),
                         "severity": "medium",
                         "message": str(item.get("message", ""))[:300]})
    return {"status": "ok", "findings": findings,
            "note": "ruff rc=%d，%d 条" % (proc.returncode, len(findings))}


def reviewer_astgrep(repo, files, patch_text):
    """第三方 AST 规则（ast-grep 内置规则集，经 engines/astgrep_adapter）。"""
    rels = [r for r in _changed_files(files)
            if Path(r).suffix.lower() in ASTGREP_EXTS
            and _rel_in_repo(repo, r)]
    if not rels:
        return {"status": "skipped", "findings": [],
                "note": "补丁无可扫描的 JS/TS/Python 文件"}
    exe = sys.executable
    adapter = AGENT_ROOT / "engines" / "astgrep_adapter.py"
    if not adapter.is_file():
        return {"status": "error", "findings": [],
                "note": "astgrep_adapter.py 缺失"}
    findings = []
    errors = []
    for rel in rels:
        proc = subprocess.run(
            [exe, str(adapter), "scan", "--file", str(Path(repo) / rel),
             "--rel", rel], shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120)
        try:
            data = json.loads(proc.stdout or "{}")
        except ValueError:
            errors.append("%s: 输出非 JSON" % rel)
            continue
        if not data.get("ok"):
            errors.append("%s: %s" % (rel, data.get("error", "scan 失败")))
            continue
        added = files.get(rel, {}).get("added") or []
        for f in data.get("findings") or []:
            line = int(f.get("line") or 0)
            if added and line and line not in added:
                continue
            findings.append({"file": rel, "line": line,
                             "rule": f.get("rule_id", "astgrep"),
                             "severity": f.get("severity", "中"),
                             "message": str(f.get("reason", ""))[:300]})
    if errors and not findings:
        return {"status": "error", "findings": [], "note": "; ".join(errors)[:300]}
    return {"status": "ok", "findings": findings,
            "note": "扫描 %d 文件，%d 条%s"
                    % (len(rels), len(findings),
                       "；部分失败：" + "; ".join(errors)[:120] if errors else "")}


def reviewer_ocr(repo, files, patch_text, ocr_exe=""):
    """Open Code Review delegate：只取文件覆盖（不调 LLM，无 endpoint 也能跑）。

    `ocr review/scan` 需要 LLM 端点；本仓库没有 key，故只把 delegate 的
    文件清单当覆盖信号——他评发现仍由 ruff/ast-grep/命令评审器提供，
    报告里不得把本项冒充成 OCR 的完整评审。
    """
    exe = (ocr_exe or os.environ.get("CRA_OCR") or shutil.which("ocr") or "")
    if exe and os.path.isfile(exe):
        exe = os.path.abspath(exe)
    if not exe:
        return {"status": "unavailable", "findings": [],
                "note": "未提供 ocr 可执行（--ocr / CRA_OCR / PATH）"}
    proc = subprocess.run(
        [exe, "delegate", "preview", "--color", "never"], shell=False,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(repo))
    if proc.returncode != 0:
        return {"status": "error", "findings": [],
                "note": "ocr delegate 失败（rc=%d）：%s"
                        % (proc.returncode, (proc.stderr or "")[:200])}
    listed = []
    for line in (proc.stdout or "").splitlines():
        m = re.match(r"^\s*-\s+`?([^`\s]+)`?\s+\[(modified|added|deleted|renamed)\]",
                     line)
        if m:
            listed.append(m.group(1).strip().replace("\\", "/"))
    changed = _changed_files(files)
    missing = [r for r in changed if r not in listed]
    return {"status": "ok", "findings": [],
            "coverage": {"reviewable": listed, "missing": missing,
                         "note": "OCR delegate 只列文件，不产出发现"}}


def _split_command(command):
    """命令拆分：Windows 用 posix=False（反斜杠路径不能被 shlex 吃掉）。"""
    if os.name == "nt":
        return [p.strip('"') for p in shlex.split(command, posix=False)]
    return shlex.split(command, posix=True)


def reviewer_command(name, command, repo, files, patch_text):
    """通用命令评审器：stdout 必须是 {"findings":[...]}。"""
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False,
                                     encoding="utf-8", newline="\n") as fh:
        fh.write(patch_text or "")
        patch_path = fh.name
    env = dict(os.environ)
    env.update({"CRA_REVIEW_PATCH": patch_path,
                "CRA_REVIEW_FILES": ",".join(_changed_files(files))})
    try:
        proc = subprocess.run(_split_command(command), shell=False,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300, cwd=str(repo),
                              env=env)
    finally:
        try:
            os.unlink(patch_path)
        except OSError:
            pass
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        return {"status": "error", "findings": [],
                "note": "%s 输出非 JSON（rc=%d）：%s"
                        % (name, proc.returncode, (proc.stderr or "")[:200])}
    findings = []
    for f in data.get("findings") or []:
        findings.append({"file": str(f.get("file", "*")),
                         "line": int(f.get("line") or 0),
                         "rule": str(f.get("rule", name)),
                         "severity": str(f.get("severity", "medium")),
                         "message": str(f.get("message", ""))[:300]})
    return {"status": "ok", "findings": findings,
            "note": "%s rc=%d，%d 条" % (name, proc.returncode, len(findings))}


# ------------------------------------------------------------------ 差异度量
def _norm_file(rel):
    return str(rel or "").replace("\\", "/")


def _dedupe(findings):
    """同一评审器对同一 (文件, 行, 规则) 的重复报告只算一次。

    ruff 对语法错误会把 invalid-syntax 报两遍；不去重会把 union 抬高、把
    差异率算歪（round-60 实踩）。
    """
    seen = set()
    out = []
    for f in findings:
        key = (_norm_file(f.get("file")), int(f.get("line") or 0),
               str(f.get("rule", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def match_findings(self_findings, external_findings, line_tol=2):
    """同文件 + 行号邻近（±2；任一方无行号则按文件配对）→ 贪心配对。"""
    used = set()
    matched = []
    for i, ext in enumerate(external_findings):
        for j, own in enumerate(self_findings):
            if j in used:
                continue
            if _norm_file(ext.get("file")) != _norm_file(own.get("file")):
                continue
            e_line = int(ext.get("line") or 0)
            o_line = int(own.get("line") or 0)
            if e_line and o_line and abs(e_line - o_line) > line_tol:
                continue
            matched.append((i, j))
            used.add(j)
            break
    matched_ext = {i for i, _j in matched}
    matched_own = {j for _i, j in matched}
    ext_only = [f for i, f in enumerate(external_findings)
                if i not in matched_ext]
    own_only = [f for j, f in enumerate(self_findings) if j not in matched_own]
    union = len(external_findings) + len(self_findings) - len(matched)
    diff_rate = (len(ext_only) + len(own_only)) / union if union else 0.0
    return {"matched": len(matched), "external_only": ext_only,
            "self_only": own_only, "union": union,
            "diff_rate": round(diff_rate, 4)}


def run_review(repo, patch_text, reviewers=("self", "ruff", "astgrep"),
               threshold=0.5, self_tests="skip", self_issues=None,
               ocr_exe="", reviewer_cmds=None, out_dir=None):
    """跑一次评审闭环 → 结果 dict（不写文件；out_dir 非空时落 review.json）。"""
    repo = Path(repo)
    if not repo.is_dir():
        raise ReviewError("repo 不存在: %s" % repo)
    files = parse_patch(patch_text)
    if not files:
        raise ReviewError("补丁解析为空（需 unified diff 且含 +++ b/ 路径）")
    results = {}
    for name in reviewers:
        if name == "self":
            results["self"] = reviewer_self(repo, files, patch_text,
                                            self_tests=self_tests,
                                            self_issues=self_issues)
        elif name == "ruff":
            results["ruff"] = reviewer_ruff(repo, files, patch_text)
        elif name == "astgrep":
            results["astgrep"] = reviewer_astgrep(repo, files, patch_text)
        elif name == "ocr":
            results["ocr"] = reviewer_ocr(repo, files, patch_text,
                                          ocr_exe=ocr_exe)
        else:
            raise ReviewError("未知评审器: %r" % name)
    for name, command in (reviewer_cmds or {}).items():
        results[name] = reviewer_command(name, command, repo, files,
                                         patch_text)
    self_findings = _dedupe(list((results.get("self") or {}).get("findings")
                                 or []))
    external_findings = []
    external_status = []
    coverage = None
    for name, res in results.items():
        if name == "self":
            continue
        external_status.append({"name": name, "status": res.get("status"),
                                "note": res.get("note", "")})
        external_findings.extend(res.get("findings") or [])
        if res.get("coverage"):
            coverage = dict(res["coverage"])
    external_findings = _dedupe(external_findings)
    metrics = match_findings(self_findings, external_findings)
    reasons = []
    if metrics["diff_rate"] > float(threshold):
        reasons.append("自评/他评差异率 %.2f > 阈值 %.2f"
                       % (metrics["diff_rate"], float(threshold)))
    # 两臂一致的硬伤也不放行：差异小只说明「看法相同」，不代表补丁干净
    high = [f for f in (self_findings + external_findings)
            if str(f.get("severity", "")).lower() in ("high", "高", "error",
                                                      "严重")]
    if high:
        reasons.append("高严重度发现 %d 条：%s" % (
            len(high), "; ".join("%s:%s" % (f.get("file"), f.get("rule"))
                                 for f in high[:5])))
    if coverage and coverage.get("missing"):
        reasons.append("评审器未覆盖补丁文件：%s"
                       % ", ".join(coverage["missing"]))
    ran = [s for s in external_status if s["status"] in ("ok", "skipped")]
    if external_status and not ran:
        reasons.append("外部评审臂全部不可用，差异无法量化")
    decision = "NEED_HUMAN" if reasons else "PASS"
    result = {
        "schema": SCHEMA, "decision": decision, "threshold": float(threshold),
        "files": [{"path": rel, "added_lines": len(info["added"])}
                  for rel, info in sorted(files.items())],
        "reviewers": results, "external_status": external_status,
        "coverage": coverage,
        "metrics": {k: v for k, v in metrics.items()
                    if k in ("matched", "union", "diff_rate")},
        "high_findings": high,
        "external_only": metrics["external_only"],
        "self_only": metrics["self_only"],
        "self_findings": self_findings,
        "external_findings": external_findings,
        "reasons": reasons,
    }
    if out_dir:
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        (target / "review.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    return result


def _parse_reviewer_cmds(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            raise ReviewError("--reviewer-cmd 需 name=command：%r" % item)
        name, command = item.split("=", 1)
        out[name.strip()] = command.strip()
    return out


def main():
    parser = argparse.ArgumentParser(description="评审闭环（4.4）")
    parser.add_argument("--repo", required=True, help="补丁已应用的工作树")
    parser.add_argument("--patch", required=True)
    parser.add_argument("--reviewers", default="self,ruff,astgrep")
    parser.add_argument("--reviewer-cmd", action="append", default=[],
                        help="name=command（可重复）")
    parser.add_argument("--ocr", default="", help="ocr 可执行路径（可缺省）")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--self-tests", default="skip",
                        choices=("pass", "fail", "skip"))
    parser.add_argument("--out", default="")
    argv = parser.parse_args()
    try:
        patch_text = Path(argv.patch).read_text(encoding="utf-8",
                                                errors="replace")
        result = run_review(
            argv.repo, patch_text,
            reviewers=[r.strip() for r in argv.reviewers.split(",") if r.strip()],
            threshold=argv.threshold, self_tests=argv.self_tests,
            ocr_exe=argv.ocr,
            reviewer_cmds=_parse_reviewer_cmds(argv.reviewer_cmd),
            out_dir=argv.out or None)
    except (ReviewError, OSError) as exc:
        _emit({"ok": False, "schema": SCHEMA, "error": str(exc)})
        return 2
    except subprocess.TimeoutExpired as exc:
        _emit({"ok": False, "schema": SCHEMA,
               "error": "评审器超时：%s" % exc})
        return 2
    _emit(result)
    return 0 if result["decision"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
