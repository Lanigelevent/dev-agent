#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_retro.py — 迭代官（第四角色）契约断言：台账去重/结案/轮报/候选。"""

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import SCRIPTS


def _fresh_iso(hours_ago=1.0):
    """新鲜相对时间戳（防夹具过期：compact-memory 老化按 now 计算 age，
    钉死日期会随时间推移越过 max-age 边界——r184 实踩）。"""
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _seed_artifacts(tmp):
    """伪造一轮产物痕迹：REJECTED + ROLLED_BACK + skipped + 误报经验。"""
    ap = tmp / "artifacts" / "ap"
    ap.mkdir(parents=True)
    (ap / "approval.json").write_text(json.dumps(
        {"verdict": "REJECTED", "reasons": ["工单外规则: dang-eval"]}),
        encoding="utf-8", newline="\n")
    (tmp / "artifacts" / "fix").mkdir(parents=True, exist_ok=True)
    (tmp / "artifacts" / "fix" / "apply-log.json").write_text(json.dumps(
        {"status": "ROLLED_BACK", "error": "行为回归失败：仓库测试未通过"}),
        encoding="utf-8", newline="\n")
    (tmp / "artifacts" / "fix" / "fix-manifest.json").write_text(json.dumps(
        {"skipped": [{"rule_id": "lang-resource-unclosed", "reason": "转人工"}]}),
        encoding="utf-8", newline="\n")
    (tmp / "artifacts" / "experience.json").write_text(json.dumps(
        {"entries": [{"pattern": "p1"}]}), encoding="utf-8", newline="\n")


def _events_file(tmp):
    events = tmp / "events.json"
    events.write_text(json.dumps({"events": [
        {"category": "手工", "description": "MCP 服务器自扫曾出现空 except 命中",
         "root_cause": "新代码吞异常", "countermeasure": "except 必须落 stderr 说明"},
        {"category": "回滚", "description": "落盘回滚: 行为回归失败：仓库测试未通过",
         "countermeasure": "缩小补丁粒度或补测试后重试"},
    ]}, ensure_ascii=False), encoding="utf-8", newline="\n")
    return events


