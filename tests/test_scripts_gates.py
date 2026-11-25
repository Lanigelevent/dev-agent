# -*- coding: utf-8 -*-
"""tests/test_scripts_gates.py — 技能闸与精度：TestSkillGates / TestPrecisionGate / TestVerifyClosureCommands（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestSkillGates(unittest.TestCase):
    """自 workbuddy-skills 移植的两道门禁契约（红线 6：反向验证必转红）。"""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "trigger_audit", ROOT / "skills/self-iteration/scripts/trigger-audit.py")
        cls.ta = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.ta)
        spec2 = importlib.util.spec_from_file_location(
            "doc_freshness", ROOT / "skills/self-iteration/scripts/doc-freshness.py")
        cls.df = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(cls.df)

    # ---- trigger-audit ----

    def test_frontmatter_crlf_tolerant(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "SKILL.md"
            f.write_bytes(b"---\r\ndescription: abc def\r\n---\r\nbody\r\n")
            fm = self.ta.frontmatter(f)
            self.assertIsNotNone(fm, "CRLF 文件不得解析失败（假红源）")
            self.assertEqual(fm["description"], "abc def")

    def test_extract_pool_subsplit_long_segment(self):
        # 单关键词嵌在超长分段：子切后长分段 ≤24 字成为词条，
        # MUST 短词经子串匹配（probe in c）仍须命中（自检教训的闭环）
        pool = self.ta.extract_pool(
            "一键对 Git 变更跑完整评审（预检→取数→评分→并行审查→核验→交付双闸），产出报告")
        self.assertTrue(any("评审" in c for c in pool),
                        "评审 应作为某词条的子串存在于池中")
        word, how = self.ta.match(pool, "评审")
        self.assertIsNotNone(word, "MUST 短词必须命中")

    def test_audit_blind_spot_fails_and_fix_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "demo").mkdir()
            (root / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: 只管甲事\n---\nbody\n",
                encoding="utf-8", newline="\n")
            probes = root / "probes.json"
            probes.write_text(json.dumps({
                "demo": ["帮我处理乙事"],
                "_must": {"demo": ["甲事"]},
            }), encoding="utf-8", newline="\n")
            rc, data, _, _ = run(
                ROOT / "skills/self-iteration/scripts/trigger-audit.py",
                "--skills-root", str(root), "--probes", str(probes),
                "--self-check")
            self.assertEqual(rc, 1, "盲区应判红")
            self.assertEqual(data["blind_count"], 1)
            self.assertTrue(data["trust"], "MUST 全过时结论应可信")
            # 反向闭环：补词后同话术必须转绿
            (root / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: 只管甲事。也用于口语说法：帮我处理乙事\n---\nbody\n",
                encoding="utf-8", newline="\n")
            rc, data, _, _ = run(
                ROOT / "skills/self-iteration/scripts/trigger-audit.py",
                "--skills-root", str(root), "--probes", str(probes),
                "--self-check")
            self.assertEqual(rc, 0)
            self.assertEqual(data["blind_count"], 0)

    def test_audit_must_fail_marks_untrusted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "demo").mkdir()
            (root / "demo" / "SKILL.md").write_text(
                "---\nname: demo\ndescription: 只管甲事\n---\nbody\n",
                encoding="utf-8", newline="\n")
            probes = root / "probes.json"
            probes.write_text(json.dumps({
                "demo": ["帮我处理乙事"],
                "_must": {"demo": ["甲事", "根本不在的词"]},
            }), encoding="utf-8", newline="\n")
            rc, data, _, _ = run(
                ROOT / "skills/self-iteration/scripts/trigger-audit.py",
                "--skills-root", str(root), "--probes", str(probes),
                "--self-check")
            self.assertEqual(rc, 1)
            self.assertFalse(data["trust"], "MUST 未过=匹配器假红，结论不可信")

    # ---- doc-freshness ----

    def test_scan_detects_drift_and_skips_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text(
                "共 13 个技能、51 个脚本\n版本 1.24.0\n12 工具\n"
                "上一轮 51 → 53 个脚本（历史记录）\n", encoding="utf-8",
                newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            drifts = self.df.scan(root, truth)
            ids = {d["id"] for d in drifts}
            self.assertIn("F2", ids, "51 个脚本 vs 真值 53 必须判红")
            # 历史行（→）与真值一致的行都不得报
            hist = [d for d in drifts if "→" in d["text"] or "上一轮" in d["text"]]
            self.assertEqual(hist, [], "历史事件值不得判漂移")

    def test_scan_clean_docs_pass(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text(
                "共 13 个技能、53 个脚本\n版本 1.24.0\n12 工具\n200 项\n",
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            self.assertEqual(self.df.scan(root, truth), [])

    def test_f10_line_baseline_detects_drift(self):
        """反向验证（红线 6）：复刻 r157 实景——改 SKILL.md 行数未同步
        BASELINE 行数基线，F10 必须判红。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# demo\n\nline3\n", encoding="utf-8", newline="\n")
            (root / "BASELINE.md").write_text(
                "# BASELINE\n\n- demo: 5\n", encoding="utf-8", newline="\n")
            truth = {"skills": 1, "scripts": 0, "version": "1.0.0",
                     "mcp_tools": 0, "tests": 0,
                     "skill_lines": {"demo": 3}}
            drifts = self.df.scan(root, truth)
            f10 = [d for d in drifts if d["id"] == "F10"]
            self.assertEqual(len(f10), 1, json.dumps(drifts, ensure_ascii=False))
            self.assertEqual(f10[0]["doc_value"], "5")
            self.assertEqual(f10[0]["truth"], "3")

    def test_f10_line_baseline_missing_skill(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "BASELINE.md").write_text(
                "- ghost: 10\n", encoding="utf-8", newline="\n")
            truth = {"skills": 0, "scripts": 0, "version": "1.0.0",
                     "mcp_tools": 0, "tests": 0,
                     "skill_lines": {}}
            drifts = self.df.scan(root, truth)
            f10 = [d for d in drifts if d["id"] == "F10"]
            self.assertEqual(len(f10), 1)
            self.assertEqual(f10[0]["truth"], "missing")

    def test_f10_line_baseline_green_when_synced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skill_dir = root / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "# demo\n\nline3\n", encoding="utf-8", newline="\n")
            (root / "BASELINE.md").write_text(
                "# BASELINE\n\n- demo: 3\n", encoding="utf-8", newline="\n")
            truth = {"skills": 1, "scripts": 0, "version": "1.0.0",
                     "mcp_tools": 0, "tests": 0,
                     "skill_lines": {"demo": 3}}
            f10 = [d for d in self.df.scan(root, truth) if d["id"] == "F10"]
            self.assertEqual(f10, [])

    def test_scan_caliber_must_match_artifact(self):
        """F7：README 头条的 agent 侧口径必须与归档产物一致（不许人工累加）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cal_dir = root / "reports" / "swebench"
            cal_dir.mkdir(parents=True)
            (cal_dir / "code-review-agent.caliber.json").write_text(
                json.dumps({"instances": 18, "resolved": 13}),
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            (root / "README.md").write_text(
                "共 13 个技能、53 个脚本\n版本 1.24.0\n12 工具\n200 项\n"
                "agent 侧口径 **11/13**\n", encoding="utf-8", newline="\n")
            drifts = self.df.scan(root, truth)
            ids = {d["id"] for d in drifts}
            self.assertIn("F7", ids, "口径与归档产物不一致必须判红")
            f7 = next(d for d in drifts if d["id"] == "F7")
            self.assertEqual(f7["truth"], "13/18")
            # 一致时不得报
            (root / "README.md").write_text(
                "共 13 个技能、53 个脚本\n版本 1.24.0\n12 工具\n200 项\n"
                "agent 侧口径 **13/18**\n", encoding="utf-8", newline="\n")
            self.assertEqual(
                [d for d in self.df.scan(root, truth) if d["id"] == "F7"], [])

    def test_scan_status_line_with_arrow_is_still_checked(self):
        """现状行里的「→」不该让整行数字被当历史值跳过（round-23 发现）。

        README 状态块里所有计数都在同一行，行级历史标记一旦命中就等于
        全部计数判据失效。
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "README.md").write_text(
                "契约测试 **231 项全绿**｜目标文件 0/7 可见 → 候选文件 6/7\n",
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            drifts = self.df.scan(root, truth)
            f5 = [d for d in drifts if d["id"] == "F5"]
            self.assertTrue(f5, "含箭头的现状行也必须参与计数对账")
            self.assertEqual(f5[0]["doc_value"], "231")

    def test_scan_agent_caliber_prefers_diagnosis(self):
        """F7：agent 口径真值取 agent-diagnosis，行内箭头不得整行豁免（round-63）。

        状态块一行里必有「→」，旧实现按整行历史标记跳过，F7 对真实 README
        形同虚设；且 caliber 已是 50 条 gold 口径，与 agent 的 20 条不同分母。
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cal_dir = root / "reports" / "swebench"
            cal_dir.mkdir(parents=True)
            (cal_dir / "code-review-agent.caliber.json").write_text(
                json.dumps({"instances": 50, "resolved": 46}),
                encoding="utf-8", newline="\n")
            (cal_dir / "code-review-agent.agent-diagnosis.json").write_text(
                json.dumps({"instances": 20, "resolved": 19}),
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            readme = root / "README.md"
            readme.write_text(
                "共 13 个技能、53 个脚本\n版本 1.24.0\n12 工具\n200 项\n"
                "台账 3 条（open 0）｜agent 侧口径 **18/20**；随后 0 → 1 收敛\n",
                encoding="utf-8", newline="\n")
            f7 = [d for d in self.df.scan(root, truth) if d["id"] == "F7"]
            self.assertEqual(len(f7), 1, "行内箭头不得豁免 F7")
            self.assertEqual(f7[0]["truth"], "19/20",
                             "真值必须取 agent-diagnosis 而非 50 条 caliber")
            readme.write_text(
                "共 13 个技能、53 个脚本\n版本 1.24.0\n12 工具\n200 项\n"
                "台账 3 条（open 0）｜agent 侧口径 **19/20**；随后 0 → 1 收敛\n",
                encoding="utf-8", newline="\n")
            self.assertEqual(
                [d for d in self.df.scan(root, truth) if d["id"] == "F7"], [])

    def test_real_repo_freshness_green(self):
        """真仓全量对账（探针级回归：计数漂移立刻暴露）。"""
        rc, data, _, _ = run(
            ROOT / "skills/self-iteration/scripts/doc-freshness.py",
            "--root", str(ROOT))
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:400])

    def test_f9_duplicate_headings_flagged(self):
        """F9：append-only 复制膨胀（round-81..85 ROADMAP 案）必须判红。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "docs"
            d.mkdir()
            (d / "ROADMAP.md").write_text(
                "## 5. 已内化\n\n### 5.1 round-1\n\nbody\n\n"
                "## 6. 分阶段路线\n\nx\n\n"
                "## 6. 分阶段路线\n\n### 5.1 round-1\n",
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            drifts = self.df.scan(root, truth)
            f9 = [x for x in drifts if x["id"] == "F9"]
            self.assertGreaterEqual(len(f9), 2, "重复标题必须判红")
            self.assertEqual({x["doc"] for x in f9}, {"docs/ROADMAP.md"})

    def test_f9_unique_headings_not_flagged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "docs"
            d.mkdir()
            (d / "ROADMAP.md").write_text(
                "## 5. 已内化\n\n### 5.1 round-1\n\n"
                "## 6. 分阶段路线\n\n### 6.1 阶段一\n",
                encoding="utf-8", newline="\n")
            truth = {"skills": 13, "scripts": 53, "version": "1.24.0",
                     "mcp_tools": 12, "tests": 200}
            f9 = [x for x in self.df.scan(root, truth) if x["id"] == "F9"]
            self.assertEqual(f9, [])


class TestPrecisionGate(unittest.TestCase):
    """eval-harness/precision-gate.py —— ROADMAP §7 评审 precision 护栏（round-62）。

    语料 datasets/reviewbench 不入库，套件只验判定逻辑与输入错误面；真实语料
    由 `run` 子命令在本地/发布签核时执行，产物落 judge.json 可复算。
    round-65（D-047）：基线 corpus 块钉 revision+逐文件 sha256，run /
    check --corpus 先验 pin；反向样例 = 改一个字节 / 换 revision 必须 code=2。
    """

    script = ROOT / "skills" / "eval-harness" / "scripts" / "precision-gate.py"
    baseline = ROOT / "skills" / "eval-harness" / "precision-baseline.json"

    def _write(self, root, name, payload):
        path = Path(root) / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _judge(self, **over):
        data = {"ok": True, "reviewer": "deterministic", "precision": 0.6667,
                "recall": 0.3636, "valid_samples": 11, "weak_samples": 1,
                "claimed": 6, "grounded": 4, "hits": 4}
        data.update(over)
        return data

    def test_pass_on_baseline_shaped_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            judge = self._write(tmp, "judge.json", self._judge())
            rc, data, _, _ = run(self.script, "check", "--judge", judge,
                                 "--baseline", self.baseline)
            self.assertEqual(rc, 0, data)
            self.assertTrue(data["ok"])
            self.assertEqual(data["status"], "PASS")
            self.assertEqual(data["failed"], [])

    def test_each_guardrail_fires(self):
        cases = [
            ("precision_floor", {"precision": 0.66}, {"floor": 0.9},
             "BELOW_FLOOR"),
            ("precision_trend", {"precision": 0.68}, {"precision": 0.75},
             "DRIFT"),
            ("sample_drift", {"valid_samples": 12}, {"valid_samples": 11},
             "SAMPLE_DRIFT"),
            ("reviewer_match", {"reviewer": "host"}, {"reviewer": "deterministic"},
             "REVIEWER_MISMATCH"),
        ]
        base = json.loads(self.baseline.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            judge = self._write(tmp, "judge.json", self._judge())
            for check_id, judge_over, base_over, status in cases:
                with self.subTest(check=check_id):
                    j = self._write(tmp, "judge-%s.json" % check_id,
                                    self._judge(**judge_over))
                    b = self._write(tmp, "base-%s.json" % check_id,
                                    dict(base, **base_over))
                    rc, data, _, _ = run(self.script, "check", "--judge", j,
                                         "--baseline", b)
                    self.assertEqual(rc, 1, (check_id, data))
                    self.assertEqual(data["status"], status)
                    self.assertEqual(data["failed"], [check_id])

    def test_missing_inputs_are_code2(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, data, _, _ = run(self.script, "check",
                                 "--judge", Path(tmp) / "nope.json",
                                 "--baseline", self.baseline)
            self.assertEqual(rc, 2)
            self.assertFalse(data["ok"])
            rc, data, _, _ = run(self.script, "run",
                                 "--corpus", Path(tmp) / "no-corpus",
                                 "--out", Path(tmp) / "out",
                                 "--baseline", self.baseline)
            self.assertEqual(rc, 2)
            self.assertIn("语料目录不存在", data["error"])

    def test_shipped_baseline_shape(self):
        data = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "precision-baseline/2")
        self.assertEqual(data["floor"], 0.65)
        self.assertEqual(data["tolerance"], 0.01)
        self.assertEqual(data["reviewer"], "deterministic")
        self.assertEqual(data["valid_samples"], 11)
        self.assertEqual(data["precision"], 0.6667)
        corpus = data["corpus"]
        self.assertEqual(corpus["upstream"],
                         "https://github.com/review-bench/ReviewBench")
        self.assertRegex(corpus["revision"], r"^[0-9a-f]{40}$")
        files = corpus["files"]
        self.assertEqual(len(files), 26, "12 diff + 12 golden + 样本清单 + manifest")
        self.assertIn("samples-py.json", files)
        self.assertIn("corpus/manifest.json", files)
        self.assertTrue(any(k.startswith("diffs/") for k in files))
        self.assertTrue(any(k.startswith("golden/") for k in files))

    def _git_corpus(self, root, files):
        """建一个带 git revision 的合成语料目录，返回 (目录, HEAD sha)。"""
        corpus = Path(root) / "synthetic-corpus"
        for name, text in files.items():
            p = corpus / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "corpus"]):
            p = subprocess.run(["git", "-C", str(corpus)] + args,
                               capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        sha = subprocess.run(["git", "-C", str(corpus), "rev-parse", "HEAD"],
                             shell=False, capture_output=True, text=True,
                             encoding="utf-8").stdout.strip()
        return corpus, sha

    def _pin_sha(self, corpus, rel):
        import hashlib
        return hashlib.sha256((Path(corpus) / rel).read_bytes()).hexdigest()

    def _pinned_baseline(self, root, revision, files):
        base = json.loads(self.baseline.read_text(encoding="utf-8"))
        base["corpus"] = {"revision": revision, "files": files}
        return self._write(root, "base-pin.json", base)

    def test_check_with_corpus_verifies_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, sha = self._git_corpus(tmp, {
                "samples-py.json": "[{\"sample_id\": \"s\"}]\n",
                "corpus/manifest.json": "{}\n",
            })
            files = {rel: self._pin_sha(corpus, rel)
                     for rel in ("samples-py.json", "corpus/manifest.json")}
            base = self._pinned_baseline(tmp, sha, files)
            judge = self._write(tmp, "judge.json", self._judge())
            rc, data, _, err = run(self.script, "check", "--judge", judge,
                                   "--baseline", base, "--corpus", corpus)
            self.assertEqual(rc, 0, (data, err))
            pin = data["corpus_pin"]
            self.assertEqual(pin["status"], "PASS")
            self.assertEqual(pin["files_verified"], 2)
            self.assertEqual(pin["actual_revision"], sha)

    def test_pin_mismatch_is_code2(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus, sha = self._git_corpus(tmp, {
                "samples-py.json": "[{\"sample_id\": \"s\"}]\n",
            })
            good = {"samples-py.json": self._pin_sha(corpus, "samples-py.json")}
            judge = self._write(tmp, "judge.json", self._judge())

            # 反向 1：语料内容改一个字节 → sha256 不匹配
            (corpus / "samples-py.json").write_text("[{\"sample_id\": \"x\"}]\n",
                                                    encoding="utf-8")
            base = self._pinned_baseline(tmp, sha, good)
            rc, data, _, _ = run(self.script, "check", "--judge", judge,
                                 "--baseline", base, "--corpus", corpus)
            self.assertEqual(rc, 2, data)
            self.assertIn("sha256 不匹配", data["error"])

            # 反向 2：基线钉的 revision 不是语料 HEAD
            base = self._pinned_baseline(
                tmp, "0" * 40, {"samples-py.json": self._pin_sha(corpus, "samples-py.json")})
            rc, data, _, _ = run(self.script, "check", "--judge", judge,
                                 "--baseline", base, "--corpus", corpus)
            self.assertEqual(rc, 2, data)
            self.assertIn("revision 不匹配", data["error"])

            # 反向 3：run 在评测前就拦 pin（不触评测器也能判红）
            rc, data, _, _ = run(self.script, "run", "--corpus", corpus,
                                 "--out", Path(tmp) / "out",
                                 "--baseline", base)
            self.assertEqual(rc, 2, data)
            self.assertIn("pin 校验失败", data["error"])


class TestVerifyClosureCommands(unittest.TestCase):
    """scripts/verify-closure-commands.py —— 台账结案口径逐条实跑（round-31 第 8 项）。

    抽取判据的四条精度规则与执行侧的三条修复都有对应断言；缺省 dry-run 一律不动盘，
    实跑只在显式 `--run` 下发生——反向验证锚点就是这条：把会写文件、会退非 0 的命令
    放进台账，dry-run 必须既不留痕也不报错，`--run` 必须既留痕又判违规。
    """

    @classmethod
    def setUpClass(cls):
        cls.script = ROOT / "scripts" / "verify-closure-commands.py"
        spec = importlib.util.spec_from_file_location(
            "verify_closure_commands", cls.script)
        cls.vc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.vc)

    def _ledger(self, root, notes):
        """写一份最小台账：[{"id","status","closure_note"}...]"""
        payload = {"pitfalls": [{"id": "p%02d" % i, "category": "行为回归",
                                 "description": "d", "source": "s", "status": "closed",
                                 "closure_note": n} for i, n in enumerate(notes)]}
        path = Path(root) / "retro"
        path.mkdir(parents=True, exist_ok=True)
        (path / "pitfalls.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path / "pitfalls.json"

    def test_extraction_accepts_commands_and_rejects_prose(self):
        got = self.vc.extract_commands(
            "根治已落地。复跑命令 scripts/sibling-test-realbench.py --verbose 二次得同一组数字；"
            "写入点闸门在 skills/retro/scripts/retro-report.py main() 之前检查 → 退出码 2")
        self.assertEqual(got, ["scripts/sibling-test-realbench.py --verbose"],
                         "散文里顺带提到的脚本名（retro-report.py main）不是口径")

    def test_extraction_drops_command_nested_inside_quotes(self):
        # 夹具里刻意不写全被台账口径计数的那条字面量——否则本测试自己就成了第 2 处命中，
        # 「检查器改变了被检查的东西」（round-31 实跑时真撞上，见 retro/pitfalls.json）。
        got = self.vc.extract_commands(
            r"验收：grep -c '\.venv/Scripts/python\.exe' README.md → 1")
        self.assertEqual(len(got), 1, got)
        self.assertTrue(got[0].startswith("grep -c"), got[0])

    def test_classify_shapes(self):
        c = self.vc.classify
        self.assertEqual(c(r"grep -c '\.venv/x' README.md"), "ok")
        self.assertEqual(c(r"grep -c '\.venv/x'"), "incomplete", "缺文件操作数的 grep 会读 stdin")
        self.assertEqual(c(".venv/Scripts/python.exe -m unittest tests.test_repair -k x"),
                         "unrunnable_shape", "与 retro-ledger 写入口闸门同口径")
        self.assertEqual(c(".venv/Scripts/python.exe -m unittest discover -s tests -p t.py"), "ok")
        self.assertEqual(c("scripts/x.py --out <dataset>.json"), "placeholder")
        self.assertEqual(c("scripts/verify-closure-commands.py --run"), "self_reference",
                         "口径写「再跑一遍本检查器」= --run 自我递归，只登记不执行")

    def test_extraction_trims_markdown_code_span_backticks(self):
        got = self.vc.extract_commands("复跑 `scripts/verify-closure-commands.py --run` 之后")
        self.assertEqual(got, ["scripts/verify-closure-commands.py --run"],
                         "反引号是 markdown 代码包裹，不属于命令本体")

    def test_extraction_keeps_quoted_parentheses_and_semicolons(self):
        """round-63：引号内的 ( ; ) 是命令正文，不得当句读截断。"""
        note = (".venv/Scripts/python.exe -c \"import json;"
                "d=json.load(open('x.json'));"
                "assert d['n']==1;print('OK')\"；"
                "台账另跑 grep -c 'a' README.md")
        got = self.vc.extract_commands(note)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(got[0].endswith("print('OK')\""), got[0])
        self.assertEqual(self.vc.classify(got[0]), "ok")
        self.assertEqual(got[1], "grep -c 'a' README.md")

    def test_extraction_quote_aware_cut_has_upper_bound(self):
        """反向：未闭合引号扫到末尾仍是 unrunnable_shape，宽松不放行。"""
        got = self.vc.extract_commands(
            ".venv/Scripts/python.exe -c \"print('未闭合")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(self.vc.classify(got[0]), "unrunnable_shape")
        # 引号外 CJK 仍断句（且引号内的中文不提前截断命令）
        got = self.vc.extract_commands(
            ".venv/Scripts/python.exe -c \"print('中文')\"→ 0")
        self.assertEqual(got, [".venv/Scripts/python.exe -c \"print('中文')\""])
        self.assertEqual(
            self.vc.extract_commands("复跑 scripts/x.py --flag 后看结果"),
            ["scripts/x.py --flag"])

    def test_self_reference_is_reported_and_never_executed(self):
        """自我递归口径判违规且不进 subprocess（否则 --run 会一层层套下去）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts").mkdir()
            (root / "scripts" / "verify-closure-commands.py").write_text(
                "import pathlib, sys\n"
                "pathlib.Path('recursed.marker').write_text('ran')\n"
                "sys.exit(0)\n", encoding="utf-8")
            ledger = self._ledger(root, ["验收：scripts/verify-closure-commands.py --run"])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root), "--run")
            self.assertEqual(rc, 1, (out + err)[:300])
            self.assertEqual(data["totals"]["self_reference"], 1)
            self.assertEqual(data["totals"]["executed"], 0, "自我递归的一条都不许真跑")
            self.assertFalse((root / "recursed.marker").exists())
            self.assertEqual(data["violations"][0]["reason"], "self_reference")

    def test_argv_of_handles_env_prefix_and_py_launcher_and_escapes(self):
        env, argv, injected = self.vc._argv_of(
            "PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m unittest discover -s tests")
        self.assertEqual(env, {"PYTHONIOENCODING": "utf-8"})
        self.assertEqual(argv[0], ".venv/Scripts/python.exe", "环境前缀不能当成可执行文件")
        self.assertFalse(injected)
        env, argv, injected = self.vc._argv_of("scripts/sibling-test-realbench.py --verbose")
        self.assertEqual(argv[0], sys.executable, "Windows 下 .py 不能直接执行")
        self.assertEqual(argv[1:], ["scripts/sibling-test-realbench.py", "--verbose"])
        self.assertTrue(injected)
        _, argv, _ = self.vc._argv_of(r"grep -c '\.venv/Scripts/python' README.md")
        self.assertEqual(argv[2], r"\.venv/Scripts/python",
                         "反斜杠是正则转义，全局换成 / 会造成静默假阴性")

    def test_dry_run_executes_nothing_and_run_reports_failure(self):
        """反向验证锚点：同一条会写文件、会退非 0 的口径，dry-run 不动盘，--run 判违规。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts").mkdir()
            (root / "scripts" / "boom.py").write_text(
                "import pathlib, sys\n"
                "pathlib.Path('boom.marker').write_text('ran')\n"
                "sys.exit(3)\n", encoding="utf-8")
            ledger = self._ledger(root, ["验收：scripts/boom.py --flag → 应当非 0"])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root))
            self.assertEqual(rc, 0, (out + err)[:300])
            self.assertEqual(data["mode"], "dry-run")
            self.assertEqual(data["totals"]["executed"], 0)
            self.assertEqual(data["totals"]["commands"], 1)
            self.assertFalse((root / "boom.marker").exists(), "dry-run 绝不能执行任何东西")
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root), "--run")
            self.assertEqual(rc, 1, (out + err)[:300])
            self.assertTrue((root / "boom.marker").exists(), "--run 必须真的跑了")
            self.assertEqual(data["totals"]["failed"], 1)
            self.assertEqual(data["violations"][0]["id"], "p00")
            self.assertIn("退出码 3", data["violations"][0]["reason"])

    def test_bad_shape_is_reported_not_run(self):
        """形状不过的口径只登记违规，绝不进 subprocess（否则等于拿假口径去跑真命令）。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "scripts").mkdir()
            (root / "scripts" / "boom.py").write_text(
                "import pathlib\npathlib.Path('boom.marker').write_text('ran')\n", encoding="utf-8")
            ledger = self._ledger(root, [
                "验收：scripts/boom.py --out <test_name> 跑一遍",
                "验收：.venv/Scripts/python.exe -m unittest tests.test_repair -k x",
            ])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root), "--run")
            self.assertEqual(rc, 1, (out + err)[:300])
            self.assertEqual(data["totals"]["executed"], 0, "形状不过的一律不实跑")
            self.assertFalse((root / "boom.marker").exists())
            self.assertEqual(sorted(v["reason"] for v in data["violations"]),
                             ["placeholder", "unrunnable_shape"])

    def test_closed_note_without_command_is_counted_not_violated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = self._ledger(root, ["根治已落地：改了三处写盘点，人工复核通过"])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root))
            self.assertEqual(rc, 0, (out + err)[:300])
            self.assertEqual(data["totals"]["no_command"], 1)
            self.assertEqual(data["no_command_closed_ids"], ["p00"],
                             "无可复算命令要如实摆出来，但不判违规")

    def test_closure_classification_three_ways(self):
        """结案口径三分类（round-33 检查单第 8 项；规则先于真台账数字写死）。

        反向验证锚：把 classify_closure 的两个信号判据删掉任何一个，
        「裸结论」例就会混进 human_conclusion，本测试立刻转红。
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = self._ledger(root, [
                "验收：scripts/sibling-test-bench.py --verbose 数字不变",        # p00 机器可复算
                "结案：历经 4 次全量零重现，两轮内复发即重开",                    # p01 人工结论型
                "根治已落地：改了三处写盘点，人工复核通过",                       # p02 裸结论（薄弱）
            ])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root))
            self.assertEqual(rc, 0, (out + err)[:300])
            t = data["totals"]
            self.assertEqual(t["machine_checkable"], 1)
            self.assertEqual(t["human_conclusion"], 1,
                             "带复验条件+期限的时间性口径是合法的人工结论型")
            self.assertEqual(t["weak_closure"], 1,
                             "两类信号缺任一 = 薄弱，如实摆出来不判违规")
            self.assertEqual(data["human_conclusion_ids"], ["p01"])
            self.assertEqual(data["weak_closure_ids"], ["p02"])
            self.assertEqual(data["no_command_closed_ids"], ["p01", "p02"],
                             "无命令名单不变，分类是其上的细分")
            by_id = {r["id"]: r for r in data["records"]}
            self.assertEqual(by_id["p00"]["closure_class"], "machine_checkable")
            self.assertEqual(by_id["p01"]["closure_class"], "human_conclusion")
            self.assertEqual(by_id["p02"]["closure_class"], "weak_closure")

    def test_closure_classification_requires_both_signals(self):
        """只有期限没有复验条件（或反过来）都算薄弱——两个信号缺一不可。"""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = self._ledger(root, [
                "三轮内有效",                 # p00 只有期限
                "复跑观察过",                 # p01 只有条件
            ])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root))
            self.assertEqual(rc, 0, (out + err)[:300])
            self.assertEqual(data["totals"]["weak_closure"], 2)
            self.assertEqual(data["totals"]["human_conclusion"], 0)

    def test_prose_test_ref_becomes_machine_checkable(self):
        """tests/...::test_ 散文钉法 → 合成唯一规范命令（derived_from 标注）。

        反向验证锚：摘掉 synthesize_from_prose 的调用，本例立刻回到
        weak_closure——消化能力就是这一个分支给的。
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = self._ledger(root, [
                "验收：钉住 tests/test_retro.py::test_round_gap 即可",   # p00 散文钉法
                "根治已落地：改了三处写盘点，人工复核通过",               # p01 仍裸结论
            ])
            rc, data, out, err = run(self.script, "--ledger", str(ledger), "--root", str(root))
            self.assertEqual(rc, 0, (out + err)[:300])
            t = data["totals"]
            self.assertEqual(t["machine_checkable"], 1)
            self.assertEqual(t["weak_closure"], 1, "不含散文引用的裸结论仍是薄弱")
            self.assertEqual(t["prose_derived"], 1)
            by_id = {r["id"]: r for r in data["records"]}
            cmd = by_id["p00"]["commands"][0]
            self.assertEqual(cmd["derived_from"], "prose_test_ref")
            self.assertIn("discover -s tests -p test_retro.py -k test_round_gap",
                          cmd["command"], "合成命令必须走 discover 形态（检查单第 10 条纪律）")
            self.assertNotIn("p00", data["weak_closure_ids"])

    def test_missing_ledger_is_input_error(self):
        with tempfile.TemporaryDirectory() as td:
            rc, data, out, err = run(self.script, "--ledger", str(Path(td) / "nope.json"),
                                     "--root", td)
            self.assertEqual(rc, 2)
            self.assertFalse(data["ok"])

    def test_real_ledger_closure_commands_pass(self):
        """真台账静态门禁：所有结案口径里的命令形状必须全过（实跑另由人工 --run）。"""
        rc, data, out, err = run(self.script, "--root", str(ROOT))
        self.assertEqual(rc, 0, json.dumps(data.get("violations"), ensure_ascii=False)[:400])
        self.assertGreater(data["totals"]["commands"], 0, "真台账里应有可复算口径")




class TruthValuesTests(unittest.TestCase):
    """truth_values() 真值提取行为断言（r166，变异抽样 9 盲区的处方补齐）。

    F8 块（deepswe 计数/canary/manifest 回退）是「信息项不判漂移」，常量变异
    在 rc==0 端到端测试下天然存活——抽样数据（kill_rate 0.1，9 盲区集中
    L61-117）指向本函数无直接断言。逐字段断言提取值即补行为断言。
    """

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "doc_freshness_tv", ROOT / "skills/self-iteration/scripts/doc-freshness.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.tv = staticmethod(mod.truth_values)

    def _fake_root(self, tmp, task_lines=3, canary=None, manifest=None):
        import json as _json
        (tmp / "skills" / "self-iteration" / "scripts").mkdir(parents=True)
        (tmp / "skills" / "demo").mkdir(parents=True)
        (tmp / "skills" / "demo" / "SKILL.md").write_text(
            "# demo\nline2\n", encoding="utf-8", newline="\n")
        (tmp / ".zcode-plugin").mkdir(parents=True)
        (tmp / ".zcode-plugin" / "plugin.json").write_text(
            _json.dumps({"version": "9.9.9"}), encoding="utf-8")
        (tmp / "mcp").mkdir(parents=True)
        (tmp / "mcp" / "review_mcp.py").write_text(
            '"name": "code_review_a", "name": "code_review_b"',
            encoding="utf-8", newline="\n")
        (tmp / "retro").mkdir(parents=True)
        (tmp / "retro" / "pitfalls.json").write_text(_json.dumps(
            {"pitfalls": [{"id": "x", "category": "手工",
                           "description": "d", "status": "open"}]}),
            encoding="utf-8", newline="\n")
        (tmp / "tests").mkdir()
        (tmp / "tests" / "__init__.py").write_text("", encoding="utf-8")
        ds = tmp / "skills" / "eval-harness" / "data"
        ds.mkdir(parents=True)
        (ds / "deepswe-tasks.jsonl").write_text(
            "\n".join(["{}"] * task_lines) + "\n",
            encoding="utf-8", newline="\n")
        (ds / "deep-swe").mkdir()
        if canary is not None:
            (ds / "deep-swe" / ".deep-swe-canary").write_text(
                canary, encoding="utf-8", newline="\n")
        if manifest is not None:
            (ds / "deep-swe" / "tasks").mkdir()
            (ds / "deep-swe" / "tasks" / "manifest.json").write_text(
                _json.dumps({"canary": manifest}), encoding="utf-8")
        return tmp

    def test_truth_values_extracts_f8_block(self):
        """canary 直读优先于 manifest 回退；计数逐行非空行；目录存在性如实。"""
        with tempfile.TemporaryDirectory() as td:
            root = self._fake_root(Path(td), task_lines=3,
                                   canary="abc-123\n", manifest="fallback-9")
            t = self.tv(root)
            self.assertEqual(t["deepswe_task_count"], 3)
            self.assertTrue(t["deepswe_data_present"])
            self.assertFalse(t["deepswe_baseline_present"])
            self.assertEqual(t["deepswe_canary"], "abc-123",
                             "canary 直读必须优先于 manifest 回退")
            self.assertEqual(t["deepswe_status"], "partial",
                             "计数 3 ≠ 113 → partial（113 特判的另一半）")

    def test_truth_values_manifest_fallback_and_full_count(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._fake_root(Path(td), task_lines=113, manifest="m-1")
            t = self.tv(root)
            self.assertEqual(t["deepswe_task_count"], 113)
            self.assertEqual(t["deepswe_canary"], "m-1",
                             "无 canary 文件时回退 manifest")
            self.assertEqual(t["deepswe_status"], "active",
                             "113 + 数据目录 → active 特判")
