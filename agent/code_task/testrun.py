#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓库测试发现与执行（pytest/go/node，按仓库自动识别引擎）。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from agent.repo_map import (find_sibling_test_paths)  # noqa: E402
from agent.workspace import open_workspace, WorkspaceError  # noqa: E402
from agent.code_task.selfcheck import _no_bytecode_env
from agent.code_task.tools import _pytest_exe


def _discover_test_paths(worktree, max_paths=40):
    """发现测试入口：仓库根的 test_*.py / tests/ 优先，否则包内 tests/ 目录。

    sympy/astropy/scikit-learn 的测试在包内（sympy/**/tests/），只查仓库根
    会误判「无测试」而把验收闸整体跳过（round-18 实踩：三个实例的测试一律
    skip）。包内目录有界取用，避免全树收集。
    """
    roots = sorted(p for p in worktree.glob("test_*.py") if p.is_file())
    if roots:
        return roots[:max_paths]
    tdir = worktree / "tests"
    if tdir.is_dir():
        return [tdir]
    found = []
    for path in worktree.rglob("tests"):
        if path.is_dir():
            found.append(path)
            if len(found) >= max_paths:
                break
    return found


def _pytest_run(exe, worktree, paths, timeout=600, ws=None):
    """跑一次 pytest → (status, detail 末 8 行)。

    ws 非空时在对应后端执行（容器/远端），测试路径转成工作区相对路径——
    宿主上的绝对路径在容器里不存在。
    """
    if ws is not None:
        root = Path(worktree).resolve()
        rels = []
        for p in paths:
            try:
                rels.append(Path(p).resolve().relative_to(root).as_posix())
            except (ValueError, OSError):
                rels.append(str(p).replace("\\", "/"))
        try:
            rc, out, err = ws.run([exe, "-m", "pytest", "-q"] + rels,
                                  timeout=timeout)
        except WorkspaceError as exc:
            return "skip", ["工作区测试引擎不可用：%s" % str(exc)[:200]]
        merged = (out or "") + "\n" + (err or "")
        tail = [l for l in merged.strip().splitlines() if l][-8:]
        return ("pass" if rc == 0 else "fail"), tail
    proc = subprocess.run(
        [exe, "-m", "pytest", "-q"] + [str(p) for p in paths],
        shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, cwd=str(worktree),
        env=_no_bytecode_env(worktree))
    tail = [l for l in (proc.stdout or "").strip().splitlines() if l][-8:]
    return ("pass" if proc.returncode == 0 else "fail"), tail


_NODE_TEST_RE = re.compile(r"\.(?:test|spec)\.(?:ts|tsx|js|jsx|mjs|cjs)$")


ENGINE_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".cache", "vendor", "site-packages",
}


def _find_exe(name, env_key):
    """外部测试工具：环境变量显式路径优先（离线机器不在 PATH），其次 PATH。"""
    cand = (os.environ.get(env_key) or "").strip()
    if cand and Path(cand).is_file():
        return cand
    return shutil.which(name) or ""


