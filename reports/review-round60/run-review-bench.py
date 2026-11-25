#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段四 4.4 验收实跑：评审样例集（干净补丁 + 植入缺陷补丁）。

每个样例：复制 fixture → 建仓提交 → apply 补丁 → run_review（自评 + 他评）
→ 记录判定与差异率，与预期比对。判据（ROADMAP 4.4）：
- 自评与他评差异可量化（matched/union/diff_rate 落盘，可复算）；
- 差异 > 阈值转人工（NEED_HUMAN），干净补丁放行（PASS）。

样例类型：
- clean-*：round-59 真实修复补丁（TS/Go）与本次纯净补丁（Py）→ 期望 PASS；
- seeded-*：在补丁里植入典型缺陷（未用导入/== None；console.log/var/空
  catch/宽松相等）→ 期望 NEED_HUMAN；
- syntax-py：语法错误——自评与他评**会一致命中**，仍须阻断（高严重度门）；
- threshold-probe：同一缺陷补丁把阈值抬到 1.01 → 期望 PASS（证明判定由
  差异率数字驱动，不是常量）；
- cmd-reviewer：经 --review-cmd 接入的第三方评审器与内置臂同点配对。

用法：
    py reports/review-round60/run-review-bench.py [--check]
退出码：0=全部符合预期；1=有样例不符；2=输入/环境错误。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "reports" / "review-round60"
WORK = ROOT / "reports" / "_work" / "review-round60"
CASES_DIR = HERE / "cases"
R59 = ROOT / "reports" / "multilang-round59"

CASES = [
    {"id": "clean-ts",
     "fixture": R59 / "fixtures" / "ts-calc",
     "patch": R59 / "tasks" / "ts-calc" / "edits.patch",
     "reviewers": ["self", "ruff", "astgrep", "ocr"],
     "threshold": 0.5, "expect": "PASS",
     "note": "round-59 真实修复补丁；ocr 只作文件覆盖"},
    {"id": "clean-go",
     "fixture": R59 / "fixtures" / "go-stack",
     "patch": R59 / "tasks" / "go-stack" / "edits.patch",
     "reviewers": ["self", "ruff", "astgrep"],
     "threshold": 0.5, "expect": "PASS",
     "note": "Go 无规则覆盖（ruff/astgrep 均跳过）——覆盖率缺口如实记录"},
    {"id": "clean-py",
     "fixture": HERE / "fixtures" / "py-calc",
     "patch": HERE / "patches" / "clean-py.patch",
     "reviewers": ["self", "ruff", "astgrep"],
     "threshold": 0.5, "expect": "PASS",
     "note": "本次纯净补丁（新增 mean）"},
    {"id": "seeded-py",
     "fixture": HERE / "fixtures" / "py-calc",
     "patch": HERE / "patches" / "seeded-py.patch",
     "reviewers": ["self", "ruff", "astgrep"],
     "threshold": 0.5, "expect": "NEED_HUMAN",
     "note": "植入未用导入 + == None；ruff F401/E711 命中"},
    {"id": "seeded-ts",
     "fixture": HERE / "fixtures" / "ts-fmt",
     "patch": HERE / "patches" / "seeded-ts.patch",
     "reviewers": ["self", "astgrep"],
     "threshold": 0.5, "expect": "NEED_HUMAN",
     "note": "植入 console.log/var/空 catch/宽松相等；ast-grep 命中"},
    {"id": "syntax-py",
     "fixture": HERE / "fixtures" / "py-calc",
     "patch": HERE / "patches" / "syntax-py.patch",
     "reviewers": ["self", "ruff"],
     "threshold": 0.5, "expect": "NEED_HUMAN",
     "note": "两臂一致命中语法错误——差异率低但高严重度仍阻断"},
    {"id": "threshold-probe",
     "fixture": HERE / "fixtures" / "py-calc",
     "patch": HERE / "patches" / "seeded-py.patch",
     "reviewers": ["self", "ruff", "astgrep"],
     "threshold": 1.01, "expect": "PASS",
     "note": "同缺陷补丁抬阈值到 1.01 → 放行；证明判定由差异率数字驱动"},
    {"id": "cmd-reviewer",
     "fixture": HERE / "fixtures" / "py-calc",
     "patch": HERE / "patches" / "seeded-py.patch",
     "reviewers": ["self", "ruff"],
     "reviewer_cmds": {"stub": "<py> <tools/stub-reviewer.py>"},
     "threshold": 0.5, "expect": "NEED_HUMAN",
     "note": "第三方命令评审器接入并计入他评（自评无对应发现）"},
]


def _run(cmd, timeout=300, env=None):
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          cwd=str(ROOT), env=env)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _ocr_exe():
    cand = (os.environ.get("CRA_OCR") or "").strip()
    if cand and Path(cand).is_file():
        return cand
    default = (ROOT / "reports" / "_work" / "tooling" / "ocr"
               / "node_modules" / ".bin" / "ocr.cmd")
    return str(default) if default.is_file() else ""


def _fresh_repo(dest, fixture):
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture, dest, dirs_exist_ok=True)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=bench@local", "-c", "user.name=bench",
                  "commit", "-qm", "base"]):
        rc, _out, err = _run(["git", "-C", str(dest)] + args)
        if rc != 0:
            raise RuntimeError("fixture git %s 失败: %s" % (args, err[:200]))


def _apply(dest, patch):
    rc, _out, err = _run(["git", "-C", str(dest), "apply",
                          "--whitespace=nowarn", str(patch)])
    if rc != 0:
        raise RuntimeError("补丁应用失败 %s: %s" % (patch, err[:300]))


