#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段二（2.1–2.5）ACI 检索与校验能力的真实语料实测（round-53）。

要回答的问题（判据**先写死在代码里再看数字**）：

2.1 repo map 图排序（Top-8 候选命中率）
  样本 A（构造，天花板守卫）：三仓（django/sympy/matplotlib）可导入包内模块，
    查询 = 模块 docstring 首行，目标 = 模块文件。查询文本就在目标文件里，
    内容扫描天然命中——这一组只用来证明「图排序没有把原来的命中挤掉」。
  样本 B（真实任务，主判据）：`datasets/swe-out/` 中 11 条已 resolved 实例的
    problem_statement，目标文件 = 本项目自产补丁的 `+++ b/` 并集。检索在
    **base_commit 的 detached worktree** 上做（同一 (repo, sha) 只建一次），
    避免克隆 HEAD 漂移把已改名/删除的目标文件变成假未命中；worktree 建不出来
    时退回克隆 HEAD，样本标 `root_mode=clone_head_fallback` 并在报告计数。
  策略对比：refs（现默认，Top-8）/ graph@8（图补充后仍取 8）/ graph@12 /
    reserved6+2（保底 6 个 refs + 2 个图邻居）。
  去留判据：
    constructed hit@8(graph) < hit@8(refs) - 1  → degrade：图排序挤掉了原命中
    real hit@8(best_graph) <= hit@8(refs)       → default_off_only：保持默认关
    real hit@8(best_graph) >  hit@8(refs)       → adopt_best（按最高策略定生产口径）

2.2 搜索排序（前 5 条是否含定义点）
  真实实例的目标文件里抽 2 个符号名作查询；旧口径 = 遍历顺序前 5 条，
  新口径 = 「定义 > 引用 > 注释」排序前 5 条（production `_search_repo`）。
  判据：new_hit > old_hit → keep；否则 revert。

2.4 测试子集（映射覆盖率 + 合成控时）
  真实仓：目标文件 → `_select_test_paths` 选中的测试文件数 vs 全量测试文件
  数（只报覆盖率，不代表这些测试一定可跑）。
  合成仓：同一套 pytest 语料全量 vs 子集各跑一次，报墙钟。
  判据：coverage > 0 且 subset 墙钟 < full 墙钟 → keep；否则 full_only。

2.5 语法树校验（变异语料）
  8 个合法片段（不得误报）+ 10 个坏片段（必须全抓）+ 非 .py 跳过。
  判据：caught == 10 且 false_positive == 0 → keep；否则 fix。

用法：
    .venv/Scripts/python.exe scripts/aci-retrieval-bench.py
    .venv/Scripts/python.exe scripts/aci-retrieval-bench.py --quick
    .venv/Scripts/python.exe scripts/aci-retrieval-bench.py --out reports/aci-bench.json

