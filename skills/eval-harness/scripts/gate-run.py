#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate 评测运行面单命令驱动（round-85 产品化；r77..84 会话一行式转正）。

用途：把 gate 语料（gate-r80-batch.jsonl 型全字段 JSONL）的编码循环
评测收敛为可复现单命令链——prepare（种子 worktree）→ run（code-task
协议 v4）→ judge（委托 live-sample predictions 判分，不复制判分逻辑）
→ report（聚合台账）。

用法示例：
  python gate-run.py prepare --tasks T.jsonl --work W --source-root S [--instances a,b] [--arms single,phases]
  python gate-run.py run --tasks T.jsonl --work W --endpoint https://api.deepseek.com --model deepseek-chat [--arms single,phases] [--rounds 24] [--retry-once] [--dry-run]
  python gate-run.py judge --tasks T.jsonl --work W [--f2p-only] [--instances a,b]
  python gate-run.py report --work W --out bench.json

纪律：
- API key 一律走环境变量（REVIEW_LLM_API_KEY 透传），本脚本不经手
  key 值，也不把它写进任何日志/产物；
- worktree dest 一律绝对路径（r81 坑 91a0a024ece2）；
- PYTHONPATH 前置 repo;repo/src（r82 修正：基线 venv editable 指向旧
  worktree，前置保证循环内测试反馈保真）；
- run 的 0 编辑 fast-done 若 history 有空内容响应标记，--retry-once
  时自动重跑一次（r79/r82 空内容流对策）；
- judge 复用 live-sample 的 predictions 模式（f2p-only 口径），
  f2p_passed 不冒充 resolved。

退出码：0=成功；1=有缺失/未全绿；2=输入/环境错误。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LIVE_SAMPLE = (ROOT / "skills" / "eval-harness" / "scripts"
               / "live-sample.py")
GCB = (ROOT / "skills" / "eval-harness" / "scripts"
       / "gate-corpus-build.py")
NOTES_TPL = ROOT / "agent" / "protocol-notes-example.md"


def _run(cmd, cwd=None, env=None, timeout=1200):
    proc = subprocess.run([str(c) for c in cmd], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(cwd or ROOT), env=env)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _err(msg, code=2):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    raise SystemExit(code)


def _read_rows(path):
    p = Path(path)
    if not p.is_file():
        _err("任务文件不存在: %s" % p)
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rows.append(json.loads(ln))
    if not rows:
        _err("空任务文件: %s" % p)
    return rows


def _select(rows, instances):
    if not instances:
        return rows
    want = set(x.strip() for x in instances.split(",") if x.strip())
    picked = [r for r in rows if r["instance_id"] in want]
    missing = want - {r["instance_id"] for r in picked}
    if missing:
        _err("实例不在任务清单中: %s" % sorted(missing))
    return picked


def _git(args, env=None, timeout=300):
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        e.update(env)
    return _run(["git"] + [str(a) for a in args], env=e, timeout=timeout)


def _seed_count(repo):
    rc, out, _ = _git(["-C", str(repo), "rev-list", "--count", "HEAD"])
    return int(out.strip()) if rc == 0 and out.strip().isdigit() else -1


def _prepare_one(task, arm, work, source_root):
    name = str(task["repo"]).rstrip("/").split("/")[-1]
    iid = task["instance_id"]
    src_cache = Path(source_root) / name
    if not src_cache.is_dir():
        return {"instance_id": iid, "arm": arm, "ok": False,
                "error": "source cache 缺仓: %s" % src_cache}
    dest = (Path(work) / iid / arm).resolve()
    repo = dest / "repo"
    if repo.is_dir() and _seed_count(repo) > 0:
        return {"instance_id": iid, "arm": arm, "ok": True,
                "skipped": "already-seeded", "repo": str(repo)}
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    repo.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = _git(["-C", str(src_cache), "worktree", "add", "-f",
                         "--detach", str(repo), task["base_commit"]])
    if rc != 0:
        return {"instance_id": iid, "arm": arm, "ok": False,
                "error": "worktree add 失败: %s" % (err or out)[-200:]}
    pf = dest / "test.patch"
    pf.write_text(task["test_patch"], encoding="utf-8", newline="\n")
    rc, out, err = _git(["-C", str(repo), "apply", str(pf)])
    if rc != 0:
        return {"instance_id": iid, "arm": arm, "ok": False,
                "error": "test.patch apply 失败: %s" % (err or out)[-200:]}
    for a in (["-C", str(repo), "add", "-A"],
              ["-C", str(repo), "-c", "user.email=gate@local",
               "-c", "user.name=gate", "commit", "-qm",
               "seed (gate-run %s)" % iid]):
        rc, out, err = _git(a)
        if rc != 0:
            return {"instance_id": iid, "arm": arm, "ok": False,
                    "error": "seed commit 失败: %s" % (err or out)[-200:]}
    sub = task.get("submodule") or {}
    if sub.get("src") and sub.get("dest"):
        s = Path(sub["src"])
        d = repo / sub["dest"]
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
            gf = d / ".git"
            if gf.exists():
                gf.unlink()
    return {"instance_id": iid, "arm": arm, "ok": True,
            "repo": str(repo), "seed_head": _git(
                ["-C", str(repo), "rev-parse", "HEAD"])[1][:12]}


