#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段四 4.4 端到端接管：code-task --review 的两条真实路径。

- gate-pass：任务 = 给 agg.py 增加 mean()（纯净补丁），仓库测试通过 →
  评审闭环 PASS → state=DONE 且 manifest 带 review 块；
- gate-human：任务 = 增加 normalize()（补丁里植入未用导入 + == None），
  测试仍通过但他评命中 → 差异率 1.0 > 阈值 → state=NEED_HUMAN、rc=1、
  **不写 manifest**（下游收集器拿不到「看起来正常」的产物）。

宿主协议：CRA_LLM_PROVIDER=host，本脚本按提示词文件名写 response 后
--resume，与 round-60 工作区验收同一驱动方式。

用法：
    py reports/review-round60/run-gate-bench.py [--check]
退出码：0=两条路径都符合预期；1=不符；2=输入/环境错误。
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
WORK = ROOT / "reports" / "_work" / "review-round60-gate"
OUT_ROOT = HERE / "tasks"
FIXTURE = HERE / "fixtures" / "py-calc"

ARMS = [
    {"id": "gate-pass", "expect_state": "DONE", "expect_decision": "PASS",
     "task": "给 pkg/agg.py 增加 mean(items) 函数并跑测试验证",
     "edits": [{"path": "pkg/agg.py",
                "search": "def total(items):\n    return sum(items)",
                "replace": "def total(items):\n    return sum(items)\n\n\n"
                           "def mean(items):\n    values = list(items)\n"
                           "    return sum(values) / len(values)"}]},
    {"id": "gate-human", "expect_state": "NEED_HUMAN",
     "expect_decision": "NEED_HUMAN",
     "task": "给 pkg/agg.py 增加 normalize(items) 函数并跑测试验证",
     "edits": [{"path": "pkg/agg.py",
                "search": "def total(items):\n    return sum(items)",
                "replace": "import os\n\n\n"
                           "def total(items):\n    return sum(items)\n\n\n"
                           "def normalize(items):\n"
                           "    if items == None:\n        return []\n"
                           "    return [float(v) for v in items]"}]},
]


def _run(cmd, env=None, timeout=600):
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          cwd=str(ROOT), env=env)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _json_tail(stdout):
    text = stdout.strip()
    start = text.rfind("\n{")
    if text.startswith("{"):
        start = 0
    else:
        start = start + 1 if start >= 0 else -1
    if start < 0:
        raise ValueError("stdout 无 JSON：%r" % text[-300:])
    return json.loads(text[start:])


def _fresh_repo(dest):
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE, dest, dirs_exist_ok=True)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.email=bench@local", "-c", "user.name=bench",
                  "commit", "-qm", "base"]):
        rc, _out, err = _run(["git", "-C", str(dest)] + args)
        if rc != 0:
            raise RuntimeError("fixture git %s 失败: %s" % (args, err[:200]))


def _run_arm(arm):
    repo = WORK / arm["id"] / "repo"
    _fresh_repo(repo)
    out = OUT_ROOT / arm["id"]
    shutil.rmtree(out, ignore_errors=True)
    env = dict(os.environ)
    env["CRA_LLM_PROVIDER"] = "host"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, str(ROOT / "agent" / "code-task.py"),
           "--repo", str(repo), "--task", arm["task"], "--out", str(out),
           "--review", "self,ruff,astgrep", "--test-cmd",
           "%s -m pytest -q" % sys.executable]
    rc, stdout, stderr = _run(cmd, env=env)
    result = _json_tail(stdout)
    if result.get("state") == "WAIT_HOST_LLM":
        prompt = Path(result["llm_task"])
        response = prompt.with_name(
            prompt.name.replace(".prompt.md", ".response.md"))
        response.write_text(json.dumps(
            {"action": "edit", "edits": arm["edits"],
             "summary": "add function"}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        rc, stdout, stderr = _run(cmd + ["--resume"], env=env)
        result = _json_tail(stdout)
    manifest = {}
    mpath = out / "task-manifest.json"
    if mpath.is_file():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    review = result.get("review") or manifest.get("review") or {}
    return {"id": arm["id"], "rc": rc, "state": result.get("state"),
            "tests": result.get("tests"),
            "review_decision": review.get("decision"),
            "diff_rate": (review.get("metrics") or {}).get("diff_rate"),
            "reasons": review.get("reasons") or result.get("reason"),
            "reasons_list": ([review.get("reasons")]
                             if review.get("reasons") else None),
            "manifest_written": mpath.is_file(),
            "manifest_review": manifest.get("review"),
            "patch": (out / "edits.patch").is_file(),
            "review_json": (out / "review.json").is_file(),
            "report": (out / "task-report.md").is_file(),
            "stderr_tail": stderr.strip().splitlines()[-4:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    argv = parser.parse_args()
    if not FIXTURE.is_dir():
        print(json.dumps({"ok": False, "error": "fixture 不存在"}))
        return 2
    rows = []
    ok = True
    for arm in ARMS:
        try:
            row = _run_arm(arm)
        except Exception as exc:  # noqa: BLE001 - 驱动脚本如实报错退出
            print(json.dumps({"ok": False, "arm": arm["id"],
                              "error": str(exc)}, ensure_ascii=False))
            return 2
        row["expect_state"] = arm["expect_state"]
        row["expect_decision"] = arm["expect_decision"]
        row["match"] = (row["state"] == arm["expect_state"]
                        and row["review_decision"] == arm["expect_decision"]
                        and (row["manifest_written"]
                             == (arm["expect_state"] == "DONE")))
        ok = ok and row["match"]
        rows.append(row)
    bench = {"schema": "review-gate-bench/1",
             "totals": {"cases": len(rows),
                        "as_expected": sum(1 for r in rows if r["match"])},
             "cases": rows}
    if not argv.check:
        (HERE / "gate-bench.json").write_text(
            json.dumps(bench, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    print(json.dumps({"ok": ok,
                      "cases": [{"id": r["id"], "state": r["state"],
                                 "review": r["review_decision"],
                                 "manifest": r["manifest_written"],
                                 "match": r["match"]} for r in rows]},
                     ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