退出码：0 = 实测跑通（数字难看也是 0）；2 = 依赖仓库/数据缺失或装载失败。
"""
import argparse
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
AGENT = HERE / "agent"
DATASETS = HERE / "datasets"
SWE_OUT = DATASETS / "swe-out"
SWE_REPOS = DATASETS / "swe-repos"

# 构造样本的取样域：与 sibling-test-realbench 同口径（只取可导入包内模块）
CONSTRUCTED_REPOS = ("swe__django", "sympy", "matplotlib")
SKIP_TOP = {"tests", "test", "docs", "doc", "build", "dist", "node_modules",
            ".git", ".venv", "benchmarks", "examples", "galleries",
            "scripts", "bin", "tools", "ci"}
COMMON_SYMBOLS = {"__init__", "get", "set", "save", "update", "delete",
                  "run", "main", "test", "setup", "teardown", "close",
                  "open", "read", "write", "load", "dump", "copy", "apply"}

VERDICT_RULES = {
    "2.1": "constructed 退步>1 → degrade；real best_graph<=refs → default_off_only；"
           "real best_graph>refs → adopt_best",
    "2.2": "new_hit>old_hit → keep；否则 revert",
    "2.4": "coverage>0 且 subset_sec<full_sec → keep；否则 full_only",
    "2.5": "caught==10 且 false_positive==0 → keep；否则 fix",
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _progress(msg):
    print("[aci-bench] %s" % msg, file=sys.stderr, flush=True)


class RepoCache:
    """同一仓库的地图/图只建一次（关键词随任务变，扫描仍按任务跑）。"""

    def __init__(self, repo_mod):
        self.repo_mod = repo_mod
        self._maps = {}
        self._graphs = {}

    def map(self, repo):
        key = str(repo)
        if key not in self._maps:
            t0 = time.monotonic()
            self._maps[key] = self.repo_mod.build_map(repo)
            _progress("build_map %s %.1fs" % (repo.name,
                                              time.monotonic() - t0))
        return self._maps[key]

    def graph(self, repo):
        key = str(repo)
        if key not in self._graphs:
            t0 = time.monotonic()
            self._graphs[key] = self.repo_mod.build_import_graph(repo)
            _progress("import graph %s %.1fs" % (repo.name,
                                                 time.monotonic() - t0))
        return self._graphs[key]


def _reserved_policy(refs, extra, cap=8, slots=2):
    """保底槽位策略：refs 头部 + 图邻居若干，不足再补 refs。"""
    head = list(refs[:max(cap - slots, 0)])
    seen = {c["file"] for c in head}
    tail = [c for c in extra if c["file"] not in seen][:slots]
    out = head + tail
    if len(out) < cap:
        seen = {c["file"] for c in out}
        out += [c for c in refs if c["file"] not in seen][:cap - len(out)]
    return out[:cap]


def _hit(files, targets):
    return bool(set(files) & set(targets))


def _first_target_rank(files, targets):
    for i, rel in enumerate(files, 1):
        if rel in targets:
            return i
    return 0


# ------------------------------------------------------------------ 2.1 采样


def _constructed_samples(repo, repo_mod, per_repo):
    """可导入包内模块 → (query=docstring 首行, target=模块文件)。"""
    picked = []
    files = []
    for path in sorted(Path(repo).rglob("*.py")):
        rel = path.relative_to(repo).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts[:-1]):
            continue
        if set(parts[:-1]) & SKIP_TOP:
            continue
        stem = parts[-1][:-3] if parts[-1].endswith(".py") else parts[-1]
        if stem.startswith("test_") or stem in ("setup", "conftest", "__main__"):
            continue
        if not repo_mod._module_names(repo, rel):
            continue
        files.append(rel)
    if not files:
        return []
    ordered = random.Random(53).sample(files, min(len(files), 400))
    for rel in ordered[:300]:
        if len(picked) >= per_repo:
            break
        try:
            text = (Path(repo) / rel).read_text(encoding="utf-8",
                                                errors="replace")
        except OSError:
            continue
        line = ""
        try:
            import ast as _ast
            doc = (_ast.get_docstring(_ast.parse(text)) or "").strip()
            line = " ".join(doc.splitlines()[0].split()) if doc else ""
        except (SyntaxError, ValueError):
            match = re.search(r'^\s*(?:"""|\'\'\')(.+?)(?:"""|\'\'\')',
                              text, re.S)
            if match:
                line = " ".join(match.group(1).strip().split())
        if len(line) < 20 or len(line) > 400:
            continue
        picked.append({"id": "%s::%s" % (Path(repo).name, rel),
                       "kind": "constructed", "repo": str(repo),
                       "targets": [rel], "query": line})
    return picked


def _load_real_samples():
    """已 resolved 实例（problem_statement + 自产补丁的目标文件）。"""
    caliber_path = SWE_OUT / "agent-sample" / "caliber-current.json"
    inst_path = SWE_OUT / "agent-instances.json"
    if not (caliber_path.is_file() and inst_path.is_file()):
        return [], "缺少 datasets/swe-out（评测语料不入库，需本机存在）"
    caliber = json.loads(caliber_path.read_text(encoding="utf-8"))
    instances = json.loads(inst_path.read_text(encoding="utf-8"))
    resolved = [k for k, v in (caliber.get("detail") or {}).items()
                if v.get("resolved")]
    samples = []
    for iid in resolved:
        rec = instances.get(iid) or {}
        repo_name = str(rec.get("repo") or "").split("/")[-1]
        repo = None
        for cand in (SWE_REPOS / ("swe__" + repo_name),
                     SWE_REPOS / repo_name,
                     SWE_REPOS / str(rec.get("repo") or "").replace("/", "__")):
            if cand.is_dir():
                repo = cand
                break
        if repo is None:
            continue
        # 自产补丁的目标文件（同实例多版本一致，取任一 run 目录即可）
        targets = []
        for run_dir in sorted((SWE_OUT / "agent-sample").glob(iid + "*")):
            patch = run_dir / "edits.patch"
            if not patch.is_file():
                continue
            text = patch.read_text(encoding="utf-8", errors="replace")
            targets = sorted(set(re.findall(r"^\+\+\+ b/(.+)$", text, re.M)))
            if targets:
                break
        if not targets or not rec.get("base_commit"):
            continue
        samples.append({"id": iid, "kind": "real_task",
                        "repo": str(repo),
                        "base_commit": str(rec.get("base_commit")),
                        "targets": targets,
                        "query": str(rec.get("problem_statement") or "")})
    return samples, None


