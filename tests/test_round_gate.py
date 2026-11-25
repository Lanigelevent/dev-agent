# -*- coding: utf-8 -*-
"""tests/test_round_gate.py — round-gate.py 契约（round-87，离线）。

覆盖：open 收官行台账对账 / 探针分诊 / 环境净化，close 复盘产物 /
三方对账 / 文档约定 / 双跑日志双格式，退出码与单 JSON stdout 契约。
夹具为最小仓库（tmpspace + git init），探针以桩脚本替换。
"""
import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "self-iteration" / "scripts" / "round-gate.py"


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("round_gate_ut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _invoke(mod, argv):
    old = sys.argv
    out = io.StringIO()
    try:
        sys.argv = ["round-gate.py"] + argv
        with contextlib.redirect_stdout(out):
            rc = mod.main()
    finally:
        sys.argv = old
    return rc, out.getvalue()


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


NEXT_ROUND_MD = """# 下一轮开局检查单

> round-86 收官（2026-11-06）：**P1 队列全量推进**（v1.87.0）。无新坑
> （4 / open 1 / closed
> 2）。下一轮（round-87）见第 47 条。
>
> round-85 收官（2026-11-05）：**P0-2 运行面产品化**。无新坑
> （4 / open 1 / closed 2）。下一轮（round-86）见第 46 条。
>
46. [路线] round-86 落地：code-task 拆分 / bump-version / 文档分卷。
47. [路线] **round-87 开局：三选一**——①扩样待端点；②D-049 待批；③维护轮。
"""

ROADMAP_MD = """# ROADMAP

### 5.44 round-86（v1.87.0）：P1 队列全量推进

## 6. 分阶段路线
"""

REPORT_MD = """# 复盘轮报 round-86

open 1 / closed 2 / archived 1
"""

STUB_PROBE = """import json, os, sys
from pathlib import Path
here = Path(__file__).resolve().parent
rc = 0
rcf = here / "_stub_rc.txt"
if rcf.is_file():
    rc = int(rcf.read_text(encoding="utf-8").strip() or "0")
(here / "_stub_env.json").write_text(json.dumps(
    {k: os.environ.get(k) for k in ("PYTHONUTF8", "PYTHONIOENCODING")}),
    encoding="utf-8")
print(json.dumps({"ok": rc == 0}))
sys.exit(rc)
"""


def _make_root(tmp, round_no=86, next_round_text=NEXT_ROUND_MD,
               roadmap=ROADMAP_MD, report_text=REPORT_MD,
               suite_format="unittest", run2_count=12, drop=()):
    pitfalls = [{"id": "o0", "status": "open"},
                {"id": "c0", "status": "closed"},
                {"id": "c1", "status": "closed"},
                {"id": "a0", "status": "archived"}]
    _write(tmp / "retro" / "pitfalls.json",
           json.dumps({"pitfalls": pitfalls}, ensure_ascii=False))
    if "next_round" not in drop:
        _write(tmp / "retro" / "next-round.md",
               next_round_text or NEXT_ROUND_MD)
    if "roadmap" not in drop:
        _write(tmp / "docs" / "ROADMAP.md", roadmap or ROADMAP_MD)
    if "report" not in drop:
        _write(tmp / "retro" / "round-86-report.md", report_text)
    if "candidates" not in drop:
        _write(tmp / "retro" / "round-86-candidates.md",
               "# round-86 改进候选\n")
    if "events" not in drop:
        _write(tmp / "retro" / "events-round-86.json", '{"events": []}\n')
    if suite_format == "unittest":
        for k in (1, 2):
            body = "Ran 12 tests in 3.00s\n\nOK (skipped=1)\nRC=0\n"
            if k == 2 and run2_count != 12:
                body = "Ran %d tests in 3.00s\n\nOK (skipped=1)\nRC=0\n" % run2_count
            _write(tmp / "logs" / ("suite-r86-run%d.log" % k), body)
    elif suite_format == "pytest":
        for k in (1, 2):
            body = "558 passed, 1 skipped in 418.79s\nRC=0\n"
            if k == 2 and run2_count != 558:
                body = "%d passed, 1 skipped in 418.79s\nRC=0\n" % run2_count
            _write(tmp / "logs" / ("suite-r86-run%d.log" % k), body)
    return tmp


def _git_init_commit(root):
    import subprocess
    def g(*a):
        subprocess.run(["git", "-C", str(root)] + list(a), shell=False,
                       capture_output=True, text=True, encoding="utf-8")
    g("init", "-b", "main")
    g("config", "user.email", "t@example.com")
    g("config", "user.name", "t")
    g("add", "-A")
    g("commit", "-m", "fixture")
    return None


class _StubProbes:
    """桩探针：写入 stub 脚本并把模块常量指过去；用完还原。"""

    def __init__(self, mod, tmp, cleanup):
        self.mod = mod
        p = Path(tmpspace.create(prefix="rg-stub-"))
        cleanup(tmpspace.release, p)
        for name in ("probe1.py", "probe2.py"):
            (p / name).write_text(STUB_PROBE, encoding="utf-8",
                                  newline="\n")
        self.p1 = mod.SESSION_PROBE
        self.p2 = mod.DOC_FRESHNESS
        mod.SESSION_PROBE = p / "probe1.py"
        mod.DOC_FRESHNESS = p / "probe2.py"
        self.tmp = p

    def set_rc(self, rc):
        (self.tmp / "_stub_rc.txt").write_text(str(rc), encoding="utf-8")

    def env_dump(self):
        return json.loads((self.tmp / "_stub_env.json").read_text(
            encoding="utf-8"))

    def restore(self):
        self.mod.SESSION_PROBE = self.p1
        self.mod.DOC_FRESHNESS = self.p2


class OpenVerbTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_script()
        self.tmp = Path(tmpspace.create(prefix="rg-open-"))
        self.addCleanup(tmpspace.release, self.tmp)
        _make_root(self.tmp)
        self.stubs = _StubProbes(self.mod, self.tmp, self.addCleanup)
        self.addCleanup(self.stubs.restore)
        _git_init_commit(self.tmp)

    def _checks(self, out_text):
        d = json.loads(out_text)
        by_id = {c["id"]: c for c in d["checks"]}
        return d, by_id

    def test_open_all_pass(self):
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d, by_id = self._checks(out)
        self.assertEqual(rc, 0)
        self.assertTrue(d["ok"])
        for cid in ("git_state", "session_probe", "doc_freshness",
                    "next_round_readable", "pitfalls_reconcile"):
            self.assertEqual(by_id[cid]["status"], "PASS", cid)

    def test_open_dirty_tree(self):
        (self.tmp / "stray.txt").write_text("x", encoding="utf-8")
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d, by_id = self._checks(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["git_state"]["status"], "FAIL")
        self.assertFalse(d["ok"])

    def test_open_counts_mismatch(self):
        text = NEXT_ROUND_MD.replace("4 / open 1 / closed", "4 / open 2 / closed")
        _write(self.tmp / "retro" / "next-round.md", text)
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d, by_id = self._checks(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["pitfalls_reconcile"]["status"], "FAIL")

    def test_open_missing_next_round_rc2(self):
        (self.tmp / "retro" / "next-round.md").unlink()
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d = json.loads(out)
        self.assertEqual(rc, 2)
        self.assertFalse(d["ok"])
        self.assertIn("必须存在", d["error"])

    def test_open_probe_signal(self):
        self.stubs.set_rc(1)
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d, by_id = self._checks(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["session_probe"]["status"], "FAIL")
        self.assertIn("待分诊", by_id["session_probe"]["note"])

    def test_open_probe_broken(self):
        self.stubs.set_rc(2)
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d, by_id = self._checks(out)
        self.assertEqual(rc, 1)
        self.assertIn("故障", by_id["session_probe"]["error"])

    def test_open_probe_env_sanitized(self):
        self.stubs.set_rc(0)
        old = dict(os.environ)
        try:
            os.environ["PYTHONUTF8"] = "1"
            os.environ["PYTHONIOENCODING"] = "utf-8"
            _invoke(self.mod, ["open", "--root", str(self.tmp)])
        finally:
            os.environ.pop("PYTHONUTF8", None)
            os.environ.pop("PYTHONIOENCODING", None)
        dump = self.stubs.env_dump()
        self.assertIsNone(dump["PYTHONUTF8"])
        self.assertIsNone(dump["PYTHONIOENCODING"])

    def test_stdout_single_json(self):
        rc, out = _invoke(self.mod, ["open", "--root", str(self.tmp)])
        d = json.loads(out)  # 整个 stdout 必须是单个 JSON 文档
        self.assertIn("checks", d)
        self.assertIn("verb", d)

    def test_close_requires_round_rc2(self):
        rc, out = _invoke(self.mod, ["close", "--root", str(self.tmp)])
        d = json.loads(out)
        self.assertEqual(rc, 2)
        self.assertIn("正整数", d["error"])


class CloseVerbTests(unittest.TestCase):
    def setUp(self):
        self.mod = _load_script()
        self.tmp = Path(tmpspace.create(prefix="rg-close-"))
        self.addCleanup(tmpspace.release, self.tmp)
        _make_root(self.tmp)

    def _close(self, out_text):
        d = json.loads(out_text)
        by_id = {c["id"]: c for c in d["checks"]}
        return d, by_id

    def test_close_all_pass(self):
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 0)
        self.assertTrue(d["ok"])
        for cid in ("retro_artifacts", "pitfalls_reconcile",
                    "next_round_topline", "next_round_item",
                    "roadmap_section", "suite_logs"):
            self.assertEqual(by_id[cid]["status"], "PASS", cid)

    def test_close_missing_events(self):
        (self.tmp / "retro" / "events-round-86.json").unlink()
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["retro_artifacts"]["status"], "FAIL")

    def test_close_events_bad_json(self):
        _write(self.tmp / "retro" / "events-round-86.json", "{not json")
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["retro_artifacts"]["status"], "FAIL")

    def test_close_header_mismatch(self):
        _write(self.tmp / "retro" / "round-86-report.md",
               "# 复盘轮报 round-86\n\nopen 2 / closed 2 / archived 1\n")
        rc, open_out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(open_out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["pitfalls_reconcile"]["status"], "FAIL")
        self.assertEqual(by_id["pitfalls_reconcile"]["report_header"]["open"], 2)

    def test_close_topline_round_mismatch(self):
        text = NEXT_ROUND_MD.replace("> round-86 收官", "> round-85 收官")
        _write(self.tmp / "retro" / "next-round.md", text)
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["next_round_topline"]["status"], "FAIL")

    def test_close_missing_next_pointer(self):
        text = NEXT_ROUND_MD.replace(
            "下一轮（round-87）见第 47 条。",
            "下一轮见第 47 条。")
        _write(self.tmp / "retro" / "next-round.md", text)
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["next_round_item"]["status"], "FAIL")

    def test_close_missing_item(self):
        text = NEXT_ROUND_MD.replace("47. [路线] **round-87 开局",
                                     "47. [路线] **round-999 开局")
        _write(self.tmp / "retro" / "next-round.md", text)
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["next_round_item"]["status"], "FAIL")
        self.assertFalse(by_id["next_round_item"]["item_found"])

    def test_close_missing_roadmap(self):
        _write(self.tmp / "docs" / "ROADMAP.md", "# ROADMAP\n\n无本环节。\n")
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["roadmap_section"]["status"], "FAIL")

    def test_close_missing_suite_logs(self):
        (self.tmp / "logs" / "suite-r86-run1.log").unlink()
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["suite_logs"]["status"], "FAIL")
        self.assertIn("缺失", by_id["suite_logs"]["error"])

    def test_close_suite_parity(self):
        _write(self.tmp / "logs" / "suite-r86-run2.log",
               "Ran 11 tests in 3.00s\n\nOK\nRC=0\n")
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["suite_logs"]["status"], "FAIL")
        self.assertFalse(by_id["suite_logs"]["parity"])

    def test_close_suite_pytest_format(self):
        _write(self.tmp / "logs" / "suite-r86-run1.log",
               "558 passed, 1 skipped in 418.79s\nRC=0\n")
        _write(self.tmp / "logs" / "suite-r86-run2.log",
               "558 passed, 1 skipped in 418.79s\nRC=0\n")
        rc, out = _invoke(self.mod,
                          ["close", "--round", "86", "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 0)
        self.assertEqual(by_id["suite_logs"]["status"], "PASS")
        self.assertEqual(by_id["suite_logs"]["runs"][0]["format"], "pytest")

    def test_close_unknown_log_format(self):
        _write(self.tmp / "logs" / "suite-r86-run1.log", "garbage content")
        _write(self.tmp / "logs" / "suite-r86-run2.log", "garbage content")
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d, by_id = self._close(out)
        self.assertEqual(rc, 1)
        self.assertEqual(by_id["suite_logs"]["status"], "FAIL")


    def test_close_light_single_run_passes(self):
        tmp = _make_root(self.tmp)
        (self.tmp / "logs" / "suite-r86-run2.log").unlink()
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp),
                                     "--round-type", "light"])
        d = json.loads(out)
        self.assertEqual(rc, 0)
        sl = [c for c in d["checks"] if c["id"] == "suite_logs"][0]
        self.assertEqual(sl["status"], "PASS")

    def test_close_light_still_requires_green(self):
        tmp = _make_root(self.tmp)
        (self.tmp / "logs" / "suite-r86-run2.log").unlink()
        _write(self.tmp / "logs" / "suite-r86-run1.log",
               "Ran 12 tests in 3.00s\\n\\nFAILED (failures=1)\\n")
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp),
                                     "--round-type", "light"])
        d = json.loads(out)
        self.assertEqual(rc, 1)
        sl = [c for c in d["checks"] if c["id"] == "suite_logs"][0]
        self.assertEqual(sl["status"], "FAIL")

    def test_close_full_requires_two_logs(self):
        tmp = _make_root(self.tmp)
        (self.tmp / "logs" / "suite-r86-run2.log").unlink()
        rc, out = _invoke(self.mod, ["close", "--round", "86",
                                     "--root", str(self.tmp)])
        d = json.loads(out)
        self.assertEqual(rc, 1)
        sl = [c for c in d["checks"] if c["id"] == "suite_logs"][0]
        self.assertEqual(sl["status"], "FAIL")