def cmd_prepare(args):
    rows = _select(_read_rows(args.tasks), args.instances)
    if not Path(args.source_root).is_dir():
        _err("source_root 不存在: %s" % args.source_root)
    out = []
    for t in rows:
        for arm in args.arms.split(","):
            out.append(_prepare_one(t, arm.strip(), args.work,
                                    args.source_root))
    ok = all(x["ok"] for x in out)
    print(json.dumps({"ok": ok, "prepared": out}, ensure_ascii=False,
                     indent=1))
    return 0 if ok else 1


def _notes_path(work, iid):
    """D-048 附录：GCB notes 产物名为 notes-<iid>.md（r84 演练验证）。"""
    p = Path(work) / iid / ("notes-" + iid + ".md")
    if not p.exists():
        rc, out, err = _run([sys.executable, "-X", "utf8", str(GCB),
                             "notes", "--tasks", _tasks_cache["path"],
                             "--out", str(p.parent), "--template",
                             str(NOTES_TPL),
                             "--rounds", str(_tasks_cache["rounds"])])
        if rc != 0 or not p.exists():
            # notes 失败不阻塞 run（D-048 附录缺失时 code-task 仍可跑）
            return ""
    return str(p)


_tasks_cache = {"path": None, "rounds": 24}


def _empty_stream_hit(meta_path):
    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hist = meta.get("history") or []
    marks = sum(1 for x in hist
                if "不可解析" in str(x) or "empty content" in str(x))
    return (meta.get("edits_applied") in (0, None) and marks >= 2
            and len(hist) >= 2)