def _prepare_roots(samples):
    """真实任务样本 → 在 base_commit 快照上跑检索（不拿克隆 HEAD 顶替）。

    返回 (roots, made, tmpdir)：roots[i] 与 samples[i]["root"] 对齐；made 是
    待清理的 (repo, worktree) 列表。base_commit 不可用时退回克隆 HEAD 并在
    样本上标 root_mode=clone_head_fallback（报告会显式计数）。
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="aci-roots-"))
    made, by_key = [], {}
    for idx, sample in enumerate(samples):
        repo = Path(sample["repo"])
        sha = str(sample.get("base_commit") or "")
        key = (str(repo), sha)
        if key not in by_key:
            root, mode = repo, "clone_head_fallback"
            if sha:
                probe = subprocess.run(
                    ["git", "-C", str(repo), "cat-file", "-e",
                     sha + "^{commit}"], shell=False,
                    capture_output=True)
                if probe.returncode == 0:
                    dest = tmpdir / ("wt-%02d" % len(made))
                    add = subprocess.run(
                        ["git", "-C", str(repo), "worktree", "add",
                         "--detach", str(dest), sha], shell=False,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
                    if add.returncode == 0:
                        root, mode = dest, "worktree@base_commit"
                        made.append((repo, dest))
                    else:
                        _progress("worktree 建立失败 %s: %s"
                                  % (sample["id"],
                                     (add.stderr or "")[:200]))
            by_key[key] = (root, mode)
            _progress("root %s → %s" % (sample["id"], by_key[key][1]))
        sample["root"] = str(by_key[key][0])
        sample["root_mode"] = by_key[key][1]
    return made, tmpdir


def _cleanup_roots(made, tmpdir):
    for repo, dest in made:
        subprocess.run(["git", "-C", str(repo), "worktree", "remove",
                        "--force", str(dest)], shell=False,
                       capture_output=True)
    shutil.rmtree(tmpdir, ignore_errors=True)


def bench_map_rank(rm_mod, cache, samples, real_start):
    """2.1：refs / graph@8 / graph@12 / reserved6+2 的 Top-8 命中对比。"""
    rows = []
    for sample in samples:
        root = Path(sample["root"])
        t0 = time.monotonic()
        repo_map = cache.map(root)
        keywords = rm_mod.extract_keywords(sample["query"])
        refs = rm_mod.merge_candidates(
            rm_mod.rank_candidates(repo_map, keywords),
            rm_mod.scan_candidates(root, keywords))
        graph = cache.graph(root)
        extra = rm_mod.graph_rank(graph, refs, keywords, limit=12)
        g8 = rm_mod.merge_candidates(refs, extra, limit=8)
        g12 = rm_mod.merge_candidates(refs, extra, limit=12)
        reserved = _reserved_policy(refs, extra)
        # r197 AB-17 新变体（aider 式大份额/纯中心度装填；D-031 单变量重验）：
        #   reserved4+4 = refs 头部 4 + 中心度 4（大份额腾槽）
        #   cent8_backfill = 中心度优先取满 8，refs 回填（aider 装填形态）
        #   cent8_pure = 仅中心度 extras（上限对照，不足不补）
        r44 = _reserved_policy(refs, extra, cap=8, slots=4)
        extra_files = {c["file"] for c in extra}
        cent8_bf = (list(extra)
                    + [c for c in refs if c["file"] not in extra_files])[:8]
        cent8_pure = list(extra)[:8]
        targets = set(sample["targets"])
        row = {
            "id": sample["id"], "kind": sample["kind"],
            "repo": Path(sample["repo"]).name, "targets": sample["targets"],
            "root_mode": sample.get("root_mode", "clone"),
            "refs_n": len(refs), "extra_n": len(extra),
            "refs_hit8": _hit([c["file"] for c in refs], targets),
            "graph_hit8": _hit([c["file"] for c in g8], targets),
            "graph_hit12": _hit([c["file"] for c in g12], targets),
            "reserved_hit8": _hit([c["file"] for c in reserved], targets),
            "r44_hit8": _hit([c["file"] for c in r44], targets),
            "cent8_bf_hit8": _hit([c["file"] for c in cent8_bf], targets),
            "cent8_pure_hit8": _hit([c["file"] for c in cent8_pure], targets),
            "refs_rank": _first_target_rank([c["file"] for c in refs],
                                            targets),
            "graph_rank": _first_target_rank([c["file"] for c in g8],
                                             targets),
            "reserved_rank": _first_target_rank(
                [c["file"] for c in reserved], targets),
            "sec": round(time.monotonic() - t0, 2),
        }
        rows.append(row)
        _progress("2.1 %s refs=%s g8=%s g12=%s rsv=%s"
                  % (sample["id"], row["refs_hit8"], row["graph_hit8"],
                     row["graph_hit12"], row["reserved_hit8"]))

    def _summary(group):
        if not group:
            return {"n": 0}
        return {
            "n": len(group),
            "refs_hit8": sum(r["refs_hit8"] for r in group),
            "graph_hit8": sum(r["graph_hit8"] for r in group),
            "graph_hit12": sum(r["graph_hit12"] for r in group),
            "reserved_hit8": sum(r["reserved_hit8"] for r in group),
            "r44_hit8": sum(r["r44_hit8"] for r in group),
            "cent8_bf_hit8": sum(r["cent8_bf_hit8"] for r in group),
            "cent8_pure_hit8": sum(r["cent8_pure_hit8"] for r in group),
            "graph_added_files": sum(r["extra_n"] for r in group),
        }

    constructed = rows[:real_start]
    real = rows[real_start:]
    constructed_sum = _summary(constructed)
    real_sum = _summary(real)
    policies = ("refs", "graph", "reserved")
    best_policy, best_hits = "refs", real_sum.get("refs_hit8", 0)
    for name, key in (("graph@8", "graph_hit8"),
                      ("graph@12", "graph_hit12"),
                      ("reserved6+2", "reserved_hit8"),
                      ("refs4+centrality4", "r44_hit8"),
                      ("centrality8_backfill", "cent8_bf_hit8"),
                      ("centrality8_pure", "cent8_pure_hit8")):
        hits = real_sum.get(key, 0)
        if hits > best_hits:
            best_policy, best_hits = name, hits
    if not real:
        verdict = "sample_missing"
    elif constructed and constructed_sum["graph_hit8"] < \
            constructed_sum["refs_hit8"] - 1:
        verdict = "degrade"
    elif best_hits <= real_sum.get("refs_hit8", 0):
        verdict = "default_off_only"
    else:
        verdict = "adopt_best"
    return {"samples": rows, "constructed": constructed_sum,
            "real": real_sum, "best_policy": best_policy,
            "verdict": verdict, "rule": VERDICT_RULES["2.1"],
            "policies": list(policies)}


# ------------------------------------------------------------------ 2.2 搜索


def _extract_symbols(path, limit=2):
    """目标文件里的 def/class 名（去重、去常用名、取较长者）。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)",
                         line)
        if not match:
            continue
        name = match.group(1)
        if len(name) < 5 or name in COMMON_SYMBOLS or name in \
                ("__repr__", "__str__", "__eq__", "__hash__"):
            continue
        found.append((name, lineno))
    seen, out = set(), []
    for name, lineno in found:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, lineno))
    out.sort(key=lambda x: -len(x[0]))
    return out[:limit]


