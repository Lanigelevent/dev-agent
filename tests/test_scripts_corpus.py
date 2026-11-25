# -*- coding: utf-8 -*-
"""tests/test_scripts_corpus.py — 语料与口径：TestStdinIsUtf8 / TestReproductionIsReal / TestRulesSelect（round-88 P2-8 自 test_scripts.py 机械拆出）。

原文按行区间逐字搬移（内容零改动）；共享夹具/runner 在
tests/_scripts_common.py（每进程构建一次，tearDownModule 交 tmpspace
atexit 兜底）。
"""
from _scripts_common import *  # noqa: F401,F403
import _scripts_common


def setUpModule():
    _scripts_common.ensure_fixture()


class TestStdinIsUtf8(unittest.TestCase):
    """stdin 契约：子代理的中文载荷必须原样进出，不跟宿主 ANSI locale 走。

    根因（round-31 全量套件 8 红里挖出的一条）：中文 Windows 桌面默认 locale 是
    cp936，子进程的 `sys.stdin` 因此按 **GBK** 打开（errors 依 locale 为
    surrogateescape）。脚本们过去只 reconfigure 了 stdout/stderr，漏了 stdin，
    于是上游以 `ensure_ascii=False` 送来的 UTF-8 中文字节在进校验器之前就被解坏：

      * findings-check：损坏后的文本打印不出来 → UnicodeEncodeError → 退出码 1，
        形状完全像「校验没过」，runner 于是把整批发现丢掉（跑成功、产出为空）；
      * report-check / score：中文章节名/区域名变乱码 → 「找不到补丁段」；
      * engines/libcst_adapter：带中文注释的源码进 codemod 前就坏了。

    复现与宿主无关：把孩子的 stdio 显式钉成 GBK（`PYTHONIOENCODING`），这正是
    该 locale 下 `sys.stdin` 的打开方式；`TestReproductionIsReal` 先证明这个旋钮
    确实会破坏不 reconfigure stdin 的子进程，下面几条才不是空过。
    """

    GBK = {"PYTHONIOENCODING": "gbk"}
    GBK_ESC = {"PYTHONIOENCODING": "gbk:surrogateescape"}
    CJK = CJK_PROBE

    def _finding_payload(self):
        good = {"loc": "a.py:1", "desc": self.CJK, "evidence": "e",
                "severity": "低", "confidence": "低",
                "cause": "完整因果链说明", "fix": "f"}
        return json.dumps({"findings": [good], "coverage_note": self.CJK},
                          ensure_ascii=False)

    def test_findings_check_survives_surrogateescape_stdio(self):
        """本机实踩形状：代理对 → 打印炸 → rc 1 被误读成「校验没过」。"""
        rc, data, out, err = run(SCRIPTS["findings-check.py"], "-",
                                 "--dimensions", "正确性与逻辑缺陷",
                                 stdin=self._finding_payload(),
                                 env_extra=self.GBK_ESC)
        self.assertEqual(rc, 0, (err or "")[-200:] or str(data)[:200])
        self.assertTrue(data["ok"], json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["accepted"], 1)

    def test_findings_check_survives_plain_gbk_stdio(self):
        """乱码形状：解码不报错但内容已坏，枚举值「低」认不出 → 整项被拒。"""
        rc, data, out, err = run(SCRIPTS["findings-check.py"], "-",
                                 "--dimensions", "正确性与逻辑缺陷",
                                 stdin=self._finding_payload(),
                                 env_extra=self.GBK)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["rejected"], 0)

    def test_report_check_survives_gbk_stdio(self):
        report = "\n".join([
            "# 代码评审报告", "", "【评审口径】对象 A..B", "",
            "## 运行信息", "档位 S", "", "## 一、变更摘要", "1 文件", "",
            "## 二、风险评分", "1.0 低", "", "## 三、测试建议", self.CJK, "",
            "## 四、优化步骤手册", "建议阅读顺序：先高后低", "",
            "## 五、行内评论", "a.py:1 | 高 | 示例", "",
            "## 六、修复补丁建议", "未生成补丁：材料窗口不足", ""])
        rc, data, out, err = run(SCRIPTS["report-check.py"], "-",
                                 stdin=report, env_extra=self.GBK)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["missing"], [])

    def test_score_echoes_chinese_region_name(self):
        region = {"name": self.CJK, "added": 120, "deleted": 10, "files": 2,
                  "modules": 1, "callers": 5, "history_3m": 2, "history_12m": 4}
        payload = json.dumps({"regions": [region], "overall": region},
                             ensure_ascii=False)
        rc, data, out, err = run(SCRIPTS["score.py"], stdin=payload,
                                 env_extra=self.GBK)
        self.assertEqual(rc, 0, (err or "")[-200:] or str(data)[:200])
        self.assertEqual(data["regions"][0]["name"], self.CJK,
                         "区域名被 locale 解码损坏：进 stdin 与出 stdout 必须同一串")

    def test_non_ascii_argv_is_not_affected(self):
        """旋钮只影响管道 stdio，不影响 --dimensions 的中文 argv（守住测试边界）。"""
        rc, data, out, err = run(SCRIPTS["findings-check.py"], "-",
                                 "--dimensions", "正确性与逻辑缺陷、" + self.CJK,
                                 stdin=self._finding_payload(),
                                 env_extra=self.GBK)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertIn(self.CJK, data["dimensions"],
                      "argv 走 Windows Unicode API，不该被 stdio 编码牵连")


