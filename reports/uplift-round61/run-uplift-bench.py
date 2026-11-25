#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段四 4.1 uplift 基准（round-61）：公开上游提交构造的 XL 多文件任务，
单循环 vs 三角色（--phases）两臂对照，机械化 pytest 判分。

口径（必须如实标注）：
- 语料独立性：任务取自公开上游仓库真实提交（click 831c8f09、tomlkit
  0561e5d），题目 = 只给提交诉求，隐藏实现；测试补丁在开跑前已种入
  （两臂看到同一批失败测试）。
- 判分机械化：judge 在独立 worktree 上重放 agent 补丁后跑 pytest，
  F2P 逐个 node 对账，P2P 跑整批文件；不由模型自评。
- 模型轴：两臂都跑同一宿主模型（本会话），**不构成跨模型结论**；
  n=2 只证机制，不外推成功率。

用法：
    py reports/uplift-round61/run-uplift-bench.py prepare --work <dir>
    py reports/uplift-round61/run-uplift-bench.py judge --task <id> --arm <single|phases> --work <dir>
    py reports/uplift-round61/run-uplift-bench.py report --work <dir> --out bench.json
退出码：0=成功；1=判定未通过/有缺失；2=输入/环境错误。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "reports" / "uplift-round61"
TASKS_FILE = HERE / "tasks.json"
ARMS = ("single", "phases")


def _run(cmd, cwd=None, env=None, timeout=900):
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          cwd=str(cwd or ROOT), env=env)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    raise SystemExit(code)


def _load_tasks():
    if not TASKS_FILE.exists():
        _emit({"ok": False, "error": "缺 tasks.json: %s" % TASKS_FILE}, 2)
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def _task(tasks, tid):
    for t in tasks["tasks"]:
        if t["id"] == tid:
            return t
    _emit({"ok": False, "error": "未知任务 %s" % tid}, 2)


def _worktree(mirror, dest, rev):
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = _run(["git", "-C", str(mirror), "worktree", "add", "-f",
                         "--detach", str(dest), rev])
    if rc != 0:
        _emit({"ok": False, "error": "worktree add 失败",
               "detail": (out + err)[-400:]}, 2)
    return dest


def _commit_all(repo, message):
    for args in (["add", "-A"],
                 ["-c", "user.email=bench@local", "-c", "user.name=bench",
                  "commit", "-qm", message]):
        rc, out, err = _run(["git", "-C", str(repo)] + args)
        if rc != 0:
            _emit({"ok": False, "error": "git %s 失败" % args[0],
                   "detail": (out + err)[-400:]}, 2)
    rc, out, _ = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    return out.strip()


def _judge_env(task, repo):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    parts = [str(Path(repo).resolve())]
    pp = task.get("pythonpath") or ""
    if pp:
        parts.insert(0, str(Path(repo) / pp))
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _pytest(py, repo, targets, env):
    cmd = [str(py), "-m", "pytest", "-q", "--tb=short", "-p",
           "no:cacheprovider"] + list(targets)
    rc, out, err = _run(cmd, cwd=repo, env=env)
    tail = (out or "") + (("\n" + err) if err else "")
    return rc, tail


