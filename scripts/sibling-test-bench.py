#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""邻近测试三路映射的命中率/误命中率实测（round-28 检查单第 6 项的量化）。

`agent/repo_map.py` 的 `find_sibling_tests()` 三路取法：
  A 名字命中（模块同级 tests/ 或仓库根 tests/，文件名含模块名）
  B 路径段映射（模块目录段 ↔ tests/<同名目录>/，django 的 app 布局）
  C 引用兜底（tests/ 里以**引用形状**点到该模块的测试文件：完整点分路径或
    `from 包 import 模块`；round-30 前是「提到模块名」的裸词，噪声挤掉真值，
    片段仍标「按内容命中」）
前一路命中即停。落到这里的问题是：**「找到了」不等于「找对了」**，
而 A 的泛化名（`base`、`utils` 这类词根）会把无关测试当命中抢先返回，
让真正对的 B 根本没机会跑。本脚本用一支**受控合成仓库**把这件事变成数字。

口径（全部是判定，不是印象）：
- 每个用例带 `expected`（该模块真值测试文件）与 `decoys`（已知无关但会被捡到的文件）；
- `lane_used` = 实际由哪一路产出（A/B/C/MIXED/NONE），按机制归位：C 有「按内容命中」硬标记，
  A 看文件名是否含模块名，B 看返回路径里是否出现模块的目录段；
- `want_lane` = **该由**哪一路负责（理想行为），两者不一致就单列进 `lane_mismatch`；
- `recall` = 命中真值数 / 真值数；`precision` = 命中真值数 / 返回数；
- C 路一律要求片段头标注「按内容命中」，没标注算作缺陷（`c_lane.all_content_hits_labeled`）。

用法：
    python scripts/sibling-test-bench.py            # 打印 JSON 数字
    python scripts/sibling-test-bench.py --verbose  # 附上逐例明细