def _old_search_first(src, query, ct_mod, need=5, max_files=2000,
                      max_file_bytes=512 * 1024):
    """旧口径（round-53 前）：遍历顺序的前 need 条命中。"""
    needle = query.casefold()
    hits = []
    scanned = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in
                         ct_mod.SEARCH_SKIP_DIRS)
        for name in sorted(files):
            path = Path(root) / name
            if path.is_symlink():
                continue
            if path.suffix.lower() not in ct_mod.SEARCH_TEXT_EXTS:
                continue
            rel = path.relative_to(src).as_posix()
            if scanned >= max_files:
                break
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line.casefold():
                    hits.append((rel, lineno))
                    if len(hits) >= need:
                        return hits, scanned
        if scanned >= max_files:
            break
    return hits, scanned


def bench_search_rank(ct_mod, real_samples, per_sample=2):
    rows = []
    for sample in real_samples:
        root = Path(sample["root"])
        for target in sample["targets"][:1]:
            for symbol, def_line in _extract_symbols(root / target,
                                                     limit=per_sample):
                t0 = time.monotonic()
                old_hits, _ = _old_search_first(root, symbol, ct_mod)
                ok, obs = ct_mod._search_repo(root, symbol, max_hits=5)
                new_hits = []
                for line in (obs.splitlines() if ok else [])[1:]:
                    match = re.match(r"^(.+?):(\d+): ", line)
                    if match:
                        new_hits.append((match.group(1), int(match.group(2))))
                want = (target, def_line)
                row = {
                    "id": sample["id"], "symbol": symbol,
                    "target": target, "def_line": def_line,
                    "old_hit": want in old_hits,
                    "new_hit": want in new_hits,
                    "old_first": old_hits[:5], "new_first": new_hits[:5],
                    "sec": round(time.monotonic() - t0, 2),
                }
                rows.append(row)
                _progress("2.2 %s %s old=%s new=%s"
                          % (sample["id"], symbol, row["old_hit"],
                             row["new_hit"]))
    old_n = sum(r["old_hit"] for r in rows)
    new_n = sum(r["new_hit"] for r in rows)
    if not rows:
        verdict = "sample_missing"
    elif new_n > old_n:
        verdict = "keep"
    else:
        verdict = "revert"
    return {"samples": rows, "n": len(rows), "old_hit": old_n,
            "new_hit": new_n, "verdict": verdict,
            "rule": VERDICT_RULES["2.2"]}