class ParseSuiteLogTests(unittest.TestCase):
    def setUp(self):
        self.parse = _load_script()._parse_suite_log

    def test_unittest_green(self):
        d = self.parse("Ran 559 tests in 418.79s\n\nOK (skipped=1)\n")
        self.assertEqual(d["format"], "unittest")
        self.assertEqual(d["tests"], 559)
        self.assertTrue(d["green"])

    def test_unittest_failed(self):
        d = self.parse("Ran 559 tests in 418.79s\nFAILED (failures=1)\n")
        self.assertFalse(d["green"])

    def test_pytest_green(self):
        d = self.parse("558 passed, 1 skipped in 418.79s\nRC=0\n")
        self.assertEqual(d["format"], "pytest")
        self.assertEqual(d["tests"], 559)
        self.assertTrue(d["green"])

    def test_pytest_failed(self):
        d = self.parse("1 failed, 557 passed, 1 skipped in 60.00s\nRC=1\n")
        self.assertFalse(d["green"])
        self.assertEqual(d["tests"], 559)

    def test_unknown(self):
        d = self.parse("hello world")
        self.assertEqual(d["format"], "unknown")
        self.assertFalse(d["green"])



if __name__ == "__main__":
    unittest.main()


class SuiteCountClaimTests(unittest.TestCase):
    """收官行测试计数声明 vs 双跑实测（r159，r154 误计坑 2122392940fc 对策）。"""

    @classmethod
    def setUpClass(cls):
        cls.check = staticmethod(_load_script()._check_suite_count_claim)

    def test_claim_mismatch_fails_like_r154(self):
        """反向验证（红线 6）：复刻 r154 实景——收官行写 751→754 而双跑实测
        748，close 门必须判红（当时只对台账三态对账、不管测试数声明）。"""
        text = ('> round-154 收官（2026-11-14）：**性能基准**（v2.56.0，'
                '测试 **751→754**、脚本 85→86）。台账不变（246 / open 5）。'
                '下一轮（round-155）见第 115 条。')
        out = self.check(text, [{"tests": 748}])
        self.assertEqual(out["status"], "FAIL")
        self.assertIn("2122392940fc", out["error"])

    def test_claim_match_passes(self):
        text = ('> round-158 收官（2026-11-14）：**行数基线机械对账**'
                '（v2.60.0，测试 **758→761**、脚本 86 不变）。')
        out = self.check(text, [{"tests": 761}, {"tests": 761}])
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["claimed"], 761)
        self.assertEqual(out["measured"], [761, 761])

    def test_flat_claim_passes(self):
        text = ('> round-142 收官（2026-11-08）：**light 收官**（v2.44.0，'
                '测试 **739 不变**、脚本 85 不变）。')
        out = self.check(text, [{"tests": 739}])
        self.assertEqual(out["status"], "PASS")
        self.assertEqual(out["claimed"], 739)

    def test_no_claim_passes_with_note(self):
        out = self.check('> round-9 收官（2026-11-01）：done。', [])
        self.assertEqual(out["status"], "PASS")
        self.assertIn("无测试计数声明", out["note"])


