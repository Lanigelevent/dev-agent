#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_director.py — 总监（第五角色）契约断言：调度/案例库/简报/污点配置。"""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import SCRIPTS

ROOT = Path(__file__).resolve().parents[1]
DIRECTOR = ROOT / "skills" / "director" / "scripts"
TAINT_CONFIG = ROOT / "skills" / "multi-agent-review" / "taint-config.json"

POPEN_CALL = "os." + "popen(%s)"


class TestOrgRoute(unittest.TestCase):
    """总监调度台：分派、指挥链、RACI、能动性、升级链、守卫。"""

    def test_route_fix_gives_chain_and_raci(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-route.py"], "--kind",
                                          "fix", "--payload", "runs/r1/out")
        self.assertEqual(rc, 0)
        self.assertEqual(data["assignee"]["role"], "repair")
        self.assertEqual(data["chain_of_command"], ["repair", "director"])
        self.assertTrue(data["assignee"]["lead"], "v2 组织必须有团队首席")
        # RACI：补丁包由 repair 负责，approval 唯一签字
        self.assertEqual(data["raci"]["R"], "repair")
        self.assertEqual(data["raci"]["A"], "approval")
        # 能动性注册表：成员主动动作清单必须下发
        self.assertTrue(data["initiatives"], "分派回执必须带能动性清单")
        self.assertTrue(data["assignee"]["error_budget"], "必须带错误预算口径")

    def test_route_research_gives_escalation(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-route.py"], "--kind",
                                          "research", "--payload", "跨文件污点")
        self.assertEqual(rc, 0)
        self.assertEqual(data["assignee"]["role"], "research")
        self.assertTrue(data["escalation_levels"], "研究分派必须带值班升级链")
        self.assertIn("案例匹配", data["research_flow"])

    def test_route_unknown_kind_exit_2(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-route.py"], "--kind",
                                          "hack", "--payload", "x")
        self.assertEqual(rc, 2)
        self.assertIn("未知任务类型", data.get("error", ""))

    def test_route_missing_org_exit_2(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-route.py"], "--kind",
                                          "fix", "--org", "nope.json")
        self.assertEqual(rc, 2)