def _resolve_cmd(template):
    return template.replace("<py>", sys.executable).replace(
        "<tools/stub-reviewer.py>",
        str(HERE / "tools" / "stub-reviewer.py"))


def _run_case(case, ocr_exe, write):
    sys.path.insert(0, str(ROOT))
    from agent.review_loop import run_review
    repo = WORK / case["id"] / "repo"
    _fresh_repo(repo, case["fixture"])
    _apply(repo, case["patch"])
    patch_text = Path(case["patch"]).read_text(encoding="utf-8")
    cmds = {name: _resolve_cmd(cmd)
            for name, cmd in (case.get("reviewer_cmds") or {}).items()}
    out_dir = CASES_DIR / case["id"] if write else None
    result = run_review(repo, patch_text,
                        reviewers=case["reviewers"],
                        threshold=case["threshold"],
                        self_tests="pass",
                        reviewer_cmds=cmds,
                        ocr_exe=ocr_exe if "ocr" in case["reviewers"] else "",
                        out_dir=out_dir)
    metrics = result.get("metrics") or {}
    ext = result.get("external_status") or []
    return {
        "id": case["id"], "expect": case["expect"],
        "decision": result["decision"],
        "match": result["decision"] == case["expect"],
        "threshold": case["threshold"],
        "diff_rate": metrics.get("diff_rate"),
        "matched": metrics.get("matched"), "union": metrics.get("union"),
        "high_findings": len(result.get("high_findings") or []),
        "external_status": [{"name": s["name"], "status": s["status"]}
                            for s in ext],
        "coverage": result.get("coverage"),
        "reasons": result.get("reasons") or [],
        "self_n": len(result.get("self_findings") or []),
        "external_n": len(result.get("external_findings") or []),
        "files": result.get("files"),
        "note": case.get("note", ""),
    }


def _render_report(rows, ocr_exe):
    passed = sum(1 for r in rows if r["decision"] == "PASS")
    blocked = sum(1 for r in rows if r["decision"] == "NEED_HUMAN")
    lines = ["# round-60 评审闭环（4.4）样例集实跑", "",
             "判据：差异率 = (external_only + self_only) / union；"
             "差异率 > 阈值或存在高严重度发现 → NEED_HUMAN（转人工）。",
             "",
             "本次 %d 例：PASS %d / NEED_HUMAN %d，与预期一致 %d/%d。"
             % (len(rows), passed, blocked,
                sum(1 for r in rows if r["match"]), len(rows)),
             "",
             "结论口径：",
             "- 干净补丁（round-59 真实修复补丁 ×2 + 本次纯净补丁）全部 PASS，"
             "他评无新增发现（差异率 0）；",
             "- 植入缺陷补丁全部 NEED_HUMAN（ruff F401/E711、ast-grep "
             "console.log/var/空 catch/宽松相等）；",
             "- 语法错误一例两臂**一致命中**（差异率 0）仍被高严重度门阻断——"
             "差异率不是放行的唯一条件；",
             "- threshold-probe 证明判定由差异率数字驱动（同一缺陷补丁抬阈值即"
             "放行），阈值是显式参数而非常量。",
             "",
             "局限（不夸大）：",
             "- OCR 只跑 `delegate preview` 取文件覆盖（本仓库无 LLM 端点，"
             "`ocr review/scan` 未跑，不得当作 OCR 的完整评审）；",
             "- Go 补丁无规则覆盖（ruff/ast-grep 对 .go 跳过），该例的 PASS 只"
             "等于「自评无发现」；",
             "- 自评臂是作者侧机械核验（补丁结构/语法树/测试），不是第二个人；"
             "他评命中而自评无对应发现时差异率必然为 1.0，默认阈值 0.5 因此"
             "偏保守（fail-closed）。",
             "",
             "端到端接管（code-task --review）见 `run-gate-bench.py` 与 "
             "`gate-bench.json`。",
             "",
             "| 样例 | 预期 | 判定 | 差异率 | matched/union | 自评/他评条数 | 说明 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s/%s | %s/%s | %s |" % (
            r["id"], r["expect"], r["decision"],
            r["diff_rate"], r["matched"], r["union"],
            r["self_n"], r["external_n"], r["note"]))
    lines += ["", "OCR 可执行：%s" % (ocr_exe or "未找到（clean-ts 的 ocr 臂记 "
                                    "unavailable，不冒充已评审）"), "",
              "每个样例的完整 review.json 在 cases/<id>/ 下，可复算。"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="复验模式：不写样例产物，只比对判定与预期")
    argv = parser.parse_args()
    ocr_exe = _ocr_exe()
    rows = []
    ok = True
    try:
        for case in CASES:
            row = _run_case(case, ocr_exe, write=not argv.check)
            rows.append(row)
            ok = ok and row["match"]
    except Exception as exc:  # noqa: BLE001 - 驱动脚本如实报错退出
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    bench = {"schema": "review-bench/1", "ocr_exe": ocr_exe,
             "cases": rows,
             "totals": {"cases": len(rows),
                        "as_expected": sum(1 for r in rows if r["match"])}}
    if not argv.check:
        HERE.mkdir(parents=True, exist_ok=True)
        (HERE / "review-bench.json").write_text(
            json.dumps(bench, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        (HERE / "report.md").write_text(_render_report(rows, ocr_exe),
                                        encoding="utf-8", newline="\n")
    print(json.dumps({"ok": ok,
                      "cases": len(rows),
                      "as_expected": sum(1 for r in rows if r["match"]),
                      "decisions": {r["id"]: r["decision"] for r in rows}},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
