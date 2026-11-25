#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""邻近测试三路映射在**真实仓库**上的归因实测（round-30 检查单第 4 项）。

要回答的问题不是「C 路能不能跑」，而是「C 路值不值得留在材料里」。合成语料
（`scripts/sibling-test-bench.py`）只能证明口径可复算，证明不了能力——所以这里
直接拿 `datasets/swe-repos/` 下的真实仓库，按**生产口径**（默认 limit=2、
max_chars=1500，与 `agent/code-task.py` 调用点一致）逐模块调
`repo_map.find_sibling_tests()`，再给每一路记客观账。

判真口径（可复算，不靠印象，且**先写死在代码里再看数字**）：
  取样域 = 仓库里**可导入包内**的 .py 模块（向上走 `__init__.py` 链求真实包名，
  于是 matplotlib 的 `lib/` 布局与 `ci/`、`galleries/` 这类脚本都不会污染样本）。
  被返回的测试文件满足下列任一条 → 记「引用命中」：
    · 模块的点分路径（如 `matplotlib.axes`）**逐字**出现——覆盖 `import` / `from … import`
      / `mock.patch("a.b.c")` 三种写法；
    · 出现 `from <该模块所在包> import <模块名>` 这种不含完整点分路径的写法。
  引用发生在 import 行上 → 另记「严格 import 命中」，是比「出现点分路径」更强的一档证据。
  「模块名只在 fixture 路径串 / 注释 / 别人的同名 import 里出现」**不会**被判真。
没判真的返回按**噪声成因**分类（路径/文件名串、注释/文档串、同名不同模块、
其他代码引用、无引用痕迹）——「C 路命中的是测试还是 fixture 路径」就是这么拆开记的。

C 路去留的判据（运行前定死，避免看完数字再挑阈值）：
  truth_rate = C 路引用命中数 / C 路返回数
  ≥ 0.5  → keep            ：C 路留在材料里（现状次序已让位给 A/B）
  0 < rate < 0.5 → keep_labeled：留在材料但必须带「按内容命中」标注（现状已带）
  == 0   → downgrade_hint ：降级为「只在 A/B 全空时提示、不进材料」

A 泛化名与 B 路的去留判据（round-33 检查单第 5 项，同样**先写死再看数字**）：
  A-generic（「按名字泛化命中」兜底，只在 A/B/C 全空后才出场）：
    returns < 10              → sample_too_small_keep：出场太少，判不动
    truth_rate == 0           → drop_from_material：带标注的纯噪声仍占 limit 槽位、
                                仍会被模型读进上下文，不如无材料（round-30「覆盖率
                                191→174 是诚实代价」的同一条原则）
    0 < truth_rate < 0.3      → keep_labeled（现状）
    truth_rate ≥ 0.3          → keep
  B（路径段映射，位置在 C 之前，命中即停）：
    returns < 10              → sample_too_small_keep：出场太少，判不动；且 B 的
                                主要风险是「噪声短路 C」，需要足够样本才能量刑
    truth_rate == 0           → keep_labeled：留在材料但片段必须带来源标注
    truth_rate ≥ 0.5          → keep

用法：
    .venv/Scripts/python.exe scripts/sibling-test-realbench.py
    .venv/Scripts/python.exe scripts/sibling-test-realbench.py --repo datasets/swe-repos/sympy --sample 20 --verbose

