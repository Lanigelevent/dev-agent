# -*- coding: utf-8 -*-
"""tests/test_scripts_reviewbench.py — ReviewBench 与发布：TestReviewBenchImport / TestReviewBenchEval / TestReleaseGate（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
from _scripts_common import _git
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestReviewBenchImport(unittest.TestCase):
    """ReviewBench 导入器契约：golden 命名、lang 过滤、offline 不触网。"""

    def _corpus(self, name):
        c = self.tmp / name
        (c / "corpus").mkdir(parents=True)
        (c / "golden").mkdir()
        (c / "diffs").mkdir()
        manifest = [
            {"repo": "https://github.com/own/alpha", "pr_number": 7,
             "base": "b" * 40, "head": "h7" * 20, "title": "fix alpha"},
            {"repo": "https://github.com/own/beta", "pr_number": 9,
             "base": "c" * 40, "head": "h9" * 20, "title": "fix beta"},
        ]
        (c / "corpus" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        (c / "golden" / "own_alpha_7-abcd1234.json").write_text(json.dumps({
            "pr_key": "own_alpha_7-abcd1234",
            "findings": [{"file": "src/a.py", "start_line": 1,
                          "end_line": 5, "message": "m1"}]},
            ensure_ascii=False), encoding="utf-8")
        (c / "golden" / "own_beta_9-efgh5678.json").write_text(json.dumps({
            "pr_key": "own_beta_9-efgh5678",
            "findings": [{"file": "web/b.js", "start_line": 2,
                          "end_line": 3, "message": "m2"}]},
            ensure_ascii=False), encoding="utf-8")
        # 预置 diff（offline 用）：alpha 有、beta 没有
        (c / "diffs" / "own_alpha_7-abcd1234.diff").write_text(
            "diff --git a/src/a.py b/src/a.py\n+changed\n", encoding="utf-8")
        return c

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rb-import-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_offline_assembles_with_predisk_diff(self):
        c = self._corpus("c1")
        out = c / "samples.json"
        rc, data, _, _ = run(SCRIPTS["reviewbench-import.py"],
                             "--corpus", str(c), "--out", str(out),
                             "--offline")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["samples"], 1)  # beta 无 diff，offline 跳过
        self.assertEqual(data["offline_missing"], 1)
        s = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(s[0]["sample_id"], "own_alpha_7-abcd1234")
        self.assertEqual(s[0]["fix_commit"], "h7" * 20)
        self.assertEqual(s[0]["expect_findings"], 1)
        self.assertEqual(s[0]["defect_class"], "reviewbench")

    def test_lang_filter(self):
        c = self._corpus("c2")
        out = c / "samples.json"
        rc, data, _, _ = run(SCRIPTS["reviewbench-import.py"],
                             "--corpus", str(c), "--out", str(out),
                             "--offline", "--lang", ".js")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["samples"], 0)  # beta 是 .js 但无 diff
        self.assertEqual(data["skipped_lang"], 1)  # alpha 纯 .py 被过滤

    def test_bad_manifest_rc1(self):
        c = self.tmp / "c3"
        c.mkdir()
        rc, data, _, _ = run(SCRIPTS["reviewbench-import.py"],
                             "--corpus", str(c), "--out",
                             str(c / "s.json"), "--offline")
        self.assertEqual(rc, 1)
        self.assertFalse(data["ok"])


class TestReviewBenchEval(unittest.TestCase):
    """ReviewBench 评测适配器契约：golden gt 提取、judge 数学、host 等待/续跑。"""

    def _corpus(self, name):
        """合成迷你语料：一个样本，golden 三条标注（tp / fp / 非 introduced）。"""
        c = self.tmp / name
        (c / "golden").mkdir(parents=True)
        (c / "diffs").mkdir()
        diff = "\n".join([
            "diff --git a/src/pay.py b/src/pay.py",
            "--- a/src/pay.py",
            "+++ b/src/pay.py",
            "@@ -0,0 +1,5 @@",
            "+def processPayment(userId, amount):",
            "+    # processPayment helper comment",
            "+    ledger.record(userId, amount)",
            "+    auditLogger.commit(userId)",
            "+    return amount",
            "diff --git a/docs/readme.md b/docs/readme.md",
            "--- a/docs/readme.md",
            "+++ b/docs/readme.md",
            "@@ -0,0 +1,2 @@",
            "+# just documentation filler",
            "+plain text",
        ]) + "\n"
        (c / "diffs" / "own_alpha_7-abcd1234.diff").write_text(diff,
                                                               encoding="utf-8")
        golden = {"pr_key": "own_alpha_7-abcd1234", "findings": [
            {"file": "src/pay.py", "start_line": 1, "end_line": 5,
             "tp_fp": "tp", "scope": "introduced-by-pr"},
            {"file": "src/pay.py", "start_line": 1, "end_line": 5,
             "tp_fp": "fp", "scope": "introduced-by-pr"},
            {"file": "src/pay.py", "start_line": 1, "end_line": 5,
             "tp_fp": "tp", "scope": "pre-existing"},
            {"file": "src/missing.py", "start_line": 1, "end_line": 3,
             "tp_fp": "tp", "scope": "introduced-by-pr"},
        ]}
        (c / "golden" / "own_alpha_7-abcd1234.json").write_text(
            json.dumps(golden), encoding="utf-8")
        samples = [{"sample_id": "own_alpha_7-abcd1234",
                    "diff_path": str(c / "diffs" / "own_alpha_7-abcd1234.diff"),
                    "expect_findings": 3, "title": "t"}]
        (c / "samples-py.json").write_text(json.dumps(samples),
                                           encoding="utf-8")
        return c

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rb-eval-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_prepare_gt_extracts_tp_introduced_only(self):
        # gt 只取 tp×introduced-by-pr 的标注区间 + 行：fp 与 pre-existing 剔除、
        # 注释行剔除、关键词剔除；区间与 diff 零交集的标注进 unmatched
        c = self._corpus("p1")
        out = self.tmp / "p1-out"
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "prepare",
                             "--corpus", str(c), "--out", str(out))
        self.assertEqual(rc, 0, data)
        m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["manifest"]
        self.assertEqual(len(m), 1)
        e = m[0]
        self.assertFalse(e["weak"])
        self.assertEqual(e["golden_tp"], 1, "只有 tp×introduced 那条区间命中 + 行")
        self.assertEqual(e["golden_unmatched"], 1, "missing.py 区间零交集须记 unmatched")
        for tok in ("processPayment", "ledger", "auditLogger", "userId"):
            self.assertIn(tok, e["gt"])
        self.assertNotIn("helper", e["gt"], "纯注释行不进 gt")
        self.assertNotIn("import", e["gt"], "关键词不进 gt")
        self.assertNotIn("documentation", e["gt"], "无关文件的 + 行不进 gt")

    def test_judge_math_and_weak_exclusion(self):
        # 命中判定：blob 提到 >=2 个 gt 标识符算 hit；weak 剔除分母；
        # recall=hits/valid、precision=grounded/claimed
        c = self._corpus("j1")
        out = self.tmp / "j1-out"
        rc, _, _, _ = run(SCRIPTS["reviewbench-eval.py"], "prepare",
                          "--corpus", str(c), "--out", str(out))
        self.assertEqual(rc, 0)
        findings = {"samples": {
            "own_alpha_7-abcd1234": [
                {"loc": "src/pay.py:1", "desc": "processPayment 与 ledger 记录无审计",
                 "evidence": "ledger.record"},
            ]}}
        fpath = out / "findings.json"
        fpath.write_text(json.dumps(findings), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "judge",
                             "--findings", str(fpath),
                             "--prepared", str(out / "manifest.json"))
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["claimed"], 1)
        self.assertEqual(data["grounded"], 1)
        self.assertEqual(data["recall"], 1.0)
        self.assertEqual(data["precision"], 1.0)
        # 弱样本变体：gt<2 时剔除分母，weak 列表可见
        g = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        g["manifest"][0]["gt"] = ["onlyOne"]
        (out / "manifest.json").write_text(json.dumps(g), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "judge",
                             "--findings", str(fpath),
                             "--prepared", str(out / "manifest.json"))
        self.assertEqual(rc, 0)
        self.assertEqual(data["valid_samples"], 0)
        self.assertEqual(data["weak_samples"], 1)
        self.assertIsNone(data["recall"])

    def test_host_reviewer_pauses_then_resumes(self):
        # 宿主文件协议全环：无响应 rc=1 + prompt 落盘；填 response 后重跑命中缓存
        c = self._corpus("h1")
        out = self.tmp / "h1-out"
        env = {"CRA_LLM_PROVIDER": "host"}
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "run",
                             "--corpus", str(c), "--out", str(out),
                             "--reviewer", "host", env_extra=env)
        self.assertEqual(rc, 1, "无宿主响应必须 WAIT_HOST_LLM（rc=1）")
        self.assertTrue(data.get("wait_host_llm"))
        prompt_path = Path(data["prompt"])
        response_path = Path(data["response"])
        self.assertTrue(prompt_path.is_file(), "prompt 必须落盘等宿主填写")
        self.assertFalse(response_path.exists())
        response_path.write_text(json.dumps([
            {"loc": "src/pay.py:1", "desc": "processPayment 未校验 userId",
             "evidence": "ledger.record(userId)", "severity": "高",
             "confidence": "高", "cause": "c", "fix": "f"},
        ]), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "run",
                             "--corpus", str(c), "--out", str(out),
                             "--reviewer", "host", env_extra=env)
        self.assertEqual(rc, 0, data)
        f = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual(f["reviewer"], "host")
        self.assertEqual(len(f["samples"]["own_alpha_7-abcd1234"]), 1)
        self.assertEqual(f["samples"]["own_alpha_7-abcd1234"][0]["engine"], "host")

    def test_deterministic_reviewer_runs_without_repo(self):
        # PR diff 直接可扫：不需要克隆样本仓库（ReviewBench 语料的接入前提）
        c = self._corpus("d1")
        out = self.tmp / "d1-out"
        rc, data, _, _ = run(SCRIPTS["reviewbench-eval.py"], "run",
                             "--corpus", str(c), "--out", str(out))
        self.assertEqual(rc, 0, data)
        f = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        self.assertEqual(f["reviewer"], "deterministic")
        self.assertIn("own_alpha_7-abcd1234", f["samples"])


class TestReleaseGate(unittest.TestCase):
    """发布闸（ROADMAP 3.5 / D-035）：版本同步 / 外部门禁 / 双跑 / git 状态。

    夹具是一个最小「可发布仓」：六处版本同值 + 四只假门禁脚本（真门禁的
    判据由各自契约覆盖，这里只验发布闸的接线）+ 两跑全绿日志 + 干净树。
    反向验证逐项造违例（版本漂移 / 日志红 / 计数不符 / 同一日志两份 / 脏树 /
    tag 不符或已存在 / 外部门禁红 / 未知检查 id），确认每一项都能单独拉开闸。
    """

    def setUp(self):
        self.d = FIXTURE["tmp"] / ("release-" + self.id().split(".")[-1])
        self.d.mkdir(exist_ok=True)

    def _repo(self, gate_rc=0):
        version = "1.58.0"
        root = self.d / "repo"
        root.mkdir()
        files = {
            ".zcode-plugin/plugin.json": json.dumps({"version": version}),
            "pyproject.toml": '[project]\nname = "dev-agent"\nversion = "%s"\n'
                              % version,
            "mcp/review_mcp.py":
                'SERVER_INFO = {"name": "dev-agent", "version": "%s"}\n'
                % version,
            "README.md":
                "# dev-agent\n\n**版本 %s**（真值源 "
                ".zcode-plugin/plugin.json）\n" % version,
            "docs/DEVELOPMENT.md":
                "## 8. 版本与发布流程\n\n1. 版本唯一事实源是 "
                "`.zcode-plugin/plugin.json` 的 `version`（当前 %s）；\n"
                % version,
            "BASELINE.md": "2026-10-01 初版：version 升 **%s**，测试 1→2。\n"
                           % version,
            "tests/test_dummy.py":
                "import unittest\n\n\nclass T(unittest.TestCase):\n"
                "    def test_a(self):\n        self.assertTrue(True)\n\n"
                "    def test_b(self):\n        self.assertEqual(1, 1)\n",
        }
        for name, text in files.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        scripts = root / "skills" / "self-iteration" / "scripts"
        scripts.mkdir(parents=True)
        stub = ("import json, sys\nprint(json.dumps({'ok': True}))\n"
                "sys.exit(%d)\n" % gate_rc)
        for name in ("doc-freshness.py", "doc-drift.py", "secret-scan.py",
                     "license-check.py"):
            (scripts / name).write_text(stub, encoding="utf-8", newline="\n")
        logs = root / "logs"
        logs.mkdir()
        self.log1 = logs / "run1.log"
        self.log2 = logs / "run2.log"
        green = "..\n" + "-" * 70 + "\nRan 2 tests in 0.010s\n\nOK\n"
        for path in (self.log1, self.log2):
            path.write_text(green, encoding="utf-8", newline="\n")
        _git(root, ["init", "-q"])
        _git(root, ["symbolic-ref", "HEAD", "refs/heads/main"])
        _git(root, ["config", "user.name", "release"])
        _git(root, ["config", "user.email", "release@local"])
        _git(root, ["add", "-A"])
        _git(root, ["commit", "-q", "-m", "init"])
        return root

    def _gate(self, root, *args):
        return run(SCRIPTS["release-gate.py"], "--root", root, *args)

    def test_ready_release_all_green_with_evidence(self):
        root = self._repo()
        out = self.d / "evidence" / "release-gate.json"
        rc, data, stdout, _ = self._gate(
            root, "--tag", "v1.58.0",
            "--suite-log", self.log1, "--suite-log", self.log2,
            "--out", out)
        self.assertEqual(rc, 0, "%r %s" % (data.get("failed"), stdout[:500]))
        self.assertTrue(data["ok"])
        self.assertFalse(data["partial"])
        self.assertEqual([c["id"] for c in data["checks"]],
                         ["version_sync", "doc_freshness", "doc_drift",
                          "secret_scan", "license_check", "suite_double_run",
                          "git_state"])
        self.assertEqual(data["failed"], [])
        self.assertEqual(data["release"]["version"], "1.58.0")
        self.assertTrue(data["release"]["tag_checked"])
        suite = [c for c in data["checks"]
                 if c["id"] == "suite_double_run"][0]
        self.assertEqual(suite["expected_tests"], 2)
        self.assertEqual([r["ran"] for r in suite["runs"]], [2, 2])
        self.assertEqual([r["mode"] for r in suite["runs"]],
                         ["reuse", "reuse"])
        saved = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["release"]["tag"], "v1.58.0")

    def test_version_sync_blocks_drift_and_bad_semver(self):
        root = self._repo()
        py = root / "pyproject.toml"
        py.write_text(py.read_text(encoding="utf-8").replace(
            'version = "1.58.0"', 'version = "1.58.1"'),
            encoding="utf-8", newline="\n")
        rc, data, out, _ = self._gate(root, "--only", "version_sync")
        self.assertEqual(rc, 1, out[:400])
        self.assertEqual(data["failed"], ["version_sync"])
        self.assertIn("pyproject.toml",
                      " ".join(data["checks"][0]["errors"]))
        plugin = root / ".zcode-plugin" / "plugin.json"
        plugin.write_text('{"version": "1.58"}', encoding="utf-8",
                          newline="\n")
        rc, data, _, _ = self._gate(root, "--only", "version_sync")
        self.assertEqual(rc, 1)
        self.assertTrue(any("X.Y.Z" in e
                            for e in data["checks"][0]["errors"]))

    def test_suite_logs_red_mismatch_and_same_file(self):
        root = self._repo()
        self.log2.write_text("..\n" + "-" * 70 +
                             "\nRan 2 tests in 0.010s\n\nFAILED (failures=1)\n",
                             encoding="utf-8", newline="\n")
        rc, data, out, _ = self._gate(root, "--only", "suite_double_run",
                                      "--suite-log", self.log1,
                                      "--suite-log", self.log2)
        self.assertEqual(rc, 1, out[:400])
        self.assertEqual(data["failed"], ["suite_double_run"])
        self.assertFalse(data["checks"][0]["runs"][1]["green"])
        self.log2.write_text("..\n" + "-" * 70 +
                             "\nRan 3 tests in 0.010s\n\nOK\n",
                             encoding="utf-8", newline="\n")
        rc, data, _, _ = self._gate(root, "--only", "suite_double_run",
                                    "--suite-log", self.log1,
                                    "--suite-log", self.log2)
        self.assertEqual(rc, 1)
        self.assertTrue(any("≠ 期望" in e
                            for e in data["checks"][0]["errors"]))
        rc, data, _, _ = self._gate(root, "--only", "suite_double_run",
                                    "--suite-log", self.log1,
                                    "--suite-log", self.log1)
        self.assertEqual(rc, 2)
        rc, data, _, _ = self._gate(root, "--only", "suite_double_run",
                                    "--suite-log", self.log1,
                                    "--suite-log", root / "nope.log")
        self.assertEqual(rc, 2)

    def test_external_gate_red_propagates(self):
        root = self._repo()
        (root / "skills" / "self-iteration" / "scripts" /
         "doc-drift.py").write_text(
            "import json, sys\nprint(json.dumps({'ok': False}))\n"
            "sys.exit(1)\n", encoding="utf-8", newline="\n")
        rc, data, out, _ = self._gate(root, "--only", "doc_drift")
        self.assertEqual(rc, 1, out[:400])
        self.assertEqual(data["failed"], ["doc_drift"])
        self.assertEqual(data["checks"][0]["rc"], 1)

    def test_git_state_dirty_branch_and_tag_rules(self):
        root = self._repo()
        (root / "untracked.txt").write_text("x", encoding="utf-8")
        rc, data, _, _ = self._gate(root, "--only", "git_state")
        self.assertEqual(rc, 1)
        self.assertFalse(data["checks"][0]["clean"])
        (root / "untracked.txt").unlink()
        rc, data, _, _ = self._gate(root, "--only", "git_state",
                                    "--branch", "develop")
        self.assertEqual(rc, 1)
        rc, data, _, _ = self._gate(root, "--only", "git_state",
                                    "--tag", "v9.9.9")
        self.assertEqual(rc, 1)
        _git(root, ["tag", "v1.58.0"])
        rc, data, _, _ = self._gate(root, "--only", "git_state",
                                    "--tag", "v1.58.0")
        self.assertEqual(rc, 1)
        self.assertTrue(data["checks"][0]["tag_exists"])
        _git(root, ["tag", "-d", "v1.58.0"])
        rc, data, out, _ = self._gate(root, "--only", "git_state",
                                      "--tag", "v1.58.0")
        self.assertEqual(rc, 0, out[:400])

    def test_run_suite_mode_executes_twice_and_writes_logs(self):
        root = self._repo()
        log_dir = self.d / "logdir"
        rc, data, out, _ = self._gate(root, "--only", "suite_double_run",
                                      "--run-suite",
                                      "--suite-log-dir", log_dir)
        self.assertEqual(rc, 0, out[:500])
        suite = data["checks"][0]
        self.assertEqual(suite["mode"], "executed")
        self.assertEqual([r["ran"] for r in suite["runs"]], [2, 2])
        self.assertEqual([r["mode"] for r in suite["runs"]],
                         ["executed", "executed"])
        self.assertTrue((log_dir / "release-gate-run1.log").is_file())
        self.assertTrue((log_dir / "release-gate-run2.log").is_file())

    def test_only_rejects_unknown_id(self):
        root = self._repo()
        rc, data, _, _ = self._gate(root, "--only", "bogus")
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
