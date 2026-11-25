# -*- coding: utf-8 -*-
"""tests/test_bump_version.py — bump-version.py 契约（round-86 P1-5，离线）。

覆盖：干跑 vs --apply、六处版本真值逐处重写、漏命中/多命中拒绝且**不写
任何文件**、版本形态校验、--sync-counts 的计数实算与历史值行跳过、
幂等性、退出码与单 JSON stdout 契约。
"""
import contextlib
import io
import json
import os
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "bump-version.py"

OLD_VERSION_FILES = {
    ".zcode-plugin/plugin.json": '{\n  "name": "dev-agent",\n  "version": "1.86.0",\n  "other": true\n}\n',
    "pyproject.toml": '[project]\nname = "dev-agent"\nversion = "1.86.0"\ndescription = "x"\n',
    "mcp/review_mcp.py": 'SERVER_INFO = {"name": "dev-agent", "version": "1.86.0"}\n',
    "README.md": "**版本 1.86.0**（真值源 plugin.json）\n\nskills/ 13 个技能 × 76 个脚本\n",
    "docs/DEVELOPMENT.md": "1. 版本唯一事实源是 `.zcode-plugin/plugin.json` 的 `version`（当前 1.86.0）；\n\nskills/ 13 个技能 × 76 个脚本，每技能 SKILL.md + scripts/\n",
    "docs/PROGRESS.md": "| 版本 | 1.86.0 | `.zcode-plugin/plugin.json` | plugin / pyproject |\n",
}


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("bump_version_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_root(tmp, overrides=None, drop=()):
    """构造六处版本文件齐备的最小仓库根。"""
    files = dict(OLD_VERSION_FILES)
    if overrides:
        files.update(overrides)
    for rel, content in files.items():
        if rel in drop:
            continue
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    # 计数真值夹具：1 个技能 / 1 个脚本 / 1 个契约用例
    sd = tmp / "skills" / "s1" / "scripts"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "x.py").write_text("", encoding="utf-8")
    td = tmp / "tests"
    td.mkdir(exist_ok=True)
    (td / "test_one.py").write_text(
        "import unittest\n\nclass T(unittest.TestCase):\n"
        "    def test_one(self):\n        pass\n",
        encoding="utf-8")
    # AGENTS.md 占位（COUNT_TARGETS 会扫它）
    (tmp / "AGENTS.md").write_text("AGENTS\n", encoding="utf-8")
    return tmp


def _invoke(mod, argv, root):
    import sys
    old = sys.argv
    out = io.StringIO()
    try:
        sys.argv = ["bump-version.py"] + [a for a in argv] + ["--root", str(root)]
        with contextlib.redirect_stdout(out):
            rc = mod.main()
    finally:
        sys.argv = old
    return rc, out.getvalue()


class TestBumpVersion(unittest.TestCase):
    def setUp(self):
        self.ct = _load_script()
        self.tmp = Path(tmpspace.create(prefix="bumpver-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def test_dry_run_writes_nothing(self):
        root = _make_root(self.tmp / "r1")
        before = {rel: (root / rel).read_text(encoding="utf-8")
                  for rel in OLD_VERSION_FILES}
        rc, out = _invoke(self.ct, ["--set", "1.87.0"], root)
        self.assertEqual(rc, 0, out)
        report = json.loads(out)
        self.assertTrue(report["ok"])
        self.assertFalse(report["applied"])
        for rel in OLD_VERSION_FILES:
            self.assertEqual((root / rel).read_text(encoding="utf-8"),
                             before[rel], "干跑不许落盘: %s" % rel)

    def test_apply_rewrites_all_six_sites(self):
        root = _make_root(self.tmp / "r2")
        rc, out = _invoke(self.ct, ["--set", "1.87.0", "--apply"], root)
        self.assertEqual(rc, 0, out)
        for rel in OLD_VERSION_FILES:
            text = (root / rel).read_text(encoding="utf-8")
            self.assertNotIn("1.86.0", text, rel)
            self.assertIn("1.87.0", text, rel)

    def test_missing_pattern_aborts_without_writes(self):
        root = _make_root(self.tmp / "r3",
                          overrides={"README.md": "no version here\n"})
        before = {rel: (root / rel).read_text(encoding="utf-8")
                  for rel in OLD_VERSION_FILES}
        rc, out = _invoke(self.ct, ["--set", "1.87.0", "--apply"], root)
        self.assertEqual(rc, 1, out)
        report = json.loads(out)
        self.assertFalse(report["ok"])
        for rel in OLD_VERSION_FILES:
            self.assertEqual((root / rel).read_text(encoding="utf-8"),
                             before[rel],
                             "校验失败时不许写任何文件: %s" % rel)

    def test_ambiguous_pattern_aborts(self):
        root = _make_root(self.tmp / "r4",
                          overrides={"pyproject.toml":
                                     'version = "1.86.0"\nversion = "1.86.0"\n'})
        rc, out = _invoke(self.ct, ["--set", "1.87.0", "--apply"], root)
        self.assertEqual(rc, 1)
        self.assertIn("命中", json.loads(out)["errors"][0]["error"])

    def test_bad_version_shape_rejected(self):
        root = _make_root(self.tmp / "r5")
        rc, out = _invoke(self.ct, ["--set", "1.87"], root)
        self.assertEqual(rc, 2)

    def test_sync_counts_rewrites_and_skips_historical(self):
        root = _make_root(self.tmp / "r6",
                          overrides={
                              "README.md": (
                                  "**版本 1.86.0**\n"
                                  "skills/ 3 个技能 × 9 个脚本\n"
                                  "历史行：9 个脚本（曾）\n"
                                  "**契约测试**：unittest discover 后 500 项\n"),
                          })
        rc, out = _invoke(self.ct, ["--set", "1.87.0", "--apply",
                                    "--sync-counts"], root)
        self.assertEqual(rc, 0, out)
        text = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("1 个技能 × 1 个脚本", text)
        # 历史值行（带「曾」）不动
        self.assertIn("9 个脚本（曾）", text)
        # 计数真值：fixture 1 技能 / 1 脚本 / discover 1 用例
        self.assertIn("1 项", text)

    def test_apply_is_idempotent(self):
        root = _make_root(self.tmp / "r7")
        rc1, _ = _invoke(self.ct, ["--set", "1.87.0", "--apply"], root)
        self.assertEqual(rc1, 0)
        rc2, out2 = _invoke(self.ct, ["--set", "1.87.0", "--apply"], root)
        self.assertEqual(rc2, 0)
        self.assertTrue(all(not t["changed"]
                            for t in json.loads(out2)["targets"]),
                        "幂等：第二次 --apply 不应再有变更")

    def test_stdout_is_single_json_document(self):
        root = _make_root(self.tmp / "r8")
        rc, out = _invoke(self.ct, ["--set", "1.87.0"], root)
        self.assertEqual(rc, 0)
        parsed = json.loads(out)  # 必须是单个 JSON 文档
        self.assertIn("targets", parsed)


if __name__ == "__main__":
    unittest.main()
