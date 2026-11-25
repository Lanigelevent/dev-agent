#!/usr/bin/env python3
"""预检门：校验仓库与变更范围可解析，按规模定档 S/M/L/XL，并给出预算两档估计。

用途:
    主流程步骤 2 的第一道门。仓库不可读或 rev 不可解析时拒绝开审；
    预算两档（typical/upper）都超过 max_review_minutes 时同样拒绝。

用法:
    python preflight.py --repo /path/to/repo --range main..feature
    python preflight.py --repo . --range HEAD~1..HEAD --config /path/agent.json

退出码:
    0 = 通过预检
    1 = 拒绝/需降级（rev 不可解析，或预算两档都超）
    2 = 参数/环境错误（缺参数、非 git 仓库、range 格式非法）
"""
import argparse
import json
import subprocess
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


def _git(repo, git_args):
    p = subprocess.run(
        ["git", "-C", str(repo)] + git_args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _profile(files, lines):
    if files <= 50 and lines <= 3000:
        return "S"
    if files <= 300 and lines <= 30000:
        return "M"
    if files <= 2000 and lines <= 200000:
        return "L"
    return "XL"


def main():
    parser = argparse.ArgumentParser(description="预检门")
    parser.add_argument("--repo", required=True, help="仓库路径")
    parser.add_argument("--range", dest="rev_range", required=True, help="变更范围，形如 A..B")
    parser.add_argument("--config", help="agent.json 路径（缺省自动定位）")
    argv = parser.parse_args()
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    rc, _, _ = _git(repo, ["rev-parse", "--git-dir"])
    if rc != 0:
        _emit({"ok": False, "error": "不是 git 仓库: %s" % repo})
        return 2
    if ".." not in argv.rev_range:
        _emit({"ok": False, "error": "range 格式非法，需形如 A..B"})
        return 2
    base, head = argv.rev_range.split("..", 1)
    if not base or not head:
        _emit({"ok": False, "error": "range 两端都不能为空"})
        return 2
    for rev in (base, head):
        rc, _, _ = _git(repo, ["rev-parse", "--verify", "%s^{commit}" % rev])
        if rc != 0:
            _emit({"ok": False, "reject": "对象不可解析: %s" % rev, "rev": rev})
            return 1
    rc, numstat, _ = _git(repo, ["diff", "--numstat", argv.rev_range])
    if rc != 0:
        _emit({"ok": False, "reject": "取数失败: %s" % _git(repo, ["diff", "--numstat", argv.rev_range])[2]})
        return 1
    files = 0
    lines = 0
    for row in numstat.splitlines():
        parts = row.split("\t")
        if len(parts) != 3:
            continue
        files += 1
        if parts[0] != "-":
            lines += int(parts[0]) + int(parts[1])
    rc, commit_count, _ = _git(repo, ["rev-list", "--count", argv.rev_range])
    commits = int(commit_count) if rc == 0 and commit_count.isdigit() else 0
    rc, is_shallow, _ = _git(repo, ["rev-parse", "--is-shallow-repository"])
    shallow = is_shallow == "true"
    profile = _profile(files, lines)
    manifest_args, config_source = load_args(argv.config)
    config = {
        "max_review_minutes": manifest_args.get("max_review_minutes", 120),
        "max_total_rounds": manifest_args.get("max_total_rounds", 32),
        "data_collection_timeout_seconds": manifest_args.get("data_collection_timeout_seconds", 600),
        "subagent_timeout_seconds": manifest_args.get("subagent_timeout_seconds", 900),
        "retry_max_attempts": manifest_args.get("retry_max_attempts", 3),
        "retry_backoff_base_seconds": manifest_args.get("retry_backoff_base_seconds", 2),
    }
    typical = round(files * 0.4 + lines * 0.004 + commits * 0.5, 1)
    upper = round(files * 1.2 + lines * 0.012 + commits * 1.5, 1)
    max_minutes = float(config["max_review_minutes"])
    if typical > max_minutes and upper > max_minutes:
        _emit(
            {
                "ok": False,
                "reject": "预算两档都超（typical=%s upper=%s > max=%s），需缩小范围或调大预算"
                % (typical, upper, max_minutes),
                "budget": {"typical": typical, "upper": upper, "max": max_minutes},
            }
        )
        return 1
    _emit(
        {
            "ok": True,
            "profile": profile,
            "files": files,
            "source_lines": lines,
            "commits": commits,
            "shallow": shallow,
            "range": argv.rev_range,
            "budget": {
                "typical": typical,
                "upper": upper,
                "max": max_minutes,
                "upper_exceeded": upper > max_minutes,
            },
            "config": config,
            "config_source": config_source or "builtin",
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