# ------------------------------------------------------------------ 2.4 子集


def _count_test_files(worktree, ct_mod_arg):
    total = 0
    for path in ct_mod_arg._discover_test_paths(worktree):
        if path.is_dir():
            total += len(list(path.rglob("test_*.py")))
        elif path.is_file():
            total += 1
    return total


def bench_test_subset(ct_mod_arg, real_samples, timing=True):
    rows = []
    for sample in real_samples:
        root = Path(sample["root"])
        total = _count_test_files(root, ct_mod_arg)
        picked = ct_mod_arg._select_test_paths(root, sample["targets"])
        rows.append({"id": sample["id"], "targets": sample["targets"],
                     "selected": picked, "selected_n": len(picked),
                     "total_n": total,
                     "coverage": round(len(picked) / total, 3) if total else 0})
        _progress("2.4 %s picked=%d/%d" % (sample["id"], len(picked), total))
    timing_result = {"ran": False}
    if timing:
        timing_result = _subset_timing(ct_mod_arg)
    audit_result = _audit_probe(ct_mod_arg)
    covered = sum(1 for r in rows if r["selected_n"] > 0)
    ok_timing = (not timing_result.get("ran")
                 or timing_result.get("subset_sec", 1) <
                 timing_result.get("full_sec", 0))
    if not rows:
        verdict = "sample_missing"
    elif covered == 0 or not ok_timing:
        verdict = "full_only"
    elif not audit_result.get("detects_hidden_regression"):
        verdict = "fix_audit"
    else:
        verdict = "keep"
    return {"samples": rows, "covered": covered, "n": len(rows),
            "timing": timing_result, "audit": audit_result,
            "verdict": verdict, "rule": VERDICT_RULES["2.4"]}