class ScorecardBudgetTests(unittest.TestCase):
    """SRE 错误预算进收官门（r164，125 条②机械化）。

    WARN（≤2×threshold）关注不阻断；EXCEEDED（>2×threshold）判红——
    放行冻结中的轮次等于冻结失效。反向验证锚定 17 个 open 坑。
    """

    @classmethod
    def setUpClass(cls):
        cls.check = staticmethod(_load_script()._check_scorecard)

    def test_budget_green_passes(self):
        with tmpspace.create(prefix="rg-sc-green-") as tmp:
            retro = tmp / "retro"
            retro.mkdir(parents=True)
            (retro / "pitfalls.json").write_text(json.dumps(
                {"pitfalls": [{"id": "x1", "category": "手工",
                               "description": "一个未结坑", "status": "open"}]},
                ensure_ascii=False), encoding="utf-8", newline="\n")
            out = self.check(tmp)
            self.assertEqual(out["status"], "PASS", json.dumps(out, ensure_ascii=False))

    def test_budget_exceeded_fails(self):
        """反向验证（红线 6）：17 个 open 坑 > 8×2 必须判红（整改冻结）。"""
        with tmpspace.create(prefix="rg-sc-exc-") as tmp:
            retro = tmp / "retro"
            retro.mkdir(parents=True)
            pits = [{"id": "p%d" % i, "category": "手工",
                     "description": "预算超限用例", "status": "open"}
                    for i in range(17)]
            (retro / "pitfalls.json").write_text(json.dumps(
                {"pitfalls": pits}, ensure_ascii=False),
                encoding="utf-8", newline="\n")
            out = self.check(tmp)
            self.assertEqual(out["status"], "FAIL")
            self.assertIn("EXCEEDED", out["error"])
            self.assertIn("retro.open_pitfalls", out["error"])


