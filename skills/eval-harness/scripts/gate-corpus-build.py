#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate 语料构建工具（round-83 产品化；r81/r82 一次性脚本转正）。

用途：把 SWE-bench Live 全字段任务 JSONL 适配为 D-045 gate 语料——
  derive: 从 test_patch 静态推导 F2P 候选（类上下文追踪、非 tests/ 前
          程容忍、async 支持）+ 窄化 test_cmds 到测试补丁目标文件
          （f2p-only 口径，r68 先例）。
  refine: 用 live-sample 基线台账回填 F2P（基线实测确认）；识别
          blocked_data（无失败信号）与 env_blocked（环境类失败）形态，
          不把环境失败冒充任务 F2P（round-82 口径纪律）。
  notes:  生成 D-048 协议附录文件（失败测试指针行 + 静态 F2P node），
          r79 实验证实指针解锁编辑行为（D-048 语料设计条款）。

用法示例：
  python gate-corpus-build.py derive --tasks in.jsonl --out out.jsonl
  python gate-corpus-build.py refine --tasks in.jsonl --ledger <dir>/live-sample-ledger.json --out out.jsonl
  python gate-corpus-build.py notes --tasks in.jsonl --out <dir> --template agent/protocol-notes-example.md --rounds 24

退出码：0=成功；1=有可处理问题（如 refine 后仍无任何 F2P 信号）；
2=输入/环境错误。
"""
import argparse
import json
import re
import sys
from pathlib import Path

MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
RE_FILE = re.compile(r"^\+\+\+ b/([^ ]+)$", re.M)
RE_CLASS = re.compile(r"^\+\s*class\s+([A-Za-z0-9_]+)")
RE_DEF = re.compile(r"^\+\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(")
RE_FAILED = re.compile(r"^FAILED (.+?)(?: - |$)", re.M)
ENV_MARKS = ("ModuleNotFoundError", "ImportError", "conftest")


def _is_test_file(path):
    p = path.replace("\\", "/")
    return p.startswith("tests/") or "/tests/" in "/" + p or "/test_" in p


def _read_jsonl(path):
    p = Path(path)
    if not p.is_file():
        raise SystemExit(_err("任务文件不存在: %s" % path, 2))
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except ValueError:
                raise SystemExit(_err("JSONL 行解析失败: %s" % path, 2))
    if not rows:
        raise SystemExit(_err("空任务文件: %s" % path, 2))
    return rows


def _write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _err(msg, code):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    return code


def _note(task, text):
    task["adaptation_note"] = "; ".join(
        x for x in [task.get("adaptation_note", ""), text] if x)


def static_f2p(test_patch):
    """从 test_patch 静态推导 F2P 候选（r81 修正链：类上下文 + 前缀容忍）。"""
    nodes = []
    cur = cls = None
    for ln in test_patch.splitlines():
        m = re.match(r"^\+\+\+ b/([^ ]+\.py)$", ln)
        if m:
            cur, cls = m.group(1), None
            continue
        m = RE_CLASS.match(ln)
        if m:
            cls = m.group(1)
            continue
        m = RE_DEF.match(ln)
        if m and cur and _is_test_file(cur):
            # 顶格 def（无缩进）结束类上下文——类内方法与模块级函数
            # 混排时不得把模块级函数挂到前一个类下（契约反例钉住）。
            if not ln[1:].startswith((" ", "\t")):
                cls = None
            nodes.append("%s::%s" % (cur, m.group(1)) if not cls
                         else "%s::%s::%s" % (cur, cls, m.group(1)))
    return sorted(set(nodes))


def test_files(test_patch):
    return sorted(set(RE_FILE.findall(test_patch)))


def cmd_derive(args):
    rows = _read_jsonl(args.tasks)
    out = []
    for t in rows:
        t = dict(t)
        # 官方 FAIL_TO_PASS 是判分真值（r94 实踩：覆写会让静态解析 0 的
        # 实例丢字段被 judge 拒收）；静态候选只进 static_f2p 供 D-048
        # 指针行；官方缺省时回退静态（保留对原始任务的建列能力）。
        t["static_f2p"] = static_f2p(t.get("test_patch", ""))
        if t.get("fail_to_pass"):
            t["fail_to_pass"] = list(t["fail_to_pass"])
        else:
            t["fail_to_pass"] = t["static_f2p"]
        files = [f for f in test_files(t.get("test_patch", ""))
                 if f.endswith(".py")]
        if files:
            t["test_cmds"] = ["python -m pytest -rA %s" % " ".join(files)]
        _note(t, "gate-corpus-build derive: static f2p candidates "
                 "(class-context parser) + test_cmds narrowed to "
                 "test-patch targets")
        out.append(t)
    _write_jsonl(args.out, out)
    print(json.dumps({"ok": True, "out": str(args.out),
                      "n": len(out),
                      "static_f2p": {t["instance_id"]:
                                     len(t.get("static_f2p") or [])
                                     for t in out}},
                     ensure_ascii=False))
    return 0


def _baseline_rows(ledger_path):
    data = json.loads(Path(ledger_path).read_text(encoding="utf-8"))
    return {r.get("instance_id"): r for r in data.get("results", [])}


def _baseline_failed(row):
    log = row.get("test_log") or ""
    p = Path(log)
    if not log or not p.exists():
        return None
    text = p.read_text(encoding="utf-8", errors="replace")
    return RE_FAILED.findall(text)


def cmd_refine(args):
    rows = _read_jsonl(args.tasks)
    led = _baseline_rows(args.ledger)
    no_signal = []
    for t in rows:
        row = led.get(t["instance_id"])
        if not row:
            continue
        files = test_files(t.get("test_patch", ""))
        failed = _baseline_failed(row)
        if failed is None:
            continue
        in_files = [f for f in failed
                    if any(f.startswith(x) for x in files)]
        env_fail = any(mark in (row.get("detail") or "")
                       or mark in json.dumps(row.get("state") or "")
                       for mark in ENV_MARKS)
        if in_files:
            t["fail_to_pass"] = sorted(set(in_files))
            _note(t, "gate-corpus-build refine: f2p baseline-confirmed "
                     "(%d nodes)" % len(in_files))
        elif not t.get("fail_to_pass"):
            _note(t, "gate-corpus-build refine: blocked_data - no failing "
                     "node in test-patch targets at baseline, no F2P "
                     "signal")
            no_signal.append(t["instance_id"])
        elif env_fail:
            _note(t, "gate-corpus-build refine: env_blocked - baseline "
                     "failures are environment-class, not task F2P")
    _write_jsonl(args.out, rows)
    ok = not no_signal
    print(json.dumps({"ok": ok, "out": str(args.out),
                      "no_signal": no_signal}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_notes(args):
    rows = _read_jsonl(args.tasks)
    tpl = Path(args.template).read_text(encoding="utf-8")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for t in rows:
        files = test_files(t.get("test_patch", "")) or \
            ["tests/ (data-driven: see test_patch)"]
        real = [x for x in (t.get("fail_to_pass")
                            or static_f2p(t.get("test_patch", "")))
                if x and x != "PENDING_BASELINE"]
        ptr = ("The failing tests live in " + ", ".join(files)
               + " (read them early).")
        if real:
            ptr += " Known failing node ids: " + "; ".join(real) + "."
        body = tpl.replace("N rounds", str(args.rounds) + " rounds")
        body = body.replace("at most N/3 rounds",
                            "at most %d rounds" % max(args.rounds // 3, 1))
        body = body + ptr + "\n"
        p = out_dir / ("notes-" + t["instance_id"] + ".md")
        p.write_text(body, encoding="utf-8", newline="\n")
        written.append(str(p))
    print(json.dumps({"ok": True, "written": written,
                      "n": len(written)}, ensure_ascii=False))
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="gate 语料构建工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("derive", help="静态 F2P 推导 + test_cmds 窄化")
    p.add_argument("--tasks", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_derive)
    p = sub.add_parser("refine", help="基线台账回填 F2P + blocked 识别")
    p.add_argument("--tasks", required=True)
    p.add_argument("--ledger", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_refine)
    p = sub.add_parser("notes", help="生成 D-048 协议附录文件")
    p.add_argument("--tasks", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--template", required=True)
    p.add_argument("--rounds", type=int, default=24)
    p.set_defaults(fn=cmd_notes)
    argv = ap.parse_args()
    sys.exit(argv.fn(argv))


if __name__ == "__main__":
    main()
