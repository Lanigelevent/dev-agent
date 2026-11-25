#!/usr/bin/env python3
"""hunk 覆盖度：把 findings 的定位映射到 diff hunk，输出未覆盖清单。

用途:
    主流程步骤 8 反向验证。只解析行号定位；函数名定位进入 unresolved 清单，
    不得静默忽略（易错点 4 的姊妹约束：漏掉的定位要可见）。

用法:
    python coverage.py --findings findings.json --diff-file change.diff
    python coverage.py --findings findings.json --repo /path/repo --range A..B

退出码:
    0 = 正常
    2 = 参数错误（缺 --findings、缺 diff 来源、JSON 非法）
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LOC_RE = re.compile(r"^(.+):(\d+)$")


def hunks_of(diff_text):
    """按文件聚合 hunk 区间：{path: [(hunk_no, start, end), ...]}。"""
    result = {}
    cur = None
    hunk_no = 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0].strip()
            if path.startswith('"') and path.endswith('"') and len(path) >= 2:
                path = path[1:-1]
            if path.startswith("b/"):
                path = path[2:]
            cur = path if path not in ("", "/dev/null") else None
        elif raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m and cur:
                hunk_no += 1
                start = int(m.group(2))
                count = int(m.group(3) or 1)
                result.setdefault(cur, []).append((hunk_no, start, start + count - 1))
    return result


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="hunk 覆盖度")
    parser.add_argument("--findings", required=True, help="findings JSON 文件")
    parser.add_argument("--diff-file", help="diff 文件")
    parser.add_argument("--repo", help="仓库路径（与 --range 配合）")
    parser.add_argument("--range", dest="rev_range", help="变更范围 A..B（与 --repo 配合）")
    argv = parser.parse_args()
    fp = Path(argv.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "findings 文件不存在: %s" % fp})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "findings JSON 非法: %s" % exc})
        return 2
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        _emit({"ok": False, "error": "findings 需为数组或含 findings 键的对象"})
        return 2
    if argv.diff_file:
        dp = Path(argv.diff_file)
        if not dp.is_file():
            _emit({"ok": False, "error": "diff 文件不存在: %s" % dp})
            return 2
        diff_text = dp.read_text(encoding="utf-8", errors="replace")
    elif argv.repo and argv.rev_range:
        p = subprocess.run(
            ["git", "-C", argv.repo, "diff", argv.rev_range],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if p.returncode != 0:
            _emit({"ok": False, "error": "git diff 失败: %s" % p.stderr.strip()[:200]})
            return 2
        diff_text = p.stdout
    else:
        _emit({"ok": False, "error": "diff 来源缺失：给 --diff-file，或 --repo + --range"})
        return 2
    hunks = hunks_of(diff_text)
    covered = set()
    unresolved = []
    for f in items:
        if not isinstance(f, dict):
            continue
        loc = str(f.get("loc", ""))
        if not loc and f.get("file") is not None and f.get("line") is not None:
            # 兼容硬规则产出的「已证事实」格式（file + line 两字段）
            loc = "%s:%s" % (f["file"], f["line"])
        m = LOC_RE.match(loc)
        if not m:
            unresolved.append({"loc": loc, "reason": "非 文件:行号 定位（如函数名），不静默忽略"})
            continue
        path, line = m.group(1), int(m.group(2))
        if path not in hunks:
            unresolved.append({"loc": loc, "reason": "定位文件不在 diff 内"})
            continue
        for hunk_no, start, end in hunks[path]:
            if start <= line <= end:
                covered.add((path, hunk_no))
    uncovered = []
    for path, hs in hunks.items():
        for hunk_no, start, end in hs:
            if (path, hunk_no) not in covered:
                uncovered.append({"file": path, "hunk": hunk_no, "start": start, "end": end})
    total = sum(len(v) for v in hunks.values())
    _emit(
        {
            "ok": True,
            "total_hunks": total,
            "covered_hunks": len(covered),
            "uncovered": uncovered,
            "unresolved": unresolved,
            "findings_seen": len(items),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
