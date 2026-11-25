# -*- coding: utf-8 -*-
"""tests/test_doc_structure.py — doc-structure.py 契约（round-91 D-050；round-219 S10）。

覆盖手册 §7.1 九判据 + 脚本 UTF-8 stdout 契约 + §7.3 判别力实证（注入缺陷必须判红；
干净骨架必须复绿）。夹具为最小三层骨架（tmpspace，11 文档 + 1 主入口脚本）。
"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "doc-structure.py"


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("doc_structure_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _invoke(mod, argv):
    old = sys.argv
    out = io.StringIO()
    try:
        sys.argv = ["doc-structure.py"] + argv
        with contextlib.redirect_stdout(out):
            rc = mod.main()
    finally:
        sys.argv = old
    return rc, out.getvalue()


META = """> **创建日期**：2026-01-01 ｜ **当前状态**：维护中
> **权威范围**：测试范围 ｜ **所有者**：t
> **复核期限**：2027-01-01 ｜ **上次复核**：2026-01-01
> **主导模式**：参考
> **不是权威**：测试用法（示例）
"""

ENTRY_NAMES = ["01-overview", "02-architecture", "03-decisions",
               "04-progress", "05-troubleshooting", "06-operations",
               "07-tasks", "08-memory"]


def _doc(title, body="", meta=META):
    return "# %s\n\n%s\n%s\n" % (title, meta, body)


SAFE_SCRIPT = '''import sys


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print("{}")


if __name__ == "__main__":
    main()
'''


def _skeleton(tmp):
    """最小三层骨架：README + RULES + INDEX + 8 类入口 = 11 文件。"""
    (tmp / "docs").mkdir(parents=True)
    (tmp / "README.md").write_text(
        _doc("统一入口", "见 [RULES](docs/RULES.md)"),
        encoding="utf-8")
    (tmp / "docs" / "RULES.md").write_text(
        _doc("工程约束", "| a | b |\n|---|---|\n| 1 | 2 |"),
        encoding="utf-8")
    idx_rows = "\n".join(
        "| docs/%s/README.md | x |" % n for n in ENTRY_NAMES)
    (tmp / "docs" / "INDEX.md").write_text(
        _doc("树内索引", "| 文档 | 类 |\n|---|---|\n%s" % idx_rows),
        encoding="utf-8")
    for n in ENTRY_NAMES:
        d = tmp / "docs" / n
        d.mkdir(exist_ok=True)
        (d / "README.md").write_text(
            _doc(n, "导航见 [INDEX](../INDEX.md) 与 [RULES](../RULES.md)"),
            encoding="utf-8")
    scripts = tmp / "skills" / "demo" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "cli.py").write_text(SAFE_SCRIPT, encoding="utf-8", newline="\n")
    return tmp


class DocStructureTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_script()
        self.tmp = Path(tmpspace.create(prefix="docstruct-"))
        self.addCleanup(tmpspace.release, self.tmp)
        _skeleton(self.tmp)

    def _run(self):
        rc, out = _invoke(self.mod, ["--root", str(self.tmp)])
        d = json.loads(out)
        by_id = {}
        for c in d["checks"]:
            by_id.setdefault(c["id"], []).append(c)
        return rc, d, by_id

    def _script(self):
        return self.tmp / "skills" / "demo" / "scripts" / "cli.py"

    def test_clean_skeleton_green(self):
        rc, d, by_id = self._run()
        self.assertEqual(rc, 0)
        self.assertTrue(d["ok"])
        self.assertGreaterEqual(d["files_scanned"], 11)
        self.assertGreaterEqual(d["links_checked"], 9)
        self.assertEqual(by_id["script_encoding"][0]["scripts_scanned"], 1)

    def test_script_encoding_missing_red(self):
        self._script().write_text(
            'def main():\n    print("x")\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])
        self.assertEqual(by_id["script_encoding"][0]["missing"][0]["file"],
                         "skills/demo/scripts/cli.py")

    def test_script_encoding_comment_and_string_not_accepted(self):
        self._script().write_text(
            'import sys\nTEXT = "sys.stdout.reconfigure(encoding=\'utf-8\')"\n'
            '# sys.stdout.reconfigure(encoding="utf-8")\n'
            'def main():\n    print("x")\n\nif __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_wrong_codec_red(self):
        self._script().write_text(SAFE_SCRIPT.replace('encoding="utf-8"',
                                                      'encoding="cp936"'),
                                  encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_unused_helper_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def configure():\n'
            '    for stream in (sys.stdout, sys.stderr):\n'
            '        stream.reconfigure(encoding="utf-8")\n\n'
            'def main():\n    print("x")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_unreachable_caller_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def configure():\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'def unused():\n    configure()\n\n'
            'def main():\n    print("x")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_loop_rebind_stderr_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n'
            '    for stream in (sys.stdout, sys.stderr):\n'
            '        stream = sys.stderr\n'
            '        stream.reconfigure(encoding="utf-8")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_call_outside_stdout_loop_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n'
            '    for stream in (sys.stdout, sys.stderr):\n        pass\n'
            '    stream = sys.stderr\n'
            '    stream.reconfigure(encoding="utf-8")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_stdout_alias_green(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n'
            '    out = sys.stdout\n'
            '    out.reconfigure(encoding="utf-8")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, _d, by_id = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(by_id["script_encoding"][0]["status"], "PASS")

    def test_script_encoding_false_branch_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n'
            '    if False:\n'
            '        sys.stdout.reconfigure(encoding="utf-8")\n'
            '    print("x")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_after_return_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n'
            '    return\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_unused_emit_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def _emit():\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'def main():\n    print("x")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_locally_shadowed_emit_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def _emit():\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'def main():\n'
            '    _emit = lambda: None\n'
            '    _emit()\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_module_call_outside_guard_red(self):
        self._script().write_text(
            'import sys\n'
            'sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'def main():\n    print("x")\n\n'
            'if __name__ == "__main__":\n    main()\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_guard_else_red(self):
        self._script().write_text(
            'import sys\n\n'
            'def main():\n    print("x")\n\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
            'else:\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_shadowed_sys_red(self):
        self._script().write_text(
            'def main(sys):\n'
            '    sys.stdout.reconfigure(encoding="utf-8")\n\n'
            'if __name__ == "__main__":\n    main(None)\n',
            encoding="utf-8", newline="\n")
        rc, d, _ = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])

    def test_script_encoding_library_module_excluded(self):
        (self._script().parent / "library.py").write_text(
            'def helper():\n    return 1\n', encoding="utf-8", newline="\n")
        rc, _d, by_id = self._run()
        self.assertEqual(rc, 0)
        self.assertEqual(by_id["script_encoding"][0]["scripts_scanned"], 1)

    def test_script_encoding_parse_error_red(self):
        self._script().write_text("def broken(:\n", encoding="utf-8", newline="\n")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])
        self.assertTrue(by_id["script_encoding"][0]["missing"][0]["reason"]
                        .startswith("parse_error:"))

    def test_script_encoding_scan_floor_red(self):
        import shutil
        shutil.rmtree(self.tmp / "skills")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("script_encoding", d["failed"])
        self.assertEqual(by_id["script_encoding"][0]["scripts_scanned"], 0)

    def test_missing_meta_field_red(self):
        p = self.tmp / "docs" / "01-overview" / "README.md"
        p.write_text(_doc("x", meta=META.replace("创建日期", "建立日期")),
                     encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("meta_fields", d["failed"])

    def test_not_authority_meta_red(self):
        """不是权威 缺失即 meta_fields 判红（D-050 第八元字段契约）。"""
        p = self.tmp / "docs" / "01-overview" / "README.md"
        stripped = "\n".join(
            ln for ln in META.splitlines() if "不是权威" not in ln)
        p.write_text(_doc("x", meta=stripped), encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("meta_fields", d["failed"])

    def test_broken_link_red(self):
        p = self.tmp / "README.md"
        p.write_text(_doc("统一入口", "见 [RULES](docs/NOPE.md)"),
                     encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("link_exists", d["failed"])
        self.assertEqual(by_id["link_exists"][0]["targets"], ["docs/NOPE.md"])

    def test_broken_anchor_red(self):
        p = self.tmp / "docs" / "01-overview" / "README.md"
        p.write_text(_doc(
            "x", "见 [IN](../INDEX.md#不存在节)"), encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("anchor_match", d["failed"])

    def test_table_shape_red(self):
        p = self.tmp / "docs" / "RULES.md"
        p.write_text(_doc(
            "工程约束",
            "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 | 5 |\n| 6 | 7 |"),
            encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("table_shape", d["failed"])

    def test_table_shape_escaped_pipe_green(self):
        # \| 转义竖线：剥离 r"\|" 后列数一致 → PASS；若 replace 目标序列
        # 变更（如漏剥 \|），本行原始 | 计数 3≠表头 2，table_shape 必红。
        p = self.tmp / "docs" / "RULES.md"
        p.write_text(_doc(
            "工程约束",
            "| a | b |\n|---|---|\n| 1 | 2 |\n| 3\\|x | y |"),
            encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 0)
        self.assertNotIn("table_shape", d["failed"])

    def test_table_shape_escaped_pipe_red(self):
        # \| 剥离后仍不一致（3 列 ≠ 表头 2 列）→ FAIL，转义竖线不豁免形状检查。
        p = self.tmp / "docs" / "RULES.md"
        p.write_text(_doc(
            "工程约束",
            "| a | b |\n|---|---|\n| 1\\|x | y | z |"),
            encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("table_shape", d["failed"])

    def test_registry_missing_red(self):
        p = self.tmp / "docs" / "INDEX.md"
        text = p.read_text(encoding="utf-8")
        p.write_text(text.replace("| docs/02-architecture/README.md | x |",
                                  "| docs/02-arch.md | x |"),
                     encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("registry", d["failed"])

    def test_link_text_banned_red(self):
        p = self.tmp / "docs" / "01-overview" / "README.md"
        p.write_text(_doc("x", "见[这里](../INDEX.md)"), encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("link_text", d["failed"])

    def test_heading_jump_red(self):
        p = self.tmp / "docs" / "01-overview" / "README.md"
        p.write_text(_doc("x", "## a\n\n#### b"),
                     encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("heading_level", d["failed"])

    def test_placeholder_red(self):
        p = self.tmp / "docs" / "01-overview" / "README.md"
        p.write_text(_doc("x", "此处写 <待补内容> 明天填"),
                     encoding="utf-8")
        rc, d, by_id = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("placeholder", d["failed"])

    def test_scan_floor_rc2(self):
        for n in ("07-tasks", "08-memory", "06-operations"):
            import shutil
            shutil.rmtree(self.tmp / "docs" / n)
        rc, out = _invoke(self.mod, ["--root", str(self.tmp)])
        self.assertEqual(rc, 2)
        d = json.loads(out)
        self.assertIn("扫描面不足", d["error"])

    def test_stdout_single_json(self):
        rc, out = _invoke(self.mod, ["--root", str(self.tmp)])
        d = json.loads(out)  # 整个 stdout 必须是单个 JSON 文档
        self.assertIn("checks", d)
        self.assertIn("files_scanned", d)
