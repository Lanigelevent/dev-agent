# -*- coding: utf-8 -*-
"""tests/test_smoke_manifest.py — smoke 清单契约（D-049 A，round-92）。

清单是预注册资产：①schema/数量界；②所有 ID 可加载；③必须是全量
discover 的子集（防陈旧 ID——清单改动漏同步时本契约当场拦下）。
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "smoke-manifest.json"


def _discover_names():
    loader = unittest.defaultTestLoader
    suite = loader.discover("tests", pattern="test_*.py",
                            top_level_dir="tests")
    names = set()

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
            else:
                names.add(t.id())
    walk(suite)
    return names


class SmokeManifestTests(unittest.TestCase):
    def test_manifest_shape_and_bounds(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "smoke-manifest/1")
        self.assertIsInstance(data["tests"], list)
        self.assertGreaterEqual(data["count"], 150)
        self.assertLessEqual(data["count"], 300)
        self.assertEqual(data["count"], len(data["tests"]))

    def test_manifest_ids_loadable_and_subset(self):
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        full = {n.split(".", 1)[1] if n.startswith("tests.")
                else n for n in _discover_names()}
        bad = [n for n in data["tests"] if n not in full]
        self.assertEqual(bad, [],
                         "清单含 discover 不存在的陈旧 ID: %r" % bad[:5])