def _discover_node_tests(root, max_paths=20):
    """Node 内置测试器的入口文件（*.test.ts/js、*.spec.ts/js；有界）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in ENGINE_SKIP_DIRS)
        for name in sorted(filenames):
            if _NODE_TEST_RE.search(name):
                out.append((Path(dirpath) / name).relative_to(root).as_posix())
                if len(out) >= max_paths:
                    return out
    return out


def _split_cmdline(command):
    """命令串拆分：Windows 用 posix=False（反斜杠路径不被 shlex 吃掉）。"""
    if os.name == "nt":
        return [p.strip('"') for p in shlex.split(command, posix=False)]
    return shlex.split(command, posix=True)


def _detect_test_engine(worktree, test_cmd=""):
    """识别仓库测试引擎 → {"engine", "argv", "note"}；都不命中返回 None。

    顺序：--test-cmd 显式覆盖 > go.mod > package.json > Python(pytest)。
    npm 在 Windows 上是 npm.cmd，shell=False 起不来——经 COMSPEC /c 转一层。
    """
    root = Path(worktree)
    if test_cmd:
        return {"engine": "cmd", "argv": _split_cmdline(test_cmd),
                "note": test_cmd}
    if (root / "go.mod").is_file():
        exe = _find_exe("go", "CRA_GO") or "go"
        return {"engine": "go", "argv": [exe, "test", "./..."],
                "note": "go.mod → go test ./..."}
    pkg = root / "package.json"
    if pkg.is_file():
        scripts = {}
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get(
                "scripts") or {}
        except (OSError, ValueError):
            scripts = {}
        if scripts.get("test"):
            exe = _find_exe("npm", "CRA_NPM") or "npm"
            argv = [exe, "test"]
            if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
                argv = [os.environ.get("COMSPEC", "cmd.exe"), "/c"] + argv
            return {"engine": "npm", "argv": argv,
                    "note": "package.json scripts.test → npm test"}
        node_tests = _discover_node_tests(root)
        if node_tests:
            exe = _find_exe("node", "CRA_NODE") or "node"
            return {"engine": "node",
                    "argv": [exe, "--experimental-strip-types", "--test"]
                            + node_tests,
                    "note": "Node 内置测试器（%d 个 *.test.*）"
                            % len(node_tests)}
    if _discover_test_paths(root):
        return {"engine": "pytest", "argv": [], "note": "pytest"}
    return None


def _engine_run(engine, worktree, timeout=600, ws=None):
    """跑一次非 pytest 引擎 → (status, detail 末 8 行)。ws 非空则在后端执行。"""
    if ws is not None:
        try:
            rc, out, err = ws.run(engine["argv"], timeout=timeout)
        except WorkspaceError as exc:
            raise FileNotFoundError(str(exc))
    else:
        proc = subprocess.run(
            engine["argv"], shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            cwd=str(worktree), env=_no_bytecode_env(worktree))
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    merged = (out or "") + "\n" + (err or "")
    tail = [l for l in merged.strip().splitlines() if l][-8:]
    return ("pass" if rc == 0 else "fail"), tail


def _select_test_paths(worktree, edited_paths, limit=20):
    """改动文件 → 相关测试文件（round-53，2.4）。

    只走 A（同名测试）与 B（目录段映射）两路，**不做 C 路内容扫描**——编码
    循环每轮编辑后都要判一次，扫 tests/ 全树太贵；映射不出就由调用方回退
    全量（漏测的兜底是「全量」，不是「猜」）。改的本身是测试文件时直接选中。
    """
    root = Path(worktree)
    picked = []
    for rel in (edited_paths or [])[:10]:
        rel = str(rel).replace("\\", "/")
        if not rel.endswith(".py"):
            continue
        name = rel.rsplit("/", 1)[-1]
        if "/tests/" in rel or rel.startswith("tests/") \
                or name.startswith("test_"):
            if rel not in picked:
                picked.append(rel)
            continue
        for path, _marker in find_sibling_test_paths(
                root, rel, limit=3, content_fallback=False):
            key = path.relative_to(root).as_posix()
            if key not in picked:
                picked.append(key)
    return picked[:limit]


def _run_tests(worktree, edited_paths=None, audit_seed="", test_cmd="",
               info=None, ws=None):
    """跑仓库测试；返回 (status, detail)。

    引擎识别（阶段四 4.2）：--test-cmd 显式覆盖 > go.mod（go test ./...）>
    package.json（scripts.test → npm test；否则 Node 内置测试器跑
    *.test.ts/js）> pytest。非 pytest 引擎跑全命令、不做子集映射；detail
    首行标注引擎，下游不得把一种引擎的结果冒充另一种。`info` 非空时回填
    {"engine": ...} 供 manifest 记录。

    pytest 保持 round-53（2.4）口径：给出本次改动文件时先跑映射到的相关
    测试子集；子集失败再回退全量（区分「改动真坏了」与「原本就有别的
    失败」）。detail 首行标注范围，避免把子集通过冒充全量通过。

    漏测抽检：子集通过仍可能掩盖「改动破坏了子集之外的测试」。给 audit_seed
    （调用方传轮次+改动文件，确定性可复算）时，约 1/3 的通过轮次再跑一次全量
    作金标准；抽检未过按 fail 返回（隐藏回归），并在 detail 标注。未抽检的
    通过也在标注里写明「未抽检」，下游不得当全量通过解读。
    """
    engine = _detect_test_engine(worktree, test_cmd)
    if engine is None:
        return "skip", ["仓库无测试"]
    if info is not None:
        info["engine"] = engine["engine"]
    ws_tag = ""
    if ws is not None:
        ws_tag = "（工作区 %s）" % (ws.image or ws.target or ws.backend)
    if engine["engine"] != "pytest":
        try:
            status, detail = _engine_run(engine, worktree, ws=ws)
        except FileNotFoundError as exc:
            return "skip", ["环境无测试引擎可执行文件：%s" % str(exc)[:160]]
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "skip", ["引擎 %s 不可用：%s" % (engine["engine"],
                                                  str(exc)[:160])]
        return status, ["引擎 %s（%s）%s"
                        % (engine["engine"], engine["note"], ws_tag)] \
            + detail
    test_paths = _discover_test_paths(worktree)
    if not test_paths:
        return "skip", ["仓库无测试"]
    if ws is not None:
        exe = ws.python
    else:
        exe = _pytest_exe()
        if exe is None:
            return "skip", ["环境无 pytest"]
    subset = _select_test_paths(worktree, edited_paths or [])
    if subset:
        status, detail = _pytest_run(exe, worktree, subset, ws=ws)
        scope = "子集 %d 项（原范围 %d 项）%s" % (len(subset), len(test_paths),
                                                   ws_tag)
        if status != "pass":
            full_status, full_detail = _pytest_run(exe, worktree, test_paths,
                                                   ws=ws)
            return full_status, [
                "%s 未过，已回退全量（%s）" % (scope, full_status)] + full_detail
        audited = bool(audit_seed) and (
            hashlib.sha1(audit_seed.encode("utf-8")).digest()[0] % 3 == 0)
        if audited:
            full_status, full_detail = _pytest_run(exe, worktree, test_paths,
                                                   ws=ws)
            if full_status != "pass":
                return full_status, [
                    "%s 通过但全量抽检未过（隐藏回归，按 fail 处理）"
                    % scope] + full_detail
            return status, ["%s：%s；全量抽检通过"
                            % (scope, "; ".join(detail))]
        return status, ["%s：%s（未抽检）" % (scope, "; ".join(detail))]
    status, detail = _pytest_run(exe, worktree, test_paths, ws=ws)
    if ws is not None:
        detail = ["工作区 %s（%s）" % (ws.backend,
                                      ws.image or ws.target or "本机")] + detail
    return status, detail