def cmd_prepare(argv):
    tasks = _load_tasks()
    work = Path(argv.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in tasks["tasks"]:
        patch = (HERE / t["test_patch"]).resolve()
        if not patch.exists():
            _emit({"ok": False, "error": "缺 test.patch: %s" % patch}, 2)
        for arm in ARMS:
            repo = _worktree(ROOT / t["mirror"],
                             work / t["id"] / arm / "repo", t["base_commit"])
            rc, out, err = _run(["git", "-C", str(repo), "apply", str(patch)])
            if rc != 0:
                _emit({"ok": False, "error": "test.patch 应用失败",
                       "task": t["id"], "arm": arm,
                       "detail": (out + err)[-400:]}, 2)
            head = _commit_all(repo, "test: seed failing tests (round-61 bench)")
            rows.append({"task": t["id"], "arm": arm, "repo": str(repo),
                         "seed_head": head})
    _emit({"ok": True, "prepared": rows})


def _extract_patch(repo):
    _run(["git", "-C", str(repo), "add", "-A", "-N"])
    rc, out, err = _run(["git", "-C", str(repo), "diff", "HEAD"])
    if rc != 0:
        raise RuntimeError((out + err)[-400:])
    return out


def cmd_judge(argv):
    tasks = _load_tasks()
    t = _task(tasks, argv.task)
    arm_dir = Path(argv.work).resolve() / t["id"] / argv.arm
    repo = arm_dir / "repo"
    out_dir = arm_dir / "out"
    wt = out_dir / "wt"
    judge_dir = arm_dir / "judge"
    result = {"ok": True, "task": t["id"], "arm": argv.arm,
              "resolved": False, "f2p": None, "p2p": None,
              "patch_bytes": 0, "elapsed_sec": None, "rounds": None}
    patch_path = out_dir / "edits.patch"
    if patch_path.exists():
        patch = patch_path.read_text(encoding="utf-8")
    elif wt.exists():
        # 交付补丁是 DONE 的产物；out/wt 只是运行期残留，可能已被清理
        patch = patch_path.read_text(encoding="utf-8")
    else:
        result["ok"] = False
        result["error"] = "无 out/wt 也无 out/edits.patch（未开跑）"
        _write_json(arm_dir / "judge.json", result)
        _emit(result, 1)
    result["patch_bytes"] = len(patch.encode("utf-8"))
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    head = _run(["git", "-C", str(repo), "rev-parse", "HEAD"])[1].strip()
    judged = _worktree(repo, judge_dir, head)
    patch_file = arm_dir / "agent.patch"
    patch_file.write_text(patch, encoding="utf-8", newline="\n")
    rc, out, err = _run(["git", "-C", str(judged), "apply",
                         "--whitespace=nowarn", str(patch_file)])
    if rc != 0:
        result["ok"] = False
        result["error"] = "补丁无法应用到干净基线"
        result["detail"] = (out + err)[-600:]
        _write_json(arm_dir / "judge.json", result)
        _emit(result, 1)
    src = t.get("submodule_src")
    if src:
        src_dir = (ROOT / src).resolve()
        dest_dir = judged / t["submodule_dest"]
        if src_dir.is_dir() and not any(dest_dir.iterdir()):
            shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
            gitfile = dest_dir / ".git"
            if gitfile.exists():
                gitfile.unlink()
    env = _judge_env(t, judged)
    rc_f2p, tail_f2p = _pytest(py, judged, t["f2p"], env)
    rc_p2p, tail_p2p = _pytest(py, judged, t["p2p"], env)
    result["f2p"] = {"rc": rc_f2p, "targets": len(t["f2p"]),
                     "tail": tail_f2p[-1200:]}
    result["p2p"] = {"rc": rc_p2p, "targets": t["p2p"],
                     "tail": tail_p2p[-1200:]}
    result["resolved"] = (rc_f2p == 0 and rc_p2p == 0)
    meta_path = out_dir / "task-meta.json"
    rep_path = out_dir / "task-report.md"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            result["elapsed_sec"] = meta.get("elapsed_sec")
            result["rounds"] = meta.get("rounds") or meta.get("round")
            result["state"] = meta.get("state")
        except ValueError:
            pass
    if rep_path.exists():
        for line in rep_path.read_text(encoding="utf-8").splitlines():
            if "轮" in line and ":" in line:
                result["report_line"] = line.strip()
                break
    _write_json(arm_dir / "judge.json", result)
    _emit(result, 0 if result["resolved"] else 1)


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def cmd_report(argv):
    tasks = _load_tasks()
    work = Path(argv.work).resolve()
    out = Path(argv.out).resolve()
    rows = []
    for t in tasks["tasks"]:
        for arm in ARMS:
            j = work / t["id"] / arm / "judge.json"
            if not j.exists():
                rows.append({"task": t["id"], "arm": arm,
                             "resolved": None, "note": "未判分"})
                continue
            d = json.loads(j.read_text(encoding="utf-8"))
            rows.append({"task": t["id"], "arm": arm,
                         "resolved": d.get("resolved"),
                         "state": d.get("state"),
                         "f2p_rc": (d.get("f2p") or {}).get("rc"),
                         "p2p_rc": (d.get("p2p") or {}).get("rc"),
                         "patch_bytes": d.get("patch_bytes"),
                         "elapsed_sec": d.get("elapsed_sec"),
                         "rounds": d.get("rounds")})
    per_arm = {}
    for arm in ARMS:
        got = [r for r in rows if r["arm"] == arm and r["resolved"] is not None]
        per_arm[arm] = {
            "tasks": len(got),
            "resolved": sum(1 for r in got if r["resolved"]),
            "elapsed_sec": [r["elapsed_sec"] for r in got],
            "patch_bytes": [r["patch_bytes"] for r in got],
        }
    payload = {
        "version": 1,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "corpus": "公开上游真实提交（click 831c8f09 / tomlkit 0561e5d），"
                  "测试补丁开跑前种入，pytest 机械判分",
        "model_axis": "两臂同一宿主模型（本会话）；不构成跨模型结论",
        "n_note": "n=2 只证机制与判定口径，不外推",
        "arms": per_arm,
        "rows": rows,
    }
    _write_json(out, payload)
    ok = all(r["resolved"] is not None for r in rows)
    _emit({"ok": ok, "out": str(out), "arms": per_arm}, 0 if ok else 1)


def main(argv):
    ap = argparse.ArgumentParser(description="round-61 uplift 基准")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("judge")
    p.add_argument("--task", required=True)
    p.add_argument("--arm", required=True, choices=list(ARMS))
    p.add_argument("--work", required=True)
    p.set_defaults(fn=cmd_judge)
    p = sub.add_parser("report")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_report)
    argv = ap.parse_args(argv)
    argv.fn(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
