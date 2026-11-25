#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_cve_corpus.py — CVEfixes 适配器契约断言。

用自建 mini-CVEfixes SQLite 夹具验证：发现式 schema（任意列名）、语言
过滤、resolve 模式的父提交解析与 pending_parent 如实标注、zip 形态解包。
"""

import json
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace
from _scripts_common import SCRIPTS


def _make_db(path):
    """自建 mini-CVEfixes：故意用非官方列名验证发现式 schema。"""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE metadata (id INTEGER PRIMARY KEY)")
    conn.execute(
        "CREATE TABLE fix_map ("
        " fix_commit TEXT, repo_url TEXT, file_path TEXT)")
    rows = [
        ("a" * 40, "https://github.com/urllib3/urllib3", "src/urllib3/x.py"),
        ("a" * 40, "https://github.com/urllib3/urllib3", "src/urllib3/y.py"),
        ("b" * 40, "https://github.com/psf/requests", "requests/api.py"),
        ("c" * 40, "https://github.com/x/jslib", "src/index.js"),
        ("not-a-hash", "https://github.com/x/y", "a.py"),
    ]
    conn.executemany("INSERT INTO fix_map VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()


class TestCveCorpus(unittest.TestCase):
    """发现式 schema / 语言过滤 / resolve / zip 形态。"""

    def setUp(self):
        self.tmp = tmpspace.create(prefix="cve-corpus-")
        self.addCleanup(tmpspace.release, self.tmp)
        self.db = self.tmp / "mini.sqlite"
        _make_db(self.db)

    def test_discovery_and_lang_filter(self):
        out = self.tmp / "samples.json"
        rc, data, _, _ = test_scripts.run(SCRIPTS["cve-corpus.py"],
                                          "--db", self.db,
                                          "--lang", "python",
                                          "--limit", "10", "--out", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["table"], "fix_map")
        self.assertEqual(data["samples"], 2, "两 Python 修复提交（js 与坏哈希剔除）")
        samples = json.loads(out.read_text(encoding="utf-8"))["samples"]
        by_sha = {s["fix_commit"]: s for s in samples}
        self.assertEqual(len(by_sha["a" * 40]["files"]), 2, "同提交文件聚合")
        self.assertEqual(by_sha["b" * 40]["files"], ["requests/api.py"])
        self.assertEqual(by_sha["b" * 40]["defect_class"], "cve")

    def test_resolve_with_local_clone(self):
        # 本地克隆夹具：两提交的迷你仓（owner__name 布局）
        repo = self.tmp / "repos" / "urllib3__urllib3"
        repo.mkdir(parents=True)
        (repo / "x.py").write_text("v1\n", encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "c1"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        sha2 = subprocess.run(["git", "-C", str(repo), "commit", "-q",
                               "-m", "c2", "--allow-empty"],
                              shell=False, capture_output=True, text=True,
                              env={"GIT_AUTHOR_NAME": "t",
                                   "GIT_AUTHOR_EMAIL": "t@t",
                                   "GIT_COMMITTER_NAME": "t",
                                   "GIT_COMMITTER_EMAIL": "t@t",
                                   **__import__("os").environ})
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              shell=False, capture_output=True,
                              text=True).stdout.strip()
        # 把夹具 DB 里 a*40 换成真实 HEAD（可解析父提交）
        conn = sqlite3.connect(str(self.db))
        conn.execute("UPDATE fix_map SET fix_commit=? WHERE fix_commit=?",
                     (head, "a" * 40))
        conn.commit()
        conn.close()
        out = self.tmp / "samples.json"
        rc, data, _, _ = test_scripts.run(
            SCRIPTS["cve-corpus.py"], "--db", self.db, "--lang", "python",
            "--limit", "10", "--out", out, "--resolve",
            "--repos-dir", self.tmp / "repos")
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["parent_resolved"], 1, "本地克隆样本应解析成功")
        self.assertEqual(data["pending_parent"], 1, "无克隆样本如实标 pending")
        samples = json.loads(out.read_text(encoding="utf-8"))["samples"]
        pending = [s for s in samples if s.get("pending_parent")]
        self.assertEqual(len(pending), 1)
        self.assertIn("本地无克隆", pending[0]["pending_parent"])

    def test_zip_form_opens(self):
        zipped = self.tmp / "dump.zip"
        with zipfile.ZipFile(zipped, "w") as zf:
            zf.write(self.db, "cvefixes.sqlite")
        out = self.tmp / "samples.json"
        rc, data, _, _ = test_scripts.run(SCRIPTS["cve-corpus.py"],
                                          "--db", zipped, "--lang", "python",
                                          "--limit", "10", "--out", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        self.assertEqual(data["samples"], 2)

    def test_zip_rejects_path_member(self):
        zipped = self.tmp / "evil.zip"
        with zipfile.ZipFile(zipped, "w") as zf:
            zf.write(self.db, "../evil.sqlite")
        rc, data, _, _ = test_scripts.run(SCRIPTS["cve-corpus.py"],
                                          "--db", zipped, "--lang", "python",
                                          "--limit", "10",
                                          "--out", self.tmp / "s.json")
        self.assertEqual(rc, 2)
        self.assertIn("无合法", data.get("error", ""))


class TestDumpScan(unittest.TestCase):
    """CVEfixes SQL dump 流式扫描器：三表关联提取。"""

    def setUp(self):
        self.tmp = tmpspace.create(prefix="dump-scan-")
        self.addCleanup(tmpspace.release, self.tmp)

    def _make_dump(self, path):
        import gzip
        import io
        sha_a = "a" * 40
        sha_b = "b" * 40
        sha_c = "c" * 40
        lines = [
            "PRAGMA foreign_keys=OFF;",
            "BEGIN TRANSACTION;",
            "CREATE TABLE IF NOT EXISTS `fixes` (\n\"cve_id\" TEXT,\n"
            "\"hash\" TEXT,\n\"repo_url\" TEXT\n);",
            "INSERT INTO fixes VALUES('CVE-2024-0001','" + sha_a + "','x');",
            "CREATE TABLE IF NOT EXISTS `commits` (\n\"hash\" TEXT,\n"
            "\"repo_url\" TEXT\n);",
            "INSERT INTO commits VALUES('" + sha_a + "','x');",
            "INSERT INTO commits VALUES('" + sha_b + "','x');",
            "CREATE TABLE IF NOT EXISTS `file_change` (\n\"id\" TEXT,\n"
            "\"commit_hash\" TEXT,\n\"old_file\" TEXT,\n\"new_file\" TEXT\n);",
            "INSERT INTO file_change VALUES('1','" + sha_a
            + "','src/old.py','src/util.py','ModificationType.MODIFY',"
              "replace('@@ x'));",
            "INSERT INTO file_change VALUES('2','" + sha_b
            + "','a.js','b.js','ModificationType.MODIFY',replace('@@ x'));",
            "INSERT INTO file_change VALUES('3','" + sha_c
            + "','s.py','t.py','ModificationType.MODIFY',replace('@@ y'));",
            "COMMIT;",
        ]
        raw = "\n".join(lines).encode("utf-8")
        gz_buf = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buf, mode="wb") as g:
            g.write(raw)
        zf_path = Path(path)
        with zipfile.ZipFile(zf_path, "w") as zf:
            zf.writestr("CVEfixes_v1.0.8/Data/CVEfixes_v1.0.8.sql.gz",
                        gz_buf.getvalue())
        return zf_path, {"a": sha_a, "b": sha_b, "c": sha_c}

    def test_scan_extracts_python_commits(self):
        dump, shas = self._make_dump(self.tmp / "dump.zip")
        out = self.tmp / "samples.json"
        rc, data, _, _ = test_scripts.run(SCRIPTS["cve-dump-scan.py"],
                                          "--dump-zip", dump, "--lang",
                                          "python", "--limit", "10",
                                          "--out", out)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:300])
        samples = json.loads(out.read_text(encoding="utf-8"))["samples"]
        by_sha = {s["fix_commit"]: s for s in samples}
        self.assertIn(shas["a"], by_sha, "Python 修复提交必须被提取")
        self.assertEqual(by_sha[shas["a"]]["files"], ["src/util.py"])
        self.assertEqual(by_sha[shas["a"]]["cve_ids"], ["CVE-2024-0001"])
        self.assertNotIn(shas["b"], by_sha, ".js 文件不应混入 Python 语料")
        self.assertNotIn(shas["c"], by_sha, "无 repo 关联的提交应被丢弃")


def setUpModule():
    test_scripts.ensure_fixture()


if __name__ == "__main__":
    unittest.main()
