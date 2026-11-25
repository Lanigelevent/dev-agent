#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_gold_sample.py — gold/agent 扩样驱动器契约（离线，不触网不碰 docker）。

覆盖：参数错误退出码 2（含缺映射/预测实例点名）、断点续跑（台账 DONE
实例跳过零网络调用）与聚合计数；agent-sample.py 的补丁收集（同实例多版本
取最新）与 --dry-run 装配。
"""
import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace
from _scripts_common import run

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "skills" / "eval-harness" / "scripts" / "gold-sample.py"
AGENT = ROOT / "skills" / "eval-harness" / "scripts" / "agent-sample.py"
COST = ROOT / "skills" / "eval-harness" / "scripts" / "eval-cost-report.py"


def _valid_diff(tag):
    """构造一个结构合法的 unified diff（hunk 行数与头一致，可被 git apply）。

    round-48 起 agent-sample 做补丁结构自检，收集测试里的「补丁」必须是
    真 diff；tag 写进新增行，供断言辨认版本。
    """
    return ("diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1 +1 @@\n"
            "-value = 'old'\n"
            "+value = '%s'\n" % tag)


def _inputs():
    """自建临时目录产出 (tmp, map_csv, preds)；调用方负责 cleanup。"""
    tmp = tmpspace.create(prefix="gold-sample-test-")
    map_csv = Path(tmp) / "map.csv"
    map_csv.write_text(
        "instance_id,image\n"
        "demo-a-1,swebench/demo.x86_64_a-1:latest\n"
        "demo-a-2,swebench/demo.x86_64_a-2:latest\n",
        encoding="utf-8", newline="\n")
    preds = Path(tmp) / "preds.jsonl"
    rows = [{"instance_id": "demo-a-1", "model_name_or_path": "gold",
             "model_patch": "p"},
            {"instance_id": "demo-a-2", "model_name_or_path": "gold",
             "model_patch": "q"}]
    preds.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                               for r in rows) + "\n",
                     encoding="utf-8", newline="\n")
    return tmp, map_csv, preds


class TestGoldSample(unittest.TestCase):

    def test_param_errors_exit_2(self):
        tmp, map_csv, preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        missing = Path(tmp) / "absent-map.csv"
        rc, _, _, _ = run(GOLD, "--predictions", str(preds),
                          "--map", str(map_csv), "--out", tmp)
        self.assertEqual(rc, 2, "实例选择器缺省应参数错误")
        rc, _, _, _ = run(GOLD, "--instances", "demo-a-1",
                          "--predictions", str(preds),
                          "--map", str(missing), "--out", tmp)
        self.assertEqual(rc, 2, "映射缺失应参数错误")
        rc, data, _, _ = run(GOLD, "--instances", "demo-none",
                             "--predictions", str(preds),
                             "--map", str(map_csv), "--out", tmp)
        self.assertEqual(rc, 2, "缺映射/预测的实例必须点名报错")
        self.assertIn("demo-none", json.dumps(data, ensure_ascii=False))

    def test_ledger_resume_skips_done(self):
        tmp, map_csv, preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        out = Path(tmp) / "out"
        out.mkdir()
        (out / "gold-sample-ledger.json").write_text(json.dumps({
            "results": [
                {"instance_id": "demo-a-1", "state": "DONE",
                 "resolved": True},
                {"instance_id": "demo-a-2", "state": "DONE",
                 "resolved": False}]}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        rc, data, _, _ = run(GOLD, "--all-from", str(preds),
                             "--predictions", str(preds),
                             "--map", str(map_csv), "--out", str(out))
        self.assertEqual(rc, 0, str(data)[:300])
        self.assertEqual(data["done"], 2)
        self.assertEqual(data["resolved"], 1, "台账聚合计数正确")


class TestAgentSample(unittest.TestCase):
    """agent 侧口径驱动器：补丁收集 + 预测装配（不触网、不碰 docker）。"""

    def _patches(self, tmp):
        """构造补丁目录：demo-a-1（单版本）、demo-a-2（v2 新于 v1）。"""
        root = Path(tmp) / "patches"
        for name, body in (("demo-a-1", _valid_diff("patch-one")),
                           ("demo-a-2", _valid_diff("patch-old")),
                           ("demo-a-2-v2", _valid_diff("patch-new"))):
            d = root / name
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(body, encoding="utf-8",
                                           newline="\n")
        # 显式拉开 mtime（文件系统时间戳精度不足时不能靠「谁先建谁赢」）
        old = root / "demo-a-2" / "edits.patch"
        new = root / "demo-a-2-v2" / "edits.patch"
        os.utime(str(old), (1000000, 1000000))
        os.utime(str(new), (2000000, 2000000))
        # 空目录（无补丁）应被忽略
        (root / "demo-a-3").mkdir(parents=True)
        return root

    def test_param_errors_exit_2(self):
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        rc, _, _, _ = run(AGENT, "--patches", str(Path(tmp) / "absent"),
                          "--map", str(map_csv), "--out", tmp)
        self.assertEqual(rc, 2, "补丁目录缺失应参数错误")
        rc, _, _, _ = run(AGENT, "--patches", str(Path(tmp)),
                          "--map", str(Path(tmp) / "absent.csv"), "--out", tmp)
        self.assertEqual(rc, 2, "映射缺失应参数错误")

    def test_dry_run_collects_latest_version(self):
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        patches = self._patches(tmp)
        out = Path(tmp) / "out"
        rc, data, _, _ = run(AGENT, "--patches", str(patches),
                             "--map", str(map_csv), "--out", str(out),
                             "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300])
        self.assertEqual(sorted(data["instances"]), ["demo-a-1", "demo-a-2"],
                         "空目录应被忽略，实例名去版本后缀")
        preds = Path(data["predictions"])
        self.assertTrue(preds.is_file())
        rows = [json.loads(l) for l in
                preds.read_text(encoding="utf-8").splitlines() if l.strip()]
        got = {r["instance_id"]: r["model_patch"].strip() for r in rows}
        self.assertIn("patch-one", got["demo-a-1"])
        self.assertIn("patch-new", got["demo-a-2"],
                      "同实例多版本应取最新补丁")
        self.assertTrue(all(r["model_name_or_path"] for r in rows),
                        "预测必须带 model_name_or_path（harness 必需字段）")


    def test_stale_patch_is_recorded_not_silent(self):
        """最新版补丁为空 → 回退评旧版**不是错误，但必须可回答**（round-28 第 7 项）。

        v1.28.0 的实踩形态：本轮补丁因编辑未命中而为空，收集器静默拿上一版
        补丁去评，台账读起来像「这一版过了」。现在每例都要回报来源目录、
        被判空的更新版本、以及 code-task 的即时校验结论。
        """
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        # demo-a-2：v1 有补丁、v2（更新）补丁为空 → 评的是 v1，属 stale
        for name, body in (("demo-a-2", _valid_diff("patch-old")),
                           ("demo-a-2-v2", "")):
            d = root / name
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(body, encoding="utf-8", newline="\n")
        old = root / "demo-a-2" / "edits.patch"
        new = root / "demo-a-2-v2" / "edits.patch"
        os.utime(str(old), (1000000, 1000000))
        os.utime(str(new), (2000000, 2000000))
        # demo-a-1：单版本、非空，但带着「即时校验有告警」的清单 → flagged
        d1 = root / "demo-a-1"
        d1.mkdir(parents=True)
        (d1 / "edits.patch").write_text(_valid_diff("patch-one"),
                                        encoding="utf-8", newline="\n")
        (d1 / "task-manifest.json").write_text(json.dumps({
            "engine": "agent",
            "patch_validation": {"ok": False, "issues": [
                {"code": "non_ascii", "detail": "新增行含非 ASCII"}]}},
            ensure_ascii=False), encoding="utf-8", newline="\n")

        out = Path(tmp) / "out"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out),
                                "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["stale_patch"], ["demo-a-2"],
                         "只有「更新版本被判空」的例进 stale 名单")
        self.assertEqual(data["validation_flagged"], ["demo-a-1"],
                         "即时校验告警独立成名单，两类问题不混为一谈")
        preds = [json.loads(l) for l in Path(data["predictions"])
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        got = {r["instance_id"]: r["model_patch"].strip() for r in preds}
        self.assertIn("patch-old", got["demo-a-2"],
                      "反向验证锚：回退用旧补丁这件事本身仍要成立（不误判为无补丁）")

        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        by_id = {p["instance_id"]: p for p in prov["instances"]}
        self.assertEqual(by_id["demo-a-2"]["source_dir"], "demo-a-2")
        self.assertEqual(by_id["demo-a-2"]["newer_versions_empty"],
                         ["demo-a-2-v2"], "来源与被判空的版本都要留档")
        self.assertTrue(by_id["demo-a-2"]["stale_patch"])
        # 反向验证锚：正常最新版本（demo-a-1）不被误标 stale
        self.assertFalse(by_id["demo-a-1"]["stale_patch"],
                         "无更新空版本时不得误标，否则名单失去意义")
        self.assertEqual([], by_id["demo-a-1"]["newer_versions_empty"])
        self.assertEqual("non_ascii",
                         by_id["demo-a-1"]["patch_validation"]["issues"][0]["code"],
                         "上游 code-task 的校验结论要一路带到评测侧")

    def test_older_empty_version_is_not_stale(self):
        """比来源**更旧**的空版本不得误举 stale 旗（round-33 复核实踩）。

        真实补丁集上的形状：v2 无补丁文件（一轮被放弃的尝试），v3 已补齐——
        评的本来就是最新版 v3，旧空窗只是历史痕迹。旧实现把「任何非来源的空
        版本」都记进 newer_versions_empty，真实 20 例里 4 例被误标 stale。
        反向验证锚：把比较谓词退回「非来源即 newer」，本例立刻转红。
        """
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        # demo-b-1：v1 是空窗（无补丁文件），v2 有补丁且更新 → 评 v2，不 stale
        (root / "demo-b-1").mkdir(parents=True)
        d2 = root / "demo-b-1-v2"
        d2.mkdir(parents=True)
        (d2 / "edits.patch").write_text(_valid_diff("patch-new"),
                                        encoding="utf-8", newline="\n")
        # demo-c-1：v1 有补丁，v2 是空窗 → 回退评 v1，必须 stale（真形状不丢）
        for name, body in (("demo-c-1", _valid_diff("patch-old")),
                           ("demo-c-1-v2", "")):
            d = root / name
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(body, encoding="utf-8", newline="\n")

        out = Path(tmp) / "out"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out),
                                "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["stale_patch"], ["demo-c-1"],
                         "只有「比来源更新的版本被判空」才举 stale 旗")
        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        by_id = {p["instance_id"]: p for p in prov["instances"]}
        self.assertFalse(by_id["demo-b-1"]["stale_patch"],
                         "较旧的空版本是历史痕迹，不是「回退评旧补丁」")
        self.assertEqual(by_id["demo-b-1"]["older_versions_empty"],
                         ["demo-b-1"], "旧空窗仍要留档，只是不举旗")
        self.assertEqual(by_id["demo-b-1"]["newer_versions_empty"], [])
        self.assertEqual(by_id["demo-c-1"]["newer_versions_empty"],
                         ["demo-c-1-v2"], "真正的新版空窗一个都不能漏")

    def test_patch_integrity_blocks_test_hacking_and_keeps_cost_fields(self):
        """agent 侧与 deepswe 同口径：conftest 补丁不进预测、不计 resolved。

        反向验证锚：把 integrity 过滤摘掉，demo-e-2 会回到预测文件里；
        把 --allow-test-edits 的豁免关掉，第二跑的 e2 不会出现在预测里。
        """
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        clean = root / "demo-e-1"
        clean.mkdir(parents=True)
        (clean / "edits.patch").write_text(
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1 +1 @@\n"
            "-x = 1\n"
            "+x = 2\n", encoding="utf-8", newline="\n")
        (clean / "task-manifest.json").write_text(json.dumps({
            "engine": "agent", "rounds": 3, "edits": 2, "tests": "pass",
            "elapsed_sec": 12.5,
            "patch_validation": {"ok": True, "issues": []}},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        hack = root / "demo-e-2"
        hack.mkdir(parents=True)
        (hack / "edits.patch").write_text(
            "diff --git a/conftest.py b/conftest.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/conftest.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def pytest_collection_modifyitems(items):\n"
            "+    pass\n", encoding="utf-8", newline="\n")

        out = Path(tmp) / "out"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out),
                                "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["integrity_flagged"], ["demo-e-2"],
                         "conftest 钩子必须一票否决")
        self.assertEqual(data["evaluable"], ["demo-e-1"])
        preds = [json.loads(l) for l in Path(data["predictions"])
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual([r["instance_id"] for r in preds], ["demo-e-1"],
                         "被拦截的补丁不得进入官方评测")
        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        by_id = {p["instance_id"]: p for p in prov["instances"]}
        self.assertEqual(by_id["demo-e-2"]["patch_integrity"]["critical"][0]
                         ["code"], "interpreter_or_pytest_hook")
        summary = json.loads((out / "agent-sample-summary.json")
                             .read_text(encoding="utf-8"))
        det = {d["instance_id"]: d for d in summary["details"]}
        self.assertEqual(det["demo-e-2"]["status"], "integrity_flagged")
        self.assertIsNone(det["demo-e-2"]["resolved"],
                          "被拦截的补丁没有 resolved 判定，不是 False")
        self.assertEqual(det["demo-e-1"]["rounds"], 3)
        self.assertEqual(det["demo-e-1"]["edits"], 2)
        self.assertEqual(det["demo-e-1"]["code_task_elapsed_sec"], 12.5)
        self.assertFalse(summary["tokens"]["available"])

        out2 = Path(tmp) / "out-waived"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out2),
                                "--dry-run", "--allow-test-edits")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["integrity_flagged"], [])
        self.assertEqual(data["integrity_waived"], ["demo-e-2"])
        preds = [json.loads(l) for l in Path(data["predictions"])
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(sorted(r["instance_id"] for r in preds),
                         ["demo-e-1", "demo-e-2"])
        prov = json.loads((out2 / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        by_id = {p["instance_id"]: p for p in prov["instances"]}
        self.assertTrue(by_id["demo-e-2"]["patch_integrity"]["waived"],
                        "豁免后 critical 仍在，留审计痕迹")
        self.assertTrue(by_id["demo-e-2"]["patch_integrity"]["critical"])

    def test_malformed_patch_blocked_and_not_waivable(self):
        """截断补丁不进预测文件，也不被 --allow-test-edits 豁免（round-48）。

        实踩形状（django-11019）：补丁尾部缺失，完整性检查只看文件头与
        增删行，看不见「hunk 行数不符」；它照样进了预测文件，最终只能记
        F2P_MISSED——把「补丁坏了」混进「修错了」。反向验证锚：把
        _patch_well_formed 摘掉，malformed_patch 名单立刻变空。
        """
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        good = root / "demo-g-1"
        good.mkdir(parents=True)
        (good / "edits.patch").write_text(_valid_diff("good"),
                                          encoding="utf-8", newline="\n")
        bad = root / "demo-g-2"
        bad.mkdir(parents=True)
        (bad / "edits.patch").write_text(
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1,4 +1,8 @@\n"
            " import os\n"
            "-x = 1\n"
            "+x = 2\n", encoding="utf-8", newline="\n")

        out = Path(tmp) / "out"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out),
                                "--dry-run", "--allow-test-edits")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["malformed_patch"], ["demo-g-2"])
        self.assertEqual(data["evaluable"], ["demo-g-1"])
        self.assertEqual(data["integrity_waived"], [],
                         "结构损坏与测试改动性质不同，豁免开关不得放行")
        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        by_id = {p["instance_id"]: p for p in prov["instances"]}
        issues = by_id["demo-g-2"]["patch_well_formed"]["issues"]
        self.assertTrue(any("行数不符" in i for i in issues), issues)
        summary = json.loads((out / "agent-sample-summary.json")
                             .read_text(encoding="utf-8"))
        det = {d["instance_id"]: d for d in summary["details"]}
        self.assertEqual(det["demo-g-2"]["status"], "malformed_patch")
        self.assertIsNone(det["demo-g-2"]["resolved"])

    def test_all_patches_flagged_exits_1_without_eval(self):
        """全部补丁被拦截时如实退出 1，不把空预测喂给 harness。"""
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        d = root / "demo-f-1"
        d.mkdir(parents=True)
        (d / "edits.patch").write_text(
            "diff --git a/tests/test_x.py b/tests/test_x.py\n"
            "--- a/tests/test_x.py\n"
            "+++ b/tests/test_x.py\n"
            "@@ -1 +1 @@\n"
            "-def test_a():\n"
            "+def test_a():\n", encoding="utf-8", newline="\n")
        out = Path(tmp) / "out"
        rc, data, _o, _e = run(AGENT, "--patches", str(root),
                               "--map", str(map_csv), "--out", str(out))
        self.assertEqual(rc, 1)
        self.assertFalse(data["ok"])
        self.assertIn("完整性红线", data["error"])
        preds = Path(out) / "predictions-agent.jsonl"
        self.assertEqual(preds.read_text(encoding="utf-8").strip(), "")


class TestCandidateRanking(unittest.TestCase):
    """候选补丁证据排序：校验未过线的新版必须让位给过线的旧版（借 Agentless 排序）。

    反向验证锚：把排序键里的 `validation.get("ok") is not False` 摘掉
    （退回纯 mtime/ver），本测试立刻转红——新版校验不合格仍会赢。
    """

    def test_validation_failed_newer_loses_to_healthy_older(self):
        tmp, map_csv, _preds = _inputs()
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        # demo-d-1：v1 校验过线；v2 更新但 patch_validation.ok=false
        for name, body, ok in (("demo-d-1", _valid_diff("patch-good"), True),
                               ("demo-d-1-v2", _valid_diff("patch-bad"), False)):
            d = root / name
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(body, encoding="utf-8",
                                           newline="\n")
            (d / "task-manifest.json").write_text(json.dumps({
                "engine": "agent",
                "patch_validation": {"ok": ok, "issues": (
                    [] if ok else [{"code": "non_ascii", "detail": "x"}])}},
                ensure_ascii=False), encoding="utf-8", newline="\n")
        old = root / "demo-d-1" / "edits.patch"
        new = root / "demo-d-1-v2" / "edits.patch"
        os.utime(str(old), (1000000, 1000000))
        os.utime(str(new), (2000000, 2000000))

        out = Path(tmp) / "out"
        rc, data, _o, err = run(AGENT, "--patches", str(root),
                                "--map", str(map_csv), "--out", str(out),
                                "--dry-run")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        preds = [json.loads(l) for l in Path(data["predictions"])
                 .read_text(encoding="utf-8").splitlines() if l.strip()]
        got = {r["instance_id"]: r["model_patch"].strip() for r in preds}
        self.assertIn("patch-good", got["demo-d-1"],
                      "校验未过线的新版不许赢过过线的旧版")
        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        cand = {c["dir"]: c for c in
                prov["instances"][0]["candidates"]}
        self.assertTrue(cand["demo-d-1"]["chosen"])
        self.assertFalse(cand["demo-d-1-v2"]["chosen"])
        self.assertIn("校验未过线", cand["demo-d-1-v2"]["reason"],
                      "落选理由必须可复算")


class TestEvalCostReport(unittest.TestCase):
    """成本归一报告：三类产物并列 resolved/耗时/轮数，token 不可得不估算。"""

    def _write(self, tmp, name, data):
        path = Path(tmp) / name
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8", newline="\n")
        else:
            path.write_text(json.dumps(data, ensure_ascii=False),
                            encoding="utf-8", newline="\n")
        return path

    def test_gold_ledger_medians_and_token_na(self):
        tmp = Path(tmpspace.create(prefix="cost-report-"))
        self.addCleanup(tmpspace.release, tmp)
        ledger = self._write(tmp, "ledger.json", {"results": [
            {"instance_id": "a", "state": "DONE", "resolved": True,
             "elapsed_sec": 10, "code_task": {"rounds": 2, "edits": 3}},
            {"instance_id": "b", "state": "DONE", "resolved": False,
             "elapsed_sec": 20, "code_task": {"rounds": 4, "edits": 5}},
            {"instance_id": "c", "state": "EVAL_FAILED", "resolved": None,
             "elapsed_sec": 30},
        ]})
        out = Path(tmp) / "out"
        rc, data, _o, err = run(COST, "--input", str(ledger),
                                "--out", str(out), "--label", "unit")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        m = data["metrics"]
        self.assertEqual(m["samples"], 3)
        self.assertEqual(m["resolved"], 1)
        self.assertEqual(m["unresolved"], 1)
        self.assertEqual(m["undetermined"], 1)
        self.assertEqual(m["median_elapsed_sec"], 20)
        self.assertEqual(m["median_elapsed_resolved_sec"], 10)
        self.assertEqual(m["median_elapsed_unresolved_sec"], 20)
        self.assertEqual(m["elapsed_per_resolved_sec"], 60)
        self.assertEqual(m["median_rounds"], 3)
        self.assertEqual(m["median_edits"], 4)
        self.assertFalse(m["tokens"]["available"],
                         "无用量时必须标 N/A，不许估算")
        self.assertTrue(Path(data["report_md"]).is_file())
        md = Path(data["report_md"]).read_text(encoding="utf-8")
        self.assertIn("N/A", md)
        # 同日同名默认拒绝覆盖（报告是结案证据引用对象）
        rc2, data2, _o, _e = run(COST, "--input", str(ledger),
                                 "--out", str(out), "--label", "unit")
        self.assertEqual(rc2, 2)
        self.assertIn("拒绝覆盖", data2["error"])

    def test_agent_summary_integrity_counted_not_in_rate(self):
        tmp = Path(tmpspace.create(prefix="cost-agent-"))
        self.addCleanup(tmpspace.release, tmp)
        summary = self._write(tmp, "summary.json", {
            "tokens": {"available": False, "reason": "host 后端"},
            "details": [
                {"instance_id": "x", "status": "resolved", "resolved": True,
                 "elapsed_sec": 5, "rounds": 1, "edits": 2,
                 "patch_integrity": {"ok": True}},
                {"instance_id": "y", "status": "integrity_flagged",
                 "resolved": None, "elapsed_sec": None, "rounds": 3,
                 "edits": 4, "patch_integrity": {"ok": False}},
            ]})
        out = Path(tmp) / "out"
        rc, data, _o, err = run(COST, "--input", str(summary),
                                "--out", str(out), "--label", "agent")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        m = data["metrics"]
        self.assertEqual(m["samples"], 2)
        self.assertEqual(m["integrity_flagged"], 1)
        self.assertEqual(m["resolved"], 1)
        self.assertEqual(m["resolved_rate"], 0.5)
        self.assertEqual(m["median_rounds"], 2)
        self.assertEqual(m["median_elapsed_sec"], 5)

    def test_deepswe_shape_and_invalid_input(self):
        tmp = Path(tmpspace.create(prefix="cost-deepswe-"))
        self.addCleanup(tmpspace.release, tmp)
        results = self._write(tmp, "results.json", {"results": [
            {"id": "t1", "status": "resolved", "elapsed_sec": 8,
             "code_task": {"rounds": 2, "edits": 1}},
            {"id": "t2", "status": "integrity_flagged", "elapsed_sec": 4},
        ]})
        out = Path(tmp) / "out"
        rc, data, _o, err = run(COST, "--input", str(results),
                                "--out", str(out), "--label", "deepswe")
        self.assertEqual(rc, 0, str(data)[:300] + err[:300])
        self.assertEqual(data["kind"], "deepswe")
        self.assertEqual(data["metrics"]["resolved"], 1)
        self.assertEqual(data["metrics"]["integrity_flagged"], 1)
        bad = self._write(tmp, "bad.json", {"hello": "world"})
        rc, data, _o, _e = run(COST, "--input", str(bad), "--out", str(out),
                               "--label", "bad")
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])


class TestPlanDistill(unittest.TestCase):
    """修复计划蒸馏（round-34 阶段1-A）：只蒸馏 resolved 实例，数据取自产物。

    反向验证锚：把 resolved 过滤条件摘掉（未过实例也进原料），
    test_resolved_only_and_family_names 的 plans 立刻多出未过实例家族。
    """

    def test_resolved_only_and_family_names(self):
        tmp = tmpspace.create(prefix="plan-distill-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp) / "patches"
        # demo-d-1 resolved、demo-u-9 unresolved（后者不该进原料）
        for name, body in (("demo__demo-1", "diff --git a/django/db/x.py b/django/db/x.py\n"
                            "@@ -1 +1 @@ f\n-old\n+new\n"),
                           ("demo__demo-1-v2", "diff --git a/django/db/y.py b/django/db/y.py\n"
                            "@@ -1 +1 @@ g\n-a\n+b\n+c\n"),
                           ("unknown__u-9", "diff --git a/u/z.py b/u/z.py\n"
                            "@@ -1 +1 @@ h\n-q\n+w\n")):
            d = root / name
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(body, encoding="utf-8", newline="\n")
            (d / "task-manifest.json").write_text(json.dumps({
                "engine": "agent", "rounds": 2, "edits": 1}),
                encoding="utf-8", newline="\n")
        old_p = root / "demo__demo-1" / "edits.patch"
        new_p = root / "demo__demo-1-v2" / "edits.patch"
        os.utime(str(old_p), (1000000, 1000000))
        os.utime(str(new_p), (2000000, 2000000))
        caliber = Path(tmp) / "caliber.json"
        caliber.write_text(json.dumps({"detail": {
            "demo__demo-1": {"resolved": True},
            "unknown__u-9": {"resolved": False}}}), encoding="utf-8", newline="\n")
        out = Path(tmp) / "plans.json"
        rc, data, _o, err = run(ROOT / "skills" / "eval-harness" / "scripts"
                            / "plan-distill.py",
                                "--patches", str(root), "--caliber", str(caliber),
                                "--out", str(out))
        self.assertEqual(rc, 0, str(data)[:200] + err[:200])
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["resolved_count"], 1,
                         "未过实例不许进蒸馏原料")
        self.assertIn("demo", payload["plans"],
                      "仓库家族名取 __ 前缀全段（scikit-learn 不许截成 scikit）")
        # 选版口径与收集器同源：校验过线的最新非空版本（v2）
        detail = payload["details"][0]
        self.assertEqual(detail["source_dir"], "demo__demo-1-v2")
        self.assertEqual(detail["added_lines"], 2)
        self.assertEqual(detail["rounds"], 2, "轮数取自 manifest.rounds")


class TestGoldSamplePaths(unittest.TestCase):
    """驱动给 harness 的路径必须是绝对路径。

    背景（round-19 实踩）：harness 在 --cwd 下运行，若驱动传相对路径的
    predictions 文件，harness 侧直接 FileNotFoundError（表现为整批实例
    EVAL_FAILED 的基础设施失败，而非实例失败）。
    """

    def test_predictions_path_is_absolute(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gold_sample_mod", GOLD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        calls = []

        def fake_run(cmd, timeout=7200, input_text=None):
            calls.append([str(c) for c in cmd])
            return 0, {"ok": True}, ""

        mod._run = fake_run
        mod.image_loaded = lambda image: True
        argv = argparse.Namespace(
            out=str(tmpspace.create(prefix="gold-abs-")), force=False,
            mirror="docker.1ms.run", retries=1, segments=1, workers=1,
            eval_timeout=60, cwd="datasets/swe-out/harness", run_prefix="t")
        mod.process_instance("demo-a-1", "img:latest",
                             {"instance_id": "demo-a-1",
                              "model_name_or_path": "m", "model_patch": "p"},
                             argv)
        eval_calls = [c for c in calls if "eval" in c]
        self.assertTrue(eval_calls, "应调用过 eval")
        cmd = eval_calls[0]
        idx = cmd.index("--predictions")
        self.assertTrue(Path(cmd[idx + 1]).is_absolute(),
                        "predictions 必须是绝对路径: %s" % cmd[idx + 1])
        idx = cmd.index("--cwd")
        self.assertTrue(Path(cmd[idx + 1]).is_absolute(),
                        "cwd 必须是绝对路径: %s" % cmd[idx + 1])


class TestEvalDiagnosis(unittest.TestCase):
    """评测结果失败归因（round-21：让每次返工拿到可执行结论）。"""

    def _report(self, tmp, payload):
        run_dir = tmp / "logs" / "run_evaluation" / "r1" / "m1" / "demo__x"
        run_dir.mkdir(parents=True)
        (run_dir / "report.json").write_text(
            json.dumps({"demo__x": payload}), encoding="utf-8", newline="\n")
        return tmp / "logs" / "run_evaluation"

    def _diagnose(self, payload):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "swe_run_mod", ROOT / "agent" / "swe_run.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.diagnose({
            "patch_successfully_applied": payload.get(
                "patch_successfully_applied", True),
            "fail_to_pass": payload.get("fail_to_pass", {"pass": 1, "fail": 0}),
            "pass_to_pass": payload.get("pass_to_pass", {"pass": 1, "fail": 0}),
            "error": payload.get("error", ""),
        })

    def test_diagnosis_buckets(self):
        self.assertEqual(self._diagnose({"fail_to_pass": {"pass": 1, "fail": 0},
                                         "pass_to_pass": {"pass": 1, "fail": 0}}),
                         "RESOLVED")
        self.assertEqual(self._diagnose({"fail_to_pass": {"pass": 0, "fail": 1},
                                         "pass_to_pass": {"pass": 2, "fail": 0}}),
                         "F2P_MISSED")
        self.assertEqual(self._diagnose({"fail_to_pass": {"pass": 0, "fail": 1},
                                         "pass_to_pass": {"pass": 1, "fail": 2}}),
                         "REGRESSION")
        self.assertEqual(self._diagnose({"patch_successfully_applied": False,
                                         "fail_to_pass": {"pass": 0, "fail": 1},
                                         "pass_to_pass": {"pass": 1, "fail": 0}}),
                         "PATCH_APPLY_FAILED")
        self.assertEqual(self._diagnose({"fail_to_pass": {"pass": 0, "fail": 1},
                                         "pass_to_pass": {"pass": 1, "fail": 0},
                                         "error": "ImportError: boom"}),
                         "PATCH_BROKE_MODULE")


class TestProLiveBaselines(unittest.TestCase):
    """Pro/Live 试点基线：独立文件、10 条 Python、全 not_run（不许伪报）。"""

    def _load(self, name):
        path = ROOT / "reports" / "swebench" / name
        self.assertTrue(path.is_file(), "基线不存在: %s" % path)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_baselines_have_ten_python_not_run(self):
        for name in ("pro-baseline-v1.49.0.json",
                     "live-baseline-v1.49.0.json"):
            data = self._load(name)
            self.assertEqual(data["version"], "v1.49.0")
            self.assertEqual(data["status"], "not_run")
            instances = data["instances"]
            self.assertGreaterEqual(len(instances), 10,
                                    "%s 应含至少 10 条" % name)
            # 仓库分散度按实测下限钉住，不虚构：Pro default 的 Python 子集
            # 实测只有 3 个仓库（ansible / openlibrary / qutebrowser），
            # Live lite 是 10 仓各 1 条。钉「≥3」防的是退化到单仓刷样，
            # 不是要求凑齐 10 仓（凑不出来还钉 10 等于逼人改数据）。
            repos = {i["repo"] for i in instances}
            self.assertGreaterEqual(
                len(repos), 3,
                "%s 试点至少跨 3 个仓库（实测下限），当前: %s"
                % (name, sorted(repos)))
            if name.startswith("live"):
                self.assertEqual(len(repos), len(instances),
                                 "Live 试点应每仓 1 条，不重复取样")
            for inst in instances:
                self.assertEqual(inst["language"], "python")
                self.assertEqual(inst["status"], "not_run")
                self.assertIsNone(inst["resolved"],
                                  "没跑就必须是 None，不是 False")
                self.assertTrue(inst["instance_id"])
                self.assertTrue(inst["base_commit"])
            src = data["source"]
            self.assertEqual(len(src["sha256"]), 64, "源文件指纹缺失")
            self.assertGreater(src["bytes"], 0)
            self.assertIn("hf-mirror", src["mirror"],
                          "数据下载必须记录国内镜像（硬约束 8）")
            self.assertIn("selection_rule", data)

    def test_pro_has_images_live_has_test_cmds(self):
        pro = self._load("pro-baseline-v1.49.0.json")
        self.assertTrue(all(i.get("docker_image") for i in pro["instances"]),
                        "Pro 实例应带预构建镜像")
        live = self._load("live-baseline-v1.49.0.json")
        self.assertTrue(all(i.get("test_cmds") for i in live["instances"]),
                        "Live 无镜像，必须带 test_cmds")


class TestDeepSWE(unittest.TestCase):
    """DeepSWE 基线 + 回归测试（离线结构校验，不触网不碰 docker）。

    基线 JSON：reports/deepswe/baseline-v1.44.0.json
    回归集：10 个 Python 任务，每次改 code-task 配置或换模型后跑一遍。
    实际评测（需 Docker + LLM API）通过环境变量 DEEPSWE_RUN=1 触发，
    默认跳过。
    """

    BASELINE = ROOT / "reports" / "deepswe" / "baseline-v1.44.0.json"
    JSONL = ROOT / "skills" / "eval-harness" / "data" / "deepswe-tasks.jsonl"
    DEEPSWE_SAMPLE = ROOT / "skills" / "eval-harness" / "scripts" / "deepswe-sample.py"

    def test_baseline_exists_and_valid(self):
        """基线 JSON 存在且结构合法。"""
        self.assertTrue(self.BASELINE.is_file(),
                        "基线文件不存在: %s" % self.BASELINE)
        data = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], "v1.44.0")
        self.assertEqual(data["benchmark"][:7], "DeepSWE")
        self.assertGreaterEqual(len(data["tasks"]), 20,
                                "基线应含至少 20 个任务")
        self.assertEqual(len(data["regression_ids"]), 10,
                         "回归集应含 10 个任务 ID")
        for t in data["tasks"]:
            for key in ("id", "language", "category", "repo",
                        "status", "resolved"):
                self.assertIn(key, t, "任务缺字段 %s" % key)

    @unittest.skipUnless(JSONL.is_file(),
                         "deepswe-tasks.jsonl 未就位（gate 语料不入库，"
                         "由 deepswe-fetch.py 本地生成）")
    def test_regression_ids_in_jsonl(self):
        """回归集 10 个 ID 在 deepswe-tasks.jsonl 中存在。"""
        jsonl_ids = set()
        with self.JSONL.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    jsonl_ids.add(json.loads(line)["id"])
        data = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        for rid in data["regression_ids"]:
            self.assertIn(rid, jsonl_ids,
                          "回归 ID %s 不在 JSONL 中" % rid)

    def test_baseline_tasks_are_python(self):
        """基线 20 个任务全部是 Python 语言。"""
        data = json.loads(self.BASELINE.read_text(encoding="utf-8"))
        for t in data["tasks"]:
            self.assertEqual(t["language"], "python",
                             "%s 不是 Python 任务" % t["id"])

    def test_deepswe_sample_script_exists(self):
        """deepswe-sample.py 存在且语法合法。"""
        self.assertTrue(self.DEEPSWE_SAMPLE.is_file())
        import ast
        ast.parse(self.DEEPSWE_SAMPLE.read_text(encoding="utf-8"))

    @staticmethod
    def _module():
        """按路径加载 deepswe-sample.py（文件名带连字符，不能直接 import）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "deepswe_sample", TestDeepSWE.DEEPSWE_SAMPLE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_verdict_requires_reward_one(self):
        """退出码 0 但 reward=0/缺失不得判 resolved（round-46 实踩回归）。"""
        mod = self._module()
        self.assertEqual(mod._verdict(0, 1), (True, ""))
        self.assertEqual(mod._verdict(0, 0), (False, "reward=0"))
        self.assertEqual(mod._verdict(0, None), (False, "reward=None"))
        self.assertEqual(mod._verdict(8, None),
                         (False, "patch apply failed"),
                         "补丁注入失败不是 resolved，也不是环境失败")
        self.assertEqual(mod._verdict(5, 0), (False, "verifier exit 5"))

    def test_structural_gate_marks_malformed_and_skips_eval(self):
        """结构闸接线：deepswe 流程本身也拦截断补丁（不只是 agent-sample）。

        反向锚：把 main 里的 `_apply_structural_gate` 调用摘掉（或让函数恒
        返回 True），本测试仍能过但 doc-drift Q3 会把该函数报成死代码；
        真正的行为断言在 agent-sample 的 malformed 用例里。
        """
        mod = self._module()
        tmp = Path(tmpspace.create(prefix="deepswe-struct-"))
        self.addCleanup(tmpspace.release, tmp)
        good = tmp / "good.patch"
        good.write_text(_valid_diff("ok") + "\n", encoding="utf-8",
                        newline="\n")
        res = {"instance_id": "demo-good"}
        self.assertTrue(mod._apply_structural_gate(res, good))
        self.assertTrue(res["patch_well_formed"]["ok"])

        bad = tmp / "bad.patch"
        bad.write_text(
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-a\n"
            "+b\n", encoding="utf-8", newline="\n")
        res2 = {"instance_id": "demo-bad"}
        self.assertFalse(mod._apply_structural_gate(res2, bad))
        self.assertEqual(res2["status"], "malformed_patch")
        self.assertIn("截断", res2["error"])

    def test_stage_tests_normalizes_crlf_only_in_copy(self):
        """语料 CRLF 只在暂存副本归一化；语料不动，二进制原样保留。"""
        mod = self._module()
        tmp = Path(tmpspace.create(prefix="deepswe-stage-"))
        self.addCleanup(tmpspace.release, tmp)
        src = tmp / "tests"
        src.mkdir()
        (src / "test.sh").write_bytes(b"#!/bin/bash\r\nset -e\r\n")
        (src / "fixture.bin").write_bytes(b"\x00\r\n\x01")
        stage = tmp / "stage"
        out = mod._stage_tests(src, stage)
        self.assertEqual(Path(out), stage)
        self.assertEqual((stage / "test.sh").read_bytes(),
                         b"#!/bin/bash\nset -e\n")
        self.assertEqual((src / "test.sh").read_bytes(),
                         b"#!/bin/bash\r\nset -e\r\n", "语料不得被改动")
        self.assertEqual((stage / "fixture.bin").read_bytes(),
                         b"\x00\r\n\x01", "含 NUL 的二进制原样保留")

    def test_patch_well_formed_detects_truncation(self):
        """hunk 行数与该头声明一致才算结构合法；截断/无 hunk 一律拦下。"""
        mod = self._module()
        tmp = Path(tmpspace.create(prefix="deepswe-wellformed-"))
        self.addCleanup(tmpspace.release, tmp)

        def check(name, body):
            p = tmp / name
            p.write_text(body, encoding="utf-8", newline="\n")
            return mod._patch_well_formed(p)

        ok = check("ok.patch", _valid_diff("x"))
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["hunks"], 1)

        # 声明 -1,4 +1,8，实际只给 3 行新/2 行旧 → 截断
        truncated = check("trunc.patch", (
            "diff --git a/pkg/mod.py b/pkg/mod.py\n"
            "--- a/pkg/mod.py\n"
            "+++ b/pkg/mod.py\n"
            "@@ -1,4 +1,8 @@\n"
            " import os\n"
            "-x = 1\n"
            "+x = 2\n"))
        self.assertFalse(truncated["ok"], truncated)
        self.assertTrue(any("行数不符" in i for i in truncated["issues"]),
                        truncated)

        no_hunk = check("nohunk.patch", "diff --git a/a b/a\n")
        self.assertFalse(no_hunk["ok"], no_hunk)
        self.assertIn("无任何 hunk", no_hunk["issues"][0])

    def test_docker_path_conversion(self):
        """Windows 盘符路径映射为 Docker Desktop 挂载路径。"""
        mod = self._module()
        self.assertEqual(mod._to_docker_path("C:\\Users\\a\\b"),
                         "//c/Users/a/b")
        self.assertEqual(mod._to_docker_path("c:/x/y"), "//c/x/y")
        self.assertEqual(mod._to_docker_path("/unix/path"), "/unix/path")

    def test_seed_submodules_fails_closed_without_docker(self):
        """无 docker 时任凭子模块缺失都返回 False（不谎报就绪）。"""
        mod = self._module()
        self.assertFalse(
            mod._seed_submodules_from_image("", "image", ROOT))

    def test_patch_integrity_flags_test_hacking(self):
        """补丁完整性：测试基础设施/既有测试改动不参加 resolved（反向验证）。"""
        mod = self._module()
        tmp = Path(tmpspace.create(prefix="deepswe-integrity-"))
        self.addCleanup(tmpspace.release, tmp)

        def patch(name, body):
            p = tmp / name
            p.write_text(body, encoding="utf-8", newline="\n")
            return mod._patch_integrity(p)

        clean = patch("clean.patch", (
            "diff --git a/tomlkit/convert.py b/tomlkit/convert.py\n"
            "--- a/tomlkit/convert.py\n"
            "+++ b/tomlkit/convert.py\n"
            "@@ -1 +1 @@\n"
            "-x = 1\n"
            "+x = 2\n"))
        self.assertTrue(clean["ok"], clean)
        self.assertEqual(clean["added_lines"], 1)
        self.assertEqual(clean["files"], 1)
        self.assertIn("tomlkit/convert.py", clean["touched"])

        hook = patch("hook.patch", (
            "diff --git a/conftest.py b/conftest.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/conftest.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def pytest_collection_modifyitems(items):\n"
            "+    pass\n"))
        self.assertFalse(hook["ok"], "conftest 钩子必须一票否决")
        self.assertEqual(hook["critical"][0]["code"],
                         "interpreter_or_pytest_hook")

        modified_test = patch("testmod.patch", (
            "diff --git a/tests/test_convert.py b/tests/test_convert.py\n"
            "--- a/tests/test_convert.py\n"
            "+++ b/tests/test_convert.py\n"
            "@@ -1 +1 @@\n"
            "-def test_a():\n"
            "+def test_a():\n"))
        self.assertFalse(modified_test["ok"], "改既有测试必须一票否决")
        self.assertEqual(modified_test["critical"][0]["code"],
                         "test_file_modified")

        quoted = patch("quoted.patch", (
            'diff --git "a/tests/test spaced.py" "b/tests/test spaced.py"\n'
            '--- "a/tests/test spaced.py"\n'
            '+++ "b/tests/test spaced.py"\n'
            "@@ -1 +1 @@\n"
            "-def test_a():\n"
            "+def test_a():\n"))
        self.assertFalse(quoted["ok"],
                         "含空格路径被 git 加引号后仍须识别为测试文件")
        self.assertEqual(quoted["critical"][0]["code"],
                         "test_file_modified")

        new_test = patch("newtest.patch", (
            "diff --git a/tests/test_new.py b/tests/test_new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/tests/test_new.py\n"
            "@@ -0,0 +1 @@\n"
            "+def test_new():\n"))
        self.assertTrue(new_test["ok"], "新增测试只记 warning，不否决")
        self.assertEqual(new_test["warnings"][0]["code"], "new_test_file")

        cfg = patch("pytestini.patch", (
            "diff --git a/pytest.ini b/pytest.ini\n"
            "--- a/pytest.ini\n"
            "+++ b/pytest.ini\n"
            "@@ -1 +1,2 @@\n"
            " [pytest]\n"
            "+addopts = -p no:cacheprovider\n"))
        self.assertFalse(cfg["ok"], "pytest 配置改动必须一票否决")
        self.assertEqual(cfg["critical"][0]["code"], "pytest_config")

        site = patch("site.patch", (
            "diff --git a/sitecustomize.py b/sitecustomize.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/sitecustomize.py\n"
            "@@ -0,0 +1 @@\n"
            "+import os\n"))
        self.assertFalse(site["ok"], "解释器启动钩子必须一票否决")

    def test_code_task_stats_reads_manifest(self):
        """成本指标：轮数/编辑数/编码墙钟从 task-manifest.json 读取。"""
        mod = self._module()
        tmp = Path(tmpspace.create(prefix="deepswe-stats-"))
        self.addCleanup(tmpspace.release, tmp)
        (tmp / "task-manifest.json").write_text(json.dumps({
            "rounds": 3, "edits": 5, "tests": "pass",
            "elapsed_sec": 9.25}), encoding="utf-8")
        self.assertEqual(mod._code_task_stats(tmp),
                         {"rounds": 3, "edits": 5, "tests": "pass",
                          "elapsed_sec": 9.25})
        # 旧 manifest 无 elapsed_sec：字段缺省不报错（历史产物照常可读）
        old = tmp / "old"
        old.mkdir()
        (old / "task-manifest.json").write_text(json.dumps({
            "rounds": 1, "edits": 1, "tests": "skip"}), encoding="utf-8")
        self.assertEqual(mod._code_task_stats(old),
                         {"rounds": 1, "edits": 1, "tests": "skip"})
        self.assertEqual(mod._code_task_stats(tmp / "missing"), {})

    @unittest.skipUnless(os.environ.get("DEEPSWE_RUN"),
                         "需 DEEPSWE_RUN=1 + Docker + LLM API")
    def test_regression_live(self):
        """实跑回归集（慢，需 Docker + LLM API）。

        设 DEEPSWE_RUN=1 触发：跑 10 个回归任务，resolved >= 3。
        """
        rc, data, _, _ = run(self.DEEPSWE_SAMPLE,
                             "--jsonl", str(self.JSONL),
                             "--out", str(ROOT / "datasets" / "deepswe-regression"),
                             "--lang", "python")
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(data["total"], 10)
        self.assertGreaterEqual(data["resolved"], 3,
                                "回归集 resolved 应 >= 3")


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