class TestRetro(unittest.TestCase):
    """迭代官：采集、去重、结案、轮报、候选排序。"""

    def test_ledger_collect_and_dedupe(self):
        tmp = test_scripts.FIXTURE["tmp"] / "retro-ledger"
        _seed_artifacts(tmp)
        events = _events_file(tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--events", events,
                                          "--scan", tmp / "artifacts")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        # 2 手工 + 4 产物痕迹；回滚事件与手工事件描述一致 → 同 id 去重为 5
        self.assertEqual(data["new"], 5)
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        self.assertEqual(len([p for p in ledger["pitfalls"]
                              if p["category"] == "回滚"]), 1)
        # 重跑：无新增
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--events", events,
                                          "--scan", tmp / "artifacts")
        self.assertEqual(data["new"], 0)
        self.assertEqual(data["total"], 5)

    def test_ledger_close_and_weight_order(self):
        tmp = test_scripts.FIXTURE["tmp"] / "retro-close"
        _seed_artifacts(tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--events",
                                          _events_file(tmp),
                                          "--scan", tmp / "artifacts")
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        rollback = [p for p in ledger["pitfalls"] if p["category"] == "回滚"][0]
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", rollback["id"],
                                          "--close-note",
                                          "缩小补丁粒度后复跑：同 id 坑未再出现，仓库测试通过")
        self.assertEqual(rc, 0)
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        status = {p["id"]: p["status"] for p in ledger["pitfalls"]}
        self.assertEqual(status[rollback["id"]], "closed")
        # 结案口径必须留在台账里，否则下一轮无从审计「当初凭什么说它填了」
        note = {p["id"]: p.get("closure_note") for p in ledger["pitfalls"]}
        self.assertIn("仓库测试通过", note[rollback["id"]])
        # 权重排序：回滚/行为回归类在前
        cats = [p["category"] for p in ledger["pitfalls"]]
        self.assertEqual(cats[0], "回滚")

    def test_close_requires_verifiable_note(self):
        """反向验证：不带验收口径的结案必须被拒（灭灯 ≠ 填坑）。"""
        tmp = test_scripts.FIXTURE["tmp"] / "retro-close-note"
        _seed_artifacts(tmp)
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", tmp / "retro",
                         "--events", _events_file(tmp),
                         "--scan", tmp / "artifacts")
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        any_id = ledger["pitfalls"][0]["id"]
        rc, data, _, err = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                            tmp / "retro", "--close", any_id)
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("验收口径", data["error"])
        # 台账不能被悄悄改掉
        after = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        self.assertEqual({p["id"]: p["status"] for p in after["pitfalls"]},
                         {p["id"]: p["status"] for p in ledger["pitfalls"]})
        # 带上口径就能结
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", any_id,
                                          "--close-note", "闸门三查 + 反向验证测试全绿")
        self.assertEqual(rc, 0)
        self.assertEqual(data["closure_note"], "闸门三查 + 反向验证测试全绿")

    def test_close_rejects_unrunnable_acceptance_command(self):
        """反向验证：结案口径里写死的验收命令必须原样能跑（round-30 实踩）。

        踩过的形状是 `-m unittest tests.test_repair -k xxx`——tests/ 下模块互相
        import 兄弟模块，按模块名加载不在 sys.path 上必然 ModuleNotFoundError，
        于是台账里躺着一行谁都复跑不了的「验收口径」。闸门只认这一条形态：提到了
        `-m unittest` 就必须是 `discover -s tests`；不写命令的口径不受影响。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-close-cmd"
        _seed_artifacts(tmp)
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", tmp / "retro",
                         "--events", _events_file(tmp), "--scan",
                         tmp / "artifacts")
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        any_id = ledger["pitfalls"][0]["id"]
        bad = ("验收：PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe "
               "-m unittest tests.test_repair -k apply_log_history 全绿")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", any_id,
                                          "--close-note", bad)
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("跑不起来", data["error"])
        self.assertIn("discover -s tests", data["error"])
        after = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        self.assertEqual([p["status"] for p in after["pitfalls"]],
                         [p["status"] for p in ledger["pitfalls"]],
                         "被拒的结案不许把坑改成 closed")
        # 正确形态能结（这条命令在本仓真实可跑，不是编出来的形状）
        good = ('验收：.venv/Scripts/python.exe -m unittest discover -s tests '
                '-p "test_repair.py" -k apply_log_history_survives_retry → OK')
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", any_id,
                                          "--close-note", good)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["closure_note"], good)
        # 不含 unittest 的口径不受闸门影响（人工复核类结案不该被误伤）
        other = ledger["pitfalls"][1]["id"]
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", other,
                                          "--close-note", "人工复核样例 + 台账留痕")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])

    def test_ledger_skips_completion_events(self):
        """入册器只收坑形态事件（round-44 结构整改）。

        实踩：round-37..42 的事件文件用 type 区分工作事项（feature/test/doc/
        confirmation），旧入册器只认 description，22 条完成事件被当坑收进台账
        （category=手工、无根因），open 虚高到 32、把 retro 队送进超预算冻结。
        规则先于数字写死在 NON_PITFALL_EVENT_TYPES；缺 type 的历史事件仍按坑
        处理（向后兼容），correction 也仍按坑处理——round-40 那条 correction
        记的正是 Edit 工具静默损坏，是真坑。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-events-type"
        tmp.mkdir(parents=True, exist_ok=True)
        events = tmp / "typed-events.json"
        events.write_text(json.dumps([
            {"type": "feature", "description": "候选补丁排序器落地"},
            {"type": "test", "description": "新增 5 项契约测试"},
            {"type": "doc", "description": "全量传播：版本升 1.45.0"},
            {"type": "confirmation", "description": "确认阶段 1-A 已落地"},
            {"type": "correction", "description": "发现并修复 Edit 工具 $$$ 静默丢失",
             "root_cause": "宿主工具静默改写", "countermeasure": "脚本直改 + 读回"},
            {"category": "手工", "description": "缺 type 的历史事件仍要入册",
             "root_cause": "旧形状", "countermeasure": "向后兼容"},
        ], ensure_ascii=False), encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--events", events)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["new"], 2)
        self.assertEqual(data["skipped_events"], 4,
                         "feature/test/doc/confirmation 必须被跳过并如实计数")
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        descs = [p["description"] for p in ledger["pitfalls"]]
        self.assertEqual(len(descs), 2, descs)
        self.assertTrue(any("Edit 工具" in d for d in descs),
                        "correction 是真坑形态，不能被白名单误伤")
        self.assertTrue(any("缺 type" in d for d in descs),
                        "缺 type 的历史事件必须向后兼容")
        # 重跑：跳过不报错、也不再新增
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--events", events)
        self.assertEqual(rc, 0)
        self.assertEqual(data["new"], 0)
        self.assertEqual(data["total"], 2)

    def test_archive_requires_note_and_only_open(self):
        """归档是「这条从来不是坑」的更正：必须有理由、只对 open、不可再结案。"""
        tmp = test_scripts.FIXTURE["tmp"] / "retro-archive"
        _seed_artifacts(tmp)
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", tmp / "retro",
                         "--events", _events_file(tmp),
                         "--scan", tmp / "artifacts")
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        open_id = [p["id"] for p in ledger["pitfalls"]
                   if p["status"] == "open"][0]
        open_before = len([p for p in ledger["pitfalls"]
                           if p["status"] == "open"])
        # 反向验证：不带理由不许归档（更正路径不能比结案更宽松）
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--archive", open_id)
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("理由", data["error"])
        # 结案与归档互斥
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--archive", open_id,
                                          "--archive-note", "完成事件误入册",
                                          "--close", open_id,
                                          "--close-note", "人工复核")
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        # 正常归档：状态/理由/日期都落盘，open 计数下降
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--archive", open_id,
                                          "--archive-note",
                                          "feature 完成事件被旧入册器误收，非坑")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["open"], open_before - 1)
        self.assertGreaterEqual(data["archived"], 1)
        after = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        rec = [p for p in after["pitfalls"] if p["id"] == open_id][0]
        self.assertEqual(rec["status"], "archived")
        self.assertIn("非坑", rec["archive_note"])
        self.assertTrue(rec.get("archived_at"), "归档必须留日期")
        # 已归档的不能再结案（非坑没有「填坑」一说），也不能再次归档
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--close", open_id,
                                          "--close-note", "人工复核")
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("已归档", data["error"])
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-ledger.py"], "--out",
                                          tmp / "retro", "--archive", open_id,
                                          "--archive-note", "重复归档")
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])

    def test_report_round_and_candidates(self):
        tmp = test_scripts.FIXTURE["tmp"] / "retro-report"
        _seed_artifacts(tmp)
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", tmp / "retro",
                         "--events", _events_file(tmp),
                         "--scan", tmp / "artifacts")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          tmp / "retro" / "pitfalls.json",
                                          "--out", tmp / "retro")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["round"], 1)
        report = Path(data["report"])
        self.assertTrue(report.is_file())
        text = report.read_text(encoding="utf-8")
        self.assertIn("复盘轮报 round-1", text)
        self.assertIn("改进候选", text)
        # 机器候选清单：带轮号、与人工检查单不同名
        candidates_file = Path(data["candidates_file"])
        self.assertTrue(candidates_file.is_file())
        self.assertIn("round-1 改进候选（机器产出）",
                      candidates_file.read_text(encoding="utf-8"))
        # 人工检查单不由脚本创建：没有就是没有，指针如实为 None
        self.assertFalse((tmp / "retro" / "next-round.md").is_file())
        self.assertIsNone(data["next_round"])
        # 候选排序：回滚（权重3）应排在 转人工（权重1）之前
        titles = [c["category"] for c in data["candidates"]]
        self.assertIn("回滚", titles)
        self.assertLess(titles.index("回滚"), titles.index("转人工"))
        # 第二轮自增
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          tmp / "retro" / "pitfalls.json",
                                          "--out", tmp / "retro")
        self.assertEqual(data["round"], 2)

    def test_report_counts_archived_separately_from_closed(self):
        """反向验证：archived 不得计进 closed（round-44 引入第三态后的口径）。

        旧口径 `status != open` 把归档条目算成已结案，轮报头条会把 24 条
        归档记成「closed 152」——数字看着更大，账却是错的。归档表示
        「从来不是坑」，与「修好了」不是一回事。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-three-states"
        retro = tmp / "retro"
        retro.mkdir(parents=True, exist_ok=True)
        ledger = {"pitfalls": [
            {"id": "a1", "category": "手工", "description": "仍开着",
             "status": "open"},
            {"id": "a2", "category": "手工", "description": "验证后结案",
             "status": "closed"},
            {"id": "a3", "category": "手工", "description": "入册错误归档",
             "status": "archived"},
        ]}
        ledger_file = retro / "pitfalls.json"
        ledger_file.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          ledger_file, "--out", retro)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["open"], 1)
        self.assertEqual(data["closed"], 1)
        self.assertEqual(data["archived"], 1)
        text = Path(data["report"]).read_text(encoding="utf-8")
        self.assertIn("open 1 / closed 1 / archived 1", text)

    def test_report_round_survives_gap_in_archive(self):
        """反向验证：归档缺轮时自增必须取「最大轮号 + 1」，不得覆盖历史轮报。

        round-29 实踩：retro/ 缺 round-9-report.md，旧口径按文件数算出 27+1=28，
        正好把真实存在的 round-28-report.md 原地盖掉（靠 git checkout 才恢复）。
        这里造 round-1 + round-3 的缺口归档：旧口径会给 3（盖掉 round-3），
        新口径必须给 4，且 round-3 的正文一字不动。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-gap"
        retro = tmp / "retro"
        retro.mkdir(parents=True, exist_ok=True)
        (retro / "round-1-report.md").write_text("# 复盘轮报 round-1\n", encoding="utf-8")
        marker = "# 复盘轮报 round-3\n历史正文：这轮结的坑不许被盖掉\n"
        (retro / "round-3-report.md").write_text(marker, encoding="utf-8")
        ledger = {"pitfalls": [{"id": "x1", "category": "手工",
                                "description": "缺口归档用例", "status": "open"}]}
        ledger_file = retro / "pitfalls.json"
        ledger_file.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          ledger_file, "--out", retro)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["round"], 4, "缺轮归档按文件数自增会撞掉已有轮报")
        self.assertEqual((retro / "round-3-report.md").read_text(encoding="utf-8"),
                         marker)
        self.assertTrue((retro / "round-4-report.md").is_file())

    def test_report_auto_guard_refused_in_real_repo(self):
        """反向验证（红线 6）：复刻 r154 实景——真仓多跑一遍 retro-report
        （无 --round）必须被护栏拦下，不得生成过早轮报（r155 坑 a5ba44db35ee）。

        r154 收官被多跑两遍生成过早 round-155/156「预览」报告并误入库；
        根因=真仓语境（有 next-round.md）缺省自动编号无护栏。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-guard-refuse"
        retro = tmp / "retro"
        retro.mkdir(parents=True, exist_ok=True)
        (retro / "round-154-report.md").write_text("# 复盘轮报 round-154\n",
                                                   encoding="utf-8")
        (retro / "next-round.md").write_text(
            "> round-154 收官（2026-11-14）：……台账 246。下一轮（round-155）见第 115 条。\n",
            encoding="utf-8")
        ledger = {"pitfalls": [{"id": "g1", "category": "手工",
                                "description": "护栏用例", "status": "open"}]}
        (retro / "pitfalls.json").write_text(json.dumps(ledger, ensure_ascii=False),
                                             encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          retro / "pitfalls.json", "--out", retro)
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])
        self.assertIn("护栏", data["error"])
        self.assertFalse((retro / "round-155-report.md").is_file(),
                         "过早轮报不得被生成")
        self.assertFalse((retro / "round-155-candidates.md").is_file())

    def test_report_auto_guard_confirm_next_allows(self):
        tmp = test_scripts.FIXTURE["tmp"] / "retro-guard-confirm"
        retro = tmp / "retro"
        retro.mkdir(parents=True, exist_ok=True)
        (retro / "round-154-report.md").write_text("# 复盘轮报 round-154\n",
                                                   encoding="utf-8")
        (retro / "next-round.md").write_text(
            "> round-154 收官（2026-11-14）：……下一轮（round-155）。\n",
            encoding="utf-8")
        ledger = {"pitfalls": [{"id": "g2", "category": "手工",
                                "description": "护栏用例", "status": "open"}]}
        (retro / "pitfalls.json").write_text(json.dumps(ledger, ensure_ascii=False),
                                             encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          retro / "pitfalls.json", "--out", retro,
                                          "--confirm-next")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["round"], 155)
        self.assertEqual(data["round_source"], "auto")
        self.assertTrue(data["auto_guard"]["confirm_next"])

    def test_report_explicit_round_bypasses_guard(self):
        tmp = test_scripts.FIXTURE["tmp"] / "retro-guard-explicit"
        retro = tmp / "retro"
        retro.mkdir(parents=True, exist_ok=True)
        (retro / "round-154-report.md").write_text("# 复盘轮报 round-154\n",
                                                   encoding="utf-8")
        (retro / "next-round.md").write_text(
            "> round-154 收官（2026-11-14）：……下一轮（round-155）。\n",
            encoding="utf-8")
        ledger = {"pitfalls": [{"id": "g3", "category": "手工",
                                "description": "护栏用例", "status": "open"}]}
        (retro / "pitfalls.json").write_text(json.dumps(ledger, ensure_ascii=False),
                                             encoding="utf-8")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          retro / "pitfalls.json", "--out", retro,
                                          "--round", "155")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["round"], 155)
        self.assertEqual(data["round_source"], "explicit")
        self.assertIsNone(data["auto_guard"])

    def test_report_refuses_to_clobber_an_existing_round(self):
        """反向验证：显式 --round 给已用过的轮号时默认拒绝，重写必须明说 --force。

        同类排查（round-30 检查单第 7 项）：_next_round 改成「最大轮号 + 1」只堵住了
        缺省路径；`--round 28` 这类手滑/脚本调用照样能绕过它，把归档里的历史轮报
        原地盖掉——round-29 就是这样重写了已归档的 round-28-report.md。
        这里锚的是「历史记录不是可重算的缓存」。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-force"
        retro = tmp / "retro"
        _seed_artifacts(tmp)
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", retro,
                         "--events", _events_file(tmp),
                         "--scan", tmp / "artifacts")
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          retro / "pitfalls.json", "--out", retro,
                                          "--round", 7)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        report = retro / "round-7-report.md"
        self.assertTrue(report.is_file())
        # 换一个台账内容再撞同一轮号：若真盖了，正文一定会变
        ledger_file = retro / "pitfalls.json"
        ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
        ledger["pitfalls"].append({"id": "z9", "category": "误报",
                                   "description": "撞号重写用例新增的坑",
                                   "status": "open"})
        ledger_file.write_text(json.dumps(ledger, ensure_ascii=False),
                               encoding="utf-8", newline="\n")
        before = report.read_bytes()
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          ledger_file, "--out", retro,
                                          "--round", 7)
        self.assertEqual(rc, 2, json.dumps(data, ensure_ascii=False)[:300])
        self.assertFalse(data.get("ok"), "拒绝必须体现在 ok=false，不能只写 stderr")
        self.assertIn("拒绝覆盖历史", data["error"])
        self.assertEqual(report.read_bytes(), before, "被拒的这次一个字都不该动")
        # 加 --force 才允许重写，且如实报出这是强制覆盖
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          ledger_file, "--out", retro,
                                          "--round", 7, "--force")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertTrue(data["forced_overwrite"])
        self.assertNotEqual(report.read_bytes(), before)
        self.assertIn("撞号重写用例新增的坑", report.read_text(encoding="utf-8"))
        # 缺省自增路径不受闸门影响：正常往下一轮写，且不带 force 标记
        rc, data, _, _ = test_scripts.run(SCRIPTS["retro-report.py"], "--ledger",
                                          ledger_file, "--out", retro)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["round"], 8, "已有 round-7，缺省应自增到 8")
        self.assertFalse(data["forced_overwrite"])

    def test_report_leaves_hand_curated_checklist_untouched(self):
        """反向验证：人工写的 next-round.md 跑完 report 必须逐字节不变。

        round-28 的坑是脚本把 46 行人工检查单重写成 5 行骨架。改产出
        round-<N>-candidates.md 之后，这个断言就是「谁也不再覆盖谁」的证据；
        若哪天有人把写回 next-round.md 的路加回来，这里会直接转红。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "retro-untouched"
        _seed_artifacts(tmp)
        retro_dir = tmp / "retro"
        test_scripts.run(SCRIPTS["retro-ledger.py"], "--out", retro_dir,
                         "--events", _events_file(tmp),
                         "--scan", tmp / "artifacts")
        checklist = retro_dir / "next-round.md"
        hand_text = ("# 下一轮开局检查单\n\n开局先读本单；逐项核对后再进入新工作。\n\n"
                     "1. [评测] 样本 n=20、17 resolved，扩样前先跑一次完整全量\n"
                     "   —— 人工增补的验收口径，脚本不许覆盖这一行\n")
        checklist.write_text(hand_text, encoding="utf-8", newline="\n")
        before = checklist.read_bytes()
        for n in (1, 2):
            rc, data, _, _ = test_scripts.run(
                SCRIPTS["retro-report.py"], "--ledger",
                retro_dir / "pitfalls.json", "--out", retro_dir,
                "--round", str(n))
            self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
            # 指针指向人工文件（存在时如实报出），但脚本不写它
            self.assertEqual(Path(data["next_round"]), checklist)
            self.assertTrue(data["next_round_untouched"])
        self.assertEqual(checklist.read_bytes(), before)
        self.assertIn("人工增补的验收口径", checklist.read_text(encoding="utf-8"))
        # 机器产出落在自己的文件里，不串台
        self.assertNotIn("下一轮开局检查单",
                         Path(data["candidates_file"]).read_text(encoding="utf-8"))

    def test_retro_scripts_self_scan_zero(self):
        """批扫口径（D-049 C）：一次子进程，按文件逐段断言。"""
        names = ("retro-ledger.py", "retro-report.py")
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
                self.assertEqual(r["findings"], [], "%s 自扫出现命中" % name)


def _seed_memory(tmp, count=5):
    """生成测试用记忆条目。"""
    mem_file = tmp / "agent-memory.jsonl"
    entries = [
        {
            "id": "mem-001",
            "timestamp": "2026-10-20T10:00:00",
            "task": "fix XSS vulnerability in innerHTML handling",
            "repo": str(tmp / "repo1"),
            "files": ["app.js"],
            "edit_format": "replace innerHTML with textContent",
            "rule_codes": ["xss-prevention", "dom-sanitize"],
            "result": "pass",
            "failure_category": "security",
            "trace_file": "",
            "retrieval_count": 2,
        },
        {
            "id": "mem-002",
            "timestamp": "2026-10-21T11:00:00",
            "task": "fix SQL injection in user input query",
            "repo": str(tmp / "repo2"),
            "files": ["db.py"],
            "edit_format": "use parameterized query",
            "rule_codes": ["sql-injection", "parameterized-query"],
            "result": "pass",
            "failure_category": "security",
            "trace_file": "",
            "retrieval_count": 1,
        },
        {
            "id": "mem-003",
            "timestamp": "2026-10-22T12:00:00",
            "task": "fix off-by-one error in array loop",
            "repo": str(tmp / "repo3"),
            "files": ["utils.py"],
            "edit_format": "change range(n+1) to range(n)",
            "rule_codes": ["off-by-one", "loop-boundary"],
            "result": "fail",
            "failure_category": "logic-error",
            "trace_file": "",
            "retrieval_count": 0,
        },
        {
            "id": "mem-004",
            "timestamp": "2026-10-23T13:00:00",
            "task": "fix memory leak in event listener",
            "repo": str(tmp / "repo4"),
            "files": ["events.js"],
            "edit_format": "remove event listener on dispose",
            "rule_codes": ["memory-leak", "event-cleanup"],
            "result": "pass",
            "failure_category": "resource-management",
            "trace_file": "",
            "retrieval_count": 3,
        },
        {
            "id": "mem-005",
            "timestamp": "2026-10-24T14:00:00",
            "task": "fix XSS in template rendering innerHTML",
            "repo": str(tmp / "repo5"),
            "files": ["template.py"],
            "edit_format": "escape HTML before render",
            "rule_codes": ["xss-prevention", "html-escape"],
            "result": "pass",
            "failure_category": "security",
            "trace_file": "",
            "retrieval_count": 1,
        },
    ]
    with open(mem_file, "w", encoding="utf-8", newline="\n") as f:
        for entry in entries[:count]:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return mem_file


class TestMemoryRetrieval(unittest.TestCase):
    """记忆检索层（步骤 1.4）集成测试。"""

    def test_retrieval_returns_top_k_hits(self):
        """基本检索：query 匹配应返回 top_k 结果，按得分降序。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-retrieve"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "XSS innerHTML",
            "--top-k", "3",
            "--max-chars", "2000"
        )
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIsNotNone(data)
        self.assertIn("hits", data)
        self.assertGreaterEqual(len(data["hits"]), 1, "XSS 相关至少命中 1 条")
        # 得分应降序
        scores = [h["score"] for h in data["hits"]]
        self.assertEqual(scores, sorted(scores, reverse=True), "得分应降序")

    def test_retrieval_empty_memory(self):
        """空记忆库：应返回空 hits 列表，exit=0。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-empty"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp, count=0)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "anything",
            "--top-k", "3"
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["hits"], [])

    def test_retrieval_top_k_truncation(self):
        """top_k=2 应只返回 2 条，即使有更多匹配。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-topk"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "fix XSS",
            "--top-k", "2",
            "--max-chars", "5000"
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        self.assertEqual(len(data["hits"]), 2, "top_k=2 应只返回 2 条")

    def test_retrieval_max_chars_truncation(self):
        """max_chars 过小应截断结果条目数。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-maxchars"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "fix XSS",
            "--top-k", "5",
            "--max-chars", "100"
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        # max_chars=100 不足以容纳 5 条，应少于 5 条
        self.assertLessEqual(len(data["hits"]), 2)

    def test_retrieval_no_match_returns_empty(self):
        """无匹配 query 应返回空 hits。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-nomatch"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "quantum computing blockchain",
            "--top-k", "3"
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["hits"], [])

    def test_min_score_filters_generic_only_matches(self):
        """只共享通用词的条目不得进入 few-shot（台账 93b028b2bc6f 结案）。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-minscore"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = _seed_memory(tmp)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file, "--query", "fix", "--top-k", "3")
        self.assertEqual(rc, 0)
        self.assertEqual(data["hits"], [], "通用词 fix 不应命中任何条目")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file, "--query", "fix typo in documentation",
            "--top-k", "3")
        self.assertEqual(rc, 0)
        self.assertEqual(data["hits"], [], "仅共享通用词的相关度不得过阈值")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file, "--query", "fix XSS", "--top-k", "3")
        self.assertEqual(rc, 0)
        self.assertEqual({h["id"] for h in data["hits"]},
                         {"mem-001", "mem-005"}, "真相关条目必须保留")
        # 反向验证：阈值归零后同样的 query 能命中，证明过滤由阈值数字驱动
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file, "--query", "fix", "--top-k", "3",
            "--min-score", "0.0")
        self.assertEqual(rc, 0)
        self.assertTrue(data["hits"], "阈值归零后通用词应能命中")

    def test_retrieval_missing_file_exit_code(self):
        """不存在的记忆文件应 exit=2。"""
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", "/nonexistent/path.jsonl",
            "--query", "test"
        )
        self.assertEqual(rc, 2, "文件不存在应 exit=2")

    def test_output_is_utf8_under_gbk_stdio(self):
        """中文记忆在 GBK 默认 stdio 下仍按 UTF-8 输出（不 mojibake）。

        反向验证：删掉 main() 里的 reconfigure 后，子进程按 cp936 写
        中文，父进程按 UTF-8 解码会得到替换字符，本断言转红。
        """
        tmp = test_scripts.FIXTURE["tmp"] / "mem-gbk"
        tmp.mkdir(parents=True, exist_ok=True)
        mem_file = tmp / "mem.jsonl"
        entry = {"id": "mem-cn", "task": "修复 innerHTML XSS 漏洞",
                 "summary": "渲染前转义 HTML，中文摘要", "rule_codes": ["xss"],
                 "failure_category": "security", "result": "pass"}
        mem_file.write_text(json.dumps(entry, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["memory_retrieval.py"],
            "--memory", mem_file,
            "--query", "XSS innerHTML",
            env_extra={"PYTHONIOENCODING": "gbk"})
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn("转义", data["hits"][0]["snippet"],
                      "中文摘要必须原样到达，不许被 stdio 编码解坏")


class TestCompactMemory(unittest.TestCase):
    """记忆压缩与老化（步骤 1.6）集成测试。"""

    def test_compact_basic_compression(self):
        """相似条目应被合并，保留最详细的一条。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-compact"
        tmp.mkdir(parents=True, exist_ok=True)
        input_file = tmp / "agent-memory.jsonl"
        entries = [
            {
                "id": "c1", "timestamp": _fresh_iso(3),
                "task": "fix XSS in innerHTML", "summary": "short",
                "edit_format": "replace innerHTML",
                "rule_codes": ["xss"], "result": "pass",
                "failure_category": "security", "trace_file": "", "retrieval_count": 0,
            },
            {
                "id": "c2", "timestamp": _fresh_iso(2),
                "task": "fix XSS vulnerability in innerHTML rendering",
                "summary": "longer description with more details about the fix",
                "edit_format": "replace innerHTML with textContent and sanitize input",
                "rule_codes": ["xss", "dom"], "result": "pass",
                "failure_category": "security", "trace_file": "", "retrieval_count": 0,
            },
            {
                "id": "c3", "timestamp": _fresh_iso(1),
                "task": "completely different task about database indexing",
                "summary": "add index to user table",
                "edit_format": "CREATE INDEX",
                "rule_codes": ["db"], "result": "pass",
                "failure_category": "performance", "trace_file": "", "retrieval_count": 0,
            },
        ]
        with open(input_file, "w", encoding="utf-8", newline="\n") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        output_file = tmp / "compacted.jsonl"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["compact-memory.py"],
            "--input", input_file,
            "--output", output_file,
            "--similarity", "0.5",
            "--max-age-days", "30"
        )
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIsNotNone(data)
        self.assertEqual(data["total"], 3)
        # c1 和 c2 相似应合并（至少一条标记 merged_into），c3 独立保留
        self.assertGreaterEqual(data["merged"], 1, "c1/c2 应合并")
        # kept = 输出条目总数（包含被合并的源条目，它们带着 merged_into 标记）
        self.assertEqual(data["kept"], 3, "3 条都保留在输出中，其中至少一条带 merged_into")
        # 代表必须是最详细的一条（c2），c1 指向 c2——不能反过来
        out = [json.loads(l) for l in output_file.read_text(
            encoding="utf-8").strip().split("\n") if l]
        by_id = {e["id"]: e for e in out}
        self.assertNotIn("merged_into", by_id["c2"],
                         "最详细的 c2 应作为簇代表保留全文")
        self.assertEqual(by_id["c1"].get("merged_into"), "c2",
                         "较简略的 c1 应标记 merged_into=c2")

    def test_compact_aged_deletion(self):
        """超过 max-age-days 且 retrieval_count==0 的冷记忆应被删除。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-aged"
        tmp.mkdir(parents=True, exist_ok=True)
        input_file = tmp / "agent-memory.jsonl"
        old_ts = "2020-01-01T00:00:00"  # 永久性远期旧值（老化桶），不随时间过期
        entries = [
            {
                "id": "old1", "timestamp": old_ts,
                "task": "old fix never retrieved",
                "summary": "ancient", "edit_format": "old",
                "rule_codes": [], "result": "pass",
                "failure_category": "", "trace_file": "", "retrieval_count": 0,
            },
            {
                "id": "recent1", "timestamp": _fresh_iso(24),
                "task": "recent fix never retrieved",
                "summary": "fresh", "edit_format": "new",
                "rule_codes": [], "result": "pass",
                "failure_category": "", "trace_file": "", "retrieval_count": 0,
            },
        ]
        with open(input_file, "w", encoding="utf-8", newline="\n") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        output_file = tmp / "compacted.jsonl"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["compact-memory.py"],
            "--input", input_file,
            "--output", output_file,
            "--similarity", "0.9",
            "--max-age-days", "30"
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["deleted_aged"], 1, "old1 应被老化删除")
        self.assertEqual(data["kept"], 1, "recent1 应保留")

    def test_compact_missing_input_exit_2(self):
        """不存在的输入文件应 exit=2 且 stdout 仍是单个 JSON 文档。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-compact-missing"
        tmp.mkdir(parents=True, exist_ok=True)
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["compact-memory.py"],
            "--input", tmp / "nope.jsonl",
            "--output", tmp / "out.jsonl")
        self.assertEqual(rc, 2, "输入文件缺失属输入错误，应 exit=2")
        self.assertIn("error", data)

    def test_compact_empty_input(self):
        """空输入文件应正常返回零统计。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-compact-empty"
        tmp.mkdir(parents=True, exist_ok=True)
        input_file = tmp / "empty.jsonl"
        input_file.write_text("", encoding="utf-8")
        output_file = tmp / "out.jsonl"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["compact-memory.py"],
            "--input", input_file,
            "--output", output_file
        )
        self.assertEqual(rc, 0)
        self.assertIsNotNone(data)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["kept"], 0)

    def test_compact_merged_into_marker(self):
        """被合并的条目应在输出中标记 merged_into 和 merged_count。"""
        tmp = test_scripts.FIXTURE["tmp"] / "mem-merged"
        tmp.mkdir(parents=True, exist_ok=True)
        input_file = tmp / "agent-memory.jsonl"
        entries = [
            {
                "id": "a1", "timestamp": _fresh_iso(3),
                "task": "fix XSS innerHTML",
                "summary": "s1", "edit_format": "e1",
                "rule_codes": ["xss", "innerhtml"], "result": "pass",
                "failure_category": "security", "trace_file": "", "retrieval_count": 0,
            },
            {
                "id": "a2", "timestamp": _fresh_iso(2),
                "task": "fix XSS innerHTML attack",
                "summary": "s2 longer detail", "edit_format": "e2",
                "rule_codes": ["xss", "innerhtml", "dom"], "result": "pass",
                "failure_category": "security", "trace_file": "", "retrieval_count": 0,
            },
            {
                "id": "a3", "timestamp": _fresh_iso(1),
                "task": "fix XSS innerHTML third variant",
                "summary": "s3", "edit_format": "e3",
                "rule_codes": ["xss", "innerhtml"], "result": "pass",
                "failure_category": "security", "trace_file": "", "retrieval_count": 0,
            },
        ]
        with open(input_file, "w", encoding="utf-8", newline="\n") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        output_file = tmp / "compacted.jsonl"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["compact-memory.py"],
            "--input", input_file,
            "--output", output_file,
            "--similarity", "0.5"
        )
        self.assertEqual(rc, 0)
        output_lines = output_file.read_text(encoding="utf-8").strip().split("\n")
        # 至少有一条被合并
        merged_lines = [l for l in output_lines if "merged_into" in l]
        self.assertGreaterEqual(len(merged_lines), 1, "至少一条应标记 merged_into")
        out = [json.loads(l) for l in output_lines if l]
        by_id = {e["id"]: e for e in out}
        self.assertNotIn("merged_into", by_id["a2"],
                         "最详细的 a2 应作为簇代表保留全文")
        self.assertEqual(by_id["a1"].get("merged_into"), "a2")
        self.assertEqual(by_id["a3"].get("merged_into"), "a2")


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
