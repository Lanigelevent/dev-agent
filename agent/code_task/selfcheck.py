#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编辑自校验：语法/import 探针、补丁结构校验、片段脱敏。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import base64
import os
import re
import subprocess
from agent.workspace import open_workspace, WorkspaceError  # noqa: E402


def _module_name(rel_path):
    """相对路径 → 可导入的模块名（去掉 .py / __init__）。"""
    parts = list(Path(rel_path).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _no_bytecode_env(src_path):
    """子进程环境：PYTHONPATH 指向待观察的树 + 禁止落 __pycache__。

    为什么必须禁字节码（本轮实踩）：自检要在编辑前后各导入一次同一模块，
    导入会把 .pyc 写进 **工作树**。若补丁改的是等长的一行（`return a - b` →
    `return a + b`）且落在同一秒内，缓存校验看的 (mtime 秒, size) 完全没变 →
    后续 pytest 导入到**旧字节码**，测试报「修了还是错的」——把一次正常修复
    误判成失败，白跑一轮甚至判 NO_PATCH。观察别人代码的进程不该留下代码。
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src_path) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _import_probe(python, repo, module, timeout=180):
    """在子进程里试导入模块 → (ok, 错误摘要)。"""
    code = "import importlib; importlib.import_module(%r)" % module
    env = _no_bytecode_env(repo)
    try:
        p = subprocess.run([python, "-c", code], shell=False,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:200]
    return p.returncode == 0, (p.stderr or "")[-300:]


def _import_probe_docker(src, module, image, timeout=180):
    """容器内试导入（与 --probe-docker 同一 merge 通道）：挂 /agent-wt 只读，
    cp -a 合并进 /testbed 保住镜像编译产物，bash -lc 激活 conda 环境。"""
    code = "import importlib; importlib.import_module(%s)" % repr(module)
    b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
    argv = ["docker", "run", "--rm", "-i",
            "-v", "%s:/agent-wt:ro" % src, "-w", "/testbed",
            image, "bash", "-lc",
            "cp -a /agent-wt/. /testbed/ && echo %s | base64 -d | python -" % b64]
    try:
        p = subprocess.run(argv, shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:200]
    return p.returncode == 0, (p.stderr or "")[-300:]


def _ws_import_probe(ws, base, module, timeout=180):
    """在工作区后端内试导入模块 → (ok, err 末 300 字)。"""
    code = "import importlib; importlib.import_module(%r)" % module
    try:
        rc, _out, err = ws.run_in(base, [ws.python, "-c", code],
                                  timeout=timeout)
    except WorkspaceError as exc:
        return False, str(exc)[:300]
    return rc == 0, (err or "")[-300:]


def _patch_selfcheck(repo, worktree, rel_paths, python=None,
                     docker_image=None, ws=None):
    """基线对比式导入冒烟：补丁后导入失败、而补丁前能导入 → 补丁弄坏了模块。

    动机（round-19 实踩）：astropy-14365 的补丁少一个右括号，正则要到
    **导入时**才编译——本地 pytest 因缺依赖跑不起来，只有容器才发现，代价
    是整整一次返工。这里用「补丁前后同模块导入结果对比」把这类错误拦在
    本地；基线本身就导不进去（环境缺依赖）时无法归因，跳过不报。
    round-34 前移（docker_image 非空时）：本地基线导不进不再静默跳过，
    改到任务镜像里做同样的前后对比（环境=官方评测环境，归因反而更准）。
    """
    python = python or sys.executable
    broken = []
    for rel in rel_paths:
        if not str(rel).endswith(".py"):
            continue
        module = _module_name(rel)
        if not module:
            continue
        if ws is not None:
            # 同一后端里做前后对比：基线目录与工作区目录都在后端可见
            ok_before, _ = _ws_import_probe(ws, ws.baseline_dir, module)
            if not ok_before:
                continue
            ok_after, err = _ws_import_probe(ws, ws.workspace_dir, module)
            if not ok_after:
                broken.append((rel, "[%s] %s" % (ws.backend, err)))
            continue
        ok_before, _ = _import_probe(python, repo, module)
        if not ok_before and docker_image:
            # 本机基线导不进（编译扩展/老 Python 语义）→ 容器内做前后对比
            ok_before, _ = _import_probe_docker(repo, module, docker_image)
            if ok_before:
                ok_after, err = _import_probe_docker(worktree, module,
                                                     docker_image)
                if not ok_after:
                    broken.append((rel, "[容器] " + err))
            continue
        if not ok_before:
            continue
        ok_after, err = _import_probe(python, worktree, module)
        if not ok_after:
            broken.append((rel, err))
    return broken


def _added_lines(patch_text):
    """取补丁的 + 行内容（剥掉前导 +，不含 --- / +++ 文件头）。

    口径纪律（维护红线 1/2）：不按行首空白锚定，且只取 + 行——把上下文行
    也算进来会让「原样保留的行」被误判成关键改动。
    """
    added = []
    for line in (patch_text or "").splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        content = line[1:].strip()
        if content:
            added.append(content)
    return added


def _novel_lines(search, replace):
    """REPLACE 相对 SEARCH 的新增内容行（strip 后比较）。"""
    old = {l.strip() for l in (search or "").splitlines() if l.strip()}
    return [l.strip() for l in (replace or "").splitlines()
            if l.strip() and l.strip() not in old]


def _match_change(added, novel):
    """关键改动是否出现在补丁 + 行里。

    两侧都取 strip 后的行：缩进由 diff 原样保留，等值优先；长度 >=6 时允许
    包含关系（模型常在 REPLACE 里多写或少写几个空格、或把续行拆开）。
    """
    for n in novel:
        if n in added:
            return True
        if len(n) >= 6 and any(n in a for a in added):
            return True
        if any(len(a) >= 6 and a in n for a in added):
            return True
    return False


def _validate_patch(patch_text, blocks, edited_paths):
    """补丁即时校验 → {ok, issues:[{code, detail}]}。

    四条判据（round-28 检查单第 7/9 项）：
      empty_patch     —— 声称应用了编辑，但 git diff 为空（等于没产出）；
      file_missing    —— 编辑过的文件没出现在补丁的 +++ 头里；
      missing_change  —— 某个编辑的关键改动行不在补丁 + 行里（改的不是这处）；
      non_ascii       —— 新增行含非 ASCII 字符（编码破坏闭合引号 →
                          SyntaxError → 容器直接 EVAL_FAILED，round-27 实踩）。
    """
    issues = []
    added = _added_lines(patch_text)
    headers = re.findall(r"^\+\+\+ b/(.+)$", patch_text or "", flags=re.M)
    if edited_paths and not (patch_text or "").strip():
        issues.append({"code": "empty_patch",
                       "detail": "已声称改动 %d 个文件但补丁为空——编辑很可能没命中"
                                 "（SEARCH 写成别版补丁的代码，或目标文件不存在；"
                                 "本轮编辑已回滚）。请重新读取当前文件内容"
                                 "后再出编辑。" % len(edited_paths)})
    for path in edited_paths:
        if path not in headers:
            issues.append({"code": "file_missing",
                           "detail": "编辑过的文件 %s 未出现在补丁头里" % path})
    for block in blocks or []:
        novel = _novel_lines(block.get("search"), block.get("replace"))
        if not novel or not added:
            continue          # 无实质差异的空编辑交给 empty_patch 抓，不误报
        if not _match_change(added, novel):
            issues.append({"code": "missing_change",
                           "detail": "%s：REPLACE 的关键行 %r 不在补丁新增行里"
                                     % (block.get("path"), novel[0][:60])})
    bad = [i + 1 for i, line in enumerate((patch_text or "").splitlines())
           if line.startswith("+") and not line.startswith("+++")
           and any(ord(c) > 127 for c in line)]
    if bad:
        issues.append({"code": "non_ascii",
                       "detail": "补丁第 %s 行含非 ASCII 字符——注释与 docstring "
                                 "一律用英文，中文只写进 summary"
                                 % ",".join(str(n) for n in bad[:8])})
    return {"ok": not issues, "issues": issues}


_SECRET_KV_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization)\b"
    r"(\s*[:=]\s*)(['\"]?)[^\s'\"]{6,}")


_SECRET_SHAPE_RES = (
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"mysql://[^\s/:]+:[^@\s]+@"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def _redact_snippet(text):
    """命中密钥形态的搜索行脱敏为 <redacted>（硬约束 5）。"""
    text = _SECRET_KV_RE.sub(
        lambda m: m.group(1) + m.group(2) + m.group(3) + "<redacted>", text)
    for pattern in _SECRET_SHAPE_RES:
        text = pattern.sub("<redacted>", text)
    return text
