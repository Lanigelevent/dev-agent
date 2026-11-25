# -*- coding: utf-8 -*-
"""tests/test_repo_rules_inject.py — repo-rules-inject 四契约（round-214，AB-22 rules 注入面）。

反向验证面：造违规样例确认抓得住（红线 6）——密钥形态摘录必须脱敏、
超限必须截断、无文件必须 none_found、坏输入必须 rc=2。
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/multi-agent-review/scripts/repo-rules-inject.py"


def _run_script(args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True, timeout=60)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def _load_module():
    spec = importlib.util.spec_from_file_location("repo_rules_inject", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRepoRulesInject(unittest.TestCase):
    """发现/摘录/脱敏/截断/none_found/坏输入六面。"""

    def test_discovery_excerpt_and_truncation(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "AGENTS.md").write_text(
                "规则" * 3000, encoding="utf-8")
            rc, out = _run_script(["--repo", td, "--max-chars", "120"])
            data = json.loads(out)
            self.assertEqual(rc, 0)
            self.assertFalse(data["none_found"])
            f = data["found"][0]
            self.assertEqual(f["name"], "AGENTS.md")
            self.assertTrue(f["truncated"])
            self.assertLessEqual(len(f["excerpt"]), 120)

    def test_secret_redaction_in_excerpt(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "AGENTS.md").write_text(
                'api_key = "sk-abc123secret"\n正常规范内容\n',
                encoding="utf-8")
            rc, out = _run_script(["--repo", td])
            data = json.loads(out)
            self.assertEqual(rc, 0)
            excerpt = data["found"][0]["excerpt"]
            self.assertNotIn("sk-abc123secret", excerpt)
            self.assertIn("<redacted>", excerpt)

    def test_cursor_rules_dir_and_none_found(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = _run_script(["--repo", td])
            data = json.loads(out)
            self.assertEqual(rc, 0)
            self.assertTrue(data["none_found"])
            (Path(td) / ".cursor" / "rules").mkdir(parents=True)
            (Path(td) / ".cursor" / "rules" / "a.mdc").write_text(
                "规则内容", encoding="utf-8")
            rc, out = _run_script(["--repo", td])
            data = json.loads(out)
            self.assertEqual(rc, 0)
            names = [f["name"] for f in data["found"]]
            self.assertIn(".cursor/rules/a.mdc", names)

    def test_bad_repo_rc2(self):
        rc, out = _run_script(["--repo", "Z:/nonexistent-repo-zz"])
        self.assertEqual(rc, 2)
        data = json.loads(out)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
