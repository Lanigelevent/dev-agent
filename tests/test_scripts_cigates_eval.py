# -*- coding: utf-8 -*-
"""tests/test_scripts_cigates_eval.py — CI 门禁与评测链：TestCiGates / TestEval（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
from _scripts_common import _git
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestCiGates(unittest.TestCase):
    """CI 工程门禁（ROADMAP 3.3/3.4）：覆盖率基线 / 凭据形态 / 许可证清单。"""

    def setUp(self):
        self.d = FIXTURE["tmp"] / ("cigate-" + self.id().split(".")[-1])
        self.d.mkdir(exist_ok=True)

    # ---- coverage-gate ----
    def _baseline(self, **over):
        base = {
            "schema": "coverage-baseline/1",
            "generated_at": "2026-10-29T00:00:00+08:00",
            "scope": {"source": ["skills", "llm", "agent"],
                      "tests": ["test_agent.py"], "python": "3.12.13",
                      "platform": "win32"},
            "tolerance_pct": 0.5, "overall_pct": 62.5,
            "files": {"agent/repo_map.py": {"pct": 80.0, "statements": 100,
                                            "covered": 80},
                      "llm/provider.py": {"pct": 90.0, "statements": 50,
                                          "covered": 45}},
            "platform_optional": [],
        }
        base.update(over)
        path = self.d / "baseline.json"
        path.write_text(json.dumps(base, ensure_ascii=False),
                        encoding="utf-8")
        return path

    def _measured(self, files, overall):
        path = self.d / "measured.json"
        path.write_text(json.dumps({"files": files, "overall_pct": overall},
                                   ensure_ascii=False), encoding="utf-8")
        return path

    def test_coverage_check_pass_tolerance_and_regression(self):
        base = self._baseline()
        good = {"agent/repo_map.py": {"pct": 79.6},
                "llm/provider.py": {"pct": 90.0}}
        rc, data, _, _ = run(SCRIPTS["coverage-gate.py"], "check",
                             "--root", self.d, "--baseline", base,
                             "--measured", self._measured(good, 62.2))
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["state"], "PASS")
        # 超过容差的下降必须抓住（80 → 79.0，降 1.0pp > 0.5）
        bad = {"agent/repo_map.py": {"pct": 79.0},
               "llm/provider.py": {"pct": 90.0}}
        rc, data, _, _ = run(SCRIPTS["coverage-gate.py"], "check",
                             "--root", self.d, "--baseline", base,
                             "--measured", self._measured(bad, 62.5))
        self.assertEqual(rc, 1)
        self.assertEqual(data["regressions"][0]["file"], "agent/repo_map.py")
        # 基线内文件消失同样判失败（不许跳过）
        gone = {"llm/provider.py": {"pct": 90.0}}
        rc, data, _, _ = run(SCRIPTS["coverage-gate.py"], "check",
                             "--root", self.d, "--baseline", base,
                             "--measured", self._measured(gone, 90.0))
        self.assertEqual(rc, 1)
        self.assertEqual(data["missing"], ["agent/repo_map.py"])

    def test_coverage_input_errors(self):
        rc, data, _, _ = run(SCRIPTS["coverage-gate.py"], "check",
                             "--root", self.d,
                             "--baseline", self.d / "nope.json",
                             "--measured", self.d / "nope.json")
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])
        bad = self.d / "bad.json"
        bad.write_text(json.dumps({"schema": "other/1", "files": {}}),
                       encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["coverage-gate.py"], "check",
                             "--root", self.d, "--baseline", bad,
                             "--measured", bad)
        self.assertEqual(rc, 2)

    def test_coverage_default_tests_exist(self):
        """DEFAULT_TESTS 模式必须命中真实测试文件（round-88 拆分曾致
        coverage-gate 静默失效 rc=5，round-89 防再犯）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cov_gate_ut", SCRIPTS["coverage-gate.py"])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for pattern in mod.DEFAULT_TESTS:
            hits = sorted((ROOT / "tests").glob(pattern))
            self.assertTrue(
                hits,
                "DEFAULT_TESTS 模式 %r 零命中——测试布局变了必须同步 "
                "coverage-gate" % pattern)

    def test_coverage_repo_baseline_present(self):
        base = ROOT / "skills/self-iteration/coverage-baseline.json"
        self.assertTrue(base.is_file(), "覆盖率基线必须入仓")
        data = json.loads(base.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "coverage-baseline/1")
        self.assertTrue(data["files"])
        self.assertGreater(data["overall_pct"], 0)
        self.assertEqual(data["scope"]["source"], ["skills", "llm", "agent"])
        self.assertTrue(data["scope"]["tests"])

    # ---- secret-scan ----
    def _git_repo(self, files):
        repo = self.d / "repo"
        repo.mkdir()
        for name, text in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        _git(repo, ["init", "-q"])
        _git(repo, ["add", "-A"])
        return repo

    def _empty_allow(self):
        path = self.d / "allow-empty.json"
        path.write_text(json.dumps({"allowlist": []}), encoding="utf-8")
        return path

    def test_secret_scan_hits_redacted(self):
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        fake_pw = "super" + "-secret-value"
        repo = self._git_repo({
            "svc/conf.py": "AWS = '%s'\nDB = 'password = %s'\n"
                           % (fake_key, fake_pw),
        })
        rc, data, out, _ = run(SCRIPTS["secret-scan.py"], "--root", repo,
                               "--allowlist", self._empty_allow())
        self.assertEqual(rc, 1, out[:300])
        rules = {h["rule"] for h in data["hits"]}
        self.assertIn("aws-access-key", rules)
        self.assertIn("assigned-credential", rules)
        self.assertNotIn(fake_key, out)
        self.assertNotIn(fake_pw, out)
        self.assertIn("<redacted>", out)

    def test_secret_scan_allow_paths(self):
        fake_key = "AKIA" + "ABCDEFGHIJKLMNOP"
        repo = self._git_repo({
            "fixtures/fake.txt": "key = '%s'\n" % fake_key,
            "svc/marked.py": "K = '%s'  # secret-scan: allow\n" % fake_key,
        })
        allow = self.d / "allow.json"
        allow.write_text(json.dumps({"allowlist": [
            {"path": "fixtures/fake.txt", "rule": "aws-access-key",
             "reason": "测试假值，仅用于负样例"}]}, ensure_ascii=False),
            encoding="utf-8")
        rc, data, out, _ = run(SCRIPTS["secret-scan.py"], "--root", repo,
                               "--allowlist", allow)
        self.assertEqual(rc, 0, out[:300])
        self.assertEqual(data["hits"], [])
        self.assertEqual(len(data["allowlisted"]), 2)
        # 白名单缺 reason 是输入问题，不许静默放行
        bad = self.d / "bad-allow.json"
        bad.write_text(json.dumps({"allowlist": [
            {"path": "fixtures/fake.txt"}]}), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["secret-scan.py"], "--root", repo,
                             "--allowlist", bad)
        self.assertEqual(rc, 1)
        self.assertTrue(data["allowlist_problems"])

    def test_secret_scan_placeholders_pass(self):
        repo = self._git_repo({
            "svc/conf.py": "api_key = 'example-placeholder-value-1234'\n"
                           "token = '<redacted>'\n",
        })
        rc, data, out, _ = run(SCRIPTS["secret-scan.py"], "--root", repo,
                               "--allowlist", self._empty_allow())
        self.assertEqual(rc, 0, out[:300])
        self.assertEqual(data["hits"], [])

    def test_secret_scan_real_repo_clean(self):
        rc, data, out, _ = run(SCRIPTS["secret-scan.py"], "--root", ROOT)
        self.assertEqual(rc, 0, out[:400])
        self.assertEqual(data["state"], "PASS")
        self.assertEqual(data["hits"], [])
        self.assertGreater(data["scanned_files"], 300)

    # ---- license-check ----
    def _license_fixture(self, deps, dev, packages, name="lic"):
        root = self.d / name
        root.mkdir()
        (root / "pyproject.toml").write_text(
            "[project]\nname='x'\nversion='0.0.1'\n"
            "dependencies = %s\n[project.optional-dependencies]\n"
            "dev = %s\n" % (json.dumps(deps), json.dumps(dev)),
            encoding="utf-8")
        reg = self.d / (name + "-licenses.json")
        reg.write_text(json.dumps({
            "schema": "license-registry/1",
            "policy": {"import": ["MIT", "Apache-2.0"],
                       "test-only": ["MIT", "Apache-2.0", "MPL-2.0"],
                       "subprocess": ["MIT", "LGPL-2.1-only"]},
            "packages": packages}, ensure_ascii=False), encoding="utf-8")
        return root, reg

    def test_license_pass_and_violations(self):
        ok_packages = {
            "mitlib": {"license": "MIT", "mode": "import", "reason": "引擎"},
            "mpllib": {"license": "MPL-2.0", "mode": "test-only",
                       "reason": "测试依赖"},
        }
        root, reg = self._license_fixture(["mitlib>=1"], ["mpllib>=2"],
                                          ok_packages)
        rc, data, _, _ = run(SCRIPTS["license-check.py"], "--root", root,
                             "--registry", reg)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["state"], "PASS")
        self.assertEqual(len(data["checked"]), 2)
        # MPL 放 import 档 = G12 违规；GPL 任何档位都禁；模式不符要抓
        bad_packages = {
            "mitlib": {"license": "MIT", "mode": "test-only", "reason": "错档"},
            "mpllib": {"license": "MPL-2.0", "mode": "import", "reason": "错档"},
            "gpllib": {"license": "GPL-3.0", "mode": "import", "reason": "禁入"},
            "stale": {"license": "MIT", "mode": "import", "reason": "多余"},
        }
        root2, reg2 = self._license_fixture(
            ["mitlib>=1", "mpllib>=2", "gpllib>=1"], [], bad_packages,
            name="lic2")
        rc, data, _, _ = run(SCRIPTS["license-check.py"], "--root", root2,
                             "--registry", reg2)
        self.assertEqual(rc, 1)
        text = json.dumps(data["problems"], ensure_ascii=False)
        self.assertIn("模式", text)
        self.assertIn("MPL", text)
        self.assertIn("GPL", text)
        self.assertIn("stale", text)

    def test_license_input_errors(self):
        root = self.d / "empty"
        root.mkdir()
        rc, data, _, _ = run(SCRIPTS["license-check.py"], "--root", root)
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])

    def test_license_real_repo_pass(self):
        rc, data, out, _ = run(SCRIPTS["license-check.py"], "--root", ROOT)
        self.assertEqual(rc, 0, out[:400])
        self.assertEqual(data["state"], "PASS")
        self.assertEqual(data["problems"], [])
        modes = {(c["package"], c["mode"]) for c in data["checked"]}
        self.assertIn(("coverage", "test-only"), modes)
        self.assertIn(("hypothesis", "test-only"), modes)
        self.assertIn(("pynguin", "subprocess"), modes)


