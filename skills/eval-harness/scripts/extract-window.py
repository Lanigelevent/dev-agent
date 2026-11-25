#!/usr/bin/env python3
"""按 diff 全部 hunk 取窗口材料，自检覆盖，抓不到即报 material_defect。

用途:
    评测链路与主流程材料构造共用。窗口 = hunk 区间 ± pad，总长受 max-window 约束；
    输出行带行号索引（`144: 代码`）。pad/max-window 默认读 agent.json args。

用法:
    python extract-window.py --repo /path/repo --sha <fix> --file svc/payment.py
    python extract-window.py --repo . --sha <fix> --file a.py --rev <parent_rev>

退出码:
    0 = 窗口齐全且自检通过
    1 = material_defect（文件在 rev 不存在、hunk 抓不到或超窗）
    2 = 参数/环境错误
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


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
    return p.returncode, p.stdout, p.stderr


def _file_hunks(diff_text, target):
    """单文件 diff 的 hunk 区间 [(start, end)]（新文件行号）。"""
    out = []
    cur = None
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0]
            if path.startswith("b/"):
                path = path[2:]
            cur = path if path == target else None
        elif raw.startswith("@@") and cur:
            m = HUNK_RE.match(raw)
            if m:
                start = int(m.group(2))
                count = int(m.group(3) or 1)
                out.append((start, start + count - 1))
    return out


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="按 hunk 取窗口材料")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True, help="fix 提交 sha")
    parser.add_argument("--file", required=True, help="目标文件（仓库相对路径）")
    parser.add_argument("--pad", type=int, default=None, help="窗口外扩行数（默认 eval_window_pad）")
    parser.add_argument("--max-window", dest="max_window", type=int, default=None,
                        help="单窗口最大行数（默认 eval_window_max_lines）")
    parser.add_argument("--rev", default=None, help="取内容版本（默认 = --sha）")
    parser.add_argument("--config", help="agent.json 路径")
    argv = parser.parse_args()
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    args, _ = load_args(argv.config)
    pad = argv.pad if argv.pad is not None else int(args.get("eval_window_pad", 25))
    max_window = argv.max_window if argv.max_window is not None else int(args.get("eval_window_max_lines", 120))
    rev = argv.rev or argv.sha
    rc, rev_content, _ = _git(repo, ["rev-parse", "--verify", "%s^{commit}" % argv.sha])
    if rc != 0:
        _emit({"ok": False, "error": "sha 不可解析: %s" % argv.sha})
        return 2
    rc, diff_text, _ = _git(repo, ["diff", "%s^" % argv.sha, argv.sha, "--", argv.file])
    if rc != 0:
        rc, diff_text, _ = _git(repo, ["show", "--format=", "--root", argv.sha, "--", argv.file])
    hunks = _file_hunks(diff_text, argv.file) if rc == 0 else []
    rc, content, _ = _git(repo, ["show", "%s:%s" % (rev, argv.file)])
    if rc != 0:
        _emit({"ok": True, "file": argv.file, "sha": argv.sha, "rev": rev,
               "windows": [], "coverage": {"hunks": len(hunks), "covered": 0},
               "material_defect": "文件在 rev %s 不存在" % rev})
        return 1
    file_lines = content.splitlines()
    windows = []
    defect = None
    for i, (start, end) in enumerate(hunks, 1):
        if end - start + 1 > max_window:
            defect = "hunk %d 行数 %d 超过窗口上限 %d" % (i, end - start + 1, max_window)
            break
        w_start = max(1, start - pad)
        w_end = min(len(file_lines), end + pad)
        if w_start > start or w_end < end:
            defect = "hunk %d 无法取到完整窗口" % i
            break
        windows.append({
            "hunk": i,
            "start": w_start,
            "end": w_end,
            "lines": ["%d: %s" % (n, file_lines[n - 1]) for n in range(w_start, w_end + 1)],
        })
    covered = sum(1 for w in windows)
    _emit({
        "ok": defect is None,
        "file": argv.file,
        "sha": argv.sha,
        "rev": rev,
        "pad": pad,
        "max_window": max_window,
        "windows": windows,
        "coverage": {"hunks": len(hunks), "windows": len(windows), "covered": covered},
        "material_defect": defect,
    })
    return 1 if defect else 0


if __name__ == "__main__":
    sys.exit(main())
