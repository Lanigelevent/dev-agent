#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_live_sample.py — SWE-bench Live 适配层契约（离线，不触网）。

覆盖：参数/字段错误退出码 2、--dry-run 计划（本地源码就绪判定、绝对路径
worktree）、test_patch 结构闸、blocked_source 不静默丢样本、台账续跑，
以及一条本地 git 仓库上的 baseline → gold 端到端（--skip-venv，秒级）。
"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

import tmpspace
from _scripts_common import run

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "skills" / "eval-harness" / "scripts" / "live-sample.py"

BASE_TEST = ("from mod import add\n\n\n"
             "def test_fix():\n    assert False\n\n\n"
             "def test_keep():\n    assert True\n")
FIXED_TEST = ("from mod import add\n\n\n"
              "def test_fix():\n    assert add(1, 2) == 3\n\n\n"
              "def test_keep():\n    assert True\n")
BASE_MOD = "def add(a, b):\n    return 0\n"
GOLD_MOD = "def add(a, b):\n    return a + b\n"


def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if p.returncode != 0:
        raise AssertionError("git %s 失败: %s" % (args, p.stderr))
    return p.stdout


def _commit(repo, message):
    _git(repo, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-m", message)


def _write(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")


def build_repo(tmp):
    """本地源仓：base 提交 + test_patch/gold_patch 两段真实 diff。"""
    src = Path(tmp) / "sources" / "repo"
    src.mkdir(parents=True)
    _write(src / "mod.py", BASE_MOD)
    _write(src / "test_mod.py", BASE_TEST)
    _git(src, "init", "-q")
    _git(src, "add", ".")
    _commit(src, "base")
    base = _git(src, "rev-parse", "HEAD").strip()
    _write(src / "test_mod.py", FIXED_TEST)
    test_patch = _git(src, "diff", "--", "test_mod.py")
    _git(src, "checkout", "--", "test_mod.py")
    _write(src / "mod.py", GOLD_MOD)
    gold_patch = _git(src, "diff", "--", "mod.py")
    _git(src, "checkout", "--", "mod.py")
    return src, base, test_patch, gold_patch


def _task(base, test_patch, gold_patch):
    return {
        "instance_id": "demo__repo-1",
        "repo": "demo/repo",
        "base_commit": base,
        "test_patch": test_patch,
        "gold_patch": gold_patch,
        "test_cmds": ["python -m pytest -rA test_mod.py"],
        "fail_to_pass": ["test_mod.py::test_fix"],
        "pass_to_pass": ["test_mod.py::test_keep"],
    }


def _write_tasks(tmp, tasks):
    path = Path(tmp) / "tasks.jsonl"
    _write(path, "\n".join(json.dumps(t, ensure_ascii=False)
                           for t in tasks) + "\n")
    return path


def _base_args(tasks, out, sources, mode="baseline"):
    return ["--tasks", str(tasks), "--mode", mode, "--out", str(out),
            "--source-root", str(sources), "--skip-venv",
            "--python", sys.executable, "--no-network",
            "--exec-timeout", "120"]


def _pid_alive(pid):
    if sys.platform == "win32":
        # PEP 686 口径：显式指定编码，不依赖 locale 默认（PYTHONUTF8=1 下
        # text=True 会按 UTF-8 严格解码 tasklist 的 ANSI 输出而抛错）。
        p = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid],
                           capture_output=True, text=True,
                           encoding="mbcs", errors="replace")
        return str(pid) in p.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class TestLiveSample(unittest.TestCase):
    def test_param_errors_exit_2(self):
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = _write_tasks(tmp, [])
        rc, _, _, _ = run(LIVE, "--tasks", str(Path(tmp) / "absent.jsonl"),
                          "--out", tmp)
        self.assertEqual(rc, 2, "任务清单缺失应参数错误")
        rc, _, _, _ = run(LIVE, "--tasks", str(tasks), "--mode", "predictions",
                          "--out", tmp)
        self.assertEqual(rc, 2, "predictions 模式缺 --predictions 应参数错误")
        rc, data, _, _ = run(LIVE, "--tasks", str(tasks), "--instances",
                             "demo-missing", "--out", tmp)
        self.assertEqual(rc, 2, "缺实例必须点名报错")
        self.assertIn("demo-missing", json.dumps(data, ensure_ascii=False))
        bad = _write_tasks(tmp, [{"instance_id": "demo-empty",
                                  "repo": "demo/repo"}])
        rc, data, _, _ = run(LIVE, "--tasks", str(bad), "--out", tmp)
        self.assertEqual(rc, 2, "任务字段缺失应参数错误")
        self.assertIn("base_commit", json.dumps(data, ensure_ascii=False))

    def test_dry_run_plan(self):
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        src, base, test_patch, gold_patch = build_repo(tmp)
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        rc, data, _, _ = run(LIVE, *_base_args(tasks, Path(tmp) / "out",
                                               Path(tmp) / "sources"),
                             "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300])
        item = data["tasks"][0]
        self.assertTrue(item["source_ready"])
        self.assertTrue(Path(item["worktree"]).is_absolute())
        self.assertEqual(item["fail_to_pass"], 1)
        self.assertEqual(item["pass_to_pass"], 1)
        self.assertIn("pytest", item["test_cmds"][0])

    def test_blocked_source_and_malformed_test_patch(self):
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        empty = Path(tmp) / "empty-sources"
        empty.mkdir()
        out = Path(tmp) / "out"
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        rc, data, _, _ = run(LIVE, *_base_args(tasks, out, empty))
        self.assertEqual(rc, 1)
        self.assertEqual(data["blocked_source"], 1)
        broken = _task(base, "diff --git a/test_mod.py b/test_mod.py\n"
                             "--- a/test_mod.py\n+++ b/test_mod.py\n"
                             "@@ -1 +1 @@\n-old\n", gold_patch)
        broken_dir = Path(tmp) / "broken"
        broken_dir.mkdir()
        tasks2 = _write_tasks(broken_dir, [broken])
        rc, data, _, _ = run(LIVE, *_base_args(tasks2, Path(tmp) / "out2",
                                               empty))
        self.assertEqual(rc, 1)
        self.assertEqual(data["counts"].get("malformed_test_patch"), 1)

    def test_predictions_integrity_flagged(self):
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        bad = ("diff --git a/test_mod.py b/test_mod.py\n"
               "--- a/test_mod.py\n+++ b/test_mod.py\n"
               "@@ -1 +1 @@\n-from mod import add\n+from mod import add  # x\n")
        preds = Path(tmp) / "preds.jsonl"
        _write(preds, json.dumps({"instance_id": "demo__repo-1",
                                  "model_patch": bad}) + "\n")
        rc, data, _, _ = run(LIVE, "--tasks", str(tasks), "--mode",
                             "predictions", "--predictions", str(preds),
                             "--out", str(Path(tmp) / "out"),
                             "--source-root", str(Path(tmp) / "empty"),
                             "--skip-venv", "--python", sys.executable,
                             "--no-network")
        self.assertEqual(rc, 1)
        self.assertEqual(data["counts"].get("integrity_flagged"), 1,
                         "改既有测试的预测补丁必须被完整性闸拦下")

    def test_baseline_then_gold_end_to_end(self):
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        src, base, test_patch, gold_patch = build_repo(tmp)
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        out = Path(tmp) / "out"
        sources = Path(tmp) / "sources"
        rc, data, _, err = run(LIVE, *_base_args(tasks, out, sources))
        self.assertEqual(rc, 0, (str(data)[:300] + err[-500:]))
        self.assertEqual(data["counts"].get("baseline_ok"), 1)
        rc, data, _, err = run(LIVE, *_base_args(tasks, out, sources, "gold"))
        self.assertEqual(rc, 0, (str(data)[:300] + err[-500:]))
        self.assertEqual(data["resolved"], 1, "gold 补丁应 resolved")
        ledger = json.loads((out / "live-sample-ledger.json")
                            .read_text(encoding="utf-8"))
        states = {(row["instance_id"], row["mode"]): row["state"]
                  for row in ledger["results"]}
        self.assertEqual(states[("demo__repo-1", "baseline")], "baseline_ok")
        self.assertEqual(states[("demo__repo-1", "gold")], "resolved")
        rc, data, _, _ = run(LIVE, *_base_args(tasks, out, sources))
        self.assertEqual(rc, 0, "台账续跑应跳过已 DONE 实例")
        self.assertEqual(data["run_this_time"], 0)

    def test_truncated_node_ids_fail_fast(self):
        """round-65 实踩：lite.parquet 参数化 node id 含空格被截断（`[` 未闭合）。

        cfn-lint-3749 的 1223 条 P2P 里 329 条形如 `...::test_sorted[Different`
        （原表 0 条含空格），exact-match 判分必判 missing；必须在建环境前判
        malformed_node_ids，而不是跑完 3 分钟套件才拿一个迟到的 baseline_unexpected。
        """
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        bad = _task(base, test_patch, gold_patch)
        bad["pass_to_pass"] = ["test_mod.py::test_keep[Different order"]
        tasks = _write_tasks(tmp, [bad])
        out = Path(tmp) / "out"
        rc, data, _, _ = run(LIVE, *_base_args(tasks, out,
                                               Path(tmp) / "sources"))
        self.assertEqual(rc, 1, data)
        self.assertEqual(data["counts"].get("malformed_node_ids"), 1)
        self.assertNotIn("blocked_source", data["counts"], "数据体检先于取源")
        ledger = json.loads((out / "live-sample-ledger.json")
                            .read_text(encoding="utf-8"))
        self.assertIn("括号不闭合", ledger["results"][0]["detail"])
        # 正向：干净 id 的 dry-run 计划 node_id_problems=0
        good = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        rc, plan, _, _ = run(LIVE, *_base_args(good, Path(tmp) / "out2",
                                               Path(tmp) / "sources"),
                             "--dry-run")
        self.assertEqual(rc, 0, plan)
        self.assertEqual(plan["tasks"][0]["node_id_problems"], 0)

    def test_node_check_scopes_to_judged_ids(self):
        """round-67 补：体检范围对齐判分范围——--f2p-only 只判 F2P。

        matplotlib-28933 实踩（round-51 结案复验失灵两轮未察觉）：P2P 里
        219 条上游截断 id 与 f2p-only 判分无关，不得把整条通路拦死；
        F2P 里出现坏 id 仍须立即判红。
        """
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        task = _task(base, test_patch, gold_patch)
        task["pass_to_pass"] = ["test_mod.py::test_keep[Different order"]
        tasks = _write_tasks(tmp, [task])
        # f2p_only：P2P 坏 id 不拦（走到取源/判分阶段才失败），不判 malformed
        rc, data, _, _ = run(LIVE, *_base_args(tasks, Path(tmp) / "out1",
                                               Path(tmp) / "sources"),
                             "--f2p-only")
        self.assertFalse(data["counts"].get("malformed_node_ids"), data)
        # dry-run 计划同样按 f2p_only 计 0
        rc, plan, _, _ = run(LIVE, *_base_args(tasks, Path(tmp) / "out2",
                                               Path(tmp) / "sources"),
                             "--f2p-only", "--dry-run")
        self.assertEqual(rc, 0, plan)
        self.assertEqual(plan["tasks"][0]["node_id_problems"], 0)
        # F2P 里的坏 id 仍立即判红（f2p_only 语义下也拦）
        task2 = _task(base, test_patch, gold_patch)
        task2["fail_to_pass"] = ["test_mod.py::test_new[Different order"]
        tasks2 = _write_tasks(tmp, [task2])
        rc, data2, _, _ = run(LIVE, *_base_args(tasks2, Path(tmp) / "out3",
                                                Path(tmp) / "sources"),
                              "--f2p-only")
        self.assertEqual(rc, 1, data2)
        self.assertEqual(data2["counts"].get("malformed_node_ids"), 1, data2)

    def test_run_timeout_kills_process_tree(self):
        """超时必须杀掉孙进程（round-51 真坑：git-remote-https 残留占目录）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("live_sample_under_test",
                                                      LIVE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        pid_file = Path(tmp) / "child.pid"
        code = ("import subprocess, sys, time, pathlib\n"
                "p = subprocess.Popen([sys.executable, '-c',\n"
                "                      'import time; time.sleep(60)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(p.pid))\n"
                "time.sleep(60)\n")
        rc, _, err = mod._run([sys.executable, "-c", code, str(pid_file)],
                              timeout=3)
        self.assertEqual(rc, 124)
        self.assertIn("timeout", err)
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        deadline = time.time() + 5
        while _pid_alive(pid) and time.time() < deadline:
            time.sleep(0.1)
        self.assertFalse(_pid_alive(pid), "孙进程必须随超时被杀掉")

    def test_env_for_uses_absolute_venv_path(self):
        """cwd 切到 worktree 后，相对 PATH 会让 venv 的 pytest 消失。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location("live_sample_under_test2",
                                                      LIVE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        env = mod.env_for("some/venv/Scripts/python.exe")
        first = env["PATH"].split(os.pathsep)[0]
        self.assertTrue(os.path.isabs(first), first)
        self.assertTrue(first.endswith("Scripts"), first)

    def test_setup_cmds_run_in_repo_root(self):
        """setup_cmds 的 cwd 必须是仓库根（round-51 真坑：外层目录导致
        `pip install -e .` 找不到工程）。"""
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        script = Path(tmp) / "cwd_probe.py"
        _write(script, "import pathlib, sys\n"
                       "pathlib.Path(sys.argv[1]).write_text(\n"
                       "    str(pathlib.Path.cwd()))\n")
        task = _task(base, test_patch, gold_patch)
        task["setup_cmds"] = ['"%s" "%s" "%s"'
                              % (sys.executable, script,
                                 "cwd.txt")]
        tasks = _write_tasks(tmp, [task])
        out = Path(tmp) / "out"
        rc, data, _, err = run(LIVE, *_base_args(tasks, out,
                                                 Path(tmp) / "sources"))
        self.assertEqual(rc, 0, str(data)[:300] + err[-400:])
        self.assertEqual(data["counts"].get("baseline_ok"), 1)
        probes = list((out / "work").glob("*/repo/cwd.txt"))
        self.assertEqual(len(probes), 1, "cwd 探针必须落在仓库根内")
        self.assertEqual(len(list((out / "work").glob("*/cwd.txt"))), 0,
                         "setup_cmds 不得在外层目录执行")

    def test_force_preserves_other_ledger_rows(self):
        """--force 只重跑目标样本，不得覆盖其他台账行（round-51 真坑）。"""
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        out = Path(tmp) / "out"
        out.mkdir()
        (out / "live-sample-ledger.json").write_text(json.dumps({
            "results": [{"instance_id": "demo__repo-1", "mode": "gold",
                         "key": "demo__repo-1|gold", "state": "f2p_passed",
                         "partial": True, "resolved": None}]},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        rc, data, _, err = run(LIVE, *_base_args(tasks, out,
                                                 Path(tmp) / "sources"))
        self.assertEqual(rc, 0, str(data)[:300] + err[-400:])
        ledger = json.loads((out / "live-sample-ledger.json")
                            .read_text(encoding="utf-8"))
        states = {(row["instance_id"], row["mode"]): row["state"]
                  for row in ledger["results"]}
        self.assertEqual(states.get(("demo__repo-1", "gold")), "f2p_passed",
                         "强制重跑不得丢掉其他模式行")
        self.assertEqual(states.get(("demo__repo-1", "baseline")),
                         "baseline_ok")

    def test_f2p_only_marks_partial(self):
        """只跑 F2P 的可行性口径：通过记 f2p_passed，不得冒充 resolved。"""
        tmp = tmpspace.create(prefix="live-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        _, base, test_patch, gold_patch = build_repo(tmp)
        tasks = _write_tasks(tmp, [_task(base, test_patch, gold_patch)])
        rc, data, _, err = run(LIVE, *_base_args(tasks, Path(tmp) / "out",
                                                 Path(tmp) / "sources",
                                                 "gold"),
                               "--f2p-only")
        self.assertEqual(rc, 0, (str(data)[:300] + err[-500:]))
        self.assertEqual(data["f2p_passed"], 1)
        self.assertEqual(data["resolved"], 0, "部分口径不得计 resolved")


class TestDepth1Rescue(unittest.TestCase):
    """round-82：depth-1 单提交救援取法（r66/r81 实测取法产品化）。"""

    def _load_driver(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("live_sample_ut", LIVE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_bare_repo(self, root):
        work = root / "src"
        work.mkdir(parents=True)
        for args in (["init", "-q"], ["config", "user.email", "t@t"],
                     ["config", "user.name", "t"],
                     ["config", "commit.gpgsign", "false"]):
            subprocess.run(["git", "-C", str(work)] + args, check=True,
                           capture_output=True)
        (work / "f.txt").write_text("v1\n", encoding="utf-8")
        for args in (["add", "-A"], ["commit", "-qm", "c1"]):
            subprocess.run(["git", "-C", str(work)] + args, check=True,
                           capture_output=True)
        sha = subprocess.run(["git", "-C", str(work), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        bare = root / "remote.git"
        subprocess.run(["git", "clone", "--quiet", "--bare", str(work),
                        str(bare)], check=True, capture_output=True)
        return bare, sha

    def test_depth1_rescue_fetches_single_commit(self):
        mod = self._load_driver()
        tmp = Path(tmpspace.create(prefix="depth1-rescue-"))
        self.addCleanup(tmpspace.release, tmp)
        bare, sha = self._make_bare_repo(Path(tmp))
        dest = Path(tmp) / "dest" / "repo"
        ok = mod._depth1_rescue(bare.as_uri(), dest, sha, 120,
                                {"GIT_TERMINAL_PROMPT": "0"})
        self.assertTrue(ok, "file:// 单提交救援应成功")
        self.assertTrue(mod._git_has_commit(dest, sha))

    def test_depth1_rescue_missing_sha_fails_clean(self):
        mod = self._load_driver()
        tmp = Path(tmpspace.create(prefix="depth1-rescue-miss-"))
        self.addCleanup(tmpspace.release, tmp)
        bare, _ = self._make_bare_repo(Path(tmp))
        dest = Path(tmp) / "dest" / "repo"
        ok = mod._depth1_rescue(bare.as_uri(), dest, "0" * 40, 60,
                                {"GIT_TERMINAL_PROMPT": "0"})
        self.assertFalse(ok, "不存在的 sha 必须干净失败返回 False")




class TestRuntestsDocstringParsing(unittest.TestCase):
    """r107：unittest -v 2 docstring 折行格式的判分补齐（11087 实踩）。"""

    def _judge(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ls_ut", ROOT / "skills" / "eval-harness" / "scripts"
            / "live-sample.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._judge_django_runtests

    def test_docstring_wrapped_ok(self):
        judge = self._judge()
        out = ("test_a (m.C.test_a)" + chr(10)
               + "Docstring first line ... ok" + chr(10)
               + "test_b (m.C.test_b) ... ok" + chr(10)
               + "test_c (m.C.test_c)" + chr(10)
               + "doc ... ERROR" + chr(10))
        r = judge(out, ["test_a (m.C)", "test_b (m.C)", "test_c (m.C)"])
        f = r["fail_to_pass"]
        self.assertEqual(f["passed"], 2)
        self.assertEqual(f["missing"], [])
        self.assertEqual(f["statuses"]["test_c (m.C)"], "FAILED")

    def test_single_line_still_ok(self):
        judge = self._judge()
        r = judge("test_a (m.C.test_a) ... ok" + chr(10), ["test_a (m.C)"])
        self.assertEqual(r["fail_to_pass"]["passed"], 1)




class TestSbcliExport(unittest.TestCase):
    """r111 P0-1：--export-sbcli 导出通路契约。"""

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ls_ut2", ROOT / "skills" / "eval-harness" / "scripts"
            / "live-sample.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_export_states_and_patch(self):
        import types
        mod = self._mod()
        tmp = Path(tmpspace.create(prefix="sbcli-"))
        self.addCleanup(tmpspace.release, tmp)
        work = tmp / "out" / "work" / mod._short("a|predictions") / "tests"
        work.mkdir(parents=True)
        (work / "candidate.patch").write_text("diff --git a/x b/x" + chr(10),
                                              encoding="utf-8")
        argv = types.SimpleNamespace(export_sbcli=str(tmp / "pred.jsonl"),
                                     out=str(tmp / "out"))
        current = [
            {"instance_id": "a", "key": "a|predictions",
             "mode": "predictions", "state": "f2p_passed"},
            {"instance_id": "b", "key": "b|predictions",
             "mode": "predictions", "state": "unresolved"},
        ]
        info = mod._export_sbcli(argv, current)
        self.assertEqual(info["n"], 1)
        self.assertEqual(info["missing_patch"], [])
        rows = [json.loads(l) for l in
                (tmp / "pred.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["instance_id"], "a")
        self.assertIn("model_patch", rows[0])
        self.assertEqual(info["states"]["a"], "f2p_passed")
        self.assertEqual(info["states"]["b"], "unresolved")

    def test_export_missing_patch_listed(self):
        import types
        mod = self._mod()
        tmp = Path(tmpspace.create(prefix="sbcli2-"))
        self.addCleanup(tmpspace.release, tmp)
        argv = types.SimpleNamespace(export_sbcli=str(tmp / "p.jsonl"),
                                     out=str(tmp / "out"))
        current = [{"instance_id": "a", "key": "a|predictions",
                    "mode": "predictions", "state": "resolved"}]
        info = mod._export_sbcli(argv, current)
        self.assertEqual(info["n"], 0)
        self.assertEqual(info["missing_patch"], ["a"])

    def test_export_disabled_by_default(self):
        import types
        mod = self._mod()
        argv = types.SimpleNamespace(export_sbcli="", out="x")
        self.assertIsNone(mod._export_sbcli(argv, []))


if __name__ == "__main__":
    unittest.main()


class TestDjangoNodeConversion(unittest.TestCase):
    """django-runner 节点格式转换（round-101，解锁 verified django 系）。"""

    def _load(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("live_sample_dj", LIVE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_django_node_candidates(self):
        mod = self._load()
        cands = mod._django_node_candidates(
            "test_count_distinct_expression (aggregation.tests.AggregateTestCase)")
        self.assertEqual(
            cands,
            ["aggregation/tests.py::AggregateTestCase::test_count_distinct_expression",
             "tests/aggregation/tests.py::AggregateTestCase::test_count_distinct_expression",
             "aggregation/tests.py::AggregateTestCase::test_count_distinct_expression"])
        self.assertEqual(mod._django_node_candidates(
            "tests/test_x.py::test_plain"), [])

    def test_normalize_converts_by_file_existence(self):
        import tmpspace
        mod = self._load()
        tmp = Path(tmpspace.create(prefix="dj-conv-"))
        self.addCleanup(tmpspace.release, tmp)
        (tmp / "tests" / "aggregation").mkdir(parents=True)
        (tmp / "tests" / "aggregation" / "tests.py").write_text(
            "", encoding="utf-8")
        task = {"fail_to_pass": [
            "test_count_distinct_expression (aggregation.tests.AggregateTestCase)",
            "tests/test_x.py::test_plain"], "pass_to_pass": []}
        task2, n = mod._normalize_django_nodes(task, tmp)
        self.assertEqual(n, 1)
        self.assertEqual(
            task2["fail_to_pass_pytest"][0],
            "tests/aggregation/tests.py::AggregateTestCase"
            "::test_count_distinct_expression")
        self.assertEqual(task2["fail_to_pass_pytest"][1],
                         "tests/test_x.py::test_plain")
        self.assertEqual(
            task2["fail_to_pass"][0],
            "test_count_distinct_expression "
            "(aggregation.tests.AggregateTestCase)",
            "原单保留（runtests 口径直接吃原标签）")

    def test_normalize_keeps_unresolvable(self):
        import tmpspace
        mod = self._load()
        tmp = Path(tmpspace.create(prefix="dj-conv2-"))
        self.addCleanup(tmpspace.release, tmp)
        task = {"fail_to_pass": ["test_a (no.such.module.Case)"],
                "pass_to_pass": []}
        task2, n = mod._normalize_django_nodes(task, tmp)
        self.assertEqual(n, 0)
        self.assertEqual(task2["fail_to_pass"],
                         ["test_a (no.such.module.Case)"])
