# -*- coding: utf-8 -*-
"""tests/test_scripts_selfiter.py — 自迭代与优化：_docstring_flag_drift / TestSelfIteration / TestE2EChain / TestContracts / TestOptimizations（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


def _docstring_flag_drift(path):
    """返回脚本 docstring 里出现、但本脚本 argparse 未定义的旗标。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    doc = ast.get_docstring(tree) or ""
    doc_flags = set(re.findall(r"--[\w][\w-]*", doc))
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "add_argument" and node.args \
                and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            defined.add(node.args[0].value)
    return sorted(doc_flags - defined)


class TestSelfIteration(unittest.TestCase):
    def test_docstring_flags_subset_of_argparse(self):
        """flag 自检前移：docstring 只许引用本脚本已定义旗标（台账 8f17737808b1）。"""
        bad = ["%s: %s" % (name, drift)
               for name, path in SCRIPTS.items()
               for drift in [_docstring_flag_drift(path)] if drift]
        self.assertEqual(bad, [], "docstring 引用了未定义旗标")
        # 反向验证：造一个 docstring 引用外部旗标的脚本必须被抓
        probe = FIXTURE["tmp"] / "flag-gate.py"
        probe.write_text(
            '#!/usr/bin/env python3\n"""用法: py flag-gate.py --nope"""\n'
            'import argparse\np = argparse.ArgumentParser()\n'
            'p.add_argument("--ok")\n', encoding="utf-8")
        self.assertEqual(_docstring_flag_drift(probe), ["--nope"])

    def test_doc_drift_clean_on_self(self):
        # 行为覆盖探针锚点：compact-memory.py 与 memory_retrieval.py 在此被 tests/ 文本覆盖
        rc, data, _, _ = run(SCRIPTS["doc-drift.py"], "--root", ROOT)
        self.assertEqual(rc, 0, json.dumps(data["questions"], ensure_ascii=False)[:2000])
        self.assertEqual(len(data["questions"]), 15)

    def test_doc_drift_catches_injection(self):
        proj = snapshot_repo(FIXTURE["tmp"] / ("drift-copy-" + self.id().split(".")[-1]))
        skill = proj / "skills" / "risk-scoring" / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") +
                         "\n```bash\npython score.py --nonexistent-flag x\n```\n", encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["doc-drift.py"], "--root", proj)
        self.assertEqual(rc, 1)
        self.assertIn(10, data["failed"])

    def test_perspective_scan_self_check_and_scan(self):
        rc, data, _, _ = run(SCRIPTS["perspective-scan.py"], "--self-check")
        self.assertEqual(rc, 0)
        self.assertTrue(all(data["checks"].values()))
        bad_findings = FIXTURE["tmp"] / "p-findings.json"
        bad = list(FIXTURE["findings"]) + [
            {"loc": "svc/payment.py:3", "desc": "可变默认参数", "evidence": "cache={}",
             "cause": "短", "fix": "f"}]
        bad_findings.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["perspective-scan.py"], "--findings", bad_findings,
                             "--diff-file", FIXTURE["change.diff"])
        self.assertEqual(rc, 1)
        self.assertTrue(any(p["perspective"] == "因果一致性" for p in data["problems"]))
        rc, _, _, _ = run(SCRIPTS["perspective-scan.py"])
        self.assertEqual(rc, 2)

    def test_dead_code_scan_clean_and_catch(self):
        rc, data, _, _ = run(SCRIPTS["dead-code-scan.py"], "--root", ROOT)
        self.assertEqual(rc, 0, json.dumps(data["findings"], ensure_ascii=False))
        proj = FIXTURE["tmp"] / ("dead-copy-" + self.id().split(".")[-1])
        (proj / "skills" / "x" / "scripts").mkdir(parents=True)
        bad = "import os\nimport sys\nprint(sys.platform)\n"
        (proj / "skills" / "x" / "scripts" / "bad.py").write_text(bad, encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["dead-code-scan.py"], "--root", proj)
        self.assertEqual(rc, 1)
        self.assertTrue(any(f["kind"] == "unused_import" for f in data["findings"]))

    def test_session_probe_green(self):
        rc, data, _, _ = run(SCRIPTS["session-probe.py"], "--root", ROOT)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:800])
        self.assertTrue(data["all_green"])
        rc, _, _, _ = run(SCRIPTS["session-probe.py"], "--root", FIXTURE["tmp"] / "nope")
        self.assertEqual(rc, 2)

    def test_convergence_and_pick(self):
        m_ok = FIXTURE["tmp"] / "metrics-ok.json"
        m_ok.write_text(json.dumps({"tests_passed": True, "consistency_clean": True,
                                    "queue_empty": True, "metrics_stable": True}), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["convergence-check.py"], "--root", ROOT, "--metrics", m_ok)
        self.assertEqual(rc, 0)
        self.assertTrue(data["can_stop"])
        m_bad = FIXTURE["tmp"] / "metrics-bad.json"
        m_bad.write_text(json.dumps({"tests_passed": True, "consistency_clean": False,
                                     "queue_empty": True, "metrics_stable": True}), encoding="utf-8")
        rc, _, _, _ = run(SCRIPTS["convergence-check.py"], "--root", ROOT, "--metrics", m_bad)
        self.assertEqual(rc, 1)
        m_missing = FIXTURE["tmp"] / "metrics-missing.json"
        m_missing.write_text(json.dumps({"tests_passed": True}), encoding="utf-8")
        rc, _, _, _ = run(SCRIPTS["convergence-check.py"], "--root", ROOT, "--metrics", m_missing)
        self.assertEqual(rc, 2)
        items = [{"id": "a", "title": "A", "roi": 5, "evidence": "x.py:10", "deps": []},
                 {"id": "b", "title": "B", "roi": 5, "evidence": "short", "deps": []},
                 {"id": "c", "title": "C", "roi": 9, "evidence": "y.py:2", "deps": ["a"]}]
        ifile = FIXTURE["tmp"] / "items.json"
        ifile.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["pick-candidate.py"], "--items", ifile)
        self.assertEqual(rc, 0)
        self.assertEqual(data["ranked"][0]["id"], "c")
        self.assertFalse(data["ranked"][0]["deps_ok"])
        self.assertEqual(data["ranked"][1]["id"], "a")
        empty = FIXTURE["tmp"] / "items-empty.json"
        empty.write_text("[]", encoding="utf-8")
        rc, _, _, _ = run(SCRIPTS["pick-candidate.py"], "--items", empty)
        self.assertEqual(rc, 1)

    def test_e2e_check(self):
        rc, data, _, _ = run(SCRIPTS["e2e-check.py"])
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:800])
        self.assertTrue(data["ok"])