class TestOrgScorecard(unittest.TestCase):
    """错误预算结算：可计算、超限定级、无数据如实标 N/A。"""

    def test_scorecard_settlement(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-scorecard.py"])
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        teams = {s["team"]: s for s in data["scorecard"]}
        self.assertIn("repair", teams)
        # 项目案例全部带链接 → research 预算 PASS
        self.assertEqual(teams["research"]["status"], "PASS")
        # 无落盘数据时如实标 N/A，不假造
        self.assertTrue(teams["repair"]["status"].startswith("N/A"))
        self.assertTrue(data["advice"])

    def test_scorecard_exceeded_triggers_freeze(self):
        out = test_scripts.FIXTURE["tmp"] / "scorecard-scan"
        for name in ("a", "b", "c"):
            d = out / name
            d.mkdir(parents=True)
            (d / "apply-log.json").write_text(
                json.dumps({"status": "ROLLED_BACK"}),
                encoding="utf-8", newline="\n")
        ok_dir = out / "ok"
        ok_dir.mkdir(parents=True)
        (ok_dir / "apply-log.json").write_text(
            json.dumps({"status": "APPLIED"}), encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["org-scorecard.py"],
                                          "--scan", out)
        self.assertEqual(rc, 0)
        repair = [s for s in data["scorecard"] if s["team"] == "repair"][0]
        self.assertEqual(repair["value"], 0.75)
        self.assertEqual(repair["status"], "EXCEEDED")
        self.assertIn("repair", data["freeze_teams"])


class TestCaseMatchV2(unittest.TestCase):
    """案例库 v2：链接型档案——无链接不得入库，匹配返回档案链接。"""

    def test_ingest_requires_link(self):
        out = test_scripts.FIXTURE["tmp"] / "cases-v2"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--ingest",
            "--title", "无链接案例", "--takeaway", "不该入库",
            "--out", out)
        self.assertEqual(rc, 2)
        self.assertIn("--url 或 --local-ref", data.get("error", ""))

    def test_ingest_with_url_and_match(self):
        out = test_scripts.FIXTURE["tmp"] / "cases-v2-link"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--ingest",
            "--title", "调度台分派失联",
            "--takeaway", "分派前先跑技能失联检查",
            "--url", "https://example.com/org-handbook",
            "--out", out)
        self.assertEqual(rc, 0)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--match", "调度分派 技能失联",
            "--out", out)
        self.assertEqual(rc, 0)
        self.assertTrue(data["hits"])
        self.assertEqual(data["hits"][0]["url"],
                         "https://example.com/org-handbook")

    def test_v1_legacy_file_still_readable(self):
        """v1 旧字段（description/countermeasure）自动映射，不强制迁移。"""
        out = test_scripts.FIXTURE["tmp"] / "cases-v1"
        out.mkdir(parents=True)
        (out / "cases.json").write_text(json.dumps({"cases": [
            {"id": "legacy1234567", "category": "手工",
             "description": "旧格式坑", "countermeasure": "旧对策"}]},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-match.py"], "--match",
                                          "旧格式坑", "--out", out)
        self.assertEqual(rc, 0)
        self.assertTrue(data["hits"])
        self.assertIn("旧对策", data["hits"][0]["takeaway"])


class TestCaseMatch(unittest.TestCase):
    """案例库：入库、按词元重合匹配复用。"""

    def test_ingest_and_match_reuse(self):
        out = test_scripts.FIXTURE["tmp"] / "cases"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--ingest",
            "--category", "回滚",
            "--title", "落盘后仓库测试失败触发回滚",
            "--takeaway", "修复前先读懂行为契约，为被修行为补测试",
            "--local-ref", "tests/test_repair.py::test_tests_gate",
            "--out", out)
        self.assertEqual(rc, 0)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--ingest",
            "--category", "手工",
            "--title", "Windows 管道传 ID 带 CR 尾巴",
            "--takeaway", "脚本提取 ID 后必须 strip()",
            "--local-ref", "retro/pitfalls.json",
            "--out", out)
        self.assertEqual(rc, 0)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-match.py"], "--match", "补丁落盘后测试挂了被回滚",
            "--out", out)
        self.assertEqual(rc, 0)
        self.assertTrue(data["hits"], "应命中测试回滚案例")
        self.assertIn("补测试", data["hits"][0]["takeaway"])

    def test_from_ledger_ingests_closed_only(self):
        out = test_scripts.FIXTURE["tmp"] / "cases-ledger"
        ledger = test_scripts.FIXTURE["tmp"] / "cases-ledger-pits.json"
        ledger.write_text(json.dumps({"pitfalls": [
            {"id": "aaaaaaaaaaaa", "category": "回滚", "status": "closed",
             "description": "已修复坑A", "countermeasure": "对策A"},
            {"id": "bbbbbbbbbbbb", "category": "手工", "status": "open",
             "description": "未结坑B", "countermeasure": "对策B"},
        ]}, ensure_ascii=False), encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-match.py"],
                                          "--from-ledger", ledger, "--out", out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["added"], 1, "只入库已结案坑")
        cases = json.loads((out / "cases.json").read_text(encoding="utf-8"))
        self.assertEqual(cases["cases"][0]["id"], "aaaaaaaaaaaa")

    def test_match_no_hit_is_ok(self):
        out = test_scripts.FIXTURE["tmp"] / "cases-empty"
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-match.py"], "--match",
                                          "完全不相关的量子计算问题",
                                          "--out", out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["hits"], [])


class TestResearchBrief(unittest.TestCase):
    """研究简报：约束/检索词/验收口径齐备，脚本不联网。"""

    def test_brief_generation(self):
        out = test_scripts.FIXTURE["tmp"] / "briefs"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["research-brief.py"],
            "--description", "跨文件污点分析如何只用标准库实现",
            "--out", out)
        self.assertEqual(rc, 0)
        self.assertTrue(data["queries"], "必须生成检索词")
        brief = json.loads(Path(data["brief_json"]).read_text(encoding="utf-8"))
        self.assertTrue(brief["constraints"])
        self.assertIn("反向验证", " ".join(brief["acceptance"]))
        self.assertIn("研究简报", Path(data["brief_md"]).read_text(encoding="utf-8"))

    def test_brief_requires_description(self):
        out = test_scripts.FIXTURE["tmp"] / "briefs-bad"
        rc, data, _, _ = test_scripts.run(SCRIPTS["research-brief.py"],
                                          "--out", out)
        self.assertEqual(rc, 2)


