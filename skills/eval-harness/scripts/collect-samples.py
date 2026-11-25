#!/usr/bin/env python3
"""采集评测样本：从 git 历史收集修复提交，过滤噪音并按文件集合+问题类型去重。

用途:
    评测链路第一步。扫描窗口与提交数上限读 agent.json args
    （eval_scan_window_months / eval_scan_max_commits）；跨编号体系只用 sha。

用法:
    python collect-samples.py --repo /path/repo --out samples.json [--limit 30]

--limit 语义（哨兵值教训，台账 aceff6563e08）：limit 是「采集到此数即停」的
上限而非「不限」；传 0 会立即停止（第一个样本都不取）。全量采集不要传 0，
传显式大数（如 9999）。

退出码:
    0 = 正常（0 个样本也算正常，由调用方决定是否继续）
    2 = 参数/环境错误（非 git 仓库、输出不可写）
"""
import argparse
import datetime
import json
import re
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


FIX_RE = re.compile(r"^(?:fix|bugfix|hotfix)(?:\(|:|\s)|修复|修正|修补", re.I)
NOISE_RE = re.compile(r"docs|readme|comment|注释|文档|typo|chore|\bci\b|flaky|测试稳定|format|lint", re.I)
CLASS_MAP = [
    (re.compile(r"越界|bounds|index|溢出", re.I), "边界"),
    (re.compile(r"leak|泄漏|oom|内存", re.I), "资源"),
    (re.compile(r"race|deadlock|锁|并发|goroutine", re.I), "并发"),
    (re.compile(r"sql|inject|xss|csrf|安全|凭据|secret", re.I), "安全"),
    (re.compile(r"null|nil|none|空指针|空引用", re.I), "空引用"),
]


def _git(repo, git_args):
    p = subprocess.run(
        ["git", "-C", str(repo)] + git_args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, p.stdout, p.stderr


def classify(subject):
    for pat, name in CLASS_MAP:
        if pat.search(subject):
            return name
    return "逻辑"


def collect(repo, limit, months, max_commits):
    rc, out, _ = _git(repo, ["log", "--since=%d.months" % months, "-n", str(max_commits),
                             "--pretty=format:%H%x09%s"])
    if rc != 0:
        return None, "git log 失败"
    samples, skipped, deduped, seen = [], 0, 0, set()
    for line in out.splitlines():
        if len(samples) >= limit:
            break
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        sha, subject = parts
        if not FIX_RE.search(subject):
            continue
        if NOISE_RE.search(subject):
            skipped += 1
            continue
        rc, names, _ = _git(repo, ["show", "--name-only", "--pretty=format:", sha])
        files = sorted({f for f in names.splitlines() if f.strip()})
        if not files:
            skipped += 1
            continue
        defect_class = classify(subject)
        key = (tuple(files), defect_class)
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        rc, parent, _ = _git(repo, ["rev-parse", "%s^" % sha])
        samples.append({
            "fix_commit": sha,
            "parent_rev": parent.strip() if rc == 0 else "",
            "summary": subject,
            "files": files,
            "type_keywords": [w for w in re.split(r"[\W_]+", subject) if len(w) >= 2][:6],
            "defect_class": defect_class,
            "context_type": "单文件" if len(files) == 1 else "多文件",
            "collected_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "evidence_commit": sha,
        })
    return {"samples": samples, "skipped": skipped, "deduped": deduped}, None


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="采集评测样本")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out", required=True, help="样本 JSON 输出路径")
    parser.add_argument("--limit", type=int, default=None, help="样本上限（默认 eval_initial_sample_size）")
    parser.add_argument("--config", help="agent.json 路径")
    argv = parser.parse_args()
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    rc, _, _ = _git(repo, ["rev-parse", "--git-dir"])
    if rc != 0:
        _emit({"ok": False, "error": "不是 git 仓库: %s" % repo})
        return 2
    args, _ = load_args(argv.config)
    limit = argv.limit if argv.limit is not None else int(args.get("eval_initial_sample_size", 30))
    limit = min(limit, int(args.get("max_eval_samples", 100)))
    months = int(args.get("eval_scan_window_months", 12))
    max_commits = int(args.get("eval_scan_max_commits", 5000))
    result, err = collect(repo, limit, months, max_commits)
    if err:
        _emit({"ok": False, "error": err})
        return 2
    out_path = Path(argv.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        _emit({"ok": False, "error": "输出不可写: %s (%s)" % (out_path, exc)})
        return 2
    _emit({
        "ok": True,
        "out": str(out_path),
        "count": len(result["samples"]),
        "skipped": result["skipped"],
        "deduped": result["deduped"],
        "window_months": months,
        "max_commits": max_commits,
        "note": "样本主键为 sha（fix_commit/evidence_commit），跨编号体系不用序号",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
