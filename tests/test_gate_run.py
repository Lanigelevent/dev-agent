"""tests/test_gate_run.py — gate 评测运行面驱动契约（round-85，离线）。

覆盖：prepare 种子 worktree（幂等 / 缓存缺仓报错）、run 的 key 环境闸
与 --dry-run（协议 v4 环境与 PYTHONPATH 前置）、judge 的 predictions
构造与 --dry-run（委托 live-sample）、report 聚合（f2p-only 口径注记）。
"""
import json
import os
import subprocess
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
GATE_RUN = ROOT / "skills" / "eval-harness" / "scripts" / "gate-run.py"
LIVE = ROOT / "skills" / "eval-harness" / "scripts" / "live-sample.py"

TASK = {
    "instance_id": "demo__demo-1",
    "repo": "demo/demo",
    "base_commit": "SET_AT_RUNTIME",
    "problem_statement": "make it work",
    "test_patch": (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n"
        "--- a/tests/test_x.py\n"
        "+++ b/tests/test_x.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def test_old():\n"
        "     assert True\n"
        "+def test_new():\n"
        "+    assert True\n"
    ),
    "test_cmds": ["python -m pytest -rA"],
    "fail_to_pass": ["tests/test_x.py::test_new"],
}


def _git(args, cwd=None):
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(["git"] + args, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, env=e)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