class TestTaintConfig(unittest.TestCase):
    """污点配置化：总监治理的行为级优化入口。"""

    def _engine(self, script_path=None):
        spec = importlib.util.spec_from_file_location(
            "dr_cfg", script_path or SCRIPTS["deterministic-rules.py"])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_config_drives_sinks(self):
        """taint_rules 等于配置汇点数；配置启用的 os.popen 能抓到流。"""
        cfg = json.loads(TAINT_CONFIG.read_text(encoding="utf-8"))
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                          "--file", SCRIPTS["score.py"])
        self.assertEqual(rc, 0)
        self.assertEqual(data["taint_rules"], len(cfg["sinks"]))
        engine = self._engine()
        code = "cmd = os.environ['X']\n" + POPEN_CALL % "cmd" + "\n"
        findings = engine._taint_findings(
            "t.py", code, {i + 1: l for i, l in enumerate(code.splitlines())})
        self.assertEqual([f["rule_id"] for f in findings], ["taint-os-shell"])

    def test_invalid_config_falls_back_to_defaults(self):
        """坏配置回退内置缺省（可用性优先），且不触碰真仓配置。"""
        original = TAINT_CONFIG.read_bytes()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            script_dir = root / "scripts"
            script_dir.mkdir()
            script_copy = script_dir / "deterministic-rules.py"
            shutil.copy2(SCRIPTS["deterministic-rules.py"], script_copy)
            (root / "taint-config.json").write_text(
                "{broken json", encoding="utf-8", newline="\n")
            engine = self._engine(script_copy)
            self.assertEqual(engine._TAINT_CONFIG_PATH, root / "taint-config.json")
            self.assertEqual(len(engine.TAINT_SINK_FUNCS), 4)
        self.assertEqual(TAINT_CONFIG.read_bytes(), original)

    def test_director_scripts_self_scan_zero(self):
        """批扫口径（D-049 C）：一次子进程，按文件逐段断言。"""
        names = ("org-route.py", "case-match.py", "research-brief.py",
                 "org-scorecard.py", "case-archive.py")
        argv = []
        for name in names:
            argv += ["--file", str(SCRIPTS[name])]
        rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"], *argv)
        self.assertEqual(rc, 0)
        self.assertTrue(data.get("batch"))
        by_file = {r["file"]: r for r in data["results"]}
        for name in names:
            with self.subTest(script=name):
                r = by_file.get(str(SCRIPTS[name]))
                self.assertIsNotNone(r)
                self.assertEqual(r["rc"], 0, name)
                self.assertEqual(r["findings"], [], "%s 自扫出现命中" % name)


class TestCaseArchive(unittest.TestCase):
    """档案员：成败双轨、详细摘抄归档、发布与推送校验。"""

    def test_failure_ingest_renders_archive(self):
        out = test_scripts.FIXTURE["tmp"] / "arch"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-archive.py"], "--kind", "failure",
            "--title", "试用方案X导致精度回归",
            "--digest", "尝试直接并入扫描器，精度跌到 0.94，立即回退。",
            "--lessons", "行为级优化先在分支跑精度基线再合并",
            "--verification", "synth 1.0/1.0/0 保持",
            "--local-ref", "retro/pitfalls.json",
            "--out", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["kind"], "failure")
        archive = Path(data["archive_md"])
        self.assertTrue(archive.is_file())
        text = archive.read_text(encoding="utf-8")
        for token in ("详细摘抄", "教训与对策", "精度跌到 0.94", "失败案例"):
            self.assertIn(token, text)
        # 索引带 kind，匹配命中失败案例带避免提示
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-match.py"], "--match",
                                          "方案X 精度回归", "--out", out)
        hit = [h for h in data["hits"] if h.get("kind") == "failure"][0]
        self.assertIn("避免同样路径", hit["note"])

    def test_publish_renders_and_commits(self):
        out = test_scripts.FIXTURE["tmp"] / "arch-publish"
        test_scripts.run(SCRIPTS["case-archive.py"], "--kind", "success",
                         "--title", "优秀案例归档演示",
                         "--digest", "摘抄正文", "--lessons", "对策要点",
                         "--local-ref", "retro/round-1-report.md",
                         "--out", out)
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-archive.py"],
                                          "--publish", "--out", out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["committed"], True)
        repo = Path(data["archive_repo"])
        self.assertTrue((repo / "archive" / "README.md").is_file())
        self.assertTrue((repo / "archive").is_dir())

    def test_push_rejects_private_host(self):
        out = test_scripts.FIXTURE["tmp"] / "arch-push"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-archive.py"], "--publish", "--out", out,
            "--push", "--remote", "https://192.168.1.5/x.git")
        self.assertEqual(rc, 2)
        self.assertIn("私有", data.get("error", ""))

    def test_push_failure_keeps_local_archive(self):
        out = test_scripts.FIXTURE["tmp"] / "arch-push-fail"
        test_scripts.run(SCRIPTS["case-archive.py"], "--kind", "success",
                         "--title", "推送前先有本地档案", "--digest", "正文",
                         "--local-ref", "retro/pitfalls.json", "--out", out)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["case-archive.py"], "--publish", "--out", out,
            "--push", "--remote", "https://github.com/example/no-such.git")
        self.assertEqual(rc, 0)
        self.assertEqual(data["pushed"], False)
        self.assertEqual(data["committed"], True, "推送失败但本地提交必须成立")
        self.assertIn("推送失败", data["push_note"])

    def test_from_artifacts_collects_rollback(self):
        out = test_scripts.FIXTURE["tmp"] / "arch-artifacts"
        scan = out / "runs" / "r1"
        scan.mkdir(parents=True)
        (scan / "apply-log.json").write_text(
            json.dumps({"status": "ROLLED_BACK",
                        "error": "行为回归失败：仓库测试未通过",
                        "files": [{"path": "a.py"}],
                        "reuse_hints": [{"takeaway": "缩小补丁粒度"}]}),
            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-archive.py"],
                                          "--from-artifacts", "--scan", scan,
                                          "--out", out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["created"], 1)
        rc, data, _, _ = test_scripts.run(SCRIPTS["case-match.py"], "--match",
                                          "回滚 行为回归 测试", "--out", out)
        self.assertTrue(any(h.get("kind") == "failure"
                            for h in data["hits"]), "自动收的应为失败案例")


