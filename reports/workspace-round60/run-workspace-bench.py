#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段四 4.3 验收实跑：同一任务在本地与容器两档跑出的补丁是否一致。

口径：
- 任务与宿主响应完全一致（同一 action JSON，由本脚本写入 response 文件）；
- 本地档 = 缺省路径（--workspace 不传），容器档 = --workspace
  container:cra-pytest:3.12；
- 判据：两档 state=DONE、tests=pass、edits.patch 字节级 sha256 相同。

用法：
    py reports/workspace-round60/run-workspace-bench.py [--check]
退出码：0=通过；1=不一致或任一路未 DONE；2=输入/环境错误。
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "reports" / "workspace-round60" / "fixtures" / "fix-calc"
WORK = ROOT / "reports" / "_work" / "workspace-round60"
OUT_ROOT = ROOT / "reports" / "workspace-round60" / "tasks"
IMAGE = "cra-pytest:3.12"
TASK = ("修复 calc.py：add 应为加法、label 应输出 Hello 前缀；"
        "跑仓库测试验证")
EDITS = [
    {"path": "calc.py",
     "search": "def add(a, b):\n    return a - b",
     "replace": "def add(a, b):\n    return a + b"},
    {"path": "calc.py",
     "search": '    return "Hi " + name',
     "replace": '    return "Hello " + name'},
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


def _run_arm(name, workspace_spec, repo, out):
    shutil.rmtree(out, ignore_errors=True)
    env = dict(os.environ)
    env["CRA_LLM_PROVIDER"] = "host"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, str(ROOT / "agent" / "code-task.py"),
           "--repo", str(repo), "--task", TASK, "--out", str(out)]
    if workspace_spec:
        cmd += ["--workspace", workspace_spec]
    t0 = time.monotonic()
    rc, stdout, stderr = _run(cmd, env=env)
    result = _json_tail(stdout)
    if result.get("state") == "WAIT_HOST_LLM":
        prompt = Path(result["llm_task"])
        response = prompt.with_name(
            prompt.name.replace(".prompt.md", ".response.md"))
        response.write_text(json.dumps(
            {"action": "edit", "edits": EDITS, "summary": "fix calc"},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        rc, stdout, stderr = _run(cmd + ["--resume"], env=env)
        result = _json_tail(stdout)
    elapsed = round(time.monotonic() - t0, 3)
    patch_path = Path(result.get("patch") or (out / "edits.patch"))
    patch = patch_path.read_text(encoding="utf-8") if patch_path.is_file() \
        else ""
    manifest = {}
    mpath = out / "task-manifest.json"
    if mpath.is_file():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    env_info = result.get("workspace") or manifest.get("workspace")
    if not env_info:
        # 缺省本地档不建 Workspace 对象（保持原 git 路径），环境信息在此补记
        env_info = {"backend": "local", "repo": str(Path(repo).resolve()),
                    "workspace": str((Path(out) / "wt").resolve()),
                    "python": sys.executable,
                    "python_version": platform.python_version(),
                    "platform": platform.system()}
    return {"arm": name, "workspace_spec": workspace_spec or "local",
            "state": result.get("state"), "tests": result.get("tests"),
            "rounds": result.get("rounds"), "edits": result.get("edits"),
            "rc": rc, "elapsed_sec": elapsed,
            "patch_bytes": len(patch.encode("utf-8")),
            "patch_sha256": hashlib.sha256(
                patch.encode("utf-8")).hexdigest(),
            "patch": patch,
            "test_scope": manifest.get("test_scope", ""),
            "test_engine": manifest.get("test_engine", ""),
            "workspace": env_info,
            "stderr_tail": stderr.strip().splitlines()[-6:]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="只判一致性（用于结案复验），退出码 0/1")
    argv = parser.parse_args()
    if not FIXTURE.is_dir():
        print(json.dumps({"ok": False, "error": "fixture 不存在"}))
        return 2
    rc, out, _err = _run(["docker", "image", "inspect", "-f", "{{.Id}}",
                          IMAGE], timeout=60)
    if rc != 0:
        print(json.dumps({"ok": False, "error": "镜像不可用: %s" % IMAGE}))
        return 2
    image_id = out.strip()
    env = dict(os.environ)
    env["CRA_LLM_PROVIDER"] = "host"
    arms = []
    for name, spec in (("local", ""), ("container", "container:" + IMAGE)):
        repo = WORK / name / "repo"
        _fresh_repo(repo)
        out_dir = OUT_ROOT / name
        arms.append(_run_arm(name, spec, repo, out_dir))
    same = (arms[0]["patch_sha256"] == arms[1]["patch_sha256"]
            and arms[0]["patch_bytes"] == arms[1]["patch_bytes"])
    done = all(a["state"] == "DONE" and a["tests"] == "pass" for a in arms)
    bench = {"schema": "workspace-bench/1", "fixture": "fix-calc",
             "task": TASK, "image": IMAGE, "image_id": image_id,
             "identical_patch": same, "both_done": done,
             "arms": [{k: v for k, v in a.items() if k != "patch"}
                      for a in arms]}
    (OUT_ROOT / "bench.json").write_text(
        json.dumps(bench, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    for name, a in (("local", arms[0]), ("container", arms[1])):
        (OUT_ROOT / name / "edits.patch").write_text(
            a["patch"], encoding="utf-8", newline="\n")
    ok = bool(same and done)
    summary = {"ok": ok, "identical_patch": same, "both_done": done,
               "local_sha": arms[0]["patch_sha256"][:16],
               "container_sha": arms[1]["patch_sha256"][:16],
               "local_env": arms[0]["workspace"],
               "container_env": arms[1]["workspace"]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