class TestGateRun(unittest.TestCase):
    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("gate_run_ut",
                                                      GATE_RUN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _fixture_repo(self, tmp):
        """本地仓 + 缓存 clone + 任务 JSONL（base_commit 运行期回填）。"""
        src = Path(tmp) / "src"
        src.mkdir(parents=True)
        for a in (["init", "-q"], ["config", "user.email", "t@t"],
                  ["config", "user.name", "t"],
                  ["config", "commit.gpgsign", "false"]):
            _git(a, cwd=src)
        (src / "mod.py").write_text("X = 1\n", encoding="utf-8",
                                    newline="\n")
        tdir = src / "tests"
        tdir.mkdir()
        (tdir / "test_x.py").write_text(
            "def test_old():\n    assert True\n", encoding="utf-8",
            newline="\n")
        _git(["add", "-A"], cwd=src)
        _git(["commit", "-qm", "c1"], cwd=src)
        sha = _git(["rev-parse", "HEAD"], cwd=src)[1].strip()
        cache = Path(tmp) / "cache" / "demo"
        cache.parent.mkdir(parents=True)
        _git(["clone", "--quiet", "--no-hardlinks", str(src),
              str(cache)])
        task = dict(TASK)
        task["base_commit"] = sha
        tasks = Path(tmp) / "tasks.jsonl"
        with tasks.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
        return tasks, sha

    def _call(self, mod, ns):
        return mod.main.__globals__  # not used; placeholder

    def test_prepare_seeds_and_idempotent(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="grun-prep-")
        self.addCleanup(tmpspace.release, tmp)
        tasks, _ = self._fixture_repo(tmp)
        work = Path(tmp) / "work"
        ns = type("A", (), {"tasks": str(tasks), "work": str(work),
                            "source_root": str(Path(tmp) / "cache"),
                            "instances": "", "arms": "single"})()
        rc = mod.cmd_prepare(ns)
        self.assertEqual(rc, 0)
        repo = work / "demo__demo-1" / "single" / "repo"
        self.assertTrue((repo / "tests" / "test_x.py").is_file())
        self.assertEqual(mod._seed_count(repo), 2, "base + 1 seed commit")
        rc = mod.cmd_prepare(ns)
        self.assertEqual(rc, 0)
        out = json.loads(self._captured_json(mod, ns))
        self.assertEqual(out["prepared"][0].get("skipped"),
                         "already-seeded")

    def _captured_json(self, mod, ns):
        # cmd_prepare prints JSON to stdout; capture via io redirect
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.cmd_prepare(ns)
        return buf.getvalue()

    def test_run_requires_key_env(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="grun-key-")
        self.addCleanup(tmpspace.release, tmp)
        tasks, _ = self._fixture_repo(tmp)
        backup = os.environ.pop("REVIEW_LLM_API_KEY", None)
        try:
            with self.assertRaises(SystemExit) as ctx:
                mod.cmd_run(type("A", (), {
                    "tasks": str(tasks), "work": str(Path(tmp) / "w"),
                    "endpoint": "https://api.example.com",
                    "model": "m", "instances": "", "arms": "single",
                    "rounds": 24, "test_cmd": "", "retry_once": False,
                    "timeout": 60, "dry_run": True})())
            self.assertEqual(ctx.exception.code, 2)
        finally:
            if backup is not None:
                os.environ["REVIEW_LLM_API_KEY"] = backup

    def test_run_dry_run_protocol_v4_env(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="grun-dry-")
        self.addCleanup(tmpspace.release, tmp)
        tasks, _ = self._fixture_repo(tmp)
        work = Path(tmp) / "work"
        mod.cmd_prepare(type("A", (), {
            "tasks": str(tasks), "work": str(work),
            "source_root": str(Path(tmp) / "cache"), "instances": "",
            "arms": "single"})())
        os.environ.setdefault("REVIEW_LLM_API_KEY", "dummy-for-contract")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.cmd_run(type("A", (), {
                "tasks": str(tasks), "work": str(work),
                "endpoint": "https://api.deepseek.com",
                "model": "deepseek-chat", "instances": "",
                "arms": "single", "rounds": 24, "test_cmd": "",
                "retry_once": False, "timeout": 60,
                "dry_run": True})())
        out = json.loads(buf.getvalue())
        r = out["results"][0]
        self.assertTrue(r["dry_run"])
        cmd = " ".join(r["cmd"])
        self.assertIn("--protocol-notes", cmd, "D-048 附录必须挂载")
        self.assertIn("--rounds", cmd)
        self.assertIn("REVIEW_LLM_JSON_MODE", " ".join(r["env_keys"]))
        pp = [k for k in r["env_keys"] if k == "PYTHONPATH"]
        self.assertEqual(pp, ["PYTHONPATH"], "PYTHONPATH 前置必须存在")

    def test_judge_dry_run_and_report(self):
        mod = self._load()
        tmp = tmpspace.create(prefix="grun-judge-")
        self.addCleanup(tmpspace.release, tmp)
        tasks, _ = self._fixture_repo(tmp)
        work = Path(tmp) / "work"
        mod.cmd_prepare(type("A", (), {
            "tasks": str(tasks), "work": str(work),
            "source_root": str(Path(tmp) / "cache"), "instances": "",
            "arms": "single"})())
        out = work / "demo__demo-1" / "single" / "out"
        out.mkdir(parents=True)
        (out / "edits.patch").write_text(
            "diff --git a/mod.py b/mod.py\n--- a/mod.py\n+++ b/mod.py\n"
            "@@ -1 +1,2 @@\n X = 1\n+Y = 2\n", encoding="utf-8",
            newline="\n")
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.cmd_judge(type("A", (), {
                "tasks": str(tasks), "work": str(work), "instances": "",
                "f2p_only": True, "timeout": 60,
                "dry_run": True})())
        d = json.loads(buf.getvalue())
        self.assertTrue(d["dry_run"])
        self.assertIn("live-sample.py", " ".join(d["cmd"]))
        self.assertIn("--f2p-only", " ".join(d["cmd"]))
        # report 聚合
        jd = work / "judge"
        jd.mkdir()
        (jd / "live-sample-ledger.json").write_text(json.dumps(
            {"results": [{"instance_id": "demo__demo-1",
                          "state": "f2p_passed",
                          "elapsed_sec": 52.5}]}), encoding="utf-8")
        bench = Path(tmp) / "bench.json"
        mod.cmd_report(type("A", (), {"work": str(work),
                                      "out": str(bench)})())
        data = json.loads(bench.read_text(encoding="utf-8"))
        self.assertEqual(data["counts"], {"f2p_passed": 1})
        self.assertIn("f2p-only", data["caliber"])
        self.assertEqual(data["rows"][0]["patch_bytes"] > 0, True)


if __name__ == "__main__":
    unittest.main()