class TestLedgerIdempotency(unittest.TestCase):
    """r186：close 门账本追加幂等守卫（r154 历史双记机制修复）——
    同轮 round-summary 已存在时跳过追加；不同轮不受阻（反向验证）。"""

    def setUp(self):
        self.mod = _load_script()
        self.tmp = Path(tmpspace.create(prefix="rg-ledger-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_recorder(self, root):
        """构造带假 event-ledger.py 的临时 root（record 调用为追加一条 JSON 行）。"""
        script_dir = root / "skills" / "production-guardrails" / "scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script = script_dir / "event-ledger.py"
        script.write_text(
            "# -*- coding: utf-8 -*-\n"
            "import json, sys\n"
            "args = sys.argv\n"
            "obs = json.loads(args[args.index('--observation-json') + 1])\n"
            "d = args[args.index('--dir') + 1]\n"
            "with open(d + '/ledger.jsonl', 'a', encoding='utf-8') as f:\n"
            "    f.write(json.dumps({'action': 'round-summary', 'observation': obs}, ensure_ascii=False) + '\\n')\n",
            encoding="utf-8", newline="\n")
        return root

    def test_append_twice_yields_single_record(self):
        root = self._fake_recorder(self.tmp / "root")
        self.assertIsNone(self.mod._append_ledger_record(root, 185, True))
        self.assertIsNone(self.mod._append_ledger_record(root, 185, True))
        ledger = root / "runs" / "rounds-ledger" / "ledger.jsonl"
        recs = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        same = [r for r in recs
                if r.get("action") == "round-summary"
                and (r.get("observation") or {}).get("round") == 185]
        self.assertEqual(len(same), 1, "close 重跑同轮不得双记（r154 教训）")

    def test_append_different_round_still_records(self):
        root = self._fake_recorder(self.tmp / "root2")
        self.mod._append_ledger_record(root, 185, True)
        self.assertIsNone(self.mod._append_ledger_record(root, 186, True))
        ledger = root / "runs" / "rounds-ledger" / "ledger.jsonl"
        recs = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
        rounds = [(r.get("observation") or {}).get("round") for r in recs
                  if r.get("action") == "round-summary"]
        self.assertEqual(rounds, [185, 186], "守卫不得阻断其他轮的追加（反向验证）")

    def test_scan_tolerates_corrupt_lines(self):
        ledger = self.tmp / "ledger.jsonl"
        ledger.write_text(
            json.dumps({"action": "round-summary", "observation": {"round": 154}}) + "\n",
            encoding="utf-8")
        with open(ledger, "a", encoding="utf-8") as h:
            h.write("garbage line\n")
        self.assertTrue(self.mod._ledger_has_round_summary(ledger, 154))
        self.assertFalse(self.mod._ledger_has_round_summary(ledger, 155))
