#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""老仓库运行垫片（agent 层）：让需要旧版 Python 的被审仓库能在本机跑。

背景（round-19 实测）：sympy 1.1 要求 Python ≤3.9（`from collections import
Mapping` 在 3.10 起被移除），本机只有 3.12/3.14 ⇒ 直接导入失败，无法本地
迭代。本垫片补回被移除的别名，让老仓库在本机可导入/可跑测试。

用法（把被审仓库放到 sys.path 首位并注入垫片后执行命令）：
    python agent/legacy_compat.py --repo <被审仓库> -- -c "import sympy; print(sympy.__version__)"
    python agent/legacy_compat.py --repo <被审仓库> -- -m pytest <被审仓库>/sympy -q

实现：把同目录的 legacy_compat/sitecustomize.py 放进 PYTHONPATH——Python 启动
时自动 import sitecustomize，垫片即生效（不改被审仓库、不改全局解释器）。

退出码：0=被执行的命令成功；1=被执行的命令失败（透传其退出码语义）；
2=参数错误。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

SHIM_DIR = Path(__file__).resolve().parent / "legacy_compat"


def build_env(repo=None, extra_path=None):
    """组装带垫片（与可选被审仓库）的环境变量。"""
    env = dict(os.environ)
    parts = [str(SHIM_DIR)]
    if repo:
        parts.append(str(repo))
    if extra_path:
        parts.append(extra_path)
    old = env.get("PYTHONPATH", "")
    if old:
        parts.append(old)
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    return env


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="老仓库运行垫片")
    parser.add_argument("--repo", default="",
                        help="被审仓库路径（放到 sys.path 首位）")
    parser.add_argument("--pythonpath", dest="extra_path", default="",
                        help="追加到 PYTHONPATH 的其他路径")
    parser.add_argument("--print-env", action="store_true",
                        help="只打印将要使用的 PYTHONPATH（不执行命令）")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="-- 之后是要执行的命令")
    argv = parser.parse_args()
    cmd = [c for c in argv.command if c != "--"]
    if not cmd and not argv.print_env:
        _emit({"ok": False, "error": "用法：--repo <仓库> -- <命令...>"})
        return 2
    repo = Path(argv.repo).resolve() if argv.repo else None
    if repo and not repo.is_dir():
        _emit({"ok": False, "error": "仓库不存在: %s" % repo})
        return 2
    env = build_env(repo, argv.extra_path)
    if argv.print_env:
        _emit({"ok": True, "PYTHONPATH": env["PYTHONPATH"],
               "shim": str(SHIM_DIR)})
        return 0
    if not (SHIM_DIR / "sitecustomize.py").is_file():
        _emit({"ok": False, "error": "垫片缺失: %s" % (SHIM_DIR / "sitecustomize.py")})
        return 2
    proc = subprocess.run(cmd, shell=False, env=env)
    return proc.returncode


def _emit(obj):
    import json
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
