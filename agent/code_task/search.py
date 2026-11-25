#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""有界字面搜索、目录树列举、行为探针（扩大权限动作）。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import base64
import fnmatch
import json
import os
import re
import subprocess
from agent.workspace import open_workspace, WorkspaceError  # noqa: E402
from agent.code_task.selfcheck import _no_bytecode_env, _redact_snippet


SEARCH_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build",
    "dist", ".eggs", "site-packages", ".idea", ".vscode",
}


SEARCH_TEXT_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".c",
    ".h", ".cc", ".cpp", ".hpp", ".rb", ".rs", ".cs", ".php", ".md", ".rst",
    ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".sh",
    ".bash", ".sql", ".html", ".css", ".vue",
}


_DEF_NAME_RE = re.compile(
    r"^\s*(?:(?:export|default|async|public|private|protected|static|"
    r"abstract)\s+)*(?:def|class|function|interface|type|func)\s+"
    r"([A-Za-z_]\w*)")


def _search_kind(line, needle):
    """命中行分类：0=定义、1=引用、2=注释（越小越靠前，2.2）。

    定义行优先的理由：模型搜一个符号时想找的是「它定义在哪」，而不是
    「哪里提到过它」；注释行最后，因为注释里的名字不承载可执行语义。
    """
    match = _DEF_NAME_RE.match(line)
    if match and match.group(1).casefold() == needle:
        return 0
    stripped = line.lstrip()
    pos = line.casefold().find(needle)
    hash_pos = line.find("#")
    slash_pos = line.find("//")
    if stripped.startswith("#") or stripped.startswith("//") or (
            hash_pos != -1 and pos != -1 and hash_pos < pos) or (
            slash_pos != -1 and pos != -1 and slash_pos < pos):
        return 2
    return 1


def _path_distance(rel, near):
    """文件到候选文件的路径距离（目录段差异数；无候选时 99）。

    同一名字在仓库里出现几十次时，靠近候选文件的引用更可能是相关代码
    （2.2 的第二排序键，只在同 kind 内生效）。
    """
    if not near:
        return 99
    base = Path(str(rel)).parent.parts
    best = 99
    for other in near:
        parts = Path(str(other)).parent.parts
        common = 0
        for left, right in zip(base, parts):
            if left != right:
                break
            common += 1
        dist = (len(base) - common) + (len(parts) - common)
        if dist < best:
            best = dist
    return best


def _search_repo(src, query, glob="", max_hits=40, max_files=2000,
                 max_file_bytes=512 * 1024, near=None):
    """在 src 内做有界字面子串搜索 → (ok, 观察文本)。

    输出 `相对路径:行号: 行内容`；不进入跳过目录，不读二进制扩展名与超大
    文件；命中行经 _redact_snippet 脱敏后截断 200 字。

    round-53（2.2）改变 **排序**：先收至多 max_hits×10 处，再按
    「定义 > 引用 > 注释」→「与候选文件的路径距离」→ 路径/行号 稳定排序，
    最后取前 max_hits。旧实现按遍历顺序截断到 40 处，定义点经常落在截断外。
    """
    needle = (query or "").strip().casefold()
    if len(needle) < 2:
        return False, "query 至少 2 个字符（字面子串，不区分大小写）"
    if len(needle) > 200:
        return False, "query 过长（≤200 字符）"
    pattern = (glob or "").strip()
    collect_cap = max(max_hits * 10, max_hits)
    hits, scanned, truncated = [], 0, False
    near_list = [str(x).replace("\\", "/") for x in (near or [])][:8]
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SEARCH_SKIP_DIRS)
        for name in sorted(files):
            path = Path(root) / name
            if path.is_symlink():
                continue  # 不跟随符号链接：仓内链接可指向仓外文件
            if path.suffix.lower() not in SEARCH_TEXT_EXTS:
                continue
            rel = path.relative_to(src).as_posix()
            if pattern:
                target = rel if "/" in pattern else name
                if not fnmatch.fnmatch(target, pattern):
                    continue
            if scanned >= max_files:
                truncated = True
                break
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            dist = _path_distance(rel, near_list)
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line.casefold():
                    hits.append({"rel": rel, "line": lineno,
                                 "kind": _search_kind(line, needle),
                                 "dist": dist,
                                 "text": _redact_snippet(line.strip())[:200]})
                    if len(hits) >= collect_cap:
                        truncated = True
                        break
            if len(hits) >= collect_cap:
                break
        if len(hits) >= collect_cap:
            break
    if not hits:
        return True, "搜索 %r 无命中（扫描 %d 个文本文件）" % (
            _redact_snippet(query), scanned)
    hits.sort(key=lambda h: (h["kind"], h["dist"], h["rel"], h["line"]))
    shown = hits[:max_hits]
    body = "\n".join("%s:%d: %s" % (h["rel"], h["line"], h["text"])
                     for h in shown)
    if len(hits) > max_hits or truncated:
        body += "\n（已截断：上限 %d 处 / %d 文件；按定义>引用>注释与路径距离排序）" \
                % (max_hits, max_files)
    return True, "搜索 %r 命中 %d 处（扫描 %d 文件）：\n%s" % (
        _redact_snippet(query), len(shown), scanned, body)