class TestReproductionIsReal(unittest.TestCase):
    """证明上面的 GBK 旋钮真的会破坏「不 reconfigure stdin」的子进程。

    没有这条，四条契约测试可能在一台本来就是 UTF-8 的机器上空过——它们断言的
    「内容没坏」会同时由宿主 locale 免费保证，测试就成了摆设。这条只依赖
    PYTHONIOENCODING（Python 自带 gbk codec），因此任何平台都能判真假。
    """

    def test_gbk_stdio_corrupts_a_naive_child(self):
        child = ("import sys, json\n"
                 "d = sys.stdin.read()\n"
                 "sys.stdout.buffer.write("
                 "json.dumps({'enc': sys.stdin.encoding, 'len': len(d)}).encode())\n")
        payload = CJK_PROBE
        p = subprocess.run([sys.executable, "-c", child], shell=False,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", input=payload, timeout=60,
                           env={**os.environ, "PYTHONIOENCODING": "gbk"})
        if p.returncode != 0:
            return  # 解码直接炸：同样是「不 reconfigure 就会坏」的证据
        info = json.loads(p.stdout)
        self.assertNotIn("utf", info["enc"].lower(),
                         "旋钮没生效：孩子仍按 UTF-8 读 stdin，上面的测试会是空过")
        self.assertNotEqual(info["len"], len(payload),
                            "GBK 下 UTF-8 中文字节必须被解成不同长度，否则复现不成立")




