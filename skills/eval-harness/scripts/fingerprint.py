#!/usr/bin/env python3
"""项目内容指纹：AGENTS.md + skills/ 整树 + agent.json args 的内容哈希聚合。

用途:
    检测项目漂移。任何文档、脚本、参数改动都会改变指纹；
    BASELINE 与评测报告应记录生成时的指纹值。

用法:
    python fingerprint.py --root /path/dev-agent

退出码:
    0 = 正常
    2 = 参数/环境错误（root 不存在、缺 AGENTS.md/agent.json/skills）
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="项目内容指纹")
    parser.add_argument("--root", required=True, help="项目根目录")
    argv = parser.parse_args()
    root = Path(argv.root)
    agents = root / "AGENTS.md"
    manifest = root / "agent.json"
    skills = root / "skills"
    if not root.is_dir() or not agents.is_file() or not manifest.is_file() or not skills.is_dir():
        _emit({"ok": False, "error": "root 需含 AGENTS.md、agent.json 与 skills/ 目录"})
        return 2
    agents_hash = _sha(agents.read_bytes())
    file_hashes = {}
    skip_dirs = {"__pycache__", ".venv", "llm-tasks", "runs", "reports",
                 "retro", "node_modules", "data", ".git"}
    # v1.16.0 起覆盖引擎层与模型层（转向后这些目录同样是行为面）
    scan_roots = [skills] + [root / d for d in
                             ("engines", "llm", "agent", "mcp")]
    extra_files = [root / "pyproject.toml"]
    for scan_root in scan_roots:
        if not scan_root.is_dir():
            continue
        for p in sorted(scan_root.rglob("*")):
            if p.is_file() and not (skip_dirs & set(p.parts)) and p.suffix != ".pyc":
                rel = p.relative_to(root).as_posix()
                file_hashes[rel] = _sha(p.read_bytes())
    for p in extra_files:
        if p.is_file():
            file_hashes[p.relative_to(root).as_posix()] = _sha(p.read_bytes())
    skills_blob = "".join("%s:%s\n" % (k, file_hashes[k]) for k in sorted(file_hashes))
    skills_hash = _sha(skills_blob.encode("utf-8"))
    try:
        args_data = json.loads(manifest.read_text(encoding="utf-8")).get("args") or {}
        args_hash = _sha(json.dumps(args_data, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "agent.json 不可解析: %s" % exc})
        return 2
    fingerprint = _sha((agents_hash + skills_hash + args_hash).encode("utf-8"))
    _emit({
        "ok": True,
        "fingerprint": fingerprint,
        "components": {"agents_md": agents_hash, "skills": skills_hash, "args": args_hash},
        "files": len(file_hashes),
        "note": "改 AGENTS.md / skills/ 整树 / args 任一内容都会改变指纹",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
