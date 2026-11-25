#!/usr/bin/env python3
"""manifest_args：让脚本真读 agent.json 的 args，可校验单个键。

用途:
    作为 locate/load 的参考实现，也可独立调用打印 args 或单键值。
    定位顺序：--agent-json 显式参数 > CWD/agent.json > 项目根（脚本位置上溯）。

用法:
    python manifest_args.py
    python manifest_args.py --agent-json /path/agent.json --key max_review_minutes

退出码:
    0 = 正常
    2 = 参数错误（agent.json 定位不到 / JSON 非法 / --key 不存在）
"""
import argparse
import json
import sys
from pathlib import Path


def locate_agent_json(explicit=None):
    """定位 agent.json：显式参数 > CWD > 项目根（脚本位置上溯）。找不到返回 None。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.cwd() / "agent.json")
    candidates.append(Path(__file__).resolve().parents[3] / "agent.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_args(explicit=None):
    """读取 agent.json 的 args；找不到返回空 dict 与 None 来源。"""
    p = locate_agent_json(explicit)
    if not p:
        return {}, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, str(p)
    return dict(data.get("args") or {}), str(p)


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="读取 agent.json 的 args")
    parser.add_argument("--agent-json", dest="agent_json", help="agent.json 路径")
    parser.add_argument("--key", help="只取单个键")
    argv = parser.parse_args()
    args, source = load_args(argv.agent_json)
    if source is None:
        _emit({"ok": False, "error": "agent.json 定位不到（试 --agent-json 显式指定）"})
        return 2
    if not args:
        _emit({"ok": False, "error": "agent.json 无 args 或不可解析: %s" % source})
        return 2
    if argv.key:
        if argv.key not in args:
            _emit({"ok": False, "error": "键不存在: %s" % argv.key, "source": source})
            return 2
        _emit({"ok": True, "source": source, "key": argv.key, "value": args[argv.key]})
    else:
        _emit({"ok": True, "source": source, "args": args})
    return 0


if __name__ == "__main__":
    sys.exit(main())