退出码：0 = 实测跑通（数字本身可以为难看得很）；2 = 环境/装载错误。
"""
import argparse
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parents[1]
REPO_MAP = HERE / "agent" / "repo_map.py"

HEADER_RE = re.compile(r"（邻近测试 ([^）]+)）")
CONTENT_MARK = "按内容命中"
GENERIC_MARK = "按名字泛化命中"

# ---- 合成语料：目录布局刻意覆盖三种真实仓库形状 ----
# 每项 (相对路径, 内容)。空内容用 None 表示。
CORPUS = {
    # ① django 形：模块在包深处，测试在 tests/<app>/ 下，名字不直接对应
    "django/db/migrations/operations/base.py": "class CreateModel:\n    pass\n",
    "tests/migrations/test_operations.py": "from django.db.migrations.operations.base import CreateModel\n",
    # 泛化名诱饵：模块名 base 太通用，A 路会先撞上它们
    "tests/migrations/test_base.py": "def test_base():\n    pass\n",
    "tests/urlpatterns/test_base.py": "def test_base():\n    pass\n",
    "tests/migrations/test_writer.py": "def test_writer():\n    pass\n",

    # ② sympy 形：测试在模块同级 tests/ 目录里（包内布局）
    "sympy/physics/quantum/hilbert.py": "class HilbertSpace:\n    pass\n",
    "sympy/physics/quantum/tests/test_hilbert.py": "from sympy.physics.quantum.hilbert import HilbertSpace\n",

    # ③ 扁平仓库形：src/ + 根 tests/
    "src/parser.py": "def parse(s):\n    return s\n",
    "tests/test_parser.py": "from src.parser import parse\n",

    # ④ C 路真命中：既不同名也不同目录，但测试真的 import 了它
    "pkg/utils/serializer.py": "def dumps(o):\n    return ''\n",
    "pkg/utils/text.py": "def squeeze(s):\n    return s\n",
    "tests/test_api.py": "from pkg.utils.serializer import dumps\n",

    # ⑤ C 路误命中：模块名只是**出现在别人的 fixture 路径字符串里**
    "pkg/core/session.py": "class Session:\n    pass\n",
    "pkg/core/store.py": "class Store:\n    pass\n",
    "tests/test_config.py": 'FIXTURE = "tests/fixtures/session/note.json"\n',

    # ⑥ 无测试模块：应当什么都不返回
    "src/leaf/quiet_module.py": "VALUE = 1\n",

    # ⑦ 泛化名 + 内容兜底同时存在的复合例（A 抢先，B/C 没机会）
    "legacy/core/utils.py": "def help_():\n    pass\n",
    "tests/util/test_utils_math.py": "def test_math():\n    pass\n",
    "tests/test_utils_io.py": "def test_io():\n    pass\n",
}

# 用例表：module → (期望真值, 已知诱饵, 期望由哪一路给出)
# want_lane 说的是「**该由**哪一路负责」，不是「实际哪一路抢了跑」——
# 两者不一致的地方就是这条链路的缺陷，summary 里单列成 lane_mismatch。
CASES = [
    {
        "name": "django 形：operations/base.py",
        "module": "django/db/migrations/operations/base.py",
        "expected": ["tests/migrations/test_operations.py"],
        "decoys": ["tests/migrations/test_base.py", "tests/urlpatterns/test_base.py"],
        "want_lane": "B",
        "note": "模块名 base 是泛化名，A 路按文件名命中会把 test_base 当邻近测试",
    },
    {
        "name": "sympy 形：包内同级 tests/",
        "module": "sympy/physics/quantum/hilbert.py",
        "expected": ["sympy/physics/quantum/tests/test_hilbert.py"],
        "decoys": [],
        "want_lane": "A",
    },
    {
        "name": "扁平仓库：src/parser.py",
        "module": "src/parser.py",
        "expected": ["tests/test_parser.py"],
        "decoys": [],
        "want_lane": "A",
    },
    {
        "name": "C 路真命中：跨目录 import",
        "module": "pkg/utils/serializer.py",
        "expected": ["tests/test_api.py"],
        "decoys": [],
        "want_lane": "C",
    },
    {
        "name": "C 路误命中：名字只是 fixture 路径",
        "module": "pkg/core/session.py",
        "expected": [],
        "decoys": ["tests/test_config.py"],
        "want_lane": "NONE",
        "note": "round-30 前 C 按裸词命中，这一例返回 fixture 路径串当邻近测试；"
                "C 的检索谓词改成「点分路径 / from 包 import 模块」后，这一例应当空手",
    },
    {
        "name": "无测试模块",
        "module": "src/leaf/quiet_module.py",
        "expected": [],
        "decoys": [],
        "want_lane": "NONE",
    },
    {
        "name": "复合泛化名：legacy/core/utils.py",
        "module": "legacy/core/utils.py",
        "expected": [],
        "decoys": ["tests/util/test_utils_math.py", "tests/test_utils_io.py"],
        "want_lane": "NONE",
        "note": "没有任何测试真的测它；round-33 前 A 泛化名兜底会带回两个标注噪声，"
                "round-33 起三路皆空即空返（真实语料定案：泛化名 36 出场 0 判真）",
    },
]


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_repo_map():
    spec = importlib.util.spec_from_file_location("repo_map_under_test", REPO_MAP)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法装载 %s" % REPO_MAP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_corpus(root):
    for rel, text in CORPUS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def _name_hit(module, rel_returned):
    """返回文件是否**靠文件名**含模块名命中（复刻 _stem_matches 的口径）。"""
    stem = Path(module).stem
    file_stem = Path(rel_returned).stem
    return (stem in file_stem
            or file_stem.replace("test_", "").replace("_test", "") == stem)


def _lane_for(rel_returned, module, mark):
    """按机制归位到 A/B/C 三路的某一路。

    标注是硬证据：「按内容命中」= C，「按名字泛化命中」= A 泛化；
    没标注的用布局判：文件名含模块名 = A（名字命中）；否则返回路径里
    出现了模块的目录段 = B（路径段映射）；两者都不像时按 A 记账
    （宁可归到最保守的解释）。
    """
    if mark == CONTENT_MARK:
        return "C"
    if mark == GENERIC_MARK:
        return "A-generic"
    if _name_hit(module, rel_returned):
        return "A"
    segments = set(Path(module).parent.parts)
    if segments & set(PurePosixPath(rel_returned).parts[:-1]):
        return "B"
    return "A"


def _dominant(lanes):
    distinct = set(lanes)
    if not distinct:
        return "NONE"
    if len(distinct) == 1:
        return next(iter(distinct))
    return "MIXED"


def _run_case(find, repo, case):
    text = find(repo, case["module"], limit=4, max_chars=200)
    paths, marks = [], []
    for match in HEADER_RE.finditer(text):
        body = match.group(1)
        rel = body.split("，")[0].strip()
        mark = body.split("，", 1)[1].strip() if "，" in body else ""
        paths.append(rel)
        marks.append(mark)
    lanes = [_lane_for(p, case["module"], m) for p, m in zip(paths, marks)]
    lane_used = _dominant(lanes)
    expected = set(case["expected"])
    hits = [p for p in paths if p in expected]
    decoy_hits = [p for p in paths if p in set(case["decoys"])]
    unknown = [p for p in paths if p not in expected and p not in set(case["decoys"])]
    return {
        "name": case["name"],
        "module": case["module"],
        "lane_used": lane_used,
        "want_lane": case["want_lane"],
        "returned": paths,
        "marks": marks,
        "truth_hits": hits,
        "decoy_hits": decoy_hits,
        "unexpected": unknown,
        "recall": (round(len(hits) / len(expected), 3) if expected
                   else (None if paths else 1.0)),
        "precision": (round(len(hits) / len(paths), 3) if paths
                      else (None if not expected else 0.0)),
        "noise_all_labeled": (all(m for p, m in zip(paths, marks) if p not in expected)
                              if paths else None),
        "note": case.get("note", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="邻近测试三路映射命中率实测")
    parser.add_argument("--verbose", action="store_true", help="附逐例明细")
    argv = parser.parse_args()
    if not REPO_MAP.is_file():
        _emit({"ok": False, "error": "找不到 %s" % REPO_MAP})
        return 2
    try:
        repo_map = _load_repo_map()
    except Exception as exc:  # noqa: BLE001 - 装载失败要如实报出口径
        _emit({"ok": False, "error": "repo_map 装载失败: %s" % exc})
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="sibling-bench-"))
    try:
        repo = tmp / "corpus"
        repo.mkdir(parents=True)
        _build_corpus(repo)
        results = [_run_case(repo_map.find_sibling_tests, repo, case)
                   for case in CASES]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    c_cases = [r for r in results if r["want_lane"] == "C"]

    def _rate(lane):
        picked = [r for r in results if r["lane_used"] == lane]
        return {"cases": len(picked),
                "hit": sum(1 for r in picked if r["truth_hits"]),
                "miss": sum(1 for r in picked if not r["truth_hits"]),
                "returned": sum(len(r["returned"]) for r in picked),
                "truth_returns": sum(len(r["truth_hits"]) for r in picked)}

    lane_names = {"A": "名字命中", "A-generic": "名字命中（泛化名，已标注）",
                  "B": "路径段映射", "C": "内容兜底",
                  "MIXED": "混着返回", "NONE": "没返回"}
    payload = {
        "ok": True,
        "corpus": {"files": len(CORPUS), "cases": len(results)},
        "by_lane": {lane: _rate(lane) for lane in
                    ("A", "A-generic", "B", "C", "MIXED", "NONE")},
        "lane_meaning": lane_names,
        "recall_mean": round(sum(r["recall"] for r in results
                                 if r["recall"] is not None)
                             / max(1, sum(1 for r in results
                                           if r["recall"] is not None)), 3),
        "precision_mean": round(sum(r["precision"] for r in results
                                    if r["precision"] is not None)
                                / max(1, sum(1 for r in results
                                              if r["precision"] is not None)), 3),
        "decoy_hits_total": sum(len(r["decoy_hits"]) for r in results),
        "unexpected_hits_total": sum(len(r["unexpected"]) for r in results),
        # C 路（内容兜底）单独口径：跨目录 import 的真命中 vs fixture 路径的假命中
        "c_lane": {
            "cases": len(c_cases),
            "precision": (round(sum(len(r["truth_hits"]) for r in c_cases)
                                / max(1, sum(len(r["returned"]) for r in c_cases)), 3)
                          if c_cases else None),
            "all_content_hits_labeled": all(
                bool(r["noise_all_labeled"]) for r in c_cases
                if r["noise_all_labeled"] is not None),
        },
        # 噪声纪律：凡不是真值的返回，片段头必须自带来源标注（内容/泛化名）
        "noise_labeled_total": sum(
            1 for r in results for p, m in zip(r["returned"], r["marks"])
            if p not in r["truth_hits"] and m),
        "noise_unlabeled_total": sum(
            1 for r in results for p, m in zip(r["returned"], r["marks"])
            if p not in r["truth_hits"] and not m),
        # 该由哪一路负责 ≠ 实际哪一路抢了跑：这两条就是本轮要修的点
        "lane_mismatch": [{"name": r["name"], "used": r["lane_used"],
                           "want": r["want_lane"], "returned": r["returned"],
                           "truth_missed": [p for p in
                                            next((c["expected"] for c in CASES
                                                  if c["name"] == r["name"]), [])
                                            if p not in r["returned"]]}
                          for r in results if r["lane_used"] != r["want_lane"]],
    }
    if argv.verbose:
        payload["cases"] = results
    _emit(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