退出码：0 = 实测跑通（数字难看也是 0）；2 = 仓库缺失 / 装载失败。
"""
import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO_MAP = HERE / "agent" / "repo_map.py"
BENCH = HERE / "scripts" / "sibling-test-bench.py"

# 默认三仓：django（tests/<app> 布局）、sympy（包内 tests/ 布局）、
# matplotlib（src + 包混合布局）——检查单要求「真实语料」，不是再攒一支合成的。
DEFAULT_REPOS = ("datasets/swe-repos/swe__django",
                 "datasets/swe-repos/sympy",
                 "datasets/swe-repos/matplotlib")

SKIP_DIRS = {"tests", "test", "docs", "doc", "build", "node_modules",
             ".git", ".venv", "benchmarks", "examples", "scripts", "bin"}
FILE_EXT_RE = re.compile(r"\.(json|csv|txt|png|py|xml|yml|yaml|fits|hdf5|npy|rst|md|sql|html)$")
QUOTED_PATH_RE = re.compile(r"""['"][^'"]*/[^'"]*['"]""")
IMPORT_LINE_RE = re.compile(r"^\s*(?:from|import)\b")

VERDICT_RULE = ("truth_rate = C 路引用命中 / C 路返回；≥0.5 keep / "
                "0<r<0.5 keep_labeled / ==0 downgrade_hint")
A_GENERIC_RULE = ("returns<10 sample_too_small_keep / truth_rate==0 "
                  "drop_from_material（带标注的纯噪声仍占 limit 槽位，不如无材料）/ "
                  "0<r<0.3 keep_labeled / r≥0.3 keep")
B_RULE = ("returns<10 sample_too_small_keep（出场太少判不动）/ "
          "truth_rate==0 keep_labeled / r≥0.5 keep")
# 小样本下限：少于这个返回数，判据不量刑（避免 n=2 的偶然定罪）
MIN_SAMPLE_FOR_VERDICT = 10


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法装载 %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module_ref(root, rel):
    """模块相对路径 → (点分路径, 包点分路径, 模块名)；不在可导入包内则 None。

    两条被实测逼出来的口径修正——**都出在量具上，不是出在映射上**：
    ① 包根 ≠ 仓库根：matplotlib 的包在 `lib/` 下，按仓库根拼点分会得到
       `lib.matplotlib.axes`，于是真的 `from matplotlib.axes import Axes` 也被判成
       噪声，整仓命中率假成 0；
    ② 取样域必须是「可导入包内的模块」：`ci/`、`galleries/` 这类脚本与图例按等距
       取样会占满样本，它们本来就没有邻近测试——那测出来的是**样本形状**，不是映射能力。
    做法：从模块所在目录**向上走**，直到该目录没有 `__init__.py`；走通的目录串就是
    真实包名，点分路径由它拼出（这一步同时修好了 ① 与 ②）。
    """
    path = root / rel
    stem = path.stem
    if stem.startswith(("test_", "_test", "__")) or stem in ("conftest", "setup"):
        return None
    pkg = []
    cur = path.parent
    while (cur / "__init__.py").is_file():
        pkg.append(cur.name)
        cur = cur.parent
    if not pkg:
        return None
    head = ".".join(reversed(pkg))
    return head + "." + stem, head, stem


def _package_modules(root):
    """取样域：仓库里**可导入包内**的 .py 模块（相对路径，排序确定）。"""
    out = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if _module_ref(root, rel.as_posix()):
            out.append(rel.as_posix())
    return out


_IMPORT_REF_CACHE = {}


def _import_pattern(head, stem):
    """`from <包> import <模块>` 写法：不含完整点分路径，但同样是真实引用。"""
    key = (head, stem)
    pat = _IMPORT_REF_CACHE.get(key)
    if pat is None:
        pat = re.compile(r"^\s*from\s+%s\s+import\s[^\n]*\b%s\b"
                         % (re.escape(head), re.escape(stem)), re.MULTILINE)
        _IMPORT_REF_CACHE[key] = pat
    return pat


def _reference_check(text, ref):
    """判真：点分路径出现，或 `from 包 import 模块`。返回 (truth, strict_import)。

    strict 档只认 **import 行**上的引用；`mock.patch("a.b.c")` 这类串内引用算 truth
    不算 strict——它确实指向这个模块，但不是「这个测试在测它」的最强证据。
    """
    dotted, head, stem = ref
    pat = _import_pattern(head, stem)
    truth = (dotted in text) or bool(pat.search(text))
    strict = False
    if truth:
        for line in text.splitlines():
            if IMPORT_LINE_RE.match(line) and (dotted in line or pat.match(line)):
                strict = True
                break
    return truth, strict


def _sample(items, n):
    """等距取样：不依赖随机种子，同一仓库永远同一批样本。"""
    if n <= 0 or n >= len(items):
        return list(items)
    step = len(items) / float(n)
    return [items[int(i * step)] for i in range(n)]


def _parse_returns(text):
    """把 find_sibling_tests 的返回拆成 [(相对路径, 标注)]，口径与合成 bench 同源。"""
    bench = _load(BENCH, "sibling_bench_for_real")
    paths, marks = [], []
    for match in bench.HEADER_RE.finditer(text):
        body = match.group(1)
        rel = body.split("，")[0].strip()
        mark = body.split("，", 1)[1].strip() if "，" in body else ""
        paths.append(rel)
        marks.append(mark)
    return paths, marks


def _classify_return(root, rel_returned, ref, text_cache):
    """一个返回的判真 + （若不真）噪声成因分类。

    返回 (truth, strict_import, reasons)：reasons 只在非真时给出，可多个。
    """
    dotted, head, stem = ref
    if rel_returned in text_cache:
        text = text_cache[rel_returned]
    else:
        try:
            text = (root / rel_returned).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = None
        text_cache[rel_returned] = text
    if text is None:
        return False, False, ["读不到文件"]
    truth, strict = _reference_check(text, ref)
    if truth:
        return True, strict, []
    reasons = set()
    stem_re = re.compile(r"\b%s\b" % re.escape(stem))
    for line in text.splitlines():
        if not stem_re.search(line):
            continue
        stripped = line.strip()
        quoted = QUOTED_PATH_RE.search(line)
        if quoted and (FILE_EXT_RE.search(quoted.group(0)) or "/" in quoted.group(0)):
            reasons.add("路径/文件名串")
        elif stripped.startswith("#"):
            reasons.add("注释/文档串")
        elif IMPORT_LINE_RE.match(line):
            reasons.add("同名不同模块")
        else:
            reasons.add("其他代码引用")
    return False, False, sorted(reasons) or ["无引用痕迹"]


def _measure(root, repo_map, sample_n, verbose):
    """按生产口径逐模块调用并记账。"""
    bench = _load(BENCH, "sibling_bench_lane")
    candidates = _package_modules(root)
    modules = _sample(candidates, sample_n)
    per_lane = {}
    records = []
    text_cache = {}
    with_context = 0
    for rel in modules:
        text = repo_map.find_sibling_tests(root, rel)
        paths, marks = _parse_returns(text)
        if paths:
            with_context += 1
        ref = _module_ref(root, rel)
        row = {"module": rel, "dotted": ref[0], "returns": []}
        for p, m in zip(paths, marks):
            lane = bench._lane_for(p, rel, m)
            truth, strict, reasons = _classify_return(root, p, ref, text_cache)
            entry = {"path": p, "lane": lane, "mark": m,
                     "truth": truth, "strict_import": strict,
                     "reasons": reasons}
            row["returns"].append(entry)
            acc = per_lane.setdefault(lane, {"returns": 0, "truth": 0,
                                             "strict_import": 0, "noise": 0,
                                             "noise_reasons": {}})
            acc["returns"] += 1
            if truth:
                acc["truth"] += 1
                if strict:
                    acc["strict_import"] += 1
            else:
                acc["noise"] += 1
                for r in reasons:
                    acc["noise_reasons"][r] = acc["noise_reasons"].get(r, 0) + 1
        if verbose:
            records.append(row)
    for acc in per_lane.values():
        acc["truth_rate"] = round(acc["truth"] / acc["returns"], 3) if acc["returns"] else None
    return {"modules_candidates": len(candidates),
            "modules_sampled": len(modules),
            "modules_with_context": with_context,
            "coverage_rate": round(with_context / max(1, len(modules)), 3),
            "by_lane": per_lane,
            "records": records}


def _lane_verdict(acc, small_sample_verdict, zero_verdict, mid_verdict, high_verdict,
                   mid_lo=0.0, high_at=0.5):
    """单路去留的通用判定：先看样本量下限，再按 truth_rate 分档。"""
    if not acc or not acc.get("returns"):
        return {"lane_returns": 0, "verdict": "not_observed"}
    rate = acc["truth_rate"]
    verdict = None
    if acc["returns"] < MIN_SAMPLE_FOR_VERDICT:
        verdict = small_sample_verdict
    elif rate == 0:
        verdict = zero_verdict
    elif rate is not None and mid_lo < rate < high_at:
        verdict = mid_verdict
    elif rate is not None and rate >= high_at:
        verdict = high_verdict
    return {"lane_returns": acc["returns"], "lane_truth_rate": rate,
            "verdict": verdict}


def _verdict(by_lane):
    """各路去留的判定（阈值见 VERDICT_RULE / A_GENERIC_RULE / B_RULE，运行前定死）。

    输出保持旧键位（c_returns/c_truth_rate/verdict）不破坏既有产物消费者，
    新增 by_lane_verdict 给出 A-generic 与 B 两路的同口径判定。
    """
    acc = by_lane.get("C")
    if not acc or not acc.get("returns"):
        out = {"c_returns": 0, "verdict": "not_observed",
               "meaning": "样本里 C 路一次都没出场——它本来只在 A/B 全空时才跑"}
    else:
        rate = acc["truth_rate"]
        if rate is None:
            verdict = "not_observed"
        elif rate >= 0.5:
            verdict = "keep"
        elif rate > 0:
            verdict = "keep_labeled"
        else:
            verdict = "downgrade_hint"
        out = {"c_returns": acc["returns"], "c_truth_rate": rate,
               "verdict": verdict}
    out["by_lane_verdict"] = {
        "A-generic": _lane_verdict(by_lane.get("A-generic"),
                                   "sample_too_small_keep", "drop_from_material",
                                   "keep_labeled", "keep", mid_lo=0.0, high_at=0.3),
        "B": _lane_verdict(by_lane.get("B"),
                           "sample_too_small_keep", "keep_labeled",
                           "keep_labeled", "keep", mid_lo=0.0, high_at=0.5),
    }
    return out


def main():
    parser = argparse.ArgumentParser(description="邻近测试三路映射的真实仓库归因实测")
    parser.add_argument("--repo", action="append", default=[],
                        help="仓库路径（可重复；缺省用 DEFAULT_REPOS）")
    parser.add_argument("--sample", type=int, default=40,
                        help="每仓取样模块数（等距取样，0=全量）")
    parser.add_argument("--verbose", action="store_true", help="附逐模块明细")
    argv = parser.parse_args()

    if not REPO_MAP.is_file() or not BENCH.is_file():
        _emit({"ok": False, "error": "找不到 %s 或 %s" % (REPO_MAP, BENCH)})
        return 2
    try:
        repo_map = _load(REPO_MAP, "repo_map_under_real_bench")
    except Exception as exc:  # noqa: BLE001 - 装载失败要如实报出口径
        _emit({"ok": False, "error": "repo_map 装载失败: %s（环境依赖问题，不是代码回归）" % exc})
        return 2

    raw = argv.repo or list(DEFAULT_REPOS)
    repos = []
    for item in raw:
        path = Path(item)
        if not path.is_absolute():
            path = HERE / path
        if not path.is_dir():
            _emit({"ok": False, "error": "仓库不存在: %s" % path})
            return 2
        repos.append(path)

    payload = {"ok": True, "verdict_rule": VERDICT_RULE,
               "a_generic_rule": A_GENERIC_RULE, "b_rule": B_RULE,
               "min_sample_for_verdict": MIN_SAMPLE_FOR_VERDICT,
               "prod_caliber": {"limit": 2, "max_chars": 1500},
               "repos": []}
    agg = {}
    t_all = time.time()
    for repo in repos:
        started = time.time()
        result = _measure(repo, repo_map, argv.sample, argv.verbose)
        result["repo"] = str(repo.relative_to(HERE)) if repo.is_relative_to(HERE) else str(repo)
        result["seconds"] = round(time.time() - started, 1)
        result["verdict"] = _verdict(result["by_lane"])
        payload["repos"].append(result)
        for lane, acc in result["by_lane"].items():
            a = agg.setdefault(lane, {"returns": 0, "truth": 0, "strict_import": 0,
                                      "noise": 0, "noise_reasons": {}})
            for key in ("returns", "truth", "strict_import", "noise"):
                a[key] += acc[key]
            for reason, num in acc["noise_reasons"].items():
                a["noise_reasons"][reason] = a["noise_reasons"].get(reason, 0) + num
    for a in agg.values():
        a["truth_rate"] = round(a["truth"] / a["returns"], 3) if a["returns"] else None
    payload["aggregate"] = {"by_lane": agg,
                            "verdict": _verdict(agg),
                            "modules_sampled": sum(r["modules_sampled"] for r in payload["repos"]),
                            "modules_with_context": sum(r["modules_with_context"] for r in payload["repos"]),
                            "seconds": round(time.time() - t_all, 1)}
    _emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