def _probe(worktree, repo, code, timeout=60, max_chars=2000,
           docker_image=None, ws=None):
    """在临时 worktree 里跑一段探针代码 → (ok, 观察输出)。

    用途（round-28 第 3 项）：报错行只给症状，状态类缺陷（如 set_val 没同步
    移动两个 handle）要把对象状态打出来才看得见。只读为主，超时与输出截断；
    默认关闭、需 --allow-probe 显式开启（执行模型给的代码属于扩大权限，
    开不开由宿主决定）。

    docker_image 非空时改在容器内执行（升级计划阶段0）：工作区**只读**挂载到
    /testbed（探针只观测、绝不写被审代码），Python 用镜像自带环境——本地
    import 不了的仓库（matplotlib 这类编译扩展缺失）由此不再是观测盲区，
    补丁自检「基线导不进就静默跳过」的缺口在探针侧先行收口。
    """
    if not code or not code.strip():
        return False, "探针代码为空"
    if ws is not None:
        # 工作区后端优先于 --probe-docker：容器/远端用各自的解释器与依赖
        try:
            rc, out, err = ws.run([ws.python, "-c", code],
                                  timeout=max(timeout, 180))
        except WorkspaceError as exc:
            return False, str(exc)[:max_chars]
        merged = out or ""
        if err:
            merged += "\n[stderr]\n" + err
        return rc == 0, merged[-max_chars:]
    src = worktree if worktree.is_dir() else repo
    if docker_image:
        # 三个实测约束拼成的形状：
        # ①bash -lc 激活镜像 conda 环境（SWE 评测镜像的解释器在
        #   /opt/miniconda3/envs/testbed/bin/python，裸 `python` 是系统环境）；
        # ②工作区挂在 /agent-wt（只读）而非直接盖 /testbed——后者会遮掉镜像
        #   构建期编译的 C 扩展（.so），import 当场 ImportError；
        # ③进容器先 `cp -a /agent-wt/. /testbed/` 合并进可写容器层：编辑过的
        #   .py 覆盖镜像内同名文件、镜像编译的 .so 存活——探针看到的是
        #   「编辑后状态 + 可运行环境」；--rm 退出即弃，镜像与宿主都不留痕。
        # 探针代码经 base64 走 stdin，避免 shell 引号与换行双重转义。
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        argv = ["docker", "run", "--rm", "-i",
                "-v", "%s:/agent-wt:ro" % src, "-w", "/testbed",
                docker_image, "bash", "-lc",
                "cp -a /agent-wt/. /testbed/ && "
                "echo %s | base64 -d | python -" % b64]
        env, cwd, run_timeout = None, None, max(timeout, 180)
    else:
        argv = [sys.executable, "-c", code]
        env, cwd, run_timeout = _no_bytecode_env(src), str(src), timeout
    try:
        proc = subprocess.run(argv, shell=False, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=run_timeout, cwd=cwd, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:max_chars]
    out = (proc.stdout or "")
    if proc.stderr:
        out += "\n[stderr]\n" + proc.stderr
    return proc.returncode == 0, out[-max_chars:]


def _list_tree(src, rel="", depth=2, max_entries=80, max_depth=3,
               max_entries_cap=200):
    """目录树观察（round-53，2.3）→ (ok, 观察文本)。

    大仓里「文件到底在哪个子目录」靠猜路径会浪费轮次；list 只读、有界：
    限深（≤3 层）、限宽（≤200 项）、剪运行产物目录、不跟随符号链接，
    且 **路径必须落在工作区内**（绝对路径与 ../ 越界一律拒绝）。
    """
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        depth = 2
    depth = max(1, min(depth, max_depth))
    try:
        max_entries = int(max_entries)
    except (TypeError, ValueError):
        max_entries = 80
    max_entries = max(1, min(max_entries, max_entries_cap))
    base = Path(src).resolve()
    rel = str(rel or "").replace("\\", "/").strip().strip("/")
    target = (base / rel).resolve() if rel else base
    if target != base and base not in target.parents:
        return False, "路径越界：%s 不在工作区内（只允许工作区内的相对路径）" % (
            rel or ".")
    if not target.exists():
        return False, "路径不存在：%s" % (rel or ".")
    if target.is_file():
        try:
            lines = len(target.read_text(encoding="utf-8",
                                         errors="replace").splitlines())
        except OSError:
            lines = 0
        return True, "文件 %s（%d 行）" % (rel, lines)
    entries, out, stopped = 0, [], False

    def walk(folder, prefix, level):
        nonlocal entries, stopped
        if stopped or level >= depth:
            return
        try:
            children = sorted(folder.iterdir(),
                              key=lambda p: (not p.is_dir(),
                                             p.name.casefold()))
        except OSError:
            return
        for child in children:
            if stopped:
                return
            if child.is_symlink() or child.name in SEARCH_SKIP_DIRS:
                continue
            if entries >= max_entries:
                out.append("%s…（条目上限 %d）" % (prefix, max_entries))
                stopped = True
                return
            if child.is_dir():
                out.append(prefix + child.name + "/")
                entries += 1
                walk(child, prefix + "  ", level + 1)
            elif child.is_file():
                out.append(prefix + child.name)
                entries += 1

    walk(target, "", 0)
    head = "目录 %s（%d 项；限深 %d 层）" % (rel or ".", entries, depth)
    return True, head + "\n" + "\n".join(out)
