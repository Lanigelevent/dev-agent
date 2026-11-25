"""tests/test_gate_corpus.py — gate 语料构建工具契约（round-83，离线）。

覆盖：静态 F2P 推导（类上下文 / 非 tests/ 前缀 / async）、test_cmds
窄化、基线台账 refine（基线确认 / blocked_data / env_blocked）、
D-048 notes 生成（指针行 + rounds 替换）。
"""
import json
import unittest
from pathlib import Path

import tmpspace

GCB = Path(__file__).resolve().parents[1] / "skills" / "eval-harness" / \
    "scripts" / "gate-corpus-build.py"

TASK = {
    "instance_id": "demo__demo-1",
    "repo": "demo/demo",
    "base_commit": "a" * 40,
    "problem_statement": "make it work",
    "test_patch": (
        "diff --git a/arviz/tests/base_tests/test_x.py "
        "b/arviz/tests/base_tests/test_x.py\n"
        "--- a/arviz/tests/base_tests/test_x.py\n"
        "+++ b/arviz/tests/base_tests/test_x.py\n"
        "+class TestThing:\n"
        "+    async def test_ok(self):\n"
        "+        pass\n"
        "+def test_plain():\n"
        "+    pass\n"
    ),
    "test_cmds": ["python -m pytest -rA"],
}


class TestGateCorpusBuild(unittest.TestCase):
    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gcb_ut", GCB)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _write(self, tmp, rows, name="tasks.jsonl"):
        p = Path(tmp) / name
        with p.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p

    def test_static_f2p_class_context_and_prefix(self):
        mod = self._load()
        nodes = mod.static_f2p(TASK["test_patch"])
        self.assertEqual(
            nodes,
            ["arviz/tests/base_tests/test_x.py::TestThing::test_ok",
             "arviz/tests/base_tests/test_x.py::test_plain"])

    def test_derive_narrows_test_cmds(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="gcb-derive-")
        self.addCleanup(tmpspace.release, tmp)
        src = self._write(tmp, [dict(TASK)])
        out = Path(tmp) / "out.jsonl"
        rc = mod.cmd_derive(type("A", (), {"tasks": str(src),
                                           "out": str(out)})())
        self.assertEqual(rc, 0)
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["fail_to_pass"][0],
                         "arviz/tests/base_tests/test_x.py::TestThing"
                         "::test_ok")
        self.assertIn("arviz/tests/base_tests/test_x.py",
                      row["test_cmds"][0])

    def test_derive_preserves_official_f2p(self):
        """官方 F2P 为判分真值不覆写（r94 实踩：静态 0 时覆写丢字段被
        judge 拒收）；静态候选移 static_f2p；官方缺省回退静态。"""
        mod = self._load()
        tmp = tmpspace.create(prefix="gcb-derive2-")
        self.addCleanup(tmpspace.release, tmp)
        official = dict(TASK)
        official["fail_to_pass"] = ["official/test_a.py::test_one",
                                    "official/test_a.py::test_two"]
        official["instance_id"] = "demo__demo-official"
        fallback = dict(TASK)
        fallback["fail_to_pass"] = []
        fallback["instance_id"] = "demo__demo-fallback"
        src = self._write(tmp, [official, fallback])
        out = Path(tmp) / "out.jsonl"
        rc = mod.cmd_derive(type("A", (), {"tasks": str(src),
                                           "out": str(out)})())
        self.assertEqual(rc, 0)
        rows = {json.loads(l)["instance_id"]: json.loads(l)
                for l in out.read_text(encoding="utf-8").splitlines()}
        self.assertEqual(rows["demo__demo-official"]["fail_to_pass"],
                         ["official/test_a.py::test_one",
                          "official/test_a.py::test_two"])
        self.assertIsInstance(rows["demo__demo-official"]["static_f2p"], list)
        self.assertGreaterEqual(len(rows["demo__demo-fallback"]["fail_to_pass"]),
                                1, "官方缺省时回退静态候选")

    def test_refine_baseline_confirmed_and_blocked(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="gcb-refine-")
        self.addCleanup(tmpspace.release, tmp)
        task_ok = dict(TASK)
        task_ok["fail_to_pass"] = []
        task_block = {"instance_id": "demo__demo-2", "repo": "demo/demo",
                      "base_commit": "b" * 40,
                      "problem_statement": "x",
                      "test_patch": "+++ b/tests/test_y.py\n+++ b/tests/"
                                    "data.yaml\n",
                      "test_cmds": ["python -m pytest -rA tests/test_y.py"],
                      "fail_to_pass": []}
        src = self._write(tmp, [task_ok, task_block])
        log_dir = Path(tmp) / "work" / "w1"
        log_dir.mkdir(parents=True)
        log = log_dir / "test.log"
        log.write_text(
            "FAILED arviz/tests/base_tests/test_x.py::TestThing::test_ok"
            " - AssertionError\n"
            "FAILED unrelated/test_z.py::test_z - X\n",
            encoding="utf-8", newline="\n")
        ledger = Path(tmp) / "ledger.json"
        ledger.write_text(json.dumps({"results": [
            {"instance_id": "demo__demo-1",
             "test_log": str(log), "detail": ""},
            {"instance_id": "demo__demo-2",
             "test_log": str(log), "detail": ""},
        ]}), encoding="utf-8")
        out = Path(tmp) / "out.jsonl"
        rc = mod.cmd_refine(type("A", (), {"tasks": str(src),
                                           "ledger": str(ledger),
                                           "out": str(out)})())
        rows = {json.loads(l)["instance_id"]:
                json.loads(l) for l in
                out.read_text(encoding="utf-8").splitlines() if l.strip()}
        self.assertEqual(rc, 1, "存在 blocked_data 时 rc=1")
        self.assertEqual(rows["demo__demo-1"]["fail_to_pass"],
                         ["arviz/tests/base_tests/test_x.py::TestThing"
                          "::test_ok"])
        self.assertIn("blocked_data",
                      rows["demo__demo-2"]["adaptation_note"])

    def test_notes_pointer_line_and_rounds(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="gcb-notes-")
        self.addCleanup(tmpspace.release, tmp)
        tpl = Path(tmp) / "tpl.md"
        tpl.write_text("- You have a total budget of N rounds.\n"
                       "- at most N/3 rounds exploration.\n",
                       encoding="utf-8", newline="\n")
        src = self._write(tmp, [dict(TASK)])
        out_dir = Path(tmp) / "notes"
        rc = mod.cmd_notes(type("A", (), {"tasks": str(src),
                                          "out": str(out_dir),
                                          "template": str(tpl),
                                          "rounds": 24})())
        self.assertEqual(rc, 0)
        text = (out_dir / "notes-demo__demo-1.md").read_text(
            encoding="utf-8")
        self.assertIn("24 rounds", text)
        self.assertIn("The failing tests live in", text)
        self.assertIn("test_ok", text)

    def test_notes_missing_file_is_param_error(self):
        mod = self._load()
        with self.assertRaises(SystemExit) as ctx:
            mod.cmd_notes(type("A", (), {"tasks": "no-such-file.jsonl",
                                         "out": "unused",
                                         "template": "unused",
                                         "rounds": 24})())
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
