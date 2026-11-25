#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_repair.py — 修复团队（补丁先行 / 五道闸 / 回滚 / undo）契约断言。

红线 6（每个检查器都要有反向验证）落到 test_per_rule_reversal：
白名单 5 类缺陷逐个走 闸1→出补丁→闸2→落盘→复扫，确认规则消失且零新增。
缺陷样例一律运行时拼接敏感 token，本文件不落危险调用字面量。
"""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace
from _scripts_common import SCRIPTS

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "skills" / "approval" / "scripts"

# 运行时拼接：yaml.load 与 eval 的调用字面量不出现在本源码中
YAML_LOAD_CALL = "yaml." + "load(p)"
EVAL_CALL = "ev" + "al(x)"

RULE_FIXTURES = {
    "lang-mutable-default": "def f(a=[]):\n    return a\n",
    "lang-empty-catch": "def f():\n    try:\n        return 1\n    except:\n        pass\n",
    "lang-closure-late-bind": ("def make():\n    out = []\n"
                               "    for i in range(3):\n"
                               "        out.append(lambda: i)\n"
                               "    return out\n"),
    "lang-is-literal-misuse": "def f(x):\n    return x == None\n",
    "dang-yaml-load": "import yaml\n\n\ndef f(p):\n    return " + YAML_LOAD_CALL + "\n",
}
UNFIXABLE_FIXTURE = "def f(x):\n    return " + EVAL_CALL + "\n"
ALL_DEFECTS = "".join(RULE_FIXTURES.values())


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _git_commit_all(repo, message):
    rc, _ = _git(repo, ["add", "-A"])
    if rc != 0:
        return rc
    return _git(repo, ["-c", "user.name=t", "-c", "user.email=t@t",
                       "commit", "-q", "-m", message])[0]


def _make_repo(self, source):
    """临时 git 仓库 + 缺陷文件 + 扫描发现清单。"""
    tmp = tmpspace.create(prefix="repair-")
    self.addCleanup(tmpspace.release, tmp)
    repo = tmp / "repo"
    repo.mkdir()
    (repo / "defects.py").write_text(source, encoding="utf-8", newline="\n")
    _git(repo, ["init", "-q"])
    self.assertEqual(_git_commit_all(repo, "init"), 0)
    rc, data, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                      "--file", repo / "defects.py")
    self.assertEqual(rc, 0)
    findings_path = tmp / "findings.json"
    findings_path.write_text(json.dumps(data, ensure_ascii=False),
                             encoding="utf-8", newline="\n")
    return repo, findings_path, tmp


def _shutil_rmtree(path):
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def _chain(self, repo, findings, tmp):
    """三方链：闸1 范围裁定 → 修复出补丁 → 闸2 补丁准出。返回关键产物路径。"""
    rc, plan, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"], "--findings",
                                      findings, "--repo", repo, "--out", tmp / "ap")
    self.assertEqual(rc, 0, json.dumps(plan, ensure_ascii=False)[:300])
    order = tmp / "ap" / "work-order.json"
    rc, patch, _, _ = test_scripts.run(SCRIPTS["fix-patch.py"], "--order", order,
                                       "--repo", repo, "--out", tmp / "out")
    self.assertEqual(rc, 0, json.dumps(patch, ensure_ascii=False)[:300])
    manifest = tmp / "out" / "fix-manifest.json"
    rc, gate2, _, _ = test_scripts.run(SCRIPTS["approve-patch.py"], "--order",
                                       order, "--manifest", manifest,
                                       "--repo", repo, "--out", tmp / "ap")
    self.assertEqual(rc, 0, json.dumps(gate2, ensure_ascii=False)[:400])
    self.assertEqual(gate2["verdict"], "APPROVED")
    return order, manifest, tmp / "ap" / "approval.json"


class TestRepair(unittest.TestCase):
    """三方链路：工单 / 补丁 / 批准书 / 落盘 / 回滚 / 撤销。"""

    def test_whitelist_agreement(self):
        """fix-plan 与 fix-patch 的白名单必须成对一致（双向维护防漂移）。"""
        import importlib.util
        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, str(path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        plan = load("fix_plan", SCRIPTS["fix-plan.py"])
        patch = load("fix_patch", SCRIPTS["fix-patch.py"])
        self.assertEqual(sorted(plan.FIXABLE_RULES), sorted(patch.AUTO_RULES))

    def test_per_rule_reversal(self):
        """红线 6：每类白名单缺陷修复后，该文件复扫必须零发现。"""
        for rule_id, source in RULE_FIXTURES.items():
            with self.subTest(rule_id=rule_id):
                repo, findings, tmp = _make_repo(self, source)
                _order, manifest, approval = _chain(self, repo, findings, tmp)
                rc, data, _, _ = test_scripts.run(
                    SCRIPTS["fix-apply.py"], "--manifest", manifest,
                    "--repo", repo, "--approval", approval, "--apply")
                self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
                self.assertEqual(data["state"], "APPLIED")
                rc, rescanned, _, _ = test_scripts.run(
                    SCRIPTS["deterministic-rules.py"], "--file", repo / "defects.py")
                self.assertEqual(rc, 0)
                self.assertEqual(rescanned["findings"], [],
                                 "%s 修复后仍有发现" % rule_id)

    def test_full_chain_and_undo(self):
        """5 类缺陷合成文件：预检不写盘 → 持批准书落盘 APPLIED → undo。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertEqual(data["state"], "PROPOSED")
        self.assertEqual(_git(repo, ["status", "--porcelain"])[1], "",
                         "预检不得改动工作树")
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["state"], "APPLIED")
        self.assertTrue(data["branch"].startswith("review-fix/"))
        rc, rescanned, _, _ = test_scripts.run(SCRIPTS["deterministic-rules.py"],
                                               "--file", repo / "defects.py")
        self.assertEqual(rescanned["findings"], [])
        self.assertTrue((tmp / "out" / "apply-log.json").is_file())
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo, "--undo")
        self.assertEqual(rc, 0)
        self.assertEqual(data["state"], "UNDONE")
        self.assertEqual(_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])[1],
                         "master")
        self.assertNotIn("review-fix/", _git(repo, ["branch"])[1])

    def test_apply_guards(self):
        """守卫：脏工作树与 base sha 漂移都拒绝落盘（rc=2）。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        (repo / "dirty.txt").write_text("x\n", encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("工作树不干净", data.get("error", ""))
        (repo / "dirty.txt").unlink()
        (repo / "extra.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
        self.assertEqual(_git_commit_all(repo, "next"), 0)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("base_sha", data.get("error", ""))

    def test_apply_requires_approval(self):
        """第五道闸：无批准书或 REJECTED 批准书都不得落盘。"""
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        # 无批准书
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("批准书", data.get("error", ""))
        # 篡改 manifest 后旧批准书因 sha256 绑定失效
        data_json = json.loads(manifest.read_text(encoding="utf-8"))
        data_json["skipped"] = [{"note": "tampered"}]
        manifest.write_text(json.dumps(data_json, ensure_ascii=False, indent=2),
                            encoding="utf-8", newline="\n")
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("sha256", data.get("error", ""))

    def test_tests_gate(self):
        """闸五行为回归：仓库测试失败必须回滚；通过则 APPLIED 并记录测试态。"""
        # 失败测试 → ROLLED_BACK（测试文件先提交，保持工作树干净）
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_bad.py").write_text(
            "def test_always_fails():\n    assert False\n",
            encoding="utf-8", newline="\n")
        self.assertEqual(_git_commit_all(repo, "tests"), 0)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 1)
        self.assertEqual(data["state"], "ROLLED_BACK")
        self.assertIn("测试", data.get("error", ""))
        # 主观能动性：回滚时必须主动附案例复用建议字段（可能为空，键必须在）
        self.assertIn("reuse_hints", data)
        log = json.loads((tmp / "out" / "apply-log.json").read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "ROLLED_BACK")
        self.assertEqual(log["tests"]["status"], "fail")
        # 修复分支应已回滚干净
        self.assertNotIn("review-fix/", _git(repo, ["branch"])[1])
        # 通过测试 → APPLIED 且台账记录 pass
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_ok.py").write_text(
            "def test_always_passes():\n    assert True\n",
            encoding="utf-8", newline="\n")
        self.assertEqual(_git_commit_all(repo, "tests"), 0)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-apply.py"], "--manifest",
                                          manifest, "--repo", repo,
                                          "--approval", approval, "--apply")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])
        self.assertEqual(data["tests"]["status"], "pass")
        log = json.loads((tmp / "out" / "apply-log.json").read_text(encoding="utf-8"))
        self.assertEqual(log["tests"]["status"], "pass")

    def test_apply_log_history_survives_retry(self):
        """反向验证（round-30 同类排查 R3）：重试落盘不得抹掉上一条回滚证据。

        apply-log.json 是「最新状态」（--undo 与 org-scorecard 按它读），原地重写是
        它的职责；但迭代官采集的是「发生过回滚」这条**事实**。旧实现只有单文件，
        采集晚于重试就永久漏账。这里连跑两次同样的失败落盘，检查两件事：
        ①历史 jsonl 攒下两条（证据没被盖掉）；②retro-ledger 采集时同一事件只记一条
        （两个文件都读不能把账记重）。
        """
        repo, findings, tmp = _make_repo(self, ALL_DEFECTS)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_bad.py").write_text(
            "def test_always_fails():\n    assert False\n",
            encoding="utf-8", newline="\n")
        self.assertEqual(_git_commit_all(repo, "tests"), 0)
        _order, manifest, approval = _chain(self, repo, findings, tmp)
        rc, first, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"], "--manifest", manifest, "--repo", repo,
            "--approval", approval, "--apply")
        self.assertEqual(rc, 1)
        self.assertEqual(first["state"], "ROLLED_BACK")
        # 回滚只还原**被跟踪**文件，pytest 在被审仓库里留下的 __pycache__ 是未跟踪的。
        # 这条残留必须被报出来：不清掉的话，下一次落盘撞的是「工作树不干净」这道闸
        # ——闸门本身没错（fail-closed），但操作者只看到拦截会以为是补丁出了问题。
        leftovers = first["worktree_leftovers"]
        self.assertTrue(any("__pycache__" in l for l in leftovers), leftovers)
        self.assertIn("重试前先清掉", first["retry_hint"])
        # 不清洗直接重试：确实被工作树闸门拦住（证明这条坑是真的，不是想象出来的）
        rc, dirty_retry, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"], "--manifest", manifest, "--repo", repo,
            "--approval", approval, "--apply")
        self.assertEqual(rc, 2)
        self.assertIn("工作树不干净", dirty_retry.get("error", ""))
        # 照报告出来的清单清掉之后，重试才真的走到回滚分支
        import shutil
        for leftover in leftovers:
            rel = leftover.split(" ", 1)[-1].strip()
            p = repo / rel
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink()
        self.assertEqual(_git(repo, ["status", "--porcelain"])[1], "")
        rc, second, _, _ = test_scripts.run(
            SCRIPTS["fix-apply.py"], "--manifest", manifest, "--repo", repo,
            "--approval", approval, "--apply")
        self.assertEqual(rc, 1, json.dumps(second, ensure_ascii=False)[:300])
        self.assertEqual(second["state"], "ROLLED_BACK")
        latest = json.loads((tmp / "out" / "apply-log.json").read_text(
            encoding="utf-8"))
        self.assertEqual(latest["status"], "ROLLED_BACK")
        history = [json.loads(l) for l in (tmp / "out" /
                                           "apply-log-history.jsonl").read_text(
                                               encoding="utf-8").splitlines() if l]
        self.assertEqual(len(history), 2, "重试把上一条回滚盖掉就是漏账")
        self.assertEqual([h["status"] for h in history],
                         ["ROLLED_BACK", "ROLLED_BACK"])
        # 采集端：两个文件都读，但同一条事件只入一次账（按 id 去重）
        rc, ledger_out, _, _ = test_scripts.run(
            SCRIPTS["retro-ledger.py"], "--out", tmp / "retro", "--scan",
            tmp / "out")
        self.assertEqual(rc, 0, json.dumps(ledger_out, ensure_ascii=False)[:300])
        self.assertEqual(ledger_out["errors"], [])
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(
            encoding="utf-8"))
        rollback = [p for p in ledger["pitfalls"] if p["category"] == "回滚"]
        self.assertEqual(len(rollback), 1,
                         "apply-log.json 与 history 里的同一条回滚被记成两条")
        self.assertIn("行为回归", rollback[0]["description"])

    def test_apply_log_history_rotation_is_bounded_and_keeps_evidence(self):
        """只追加的历史也要有上限（round-31 检查单第 7 项的后半段）。

        `apply-log-history.jsonl` 是 round-30 加的，但它自己就是新的「无界增长」：
        同一 manifest 目录反复重试落盘，一条一行一直长，没人管。口径 = 活跃文件只留
        最近 `HISTORY_LIVE_MAX` 次，溢出按签名压进同目录归档。

        反向验证两头：①连写 120 次（不轮转就是 120 行）→ 活跃恰好 50 行、归档累计
        70 行、条目只有「形状数」那么几条；再补 60 次同一形状 → 归档条目不增，
        证明长度真由形状决定而不是由次数决定；②补的那 60 次把活跃窗口刷成单一形状，
        「形状 1」只剩归档里有，此时 retro-ledger 扫这个目录仍然两种回滚都入账——
        轮转不许把窗口外的证据弄丢（这是「截断」最容易被混过去的代价，变异验证：
        把采集端改回只认 apply-log-history.jsonl，本断言立刻只剩一条）。
        """
        spec = importlib.util.spec_from_file_location(
            "fix_apply_rotation", SCRIPTS["fix-apply.py"])
        fa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fa)
        tmp = tmpspace.create(prefix="repair-rot-")
        self.addCleanup(tmpspace.release, tmp)
        out_dir = tmp / "out"
        out_dir.mkdir()
        manifest = {"__dir__": str(out_dir)}

        def write(times, start, fixed_shape=None):
            for i in range(start, start + times):
                rolled = (i % 3) != 0
                payload = {"status": "ROLLED_BACK" if rolled else "APPLIED",
                           "files": []}
                if rolled:
                    shape = (i % 2 if fixed_shape is None else fixed_shape)
                    payload["error"] = "形状 %s: 行为回归失败" % shape
                fa._write_log(manifest, payload)

        write(120, 0)
        live = [json.loads(l) for l in (out_dir / "apply-log-history.jsonl")
                .read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(live), fa.HISTORY_LIVE_MAX,
                         "活跃历史必须停在窗口大小，不是一路长到 120")
        archive_path = out_dir / fa.HISTORY_ARCHIVE_NAME
        archive = [json.loads(l) for l in archive_path.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(archive), 3,
                         "归档条目 = 不同形状数（2 种回滚 + 1 种成功），不是 70")
        self.assertEqual(sum(a["occurrences"] for a in archive), 70)
        latest = json.loads((out_dir / "apply-log.json").read_text(encoding="utf-8"))
        self.assertEqual(latest["history"], {
            "live_lines": fa.HISTORY_LIVE_MAX, "live_max": fa.HISTORY_LIVE_MAX,
            "archive_entries": 3, "archived_lines": 70})
        # 补 60 次同一形状：窗口滚动，但归档条目不新增（长度与次数无关）
        write(60, 1000, fixed_shape=0)
        archive2 = [json.loads(l) for l in archive_path.read_text(
            encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(archive2), 3, "同一形状的第 N 次要并进去，不是各占一条")
        self.assertEqual(sum(a["occurrences"] for a in archive2), 130)
        live_now = (out_dir / "apply-log-history.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("形状 1", live_now,
                         "前置条件：活跃窗口已被单一形状刷干净，形状 1 只剩归档里有")
        # 采集端：窗口外的回滚仍在账上——两种形状各一条，按 id 去重不重复记账
        rc, ledger_out, _, err = test_scripts.run(
            SCRIPTS["retro-ledger.py"], "--out", tmp / "retro", "--scan", out_dir)
        self.assertEqual(rc, 0, (err or json.dumps(ledger_out, ensure_ascii=False))[:300])
        self.assertEqual(ledger_out["errors"], [])
        ledger = json.loads((tmp / "retro" / "pitfalls.json").read_text(encoding="utf-8"))
        rollback = sorted(p["description"] for p in ledger["pitfalls"]
                          if p["category"] == "回滚")
        self.assertEqual(rollback, ["落盘回滚: 形状 0: 行为回归失败",
                                    "落盘回滚: 形状 1: 行为回归失败"],
                         "轮转后丢窗口外证据就是销账")

    def test_patch_never_contains_credential(self):
        """凭据类发现只进 manual/工单拒绝清单，不生成补丁；产物无明文凭据。"""
        repo, findings, tmp = _make_repo(self,
                                         "import os\npassword = " + '"'
                                         + test_scripts.SECRET + '"\n')
        rc, data, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"], "--findings",
                                          findings, "--repo", repo, "--out",
                                          tmp / "ap")
        self.assertEqual(rc, 0)
        order = json.loads((tmp / "ap" / "work-order.json").read_text(encoding="utf-8"))
        self.assertEqual(order["approved"], [])
        self.assertEqual(order["rejected"][0]["rule_id"], "cred-password")
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-patch.py"], "--order",
                                          tmp / "ap" / "work-order.json",
                                          "--repo", repo, "--out", tmp / "out")
        self.assertEqual(rc, 0)
        self.assertEqual(data["files"], [])
        for p in (tmp / "out").rglob("*"):
            if p.is_file():
                self.assertNotIn(test_scripts.SECRET,
                                 p.read_text(encoding="utf-8", errors="replace"),
                                 p.name)

    def test_unfixable_rule_marks_manual(self):
        """非白名单规则（如动态求值类）分诊为 manual，闸 1 裁定拒绝并给原因。"""
        repo, findings, tmp = _make_repo(self, UNFIXABLE_FIXTURE)
        rc, data, _, _ = test_scripts.run(SCRIPTS["fix-plan.py"], "--findings",
                                          findings, "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertEqual(data["fixable"], [])
        self.assertTrue(data["manual"])
        rc, data, _, _ = test_scripts.run(SCRIPTS["approve-plan.py"], "--findings",
                                          findings, "--repo", repo, "--out",
                                          tmp / "ap")
        self.assertEqual(rc, 0)
        order = json.loads((tmp / "ap" / "work-order.json").read_text(encoding="utf-8"))
        self.assertEqual(order["approved"], [])
        self.assertIn("manual", order["rejected"][0]["reason"])


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
