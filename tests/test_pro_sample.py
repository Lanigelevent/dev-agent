#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_pro_sample.py — SWE-bench Pro 适配层契约（离线，不触网不碰 docker）。

覆盖：参数/字段错误退出码 2、--dry-run 计划（命令与判分点计数、docker 缺席
不阻断）、pytest -rA 解析与 judge 语义（SKIPPED/缺失不算过、基线互斥判定）、
补丁双闸接线（test_patch 结构损坏 / predictions 完整性 critical）、
blocked_source 不静默丢样本、台账断点续跑与聚合计数。
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

import tmpspace
from _scripts_common import run

ROOT = Path(__file__).resolve().parents[1]
PRO = ROOT / "skills" / "eval-harness" / "scripts" / "pro-sample.py"


def _diff(path, old, new, tag):
    return ("diff --git a/%s b/%s\n--- a/%s\n+++ b/%s\n@@ -1 +1 @@\n-%s\n+%s\n"
            % (path, path, path, path, old, new + tag))


def _task(iid, f2p=None, p2p=None, docker=True):
    task = {
        "instance_id": iid,
        "repo": "demo/repo",
        "base_commit": "deadbeef",
        "docker_image": ("ghcr.io/demo/pro:%s" % iid) if docker else "",
        "test_patch": _diff("pkg/test_mod.py", "assert False", "assert True",
                            "-t"),
        "gold_patch": _diff("pkg/mod.py", "value = 'old'", "value = 'new'",
                            "-g"),
        "fail_to_pass": f2p or ["pkg/test_mod.py::test_fix"],
        "pass_to_pass": p2p or ["pkg/test_mod.py::test_keep"],
        "before_repo_set_cmd": ("git reset --hard deadbeef\n"
                                "git apply --verbose /tests/test_patch.patch"),
        "selected_test_files_to_run": ["pkg/test_mod.py"],
    }
    return task


def _write_tasks(tmp, tasks):
    path = Path(tmp) / "tasks.jsonl"
    path.write_text("\n".join(json.dumps(t, ensure_ascii=False)
                              for t in tasks) + "\n",
                    encoding="utf-8", newline="\n")
    return path