class TestE2EChain(unittest.TestCase):
    """七步链条：定档→边界→规则→材料→派发→评分→覆盖，产物逐级消费。"""

    def test_seven_step_chain(self):
        repo = FIXTURE["repo"]
        rng = "HEAD~2..HEAD~1"
        diff = FIXTURE["change.diff"]
        rc, pre, _, _ = run(SCRIPTS["preflight.py"], "--repo", repo, "--range", rng)
        self.assertEqual(rc, 0)
        self.assertEqual(pre["profile"], "S")
        rc, edges, _, _ = run(SCRIPTS["edge-detect.py"], "--repo", repo, "--range", rng)
        self.assertEqual(rc, 0)
        self.assertFalse(edges["any_found"])
        rc, rules, _, _ = run(SCRIPTS["deterministic-rules.py"], "--diff-file", diff)
        self.assertEqual(rc, 0)
        self.assertTrue(rules["findings"])
        findings_file = FIXTURE["tmp"] / "chain-findings.json"
        findings_file.write_text(json.dumps(rules["findings"], ensure_ascii=False), encoding="utf-8")
        rc, mat, _, _ = run(SCRIPTS["material-check.py"], "--diff-file", diff, "--symbol", "charge")
        self.assertEqual(rc, 0)
        self.assertEqual(mat["needed_context"]["level"], "A")
        rc, disp, _, _ = run(SCRIPTS["dispatch-plan.py"], "--diff", diff,
                             "--intent", "修复支付回调逻辑并补充校验")
        self.assertEqual(rc, 0)
        self.assertIn("回退风险与影响面", disp["enable_reasons"])
        rows = [{"name": "svc", "files": pre["files"], "added": pre["source_lines"],
                 "deleted": 0, "modules": 1, "callers": 0, "high_impact": [],
                 "history_3m": 0, "history_12m": 0}]
        payload = {"regions": rows,
                   "overall": {"files": pre["files"], "added": pre["source_lines"],
                               "deleted": 0, "modules": 1, "callers": 0,
                               "history_3m": 0, "history_12m": 0}}
        rc, risk, _, _ = run(SCRIPTS["score.py"], stdin=json.dumps(payload))
        self.assertEqual(rc, 0)
        self.assertEqual(risk["overall"]["level"], "低")
        rc, cov, _, _ = run(SCRIPTS["coverage.py"], "--findings", findings_file,
                            "--diff-file", diff)
        self.assertEqual(rc, 0)
        self.assertEqual(cov["covered_hunks"], cov["total_hunks"])
        self.assertTrue(cov["findings_seen"] >= len(rules["findings"]))