def cmd_run(args):
    rows = _select(_read_rows(args.tasks), args.instances)
    _tasks_cache["path"] = str(Path(args.tasks).resolve())
    _tasks_cache["rounds"] = args.rounds
    if not os.environ.get("REVIEW_LLM_API_KEY"):
        _err("环境变量 REVIEW_LLM_API_KEY 未设置（key 不经本脚本）")
    arms = [a.strip() for a in args.arms.split(",")]
    results = []
    for t in rows:
        for arm in arms:
            iid = t["instance_id"]
            base = (Path(args.work) / iid / arm).resolve()
            out = base / ("out-retry" if args.retry_once else "out")
            if (out / "edits.patch").exists():
                results.append({"instance_id": iid, "arm": arm,
                                "skipped": "patch-exists"})
                continue
            repo = base / "repo"
            if not repo.is_dir():
                results.append({"instance_id": iid, "arm": arm,
                                "ok": False, "error": "repo 未 prepare"})
                continue
            env = dict(os.environ)
            env.update({
                "PYTHONDONTWRITEBYTECODE": "1",
                "CRA_LLM_PROVIDER": "openai",
                "REVIEW_LLM_BASE_URL": args.endpoint,
                "REVIEW_LLM_MODEL": args.model,
                "REVIEW_LLM_JSON_MODE": "1",
            })
            pp = os.pathsep.join(
                p for p in [str(repo), str(repo / "src")]
                if Path(p).is_dir())
            if env.get("PYTHONPATH"):
                pp = pp + os.pathsep + env["PYTHONPATH"]
            env["PYTHONPATH"] = pp
            notes = _notes_path(args.work, iid)
            cmd = [sys.executable, "-X", "utf8",
                   str(ROOT / "agent" / "code-task.py"),
                   "--repo", str(repo),
                   "--task", t["problem_statement"],
                   "--out", str(out),
                   "--rounds", str(args.rounds)]
            if arm == "phases":
                cmd.append("--phases")
            if notes:
                cmd.extend(["--protocol-notes", notes])
            if args.test_cmd:
                cmd.extend(["--test-cmd", args.test_cmd])
            if args.dry_run:
                results.append({"instance_id": iid, "arm": arm,
                                "dry_run": True,
                                "cmd": cmd,
                                "env_keys": sorted(
                                    k for k in env if k.startswith(
                                        ("REVIEW_LLM", "CRA_LLM",
                                         "PYTHONPATH")))})
                continue
            t0 = time.time()
            attempts = []
            row = None
            for attempt in range(2 if args.retry_once else 1):
                if attempt == 1:
                    # r79/r82 空内容流对策：0 编辑 + 空白响应标记 ≥2 →
                    # 清空产物重跑一次（间歇性端点怪癖）。
                    shutil.rmtree(out, ignore_errors=True)
                try:
                    rc, so, se = _run(cmd, env=env, timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    row = {"instance_id": iid, "arm": arm, "ok": False,
                           "error": "run 超时"}
                    break
                dt = time.time() - t0
                attempts.append(dt)
                (out / "run-stdout.json").write_text(so,
                                                     encoding="utf-8")
                (out / "run-stderr.log").write_text(se[-4000:],
                                                    encoding="utf-8")
                try:
                    m = json.loads(so or "{}")
                    state, edits = str(m.get("state")), m.get("edits")
                except ValueError:
                    state, edits = "parse_err", None
                row = {"instance_id": iid, "arm": arm, "ok": True,
                       "state": state, "edits": edits,
                       "elapsed_sec": round(sum(attempts), 1),
                       "attempts": len(attempts)}
                if not (edits in (0, None)
                        and _empty_stream_hit(out / "task-meta.json")):
                    break
            results.append(row)
    ok = all(r.get("ok", True) for r in results) and all(
        "error" not in r for r in results)
    print(json.dumps({"ok": ok, "results": results}, ensure_ascii=False,
                     indent=1))
    return 0 if ok else 1


def cmd_judge(args):
    rows = _select(_read_rows(args.tasks), args.instances)
    work = Path(args.work).resolve()
    pred_rows = []
    ids = []
    for t in rows:
        iid = t["instance_id"]
        pp = work / iid / "single" / "out" / "edits.patch"
        if not pp.exists():
            pp = work / iid / "single" / "out-retry" / "edits.patch"
        if not pp.exists():
            continue
        pred_rows.append({"instance_id": iid,
                          "model_patch": pp.read_text(encoding="utf-8")})
        ids.append(iid)
    if not pred_rows:
        _err("工作区无任何 edits.patch（先 prepare+run）", 1)
    pred = work / ("predictions-%s.jsonl" % time.strftime("%H%M%S"))
    with pred.open("w", encoding="utf-8", newline="\n") as f:
        for r in pred_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cmd = [sys.executable, "-X", "utf8", str(LIVE_SAMPLE),
           "--tasks", str(Path(args.tasks).resolve()),
           "--instances", ",".join(ids),
           "--mode", "predictions",
           "--predictions", str(pred),
           "--out", str(work / "judge")]
    if args.f2p_only:
        cmd.append("--f2p-only")
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "cmd": cmd},
                         ensure_ascii=False, indent=1))
        return 0
    rc, out, err = _run(cmd, timeout=args.timeout)
    tail = (out or err).strip().splitlines()
    print(tail[-1] if tail else json.dumps({"ok": False}))
    return 0 if rc == 0 else 1


def cmd_report(args):
    work = Path(args.work).resolve()
    led_path = work / "judge" / "live-sample-ledger.json"
    if not led_path.exists():
        _err("判分台账不存在: %s（先 judge）" % led_path, 1)
    led = json.loads(led_path.read_text(encoding="utf-8"))
    bench = {"version": 1,
             "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "caliber": "f2p-only（f2p_passed 不冒充 resolved，r68 契约）",
             "rows": []}
    for r in led.get("results", []):
        iid = r.get("instance_id")
        pb = 0
        for cand in (work / iid / "single" / "out" / "edits.patch",
                     work / iid / "single" / "out-retry" / "edits.patch"):
            if cand.exists():
                pb = len(cand.read_text(encoding="utf-8").encode())
                break
        bench["rows"].append({"instance_id": iid,
                              "state": r.get("state"),
                              "patch_bytes": pb,
                              "elapsed_sec": r.get("elapsed_sec")})
    counts = {}
    for row in bench["rows"]:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    bench["counts"] = counts
    out = Path(args.out)
    out.write_text(json.dumps(bench, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out), "counts": counts},
                     ensure_ascii=False))
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="gate 评测运行面驱动")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--tasks", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--source-root", required=True)
    p.add_argument("--instances", default="")
    p.add_argument("--arms", default="single")
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("run")
    p.add_argument("--tasks", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--endpoint", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--instances", default="")
    p.add_argument("--arms", default="single")
    p.add_argument("--rounds", type=int, default=24)
    p.add_argument("--test-cmd", default="")
    p.add_argument("--retry-once", action="store_true")
    p.add_argument("--timeout", type=int, default=3000)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("judge")
    p.add_argument("--tasks", required=True)
    p.add_argument("--work", required=True)
    p.add_argument("--instances", default="")
    p.add_argument("--f2p-only", action="store_true")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_judge)
    p = sub.add_parser("report")
    p.add_argument("--work", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_report)
    argv = ap.parse_args()
    sys.exit(argv.fn(argv))


if __name__ == "__main__":
    main()
