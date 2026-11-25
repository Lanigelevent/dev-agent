# -*- coding: utf-8 -*-
"""tests/test_scripts_provider_host.py — provider host 文件协议流契约（round-145）。

覆盖：HostLLMPending 抛出与 prompt/meta 落盘、幂等 id 稳定性、响应文件缓存
命中、POSIX 风格 base_dir（跨平台断言，Linux CI 可跑）、prompt 内容完整性。
平台口径：provider.py 无任何平台分支（pathlib/urllib 纯可移植实现），
host 桌面协议在 Windows/Linux 均以文件进出为界（round-145 验证落档）。
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "llm" / "provider.py"


def _load():
    sys.path.insert(0, str(ROOT))
    import llm.provider as prov
    return prov


class ProviderHostFlowTests(unittest.TestCase):
    def setUp(self):
        self.prov = _load()
        self.tmp = Path(tmpspace.create(prefix="prov-host-"))
        self.addCleanup(tmpspace.release, self.tmp)

    def test_pending_writes_prompt_and_meta(self):
        base = self.tmp / "tasks"
        with self.assertRaises(self.prov.HostLLMPending) as cm:
            self.prov._host_complete("sys-提示", "user-材料", base)
        p = Path(cm.exception.prompt_path)
        r = Path(cm.exception.response_path)
        self.assertTrue(p.is_file())
        self.assertIn("sys-提示", p.read_text(encoding="utf-8"))
        self.assertIn("user-材料", p.read_text(encoding="utf-8"))
        meta = json.loads(Path(str(p).replace(".prompt.md", ".meta.json"))
                          .read_text(encoding="utf-8"))
        self.assertEqual(meta["status"], "waiting")
        self.assertFalse(r.exists())

    def test_idempotent_id_and_cache_hit(self):
        base = self.tmp / "tasks"
        tid = self.prov.task_id("sys", "user-a")
        self.assertEqual(tid, self.prov.task_id("sys", "user-a"))
        self.assertNotEqual(tid, self.prov.task_id("sys", "user-b"))
        base.mkdir(parents=True, exist_ok=True)
        (base / (tid + ".response.md")).write_text("响应文本",
                                                   encoding="utf-8")
        text, meta = self.prov._host_complete("sys", "user-a", base)
        self.assertEqual(text, "响应文本")
        self.assertEqual(meta["provider"], "host")
        self.assertEqual(meta["task_id"], tid)

    def test_posix_style_base_dir(self):
        # 跨端口径：正斜杠字符串路径在 Windows pathlib 下会被归一化，
        # 但 host 流必须照常工作（Linux 原生正斜杠同理）——断言流程完成
        # 与文件落位，不断言分隔符字面量。
        base_str = str(self.tmp / "p-tasks").replace(chr(92), "/")
        base = Path(base_str)
        with self.assertRaises(self.prov.HostLLMPending) as cm:
            self.prov._host_complete("s", "u", base)
        prompt = Path(cm.exception.prompt_path)
        self.assertTrue(prompt.is_file())
        self.assertEqual(prompt.parent.name, "p-tasks")

    def test_prompt_file_has_system_user_sections(self):
        base = self.tmp / "tasks"
        try:
            self.prov._host_complete("SYSTEM-SECTION", "USER-SECTION",
                                     base)
        except self.prov.HostLLMPending:
            pass
        tid = self.prov.task_id("SYSTEM-SECTION", "USER-SECTION")
        body = (base / (tid + ".prompt.md")).read_text(encoding="utf-8")
        self.assertIn("# system", body)
        self.assertIn("SYSTEM-SECTION", body)
        self.assertIn("# user", body)
        self.assertIn("USER-SECTION", body)

    def test_select_forced_env_priority(self):
        self.assertEqual(self.prov.select({"CRA_LLM_PROVIDER": "host"}),
                         "host")
        self.assertEqual(self.prov.select({}), "none")


if __name__ == "__main__":
    unittest.main()
