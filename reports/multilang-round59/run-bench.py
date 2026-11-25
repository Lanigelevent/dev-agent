#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多语言编码实跑台（阶段四 4.2，round-59）：TS 与 Go 各一条任务端到端。

驱动方式：code-task.py 的宿主协议（CRA_LLM_PROVIDER=host）——首跑停在
WAIT_HOST_LLM 并落 llm-tasks/<sha>.prompt.md；本脚本把 host-responses/ 下
的**宿主会话模型已写好的动作**填进 .response.md，再 --resume，直到 DONE
或 NO_PATCH。宿主动作是先写死、由本脚本复放的（可复算），不是另调模型。

用法示例（项目根目录、.venv Python）：
    .venv/Scripts/python reports/multilang-round59/run-bench.py \
        --out reports/multilang-round59

产物：bench.json（schema=multilang-bench/1）+ tasks/<name>/ 下的
llm-tasks 提示、edits.patch、task-manifest.json、task-meta.json、invoke*.json。

退出码：0=两条任务均 DONE 且 tests=pass；1=有任务未 resolved；2=输入错误。
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "agent" / "code-task.py"
PY = sys.executable

TASKS = [
    {
        "name": "ts-calc",
        "language": "ts",
        "fixture": "fixtures/ts-calc",
        "responses": ["host-responses/ts-calc-1.json"],
        "task": "The clamp() helper in lib/calc.ts returns the wrong bound "
                "when the value is outside [lo, hi]; the Node tests in "
                "lib/calc.test.ts fail. Fix the implementation so all "
                "tests pass.",
        "expect_engine": "node",
        "patch_must_contain": "+  if (value < lo) return lo;",
    },
    {
        "name": "go-stack",
        "language": "go",
        "fixture": "fixtures/go-stack",
        "responses": ["host-responses/go-stack-1.json"],
        "task": "Stack.Size() in stack/stack.go returns one more than the "
                "number of items, so `go test ./...` fails. Fix it so all "
                "tests pass.",
        "expect_engine": "go",
        "patch_must_contain": "+\treturn len(s.items)",
    },
]


def run(cmd, env, timeout=600):
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env=env)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"_raw_stdout": proc.stdout, "_raw_stderr": proc.stderr}
    return proc.returncode, data


def git(repo, args):
    return subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def prepare_repo(fixture, workdir):
    # Windows 上旧副本的 .git/objects 偶发被杀软/悬挂 git 锁住：重试几次，
    # 仍锁就换带时间戳的唯一目录（工作副本不需可复现路径）
    for _ in range(3):
        if not workdir.is_dir():
            break
        try:
            shutil.rmtree(workdir)
            break
        except OSError:
            time.sleep(0.5)
    if workdir.is_dir():
        workdir = workdir.with_name(
            workdir.name + "-" + str(int(time.time())))
        shutil.rmtree(workdir, ignore_errors=True)
    shutil.copytree(fixture, workdir)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=bench", "-c", "user.email=b@b",
                  "commit", "-q", "-m", "fixture"]):
        git(workdir, args)
    return workdir


def go_env(env):
    exe = os.environ.get("CRA_GO") or shutil.which("go") or ""
    if not exe:
        cand = ROOT / "reports" / "_work" / "tooling" / "go" / "bin"
        for name in ("go.exe", "go"):
            if (cand / name).is_file():
                exe = str(cand / name)
                break
    if not exe:
        raise SystemExit("找不到 go：设 CRA_GO 或放 reports/_work/tooling/go/bin")
    env["CRA_GO"] = exe
    env["GOTOOLCHAIN"] = "local"
    env["GOPROXY"] = "off"
    env["GOCACHE"] = str(ROOT / "reports" / "_work" / "tooling" / "gocache")
    return exe