class TestEval(unittest.TestCase):
    def test_extract_window_ok_and_defect(self):
        rc, data, _, _ = run(SCRIPTS["extract-window.py"], "--repo", FIXTURE["repo"],
                             "--sha", FIXTURE["shaB"], "--file", "svc/payment.py")
        self.assertEqual(rc, 0)
        self.assertEqual(data["coverage"]["hunks"], data["coverage"]["covered"])
        self.assertTrue(all(re.match(r"^\d+: ", ln) for w in data["windows"] for ln in w["lines"]))
        rc, data, _, _ = run(SCRIPTS["extract-window.py"], "--repo", FIXTURE["repo"],
                             "--sha", FIXTURE["shaB"], "--file", "svc/payment.py",
                             "--max-window", 1)
        self.assertEqual(rc, 1)
        self.assertTrue(data["material_defect"])
        rc, _, _, _ = run(SCRIPTS["extract-window.py"], "--repo", FIXTURE["repo"],
                          "--sha", "deadbeef", "--file", "svc/payment.py")
        self.assertEqual(rc, 2)

    def test_forward_bench_judge(self):
        rc, data, _, _ = run(SCRIPTS["forward-bench.py"], "judge",
                             "--findings", FIXTURE["findings-per-sample"],
                             "--prepared", FIXTURE["manifest"], "--repo", FIXTURE["repo"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["recall"], 1.0)
        self.assertIn("valid_samples", data)
        self.assertEqual(data["weak_samples"], 0)

    def test_forward_bench_param_errors(self):
        rc, _, _, _ = run(SCRIPTS["forward-bench.py"], "judge", "--findings",
                          FIXTURE["findings-per-sample"], "--prepared",
                          FIXTURE["tmp"] / "no-manifest.json", "--repo", FIXTURE["repo"])
        self.assertEqual(rc, 2)
        rc, _, _, _ = run(SCRIPTS["forward-bench.py"])
        self.assertEqual(rc, 2)

    def test_run_regression_clean(self):
        rc, data, _, _ = run(SCRIPTS["run-regression.py"], "--repo", FIXTURE["repo"],
                             "--baseline", FIXTURE["baseline"], "--sample-size", 1)
        self.assertEqual(rc, 0)
        self.assertIn("valid_samples", data)
        self.assertFalse(data["suspect_identical"])

    def test_run_regression_detects_break(self):
        mismatch = json.loads(FIXTURE["baseline"].read_text(encoding="utf-8"))
        mismatch["sample_ids"] = ["deadbeef" + "0" * 33]
        b3 = FIXTURE["tmp"] / "baseline-mismatch.json"
        b3.write_text(json.dumps(mismatch, ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["run-regression.py"], "--repo", FIXTURE["repo"],
                             "--baseline", b3, "--sample-size", 1)
        self.assertEqual(rc, 1)
        self.assertTrue(data["suspect_identical"])
        rc, _, _, _ = run(SCRIPTS["run-regression.py"], "--repo", FIXTURE["repo"],
                          "--baseline", FIXTURE["tmp"] / "nope.json")
        self.assertEqual(rc, 2)

    def test_fingerprint_stable_and_sensitive(self):
        rc, f1, _, _ = run(SCRIPTS["fingerprint.py"], "--root", ROOT)
        rc2, f2, _, _ = run(SCRIPTS["fingerprint.py"], "--root", ROOT)
        self.assertEqual(rc, 0)
        self.assertEqual(f1["fingerprint"], f2["fingerprint"])
        proj = snapshot_repo(FIXTURE["tmp"] / "proj-copy")
        # 反向断言：快照只含源码树，运行产物目录不得混入（round-45 瘦身口径）
        for name in ("reports", "retro", "runs", "llm-tasks"):
            if (ROOT / name).exists():
                self.assertFalse((proj / name).exists(),
                                 "快照不应包含运行产物目录 %s" % name)
        data_dir = ROOT / "skills" / "eval-harness" / "data"
        if data_dir.exists():
            self.assertFalse((proj / "skills" / "eval-harness" / "data").exists(),
                             "快照不应包含 gate 语料目录")
        rc, f3, _, _ = run(SCRIPTS["fingerprint.py"], "--root", proj)
        self.assertEqual(f3["fingerprint"], f1["fingerprint"])
        agents = proj / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\n漂移测试行\n", encoding="utf-8")
        rc, f4, _, _ = run(SCRIPTS["fingerprint.py"], "--root", proj)
        self.assertNotEqual(f4["fingerprint"], f3["fingerprint"])

    def test_reviewbench_bridge(self):
        rc, data, _, _ = run(SCRIPTS["reviewbench-bridge.py"], "--input", FIXTURE["manifest"],
                             "--validate-only")
        self.assertEqual(rc, 0)
        out = FIXTURE["tmp"] / "cases.json"
        rc, data, _, _ = run(SCRIPTS["reviewbench-bridge.py"], "--input", FIXTURE["manifest"],
                             "--out", out)
        self.assertEqual(rc, 0)
        cases = json.loads(out.read_text(encoding="utf-8"))["cases"]
        self.assertTrue(all(c["id"] for c in cases))
        bad = FIXTURE["tmp"] / "bad-input.json"
        bad.write_text(json.dumps({"foo": 1}), encoding="utf-8")
        rc, _, _, _ = run(SCRIPTS["reviewbench-bridge.py"], "--input", bad)
        self.assertEqual(rc, 1)

    def test_collect_samples_bad_repo(self):
        rc, _, _, _ = run(SCRIPTS["collect-samples.py"], "--repo", FIXTURE["tmp"],
                          "--out", FIXTURE["tmp"] / "x.json")
        self.assertEqual(rc, 2)

    def test_precision_report_refuses_same_day_overwrite(self):
        """反向验证（round-30 同类排查 R4）：报告名只带日期，同日再跑必须被拒。

        结案证据引用的就是 `reports/precision-report-<date>.md` 这一份（round-6 的
        d8c4b419a461）；同一天重跑把数字盖掉等于改了证据。闸门必须在跑分**之前**——
        合成语料 + 引擎指纹要上百秒，不该为一次注定被拒的写入付这个钱。
        """
        import datetime
        out = FIXTURE["tmp"] / "precision-guard"
        out.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()
        targets = [out / ("precision-report-%s.md" % today),
                   out / ("precision-report-%s.json" % today)]
        sentinel = "当天已发布的那一份：不许被盖掉\n"
        for p in targets:
            p.write_text(sentinel, encoding="utf-8", newline="\n")
        rc, data, _, _ = run(SCRIPTS["precision-report.py"], "--count", "40",
                             "--out", out)
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("拒绝覆盖历史", data["error"])
        for p in targets:
            self.assertEqual(p.read_text(encoding="utf-8"), sentinel,
                             "被拒的这次一个字都不该动")
        # --force 时闸门确实放行：用不存在的 judge 触发**下一条**校验失败来证明
        rc, data, _, _ = run(SCRIPTS["precision-report.py"], "--count", "40",
                             "--out", out, "--judge", out / "no-such-judge.json",
                             "--force")
        self.assertEqual(rc, 2)
        self.assertIn("judge 文件不存在", data["error"],
                      "带 --force 仍报覆盖拒绝，说明闸门没被绕过")

    def test_precision_report_rejects_bad_cost_inputs_before_scoring(self):
        """成本/合并率输入先校验再跑分：坏输入必须秒回 exit 2（round-48）。

        反向验证锚：把校验块移回 synth 之后，本测试会在合成语料上耗上百秒
        （功能仍对，但纪律破了）——用耗时为锚不现实，故只钉「错误信息在
        stdout 且 rc=2」；校验位置由实现顺序保证。
        """
        out = FIXTURE["tmp"] / "precision-cost-inputs"
        out.mkdir(parents=True, exist_ok=True)
        bad_cost = out / "bad-cost.json"
        bad_cost.write_text(json.dumps({"kind": "agent-summary"}),
                            encoding="utf-8", newline="\n")
        rc, data, _, _ = run(SCRIPTS["precision-report.py"], "--count", "40",
                             "--out", out, "--cost-report", str(bad_cost))
        self.assertEqual(rc, 2)
        self.assertIn("成本报告非法", data["error"])
        bad_audit = out / "bad-audit.json"
        bad_audit.write_text(json.dumps({"metrics": {"reviewed": 20}}),
                             encoding="utf-8", newline="\n")
        rc, data, _, _ = run(SCRIPTS["precision-report.py"], "--count", "40",
                             "--out", out, "--merge-audit", str(bad_audit))
        self.assertEqual(rc, 2)
        self.assertIn("合并率抽检非法", data["error"])

    def test_deepswe_fetch_no_clone_missing_repo(self):
        """deepswe-fetch.py --no-clone 需 --repo-path，缺则 exit 2。"""
        rc, data, _, _ = run(SCRIPTS["deepswe-fetch.py"], "--output",
                             FIXTURE["tmp"] / "deepswe.jsonl", "--no-clone")
        self.assertEqual(rc, 2)

    def test_deepswe_fetch_no_clone_bad_path(self):
        """--no-clone --repo-path 不存在则 exit 2。"""
        rc, data, _, _ = run(SCRIPTS["deepswe-fetch.py"], "--output",
                             FIXTURE["tmp"] / "deepswe.jsonl", "--no-clone",
                             "--repo-path", FIXTURE["tmp"] / "no-such-repo")
        self.assertEqual(rc, 2)

    def test_deepswe_fetch_no_clone_reports_local_source(self):
        """--no-clone 时 source 必须是 local 且 degraded=true（降级如实记录）。

        反向验证的锚：修前实现直接回吐 argv.source（"github"）——用本地仓库
        跑却声称从 GitHub 拉的，假账。这里既钉实际来源，也钉请求来源保留。
        """
        work = FIXTURE["tmp"] / "deepswe-local"
        task_dir = work / "repo" / "tasks" / "demo-task"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.toml").write_text(
            '[metadata]\n'
            'task_id = "demo-task"\n'
            'language = "python"\n'
            'repository_url = "https://example.invalid/demo"\n'
            'base_commit_hash = "%s"\n'
            'category = "bug-fix"\n'
            'display_title = "Demo"\n' % ("0" * 40),
            encoding="utf-8", newline="\n")
        (task_dir / "instruction.md").write_text(
            "Fix the demo bug.\n", encoding="utf-8", newline="\n")
        out = work / "tasks.jsonl"
        rc, data, _, _ = run(SCRIPTS["deepswe-fetch.py"], "--output", out,
                             "--no-clone", "--repo-path", work / "repo")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["source"], "local")
        self.assertEqual(data["requested_source"], "github")
        self.assertTrue(data["degraded"])
        self.assertEqual(data["total"], 1)
        row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["id"], "demo-task")
        self.assertEqual(row["language"], "python")

    def test_deepswe_sample_missing_jsonl(self):
        """deepswe-sample.py 缺 --jsonl 文件则 exit 2。"""
        rc, data, _, _ = run(SCRIPTS["deepswe-sample.py"],
                             "--jsonl", FIXTURE["tmp"] / "no-such.jsonl",
                             "--out", FIXTURE["tmp"] / "deepswe-out",
                             "--dry-run")
        self.assertEqual(rc, 2)

    def test_deepswe_sample_dry_run_no_match(self):
        """--dry-run 过滤无匹配则 exit 2。"""
        rc, data, _, _ = run(SCRIPTS["deepswe-sample.py"],
                             "--jsonl", FIXTURE["tmp"] / "no-such.jsonl",
                             "--out", FIXTURE["tmp"] / "deepswe-out",
                             "--dry-run", "--lang", "cobol")
        self.assertEqual(rc, 2)

    def test_deepswe_sample_host_waiting_exit_1(self):
        """--host-loop：WAIT_HOST_LLM 记 waiting_host（非失败）并 exit=1。"""
        import json as _json
        work = FIXTURE["tmp"] / "deepswe-host"
        work.mkdir(parents=True, exist_ok=True)
        repo = work / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args,
                           shell=False, capture_output=True)
        sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             shell=False, capture_output=True, text=True,
                             encoding="utf-8").stdout.strip()
        tasks = work / "tasks.jsonl"
        tasks.write_text(_json.dumps({
            "id": "t-host-wait", "task": "给 a.py 的 x 常量加注释",
            "repo": str(repo), "base_commit": sha, "language": "python",
            "category": "bug", "test_command": "bash tests/test.sh",
            "docker_image": "demo/img", "task_dir": str(work),
        }) + "\n", encoding="utf-8")
        out = work / "out"
        rc, data, _, _ = run(SCRIPTS["deepswe-sample.py"],
                             "--jsonl", tasks, "--out", out,
                             "--limit", "1", "--no-eval", "--host-loop")
        self.assertEqual(rc, 1, "等待宿主回复属可处理状态，必须 exit=1")
        self.assertEqual(data["failed"], 0, "WAIT_HOST_LLM 不得记失败")
        self.assertEqual(data["waiting"], 1)
        row = data["results"][0]
        self.assertEqual(row["status"], "waiting_host")
        self.assertTrue(Path(row["llm_task"]).is_file(), "提示词文件应已写出")
        self.assertTrue(row["llm_response"].endswith(".response.md"))

    def test_deepswe_sample_failure_exit_1(self):
        """环境失败（base_commit 不存在）须 exit=1 并计入 failed（硬约束 3）。"""
        import json as _json
        work = FIXTURE["tmp"] / "deepswe-fail"
        work.mkdir(parents=True, exist_ok=True)
        repo = work / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args,
                           shell=False, capture_output=True)
        tasks = work / "tasks.jsonl"
        tasks.write_text(_json.dumps({
            "id": "t-bad-sha", "task": "noop", "repo": str(repo),
            "base_commit": "0" * 40, "language": "python",
            "category": "bug", "test_command": "bash tests/test.sh",
            "docker_image": "demo/img", "task_dir": str(work),
        }) + "\n", encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["deepswe-sample.py"],
                             "--jsonl", tasks, "--out", work / "out",
                             "--limit", "1", "--no-eval")
        self.assertEqual(rc, 1, "clone/checkout 失败必须 exit=1")
        self.assertEqual(data["failed"], 1)
        self.assertEqual(data["results"][0]["status"], "clone_failed")

    def test_deepswe_sample_malformed_jsonl_exit_2(self):
        """JSONL 行缺 id 属坏输入，须 exit 2。"""
        tasks = FIXTURE["tmp"] / "deepswe-bad.jsonl"
        tasks.write_text('{"language": "python"}\n', encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["deepswe-sample.py"],
                             "--jsonl", tasks,
                             "--out", FIXTURE["tmp"] / "deepswe-bad-out")
        self.assertEqual(rc, 2)
        self.assertIn("id", data["error"])