class TestRulesSelect(unittest.TestCase):
    """规则文档选择器契约：路径→规则文档映射、截断、路径穿越防护。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rules-select-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        rules = self.tmp / "skills" / "multi-agent-review" / "rules"
        rules.mkdir(parents=True)
        (rules / "index.json").write_text(json.dumps({
            "mappings": [
                {"pattern": "*.py", "docs": ["a-rule.md"]},
                {"pattern": "**/migrations/**", "docs": ["b-schema.md"]},
            ]}, ensure_ascii=False), encoding="utf-8")
        (rules / "a-rule.md").write_text("# 规则A\n内容A", encoding="utf-8")
        (rules / "b-schema.md").write_text("# 规则B\n内容B", encoding="utf-8")

    def run_sel(self, *args, stdin=None):
        return run(SCRIPTS["rules-select.py"], "--root", str(self.tmp), *args,
                   stdin=stdin)

    def test_py_file_hits_python_rule(self):
        rc, data, _, _ = self.run_sel("--files", "svc/payment.py")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["matched"], ["a-rule.md"])
        self.assertIn("内容A", data["block"])

    def test_migrations_hits_both(self):
        rc, data, _, _ = self.run_sel("--files", "app/migrations/0001_init.py")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["matched"], ["a-rule.md", "b-schema.md"])

    def test_no_hit_empty_block(self):
        rc, data, _, _ = self.run_sel("--files", "docs/readme.md")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["matched"], [])
        self.assertEqual(data["block"], "")

    def test_stdin_and_names_only(self):
        rc, data, _, _ = self.run_sel("--stdin", "--names-only",
                                      stdin="a/b.py\n")
        self.assertEqual(rc, 0, data)
        self.assertEqual(data["matched"], ["a-rule.md"])
        self.assertEqual(data["block"], "")

    def test_bad_index_rc1(self):
        (self.tmp / "skills" / "multi-agent-review" / "rules" /
         "index.json").write_text("{broken", encoding="utf-8")
        rc, data, _, _ = self.run_sel("--files", "a.py")
        self.assertEqual(rc, 1)
        self.assertFalse(data["ok"])

    def test_runner_wires_rules_select(self):
        """runner 材料装配必须调用 rules-select.py（静态接线契约）。"""
        src = (ROOT / "skills" / "orchestrator" / "scripts" /
               "runner.py").read_text(encoding="utf-8")
        self.assertIn("rules-select.py", src)
        self.assertIn("规则文档（路径命中的评审规则", src)

    def test_v2_js_ts_mappings(self):
        """v2 扩展：JS/TS 文件命中 var/eval/debug 三条规则文档。"""
        rules = self.tmp / "skills" / "multi-agent-review" / "rules"
        (rules / "index.json").write_text(json.dumps({
            "mappings": [
                {"pattern": "*.js", "docs": ["js-var.md", "js-eval.md"]},
                {"pattern": "*.ts", "docs": ["js-var.md", "js-eval.md"]},
            ]}, ensure_ascii=False), encoding="utf-8")
        (rules / "js-var.md").write_text("var scope", encoding="utf-8")
        (rules / "js-eval.md").write_text("eval risk", encoding="utf-8")
        for ext in (".js", ".ts"):
            rc, data, _, _ = self.run_sel("--files", "app/mod" + ext,
                                           "--names-only")
            self.assertEqual(rc, 0, data)
            self.assertEqual(data["matched"], ["js-var.md", "js-eval.md"],
                             "%s 应命中 JS/TS 规则" % ext)

    def test_v2_shared_debug_rule_cross_lang(self):
        """debug-statement-residue 规则跨 Python+JS/TS 共享。"""
        rules = self.tmp / "skills" / "multi-agent-review" / "rules"
        (rules / "index.json").write_text(json.dumps({
            "mappings": [
                {"pattern": "*.py", "docs": ["debug.md"]},
                {"pattern": "*.js", "docs": ["debug.md"]},
            ]}, ensure_ascii=False), encoding="utf-8")
        (rules / "debug.md").write_text("debug residue", encoding="utf-8")
        rc, data, _, _ = self.run_sel("--files", "a.py", "--names-only")
        self.assertIn("debug.md", data["matched"])
        rc, data, _, _ = self.run_sel("--files", "b.js", "--names-only")
        self.assertIn("debug.md", data["matched"])

    def test_v2_production_index_contract(self):
        """生产 index.json（v2）形状契约：含 JS/TS 映射 + 版本 2。"""
        ipath = (ROOT / "skills" / "multi-agent-review" / "rules" /
                 "index.json")
        data = json.loads(ipath.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 2)
        patterns = [m["pattern"] for m in data["mappings"]]
        self.assertIn("*.py", patterns)
        self.assertIn("*.js", patterns)
        self.assertIn("*.ts", patterns)
        # 每条映射的 docs 都有对应的 .md 文件存在
        rules_dir = ipath.parent
        for m in data["mappings"]:
            for doc in m["docs"]:
                self.assertTrue((rules_dir / doc).is_file(),
                                 "规则文档 %s 不存在（映射 %s 引用）"
                                 % (doc, m["pattern"]))