class TestTaskPipeline(unittest.TestCase):
    """任务流水线：拆解带 DoD / 派发经 org-route / 汇总不吞遗留。"""

    def _plan(self, name, request="review PR #12"):
        out = test_scripts.FIXTURE["tmp"] / name
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--from-intent", "--request", request,
                                          "--out", out)
        self.assertEqual(rc, 0, data)
        return out, data

    def test_from_intent_decomposes_with_dod(self):
        out, data = self._plan("taskpipe-decomp")
        tasks = data["tasks"]
        self.assertEqual([t["id"] for t in tasks], ["T1", "T2", "T3"])
        for t in tasks:
            self.assertIn(t["kind"], ("review", "fix", "retro"))
            self.assertTrue(t["produces"], "每个子任务必须写明产出物")
            self.assertTrue(t["dod"], "每个子任务必须带完成标准")
        self.assertEqual(tasks[0]["depends_on"], [])
        self.assertEqual(tasks[1]["depends_on"], ["T1"])
        self.assertTrue(Path(data["plan"]).is_file(), "plan 必须落盘")

    def test_from_intent_blocked_exit_3_single_question(self):
        out = test_scripts.FIXTURE["tmp"] / "taskpipe-blocked"
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--from-intent", "--request",
                                          "快速但也要仔细全面", "--out", out)
        self.assertEqual(rc, 3)
        self.assertTrue(data.get("blocked"))
        self.assertTrue(data.get("question"), "阻塞必须带回单问")
        self.assertEqual(len(out.glob("plan-*.json").fetchall() if False else
                         list(out.glob("plan-*.json"))), 0, "阻塞时不得落盘 plan")

    def test_dispatch_attaches_assignments(self):
        out, _ = self._plan("taskpipe-dispatch")
        plan_path = next(out.glob("plan-*.json"))
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--dispatch", "--plan", plan_path)
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["dispatched"], ["T1", "T2", "T3"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        t1 = plan["tasks"][0]["assignment"]
        self.assertEqual(t1["assignee"]["role"], "review")
        self.assertIn("raci", t1)
        self.assertIn("output_format", t1, "派发必须写明回报格式")
        self.assertIn("deadline", t1, "派发必须写明截止条件")

    def test_dispatch_rejects_cycle(self):
        plan_path = test_scripts.FIXTURE["tmp"] / "taskpipe-cycle.json"
        plan_path.write_text(json.dumps({"tasks": [
            {"id": "A", "kind": "review", "title": "x", "depends_on": ["B"],
             "produces": "p", "dod": ["d"]},
            {"id": "B", "kind": "retro", "title": "y", "depends_on": ["A"],
             "produces": "p", "dod": ["d"]}]}, ensure_ascii=False),
            encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--dispatch", "--plan", plan_path)
        self.assertEqual(rc, 2)
        self.assertTrue(any("环" in p for p in data.get("problems", [])))

    def test_collect_reports_unfinished_and_keeps_confirmations(self):
        out, _ = self._plan("taskpipe-collect")
        plan_path = next(out.glob("plan-*.json"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        results = {"tasks": {
            "T1": {"status": "done", "summary": "预检完成",
                   "artifacts": ["intent.json"]},
            "T2": {"status": "done", "summary": "评审 3 条发现",
                   "risks": ["2 条待人工复核"]}}}
        results_path = out / "results.json"
        results_path.write_text(json.dumps(results, ensure_ascii=False),
                                encoding="utf-8")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["task-pipeline.py"], "--collect", "--plan", plan_path,
            "--results", results_path, "--out", out / "collect.json")
        self.assertEqual(rc, 0)
        self.assertIn("2/3", data["overall"])
        self.assertEqual(len(data["key_changes"]), 2)
        self.assertEqual([o["id"] for o in data["open_tasks"]], ["T3"])
        self.assertEqual(len(data["remaining_risks"]), 2, "未回报任务必须进遗留")
        self.assertEqual(len(data["assumptions_still_open"]),
                         len(plan.get("confirmations", [])),
                         "待确认项必须原样带回汇总")
        self.assertTrue((out / "collect.json").is_file())

    def test_mode_and_args_errors_exit_2(self):
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"])
        self.assertEqual(rc, 2)
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--from-intent", "--request", "x")
        self.assertEqual(rc, 2, "--from-intent 缺 --out 必须拒绝")
        rc, data, _, _ = test_scripts.run(SCRIPTS["task-pipeline.py"],
                                          "--from-intent", "--request", "x",
                                          "--out", "y", "--dispatch")
        self.assertEqual(rc, 2, "多模式必须拒绝")

    def test_compound_clause_becomes_subtask_after_review(self):
        # 复合子句（坑 791468dc0ca2 ②）拆成独立子任务，依赖最后的评审任务
        out, data = self._plan("taskpipe-compound",
                               request="review PR #12，然后顺便把测试也补全")
        tasks = data["tasks"]
        self.assertEqual([t["id"] for t in tasks], ["T1", "T2", "T3", "T4"])
        extra = tasks[-1]
        self.assertEqual(extra["origin"], "compound_clause")
        self.assertEqual(extra["kind"], "fix")
        self.assertIn("补全测试", extra["title"])
        self.assertEqual(extra["depends_on"], ["T2"],
                         "搭车工作必须依赖最后一个 review 任务（standard 模板=T2）")
        self.assertTrue(extra["dod"], "复合子任务与模板任务同规范：必须带完成标准")

    def test_collect_rejects_list_shape_exit_2(self):
        # 形状错（坑 791468dc0ca2 ③）：列表回报必须 exit 2 报错，
        # 不许静默当「全部未回报」零命中
        out, _ = self._plan("taskpipe-shape")
        plan_path = next(out.glob("plan-*.json"))
        results_path = out / "results.json"
        results_path.write_text(json.dumps(
            [{"id": "T1", "status": "done", "summary": "s"}], ensure_ascii=False),
            encoding="utf-8")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["task-pipeline.py"], "--collect", "--plan", plan_path,
            "--results", results_path, "--out", out / "collect.json")
        self.assertEqual(rc, 2)
        self.assertIn("形状", data.get("error", ""))
        self.assertFalse((out / "collect.json").exists(), "报错路径不得落盘汇总")

    def test_collect_out_directory_rejected(self):
        # --out 是文件路径（坑 791468dc0ca2 ③）：传目录要明确报错，
        # 不许拖到写盘时才 PermissionError
        out, _ = self._plan("taskpipe-outdir")
        plan_path = next(out.glob("plan-*.json"))
        results_path = out / "results.json"
        results_path.write_text(json.dumps(
            {"T1": {"status": "done", "summary": "s"}}, ensure_ascii=False),
            encoding="utf-8")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["task-pipeline.py"], "--collect", "--plan", plan_path,
            "--results", results_path, "--out", out)
        self.assertEqual(rc, 2)
        self.assertIn("--out", data.get("error", ""))

    def test_collect_flags_unmatched_result_keys(self):
        # 回报键对不上任务 id 也不许静默丢弃：进 unmatched_results + 遗留风险
        out, _ = self._plan("taskpipe-unmatched")
        plan_path = next(out.glob("plan-*.json"))
        results_path = out / "results.json"
        results_path.write_text(json.dumps(
            {"tasks": {"XX9": {"status": "done", "summary": "x"}}},
            ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["task-pipeline.py"], "--collect", "--plan", plan_path,
            "--results", results_path, "--out", out / "collect.json")
        self.assertEqual(rc, 0)
        self.assertEqual(data["unmatched_results"], ["XX9"])
        self.assertTrue(any("XX9" in r["risk"]
                            for r in data["remaining_risks"]),
                        "对不上的键必须进 remaining_risks")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        self.assertEqual({o["id"] for o in data["open_tasks"]},
                         {t["id"] for t in plan["tasks"]})


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
