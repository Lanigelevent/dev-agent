#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_agent.py — Phase 2B：编码循环 v1（repo_map/edit_formats/code-task）。

code-task 以宿主协议运行：stub 宿主填 llm-tasks 响应后 --resume，
断言 worktree 编辑、仓库测试由 fail 转 pass、产出标准 a/ b/ 补丁。
agent 层脚本运行于项目 .venv Python（tree-sitter 依赖）。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _scripts_common as test_scripts
import tmpspace

ROOT = Path(__file__).resolve().parents[1]
# CI（Linux）没有 .venv：回落到当前解释器，避免 FileNotFoundError 把整套
# agent 测试判成环境失败；依赖由 workflow 安装（2026-10-28 CI 硬化）。
VENV_PY = next(
    (p for p in (ROOT / ".venv" / "Scripts" / "python.exe",
                 ROOT / ".venv" / "bin" / "python") if p.is_file()),
    Path(sys.executable))
AGENT = ROOT / "agent"


def venv_run(script, *args, timeout=180):
    """以项目 .venv 解释器运行 agent 层脚本（tree-sitter 依赖）。"""
    cmd = [str(VENV_PY), str(script)] + [str(a) for a in args]
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    try:
        return p.returncode, json.loads(p.stdout), p.stdout, p.stderr
    except ValueError:
        return p.returncode, None, p.stdout, p.stderr


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def load_agent_script(name):
    """以模块形式加载 agent/ 下的脚本（code-task 等不是 package 模块）。"""
    import importlib.util
    mod_name = "agent_under_test_" + name.replace(".py", "").replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, AGENT / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _submodule(name):
    """拆分后（round-86 P1-3）：tests 需要直接 patch 子模块全局时用。

    tests 以 tests/ 为顶层目录运行，仓库根不在 sys.path，这里显式补入。
    """
    import importlib
    import sys
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("agent.code_task." + name)


