#!/usr/bin/env python3
"""断点管理：write 记录进度，read 给续跑位置，verify 校验产物齐全。

用途:
    主流程全程。产物缺失的状态不能沿用；verify 校验失败必须重跑对应步骤。

用法:
    python checkpoint.py write --dir runs/run-1 --step step4 --rounds 2 --artifacts a.json,b.json
    python checkpoint.py read --dir runs/run-1
    python checkpoint.py verify --dir runs/run-1

退出码:
    0 = 正常（read 在无断点时也返回 0 并给 resume_from=step0）
    1 = verify 失败（产物缺失或断点损坏）
    2 = 参数错误（缺子命令/参数、目录不可用）
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

STEP_ORDER = ["step0", "step1", "step2", "step3", "step4", "step5",
              "step6", "step7", "step8", "step9", "step10"]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _path(args):
    return Path(args.dir) / "checkpoint.json"


def _resume_from(step):
    if step not in STEP_ORDER:
        return None
    i = STEP_ORDER.index(step)
    return STEP_ORDER[i + 1] if i + 1 < len(STEP_ORDER) else None


def main():
    parser = argparse.ArgumentParser(description="断点管理")
    sub = parser.add_subparsers(dest="mode")
    for name in ("write", "read", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True, help="断点目录（存放 checkpoint.json）")
        if name == "write":
            p.add_argument("--step", required=True, help="刚完成的步骤，如 step4")
            p.add_argument("--rounds", required=True, type=int, help="已用轮数")
            p.add_argument("--artifacts", default="", help="逗号分隔的产物路径清单")
    argv = parser.parse_args()
    if not argv.mode:
        _emit({"ok": False, "error": "缺少子命令 write|read|verify"})
        return 2
    if argv.mode == "write":
        if argv.step not in STEP_ORDER:
            _emit({"ok": False, "error": "step 越界: %s" % argv.step})
            return 2
        d = Path(argv.dir)
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _emit({"ok": False, "error": "目录不可建: %s (%s)" % (d, exc)})
            return 2
        state = {
            "last_complete_step": argv.step,
            "rounds_used": argv.rounds,
            "artifacts": [a for a in argv.artifacts.split(",") if a.strip()],
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        _path(argv).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        _emit({"ok": True, "mode": "write", "state": state,
               "resume_from": _resume_from(argv.step)})
        return 0
    cp = _path(argv)
    if not cp.is_file():
        if argv.mode == "read":
            _emit({"ok": True, "mode": "read", "exists": False,
                   "resume_from": "step0", "reason": "无断点记录，从头开始"})
            return 0
        _emit({"ok": False, "error": "断点不存在: %s" % cp})
        return 2
    try:
        state = json.loads(cp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "断点损坏: %s" % exc})
        return 1
    if argv.mode == "read":
        _emit({"ok": True, "mode": "read", "exists": True, "state": state,
               "resume_from": _resume_from(state.get("last_complete_step", ""))})
        return 0
    missing = [a for a in state.get("artifacts", []) if not Path(a).exists()]
    if missing:
        _emit({"ok": False, "mode": "verify", "missing": missing,
               "reason": "产物缺失的状态不能沿用，must_rerun 自 last_complete_step"})
        return 1
    _emit({"ok": True, "mode": "verify", "artifacts": state.get("artifacts", []),
           "resume_from": _resume_from(state.get("last_complete_step", ""))})
    return 0


if __name__ == "__main__":
    sys.exit(main())