class TestContracts(unittest.TestCase):
    def test_all_scripts_exist(self):
        for name, path in SCRIPTS.items():
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("#!/usr/bin/env python3"), name)
            self.assertIn("退出码", text, name)

    def test_weights_pinned(self):
        src = (SCRIPTS["score.py"]).read_text(encoding="utf-8")
        self.assertIn('"scale": 0.3', src)
        self.assertIn('"coupling": 0.4', src)
        self.assertIn('"stability": 0.3', src)

    def test_redaction_contract(self):
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"], "--diff-file", FIXTURE["change.diff"])
        raw = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn(APIKEY, raw)

    def test_skill_md_line_baseline(self):
        baseline = (ROOT / "BASELINE.md").read_text(encoding="utf-8")
        for m in re.finditer(r"^-\s*([a-z-]+):\s*(\d+)\s*$", baseline, re.M):
            skill = m.group(1)
            sp = ROOT / "skills" / skill / "SKILL.md"
            self.assertTrue(sp.is_file(), skill)
            actual = len(sp.read_text(encoding="utf-8").splitlines())
            self.assertEqual(actual, int(m.group(2)), skill)


class TestOptimizations(unittest.TestCase):
    """2026-10-24 优化验收：误报清零、合成语料精度、编排器端到端、反馈闭环。"""

    def test_self_scan_zero_fp(self):
        """批扫口径（D-049 C）：一次子进程扫全部脚本，按文件逐段断言。"""
        files = [str(p) for p in SCRIPTS.values()]
        rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"],
                             *sum((["--file", f] for f in files), []))
        self.assertEqual(rc, 0)
        self.assertTrue(data.get("batch"))
        by_file = {r["file"]: r for r in data["results"]}
        for name, path in SCRIPTS.items():
            with self.subTest(script=name):
                r = by_file.get(str(path))
                self.assertIsNotNone(r, "缺结果段: %s" % name)
                self.assertEqual(r["rc"], 0, name)
                self.assertEqual(r["findings"], [], "%s 自扫出现误报" % name)

    def test_clean_and_defect_both_ways(self):
        d = FIXTURE["tmp"] / "fp-cases"
        d.mkdir(exist_ok=True)
        clean = {
            "c1_env.py": "import os\npassword = os.environ.get('PW', '')\n",
            "c2_with.py": "with open('a.txt') as fh:\n    data = fh.read()\n",
            "c3_lambda.py": "def run(items):\n    out = []\n"
                            "    for it in items:\n"
                            "        out.append(sorted(items, key=lambda x: x))\n"
                            "    return out\n",
            "c4_concat.py": "SECRET = 'a' + 'b' + 'c'\n",
        }
        defect = {
            "d1_creds.py": "import os\npassword = " + '"' + SECRET + '"\n',
            "d2_latebind.py": "def make():\n    fns = []\n    for i in range(3):\n"
                              "        fns.append(lambda: i)\n    return fns\n",
            "d3_open.py": "f = open('data.txt')\ndata = f.read()\n",
        }
        for name, src in clean.items():
            f = d / name
            f.write_text(src, encoding="utf-8")
            rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"], "--file", f)
            self.assertEqual(data["findings"], [], "%s 干净样例被误报" % name)
        for name, src in defect.items():
            f = d / name
            f.write_text(src, encoding="utf-8")
            rc, data, _, _ = run(SCRIPTS["deterministic-rules.py"], "--file", f)
            self.assertTrue(data["findings"], "%s 真缺陷未被抓住" % name)

    def test_synth_corpus_precision(self):
        corpus = FIXTURE["tmp"] / "corpus"
        rc, data, _, _ = run(SCRIPTS["forward-bench.py"], "synth", "--out", corpus, "--count", 20)
        self.assertEqual(rc, 0)
        rc, data, _, _ = run(SCRIPTS["forward-bench.py"], "fp", "--corpus", corpus)
        self.assertEqual(rc, 0)
        self.assertEqual(data["clean_fp"], 0)
        self.assertEqual(data["precision"], 1.0)
        self.assertGreaterEqual(data["recall_injected"], 0.8)

    def test_dispatch_security_dimension(self):
        rc, data, _, _ = run(SCRIPTS["dispatch-plan.py"], "--diff", FIXTURE["change.diff"])
        self.assertEqual(rc, 0)
        self.assertIn("安全与敏感信息", data["dimensions_enabled"])

    def test_findings_check_stdin(self):
        good = {"loc": "a.py:1", "desc": "d", "evidence": "e", "severity": "低",
                "confidence": "低", "cause": "完整因果链说明", "fix": "f"}
        rc, data, _, _ = run(SCRIPTS["findings-check.py"], "-", "--dimensions", "测试覆盖",
                             stdin=json.dumps({"findings": [good]}, ensure_ascii=False))
        self.assertEqual(rc, 0)

    def test_runner_e2e(self):
        out = FIXTURE["tmp"] / "runner-e2e"
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1", "--out", out, "--skip-probe")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:600])
        self.assertEqual(data["state"], "DONE")
        self.assertTrue(data["inline"], "编排器应产出行内评论")
        self.assertLessEqual(data["rounds_used"], int(json.loads(
            (ROOT / "agent.json").read_text(encoding="utf-8"))["args"]["max_total_rounds"]))
        raw = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(SECRET, raw)
        self.assertNotIn(APIKEY, raw)
        rc, _, _, _ = run(SCRIPTS["report-check.py"], data["report_path"])
        self.assertEqual(rc, 0)
        rc, _, _, _ = run(SCRIPTS["schema-check.py"], "--dir", data["run_dir"])
        self.assertEqual(rc, 0)
        run_dir = Path(data["run_dir"])
        for name in ("checkpoint.json", "step2_collect.json", "step3_risk.json", "totals.json"):
            self.assertTrue((run_dir / name).is_file(), name)
        totals = json.loads((run_dir / "totals.json").read_text(encoding="utf-8"))
        agent_args = json.loads((ROOT / "agent.json").read_text(encoding="utf-8"))["args"]
        self.assertEqual(totals["caps"]["max_total_rounds"], agent_args["max_total_rounds"])
        self.assertEqual(len(totals["rounds"]), data["rounds_used"])
        self.assertEqual(len(totals["steps"]), 11)
        self.assertEqual(totals["ledger"]["errors"], 0)
        self.assertTrue(totals["ledger"]["active"])
        # 统一事件账本（ROADMAP 3.1）：真 run 必须产出可校验、可重放的账本
        ledger = run_dir / "ledger.jsonl"
        self.assertTrue(ledger.is_file(), "runner 未产出 ledger.jsonl")
        rc_l, ver, _, _ = run(SCRIPTS["event-ledger.py"], "verify", "--ledger", ledger)
        self.assertEqual(rc_l, 0, json.dumps(ver, ensure_ascii=False)[:300])
        self.assertGreaterEqual(ver["records"], 10)
        rc_rp, rep, _, _ = run(SCRIPTS["event-ledger.py"], "replay", "--ledger", ledger,
                               "--root", ROOT, "--only", "script.score")
        self.assertEqual(rc_rp, 0, json.dumps(rep, ensure_ascii=False)[:400])
        self.assertEqual(rep["state"], "MATCH")
        self.assertEqual(rep["matched"], 1)
        ledger_text = ledger.read_text(encoding="utf-8")
        self.assertNotIn(SECRET, ledger_text, "账本含明文凭据（硬约束 5）")
        self.assertNotIn(APIKEY, ledger_text, "账本含明文凭据（硬约束 5）")
        self.assertIn("$REPO", ledger_text, "被审仓库路径应令牌化")
        self.assertNotIn(str(FIXTURE["repo"]), ledger_text, "绝对仓库路径未令牌化")
        # 成本账本（ROADMAP 3.2）：cost 块与 caps 逐项对账，check 必须 PASS
        cost = totals["cost"]
        self.assertGreater(cost["wall_sec"], 0)
        self.assertEqual(cost["rounds_used"], len(totals["rounds"]))
        self.assertEqual(cost["tokens_status"], "not_used")
        rows = {row["item"]: row for row in cost["budget"]}
        for item, cap_key in (("minutes", "max_review_minutes"),
                              ("rounds", "max_total_rounds"),
                              ("dynamic_dispatches", "max_dynamic_dispatches")):
            self.assertEqual(rows[item]["cap"], agent_args[cap_key], item)
            self.assertEqual(rows[item]["status"], "OK", item)
        self.assertEqual(rows["tokens"]["status"], "N/A")
        self.assertEqual(len(cost["steps"]), 11)
        self.assertGreater(cost["steps"][-1]["elapsed_sec"], 0)
        rc_c, cost_chk, _, _ = run(SCRIPTS["cost-ledger.py"], "check", "--dir", run_dir)
        self.assertEqual(rc_c, 0, json.dumps(cost_chk, ensure_ascii=False)[:400])
        self.assertEqual(cost_chk["state"], "PASS")
        rc2, data2, _, _ = run(SCRIPTS["runner.py"], "--resume", data["run_dir"])
        self.assertEqual(rc2, 0, json.dumps(data2, ensure_ascii=False)[:400])

    def test_runner_report_style_variant(self):
        """--report-style 契约（r122 补覆盖率漂移，r105 接线）：
        双闸通过后 report-<style>.md 必须落盘，内容非空且含输入 finding 定位。"""
        out = FIXTURE["tmp"] / "runner-style-engineering"
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1", "--out", out,
                             "--skip-probe",
                             "--report-style", "engineering")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:600])
        self.assertEqual(data["state"], "DONE")
        run_dir = Path(data["run_dir"])
        variant = run_dir / "report-engineering.md"
        self.assertTrue(variant.is_file(), "report-engineering.md 应落盘")
        text = variant.read_text(encoding="utf-8")
        self.assertGreater(len(text.strip()), 50, "engineering 变体不应为空壳")

    def test_runner_material_redacted_in_prompts(self):
        """反向验证（台账 5fc9903b1f38）：评审材料进 LLM prompt 前必须脱敏。

        host 协议逐问填答（每维度一问，无问题回 []），收束后全量扫描
        llm-tasks/*.prompt.md，明文凭据不得出现（硬约束 5）。
        """
        out = FIXTURE["tmp"] / "runner-host"
        env = {"CRA_LLM_PROVIDER": "host"}
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1", "--out", out,
                             "--skip-probe", "--reviewer", "both", env_extra=env)
        run_dir = None
        for _ in range(64):
            if rc == 0:
                break
            self.assertEqual(rc, 1, json.dumps(data, ensure_ascii=False)[:400])
            self.assertEqual(data["state"], "WAIT_HOST_LLM")
            run_dir = Path(data["llm_task"]).parents[1]
            prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
            self.assertNotIn(SECRET, prompt, "prompt 含明文凭据（硬约束 5）")
            self.assertNotIn(APIKEY, prompt, "prompt 含明文凭据（硬约束 5）")
            Path(data["llm_response"]).write_text("```json\n[]\n```",
                                                  encoding="utf-8", newline="\n")
            rc, data, _, _ = run(SCRIPTS["runner.py"], "--resume", str(run_dir),
                                 env_extra=env)
        self.assertEqual(rc, 0, "64 轮填答内未收束: %s"
                         % json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["state"], "DONE")
        self.assertIsNotNone(run_dir, "host 模式应至少征询一次")
        for f in (run_dir / "llm-tasks").glob("*.prompt.md"):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn(SECRET, text, f.name)
            self.assertNotIn(APIKEY, text, f.name)

    def test_runner_feedback_loop(self):
        out = FIXTURE["tmp"] / "runner-fb"
        rejects = FIXTURE["tmp"] / "rejects.json"
        rejects.write_text(json.dumps([
            {"pattern": "password 赋值形态", "dimension": "安全与敏感信息"}],
            ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1", "--out", out,
                             "--skip-probe", "--feedback", rejects)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        exp = json.loads((out / "experience.json").read_text(encoding="utf-8"))
        self.assertTrue(any(e["pattern"] == "password 赋值形态" for e in exp["entries"]))
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1", "--out", out, "--skip-probe")
        self.assertEqual(rc, 0)
        hit = [f for f in data.get("findings", []) if f.get("human_review")]
        self.assertTrue(hit, "命中误报模式的发现应标人工复核")
        self.assertTrue(any("误报模式" in f.get("note", "") for f in hit))

    def test_judge_dual_metrics(self):
        self.assertIn("recall", FIXTURE["judge"])
        self.assertIn("precision", FIXTURE["judge"])
        self.assertIn("claimed", FIXTURE["judge"])
        self.assertIn("grounded", FIXTURE["judge"])
        self.assertIn("claimed_but_not_grounded", FIXTURE["judge"])

    def test_feedback_close_aggregates(self):
        d = FIXTURE["tmp"] / "fb-close"
        d.mkdir(exist_ok=True)
        rejects = d / "rejects.json"
        rejects.write_text(json.dumps([
            {"pattern": "npe-optional", "dimension": "测试覆盖", "count": 1},
            {"pattern": "npe-optional", "dimension": "测试覆盖", "count": 2},
            {"rule_id": "cred-password", "dimension": "安全与敏感信息"}],
            ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["feedback-close.py"], "--findings", rejects,
                             "--experience", d / "exp")
        self.assertEqual(rc, 0)
        self.assertEqual(data["recorded"], 3)
        npe = [e for e in data["aggregated"] if e["pattern"] == "npe-optional"]
        self.assertEqual(len(npe), 1, "同维度同 pattern 不新增条目")
        self.assertEqual(npe[0]["rejected_count"], 3)

    def test_dispatch_experience_evidence_level(self):
        d = FIXTURE["tmp"] / "exp-strict"
        run(SCRIPTS["experience.py"], "record", "--dir", d,
            "--pattern", "flaky-test", "--dimension", "测试覆盖", "--count", 5)
        rc, data, _, _ = run(SCRIPTS["dispatch-plan.py"], "--diff", FIXTURE["change.diff"],
                             "--experience", d)
        self.assertEqual(rc, 0)
        self.assertEqual(data["evidence_levels"].get("测试覆盖"), "严格")

    def test_runner_budget_gate(self):
        cfg = FIXTURE["tmp"] / "zero-agent.json"
        args = json.loads((ROOT / "agent.json").read_text(encoding="utf-8"))
        args["args"]["max_review_minutes"] = 0
        cfg.write_text(json.dumps(args, ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = run(SCRIPTS["runner.py"], "--repo", FIXTURE["repo"],
                             "--range", "HEAD~2..HEAD~1",
                             "--out", FIXTURE["tmp"] / "runner-budget",
                             "--config", cfg, "--skip-probe")
        self.assertEqual(rc, 1)
        self.assertEqual(data["state"], "NEED_HUMAN")
        self.assertTrue(any(g["situation"] == "budget_both_exceeded" for g in data["gates"]))