class TestRepoMapAndEdits(unittest.TestCase):
    """地图与编辑格式的单元契约。"""

    def test_search_is_bounded_and_redacts_secrets(self):
        """仓库搜索：字面子串、glob、剪运行产物目录、命中行脱敏。"""
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="agent-search-")
        self.addCleanup(tmpspace.release, tmp)
        tmp = Path(tmp)
        (tmp / "pkg").mkdir()
        (tmp / "pkg" / "core.py").write_text(
            "def parse_toml():\n    return 1\n\n\n"
            "TOKEN = 'api_key=super-secret-value'\n",  # secret-scan: allow
            encoding="utf-8", newline="\n")
        (tmp / "pkg" / "other.py").write_text(
            "from core import parse_toml\n", encoding="utf-8", newline="\n")
        (tmp / ".git").mkdir()
        (tmp / ".git" / "hooks.py").write_text(
            "parse_toml in git metadata\n", encoding="utf-8", newline="\n")
        ok, obs = mod._search_repo(tmp, "parse_toml")
        self.assertTrue(ok)
        self.assertIn("pkg/core.py:1:", obs)
        self.assertIn("pkg/other.py:1:", obs)
        self.assertNotIn(".git/hooks.py", obs, "运行产物目录必须剪掉")
        ok, obs = mod._search_repo(tmp, "parse_toml", glob="*.py")
        self.assertEqual(obs.count("pkg/core.py:1:"), 1)
        ok, obs = mod._search_repo(tmp, "api_key=super-secret-value")  # secret-scan: allow
        self.assertNotIn("super-secret-value", obs,
                         "密钥形态必须脱敏（命中行与回显的查询都不得带明文）")
        self.assertIn("<redacted>", obs)
        (tmp / "pkg" / "shapes.py").write_text(
            "K = 'AKIAABCDEFGHIJKLMNOP'\n"  # secret-scan: allow
            "J = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".dGhpcy1pcy1hLXNpZ25hdHVyZQ'\n",
            encoding="utf-8", newline="\n")
        ok, obs = mod._search_repo(tmp, "AKIAABCDEFGHIJKLMNOP")  # secret-scan: allow
        self.assertNotIn("AKIAABCDEFGHIJKLMNOP", obs, "云凭据形态必须脱敏")  # secret-scan: allow
        jwt = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
               ".dGhpcy1pcy1hLXNpZ25hdHVyZQ")
        ok, obs = mod._search_repo(tmp, jwt)
        self.assertNotIn(jwt, obs, "JWT 形态必须脱敏")
        ok, obs = mod._search_repo(tmp, "a")
        self.assertFalse(ok, "过短 query 必须拒绝（避免全仓噪声）")

    def test_repo_map_ranks_by_refs(self):
        tmp = tmpspace.create(prefix="repo-map-")
        self.addCleanup(tmpspace.release, tmp)
        (tmp / "core.py").write_text(
            "def core_fn(x):\n    return x\n\n\ndef lonely():\n"
            "    return 1\n", encoding="utf-8", newline="\n")
        (tmp / "app.py").write_text(
            "from core import core_fn\n\n\ndef main():\n"
            "    return core_fn(1) + core_fn(2)\n",
            encoding="utf-8", newline="\n")
        rc, data, _, _ = venv_run(AGENT / "repo_map.py", "--repo", tmp)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(data["symbols"], 3)
        top = data["repo_map"]["ranked_symbols"][0]
        self.assertEqual(top["name"], "core_fn", "被引用最多的符号应排首位")
        self.assertGreaterEqual(top["total_refs"], 3)

    def test_repo_map_not_skipped_by_ancestor_dir_name(self):
        """仓库位于 reports/runs 等同名祖先目录下时，地图不得整仓静默为空。"""
        tmp = tmpspace.create(prefix="repo-map-anc-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "reports" / "proj"
        repo.mkdir(parents=True)
        (repo / "core.py").write_text(
            "def f():\n    return 1\n", encoding="utf-8", newline="\n")
        rc, data, _, _ = venv_run(AGENT / "repo_map.py", "--repo", repo)
        self.assertEqual(rc, 0)
        self.assertEqual(data["symbols"], 1,
                         "祖先目录名不得触发 SKIP_DIRS（round-58 实踩）")
        mod = load_agent_script("repo_map.py")
        built = mod.build_map(str(repo))
        self.assertEqual(built["scanned"], 1)
        cands = mod.rank_candidates(built, mod.extract_keywords("core 函数"))
        self.assertTrue(cands, "关键词候选同样不得因祖先目录名被清空")

    def test_edit_format_unique_match_only(self):
        from agent.edit_formats import apply_edits, parse_blocks
        tmp = tmpspace.create(prefix="edit-fmt-")
        self.addCleanup(tmpspace.release, tmp)
        (tmp / "a.py").write_text("def add(a, b):\n    return a - b\n",
                                  encoding="utf-8", newline="\n")
        blocks = parse_blocks(
            "a.py\n<<<<<<< SEARCH\n    return a - b\n=======\n"
            "    return a + b\n>>>>>>> REPLACE\n")
        result = apply_edits(tmp, blocks)
        self.assertEqual(result["errors"], [])
        self.assertIn("a + b", (tmp / "a.py").read_text(encoding="utf-8"))
        # 非唯一命中必须拒绝
        (tmp / "b.py").write_text("x = 1\nx = 1\n", encoding="utf-8",
                                  newline="\n")
        blocks = parse_blocks(
            "b.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n")
        result = apply_edits(tmp, blocks)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("命中 2 处", result["errors"][0]["error"])

    def test_edit_format_create_new_file(self):
        """空 SEARCH + 目标不存在 = 新建文件；已存在文件时空 SEARCH 必须拒绝。"""
        from agent.edit_formats import apply_edits, parse_blocks
        tmp = tmpspace.create(prefix="edit-new-")
        self.addCleanup(tmpspace.release, tmp)
        blocks = parse_blocks(
            "pkg/new_mod.py\n<<<<<<< SEARCH\n=======\n"
            "def f():\n    return 1\n>>>>>>> REPLACE\n")
        result = apply_edits(tmp, blocks)
        self.assertEqual(result["errors"], [])
        self.assertEqual(
            (tmp / "pkg" / "new_mod.py").read_text(encoding="utf-8"),
            "def f():\n    return 1\n")
        (tmp / "exists.py").write_text("x = 1\n", encoding="utf-8",
                                       newline="\n")
        blocks = parse_blocks(
            "exists.py\n<<<<<<< SEARCH\n=======\ny = 2\n>>>>>>> REPLACE\n")
        result = apply_edits(tmp, blocks)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("SEARCH 为空", result["errors"][0]["error"])
        self.assertEqual((tmp / "exists.py").read_text(encoding="utf-8"),
                         "x = 1\n")


class TestTaskStateCost(unittest.TestCase):
    """成本字段跨 --resume 累加：续跑不得把已有计时清零。"""

    def test_elapsed_sec_accumulates_and_persists(self):
        mod = load_agent_script("code-task.py")
        tmp = Path(tmpspace.create(prefix="task-state-cost-"))
        self.addCleanup(tmpspace.release, tmp)
        st = mod.TaskState(tmp)
        st.begin_session()
        st.data["elapsed_sec"] = 5.0  # 模拟前一进程已累计
        self.assertGreaterEqual(st.elapsed_now(), 5.0)
        st.save()
        meta = json.loads((tmp / "task-meta.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(meta["elapsed_sec"], 5.0)
        first = meta["elapsed_sec"]
        # 第二进程续跑：load 后继续累加，不回落
        st2 = mod.TaskState(tmp).load()
        st2.begin_session()
        st2.save()
        self.assertGreaterEqual(st2.data["elapsed_sec"], first)


class TestCodeTaskLoop(unittest.TestCase):
    """编码循环：宿主协议暂停→stub 填答→续跑→测试由红转绿→补丁产出。"""

    def test_fix_task_end_to_end(self):
        tmp = tmpspace.create(prefix="code-task-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_bug.py").write_text(
            "from bug import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "修复 bug.py 使 tests 通过",
               "--out", str(out)]
        # 第一轮：等待宿主
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        # round-72 结构改造：PENDING 指针文件逐跳覆写，且指向本次 prompt/response
        pending_ptr = Path(data["pending_ptr"])
        self.assertTrue(pending_ptr.is_file(), "PENDING 指针必须落盘")
        ptr_text = pending_ptr.read_text(encoding="utf-8")
        self.assertIn(data["llm_task"], ptr_text)
        self.assertIn(data["llm_response"], ptr_text)
        prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
        self.assertIn("仓库符号地图", prompt)
        self.assertIn("add", prompt)
        # stub 宿主：给出唯一命中修复
        response = {"action": "edit",
                    "edits": [{"path": "bug.py",
                               "search": "    return a - b",
                               "replace": "    return a + b"}],
                    "summary": "减号应为加号"}
        Path(data["llm_response"]).write_text(
            json.dumps(response, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        # 续跑：测试应转 pass 并收束
        p2 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0,
                         json.dumps(data2, ensure_ascii=False)[:400])
        self.assertEqual(data2["state"], "DONE")
        self.assertEqual(data2["tests"], "pass")
        patch = Path(data2["patch"])
        self.assertTrue(patch.is_file(), "必须产出补丁")
        text = patch.read_text(encoding="utf-8")
        self.assertIn("+    return a + b", text)
        self.assertIn("a/bug.py", text)
        manifest = json.loads((out / "task-manifest.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["engine"], "agent")
        self.assertEqual(manifest["tests"], "pass")
        self.assertGreaterEqual(manifest.get("elapsed_sec", -1), 0,
                                "成本字段：编码墙钟必须进 manifest（round-48）")
        # 被审仓库未被直接写入（治理红线：产物只落任务目录）
        self.assertIn("return a - b",
                      (repo / "bug.py").read_text(encoding="utf-8"))

    def test_new_file_edit_lands_in_patch(self):
        """新建文件的编辑必须进补丁（round-46 实踩的 file_missing）。

        背景：补丁由 `git diff HEAD` 收，未跟踪文件天然不在 diff 里，
        新建的模块会被即时校验判成「没改」，正确补丁被退回。修法是
        出补丁前 `git add -A -N`（intent-to-add）。
        """
        tmp = tmpspace.create(prefix="code-task-newfile-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("demo\n", encoding="utf-8",
                                        newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_helper.py").write_text(
            "from helper import add\n\n\ndef test_add():\n"
            "    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "新增 helper.py",
               "--out", str(out)]
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        response = {"action": "edit",
                    "edits": [{"path": "helper.py", "search": "",
                               "replace": "def add(a, b):\n    return a + b\n"}],
                    "summary": "create helper module"}
        Path(data["llm_response"]).write_text(
            json.dumps(response, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        p2 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0,
                         json.dumps(data2, ensure_ascii=False)[:400])
        self.assertEqual(data2["state"], "DONE")
        patch = Path(data2["patch"])
        self.assertTrue(patch.is_file(), "新建文件也必须产出补丁")
        text = patch.read_text(encoding="utf-8")
        self.assertIn("+++ b/helper.py", text)
        self.assertIn("+def add(a, b):", text)
        self.assertFalse((repo / "helper.py").exists(),
                         "被审仓库不得被直接写入")


class TestCodeTaskPatchHygiene(unittest.TestCase):
    """补丁产物必须是纯净 unified diff：不得混入 git stderr。

    背景（round-18 实踩）：code-task.py 早期把 git 的 stdout 与 stderr 拼在一起
    收补丁，`core.autocrlf` 的 CRLF 警告（走 stderr）因此被写进 edits.patch 末行。
    实测 `git apply` 容忍尾部噪声（非功能性阻断），但补丁不再是合法 diff 产物，
    严格消费者（patch -p1 / git am / 评审器）会判损坏。
    """

    def _make_repo(self, tmp):
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_bug.py").write_text(
            "from bug import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["config", "core.autocrlf", "true"],
                     ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t",
                                    "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    def test_patch_excludes_git_stderr(self):
        tmp = tmpspace.create(prefix="code-task-stderr-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._make_repo(tmp)

        # 前置条件（反向验证的锚）：本仓库设置 core.autocrlf=true 后，
        # git diff 的 CRLF 警告确实走 stderr——污染源真实存在，非构造性假设。
        (repo / "bug.py").write_text("def add(a, b):\n    return a + b\n",
                                     encoding="utf-8", newline="\n")
        probe = subprocess.run(["git", "-C", str(repo), "diff", "HEAD"],
                               shell=False, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
        self.assertIn("warning:", probe.stderr,
                      "前置条件：应能复现 git 的 CRLF 警告（stderr 污染源）")
        self.assertNotIn("warning:", probe.stdout,
                         "前置条件：警告不应出现在 stdout")
        # 反向验证：旧实现（stdout+stderr 拼接）确实会产出被污染的补丁
        self.assertIn("warning:", probe.stdout + probe.stderr,
                      "反向验证：旧拼接口径必然把警告写进补丁")
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")

        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "修复 bug.py 使 tests 通过",
               "--out", str(out)]
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        Path(data["llm_response"]).write_text(
            json.dumps({"action": "edit",
                        "edits": [{"path": "bug.py",
                                   "search": "    return a - b",
                                   "replace": "    return a + b"}],
                        "summary": "减号应为加号"}),
            encoding="utf-8", newline="\n")
        p2 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0,
                         json.dumps(data2, ensure_ascii=False)[:400])
        patch = Path(data2["patch"])
        self.assertTrue(patch.is_file(), "必须产出补丁")
        text = patch.read_text(encoding="utf-8")
        self.assertNotIn("warning:", text, "补丁不得混入 git stderr 噪声")
        self.assertIn("+    return a + b", text)

        # 补丁必须是可应用的合法 diff：在 HEAD 的干净副本上 git apply --check
        clone = tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(repo), str(clone)],
                       shell=False, capture_output=True)
        applied = subprocess.run(["git", "-C", str(clone), "apply", "--check",
                                  "-"], shell=False, capture_output=True,
                                 input=text.encode("utf-8"))
        self.assertEqual(applied.returncode, 0,
                         "补丁必须能被 git apply 应用: %s"
                         % applied.stderr.decode("utf-8", "replace")[:200])


class TestRepoMapCandidates(unittest.TestCase):
    """关键词候选文件与按窗取上下文（round-19：材料看不见目标文件/截断）。"""

    def _repo(self, tmp):
        """合成仓：目标符号定义在深处的文件里，另有「只提及」的文件。"""
        repo = tmp / "repo"
        (repo / "pkg" / "deep").mkdir(parents=True)
        (repo / "pkg" / "deep" / "ops.py").write_text(
            '"""Operations module."""\n\n\nclass RenameModel:\n'
            '    """Rename a model."""\n\n'
            '    def database_forwards(self, app_label, schema_editor):\n'
            '        """Apply the rename."""\n'
            '        old_model = schema_editor\n'
            '        return old_model\n',
            encoding="utf-8", newline="\n")
        (repo / "pkg" / "mentions.py").write_text(
            "# 这里只是提到 RenameModel 与 db_table，不定义它们\n"
            "x = 1\n",
            encoding="utf-8", newline="\n")
        (repo / "pkg" / "unrelated.py").write_text(
            "def totally_other():\n    return 0\n", encoding="utf-8",
            newline="\n")
        return repo

    def test_keywords_from_issue_text(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        issue = ("RenameModel with db_table should be a noop. "
                 "See `db_table` and `RenameModel.database_forwards`.")
        kws = mod.extract_keywords(issue)
        self.assertIn("RenameModel", kws)
        self.assertIn("db_table", kws)
        self.assertIn("database_forwards", kws)

    def test_definition_file_outranks_mention_file(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td))
            kws = mod.extract_keywords("RenameModel with db_table is a noop")
            cands = mod.scan_candidates(repo, kws)
            files = [c["file"] for c in cands]
            self.assertIn("pkg/deep/ops.py", files, "定义目标符号的文件必须入选")
            # 反向验证：只提及的文件不得排在定义文件之前
            if "pkg/mentions.py" in files:
                self.assertLess(files.index("pkg/deep/ops.py"),
                                files.index("pkg/mentions.py"),
                                "定义信号必须压过 mere 提及")
            self.assertNotIn("pkg/unrelated.py", files,
                             "无关文件不得进候选")

    def test_no_keyword_no_candidate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            repo = self._repo(Path(td))
            cands = mod.scan_candidates(repo, ["zzzz_unrelated_token"])
            self.assertEqual(cands, [], "无命中时不得硬凑候选")

    def test_extract_window_centers_on_keyword(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 目标符号在文件深处：文件头 3000 字窗口看不到它
        filler = "\n".join("# filler line %d" % i for i in range(400))
        text = '"""Module docstring here."""\n%s\nclass Target:\n    def go(self):\n        return 1\n' % filler
        window = mod.extract_window(text, ["Target"], max_chars=3000,
                                    context=20)
        self.assertIn("class Target", window, "窗口必须命中目标符号")
        self.assertIn("Module docstring here", window, "窗口应带模块 docstring")
        head = text[:3000]
        self.assertNotIn("class Target", head,
                         "前提：文件头窗口本来看不到目标（反证有效）")

    def test_extract_window_prefers_definition_over_mention(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # 「Target」先在别处被提及（注释），真正的类定义在后面
        lines = ["# Target 在这里只是被提及"] + \
                ["# filler %d" % i for i in range(200)] + \
                ["class Target:", "    def go(self):", "        return 1"]
        text = "\n".join(lines) + "\n"
        window = mod.extract_window(text, ["Target"], max_chars=3000,
                                    context=10)
        self.assertIn("class Target:", window,
                      "窗口应落在定义处而不是首次提及处")
        self.assertIn("def go(self)", window, "目标类体必须在窗口内")

    def test_extract_window_fallback_without_match(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = "a = 1\nb = 2\n"
        self.assertTrue(mod.extract_window(text, ["zzz_absent"],
                                           max_chars=100).startswith("a = 1"))

    def test_slice_lines_numbered_and_clamped(self):
        """round-69 结构改造：行区间取窗，逐行带 1 基行号、越界钳制、超限截断。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = "\n".join("line %d" % i for i in range(1, 31)) + "\n"
        out = mod.slice_lines(text, 20, 25)
        self.assertIn("   20| line 20", out)
        self.assertIn("   25| line 25", out)
        self.assertNotIn("line 19", out)
        self.assertNotIn("line 26", out)
        # open-ended：start 到 EOF
        out2 = mod.slice_lines(text, 28)
        self.assertIn("   28| line 28", out2)
        self.assertIn("   30| line 30", out2)
        # 非法输入钳制不抛错（start 越界钳到末行；负数钳到首行）
        self.assertIn("   30| line 30", mod.slice_lines(text, 999))
        self.assertIn("line 1", mod.slice_lines(text, -5, 2))
        # 超上限截断并提示续取
        big = "\n".join("x" for _ in range(mod.SPAN_MAX_LINES + 50))
        out3 = mod.slice_lines(big, 1)
        self.assertIn("单段上限", out3)
        self.assertIn("可用 read 路径:%d- 续取" % (mod.SPAN_MAX_LINES + 1), out3)
        self.assertEqual(mod.slice_lines("", 1), "")

    def test_extract_symbol_span_full_body(self):
        """round-69 结构改造：符号锚定取窗——def/class 到同级缩进为止。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        text = (
            "import os\n"
            "\n"
            "class Builder:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "\n"
            "    def prepare(self):\n"
            "        return 'deep'\n"
            "\n"
            "def next_top_level():\n"
            "    return 2\n")
        span = mod.extract_symbol_span(text, "Builder")
        self.assertIn("class Builder:", span)
        self.assertIn("def prepare(self):", span)
        self.assertIn("return 'deep'", span)
        self.assertNotIn("next_top_level", span, "同级后续定义不属于本符号")
        self.assertNotIn("import os", span)
        # 行号 1 基
        self.assertIn("    3| class Builder:", span)
        # 顶层函数
        span2 = mod.extract_symbol_span(text, "next_top_level")
        self.assertIn("return 2", span2)
        self.assertNotIn("class Builder:", span2)
        # 未找到 → 空串（调用方退回关键词取窗）
        self.assertEqual(mod.extract_symbol_span(text, "Absent"), "")


class TestLegacyCompat(unittest.TestCase):
    """老仓库垫片（round-19 结案项：被审仓库 Python 版本约束）。"""

    def _legacy_repo(self, tmp):
        repo = tmp / "legacy"
        repo.mkdir()
        (repo / "legacy_mod.py").write_text(
            "from collections import Mapping\n\n\n"
            "class M(Mapping):\n"
            "    def __init__(self):\n        self.d = {'a': 1}\n"
            "    def __getitem__(self, k):\n        return self.d[k]\n"
            "    def __iter__(self):\n        return iter(self.d)\n"
            "    def __len__(self):\n        return len(self.d)\n",
            encoding="utf-8", newline="\n")
        return repo

    def test_legacy_import_fails_without_shim(self):
        """反向验证的前提：老式 import 在无垫片时确实失败。"""
        with tempfile.TemporaryDirectory() as td:
            repo = self._legacy_repo(Path(td))
            env = dict(os.environ)
            env["PYTHONPATH"] = str(repo)
            p = subprocess.run([str(VENV_PY), "-c", "import legacy_mod"],
                               shell=False, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env)
            self.assertNotEqual(p.returncode, 0,
                                "前提：无垫片时老式 import 应失败")

    def test_legacy_import_succeeds_with_shim(self):
        with tempfile.TemporaryDirectory() as td:
            repo = self._legacy_repo(Path(td))
            p = subprocess.run(
                [str(VENV_PY), str(AGENT / "legacy_compat.py"),
                 "--repo", str(repo), "--", str(VENV_PY), "-c",
                 "import legacy_mod; print(legacy_mod.M()['a'])"],
                shell=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120)
            self.assertEqual(p.returncode, 0,
                             "垫片注入后老仓库应可导入: %s" % p.stderr[-300:])
            self.assertIn("1", p.stdout)

    def test_param_error_exit_2(self):
        rc, _, _, _ = venv_run(AGENT / "legacy_compat.py", "--repo",
                               "Z:/no/such/repo", "--", "python", "-c", "pass")
        self.assertEqual(rc, 2)


class TestPatchSelfCheck(unittest.TestCase):
    """补丁自检 + 邻近测试上下文（round-20：把「补丁弄坏模块」拦在本地）。"""

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_mod", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_selfcheck_flags_broken_import(self):
        mod = self._mod()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / "good_mod.py").write_text("VALUE = 1\n", encoding="utf-8",
                                              newline="\n")
            wt = tmp / "wt"
            wt.mkdir()
            (wt / "good_mod.py").write_text("VALUE = (\n", encoding="utf-8",
                                            newline="\n")
            broken = mod._patch_selfcheck(repo, wt, ["good_mod.py"],
                                         python=str(VENV_PY))
            self.assertTrue(broken, "导入被补丁破坏时必须报出来")
            self.assertEqual(broken[0][0], "good_mod.py")

    def test_selfcheck_docker_fallback_when_local_baseline_fails(self):
        """本机基线导不进 + 给了任务镜像 → 改到容器做前后对比（不再静默跳过）。

        反向验证锚：把 _patch_selfcheck 里的 docker 回退分支删掉，
        本测试立刻转红（broken 会是空表=静默跳过）。
        """
        mod = self._mod()
        calls = []
        # 本机导入恒失败（模拟编译扩展缺失的老仓库）；
        # 拆分后内部调用走 selfcheck 模块全局，patch 目标随之迁移
        sc = _submodule("selfcheck")
        orig_local = sc._import_probe
        orig_docker = sc._import_probe_docker
        sc._import_probe = lambda *a, **k: (False, "ImportError: no _c_internal")

        def fake_docker(src, module, image, timeout=180):
            calls.append((str(src), module, image))
            # 基线（repo）在容器里能导，补丁后（wt）导不进 → 补丁弄坏了模块
            return (str(src).endswith("repo"), "")

        sc._import_probe_docker = fake_docker
        try:
            from pathlib import Path as _P
            broken = mod._patch_selfcheck(_P("/repo"), _P("/wt"),
                                          ["widgets.py"], docker_image="img:x")
        finally:
            sc._import_probe = orig_local
            sc._import_probe_docker = orig_docker
        self.assertTrue(broken, "容器内基线可导而补丁后不可导，必须报出来")
        self.assertTrue(broken[0][1].startswith("[容器]"),
                        "容器归因要带标记，与本机口径区分")
        self.assertEqual(len(calls), 2, "前后各探一次")
        self.assertTrue(calls[0][0].endswith("repo")
                        and calls[1][0].endswith("wt"))

    def test_selfcheck_ignores_baseline_failure(self):
        """基线就导不进去（环境缺依赖）→ 无法归因，不报。"""
        mod = self._mod()
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            repo = tmp / "repo"
            repo.mkdir()
            (repo / "needs_dep.py").write_text("import totally_missing_dep\n",
                                               encoding="utf-8", newline="\n")
            wt = tmp / "wt"
            wt.mkdir()
            (wt / "needs_dep.py").write_text("import totally_missing_dep\nVALUE=(\n",
                                            encoding="utf-8", newline="\n")
            broken = mod._patch_selfcheck(repo, wt, ["needs_dep.py"],
                                         python=str(VENV_PY))
            self.assertEqual(broken, [], "基线失败不应归因到补丁")

    def test_sibling_tests_context(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "repo_map_mod", AGENT / "repo_map.py")
        rmod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rmod)
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / "pkg" / "tests").mkdir(parents=True)
            (repo / "pkg" / "thing.py").write_text("X = 1\n", encoding="utf-8",
                                                   newline="\n")
            (repo / "pkg" / "tests" / "test_thing.py").write_text(
                "def test_x():\n    assert X == 1\n", encoding="utf-8",
                newline="\n")
            (repo / "pkg" / "tests" / "test_other.py").write_text(
                "def test_y():\n    pass\n", encoding="utf-8", newline="\n")
            ctx = rmod.find_sibling_tests(repo, "pkg/thing.py")
            self.assertIn("test_thing.py", ctx)
            self.assertIn("def test_x", ctx)
            self.assertNotIn("test_other.py", ctx, "不相关的测试不应塞进材料")


class TestCodeTaskDiscoveryAndResume(unittest.TestCase):
    """编码循环的测试探测与续跑幂等（round-18 实踩两项）。"""

    def _repo(self, tmp):
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_bug.py").write_text(
            "from bug import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    def test_discovers_package_level_tests(self):
        """包内布局（pkg/tests/）也必须被发现——sympy/astropy/sklearn 布局。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_mod", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "pkg" / "tests").mkdir(parents=True)
            (tmp / "pkg" / "tests" / "test_x.py").write_text("x = 1\n",
                                                              encoding="utf-8",
                                                              newline="\n")
            found = mod._discover_test_paths(tmp)
            self.assertTrue(found, "包内 tests/ 必须被发现")
            self.assertTrue(any("tests" in str(p) for p in found))
            # 仓库根优先
            (tmp / "tests").mkdir()
            found_root = mod._discover_test_paths(tmp)
            self.assertEqual([p.name for p in found_root], ["tests"])

    def test_resume_after_done_is_idempotent(self):
        """已收束的任务再 --resume：幂等回放，补丁不被改写。"""
        tmp = tmpspace.create(prefix="code-task-idem-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "修复 bug.py",
               "--out", str(out)]
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        Path(data["llm_response"]).write_text(
            json.dumps({"action": "edit",
                        "edits": [{"path": "bug.py",
                                   "search": "    return a - b",
                                   "replace": "    return a + b"}]}),
            encoding="utf-8", newline="\n")
        p2 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(data2["state"], "DONE")
        patch = Path(data2["patch"])
        before = patch.read_text(encoding="utf-8")
        # 再续跑一次：必须幂等（不再进循环、不改写补丁）
        p3 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data3 = json.loads(p3.stdout)
        self.assertEqual(p3.returncode, 0, json.dumps(data3, ensure_ascii=False)[:300])
        self.assertEqual(data3["state"], "DONE")
        self.assertEqual(patch.read_text(encoding="utf-8"), before,
                         "幂等续跑不得改写补丁")


def _host_env():
    """宿主 LLM 协议环境（外部 provider 一律屏蔽，保证离线可复现）。"""
    env = dict(os.environ)
    env["CRA_LLM_PROVIDER"] = "host"
    env.pop("REVIEW_LLM_BASE_URL", None)
    env.pop("REVIEW_LLM_MODEL", None)
    return env


def _mini_repo(tmp):
    """「测试为红」的最小仓库：bug.py 的 add 把加号写成减号。"""
    repo = tmp / "repo"
    repo.mkdir()
    (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                 encoding="utf-8", newline="\n")
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_bug.py").write_text(
        "from bug import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8", newline="\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t",
                  "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                       capture_output=True)
    return repo


def _load(script, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSearchActionTrace(unittest.TestCase):
    """search 动作的输入回显不得把凭据带进 trace 与后续材料（硬约束 5）。"""

    def _run(self, cmd, env):
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           env=env)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = {"raw": p.stdout[:400], "stderr": p.stderr[-400:]}
        return p, data

    def test_query_redacted_in_trace_and_material(self):
        tmp = tmpspace.create(prefix="agent-search-trace-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "找 api_key 的引用点", "--out", str(out),
                "--rounds", "2"]
        _p, data = self._run(base, env)
        self.assertEqual(data.get("state"), "WAIT_HOST_LLM", str(data)[:300])
        Path(data["llm_response"]).write_text(json.dumps(
            {"action": "search", "query": "api_key=super-secret-value",  # secret-scan: allow
             "glob": "*.py"}, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        _p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(d2.get("state"), "WAIT_HOST_LLM", str(d2)[:300])
        trace = (out / "traces" / "task.jsonl").read_text(
            encoding="utf-8", errors="replace")
        self.assertNotIn("super-secret-value", trace,
                         "trace 不得记录明文凭据（硬约束 5）")
        self.assertIn("<redacted>", trace)
        prompt = Path(d2["llm_task"]).read_text(encoding="utf-8")
        self.assertNotIn("super-secret-value", prompt,
                         "下一轮材料不得带明文凭据")


class TestPatchInstantValidation(unittest.TestCase):
    """补丁即时校验闸（round-28 检查单第 7/9 项）。

    动机（v1.28.0 实踩）：模型把 SEARCH 写成**上一版补丁**的代码 → 编辑没命中
    → 补丁为空，但任务照常收束，下游收集器静默回退评上一版补丁，全程无报错。
    现在编辑轮内先校验、把根因写进材料让模型当轮重做；收束仍拿不出补丁就是
    NO_PATCH（退出码 1、不写 manifest）——没有可交付物时不伪装成功。
    """

    def _run(self, cmd, env):
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           env=env)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = {"raw": p.stdout[:400], "stderr": p.stderr[-400:]}
        return p, data

    def _fill(self, path, payload):
        Path(path).write_text(json.dumps(payload, ensure_ascii=False),
                              encoding="utf-8", newline="\n")

    def test_empty_edit_reworked_then_delivers(self):
        """空编辑（SEARCH==REPLACE）必须打回重做，且打回材料里写清根因。"""
        tmp = tmpspace.create(prefix="patch-gate-rework-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "修复 bug.py 使 tests 通过", "--out", str(out)]
        p, data = self._run(base, env)
        self.assertEqual(data.get("state"), "WAIT_HOST_LLM", str(data)[:300])
        self._fill(data["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    return a - b"}]})
        p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(p2.returncode, 1, json.dumps(d2, ensure_ascii=False)[:400])
        self.assertEqual(d2.get("state"), "WAIT_HOST_LLM",
                         "补丁为空不得当成一次正常编辑收束，必须打回")
        prompt = Path(d2["llm_task"]).read_text(encoding="utf-8")
        self.assertIn("补丁即时校验未过[empty_patch]", prompt,
                      "打回时必须把根因写进材料，否则模型只会重复同一个错误")
        self.assertIn("请先 read 当前文件的真实内容", prompt)
        # 第二轮给出真正的修复 → 正常收束
        self._fill(d2["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    return a + b"}]})
        p3, d3 = self._run(base + ["--resume"], env)
        self.assertEqual(p3.returncode, 0, json.dumps(d3, ensure_ascii=False)[:400])
        self.assertEqual(d3.get("state"), "DONE")
        self.assertEqual(d3.get("tests"), "pass")
        self.assertTrue(d3["patch_validation"]["ok"], "干净补丁不该带告警")
        self.assertTrue(Path(d3["patch"]).is_file())

    def test_observer_leaves_no_bytecode_in_reviewed_trees(self):
        """自检/测试子进程不得往被观察的树里落 __pycache__。

        本轮实踩（打回重做后拿不到 DONE）：补丁改的是**等长的一行**
        （`return a - b` → `return a + b`）且与自检导入落在同一秒内，旧 .pyc
        的 (mtime 秒, size) 校验照样通过 → pytest 导入到修复**前**的字节码 →
        循环把一次正常修复判成「测试还是红的」，白烧一轮。观察别人代码的
        进程不该在别人的树里留下代码。
        """
        tmp = tmpspace.create(prefix="patch-gate-pyc-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "修复 bug.py 使 tests 通过", "--out", str(out)]
        _p, data = self._run(base, env)
        self._fill(data["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    return a + b"}]})
        p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(d2.get("state"), "DONE",
                         json.dumps(d2, ensure_ascii=False)[:400])
        self.assertEqual(d2.get("tests"), "pass")
        self.assertFalse((repo / "__pycache__").exists(),
                         "基线仓被自检导入过，也不得留下字节码缓存")
        # 机制本身钉住（三处子进程共用同一份环境构造）
        mod = _load(AGENT / "code-task.py", "code_task_nb")
        sub_env = mod._no_bytecode_env("X")
        self.assertEqual(sub_env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertTrue(sub_env["PYTHONPATH"].startswith("X"),
                        "被观察的树要排在导入路径最前")

    def test_no_patch_is_terminal_state(self):
        """轮数用尽仍无补丁 → NO_PATCH 终态：退出码 1、不写 manifest。"""
        tmp = tmpspace.create(prefix="patch-gate-noop-")
        self.addCleanup(tmpspace.release, tmp)
        repo, env = _mini_repo(tmp), _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "修复 bug.py", "--out", str(tmp / "task"),
                "--rounds", "1"]
        _p, data = self._run(base, env)
        self._fill(data["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    return a - b"}]})
        p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(p2.returncode, 1, json.dumps(d2, ensure_ascii=False)[:400])
        self.assertEqual(d2.get("state"), "NO_PATCH")
        self.assertEqual(d2.get("patch"), "")
        codes = [i["code"] for i in d2["patch_validation"]["issues"]]
        self.assertIn("empty_patch", codes)
        self.assertFalse((tmp / "task" / "task-manifest.json").exists(),
                         "无补丁不得写 manifest（下游据此回评旧补丁）")
        report = (tmp / "task" / "task-report.md").read_text(encoding="utf-8")
        self.assertIn("## 补丁即时校验未过", report)
        # 反向验证锚：同一轮数上限下，真正命中的编辑必须正常交付——
        # 说明闸门不是「一律判死」，只在拿不出补丁时拦
        base_ok = [str(VENV_PY), str(AGENT / "code-task.py"),
                   "--repo", str(repo), "--task", "修复 bug.py",
                   "--out", str(tmp / "task-ok"), "--rounds", "1"]
        _p3, d3 = self._run(base_ok, env)
        self._fill(d3["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    return a + b"}]})
        p4, d4 = self._run(base_ok + ["--resume"], env)
        self.assertEqual(p4.returncode, 0, json.dumps(d4, ensure_ascii=False)[:400])
        self.assertEqual(d4.get("state"), "DONE")
        self.assertTrue((tmp / "task-ok" / "task-manifest.json").is_file())

    def test_non_ascii_patch_warns_but_delivers(self):
        """新增行含非 ASCII：告警随交付走（不打断），但必须留下书面痕迹。

        round-27 实踩的根因链是「中文注释破坏闭合引号 → SyntaxError → 容器
        EVAL_FAILED」，代价整轮评测；本地能标出来就不必等远端。
        """
        tmp = tmpspace.create(prefix="patch-gate-ascii-")
        self.addCleanup(tmpspace.release, tmp)
        repo, env = _mini_repo(tmp), _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "修复 bug.py", "--out", str(tmp / "task"),
                "--rounds", "1"]
        _p, data = self._run(base, env)
        self._fill(data["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "bug.py", "search": "    return a - b",
                               "replace": "    # 修正：减号应为加号\n"
                                          "    return a + b"}]})
        p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(p2.returncode, 0, json.dumps(d2, ensure_ascii=False)[:400])
        self.assertEqual(d2.get("state"), "DONE")
        issues = d2["patch_validation"]["issues"]
        self.assertIn("non_ascii", [i["code"] for i in issues])
        self.assertFalse(d2["patch_validation"]["ok"])
        manifest = json.loads((tmp / "task" / "task-manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertIn("non_ascii",
                      [i["code"] for i in manifest["patch_validation"]["issues"]],
                      "告警必须进 manifest，供收集器与台账追责")
        report = (tmp / "task" / "task-report.md").read_text(encoding="utf-8")
        self.assertIn("补丁即时校验（有告警", report)

    def test_validate_patch_unit_codes(self):
        """四条判据的单元口径 + 反向验证（干净补丁一律不报）。"""
        mod = _load(AGENT / "code-task.py", "code_task_gate")
        patch = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n"
                 "-older = 1\n+newer = 2\n")
        clean = mod._validate_patch(
            patch, [{"path": "x.py", "search": "older = 1",
                     "replace": "newer = 2"}], ["x.py"])
        self.assertTrue(clean["ok"],
                        "反向验证：正常补丁不得触发任何告警，否则闸门只会制造噪声")
        bad = mod._validate_patch(
            patch, [{"path": "y.py", "search": "older = 1",
                     "replace": "brand_new_value = 2"}], ["y.py"])
        self.assertEqual({i["code"] for i in bad["issues"]},
                         {"file_missing", "missing_change"})
        uni = mod._validate_patch(patch + "+中文 = 3\n", [], [])
        self.assertIn("non_ascii", {i["code"] for i in uni["issues"]})
        # 口径纪律：只有 + 行算新增，上下文行与 --- / +++ 头不参与判定
        self.assertEqual(mod._added_lines(patch), ["newer = 2"])

    def test_resume_after_no_patch_replays_verdict(self):
        """NO_PATCH 后再续跑：仍如实回告警，不伪装成 DONE。"""
        tmp = tmpspace.create(prefix="patch-gate-replay-")
        self.addCleanup(tmpspace.release, tmp)
        repo, env = _mini_repo(tmp), _host_env()
        out = tmp / "task"
        base = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                "--task", "修复 bug.py", "--out", str(out), "--rounds", "1"]
        _p, data = self._run(base, env)
        self._fill(data["llm_response"],
                   {"action": "edit",
                    "edits": [{"path": "other.py",
                               "search": "no such line",
                               "replace": "whatever"}]})
        p2, d2 = self._run(base + ["--resume"], env)
        self.assertEqual(d2.get("state"), "NO_PATCH",
                         "SEARCH 没命中 → applied 为空也不得有补丁假象")
        codes = [i["code"] for i in d2["patch_validation"]["issues"]]
        self.assertIn("empty_patch", codes)


class TestBehaviorProbe(unittest.TestCase):
    """行为探针动作（round-28 检查单第 3 项）。

    报错行只给症状，状态类缺陷（顶点表没同步、extent 没更新）要把对象状态
    打出来才看得见。执行模型给的代码属于**扩大权限**，默认关闭，需
    --allow-probe 显式授权；未授权时只做观察说明，绝不落盘执行。
    """

    def _run(self, cmd, env):
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           env=env)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = {"raw": p.stdout[:400], "stderr": p.stderr[-400:]}
        return p, data

    def _base(self, repo, out, extra=()):
        return ([str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
                 "--task", "定位 bug.py 的状态异常", "--out", str(out),
                 "--rounds", "1"] + list(extra))

    def test_probe_denied_without_flag(self):
        tmp = tmpspace.create(prefix="probe-deny-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        p, data = self._run(self._base(repo, out), env)
        prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
        self.assertNotIn('"action":"probe"', prompt,
                         "未授权时动作面里不该出现探针（否则模型会去用）")
        self.assertNotIn("行为探针", prompt)
        Path(data["llm_response"]).write_text(json.dumps(
            {"action": "probe", "code": "print('PROBE_RAN_MUST_NOT_APPEAR')"},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        p2, d2 = self._run(self._base(repo, out) + ["--resume"], env)
        self.assertEqual(p2.returncode, 0, json.dumps(d2, ensure_ascii=False)[:300])
        report = (out / "task-report.md").read_text(encoding="utf-8")
        self.assertIn("probe 动作未授权", report)
        self.assertNotIn("PROBE_RAN_MUST_NOT_APPEAR", report,
                         "未授权探针必须不执行")

    def test_probe_docker_requires_allow_probe(self):
        """--probe-docker 只是执行位置，权限闸仍只有 --allow-probe（缺即退出码 2）。"""
        tmp = tmpspace.create(prefix="probe-docker-gate-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        p, data = self._run(self._base(repo, out, ["--probe-docker", "img:x"]),
                            env)
        self.assertEqual(p.returncode, 2, "--probe-docker 不带 --allow-probe 必须参数错误")
        self.assertFalse(data.get("ok", True))

    def test_probe_docker_argv_and_container_note(self):
        """容器通道：argv 必须是「只读挂载 /testbed + 镜像 python」；材料带容器说明。

        反向验证锚：把 _probe 的 docker 分支摘掉，本测试两例立刻转红。
        """
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location(
            "code_task_docker", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # _material：probe_docker 非空时材料必须带容器说明（模型才知道环境是镜像）；
        # 拆分后内部调用走 materials 模块全局，patch 目标随之迁移
        mt = _submodule("materials")
        orig = (mt.build_map, mt.render_material)
        mt.build_map = lambda repo: {"scanned": 0, "files": [],
                                     "ranked_symbols": []}
        mt.render_material = lambda m, n: ""
        try:
            text = mod._material(".", "t", [], 1000, candidates=[],
                                 allow_probe=True, probe_docker="img:x")
        finally:
            mt.build_map, mt.render_material = orig
        self.assertIn("img:x", text, "材料必须写明探针在哪个镜像里执行")

        # _probe：docker 通道 argv 形状（只读挂载 + 镜像 python -c）
        calls = []

        class _P:
            returncode = 0
            stdout = "obs"
            stderr = ""

        def fake_run(argv, **kw):
            calls.append(argv)
            return _P()

        with mock.patch.object(mod.subprocess, "run", fake_run):
            ok, obs = mod._probe(Path("/nonexistent-wt"), Path("/repo"),
                                 "print(1)", docker_image="img:x")
        self.assertTrue(ok)
        argv = calls[0]
        self.assertEqual(argv[0], "docker")
        self.assertIn("--rm", argv)
        self.assertIn("/agent-wt:ro", " ".join(argv),
                        "工作区必须只读挂载（探针只观测不写宿主侧）")
        self.assertIn("cp -a /agent-wt/. /testbed/", argv[-1],
                        "进容器先合并到 /testbed（保住镜像编译的 C 扩展）")
        self.assertEqual(argv[-4:-1], ["img:x", "bash", "-lc"],
                         "经 bash -lc 激活镜像 conda 环境（实测裸 python 是系统环境）")
        self.assertIn("base64 -d | python -", argv[-1],
                      "探针代码经 base64 走 stdin，避免双重转义")

    def test_probe_docker_state_persists_across_resume(self):
        """--resume 不丢执行位置：probe_docker 持久化进 task-meta.json。"""
        tmp = tmpspace.create(prefix="probe-docker-resume-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        p, data = self._run(self._base(repo, out, ["--allow-probe",
                                                   "--probe-docker", "img:x"]),
                            env)
        self.assertEqual(p.returncode, 1, "首跑应停在 WAIT_HOST_LLM")
        meta = json.loads((out / "task-meta.json").read_text(encoding="utf-8"))
        self.assertEqual(meta.get("probe_docker"), "img:x",
                         "执行位置必须持久化，resume 后不靠 CLI 重传")

    def test_material_carries_probe_first_note(self):
        """「先探针后编辑」建议位（round-34 检查单第 4 条）：授权探针时材料
        必须带该建议，未授权时不得出现（没有 probe 动作就许愿是误导）。
        装配点删掉即转红。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_probe_first", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # materials 子模块内部调用走模块全局，patch 目标随之迁移
        mt = _submodule("materials")
        orig = (mt.build_map, mt.render_material)
        mt.build_map = lambda repo: {"scanned": 0, "files": [],
                                     "ranked_symbols": []}
        mt.render_material = lambda m, n: ""
        try:
            text_on = mod._material(".", "t", [], 1000, candidates=[],
                                    allow_probe=True, probe_docker="")
            text_off = mod._material(".", "t", [], 1000, candidates=[],
                                     allow_probe=False, probe_docker="")
        finally:
            mt.build_map, mt.render_material = orig
        self.assertIn("先探针后编辑", text_on,
                      "授权探针时材料必须带「先探针后编辑」建议位")
        self.assertNotIn("先探针后编辑", text_off,
                         "未授权探针时不得出现该建议（动作面里没有 probe）")

    def test_repair_plan_note_lookup_and_material_injection(self):
        """修复计划蒸馏进材料：命中仓库家族才附带；装配点删掉本测试即转红。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_plan", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        import json as _json
        import tempfile as _tf
        with _tf.TemporaryDirectory() as td:
            plans = Path(td) / "plans.json"
            plans.write_text(_json.dumps({"plans": {"matplotlib": {
                "instances": ["matplotlib__matplotlib-22711"],
                "top_file_prefixes": [["lib/matplotlib/widgets.py", 1]],
                "added_lines_minmax": [4, 20], "rounds_minmax": [2, 4]}}},
                ensure_ascii=False), encoding="utf-8", newline="\n")
            hit = mod._repair_plan_note("C:/x/matplotlib-wt", plans_path=plans)
            self.assertIn("修复计划蒸馏", hit)
            self.assertIn("widgets.py", hit)
            miss = mod._repair_plan_note("C:/x/unknown-repo", plans_path=plans)
            self.assertEqual(miss, "", "未命中家族不许附带（材料预算只给相关计划）")

        # 装配点：_material 必须把计划段放进材料；
        # 拆分后内部调用走 materials 模块全局，patch 目标随之迁移
        mt = _submodule("materials")
        orig = (mt.build_map, mt.render_material, mt._repair_plan_note)
        mt.build_map = lambda repo: {"scanned": 0, "files": [],
                                     "ranked_symbols": []}
        mt.render_material = lambda m, n: ""
        mt._repair_plan_note = lambda repo, **kw: "PLAN_SENTINEL"
        try:
            text = mod._material(".", "t", [], 1000, candidates=[])
        finally:
            (mt.build_map, mt.render_material,
             mt._repair_plan_note) = orig
        self.assertIn("PLAN_SENTINEL", text,
                      "命中家族时计划段必须进材料（装配点被摘则此处转红）")

    def test_probe_runs_and_observation_returns(self):
        tmp = tmpspace.create(prefix="probe-run-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        cmd = self._base(repo, out, ["--allow-probe"])
        p, data = self._run(cmd, env)
        prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
        self.assertIn('"action":"probe"', prompt, "授权后动作面必须下发探针动作")
        self.assertIn("## 行为探针（本任务已授权 probe）", prompt,
                      "材料要给出可直接改写的探针样式，不只说「可以用」")
        Path(data["llm_response"]).write_text(json.dumps(
            {"action": "probe",
             "code": "import bug; print('PROBE_OK', bug.add(1, 2), "
                     "sorted(vars(bug)))"},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        p2, d2 = self._run(cmd + ["--resume"], env)
        self.assertEqual(p2.returncode, 0, json.dumps(d2, ensure_ascii=False)[:300])
        report = (out / "task-report.md").read_text(encoding="utf-8")
        self.assertIn("行为探针（rc=0）", report)
        self.assertIn("PROBE_OK -1", report, "探针输出必须回到观察历史")
        # 反向验证锚：授权态持久化在任务态里，续跑不重算动作面
        # （provider 幂等 id = sha256(system+user)，改了 system 会让同一材料
        #   重新进等待态）
        self.assertTrue(json.loads((out / "task-meta.json")
                                   .read_text(encoding="utf-8"))["allow_probe"])


class TestRepoTopLevelGuard(unittest.TestCase):
    """--repo 必须是仓库顶层：非 git 目录与外层仓子目录都不得开 worktree。

    背景（本轮实踩）：把没 git init 的临时目录当 --repo，`git -C <repo>
    worktree add` 会向上找到祖先仓库，于是 dev-agent **自己的**工作树被挂
    到任务目录下，后台任务在整仓跑测试。这类越界必须参数错退出，不能靠人
    自觉。
    """

    def _run(self, repo, out):
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"), "--repo", str(repo),
               "--task", "修复 bug.py 使 tests 通过", "--out", str(out),
               "--rounds", "1"]
        return subprocess.run(cmd, shell=False, capture_output=True,
                              text=True, encoding="utf-8",
                              errors="replace", timeout=120, env=_host_env())

    def test_non_git_dir_is_param_error(self):
        tmp = tmpspace.create(prefix="code-task-nogit-")
        self.addCleanup(tmpspace.release, tmp)
        plain = tmp / "plain"
        plain.mkdir()
        (plain / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                      encoding="utf-8", newline="\n")
        out = tmp / "task"
        proc = self._run(plain, out)
        self.assertEqual(proc.returncode, 2, proc.stdout[:200])
        data = json.loads(proc.stdout)
        self.assertIn("不是 git 仓库", data.get("error", ""))
        # 反向验证：绝不能因为「向上找到了祖先仓」而挂出 worktree 或产出补丁
        self.assertFalse((out / "wt").exists(), "非仓库不得建 worktree")
        self.assertFalse(list(out.glob("*.patch")), "非仓库不得产出补丁")

    def test_repo_subdir_is_param_error(self):
        tmp = tmpspace.create(prefix="code-task-subdir-")
        self.addCleanup(tmpspace.release, tmp)
        repo = _mini_repo(tmp)
        sub = repo / "tests"
        proc = self._run(sub, tmp / "task-sub")
        self.assertEqual(proc.returncode, 2, proc.stdout[:200])
        self.assertIn("不是仓库顶层", json.loads(proc.stdout).get("error", ""))
        # 反向验证的对照：同一个仓库按顶层传就正常进等待态
        ok = self._run(repo, tmp / "task-root")
        self.assertEqual(ok.returncode, 1, ok.stdout[:200])
        self.assertEqual(json.loads(ok.stdout).get("state"), "WAIT_HOST_LLM")


class TestSiblingTestMapping(unittest.TestCase):
    """模块→邻近测试的三路取法（round-28 检查单第 6 项）。

    边界语义常只写在模块自己的测试里；django 的 tests/<app>/ 布局与模块路径
    不同名，只按文件名命中在这里一律取不到。
    """

    def _repo(self, root):
        ops = root / "django" / "db" / "migrations" / "operations"
        ops.mkdir(parents=True)
        (ops / "base.py").write_text("class Operation:\n    pass\n",
                                     encoding="utf-8", newline="\n")
        (root / "django" / "forms").mkdir(parents=True)
        (root / "django" / "forms" / "formsets.py").write_text(
            "class BaseFormSet:\n    pass\n", encoding="utf-8", newline="\n")
        mig = root / "tests" / "migrations"
        mig.mkdir(parents=True)
        (mig / "test_operations.py").write_text(
            "def test_add_operation():\n    pass\n", encoding="utf-8",
            newline="\n")
        (mig / "test_writer.py").write_text("def test_writer():\n    pass\n",
                                            encoding="utf-8", newline="\n")
        forms = root / "tests" / "forms"
        forms.mkdir(parents=True)
        (forms / "test_thing.py").write_text(
            "from django.forms.formsets import BaseFormSet\n\n\n"
            "def test_thing():\n    pass\n", encoding="utf-8", newline="\n")
        return root

    def test_django_path_segment_mapping(self):
        mod = _load(AGENT / "repo_map.py", "repo_map_map")
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(Path(td))
            ctx = mod.find_sibling_tests(root,
                                         "django/db/migrations/operations/base.py")
            self.assertIn("test_operations.py", ctx,
                          "路径段 migrations ↔ tests/migrations 必须映射上")
            self.assertIn("def test_add_operation", ctx)
            self.assertNotIn("test_writer.py", ctx, "同目录但不相关的测试不该塞")
            self.assertNotIn("test_thing.py", ctx, "别的 app 不该串味")
            # 反向验证锚：目录段映射不上、内容也没提及时不得硬塞测试
            # （同 app 目录下按段名命中是设计行为，见 B 路；这里锚的是「无证据不编」）
            (root / "django" / "core" / "serializers").mkdir(parents=True)
            (root / "django" / "core" / "serializers" / "json.py").write_text(
                "def dump():\n    pass\n", encoding="utf-8", newline="\n")
            self.assertEqual(
                mod.find_sibling_tests(root, "django/core/serializers/json.py"),
                "", "无命中就该返回空，别用噪声填材料")

    def test_content_fallback_labeled(self):
        mod = _load(AGENT / "repo_map.py", "repo_map_map2")
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(Path(td))
            ctx = mod.find_sibling_tests(root, "django/forms/formsets.py")
            self.assertIn("按内容命中", ctx,
                          "内容兜底的来源必须标注，供材料可信度分级")
            self.assertIn("test_thing.py", ctx)

    def test_generic_name_does_not_preempt_path_mapping(self):
        """泛化名的名字命中不得短路目录段映射（round-29 实测出的缺陷）。

        模块名 `base` 太通用：tests/migrations/test_base.py 与
        tests/urlpatterns/test_base.py 都会按文件名命中。旧实现「前一路命中即停」
        就把这两个无关文件当邻近测试交出去，真值 test_operations.py 根本没机会出场。
        """
        mod = _load(AGENT / "repo_map.py", "repo_map_generic")
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(Path(td))
            for app in ("migrations", "urlpatterns"):
                (root / "tests" / app).mkdir(parents=True, exist_ok=True)
                (root / "tests" / app / "test_base.py").write_text(
                    "def test_base():\n    pass\n", encoding="utf-8", newline="\n")
            ctx = mod.find_sibling_tests(root,
                                         "django/db/migrations/operations/base.py")
            self.assertIn("test_operations.py", ctx,
                          "泛化名命中散落两个目录时必须让位给路径段映射")
            self.assertNotIn("test_base.py", ctx, "同名但不同 app 的测试不是邻近测试")

    def test_generic_only_hits_stay_out_of_material(self):
        """只剩泛化名证据时**不入材料**（round-33 真实语料定案：36 出场 0 判真）。

        反向验证锚：把「三路皆空后回头用泛化名候选」那段加回来，本例立刻转红——
        带标注的纯噪声仍占 limit 槽位、仍会被模型读进上下文，不如无材料。
        """
        mod = _load(AGENT / "repo_map.py", "repo_map_marked")
        with tempfile.TemporaryDirectory() as td:
            root = self._repo(Path(td))
            legacy = root / "legacy" / "core"
            legacy.mkdir(parents=True)
            (legacy / "utils.py").write_text("def h():\n    pass\n",
                                             encoding="utf-8", newline="\n")
            (root / "tests" / "util").mkdir(parents=True)
            for rel in ("tests/util/test_utils_math.py", "tests/test_utils_io.py"):
                (root / rel).write_text("def test_x():\n    pass\n",
                                        encoding="utf-8", newline="\n")
            ctx = mod.find_sibling_tests(root, "legacy/core/utils.py")
            self.assertEqual(ctx, "",
                             "泛化名兜底回来就是把纯噪声放回材料（真实语料 36/0）")

    def test_sibling_bench_contract(self):
        """三路命中率的受控实测：数字变了要当场看见，不靠印象说「找到了」。"""
        rc, data, out, err = venv_run(ROOT / "scripts" / "sibling-test-bench.py",
                                      "--verbose")
        self.assertEqual(rc, 0, (out + err)[:400])
        self.assertTrue(data["ok"])
        self.assertEqual(data["corpus"]["cases"], 7)
        # B 路必须真的有出场（round-29 修复前是 0 次）
        self.assertGreaterEqual(data["by_lane"]["B"]["hit"], 1,
                                "路径段映射被泛化名短路就是回归")
        self.assertGreaterEqual(data["recall_mean"], 0.95)
        # round-30 起 C 路只认引用形状：把裸词检索改回去，精度立刻掉回 0.667
        self.assertGreaterEqual(data["precision_mean"], 0.75,
                                "C 路退回裸词命中就是把噪声放回材料")
        by_name = {c["name"]: c for c in data["cases"]}
        self.assertEqual(by_name["C 路误命中：名字只是 fixture 路径"]["returned"], [],
                         "fixture 路径串又被当邻近测试就是回归")
        self.assertEqual(by_name["C 路真命中：跨目录 import"]["truth_hits"],
                         ["tests/test_api.py"],
                         "C 路收窄谓词不许把真引用一起收窄掉")

    def test_content_fallback_requires_reference_not_bare_word(self):
        """C 路只认「引用形状」，裸词命中不得再进材料（round-30 真实仓库实测的结论）。

        旧口径拿 `\b<stem>\b` 在 tests/ 里捞。三仓 300 模块实测（同一条等距样本）：
        C 路 132 条返回里只有 46 条真引用（0.348），噪声最多的形状是「别的模块里的
        同名变量/函数」和「同名不同模块的 import」；更坏的是 `limit` 早停——噪声把
        真引用挤了出去。改成检索点分路径 / `from 包 import 模块` 后，同一批样本
        C 路 76 条返回**全部**是真引用（1.0），真引用数从 46 涨到 76。
        这一例锚负向：模块名只以变量与 fixture 路径出现 → 什么都不给；
        正向对照：同一支测试写上真实引用 → 必须出场且带标注。
        """
        mod = _load(AGENT / "repo_map.py", "repo_map_bareword")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pkg" / "core").mkdir(parents=True)
            (root / "pkg" / "core" / "session.py").write_text(
                "class Session:\n    pass\n", encoding="utf-8", newline="\n")
            tests = root / "tests"
            tests.mkdir()
            noisy = ('FIXTURE = "tests/fixtures/session/note.json"\n\n\n'
                     'def test_load():\n    session = object()\n    assert session\n')
            (tests / "test_config.py").write_text(noisy, encoding="utf-8",
                                                  newline="\n")
            self.assertEqual(mod.find_sibling_tests(root, "pkg/core/session.py"),
                             "", "裸词命中不是引用，不该冒充邻近测试")
            (tests / "test_config.py").write_text(
                "from pkg.core.session import Session\n\n\n"
                "def test_load():\n    assert Session\n", encoding="utf-8",
                newline="\n")
            ctx = mod.find_sibling_tests(root, "pkg/core/session.py")
            self.assertIn("test_config.py", ctx, "真引用被裸词口径的收窄误伤就是回归")
            self.assertIn("按内容命中", ctx)

    def test_package_root_differs_from_repo_root(self):
        """包根在 `lib/` 下时（matplotlib 形），引用形状必须由 `__init__.py` 链推出。

        拿仓库根拼点分会得到 `lib.pkg.engine`，而测试里写的是 `pkg.sub.engine`。
        round-30 首轮真实实测就坏在这里：matplotlib 两路命中率被系统性判成 0，
        形状极像「映射在这类仓库上完全失效」，其实是**量具**坏了。
        """
        mod = _load(AGENT / "repo_map.py", "repo_map_srclayout")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "lib" / "pkg" / "sub"
            pkg.mkdir(parents=True)
            (root / "lib" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "engine.py").write_text("def run():\n    return 1\n",
                                           encoding="utf-8", newline="\n")
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_misc.py").write_text(
                "from pkg.sub.engine import run\n\n\ndef test_run():\n"
                "    assert run()\n", encoding="utf-8", newline="\n")
            self.assertEqual(mod.module_ref(root, "lib/pkg/sub/engine.py"),
                             ("pkg.sub.engine", "pkg.sub", "engine"),
                             "包根在 lib/ 下时点分路径不得带 lib")
            ctx = mod.find_sibling_tests(root, "lib/pkg/sub/engine.py")
            self.assertIn("test_misc.py", ctx, "src/lib 布局下引用命中必须能出场")
            self.assertIn("按内容命中", ctx)

    def test_realbench_judge_and_repo_map_share_one_reference_shape(self):
        """量具与映射各算一遍引用形状，两者必须一致。

        判真的口径和检索的口径如果是**两份实现**，就随时可能悄悄分叉——到那时
        「命中率」量的就不是映射，而是两份代码的差异。这一例是防分叉的钉。
        """
        real = _load(ROOT / "scripts" / "sibling-test-realbench.py", "realbench_judge")
        mod = _load(AGENT / "repo_map.py", "repo_map_refsync")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            deep = root / "src" / "outer" / "inner"
            deep.mkdir(parents=True)
            (root / "src" / "outer" / "__init__.py").write_text("", encoding="utf-8")
            (deep / "__init__.py").write_text("", encoding="utf-8")
            (deep / "widget.py").write_text("X = 1\n", encoding="utf-8", newline="\n")
            (root / "loose.py").write_text("Y = 1\n", encoding="utf-8", newline="\n")
            for rel in ("src/outer/inner/widget.py", "src/outer/__init__.py",
                        "loose.py"):
                self.assertEqual(mod.module_ref(root, rel),
                                 real._module_ref(root, rel),
                                 "%s 在映射与量具里必须是同一个引用形状" % rel)
            self.assertEqual(mod.module_ref(root, "src/outer/inner/widget.py"),
                             ("outer.inner.widget", "outer.inner", "widget"))


class TestSweRun(unittest.TestCase):
    """swe_run.py 四阶段契约（Phase 3B 扩样编排；台账 dcd866f9d912 恢复）。"""

    def _prepare_task(self, tmp):
        task = tmp / "taskdir"
        task.mkdir()
        (task / "Dockerfile").write_text("\n".join([
            "FROM --platform=linux/amd64 ubuntu:jammy",
            "RUN apt update && apt install -y wget",
            "RUN wget 'https://repo.anaconda.com/miniconda/Miniconda3-x.sh' "
            "-O miniconda.sh",
            "RUN conda config --append channels conda-forge",
            "RUN <<EOF_abc123",
            "#!/bin/bash",
            "set -euxo pipefail",
            "source /opt/miniconda3/bin/activate",
            "conda env create -f /root/environment.yml",
            "EOF_abc123",
            "RUN <<EOF_def456",
            "git clone https://github.com/django/django /testbed",
            "EOF_def456",
            "WORKDIR /testbed/",
            ""]) + "\n", encoding="utf-8", newline="\n")
        return task

    def test_prepare_transform_and_rewrites(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            task = self._prepare_task(tmp)
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "prepare",
                                      "--task", "demo__demo-1",
                                      "--task-dir", task)
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertEqual(data["setup_scripts"], ["setup1.sh", "setup2.sh"])
            local = (task / "Dockerfile.local").read_text(encoding="utf-8")
            self.assertNotIn("<<EOF_", local, "heredoc 应被抽走")
            self.assertIn("COPY setup1.sh /tmp/setup1.sh", local)
            self.assertIn('RUN ["/bin/bash", "/tmp/setup1.sh"]', local)
            # setupN.sh 体逐字保留（含块内自带 shebang）
            s1 = (task / "setup1.sh").read_text(encoding="utf-8")
            self.assertIn("source /opt/miniconda3/bin/activate", s1)
            # setup2.sh 无 shebang 块体应补 shebang
            s2 = (task / "setup2.sh").read_text(encoding="utf-8")
            self.assertTrue(s2.startswith("#!/bin/bash"))
            # 国内源改写三项
            self.assertIn("s|//archive.ubuntu.com|//mirror.nju.edu.cn|g", local)
            self.assertIn("mirror.nju.edu.cn/anaconda/miniconda/", local)
            self.assertIn("pypi.tuna.tsinghua.edu.cn/simple", local)

    def test_prepare_bad_task_id_exit_2(self):
        rc, data, _, _ = venv_run(AGENT / "swe_run.py", "prepare",
                                  "--task", "../evil")
        self.assertEqual(rc, 2)

    def test_prepare_task_dir_missing_exit_2(self):
        rc, _, _, _ = venv_run(AGENT / "swe_run.py", "prepare",
                               "--task", "demo__x", "--task-dir", "Z:/no/dir")
        self.assertEqual(rc, 2)

    def test_build_dry_run_and_docker_gate(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            task = self._prepare_task(tmp)
            venv_run(AGENT / "swe_run.py", "prepare", "--task", "demo__x",
                     "--task-dir", task)
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "build",
                                      "--task-dir", task, "--image",
                                      "swebench/sweb.eval.x86_64.demo:latest",
                                      "--dry-run")
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertIn("build", data["cmd"])
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "build",
                                      "--task-dir", task, "--image", "x:y",
                                      "--docker", "Z:/no/docker.exe")
            self.assertEqual(rc, 1)
            self.assertEqual(data["state"], "DOCKER_UNAVAILABLE")

    def test_eval_pred_validation_and_gates(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bad = tmp / "bad.jsonl"
            bad.write_text(json.dumps({"instance_id": "demo__x"}),
                           encoding="utf-8", newline="\n")
            rc, _, _, _ = venv_run(AGENT / "swe_run.py", "eval",
                                   "--predictions", bad, "--run-id", "r1",
                                   "--venv-python", sys.executable)
            self.assertEqual(rc, 2, "缺 model_name_or_path 应判参数错误")
            good = tmp / "good.jsonl"
            good.write_text(json.dumps({
                "instance_id": "demo__x", "model_name_or_path": "m",
                "model_patch": "x"}) + "\n", encoding="utf-8", newline="\n")
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "eval",
                                      "--predictions", good, "--run-id", "r1",
                                      "--venv-python", sys.executable,
                                      "--dry-run")
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertEqual(data["env"]["HF_ENDPOINT"],
                             "https://hf-mirror.com")
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "eval",
                                      "--predictions", good, "--run-id", "r1",
                                      "--venv-python", sys.executable,
                                      "--docker", "Z:/no/docker.exe")
            self.assertEqual(rc, 1)
            self.assertEqual(data["state"], "DOCKER_UNAVAILABLE")

    def test_report_parse_and_model_ambiguity(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            run = tmp / "logs/run_evaluation/r9/m1/django__demo-1"
            run.mkdir(parents=True)
            report = {"demo__a": {"resolved": True,
                                  "patch_successfully_applied": True,
                                  "infra_failure": False,
                                  "tests_status": {
                                      "FAIL_TO_PASS": {"success": ["t1"],
                                                       "failure": []},
                                      "PASS_TO_PASS": {"success": ["p1", "p2"],
                                                       "failure": ["p3"]}}},
                      "demo__b": {"resolved": False,
                                  "patch_successfully_applied": False,
                                  "infra_failure": True,
                                  "tests_status": {
                                      "FAIL_TO_PASS": {"success": [],
                                                       "failure": ["t2"]},
                                      "PASS_TO_PASS": {"success": [],
                                                       "failure": []}}}}
            (run / "report.json").write_text(
                json.dumps(report), encoding="utf-8", newline="\n")
            rc, data, _, _ = venv_run(AGENT / "swe_run.py", "report",
                                      "--run-id", "r9",
                                      "--logs-root",
                                      tmp / "logs/run_evaluation")
            self.assertEqual(rc, 0, str(data)[:300])
            self.assertEqual(data["resolved_count"], 1)
            self.assertEqual(data["total"], 2)
            a = data["instances"][0]
            self.assertEqual(a["fail_to_pass"], {"pass": 1, "fail": 0})
            self.assertEqual(a["pass_to_pass"], {"pass": 2, "fail": 1})
            # 两个 model 目录且未指定 --model → 参数错误
            (tmp / "logs/run_evaluation/r9/m2/x").mkdir(parents=True)
            (tmp / "logs/run_evaluation/r9/m2/x/report.json").write_text(
                "{}", encoding="utf-8", newline="\n")
            rc, _, _, _ = venv_run(AGENT / "swe_run.py", "report",
                                   "--run-id", "r9",
                                   "--logs-root", tmp / "logs/run_evaluation")
            self.assertEqual(rc, 2)


class TestCandidateRanking(unittest.TestCase):
    """Candidate snapshot collection + regression filtering + vote ranking
    (round-37, borrowing Agentless layering + patch sorting architecture).

    Each successful edit round produces a snapshot in candidates/; at
    convergence _rank_candidates picks the best by test outcome, validation,
    and minimal-patch principle. Single-candidate is a passthrough.
    """

    def _mod(self):
        return _load(AGENT / "code-task.py", "code_task_cand")

    def test_single_candidate_passthrough(self):
        """Single candidate: ranking is a passthrough (no behavior change)."""
        mod = self._mod()
        tmp = tmpspace.create(prefix="cand-1-")
        self.addCleanup(tmpspace.release, tmp)
        mod._save_candidate(tmp, 0, "diff --git a/x b/x\n+new\n",
                           "pass", ["ok"], 1,
                           {"ok": True, "issues": []}, [], ["x.py"])
        cands, best = mod._rank_candidates(tmp)
        self.assertEqual(len(cands), 1)
        self.assertIsNotNone(best)
        self.assertEqual(best["tests"], "pass")
        self.assertEqual(best["rank"], 0)

    def test_rank_test_pass_beats_fail(self):
        """Test-passing candidate ranks ahead of test-failing one."""
        mod = self._mod()
        tmp = tmpspace.create(prefix="cand-rank-")
        self.addCleanup(tmpspace.release, tmp)
        mod._save_candidate(tmp, 1, "patch1", "fail", ["err"], 1,
                           {"ok": True, "issues": []}, [], ["f.py"])
        mod._save_candidate(tmp, 2, "patch2", "pass", [], 2,
                           {"ok": True, "issues": []}, [], ["f.py"])
        cands, best = mod._rank_candidates(tmp)
        self.assertEqual(best["tests"], "pass")
        self.assertEqual(best["round"], 2)
        self.assertEqual(cands[0]["round"], 2)
        self.assertEqual(cands[1]["round"], 1)

    def test_bad_patch_ranks_last(self):
        """Reverse verification: empty patch candidate goes to the bottom."""
        mod = self._mod()
        tmp = tmpspace.create(prefix="cand-bad-")
        self.addCleanup(tmpspace.release, tmp)
        mod._save_candidate(tmp, 1, "patch1", "fail", [], 1,
                           {"ok": True, "issues": []}, [], ["f.py"])
        mod._save_candidate(tmp, 2, "", "skip", [], 0,
                           {"ok": False,
                            "issues": [{"code": "empty_patch"}]}, [], [])
        cands, best = mod._rank_candidates(tmp)
        self.assertIsNotNone(best, "Candidate with a patch should be best")
        self.assertEqual(best["round"], 1)
        self.assertEqual(cands[-1]["round"], 2, "Empty-patch candidate goes last")
        self.assertEqual(cands[-1]["rank_reason"]["tier_name"], "empty")

    def test_rank_minimal_patch_wins(self):
        """Same tier + same validation: smaller patch wins (minimal change)."""
        mod = self._mod()
        tmp = tmpspace.create(prefix="cand-min-")
        self.addCleanup(tmpspace.release, tmp)
        mod._save_candidate(tmp, 1, "x" * 100, "pass", [], 1,
                           {"ok": True, "issues": []}, [], ["f.py"])
        mod._save_candidate(tmp, 2, "x" * 10, "pass", [], 1,
                           {"ok": True, "issues": []}, [], ["f.py"])
        cands, best = mod._rank_candidates(tmp)
        self.assertEqual(best["round"], 2, "Smaller patch should rank first")
        self.assertLess(best["patch_chars"], cands[1]["patch_chars"])

    def test_manifest_includes_candidates(self):
        """End-to-end: manifest carries candidates list and selected_source."""
        tmp = tmpspace.create(prefix="cand-e2e-")
        self.addCleanup(tmpspace.release, tmp)
        repo, out, env = _mini_repo(tmp), tmp / "task", _host_env()
        base = [str(VENV_PY), str(AGENT / "code-task.py"),
                "--repo", str(repo), "--task",
                "修复 bug.py 使 tests 通过", "--out", str(out)]
        p = subprocess.run(base, shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=120, env=env)
        data = json.loads(p.stdout)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        Path(data["llm_response"]).write_text(json.dumps(
            {"action": "edit",
             "edits": [{"path": "bug.py", "search": "    return a - b",
                        "replace": "    return a + b"}]}),
            encoding="utf-8", newline="\n")
        p2 = subprocess.run(base + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            timeout=180, env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(data2["state"], "DONE")
        manifest = json.loads((out / "task-manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertIn("candidates", manifest,
                      "manifest must carry candidates list")
        self.assertIn("selected_source", manifest,
                      "manifest must carry patch provenance source")
        self.assertGreaterEqual(len(manifest["candidates"]), 1,
                                "At least one snapshot from successful edit")
        for c in manifest["candidates"]:
            self.assertNotIn("patch_text", c,
                             "Candidates in manifest must not carry patch text")


def setUpModule():
    test_scripts.ensure_fixture()


class TestMemoryWriteIntegration(unittest.TestCase):
    """记忆写入层集成测试：--memory-file 指定时才写，默认不污染仓库。"""

    def test_memory_write_on_successful_task(self):
        """一轮成功的编码循环应在 --memory-file 指定的文件写入一条记忆。"""
        tmp = tmpspace.create(prefix="mem-write-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "calc.py").write_text(
            "def add(a, b):\n    return a - b\n",
            encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_calc.py").write_text(
            "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        mem_file = tmp / "memory.jsonl"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "fix calc.py add function",
               "--out", str(out), "--rounds", "3",
               "--memory-file", str(mem_file)]
        # 第一轮：等待宿主
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertEqual(data["state"], "WAIT_HOST_LLM")
        # stub 宿主响应
        response = {"action": "edit",
                    "edits": [{"path": "calc.py",
                               "search": "    return a - b",
                               "replace": "    return a + b"}],
                    "summary": "fix add operator"}
        Path(data["llm_response"]).write_text(
            json.dumps(response, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        # 续跑：应 DONE
        p2 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=180,
                            env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0)
        self.assertEqual(data2["state"], "DONE")
        # 验证记忆文件被写入（--memory-file 指定路径，不是仓库 retro/）
        self.assertTrue(mem_file.is_file(), "记忆文件应被创建")
        lines = mem_file.read_text(encoding="utf-8").strip().split("\n")
        # 过滤出当前任务的记忆条目（task 字段包含 "calc"）
        task_entries = [json.loads(l) for l in lines
                        if "calc" in l]
        self.assertGreaterEqual(len(task_entries), 1,
                                "应至少有一条 calc 相关记忆")
        entry = task_entries[0]
        # 关键字段存在性断言
        self.assertIn("id", entry)
        self.assertIn("timestamp", entry)
        self.assertEqual(entry["task"], "fix calc.py add function")
        self.assertEqual(entry["result"], "pass")
        # repo 路径应指向一个仓库目录
        self.assertTrue(entry["repo"].endswith("repo"),
                        "repo 路径应指向测试仓库目录")
        # trace_file 必须指向真实存在的轨迹文件（不许写不存在的预定路径）
        self.assertTrue(entry["trace_file"], "trace_file 不应为空")
        self.assertTrue(Path(entry["trace_file"]).is_file(),
                        "trace_file 指向的文件必须真实存在: %s"
                        % entry["trace_file"])
        # 记忆条目记录的检索命中数应是整数（本次无记忆注入 → 0）
        self.assertEqual(entry["retrieval_count"], 0)

    def test_memory_write_off_by_default(self):
        """未给 --memory-file / CRA_MEMORY_FILE 时不写记忆（仓库零污染）。"""
        import importlib.util
        from unittest import mock
        spec = importlib.util.spec_from_file_location(
            "code_task_memoff", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = tmpspace.create(prefix="mem-off-")
        self.addCleanup(tmpspace.release, tmp)
        env = dict(os.environ)
        env.pop("CRA_MEMORY_FILE", None)
        with mock.patch.dict(os.environ, env, clear=True):
            mod._write_memory(tmp, ".", "t", ["x.py"], "", [], "pass", "", "",
                              round_num=0)
        self.assertEqual(list(tmp.rglob("*.jsonl")), [],
                         "默认关闭时不应创建任何记忆文件")


class TestProgressFrameConsumer(unittest.TestCase):
    """流式帧消费端验证：stderr JSON 帧的结构、隔离性与时序。"""

    def test_progress_frame_stderr_isolation(self):
        """_progress_frame 输出到 stderr，不污染 stdout 主输出。"""
        tmp = tmpspace.create(prefix="prog-frame-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "x.py").write_text("def f():\n    return 1\n",
                                   encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_x.py").write_text(
            "from x import f\n\ndef test_f():\n    assert f() == 1\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "no-op",
               "--out", str(out), "--rounds", "1"]
        p = subprocess.run(cmd, shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=120, env=env)
        # stdout 必须是合法 JSON（主输出）
        self.assertEqual(p.returncode, 1)  # WAIT_HOST_LLM
        stdout_data = json.loads(p.stdout)
        self.assertEqual(stdout_data["state"], "WAIT_HOST_LLM")
        # stderr 必须包含至少一个进度帧（单行 JSON）
        stderr_lines = [l for l in p.stderr.split("\n") if l.strip()]
        self.assertGreaterEqual(len(stderr_lines), 1,
                                "stderr 应至少有一条进度帧")
        # 每行 stderr 必须是合法 JSON
        for line in stderr_lines:
            frame = json.loads(line)
            self.assertIn("round", frame)
            self.assertIn("event", frame)

    def test_progress_frame_events_sequence(self):
        """一轮完整流程的 stderr 帧事件序列：round_start → llm_call_start → parsed。"""
        tmp = tmpspace.create(prefix="prog-seq-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "y.py").write_text("def g():\n    return 2\n",
                                   encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_y.py").write_text(
            "from y import g\n\ndef test_g():\n    assert g() == 2\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "no-op",
               "--out", str(out), "--rounds", "1"]
        p = subprocess.run(cmd, shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=120, env=env)
        stderr_lines = [json.loads(l) for l in p.stderr.split("\n")
                        if l.strip()]
        events = [f["event"] for f in stderr_lines]
        # 至少应包含 round_start 和 llm_call_start
        self.assertIn("round_start", events)
        self.assertIn("llm_call_start", events)


class TestTracer(unittest.TestCase):
    """v1.43.0 轻量 Trace：JSONL 形状与 timer 语义。"""

    @classmethod
    def setUpClass(cls):
        cls.trace = load_agent_script("trace.py")

    def test_span_jsonl_shape(self):
        tmp = tmpspace.create(prefix="trace-shape-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s1",
                                   trace_dir=str(tmp / "traces"))
        tracer.span("llm", "call_start", round=0)
        tracer.span("llm", "call_end", duration_ms=12,
                    token_output=7, status="ok")
        path = tmp / "traces" / "s1.jsonl"
        lines = [json.loads(l) for l in
                 path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        first, second = lines
        for key in ("trace_id", "observation_id", "session_id", "step",
                    "phase", "timestamp", "duration_ms", "token_input",
                    "token_output", "cost_usd", "status"):
            self.assertIn(key, first, "trace 缺字段 %s" % key)
        self.assertEqual(first["trace_id"], "s1")
        self.assertEqual(first["round"], 0)
        self.assertEqual(second["token_output"], 7)
        self.assertNotEqual(first["observation_id"],
                            second["observation_id"],
                            "每条 span 的 observation_id 必须唯一")

    def test_timer_records_failure_and_propagates(self):
        tmp = tmpspace.create(prefix="trace-timer-")
        self.addCleanup(tmpspace.release, tmp)
        tracer = self.trace.Tracer(session_id="s2",
                                   trace_dir=str(tmp / "traces"))
        with self.assertRaises(RuntimeError):
            with tracer.timer("edit", "apply"):
                raise RuntimeError("boom")
        rec = json.loads((tmp / "traces" / "s2.jsonl").read_text(
            encoding="utf-8").splitlines()[0])
        self.assertEqual(rec["status"], "fail")
        self.assertIsNotNone(rec["duration_ms"], "timer 必须写入耗时")


class TestContextBudget(unittest.TestCase):
    """v1.43.0 上下文工程：工具输出外置 + 历史确定性压缩。"""

    @classmethod
    def setUpClass(cls):
        cls.ct = load_agent_script("code-task.py")

    def test_truncate_small_text_stays_inline(self):
        tmp = tmpspace.create(prefix="ctx-small-")
        self.addCleanup(tmpspace.release, tmp)
        text = "def f():\n    return 1\n"
        self.assertEqual(
            self.ct._truncate_for_history(text, tmp, 0, "read_x"), text)
        self.assertFalse((tmp / "tool-outputs").exists(),
                         "小输出不应落外置文件")

    def test_truncate_large_text_externalized(self):
        tmp = tmpspace.create(prefix="ctx-big-")
        self.addCleanup(tmpspace.release, tmp)
        big = "A" * (self.ct.MAX_INLINE_CHARS + 1)
        out = self.ct._truncate_for_history(big, tmp, 3, "read_big")
        self.assertIn("完整输出见", out)
        f = tmp / "tool-outputs" / "r3_read_big.txt"
        self.assertTrue(f.is_file(), "大输出应外置到 tool-outputs/")
        self.assertEqual(f.read_text(encoding="utf-8"), big,
                         "外置文件必须是完整原文，不许二次截断")

    def test_truncate_many_lines_externalized(self):
        tmp = tmpspace.create(prefix="ctx-lines-")
        self.addCleanup(tmpspace.release, tmp)
        text = "\n".join("line%d" % i
                         for i in range(self.ct.MAX_INLINE_LINES + 1))
        out = self.ct._truncate_for_history(text, tmp, 0, "read_many")
        self.assertIn("完整输出见", out)

    def test_compress_history_below_threshold_unchanged(self):
        mt = _submodule("materials")
        old_t = mt.COMPRESS_TRIGGER_CHARS
        old_k = mt.KEEP_RECENT_ENTRIES
        mt.COMPRESS_TRIGGER_CHARS = 100
        mt.KEEP_RECENT_ENTRIES = 3
        try:
            hist = ["short"] * 5
            self.assertEqual(self.ct._compress_history(hist), hist,
                             "未超阈值时原文不许动")
        finally:
            mt.COMPRESS_TRIGGER_CHARS = old_t
            mt.KEEP_RECENT_ENTRIES = old_k

    def test_compress_history_keeps_recent_and_marks(self):
        mt = _submodule("materials")
        old_t = mt.COMPRESS_TRIGGER_CHARS
        old_k = mt.KEEP_RECENT_ENTRIES
        mt.COMPRESS_TRIGGER_CHARS = 100
        mt.KEEP_RECENT_ENTRIES = 3
        try:
            old = ["old%d %s" % (i, "x" * 200) for i in range(5)]
            recent = ["recent1", "recent2", "recent3"]
            out = self.ct._compress_history(old + recent)
            self.assertTrue(out[0].startswith("[已压缩 5 条旧历史"),
                            "压缩后首行应带压缩标记")
            self.assertEqual(out[-3:], recent,
                             "最近 KEEP_RECENT_ENTRIES 条必须保留原文")
            self.assertTrue(out[1].startswith("old0"),
                            "旧条目应保留首行")
            self.assertLessEqual(len(out[1]), 103,
                                 "旧条目首行超过 100 字符应加省略号")
        finally:
            mt.COMPRESS_TRIGGER_CHARS = old_t
            mt.KEEP_RECENT_ENTRIES = old_k


class TestMemoryFewShot(unittest.TestCase):
    """v1.44.0 记忆 few-shot：默认关闭，显式给文件才注入。"""

    @classmethod
    def setUpClass(cls):
        cls.ct = load_agent_script("code-task.py")

    def test_few_shot_off_without_memory_file(self):
        tmp = tmpspace.create(prefix="fewshot-off-")
        self.addCleanup(tmpspace.release, tmp)
        self.assertEqual(self.ct._retro_few_shot("fix xss", ""), ("", 0))
        self.assertEqual(
            self.ct._retro_few_shot("fix xss", str(tmp / "none.jsonl")),
            ("", 0), "记忆文件不存在时必须静默降级，不许中断编码循环")

    def test_few_shot_injects_similar_case(self):
        tmp = tmpspace.create(prefix="fewshot-hit-")
        self.addCleanup(tmpspace.release, tmp)
        mem = tmp / "memory.jsonl"
        entries = [
            {"id": "mem-xss", "task": "fix XSS in innerHTML rendering",
             "summary": "escape HTML before render", "rule_codes": ["xss"],
             "failure_category": "security", "result": "pass"},
            {"id": "mem-docs", "task": "update readme documentation",
             "summary": "typo correction", "rule_codes": [],
             "failure_category": "", "result": "pass"},
        ]
        mem.write_text("\n".join(json.dumps(e, ensure_ascii=False)
                                 for e in entries) + "\n", encoding="utf-8")
        section, hits = self.ct._retro_few_shot(
            "fix XSS innerHTML", str(mem))
        self.assertEqual(hits, 1, "无关任务不应被检索进来")
        self.assertIn("历史相似案例", section)
        self.assertIn("mem-xss", section)


class TestAciStageTwo(unittest.TestCase):
    """round-53 阶段二：图排序（2.1）/ 搜索排序（2.2）/ list（2.3）/
    测试子集与语法树校验（2.4/2.5）的判据测试。"""

    def _graph_repo(self, root):
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "target.py").write_text(
            "def wanted_helper():\n    return 1\n",
            encoding="utf-8", newline="\n")
        (root / "pkg" / "impl.py").write_text(
            "from pkg.target import wanted_helper\n\n\n"
            "def run_it():\n    return wanted_helper()\n",
            encoding="utf-8", newline="\n")
        (root / "pkg" / "other.py").write_text(
            "def unrelated():\n    return 0\n",
            encoding="utf-8", newline="\n")
        return root

    def test_graph_rank_pulls_import_neighbors(self):
        """候选只命中调用方时，图传播必须把被 import 的目标文件补进来。"""
        mod = _load(AGENT / "repo_map.py", "repo_map_graph")
        tmp = tmpspace.create(prefix="aci-graph-")
        self.addCleanup(tmpspace.release, tmp)
        root = self._graph_repo(Path(tmp))
        graph = mod.build_import_graph(root)
        self.assertGreaterEqual(graph["edges"], 1, "import 边必须建起来")
        candidates = mod.scan_candidates(root, ["run_it"])
        self.assertIn("pkg/impl.py", [c["file"] for c in candidates])
        extra = mod.graph_rank(graph, candidates, ["run_it"])
        files = [c["file"] for c in extra]
        self.assertIn("pkg/target.py", files,
                      "被调用方 import 的文件必须由图传播补充")
        self.assertNotIn("pkg/other.py", files, "无边的文件不得凭空出现")
        self.assertNotIn("pkg/impl.py", files, "已有候选不得重复返回")

    def test_graph_rank_cli_opt_in(self):
        """--rank 默认 refs：同一仓库不出现图字段；显式 graph 才补邻居。"""
        tmp = tmpspace.create(prefix="aci-graph-cli-")
        self.addCleanup(tmpspace.release, tmp)
        root = self._graph_repo(Path(tmp))
        rc, data, _, _ = venv_run(AGENT / "repo_map.py", "--repo", root,
                                  "--task-text", "run_it")
        self.assertEqual(rc, 0)
        self.assertEqual(data["rank"]["mode"], "refs")
        self.assertNotIn("graph_files", data["rank"], "默认不得建图")
        rc, data, _, _ = venv_run(AGENT / "repo_map.py", "--repo", root,
                                  "--task-text", "run_it", "--rank", "graph")
        self.assertEqual(rc, 0)
        self.assertEqual(data["rank"]["mode"], "graph")
        self.assertGreaterEqual(data["rank"]["graph_files"], 3)
        self.assertIn("pkg/target.py",
                      [c["file"] for c in data["candidates"]])

    def test_search_ranks_definition_before_mentions(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="aci-search-rank-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        (root / "pkg").mkdir()
        mentions = "\n".join("x%d = wanted_symbol + %d" % (i, i)
                             for i in range(20))
        (root / "pkg" / "uses.py").write_text(mentions + "\n",
                                              encoding="utf-8", newline="\n")
        (root / "pkg" / "defs.py").write_text(
            "def wanted_symbol():\n    return 1\n",
            encoding="utf-8", newline="\n")
        ok, obs = mod._search_repo(root, "wanted_symbol")
        self.assertTrue(ok)
        first = obs.splitlines()[1]
        self.assertTrue(first.startswith("pkg/defs.py:1:"),
                        "定义点必须排在 20 条引用之前：%s" % first)
        # 反向验证：关掉排序键（等价旧行为）时按遍历顺序命中在 uses.py 更早
        self.assertIn("pkg/uses.py:1:", obs)

    def test_search_prefers_files_near_candidates(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="aci-search-near-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        for folder in ("alpha", "beta"):
            (root / folder).mkdir()
            (root / folder / "mod.py").write_text(
                "value = needle_here\n", encoding="utf-8", newline="\n")
        ok, obs = mod._search_repo(root, "needle_here",
                                   near=["alpha/other.py"])
        self.assertTrue(ok)
        first = obs.splitlines()[1]
        self.assertTrue(first.startswith("alpha/mod.py:1:"),
                        "同 kind 内应优先靠近候选目录的命中：%s" % first)

    def test_list_tree_bounded_and_jailed(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="aci-list-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        (root / "pkg" / "sub" / "deeper").mkdir(parents=True)
        (root / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
        (root / "pkg" / "sub" / "b.py").write_text("x = 2\n", encoding="utf-8")
        (root / "pkg" / "sub" / "deeper" / "c.py").write_text(
            "x = 3\n", encoding="utf-8")
        (root / ".git").mkdir()
        (root / ".git" / "secret").write_text("no\n", encoding="utf-8")
        linked = False
        try:
            (root / "link").symlink_to(root / "pkg",
                                       target_is_directory=True)
            linked = True
        except (OSError, NotImplementedError):
            pass  # Windows 非管理员无 symlink 权限：跳过该断言
        ok, obs = mod._list_tree(root, "")
        self.assertTrue(ok)
        self.assertIn("pkg/", obs)
        self.assertIn("a.py", obs)
        self.assertIn("sub/", obs)
        self.assertNotIn("b.py", obs, "depth=2 不得展开到 grandchildren")
        self.assertNotIn("secret", obs, "运行产物目录必须剪掉")
        if linked:
            self.assertNotIn("link", obs, "符号链接不得跟随")
        ok, obs = mod._list_tree(root, "pkg", depth=3)
        self.assertTrue(ok)
        self.assertIn("b.py", obs)
        ok, obs = mod._list_tree(root, "../outside")
        self.assertFalse(ok, "../ 越界必须拒绝")
        outside = str(Path(tmp).parent)
        ok, obs = mod._list_tree(root, outside)
        self.assertFalse(ok, "绝对路径越界必须拒绝")

    def test_test_subset_selection_and_scope_label(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="aci-subset-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        (root / "pkg").mkdir()
        (root / "pkg" / "alpha.py").write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8", newline="\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_alpha.py").write_text(
            "from pkg.alpha import add\n\n\ndef test_add():\n"
            "    assert add(1, 2) == 3\n", encoding="utf-8", newline="\n")
        (root / "tests" / "test_beta.py").write_text(
            "def test_beta():\n    assert True\n",
            encoding="utf-8", newline="\n")
        picked = mod._select_test_paths(root, ["pkg/alpha.py"])
        self.assertIn("tests/test_alpha.py", picked)
        self.assertNotIn("tests/test_beta.py", picked)
        # 改的本身就是测试文件时直接选中
        picked = mod._select_test_paths(root, ["tests/test_beta.py"])
        self.assertEqual(picked, ["tests/test_beta.py"])
        # 映射不出时返回空（由调用方回退全量，不许猜）
        self.assertEqual(mod._select_test_paths(root, ["pkg/unknown.py"]), [])
        status, detail = mod._run_tests(root, ["pkg/alpha.py"])
        self.assertEqual(status, "pass", detail)
        self.assertTrue(detail[0].startswith("子集"), detail)
        self.assertIn("原范围", detail[0])

    def test_subset_audit_catches_hidden_regression(self):
        """子集通过但全量有隐藏回归：抽检轮次必须转 fail，未抽检轮次须标注。"""
        import hashlib
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="aci-audit-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        (root / "mod").mkdir()
        (root / "mod" / "core.py").write_text(
            "def value():\n    return 1\n", encoding="utf-8", newline="\n")
        (root / "tests").mkdir()
        (root / "tests" / "test_core.py").write_text(
            "from mod.core import value\n\n\ndef test_value():\n"
            "    assert value() == 1\n", encoding="utf-8", newline="\n")
        (root / "tests" / "test_contract.py").write_text(
            "from mod.core import value\n\n\ndef test_contract():\n"
            "    assert value() == 2\n", encoding="utf-8", newline="\n")
        seed = ""
        for i in range(60):
            cand = "0|mod/core.py|%d" % i
            if hashlib.sha1(cand.encode("utf-8")).digest()[0] % 3 == 0:
                seed = cand
                break
        status, detail = mod._run_tests(root, ["mod/core.py"],
                                        audit_seed=seed)
        self.assertEqual(status, "fail", detail)
        self.assertIn("抽检未过", detail[0])
        status, detail = mod._run_tests(root, ["mod/core.py"])
        self.assertEqual(status, "pass", "未抽检时子集通过即为 pass")
        self.assertIn("未抽检", detail[0], "必须标注未经全量确认")

    def test_syntax_issues_flags_broken_python_only(self):
        mod = _load(AGENT / "repo_map.py", "repo_map_syntax")
        tmp = tmpspace.create(prefix="aci-syntax-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        (root / "good.py").write_text("def f():\n    return 1\n",
                                      encoding="utf-8", newline="\n")
        (root / "bad.py").write_text(
            "def f(:\n    return 1\n", encoding="utf-8", newline="\n")
        # tree-sitter 的 ERROR 恢复会放过纯缩进错误（round-53 变异语料实测
        # 8/10），必须由 ast.parse 第二道网兜住
        (root / "bad_indent.py").write_text(
            "def f():\n    return 1\n      return 2\n",
            encoding="utf-8", newline="\n")
        (root / "notes.txt").write_text("def f(:\n", encoding="utf-8")
        issues = mod.syntax_issues(root, ["good.py", "bad.py", "bad_indent.py",
                                          "notes.txt", "missing.py"])
        self.assertEqual(len(issues), 2, issues)
        self.assertEqual({i["code"] for i in issues}, {"syntax_error"})
        self.assertIn("bad.py", issues[0]["detail"])
        self.assertIn(":1", issues[0]["detail"], "必须给出行号")

    def _init_repo(self, repo):
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)

    def _run_stage(self, cmd, env, response):
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(data["state"], "WAIT_HOST_LLM",
                         json.dumps(data, ensure_ascii=False)[:400])
        Path(data["llm_response"]).write_text(
            json.dumps(response, ensure_ascii=False),
            encoding="utf-8", newline="\n")
        prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
        return p, data, prompt

    def test_syntax_error_edit_is_bounced_e2e(self):
        """语法坏掉的编辑不得进入补丁：非末轮退回重做，改对后测试转绿。"""
        tmp = tmpspace.create(prefix="aci-syntax-e2e-")
        self.addCleanup(tmpspace.release, tmp)
        repo = Path(tmp) / "repo"
        repo.mkdir()
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")
        (repo / "tests").mkdir()
        (repo / "tests" / "test_bug.py").write_text(
            "from bug import add\n\n\ndef test_add():\n"
            "    assert add(1, 2) == 3\n", encoding="utf-8", newline="\n")
        self._init_repo(repo)
        out = Path(tmp) / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "修复 bug.py 使 tests 通过",
               "--out", str(out)]
        bad = {"action": "edit",
               "edits": [{"path": "bug.py",
                          "search": "    return a - b",
                          "replace": "    return a - (b"}],
               "summary": "故意写坏括号"}
        p, data, _ = self._run_stage(cmd, env, bad)
        self.assertEqual(p.returncode, 1)
        # 坏语法那轮已被回滚（round-58：校验未过的编辑不得留在工作树），
        # 因此重试必须按基线内容写 SEARCH，而不是按上一版补丁的代码。
        p2, data2, prompt2 = self._run_stage(cmd + ["--resume"], env, {
            "action": "edit",
            "edits": [{"path": "bug.py",
                       "search": "    return a - b",
                       "replace": "    return a + b"}],
            "summary": "修正"})
        self.assertEqual(p2.returncode, 1)
        self.assertEqual(data2["state"], "WAIT_HOST_LLM")
        self.assertIn("补丁即时校验未过[syntax_error]", prompt2,
                      "坏语法必须退回并出现在下一轮材料里")
        self.assertIn("本轮编辑已回滚", prompt2,
                      "回滚必须对模型可见（否则重试会按脏文件写 SEARCH）")
        p3 = subprocess.run(cmd + ["--resume"], shell=False,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace",
                            timeout=180, env=env)
        data3 = json.loads(p3.stdout)
        self.assertEqual(p3.returncode, 0,
                         json.dumps(data3, ensure_ascii=False)[:400])
        self.assertEqual(data3["state"], "DONE")
        self.assertEqual(data3["tests"], "pass")
        text = Path(data3["patch"]).read_text(encoding="utf-8")
        self.assertIn("+    return a + b", text)
        self.assertNotIn("a - (b", text)
        manifest = json.loads((out / "task-manifest.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["rank"], "refs", "默认排序模式必须入 manifest")



class TestAgentPhases(unittest.TestCase):
    """阶段四 4.1：定位/修复/验证三角色 + 主循环裁决（--phases）。

    契约：角色动作面门禁（locate/verify 禁编辑）、裁决台账 phases.json
    （accept/rework/escalate）、机械测试结果优先于 verify 自评、locate
    轮数耗尽降级、轮数预算跨 --resume 持久化、单循环模式零变化。
    """

    TASK = "修复 bug.py 使 tests 通过"
    FIX_EDIT = {"action": "edit",
                "edits": [{"path": "bug.py", "search": "    return a - b",
                           "replace": "    return a + b"}],
                "summary": "减号改加号"}
    BAD_EDIT = {"action": "edit",
                "edits": [{"path": "bug.py", "search": "def add(a, b):",
                           "replace": "def add(a, b):  # still wrong"}],
                "summary": "只加注释"}
    BAD_ASCII_EDIT = {"action": "edit",
                      "edits": [{"path": "bug.py",
                                 "search": "    return a - b",
                                 "replace": "    return abs(a - b)  # 中文注释"}],
                      "summary": "用 abs 兜底（新增行含非 ASCII）"}
    LOCATE_DONE = {"action": "locate_done",
                   "files": [{"path": "bug.py", "why": "add 返回 a-b"}],
                   "root_cause": "减号写错", "confidence": "high"}
    DONE = {"action": "done", "summary": "无更多改动"}
    PASS = {"action": "verdict", "pass": True, "reasons": ["补丁覆盖根因"]}
    REJECT = {"action": "verdict", "pass": False,
              "reasons": ["没有覆盖同类缺陷"]}

    def _repo(self):
        tmp = tmpspace.create(prefix="code-task-phases-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "bug.py").write_text("def add(a, b):\n    return a - b\n",
                                     encoding="utf-8", newline="\n")
        tests = repo / "tests"
        tests.mkdir()
        (tests / "test_bug.py").write_text(
            "from bug import add\n\n\ndef test_add():\n"
            "    assert add(1, 2) == 3\n", encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        return repo, out, env

    @staticmethod
    def _phase_of(prompt):
        for marker, name in (("阶段：定位", "locate"),
                             ("阶段：修复", "fix"),
                             ("阶段：验证", "verify")):
            if marker in prompt:
                return name
        return ""

    def _drive(self, repo, out, env, script, extra=(), phases=True,
               max_turns=16):
        """按阶段脚本应答宿主协议，返回 (rc, 末次 JSON, [(phase, prompt)])。"""
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", self.TASK, "--out", str(out)]
        if phases:
            cmd.append("--phases")
        cmd += [str(x) for x in extra]
        queues = {k: list(v) for k, v in script.items()}
        prompts = []
        resume = False
        for _ in range(max_turns):
            full = cmd + (["--resume"] if resume else [])
            p = subprocess.run(full, shell=False, capture_output=True,
                               text=True, encoding="utf-8",
                               errors="replace", timeout=300, env=env)
            data = json.loads(p.stdout)
            if data.get("state") != "WAIT_HOST_LLM":
                return p.returncode, data, prompts
            prompt = Path(data["llm_task"]).read_text(encoding="utf-8")
            phase = self._phase_of(prompt)
            prompts.append((phase, prompt))
            queue = queues.get(phase) or []
            self.assertTrue(
                queue, "阶段 %s 无脚本化应答（第 %d 轮）；prompt 头部：%s"
                % (phase, len(prompts), prompt[:600]))
            Path(data["llm_response"]).write_text(
                json.dumps(queue.pop(0), ensure_ascii=False),
                encoding="utf-8", newline="\n")
            resume = True
        self.fail("超过 %d 轮仍在等待宿主：%s"
                  % (max_turns, [x[0] for x in prompts]))

    def _phases_doc(self, out):
        return json.loads((out / "phases.json").read_text(encoding="utf-8"))

    def test_happy_path_resolves_with_decision_ledger(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.LOCATE_DONE],
            "fix": [self.FIX_EDIT],
            "verify": [self.PASS],
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertEqual(data["state"], "DONE")
        self.assertTrue(data["resolved"], "三角色全绿才 resolved")
        self.assertEqual(data["tests"], "pass")
        self.assertEqual([x[0] for x in prompts], ["locate", "fix", "verify"])
        # 角色材料：fix 拿定位报告，verify 拿补丁与测试状态
        self.assertIn("定位报告", prompts[1][1])
        self.assertIn("补丁（git diff", prompts[2][1])
        doc = self._phases_doc(out)
        self.assertEqual([(d["phase"], d["decision"]) for d in doc["decisions"]],
                         [("locate", "accept"), ("fix", "accept"),
                          ("verify", "accept")])
        manifest = json.loads((out / "task-manifest.json").read_text(
            encoding="utf-8"))
        self.assertTrue(manifest["resolved"])
        self.assertEqual(manifest["phases"]["decision_counts"],
                         {"accept": 3})
        patch = Path(data["patch"]).read_text(encoding="utf-8")
        self.assertIn("+    return a + b", patch)
        self.assertIn("return a - b", (repo / "bug.py").read_text(
            encoding="utf-8"), "被审仓库不得被直接写入")

    def test_locate_cannot_edit_and_gets_rejected(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.FIX_EDIT, self.LOCATE_DONE],
            "fix": [self.FIX_EDIT],
            "verify": [self.PASS],
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertTrue(data["resolved"])
        self.assertEqual(prompts[0][0], "locate")
        self.assertEqual(prompts[1][0], "locate", "edit 被拒后仍停在定位")
        self.assertIn("动作 edit 在 locate 阶段不可用", prompts[1][1])
        # 定位阶段的 edit 没有落盘：fix 的 SEARCH 仍能匹配基线内容
        doc = self._phases_doc(out)
        self.assertEqual(doc["decisions"][0]["decision"], "accept")

    def test_verify_reject_triggers_rework_with_reasons(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.LOCATE_DONE],
            "fix": [self.FIX_EDIT, self.DONE],
            "verify": [self.REJECT, self.PASS],
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertTrue(data["resolved"])
        doc = self._phases_doc(out)
        self.assertEqual(doc["rework_count"], 1)
        seq = [(d["phase"], d["decision"]) for d in doc["decisions"]]
        self.assertIn(("verify", "reject"), seq)
        self.assertIn(("verify", "rework"), seq)
        # 返工材料必须带拒收理由，fix 才知道为什么被打回
        fix_prompts = [p for ph, p in prompts if ph == "fix"]
        self.assertTrue(any("验证退回理由" in p for p in fix_prompts))
        self.assertTrue(any("没有覆盖同类缺陷" in p for p in fix_prompts))

    def test_tests_fail_overrides_verify_pass(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.LOCATE_DONE],
            "fix": [self.BAD_EDIT, self.DONE, self.FIX_EDIT],
            "verify": [self.PASS, self.PASS],
        })
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertTrue(data["resolved"])
        doc = self._phases_doc(out)
        first_reject = [d for d in doc["decisions"]
                        if d["phase"] == "verify" and d["decision"] == "reject"]
        self.assertTrue(first_reject)
        self.assertIn("机械测试未通过", first_reject[0]["reason"],
                      "verdict.pass=true 不得压过 tests=fail")

    def test_rework_budget_exhausted_escalates_without_manifest(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.LOCATE_DONE],
            "fix": [self.BAD_EDIT, self.DONE, self.DONE],
            "verify": [self.PASS, self.PASS, self.PASS],
        }, extra=["--rework-max", "1"])
        self.assertEqual(rc, 1)
        self.assertEqual(data["state"], "ESCALATED")
        self.assertFalse(data["resolved"])
        self.assertFalse((out / "task-manifest.json").exists(),
                         "升级态不得写 manifest（下游不收）")
        doc = self._phases_doc(out)
        self.assertTrue(doc["escalated"])
        report = (out / "task-report.md").read_text(encoding="utf-8")
        self.assertIn("阶段裁决（phases.json）", report)

    def test_locate_budget_exhausted_degrades_to_fix(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [{"action": "read", "files": ["bug.py"]}],
            "fix": [self.FIX_EDIT],
            "verify": [self.PASS],
        }, extra=["--locate-rounds", "1"])
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertTrue(data["resolved"])
        doc = self._phases_doc(out)
        decisions = [(d["phase"], d["decision"]) for d in doc["decisions"]]
        self.assertIn(("locate", "degrade"), decisions)
        self.assertEqual(prompts[1][0], "fix", "降级后下一轮进修复阶段")
        self.assertIn("定位轮数用尽", prompts[1][1])

    def test_rounds_budget_persists_across_resume(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "locate": [self.LOCATE_DONE],
            "fix": [self.FIX_EDIT],
        }, extra=["--rounds", "2"])
        self.assertEqual(rc, 1)
        self.assertEqual(data["state"], "ESCALATED")
        self.assertEqual(data["rounds"], 2)
        doc = self._phases_doc(out)
        self.assertIn("全局轮数用尽（2 轮）", doc["reason"],
                      "resume 不得回退默认轮数预算")

    def test_legacy_mode_has_no_phase_artifacts(self):
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "": [self.FIX_EDIT],
        }, phases=False)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertEqual(data["state"], "DONE")
        self.assertEqual(data["tests"], "pass")
        self.assertFalse((out / "phases.json").exists())
        manifest = json.loads((out / "task-manifest.json").read_text(
            encoding="utf-8"))
        self.assertNotIn("resolved", manifest)
        self.assertNotIn("phases", manifest)

    def test_rejected_edit_is_rolled_back_before_retry(self):
        """校验未过的编辑必须回滚：下一轮按基线文本的 SEARCH 仍能命中。"""
        repo, out, env = self._repo()
        rc, data, prompts = self._drive(repo, out, env, {
            "": [self.BAD_ASCII_EDIT, self.FIX_EDIT],
        }, phases=False)
        self.assertEqual(rc, 0, json.dumps(data, ensure_ascii=False)[:500])
        self.assertEqual(data["state"], "DONE")
        self.assertEqual(data["tests"], "pass")
        meta = json.loads((out / "task-meta.json").read_text(encoding="utf-8"))
        joined = "\n".join(meta.get("history") or [])
        self.assertIn("补丁即时校验未过[non_ascii]", joined)
        self.assertIn("本轮编辑已回滚", joined,
                      "校验未过的改动不得留在工作树（round-58 实踩）")
        self.assertEqual(meta["edits_applied"], 1,
                         "被回滚的编辑不得计入 edits_applied")
        patch = Path(data["patch"]).read_text(encoding="utf-8")
        self.assertIn("+    return a + b", patch)
        self.assertNotIn("中文注释", patch, "被拒改动不得留在最终补丁里")


TS_CALC = """export function clamp(value: number, lo: number, hi: number): number {
  if (value < lo) return hi;
  if (value > hi) return lo;
  return value;
}
"""

TS_TEST = """import { test } from "node:test";
import assert from "node:assert/strict";
import { clamp } from "./calc.ts";

test("clamp below", () => {
  assert.equal(clamp(-5, 0, 10), 0);
});

test("clamp above", () => {
  assert.equal(clamp(15, 0, 10), 10);
});

test("clamp inside", () => {
  assert.equal(clamp(5, 0, 10), 5);
});
"""

GO_STACK = """package stack

type Stack struct {
	items []int
}

func (s *Stack) Push(v int) {
	s.items = append(s.items, v)
}

func (s *Stack) Pop() int {
	if len(s.items) == 0 {
		panic("pop from empty stack")
	}
	v := s.items[len(s.items)-1]
	s.items = s.items[:len(s.items)-1]
	return v
}

func (s *Stack) Size() int {
	return len(s.items) + 1
}
"""

GO_TEST = """package stack

import "testing"

func TestPushPopSize(t *testing.T) {
	s := &Stack{}
	s.Push(1)
	s.Push(2)
	if s.Size() != 2 {
		t.Fatalf("Size=%d, want 2", s.Size())
	}
	if got := s.Pop(); got != 2 {
		t.Fatalf("Pop=%d, want 2", got)
	}
	if s.Size() != 1 {
		t.Fatalf("Size after pop=%d, want 1", s.Size())
	}
}
"""


class TestMultiLang(unittest.TestCase):
    """阶段四 4.2（round-59）：TS/Go 的 repo map、语法校验与测试引擎。

    外部工具（node/go）缺失时相应 e2e 跳过——CI 只保证 Python 与 pytest；
    本机/验收实跑的 resolved 证据见 reports/multilang-round59/。
    """

    def _write(self, root, rel, text):
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def _init_repo(self, repo):
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)

    def _stage(self, cmd, env, response):
        p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300,
                           env=env)
        data = json.loads(p.stdout)
        self.assertEqual(data["state"], "WAIT_HOST_LLM",
                         json.dumps(data, ensure_ascii=False)[:400])
        Path(data["llm_response"]).write_text(
            json.dumps(response, ensure_ascii=False), encoding="utf-8",
            newline="\n")
        return p, data

    def test_repo_map_multilang_symbols(self):
        mod = load_agent_script("repo_map.py")
        tmp = tmpspace.create(prefix="ml-map-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        self._write(root, "src/calc.ts", TS_CALC)
        self._write(root, "src/view.tsx",
                    "export const Btn = () => <b>x</b>;\n")
        self._write(root, "src/legacy.js", "function legacy() { return 1; }\n")
        self._write(root, "pkg/stack.go", GO_STACK)
        self._write(root, "node_modules/dep/index.ts",
                    "export function hidden() { return 1; }\n")
        repo_map = mod.build_map(root)
        files = repo_map["files"]
        self.assertIn("src/calc.ts", files)
        self.assertIn("pkg/stack.go", files)
        self.assertIn("src/view.tsx", files, "tsx 必须走 tsx 语法")
        self.assertNotIn("node_modules/dep/index.ts", files,
                         "node_modules 必须在目录级剪枝")
        names = {(d["name"], d["kind"]) for info in files.values()
                 for d in info["defs"]}
        for want in (("clamp", "func"), ("Stack", "class"), ("Push", "func"),
                     ("Pop", "func"), ("Size", "func"), ("legacy", "func"),
                     ("Btn", "func")):
            self.assertIn(want, names, "缺符号 %s" % (want,))

    def test_syntax_issues_multilang_negative(self):
        """反向验证：坏 TS/Go 必须被抓住，好的不得误报（维护红线 6）。"""
        mod = load_agent_script("repo_map.py")
        tmp = tmpspace.create(prefix="ml-syntax-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        self._write(root, "ok.ts",
                    "export function f(v: number): number {\n"
                    "  return v;\n}\n")
        self._write(root, "bad.ts",
                    "export function f(v: number) {\n  return v +;\n}\n")
        self._write(root, "ok.go", "package p\n\nfunc f() int {\n\treturn 1\n}\n")
        self._write(root, "bad.go",
                    "package p\n\nfunc f() int {\n\treturn 1 +\n}\n")
        issues = mod.syntax_issues(root, ["ok.ts", "bad.ts", "ok.go",
                                          "bad.go", "x.md"])
        self.assertEqual([i["code"] for i in issues],
                         ["syntax_error", "syntax_error"], issues)
        self.assertIn("bad.ts", issues[0]["detail"])
        self.assertIn("bad.go", issues[1]["detail"])

    def test_detect_engine_priority(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="ml-engine-")
        self.addCleanup(tmpspace.release, tmp)
        base = Path(tmp)
        go_repo = base / "go"
        go_repo.mkdir()
        self._write(go_repo, "go.mod", "module x\n\ngo 1.23\n")
        self.assertEqual(mod._detect_test_engine(go_repo)["engine"], "go")
        npm_repo = base / "npm"
        npm_repo.mkdir()
        self._write(npm_repo, "package.json",
                    json.dumps({"scripts": {"test": "node --test"}}))
        self.assertEqual(mod._detect_test_engine(npm_repo)["engine"], "npm")
        node_repo = base / "node"
        node_repo.mkdir()
        self._write(node_repo, "package.json", json.dumps({"name": "x"}))
        self._write(node_repo, "lib/a.test.ts", "// placeholder\n")
        engine = mod._detect_test_engine(node_repo)
        self.assertEqual(engine["engine"], "node")
        self.assertIn("--experimental-strip-types", engine["argv"])
        py_repo = base / "py"
        py_repo.mkdir()
        self._write(py_repo, "test_a.py",
                    "def test_a():\n    assert True\n")
        self.assertEqual(mod._detect_test_engine(py_repo)["engine"], "pytest")
        override = mod._detect_test_engine(go_repo, "python -m pytest -q")
        self.assertEqual(override["engine"], "cmd",
                         "--test-cmd 必须优先于仓库形态识别")
        self.assertEqual(override["argv"][:2], ["python", "-m"])
        empty = base / "empty"
        empty.mkdir()
        self.assertIsNone(mod._detect_test_engine(empty))

    def test_run_tests_cmd_override(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="ml-cmd-")
        self.addCleanup(tmpspace.release, tmp)
        root = Path(tmp)
        exe = '"%s"' % sys.executable
        info = {}
        status, detail = mod._run_tests(
            root, test_cmd='%s -c "import sys; sys.exit(0)"' % exe, info=info)
        self.assertEqual(status, "pass", detail)
        self.assertEqual(info.get("engine"), "cmd")
        self.assertIn("引擎 cmd", detail[0])
        status, _detail = mod._run_tests(
            root, test_cmd='%s -c "import sys; sys.exit(3)"' % exe)
        self.assertEqual(status, "fail")
        status, detail = mod._run_tests(
            root, test_cmd="definitely-not-a-real-binary-xyz --run")
        self.assertEqual(status, "skip", detail)
        self.assertIn("可执行文件", detail[0])

    def test_search_kind_multilang(self):
        mod = load_agent_script("code-task.py")
        self.assertEqual(mod._search_kind(
            "export function add(a: number) {", "add"), 0)
        self.assertEqual(mod._search_kind("func Add(a int) int {", "add"), 0)
        self.assertEqual(mod._search_kind("// add is exported", "add"), 2)
        self.assertEqual(mod._search_kind("  const x = add(1, 2);", "add"), 1)

    def _e2e(self, kind, files, response, engine_name):
        tmp = tmpspace.create(prefix="ml-e2e-%s-" % kind)
        self.addCleanup(tmpspace.release, tmp)
        repo = Path(tmp) / "repo"
        repo.mkdir()
        for rel, text in files.items():
            self._write(repo, rel, text)
        self._init_repo(repo)
        out = Path(tmp) / "task"
        env = dict(os.environ)
        env["CRA_LLM_PROVIDER"] = "host"
        env.pop("REVIEW_LLM_BASE_URL", None)
        env.pop("REVIEW_LLM_MODEL", None)
        if kind == "go":
            candidates = [os.environ.get("CRA_GO") or "", shutil.which("go") or "",
                          str(ROOT / "reports" / "_work" / "tooling" / "go" /
                              "bin" / "go.exe")]
            go_exe = next((c for c in candidates if c and Path(c).is_file()),
                          "")
            if not go_exe:
                self.skipTest("无 go 可执行文件（设 CRA_GO 或放本地工具链）")
            env["CRA_GO"] = go_exe
            env["GOTOOLCHAIN"] = "local"
            env["GOPROXY"] = "off"
            env["GOCACHE"] = str(Path(tmp) / "gocache")
        cmd = [str(VENV_PY), str(AGENT / "code-task.py"),
               "--repo", str(repo), "--task", "fix the failing tests",
               "--out", str(out)]
        p, _data = self._stage(cmd, env, response)
        self.assertEqual(p.returncode, 1)
        p2 = subprocess.run(cmd + ["--resume"], shell=False, capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            timeout=600, env=env)
        data2 = json.loads(p2.stdout)
        self.assertEqual(p2.returncode, 0,
                         json.dumps(data2, ensure_ascii=False)[:600])
        self.assertEqual(data2["state"], "DONE")
        self.assertEqual(data2["tests"], "pass")
        manifest = json.loads((out / "task-manifest.json").read_text(
            encoding="utf-8"))
        self.assertEqual(manifest["test_engine"], engine_name,
                         "manifest 必须记录实际测试引擎")
        patch = Path(data2["patch"]).read_text(encoding="utf-8")
        self.assertIn("+", patch)
        self.assertNotIn("diff --git a/package.json", patch)
        return manifest, patch

    @unittest.skipUnless(shutil.which("node"), "node 不在 PATH")
    def test_ts_task_end_to_end(self):
        manifest, patch = self._e2e("ts", {
            "package.json": json.dumps({"name": "calc", "type": "module"}),
            "lib/calc.ts": TS_CALC,
            "lib/calc.test.ts": TS_TEST,
        }, {
            "action": "edit",
            "edits": [{"path": "lib/calc.ts",
                       "search": "  if (value < lo) return hi;\n"
                                 "  if (value > hi) return lo;",
                       "replace": "  if (value < lo) return lo;\n"
                                  "  if (value > hi) return hi;"}],
            "summary": "clamp 上下界写反了"},
            "node")
        self.assertIn("+  if (value < lo) return lo;", patch)
        self.assertEqual(manifest["tests"], "pass")

    def test_go_task_end_to_end(self):
        manifest, patch = self._e2e("go", {
            "go.mod": "module demo\n\ngo 1.23\n",
            "stack/stack.go": GO_STACK,
            "stack/stack_test.go": GO_TEST,
        }, {
            "action": "edit",
            "edits": [{"path": "stack/stack.go",
                       "search": "\treturn len(s.items) + 1",
                       "replace": "\treturn len(s.items)"}],
            "summary": "Size 多算了 1"},
            "go")
        self.assertIn("+\treturn len(s.items)", patch)
        self.assertEqual(manifest["tests"], "pass")


class TestWorkspaceBackends(unittest.TestCase):
    """阶段四 4.3：local/container/remote 三档统一接口的契约测试。"""

    def _repo(self, tmp):
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "m.py").write_text("def value():\n    return 1\n",
                                   encoding="utf-8", newline="\n")
        (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8",
                                         newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    def test_local_roundtrip_diff_and_close(self):
        from agent.workspace import open_workspace
        tmp = tmpspace.create(prefix="ws-local-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        out = tmp / "task"
        ws = open_workspace("", repo, out)
        self.assertEqual(ws.backend, "local")
        ws.prepare()
        self.assertTrue(ws.exists("m.py"))
        self.assertFalse(ws.exists("nope.py"))
        self.assertIn("return 1", ws.read_text("m.py"))
        ws.write_text("m.py", "def value():\n    return 2\n")
        res = ws.apply_blocks([{"path": "m.py", "search": "return 2",
                                "replace": "return 3"}])
        self.assertEqual(res["errors"], [])
        self.assertIn("return 3", ws.read_text("m.py"))
        bad = ws.apply_blocks([{"path": "../escape.py", "search": "",
                                "replace": "x"}])
        self.assertTrue(bad["errors"], "越界路径必须拒绝")
        rc, patch, _err = ws.diff()
        self.assertEqual(rc, 0)
        self.assertIn("+++ b/m.py", patch)
        self.assertIn("+    return 3", patch)
        ws.close()
        self.assertFalse((out / "wt").exists(), "close 后工作树必须移除")

    def test_unknown_spec_does_not_fall_back_to_local(self):
        from agent.workspace import open_workspace, WorkspaceError
        tmp = tmpspace.create(prefix="ws-spec-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        with self.assertRaises(WorkspaceError) as ctx:
            open_workspace("docker:whatever", repo, tmp / "out")
        self.assertEqual(ctx.exception.code, 2)

    def test_remote_command_construction(self):
        """无真实远端：假 ssh 传输验证命令拼装（不冒充真机实跑）。"""
        from agent.workspace import open_workspace, RemoteWorkspace

        class FakeRemote(RemoteWorkspace):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.calls = []

            def _subprocess(self, argv, timeout=600, input_text=None):
                self.calls.append((list(argv), input_text))
                return 0, "python3\n", ""

        tmp = tmpspace.create(prefix="ws-remote-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        out = tmp / "task"
        ws = open_workspace("remote:host.example:22", repo, out)
        self.assertIsInstance(ws, RemoteWorkspace)
        self.assertEqual(ws.backend, "remote")
        self.assertEqual(ws.target, "host.example:22")
        self.assertEqual(ws.ssh_cmd[:2], ["ssh", "-o"])
        self.assertIn("BatchMode=yes", ws.ssh_cmd)
        fake = FakeRemote(repo, out, "host:22")
        fake.prepare()
        self.assertEqual(fake.python, "python3")
        rc, _out, _err = fake.run(["python3", "-c", "print('a b')"])
        self.assertEqual(rc, 0)
        script = fake.calls[-1][0][-1]
        self.assertIn("python3 -c", script)
        self.assertIn("'a b'", script, "参数必须经 shlex 引用，空格不丢")
        self.assertTrue(script.startswith("cd "))
        self.assertEqual(fake.workspace_dir, fake.remote_wt)
        self.assertEqual(fake.baseline_dir, fake.remote_repo)

    def test_container_matches_local_when_docker_present(self):
        """容器档真实跑（本机无 docker/镜像时跳过，CI 不假绿）。"""
        image = os.environ.get("CRA_TEST_IMAGE", "cra-pytest:3.12")
        probe = subprocess.run(["docker", "image", "inspect", image],
                               shell=False, capture_output=True, text=True)
        if probe.returncode != 0:
            self.skipTest("无 docker 或镜像 %s" % image)
        from agent.workspace import open_workspace
        tmp = tmpspace.create(prefix="ws-container-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        out = tmp / "task"
        ws = open_workspace("container:" + image, repo, out)
        ws.prepare()
        try:
            self.assertEqual(ws.backend, "container")
            self.assertIn("return 1", ws.read_text("m.py"))
            ws.write_text("m.py", "def value():\n    return 7\n")
            res = ws.apply_blocks([{"path": "m.py", "search": "return 7",
                                    "replace": "return 8"}])
            self.assertEqual(res["errors"], [])
            rc, out_text, err = ws.run(
                [ws.python, "-c",
                 "import pathlib;print(pathlib.Path('m.py')"
                 ".read_text().strip())"])
            self.assertEqual(rc, 0, err)
            self.assertIn("return 8", out_text)
            rc, patch, _err = ws.diff()
            self.assertEqual(rc, 0)
            self.assertIn("+    return 8", patch)
            info = ws.describe(probe=True)
            self.assertEqual(info["backend"], "container")
            self.assertTrue(info.get("python_version"))
        finally:
            ws.close()


class TestReviewLoop(unittest.TestCase):
    """阶段四 4.4：自评/他评差异量化与阈值转人工的契约测试。"""

    def _repo(self, tmp, name="repo"):
        repo = tmp / name
        repo.mkdir()
        (repo / "agg.py").write_text(
            "def total(items):\n    return sum(items)\n",
            encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    def _patch(self, body_lines):
        old = sum(1 for line in body_lines if line.startswith((" ", "-")))
        new = sum(1 for line in body_lines if line.startswith((" ", "+")))
        return ("diff --git a/agg.py b/agg.py\n--- a/agg.py\n+++ b/agg.py\n"
                "@@ -1,%d +1,%d @@\n%s\n"
                % (old, new, "\n".join(body_lines)))

    def _apply(self, repo, patch):
        p = repo.parent / "p.patch"
        p.write_text(patch, encoding="utf-8", newline="\n")
        subprocess.run(["git", "-C", str(repo), "apply", str(p)],
                       shell=False, capture_output=True, check=True)

    def test_parse_patch_added_lines(self):
        from agent.review_loop import parse_patch
        patch = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                 "@@ -1,2 +1,3 @@\n x = 1\n+y = 2\n z = 3\n")
        files = parse_patch(patch)
        self.assertEqual(list(files), ["a.py"])
        self.assertEqual(files["a.py"]["added"], [2])

    def test_match_findings_tolerance_and_rate(self):
        from agent.review_loop import match_findings
        own = [{"file": "a.py", "line": 10, "rule": "self:x"}]
        ext = [{"file": "a.py", "line": 11, "rule": "ruff:F401"}]
        m = match_findings(own, ext, line_tol=2)
        self.assertEqual(m["matched"], 1)
        self.assertEqual(m["union"], 1)
        self.assertEqual(m["diff_rate"], 0.0)
        far = [{"file": "a.py", "line": 20, "rule": "ruff:F401"}]
        m2 = match_findings(own, far, line_tol=2)
        self.assertEqual(m2["matched"], 0)
        self.assertEqual(m2["diff_rate"], 1.0)
        self.assertEqual(len(m2["external_only"]), 1)
        self.assertEqual(len(m2["self_only"]), 1)

    @unittest.skipUnless(shutil.which("ruff") or (
        ROOT / ".venv" / "Scripts" / "ruff.exe").is_file() or (
        ROOT / ".venv" / "bin" / "ruff").is_file(),
        "ruff 不可用（他评臂无法运行）")
    def test_clean_passes_seeded_blocks(self):
        from agent.review_loop import run_review
        tmp = tmpspace.create(prefix="review-loop-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        clean = self._patch([" def total(items):", "     return sum(items)",
                             "+", "+", "+def mean(items):",
                             "+    return sum(items) / 2"])
        self._apply(repo, clean)
        res = run_review(repo, clean, reviewers=["self", "ruff"],
                         threshold=0.5, out_dir=tmp / "out")
        self.assertEqual(res["decision"], "PASS",
                         json.dumps(res["reasons"], ensure_ascii=False))
        self.assertTrue((tmp / "out" / "review.json").is_file())
        # 植入缺陷：未用导入 + == None（测试仍能过，规则必须抓住）
        repo2 = self._repo(tmp, name="repo2")
        seeded = self._patch(["+import os", "+", "+",
                              " def total(items):",
                              "     return sum(items)",
                              "+", "+", "+def bad(items):",
                              "+    if items == None:",
                              "+        return 0"])
        self._apply(repo2, seeded)
        res2 = run_review(repo2, seeded, reviewers=["self", "ruff"],
                          threshold=0.5)
        self.assertEqual(res2["decision"], "NEED_HUMAN")
        self.assertGreater(res2["metrics"]["diff_rate"], 0.5)
        rules = {f["rule"] for f in res2["external_findings"]}
        self.assertIn("ruff:F401", rules)
        self.assertIn("ruff:E711", rules)

    def test_all_external_unavailable_needs_human(self):
        from agent.review_loop import run_review
        if shutil.which("ocr"):
            self.skipTest("环境含 ocr，无法构造不可用臂")
        tmp = tmpspace.create(prefix="review-unavail-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        patch = self._patch([" def total(items):", "+X = 1",
                             "     return sum(items)"])
        self._apply(repo, patch)
        res = run_review(repo, patch, reviewers=["self", "ocr"],
                         threshold=0.5, ocr_exe="")
        self.assertEqual(res["decision"], "NEED_HUMAN")
        self.assertEqual(res["external_status"][0]["status"], "unavailable")
        self.assertIn("不可用", " ".join(res["reasons"]))

    @unittest.skipUnless(shutil.which("ruff") or (
        ROOT / ".venv" / "Scripts" / "ruff.exe").is_file() or (
        ROOT / ".venv" / "bin" / "ruff").is_file(),
        "ruff 不可用（他评臂无法运行）")
    def test_high_severity_blocks_even_without_diff(self):
        """两臂一致命中也必须阻断：差异小 != 补丁干净。"""
        from agent.review_loop import run_review
        tmp = tmpspace.create(prefix="review-high-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        patch = self._patch(["+def broken(:", "+", "+",
                             " def total(items):",
                             "     return sum(items)"])
        self._apply(repo, patch)
        res = run_review(repo, patch, reviewers=["self", "ruff"],
                         threshold=0.5)
        self.assertEqual(res["decision"], "NEED_HUMAN")
        self.assertEqual(res["metrics"]["diff_rate"], 0.0,
                         "自评/他评应在同一处命中（差异率为 0）")
        self.assertTrue(res["high_findings"], "语法错误必须记高严重度")

    def test_command_reviewer_protocol(self):
        from agent.review_loop import run_review
        tmp = tmpspace.create(prefix="review-cmd-")
        self.addCleanup(tmpspace.release, tmp)
        repo = self._repo(tmp)
        patch = self._patch([" def total(items):", "+X = 1",
                             "     return sum(items)"])
        self._apply(repo, patch)
        script = tmp / "reviewer.py"
        script.write_text(
            "import json, os\n"
            "assert os.environ.get('CRA_REVIEW_PATCH')\n"
            "print(json.dumps({'findings': [{'file': 'agg.py', 'line': 2,\n"
            "  'rule': 'stub:x', 'severity': 'medium', 'message': 'm'}]}))\n",
            encoding="utf-8", newline="\n")
        res = run_review(repo, patch, reviewers=["self"], threshold=0.5,
                         reviewer_cmds={"stub": '"%s" "%s"'
                                        % (VENV_PY, script)})
        self.assertEqual(res["external_status"][0]["name"], "stub")
        self.assertEqual(res["external_status"][0]["status"], "ok")
        self.assertEqual(len(res["external_findings"]), 1)
        self.assertEqual(res["decision"], "NEED_HUMAN")


class TestReviewGateWiring(unittest.TestCase):
    """code-task --review 收口接线：评审检出干净、PASS 落 review.json。"""

    def test_review_gate_checks_out_and_cleans_up(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_review_gate", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = tmpspace.create(prefix="review-gate-")
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("X = 1\n", encoding="utf-8", newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        out = tmp / "out"
        out.mkdir()
        patch = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                 "@@ -1 +1,2 @@\n X = 1\n+Y = 2\n")
        (out / "edits.patch").write_text(patch, encoding="utf-8",
                                         newline="\n")
        res = mod._review_gate(repo, out, patch, ["self"], 0.5, {}, "",
                               self_tests="pass")
        self.assertEqual(res["decision"], "PASS")
        self.assertTrue((out / "review.json").is_file())
        self.assertFalse((out / "review-wt").exists(),
                         "评审检出必须清理，不残留工作树")

    def _make_repo(self, tmp):
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "a.py").write_text("X = 1\n", encoding="utf-8",
                                   newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    def test_review_gate_missing_patch_raises_review_error(self):
        """缺少 edits.patch 必须抛 ReviewError，不得静默当通过。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_review_gate_miss", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = Path(tmpspace.create(prefix="review-gate-miss-"))
        self.addCleanup(tmpspace.release, tmp)
        repo = self._make_repo(tmp)
        out = tmp / "out"
        out.mkdir()
        with self.assertRaises(mod.ReviewError):
            mod._review_gate(repo, out, "", ["self"], 0.5, {}, "",
                             self_tests="pass")

    def test_review_gate_apply_failure_raises_and_cleans_up(self):
        """交付补丁在干净检出上应用失败必须抛 ReviewError 且清理 worktree。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_review_gate_apply", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = Path(tmpspace.create(prefix="review-gate-apply-"))
        self.addCleanup(tmpspace.release, tmp)
        repo = self._make_repo(tmp)
        out = tmp / "out"
        out.mkdir()
        bad = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
               "@@ -1 +1,2 @@\n-NOPE_DIFFERENT_CONTEXT\n+Y = 2\n")
        (out / "edits.patch").write_text(bad, encoding="utf-8",
                                         newline="\n")
        with self.assertRaises(mod.ReviewError):
            mod._review_gate(repo, out, bad, ["self"], 0.5, {}, "",
                             self_tests="pass")
        self.assertFalse((out / "review-wt").exists(),
                         "应用失败也必须清理评审检出")

    def test_review_gate_not_a_git_repo_raises_review_error(self):
        """评审检出 git worktree 失败必须抛 ReviewError（不得静默通过）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_review_gate_nogit", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tmp = Path(tmpspace.create(prefix="review-gate-nogit-"))
        self.addCleanup(tmpspace.release, tmp)
        repo = tmp / "repo-not-git"
        repo.mkdir()
        out = tmp / "out"
        out.mkdir()
        patch = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
                 "@@ -1 +1,2 @@\n X = 1\n+Y = 2\n")
        (out / "edits.patch").write_text(patch, encoding="utf-8",
                                         newline="\n")
        with self.assertRaises(mod.ReviewError):
            mod._review_gate(repo, out, patch, ["self"], 0.5, {}, "",
                             self_tests="pass")

    def test_parse_review_cmds_contract(self):
        """_parse_review_cmds：name=command 解析、缺 = 必须抛 ReviewError。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "code_task_review_cmds", AGENT / "code-task.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod._parse_review_cmds(None), {})
        self.assertEqual(mod._parse_review_cmds(["ok=ls -la"]),
                         {"ok": "ls -la"})
        self.assertEqual(mod._parse_review_cmds(["a=b=c"]), {"a": "b=c"})
        with self.assertRaises(mod.ReviewError):
            mod._parse_review_cmds(["a-no-equals"])


class TestWorkspaceFakeBackends(unittest.TestCase):
    """workspace.py 远程/容器档的公式化分支（不触真 docker/ssh 二进制）。"""

    def _repo(self, tmp):
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "m.py").write_text("X = 1\n", encoding="utf-8",
                                   newline="\n")
        for args in (["init", "-q"], ["add", "-A"],
                     ["-c", "user.name=t", "-c", "user.email=t@t",
                      "commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                           capture_output=True)
        return repo

    # ---------------- 远程（ssh 脚本）----------------
    def _remote(self, tmp, responses):
        repo = self._repo(tmp)
        from agent.workspace import RemoteWorkspace

        class FakeRemote(RemoteWorkspace):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.calls = []

            def _subprocess(self, argv, timeout=600, input_text=None):
                script = argv[-1]
                self.calls.append((script, input_text))
                for key, resp in responses:
                    if key in script:
                        return resp
                return (0, "", "")

        ws = FakeRemote(repo, tmp / "task", "host:22")
        return ws, repo

    def test_remote_prepare_happy_path_and_detect_python(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-ok-"))
        self.addCleanup(tmpspace.release, tmp)
        ws, _ = self._remote(tmp, [
            ("if [ ! -d", (0, "", "")),
            ("command -v python", (0, "python3\n", "")),
        ])
        ws.prepare()
        self.assertEqual(ws.backend, "remote")
        self.assertEqual(ws.python, "python3")
        self.assertTrue(ws._prepared)

    def test_remote_prepare_worktree_failure_raises(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-fail-"))
        self.addCleanup(tmpspace.release, tmp)
        ws, _ = self._remote(tmp, [("if [ ! -d", (1, "", "ssh denied"))])
        from agent.workspace import WorkspaceError
        with self.assertRaises(WorkspaceError):
            ws.prepare()

    def test_remote_detect_python_falls_back_to_host_default(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-pyfb-"))
        self.addCleanup(tmpspace.release, tmp)
        ws, _ = self._remote(tmp, [("command -v", (0, "", ""))])
        ws.prepare()
        self.assertEqual(ws.python, "python")

    def test_remote_read_text_failure_raises(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-rw-"))
        self.addCleanup(tmpspace.release, tmp)
        from agent.workspace import WorkspaceError
        ws, _ = self._remote(tmp, [("cat", (1, "", "no such file"))])
        ws.prepare()
        with self.assertRaises(WorkspaceError):
            ws.read_text("m.py")

    def test_remote_write_text_failure_raises(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-wr-"))
        self.addCleanup(tmpspace.release, tmp)
        from agent.workspace import WorkspaceError
        ws, _ = self._remote(tmp, [("&& cat > ", (1, "", "disk full"))])
        ws.prepare()
        with self.assertRaises(WorkspaceError):
            ws.write_text("m.py", "x = 1\n")

    def test_remote_exists_true_and_false(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-ex-"))
        self.addCleanup(tmpspace.release, tmp)
        ws, _ = self._remote(tmp, [("test -f", (0, "", ""))])
        ws.prepare()
        self.assertTrue(ws.exists("m.py"))
        sub2 = tmp / "task2"
        sub2.mkdir()
        ws2, _ = self._remote(sub2, [("test -f", (1, "", ""))])
        ws2.prepare()
        self.assertFalse(ws2.exists("m.py"))

    def test_remote_git_defaults_to_worktree_not_repo(self):
        tmp = Path(tmpspace.create(prefix="wsf-remote-git-"))
        self.addCleanup(tmpspace.release, tmp)
        ws, _ = self._remote(tmp, [("git -C", (0, "", ""))])
        ws.prepare()
        rc, _out, _err = ws._git(["status", "--porcelain"])
        self.assertEqual(rc, 0)
        script = ws.calls[-1][0]
        self.assertIn("/wt", script, "git 默认应发往 worktree")

    # ---------------- 容器（docker 子命令）----------------
    def _docker(self, tmp, responses):
        repo = self._repo(tmp)
        from agent.workspace import ContainerWorkspace

        class FakeContainer(ContainerWorkspace):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.calls = []

            def _subprocess(self, argv, timeout=600, input_text=None):
                args = list(argv[1:])
                self.calls.append((args, input_text))
                for key, resp in responses:
                    if key in " ".join(args):
                        return resp
                return (0, "", "")

        ws = FakeContainer(repo, tmp / "task", "fake-image:latest")
        return ws

    def test_container_running_short_circuits(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-run-"))
        self.addCleanup(tmpspace.release, tmp)
        ws = self._docker(tmp, [("inspect", (0, "true\n", "")),
                                ("command -v", (0, "/usr/bin/python\n", ""))])
        ws.prepare()
        self.assertIn("inspect", " ".join(ws.calls[0][0]))
        self.assertFalse(any(c[0] and c[0][0] == "run" for c in ws.calls),
                         "容器已在运行时不得再次 docker run")

    def test_container_create_run_and_detect_python(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-create-"))
        self.addCleanup(tmpspace.release, tmp)
        ws = self._docker(tmp, [
            ("inspect", (1, "", "no such image")),
            ("rm -f", (0, "", "")),
            ("run -d", (0, "container-id\n", "")),
            ("exec", (0, "true\n", "")),
            ("command -v python", (0, "/usr/bin/python\n", "")),
        ])
        ws.prepare()
        self.assertEqual(ws.backend, "container")
        self.assertTrue(any(c[0][:2] == ["run", "-d"] for c in ws.calls))
        ws.run(["python", "-V"])
        last = ws.calls[-1][0]
        self.assertIn("sh", last)

    def test_container_run_failure_raises(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-fail-"))
        self.addCleanup(tmpspace.release, tmp)
        from agent.workspace import WorkspaceError
        ws = self._docker(tmp, [
            ("inspect", (1, "", "no such")),
            ("run -d", (1, "", "port in use")),
        ])
        with self.assertRaises(WorkspaceError):
            ws.prepare()

    def test_container_exec_failure_closes_container(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-execfail-"))
        self.addCleanup(tmpspace.release, tmp)
        from agent.workspace import WorkspaceError
        ws = self._docker(tmp, [
            ("inspect", (1, "", "no such")),
            ("run -d", (0, "cid\n", "")),
            ("exec", (1, "", "daemon crashed")),
        ])
        with self.assertRaises(WorkspaceError):
            ws.prepare()
        self.assertTrue(any(c[0][:2] == ["rm", "-f"] for c in ws.calls),
                        "exec 失败必须闭包清理容器")

    def test_container_read_write_exists_happy_path(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-rw-"))
        self.addCleanup(tmpspace.release, tmp)
        ws = self._docker(tmp, [
            ("inspect", (0, "true\\n", "")),
            ("command -v", (0, "/usr/bin/python\\n", "")),
            ("exec", (0, "X = 1\\n", "")),
        ])
        ws.prepare()
        self.assertEqual(ws.read_text("m.py"), "X = 1\\n")
        self.assertTrue(ws.exists("m.py"))
        ws.write_text("m.py", "X = 2\\n")
        ws.run_in("/", ["true"])

    def test_container_exists_false_and_run_in_cwd(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-ex2-"))
        self.addCleanup(tmpspace.release, tmp)
        ws = self._docker(tmp, [
            ("inspect", (0, "true\\n", "")),
            ("command -v", (0, "/usr/bin/python\\n", "")),
            ("test -f", (1, "", "")),
        ])
        ws.prepare()
        self.assertFalse(ws.exists("nope.py"))
        ws.run_in("/app", ["ls", "-la"])

    def test_container_detect_python_defaults_to_python(self):
        tmp = Path(tmpspace.create(prefix="wsf-ctr-pydef-"))
        self.addCleanup(tmpspace.release, tmp)
        ws = self._docker(tmp, [
            ("inspect", (0, "true\n", "")),
            ("command -v", (1, "", "not found")),
        ])
        ws.prepare()
        self.assertEqual(ws.python, "python")


class TestParseResponseMultiObject(unittest.TestCase):
    """round-77：多 JSON 对象响应解析（DeepSeek JSON 模式实跑暴露的形态）。"""

    def test_parse_response_tolerates_multi_object(self):
        mod = load_agent_script("code-task.py")
        self.assertEqual(mod._parse_response('{"action":"read","files":["a.py"]}')["action"], "read")
        self.assertEqual(mod._parse_response('```json\n{"action":"done"}\n```')["action"], "done")
        double = '{"action":"search","query":"x"}\n{"action":"edit","edits":[]}'
        self.assertEqual(mod._parse_response(double)["action"], "edit")
        self.assertIsNone(mod._parse_response('{"a":1'))
        self.assertIsNone(mod._parse_response(""))

    def test_parse_response_prefers_last_object(self):
        mod = load_agent_script("code-task.py")
        text = ('{"action":"search","query":"keep"}\n先想后答\n'
                '{"action":"done","summary":"final"}')
        self.assertEqual(mod._parse_response(text)["action"], "done")


class TestOpenAIProviderJSONMode(unittest.TestCase):
    """round-77：openai 兼容端点的 JSON 模式门控与空内容重试（DeepSeek 实跑暴露）。"""

    def setUp(self):
        self._backup = {}
        env = os.environ
        for key in ("REVIEW_LLM_BASE_URL", "REVIEW_LLM_MODEL",
                    "REVIEW_LLM_API_KEY", "REVIEW_LLM_JSON_MODE",
                    "CRA_LLM_PROVIDER"):
            self._backup[key] = env.pop(key, None)
        env["REVIEW_LLM_BASE_URL"] = "https://api.example.com"
        env["REVIEW_LLM_MODEL"] = "test-model"

    def tearDown(self):
        env = os.environ
        for key, val in self._backup.items():
            if val is None:
                env.pop(key, None)
            else:
                env[key] = val

    def _patch_urlopen(self, responses):
        import urllib.request as _ur
        import io as _io
        captured = {}
        state = {"n": 0}

        def fake(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = req.data
            captured["auth"] = req.headers.get("Authorization")
            payload = responses[min(state["n"], len(responses) - 1)]
            state["n"] += 1
            return _io.BytesIO(payload)

        orig = _ur.urlopen
        _ur.urlopen = fake
        self.addCleanup(setattr, _ur, "urlopen", orig)
        return captured, state

    def test_json_mode_env_gates_response_format(self):
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        import llm.provider as prov
        resp = (b'{"choices":[{"message":{"content":"{\\"action\\":\\"done\\"}"}}],'
                b'"usage":{"total_tokens":7}}')
        captured, state = self._patch_urlopen([resp])
        # JSON 模式关闭：请求体不得带 response_format
        out, meta = prov._openai_complete("s", "u", {}, None)
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertNotIn("response_format", body)
        self.assertEqual(out, '{"action":"done"}')
        # JSON 模式开启：请求体带 response_format=json_object
        os.environ["REVIEW_LLM_JSON_MODE"] = "1"
        out2, meta2 = prov._openai_complete("s", "u", {}, None)
        body2 = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual(body2["response_format"], {"type": "json_object"})
        self.assertEqual(out2, '{"action":"done"}')

    def test_empty_content_retries_then_succeeds(self):
        import sys as _sys
        if str(ROOT) not in _sys.path:
            _sys.path.insert(0, str(ROOT))
        import llm.provider as prov
        empty = b'{"choices":[{"message":{"content":"  "}}],"usage":{}}'
        good = (b'{"choices":[{"message":{"content":"{\\"action\\":\\"read\\"}"}}],'
                b'"usage":{"total_tokens":9}}')
        captured, state = self._patch_urlopen([empty, good])
        out, meta = prov._openai_complete(
            "s", "u", {"retry_backoff_base_seconds": 0}, None)
        self.assertEqual(out, '{"action":"read"}')
        self.assertEqual(state["n"], 2, "空内容必须按可重试失败处理")
        body = json.loads(captured["body"].decode("utf-8"))
        self.assertEqual(body["messages"][0]["role"], "system")


class TestProtocolNotes(unittest.TestCase):
    """round-78：协议提示附录产品化（--protocol-notes）。"""

    def test_apply_protocol_notes_appends_content(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="protocol-notes-")
        self.addCleanup(tmpspace.release, tmp)
        notes = Path(tmp) / "notes.md"
        notes.write_text("## Protocol notes\n- budget: 24 rounds\n",
                         encoding="utf-8", newline="\n")
        task = "Fix the bug."
        merged = mod._apply_protocol_notes(task, str(notes))
        self.assertTrue(merged.startswith("Fix the bug.\n\n## Protocol notes"))
        self.assertIn("budget: 24 rounds", merged)

    def test_apply_protocol_notes_missing_file_is_error(self):
        mod = load_agent_script("code-task.py")
        with self.assertRaises(ValueError):
            mod._apply_protocol_notes("task", str(AGENT / "no-such-notes.md"))

    def test_apply_protocol_notes_empty_file_keeps_task(self):
        mod = load_agent_script("code-task.py")
        tmp = tmpspace.create(prefix="protocol-notes-empty-")
        self.addCleanup(tmpspace.release, tmp)
        notes = Path(tmp) / "empty.md"
        notes.write_text("  \n", encoding="utf-8", newline="\n")
        self.assertEqual(mod._apply_protocol_notes("keep", str(notes)), "keep")

    def test_protocol_notes_example_file_shipped(self):
        example = AGENT / "protocol-notes-example.md"
        self.assertTrue(example.is_file(), "--protocol-notes 样例模板须入仓")
        text = example.read_text(encoding="utf-8")
        self.assertIn("Protocol notes", text)
        self.assertIn("failing tests", text)


if __name__ == "__main__":
    unittest.main()