def run_task(spec, out_root, work_root, check=False):
    task_dir = (work_root / "check-tasks" / spec["name"]) if check else         (out_root / "tasks" / spec["name"])
    if task_dir.is_dir():
        shutil.rmtree(task_dir)
    task_dir.mkdir(parents=True)
    repo = prepare_repo(ROOT / "reports" / "multilang-round59" / spec["fixture"],
                        work_root / spec["name"])
    env = dict(os.environ)
    env["CRA_LLM_PROVIDER"] = "host"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("REVIEW_LLM_BASE_URL", None)
    env.pop("REVIEW_LLM_MODEL", None)
    if spec["language"] == "go":
        env["_BENCH_GO"] = go_env(env)
    cmd = [str(PY), str(AGENT), "--repo", str(repo), "--task", spec["task"],
           "--out", str(task_dir)]
    invocations = []
    started = time.time()
    state = ""
    for step in range(4):
        rc, data = run(cmd if step == 0 else cmd + ["--resume"], env)
        invocations.append({"step": step, "rc": rc, "state": data.get("state"),
                            "tests": data.get("tests"),
                            "rounds": data.get("rounds")})
        (task_dir / ("invoke-%d.json" % step)).write_text(
            json.dumps({"rc": rc, "data": data}, ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
        state = data.get("state") or ""
        if state == "WAIT_HOST_LLM":
            if step >= len(spec["responses"]):
                break
            response = json.loads(
                (ROOT / "reports" / "multilang-round59" /
                 spec["responses"][step]).read_text(encoding="utf-8"))
            Path(data["llm_response"]).write_text(
                json.dumps(response, ensure_ascii=False, indent=2),
                encoding="utf-8", newline="\n")
            continue
        break
    elapsed = round(time.time() - started, 3)
    manifest = {}
    manifest_path = task_dir / "task-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    patch_field = manifest.get("patch") or ""
    patch_path = Path(patch_field)
    if patch_field and not patch_path.is_absolute():
        patch_path = task_dir / patch_path  # manifest 里是相对产物目录的路径
    patch_text = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else ""
    resolved = bool(state == "DONE" and manifest.get("tests") == "pass"
                    and spec["patch_must_contain"] in patch_text
                    and manifest.get("test_engine") == spec["expect_engine"])
    return {
        "name": spec["name"],
        "language": spec["language"],
        "state": state,
        "tests": manifest.get("tests"),
        "test_engine": manifest.get("test_engine"),
        "expect_engine": spec["expect_engine"],
        "rounds": manifest.get("rounds"),
        "edits": manifest.get("edits"),
        "invocations": len(invocations),
        "elapsed_sec": elapsed,
        "resolved": resolved,
        "patch_sha256": (hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
                         if patch_text else ""),
        "patch_bytes": len(patch_text.encode("utf-8")),
        "patch_file": _rel_or_abs(patch_path, out_root),
        "invoke_log": invocations,
    }


def _rel_or_abs(path, root):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def main():
    parser = argparse.ArgumentParser(description="多语言编码实跑台（TS/Go）")
    parser.add_argument("--out", required=True, help="证据目录（本报告目录）")
    parser.add_argument("--check", action="store_true",
                        help="只跑通路校验：任务产物放工作区、不写 bench.json，"
                             "供结案命令复验（不动已入仓证据）")
    argv = parser.parse_args()
    out_root = Path(argv.out).resolve()
    if not (out_root / "fixtures").is_dir():
        print("缺少 fixtures/：--out 应为 reports/multilang-round59",
              file=sys.stderr)
        return 2
    work_root = out_root.parent / "_work" / "multilang-bench"
    work_root.mkdir(parents=True, exist_ok=True)
    results = [run_task(spec, out_root, work_root, check=argv.check)
               for spec in TASKS]
    if argv.check:
        ok = all(r["resolved"] for r in results)
        print(json.dumps({"ok": ok,
                          "resolved": sum(1 for r in results if r["resolved"]),
                          "n": len(results),
                          "check": True,
                          "patches": {r["name"]: r["patch_sha256"][:12]
                                       for r in results}},
                         ensure_ascii=False))
        return 0 if ok else 1
    bench = {
        "schema": "multilang-bench/1",
        "round": 59,
        "host": "host-session-model (actions pre-authored, replayed)",
        "n": len(results),
        "resolved": sum(1 for r in results if r["resolved"]),
        "note": "宿主会话模型按 host 协议写动作、脚本复放；n=2，只证明"
                "TS/Go 通路可用，不外推成功率",
        "tasks": results,
    }
    (out_root / "bench.json").write_text(
        json.dumps(bench, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    print(json.dumps({"ok": bench["resolved"] == bench["n"],
                      "resolved": bench["resolved"], "n": bench["n"]},
                     ensure_ascii=False))
    return 0 if bench["resolved"] == bench["n"] else 1


if __name__ == "__main__":
    sys.exit(main())