def _subset_timing(ct_mod_arg):
    """合成仓：24 个无关测试 + 1 个相关测试，全量 vs 子集各跑一次。"""
    with tempfile.TemporaryDirectory(prefix="aci-subset-timing-") as td:
        root = Path(td)
        (root / "mod").mkdir()
        (root / "mod" / "core.py").write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8", newline="\n")
        tests = root / "tests"
        tests.mkdir()
        (tests / "test_core.py").write_text(
            "from mod.core import add\n\n\ndef test_add():\n"
            "    assert add(1, 2) == 3\n", encoding="utf-8", newline="\n")
        for i in range(24):
            (tests / ("test_bulk_%02d.py" % i)).write_text(
                "def test_bulk_%02d():\n"
                "    assert sum(x * x for x in range(400000)) > 0\n" % i,
                encoding="utf-8", newline="\n")
        t0 = time.monotonic()
        full_status, _ = ct_mod_arg._run_tests(root)
        full_sec = round(time.monotonic() - t0, 2)
        t0 = time.monotonic()
        subset_status, subset_detail = ct_mod_arg._run_tests(
            root, ["mod/core.py"])
        subset_sec = round(time.monotonic() - t0, 2)
        _progress("2.4 timing full=%.2fs subset=%.2fs"
                  % (full_sec, subset_sec))
        return {"ran": True, "full_sec": full_sec, "subset_sec": subset_sec,
                "full_status": full_status, "subset_status": subset_status,
                "subset_detail": " ".join(subset_detail)[:200],
                "speedup": round(full_sec / subset_sec, 2)
                if subset_sec else None}


def _audit_probe(ct_mod_arg):
    """合成「子集通过但全量失败」的隐藏回归，验证抽检真的会转 fail。"""
    with tempfile.TemporaryDirectory(prefix="aci-audit-") as td:
        root = Path(td)
        (root / "mod").mkdir()
        (root / "mod" / "core.py").write_text(
            "def value():\n    return 1\n", encoding="utf-8", newline="\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_core.py").write_text(
            "from mod.core import value\n\n\ndef test_value():\n"
            "    assert value() == 1\n", encoding="utf-8", newline="\n")
        (root / "tests" / "test_contract.py").write_text(
            "from mod.core import value\n\n\ndef test_contract():\n"
            "    assert value() == 2\n", encoding="utf-8", newline="\n")
        audit_seed = ""
        for i in range(30):
            cand = "0|mod/core.py" if i == 0 else "0|mod/core.py|%d" % i
            import hashlib
            if hashlib.sha1(cand.encode("utf-8")).digest()[0] % 3 == 0:
                audit_seed = cand
                break
        status, detail = ct_mod_arg._run_tests(
            root, ["mod/core.py"], audit_seed=audit_seed)
        plain_status, plain_detail = ct_mod_arg._run_tests(
            root, ["mod/core.py"])
        return {"ran": True, "audit_seed": audit_seed,
                "audited_status": status,
                "audited_note": detail[0] if detail else "",
                "unaudited_status": plain_status,
                "unaudited_note": plain_detail[0] if plain_detail else "",
                "detects_hidden_regression": status == "fail" and
                "抽检未过" in (detail[0] if detail else ""),
                "labels_unaudited": "未抽检" in (plain_detail[0]
                                                if plain_detail else "")}


# ------------------------------------------------------------------ 2.5 语法


VALID_SNIPPETS = {
    "plain_func.py": "def f(a, b=1):\n    return a + b\n",
    "class_body.py": "class A:\n    def m(self):\n        return {'x': [1, 2]}\n",
    "async_def.py": "import asyncio\n\nasync def main():\n    await asyncio.sleep(0)\n",
    "fstring.py": "name = 'x'\nmsg = f'hello {name!r} {1 + 2}'\n",
    "decorator.py": "@property\ndef p(self):\n    return 1\n",
    "match_stmt.py": "def f(x):\n    match x:\n        case 1:\n            return 'one'\n    return 'other'\n",
    "type_hint.py": "from typing import Optional\n\ndef f(x: Optional[int] = None) -> int:\n    return x or 0\n",
    "lambda_comp.py": "items = [i for i in range(10) if i % 2]\npairs = sorted(items, key=lambda v: -v)\n",
}

BROKEN_SNIPPETS = {
    "missing_paren.py": "def f(a, b):\n    return a + (b\n",
    "unclosed_string.py": "x = 'abc\ny = 1\n",
    "bad_indent.py": "def f():\n    return 1\n      return 2\n",
    "missing_colon.py": "def f()\n    return 1\n",
    "unclosed_bracket.py": "x = [1, 2, 3\n",
    "stray_else.py": "x = 1\nelse:\n    y = 2\n",
    "truncated_def.py": "class A:\n    def m(self):\n        return 1\n   def n(self):\n        return 2\n",
    "unclosed_triple.py": 'x = """abc\n',
    "broken_dict.py": "d = {'a': 1, 'b': 2\n",
    "garbage_token.py": "def f():\n    return 1 $\n",
}


