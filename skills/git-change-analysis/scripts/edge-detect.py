#!/usr/bin/env python3
"""边界形态机械检测：对变更范围探测 11 类边界并逐类给出 evidence。

用途:
    主流程步骤 2。识别 merge 提交、二进制文件、LFS、空提交、子模块、worktree、
    浅克隆、稀疏检出、monorepo 多包、超大单文件、纯重命名，供派发与降级决策参考。

用法:
    python edge-detect.py --repo /path/to/repo --range main..feature
    python edge-detect.py --repo .   # 缺省范围 HEAD~1..HEAD

退出码:
    0 = 检测完成（是否发现边界不改变退出码）
    1 = 对象不可解析（rev 不存在）
    2 = 参数/环境错误（缺参数、非 git 仓库、range 格式非法）
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

EDGE_TYPES = [
    "merge_commit",
    "binary_file",
    "lfs_pointer",
    "empty_commit",
    "submodule_change",
    "worktree",
    "shallow_clone",
    "sparse_checkout",
    "monorepo_multi_package",
    "oversized_single_file",
    "pure_rename",
]
MANIFESTS = {"package.json", "pyproject.toml", "setup.py", "go.mod", "Cargo.toml", "pom.xml", "build.gradle"}


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


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _numstat(repo, rng):
    rc, out, _ = _git(repo, ["diff", "--numstat", rng])
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            rows.append(parts)
    return rows


def _check(repo, rng, oversized):
    edges = []

    def add(name, found, evidence, probe):
        edges.append({"type": name, "found": bool(found), "evidence": evidence, "probe": probe})

    rc, out, _ = _git(repo, ["log", "--merges", "--format=%h %s", rng])
    add("merge_commit", rc == 0 and out.strip(), [l for l in out.splitlines() if l.strip()][:10],
        "git log --merges <range>")

    rows = _numstat(repo, rng)
    binary = [r[2] for r in rows if r[0] == "-"]
    add("binary_file", binary, binary[:10], "git diff --numstat 中增删行为 - 的文件")

    rc, attrs, _ = _git(repo, ["show", "%s:.gitattributes" % rng.split("..")[-1]])
    lfs_evidence = [l for l in attrs.splitlines() if "filter=lfs" in l] if rc == 0 else []
    rc2, diff_text, _ = _git(repo, ["diff", rng])
    if rc2 == 0 and "version https://git-lfs" in diff_text:
        lfs_evidence.append("diff 内含 git-lfs pointer 文本")
    add("lfs_pointer", lfs_evidence, lfs_evidence[:10], ".gitattributes filter=lfs / diff 内 pointer")

    rc, shas, _ = _git(repo, ["rev-list", "--no-merges", rng])
    empty = []
    if rc == 0:
        for sha in [s for s in shas.splitlines() if s.strip()][:500]:
            rc2, _, _ = _git(repo, ["diff-tree", "--quiet", "--no-commit-id", "--root", "-r", sha])
            if rc2 == 0:
                empty.append(sha)
    add("empty_commit", empty, empty[:10], "git diff-tree --quiet -r <sha> 退出码 0")

    rc, raw, _ = _git(repo, ["diff", "--raw", rng])
    submods = [l.split("\t")[-1] for l in raw.splitlines() if l.startswith(":160000")]
    add("submodule_change", submods, submods[:10], "git diff --raw 中 mode 160000 条目")

    rc, gdir, _ = _git(repo, ["rev-parse", "--git-dir"])
    rc2, wtlist, _ = _git(repo, ["worktree", "list", "--porcelain"])
    wt_count = len([l for l in wtlist.splitlines() if l.startswith("worktree")])
    wt_found = (rc == 0 and "worktrees" in gdir) or wt_count > 1
    add("worktree", wt_found, ["git-dir 含 worktrees: %s" % gdir] if "worktrees" in gdir else
        (["worktree list 共 %d 个" % wt_count] if wt_count > 1 else []),
        "git rev-parse --git-dir / git worktree list")

    rc, is_shallow, _ = _git(repo, ["rev-parse", "--is-shallow-repository"])
    add("shallow_clone", rc == 0 and is_shallow.strip() == "true",
        ["rev-parse --is-shallow-repository = %s" % is_shallow.strip()] if rc == 0 else [],
        "git rev-parse --is-shallow-repository")

    rc, sparse_cfg, _ = _git(repo, ["config", "core.sparseCheckout"])
    sparse_file = (Path(gdir) / "info" / "sparse-checkout") if rc == 0 and gdir else None
    add("sparse_checkout", sparse_cfg.strip() == "true" or bool(sparse_file and sparse_file.is_file()),
        ["core.sparseCheckout=%s" % sparse_cfg.strip()] if sparse_cfg.strip() else [],
        "git config core.sparseCheckout / info/sparse-checkout")

    rc, tree, _ = _git(repo, ["ls-tree", "-r", "--name-only", rng.split("..")[-1]])
    groups = {}
    if rc == 0:
        for path in tree.splitlines()[:20000]:
            name = path.rsplit("/", 1)[-1]
            if name in MANIFESTS:
                top = path.split("/")[0] if "/" in path else "(root)"
                groups.setdefault(top, []).append(path)
    mono = {k: v[:5] for k, v in groups.items() if v}
    add("monorepo_multi_package", len(mono) >= 2,
        ["%s: %s" % (k, v) for k, v in sorted(mono.items())][:10] if len(mono) >= 2 else [],
        "git ls-tree -r 中按顶层目录归并包清单文件")

    oversized_files = ["%s (+%s/-%s)" % (r[2], r[0], r[1]) for r in rows
                       if r[0] != "-" and int(r[0]) + int(r[1]) > oversized]
    add("oversized_single_file", oversized_files, oversized_files[:10],
        "单文件增删行数 > oversized_diff_lines(%d)" % oversized)

    rc, ns, _ = _git(repo, ["diff", "--name-status", "-M", rng])
    entries = [l.split("\t") for l in ns.splitlines() if l.strip()]
    renames = ["%s => %s" % (p[1], p[2]) for p in entries if len(p) >= 3 and p[0].startswith("R")]
    all_rename = bool(entries) and all(p[0].startswith("R") for p in entries)
    add("pure_rename", all_rename, renames[:10] if all_rename else [],
        "git diff --name-status -M 全部为 R 状态")
    return edges


def main():
    parser = argparse.ArgumentParser(description="边界形态机械检测")
    parser.add_argument("--repo", required=True, help="仓库路径")
    parser.add_argument("--range", dest="rev_range", default="HEAD~1..HEAD", help="变更范围，形如 A..B")
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
    for rev in (base, head):
        rc, _, err = _git(repo, ["rev-parse", "--verify", "%s^{commit}" % rev])
        if rc != 0:
            _emit({"ok": False, "reject": "对象不可解析: %s (%s)" % (rev, err.strip()[:120])})
            return 1
    manifest_args, _ = load_args(argv.config)
    oversized = manifest_args.get("oversized_diff_lines", 10000)
    edges = _check(repo, argv.rev_range, int(oversized))
    _emit(
        {
            "ok": True,
            "repo": str(repo),
            "range": argv.rev_range,
            "edge_type_count": len(EDGE_TYPES),
            "edges": edges,
            "any_found": any(e["found"] for e in edges),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