def _load_module():
    spec = importlib.util.spec_from_file_location("pro_sample_mod", PRO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestProSampleCli(unittest.TestCase):
    """子进程契约：参数错误、dry-run、闸与 blocked_source、台账续跑。"""

    def _inputs(self, tmp):
        return _write_tasks(tmp, [_task("demo-a"), _task("demo-b")])

    def test_param_errors_exit_2(self):
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = self._inputs(tmp)
        rc, _, _, _ = run(PRO, "--tasks", str(Path(tmp) / "absent.jsonl"),
                          "--out", tmp)
        self.assertEqual(rc, 2, "任务清单缺失应参数错误")
        rc, _, _, _ = run(PRO, "--tasks", str(tasks), "--mode", "predictions",
                          "--out", tmp)
        self.assertEqual(rc, 2, "predictions 模式缺 --predictions 应参数错误")
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--instances",
                             "demo-missing", "--out", tmp)
        self.assertEqual(rc, 2, "缺实例必须点名报错")
        self.assertIn("demo-missing", json.dumps(data, ensure_ascii=False))
        bad = _write_tasks(tmp, [_task("demo-c", docker=False)])
        rc, data, _, _ = run(PRO, "--tasks", str(bad), "--out", tmp)
        self.assertEqual(rc, 2, "任务字段缺失应参数错误")
        self.assertIn("docker_image", json.dumps(data, ensure_ascii=False))

    def test_dry_run_plan(self):
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = self._inputs(tmp)
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode", "gold",
                             "--out", tmp, "--dry-run",
                             "--docker", str(Path(tmp) / "no-docker"))
        self.assertEqual(rc, 0, str(data)[:300])
        self.assertTrue(data["dry_run"])
        self.assertEqual(len(data["tasks"]), 2)
        item = data["tasks"][0]
        self.assertEqual(item["fail_to_pass"], 1)
        self.assertEqual(item["pass_to_pass"], 1)
        self.assertIn("python -m pytest -rA pkg/test_mod.py",
                      item["pytest_cmd"])
        self.assertTrue(item["prepare_cmd"].startswith("cd /app"))
        self.assertIn("/tests/candidate.patch", item["apply_cmd"])
        self.assertEqual(item["local_image"], "")
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--instances",
                             "demo-b", "--out", tmp, "--dry-run")
        self.assertEqual([t["instance_id"] for t in data["tasks"]],
                         ["demo-b"], "--instances 过滤生效")

    def test_zero_p2p_task_runs(self):
        """零 P2P 实例（ansible-11c1777d 实测形态）不得被字段校验挡掉。"""
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        task = _task("demo-zero")
        task["pass_to_pass"] = []
        tasks = _write_tasks(tmp, [task])
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--out", tmp,
                             "--dry-run",
                             "--docker", str(Path(tmp) / "no-docker"))
        self.assertEqual(rc, 0, str(data)[:300])
        self.assertEqual(data["tasks"][0]["pass_to_pass"], 0)

    def test_gate_and_blocked_without_docker(self):
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        # test_patch 结构损坏：hunk 声明 -1/+1 但只有删除行
        broken = _task("demo-broken")
        broken["test_patch"] = ("diff --git a/pkg/test_mod.py "
                                "b/pkg/test_mod.py\n--- a/pkg/test_mod.py\n"
                                "+++ b/pkg/test_mod.py\n@@ -1 +1 @@\n-old\n")
        tasks = _write_tasks(tmp, [broken, _task("demo-ok")])
        out = Path(tmp) / "out"
        rc, data, _, _ = run(PRO, "--tasks", str(tasks),
                             "--instances", "demo-broken", "--mode", "baseline",
                             "--out", str(out), "--no-fetch")
        self.assertEqual(rc, 1)
        self.assertEqual(data["counts"].get("malformed_test_patch"), 1,
                         "结构损坏必须在应用前拦截，不碰 docker")
        # 正常 test_patch + 无本地镜像 + --no-fetch → blocked_source 不丢样本
        # （用 sys.executable 冒充 docker：images 查询失败 → 本地集合未知 →
        #  按缺失处理，正好覆盖「docker 在但镜像不在」的降级路径）
        rc, data, _, _ = run(PRO, "--tasks", str(tasks),
                             "--instances", "demo-ok", "--mode", "baseline",
                             "--out", str(out), "--no-fetch",
                             "--docker", sys.executable)
        self.assertEqual(rc, 1)
        self.assertEqual(data["blocked_source"], 1)
        ledger = json.loads((out / "pro-sample-ledger.json")
                            .read_text(encoding="utf-8"))
        states = {row["instance_id"]: row["state"]
                  for row in ledger["results"]}
        self.assertEqual(states.get("demo-broken"), "malformed_test_patch")
        self.assertEqual(states.get("demo-ok"), "blocked_source")

    def test_predictions_integrity_flagged(self):
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = _write_tasks(tmp, [_task("demo-a")])
        preds = Path(tmp) / "preds.jsonl"
        bad_patch = _diff("tests/test_mod.py", "assert False", "assert True",
                          "-cheat")
        preds.write_text(json.dumps({"instance_id": "demo-a",
                                     "model_patch": bad_patch}) + "\n",
                         encoding="utf-8", newline="\n")
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode",
                             "predictions", "--predictions", str(preds),
                             "--out", tmp, "--no-fetch")
        self.assertEqual(rc, 1)
        self.assertEqual(data["integrity_flagged"], 1,
                         "改既有测试的预测补丁必须被完整性闸拦下")

    def test_predictions_from_agent_patches(self):
        """agent 侧入口：edits.patch 目录 → 预测文件 + 来源留档。"""
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = self._inputs(tmp)
        patches = Path(tmp) / "patches"
        for iid in ("demo-a", "demo-b"):
            d = patches / iid
            d.mkdir(parents=True)
            (d / "edits.patch").write_text(
                _diff("pkg/mod.py", "value = 'old'", "value = 'new'",
                      "-%s" % iid), encoding="utf-8", newline="\n")
        out = Path(tmp) / "out"
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode",
                             "predictions", "--patches", str(patches),
                             "--out", str(out), "--dry-run",
                             "--docker", str(Path(tmp) / "no-docker"))
        self.assertEqual(rc, 0, str(data)[:300])
        pred = out / "predictions-agent.jsonl"
        rows = [json.loads(line) for line in
                pred.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({r["instance_id"] for r in rows},
                         {"demo-a", "demo-b"})
        prov = json.loads((out / "patch-provenance.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(len(prov["instances"]), 2)
        rc, _, _, _ = run(PRO, "--tasks", str(tasks), "--mode", "predictions",
                          "--patches", str(patches), "--predictions", str(pred),
                          "--out", str(out))
        self.assertEqual(rc, 2, "--predictions 与 --patches 必须互斥")
        (patches / "demo-b" / "edits.patch").unlink()
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode",
                             "predictions", "--patches", str(patches),
                             "--out", str(out), "--dry-run")
        self.assertEqual(rc, 2, "缺一例补丁必须点名报错")
        self.assertIn("demo-b", json.dumps(data, ensure_ascii=False))

    def test_force_preserves_other_ledger_rows(self):
        """--force 只重跑目标样本，不得覆盖其他台账行（round-51 真坑）。"""
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = self._inputs(tmp)
        out = Path(tmp) / "out"
        out.mkdir()
        (out / "pro-sample-ledger.json").write_text(json.dumps({
            "results": [{"instance_id": "demo-a", "mode": "baseline",
                         "key": "demo-a|baseline", "state": "baseline_ok",
                         "resolved": None}]}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode", "baseline",
                             "--instances", "demo-b", "--force", "--out",
                             str(out), "--no-fetch",
                             "--docker", sys.executable)
        self.assertEqual(rc, 1, "demo-b 会 blocked_source")
        ledger = json.loads((out / "pro-sample-ledger.json")
                            .read_text(encoding="utf-8"))
        states = {row["instance_id"]: row["state"]
                  for row in ledger["results"]}
        self.assertEqual(states.get("demo-a"), "baseline_ok",
                         "强制重跑不得丢掉其他样本行")
        self.assertEqual(states.get("demo-b"), "blocked_source")

    def test_ledger_resume_skips_done(self):
        tmp = tmpspace.create(prefix="pro-sample-test-")
        self.addCleanup(tmpspace.release, tmp)
        tasks = self._inputs(tmp)
        out = Path(tmp) / "out"
        out.mkdir()
        (out / "pro-sample-ledger.json").write_text(json.dumps({
            "results": [{"instance_id": "demo-a", "mode": "baseline",
                         "key": "demo-a|baseline", "state": "baseline_ok",
                         "resolved": None}]}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        rc, data, _, _ = run(PRO, "--tasks", str(tasks), "--mode", "baseline",
                             "--out", str(out), "--no-fetch",
                             "--docker", str(Path(tmp) / "no-docker"))
        self.assertEqual(rc, 1, "demo-b 会 blocked_source，退出码 1")
        self.assertEqual(data["run_this_time"], 1, "DONE 实例不应重跑")
        self.assertEqual(data["total"], 2, "聚合计数覆盖本模式全部实例")
        self.assertEqual(data["counts"].get("baseline_ok"), 1)


class TestProSampleUnits(unittest.TestCase):
    """纯函数语义：解析、对账、判定（不起子进程）。"""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_parse_last_status_wins(self):
        text = ("PASSED pkg/test_mod.py::test_a\n"
                "FAILED pkg/test_mod.py::test_b\n"
                "PASSED pkg/test_mod.py::test_b\n"
                "SKIPPED [1] pkg/test_mod.py:3: skipped\n")
        results = self.mod.parse_pytest_output(text)
        self.assertEqual(results["pkg/test_mod.py::test_b"], "PASSED")
        self.assertNotIn("[1]", results, "SKIPPED 统计行不是 node 行")

    def test_parse_node_with_spaces_and_reason(self):
        """参数化 node 含空格不得被截断；` - reason` 尾注要能对上。"""
        text = ("PASSED t.py::T::test_data[Hello World! This is a test.]\n"
                "FAILED t.py::T::test_x - AssertionError: boom\n")
        results = self.mod.parse_pytest_output(text)
        node = "t.py::T::test_data[Hello World! This is a test.]"
        self.assertEqual(self.mod.lookup_node(results, node), "PASSED")
        self.assertEqual(self.mod.lookup_node(results, "t.py::T::test_x"),
                         "FAILED")

    def test_judge_resolved_requires_all_pass(self):
        judge = self.mod.judge
        f2p = ["t.py::fix"]
        p2p = ["t.py::keep"]
        verdict, _ = judge({"t.py::fix": "PASSED", "t.py::keep": "PASSED"},
                           f2p, p2p, "gold")
        self.assertEqual(verdict, "resolved")
        verdict, _ = judge({"t.py::fix": "PASSED", "t.py::keep": "SKIPPED"},
                           f2p, p2p, "gold")
        self.assertEqual(verdict, "unresolved", "SKIPPED 不算过")
        verdict, _ = judge({"t.py::keep": "PASSED"}, f2p, p2p, "gold")
        self.assertEqual(verdict, "unresolved", "缺 F2P 判分点不算过")
        verdict, _ = judge({"./t.py::fix": "PASSED", "./t.py::keep": "PASSED"},
                           f2p, p2p, "gold")
        self.assertEqual(verdict, "resolved", "前缀差异用后缀匹配兜底")

    def test_judge_zero_p2p(self):
        """零 P2P 只要 F2P 全过即 resolved；基线期望 F2P 不过即通过。"""
        judge = self.mod.judge
        verdict, _ = judge({"t.py::fix": "PASSED"}, ["t.py::fix"], [], "gold")
        self.assertEqual(verdict, "resolved")
        verdict, _ = judge({"t.py::fix": "FAILED"}, ["t.py::fix"], [],
                           "baseline")
        self.assertEqual(verdict, "baseline_ok")

    def test_judge_baseline_semantics(self):
        judge = self.mod.judge
        f2p = ["t.py::fix"]
        p2p = ["t.py::keep"]
        verdict, _ = judge({"t.py::fix": "FAILED", "t.py::keep": "PASSED"},
                           f2p, p2p, "baseline")
        self.assertEqual(verdict, "baseline_ok")
        verdict, _ = judge({"t.py::fix": "PASSED", "t.py::keep": "PASSED"},
                           f2p, p2p, "baseline")
        self.assertEqual(verdict, "baseline_unexpected")
        verdict, _ = judge({"t.py::fix": "FAILED", "t.py::keep": "FAILED"},
                           f2p, p2p, "baseline")
        self.assertEqual(verdict, "baseline_p2p_failed")
        verdict, _ = judge({"t.py::keep": "PASSED"}, f2p, p2p, "baseline")
        self.assertEqual(verdict, "baseline_unexpected",
                         "判分点未被收集＝环境不可信，不能算基线通过")

    def test_split_ref_and_candidates(self):
        cases = {
            "ghcr.io/scaleapi/swe-bench_pro-v2:inst-1":
                ("ghcr.io", "scaleapi/swe-bench_pro-v2", "inst-1"),
            "owner/repo:tag": ("", "owner/repo", "tag"),
            "owner/repo": ("", "owner/repo", "latest"),
        }
        for ref, expected in cases.items():
            self.assertEqual(self.mod.split_ref(ref), expected)
        cands = self.mod.image_candidates(
            {"docker_image": "ghcr.io/scaleapi/pro:x"}, "ghcr.nju.edu.cn")
        self.assertEqual(cands[0], "ghcr.nju.edu.cn/scaleapi/pro:x")
        self.assertIn("ghcr.io/scaleapi/pro:x", cands)

    def test_pytest_command_with_adaptation(self):
        """任务级环境适配：env 前缀 + 附加参数进命令，非法变量名被丢弃。"""
        task = _task("demo-adapt")
        task.update(pre_test_cmd="Xvfb :99 >/dev/null 2>&1 & sleep 1",
                    env={"DISPLAY": ":99",
                         "QTWEBENGINE_DISABLE_SANDBOX": "1",
                         "bad-key": "x"},
                    pytest_args=["-p", "no:xvfb"])
        cmd = self.mod.pytest_command(task)
        self.assertIn("DISPLAY=:99", cmd)
        self.assertIn("QTWEBENGINE_DISABLE_SANDBOX=1", cmd)
        self.assertIn("-p no:xvfb", cmd)
        self.assertNotIn("bad-key", cmd)
        self.assertTrue(cmd.endswith("pkg/test_mod.py"))


if __name__ == "__main__":
    unittest.main()