def bench_syntax(rm_mod):
    with tempfile.TemporaryDirectory(prefix="aci-syntax-bench-") as td:
        root = Path(td)
        for name, body in VALID_SNIPPETS.items():
            (root / name).write_text(body, encoding="utf-8", newline="\n")
        for name, body in BROKEN_SNIPPETS.items():
            (root / name).write_text(body, encoding="utf-8", newline="\n")
        (root / "notes.txt").write_text("def f(:\n", encoding="utf-8")
        issues = rm_mod.syntax_issues(root, list(VALID_SNIPPETS) +
                                      list(BROKEN_SNIPPETS) + ["notes.txt"])
        flagged = {i["detail"].split(":")[0] for i in issues}
        caught = sorted(set(BROKEN_SNIPPETS) & flagged)
        false_pos = sorted(set(VALID_SNIPPETS) & flagged)
        verdict = "keep" if len(caught) == len(BROKEN_SNIPPETS) and \
            not false_pos else "fix"
        return {"valid_n": len(VALID_SNIPPETS),
                "broken_n": len(BROKEN_SNIPPETS),
                "caught": caught, "caught_n": len(caught),
                "false_positive": false_pos,
                "false_positive_n": len(false_pos),
                "non_py_flagged": "notes.txt" in flagged,
                "verdict": verdict, "rule": VERDICT_RULES["2.5"]}


# ---------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description="阶段二 ACI 检索基准")
    parser.add_argument("--out", help="JSON 结果写入文件（同时打印摘要）")
    parser.add_argument("--per-repo", dest="per_repo", type=int, default=3,
                        help="构造样本每仓条数（默认 3）")
    parser.add_argument("--quick", action="store_true",
                        help="跳过构造样本与合成控时（只跑真实语料）")
    parser.add_argument("--skip-search", action="store_true")
    argv = parser.parse_args()

    rm_mod = _load("aci_repo_map", AGENT / "repo_map.py")
    ct_mod = _load("aci_code_task", AGENT / "code-task.py")
    cache = RepoCache(rm_mod)

    real_samples, err = _load_real_samples()
    if err:
        _progress(err)
    constructed_repos = [SWE_REPOS / n for n in CONSTRUCTED_REPOS
                         if (SWE_REPOS / n).is_dir()]
    if not real_samples and not constructed_repos:
        _emit({"ok": False, "error": "无可用语料：datasets/swe-repos 与 "
                                     "datasets/swe-out 均缺失"})
        return 2

    result = {"ok": True, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "rules": VERDICT_RULES,
              "real_samples": len(real_samples),
              "constructed_repos": [r.name for r in constructed_repos]}
    constructed = []
    if not argv.quick:
        for repo in constructed_repos:
            constructed += _constructed_samples(repo, rm_mod, argv.per_repo)
    for sample in constructed:
        sample["root"] = sample["repo"]
        sample["root_mode"] = "clone_head"
    made, roots_tmp = _prepare_roots(real_samples)
    try:
        result["map_rank"] = bench_map_rank(
            rm_mod, cache, constructed + real_samples, len(constructed))
        if not argv.skip_search:
            result["search_rank"] = bench_search_rank(ct_mod, real_samples)
        result["test_subset"] = bench_test_subset(ct_mod, real_samples,
                                                  timing=not argv.quick)
    finally:
        _cleanup_roots(made, roots_tmp)
    result["syntax"] = bench_syntax(rm_mod)

    summary = {
        "map_real": result["map_rank"]["real"],
        "map_verdict": result["map_rank"]["verdict"],
        "map_best_policy": result["map_rank"]["best_policy"],
        "search": {k: result["search_rank"][k]
                   for k in ("n", "old_hit", "new_hit", "verdict")}
        if "search_rank" in result else "skipped",
        "subset": {k: result["test_subset"][k]
                   for k in ("n", "covered", "verdict", "timing", "audit")},
        "syntax": {k: result["syntax"][k]
                   for k in ("broken_n", "caught_n", "false_positive_n",
                             "verdict")},
    }
    result["summary"] = summary
    if argv.out:
        out_path = Path(argv.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
        _progress("结果已写入 %s" % out_path)
    _emit({"ok": True, "summary": summary, "out": argv.out or ""})
    return 0


if __name__ == "__main__":
    sys.exit(main())
