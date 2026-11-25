#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_approval.py — 审核人两道闸契约断言（独立第三方，不得自审自批）。

闸 1：范围裁定（白名单 ∩ 严重度政策 → 工单）；
闸 2：补丁准出（五项独立检查 → 批准书），含被篡改补丁的反向验证。
"""

import json
import unittest
from pathlib import Path

import _scripts_common as test_scripts
from _scripts_common import SCRIPTS
from test_repair import ALL_DEFECTS, _chain, _git, _git_commit_all, _make_repo

ROOT = Path(__file__).resolve().parents[1]


class TestApproval(unittest.TestCase):
    """审核人：工单签发 / 批准书签发 / 篡改拒绝。"""

    def test_gate1_severity_policy(self):
        """闸 1 政策：--severities 高 时，中严重度白名单缺陷被拒并给政策原因。

        白名单严重度实况：dang-yaml-load 为高，其余 4 类 lang 规则为中。
        """
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        rc, data, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"], "--findings",
                                          findings, "--repo", repo, "--out",
                                          tmp / "ap", "--severities", "高")
        self.assertEqual(rc, 0)
        order = json.loads((tmp / "ap" / "work-order.json").read_text(encoding="utf-8"))
        self.assertEqual([e["rule_id"] for e in order["approved"]],
                         ["dang-yaml-load"])
        self.assertEqual(len(order["rejected"]), 4)
        self.assertIn("严重度不在政策内", order["rejected"][0]["reason"])
        # 不带政策时白名单缺陷全部放行
        rc, data, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"], "--findings",
                                          findings, "--repo", repo, "--out",
                                          tmp / "ap2")
        order2 = json.loads((tmp / "ap2" / "work-order.json").read_text(encoding="utf-8"))
        self.assertEqual(len(order2["approved"]), 5)
        self.assertEqual(order2["rejected"], [])

    def test_gate2_rejects_foreign_rule(self):
        """闸 2 工单绑定：补丁清单夹带工单外规则 → REJECTED，落盘被拒。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, _approval = _chain(self, repo, findings, tmp)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["files"][0]["rules"] = sorted(set(data["files"][0]["rules"]) | {"dang-eval"})
        manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
        rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"], "--order",
                                           _order, "--manifest", manifest,
                                           "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 1)
        self.assertEqual(gate2["verdict"], "REJECTED")
        self.assertTrue(any("工单外规则" in r for r in gate2["reasons"]))
        # 主观能动性：拒绝时必须附案例复用建议字段（可能为空，键必须在）
        self.assertIn("reuse_hints", gate2)
        rc, apply_out, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"], "--manifest", manifest, "--repo", repo,
            "--approval", tmp / "ap" / "approval.json", "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("非 APPROVED", apply_out.get("error", ""))

    def test_gate2_rejects_credential_in_added_lines(self):
        """闸 2 内容红线：补丁新增行引入凭据形态 → REJECTED（红线 5）。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, _approval = _chain(self, repo, findings, tmp)
        patch = tmp / "out" / manifest_json(manifest)["files"][0]["patch_file"]
        text = patch.read_text(encoding="utf-8")
        text += ("+import os\n"
                 "+password = " + '"' + test_scripts.SECRET + '"\n')
        patch.write_text(text, encoding="utf-8", newline="\n")
        rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"], "--order",
                                           _order, "--manifest", manifest,
                                           "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 1)
        self.assertEqual(gate2["verdict"], "REJECTED")
        self.assertTrue(any("新增行" in r for r in gate2["reasons"]))

    def test_gate2_rejects_base_sha_drift(self):
        """闸 2 基线一致：工单签发后仓库前进 → REJECTED。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, _approval = _chain(self, repo, findings, tmp)
        (repo / "extra.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
        self.assertEqual(_git_commit_all(repo, "next"), 0)
        rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"], "--order",
                                           _order, "--manifest", manifest,
                                           "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 1)
        self.assertEqual(gate2["verdict"], "REJECTED")
        self.assertTrue(any("基线不一致" in r for r in gate2["reasons"]))

    def test_gate2_rejects_foreign_import(self):
        """闸 2 结构不变量：补丁新增白名单外导入 → REJECTED（第六项检查）。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, _approval = _chain(self, repo, findings, tmp)
        patch = tmp / "out" / manifest_json(manifest)["files"][0]["patch_file"]
        text = patch.read_text(encoding="utf-8")
        text += "+import requests\n"
        patch.write_text(text, encoding="utf-8", newline="\n")
        rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"], "--order",
                                           _order, "--manifest", manifest,
                                           "--repo", repo, "--out", tmp / "ap")
        self.assertEqual(rc, 1)
        self.assertEqual(gate2["verdict"], "REJECTED")
        self.assertTrue(any("白名单外导入" in r for r in gate2["reasons"]))
        # 六项检查齐全
        self.assertEqual(len(gate2["checks"]), 6)

    def test_apply_log_records_approval(self):
        """落盘台账必须记录批准书出处（审计可回溯）。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 0)
        log = json.loads((tmp / "out" / "apply-log.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(log["approval"]), approval.resolve())

    def test_approval_scripts_self_scan_zero(self):
        """审核人脚本自身纳入自扫（红线 6 的自指检查）；批扫口径（D-049 C）。"""
        names = ("approve-plan.py", "approve-patch.py")
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


def manifest_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
