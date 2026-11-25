#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSWE 任务清单获取器（治理壳，零第三方依赖，AGENTS.md 硬约束 1）。

DeepSWE 是 113 任务的原创 SWE 基准（TypeScript/Go/Python/JavaScript/Rust），
使用 Harbor task 格式（每个任务是一个目录，含 task.toml + instruction.md +
tests/ + solution/），不是 JSONL 数据集。

本脚本：
  1. 从 GitHub 或 ModelScope clone deep-swe 仓库（遵循硬约束 8：优先国内源）
  2. 遍历 tasks/ 目录，解析每个 task.toml（用 tomllib 标准库）
  3. 输出 JSONL 索引文件：每行含 id/task/repo/base_commit/language/difficulty

用法示例:
    py deepswe-fetch.py --output skills/eval-harness/data/deepswe-tasks.jsonl
    py deepswe-fetch.py --output <路径> --source modelscope
    py deepswe-fetch.py --output <路径> --source github --no-clone --repo-path <已有路径>

退出码: 0=成功；1=有可处理的问题（含 NEED_HUMAN）；2=输入/环境错误。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

# 标准库 tomllib（Python 3.11+）
try:
    import tomllib
except ModuleNotFoundError:
    print(json.dumps({"ok": False, "error": "需要 Python 3.11+（tomllib）"}),
          file=sys.stderr)
    sys.exit(2)

GITHUB_URL = "https://github.com/datacurve-ai/deep-swe"
MODELSCOPE_URL = "https://www.modelscope.cn/datasets/evalscope/deep-swe.git"

SOURCES = {
    "github": GITHUB_URL,
    "modelscope": MODELSCOPE_URL,
}


def _emit(obj):
    """stdout 只输出一个 JSON 文档（AGENTS.md 硬约束 2）。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _clone(source, dest):
    """git clone deep-swe 仓库。优先国内源（硬约束 8）。"""
    url = SOURCES.get(source)
    if not url:
        return False, "未知源: %s（可选: %s）" % (source, ", ".join(SOURCES))
    if dest.exists():
        return True, "仓库已存在: %s" % dest
    # ModelScope 用 git clone，GitHub 也用 git clone
    # ModelScope 数据集需要特殊处理——用 git clone 加 -c http.sslVerify=false
    cmd = ["git", "clone", "--depth", "1", url, str(dest)]
    if source == "modelscope":
        cmd = ["git", "clone", "--depth", "1",
               "-c", "http.sslVerify=false", url, str(dest)]
    try:
        proc = subprocess.run(cmd, shell=False, capture_output=True,
                              text=True, encoding="utf-8",
                              errors="replace", timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "git clone 失败: %s" % str(exc)[:500]
    if proc.returncode != 0:
        err = (proc.stderr or "")[:500]
        # 如果主源失败，记录降级原因
        return False, "git clone 返回 %d: %s" % (proc.returncode, err)
    return True, "clone 成功"


def _parse_task(task_dir):
    """解析单个任务目录的 task.toml + instruction.md。

    返回 dict 或 None（解析失败）。
    task.toml 结构（Harbor 格式，实测 DeepSWE v1.1）：
      [task] name=... description=...
      [metadata] task_id=... language=... repository_url=...
                  base_commit_hash=... display_title=... category=...
      [environment] docker_image=... cpus=... memory_mb=...
      [verifier] timeout_sec=...
      [agent] timeout_sec=...
    """
    toml_path = task_dir / "task.toml"
    instr_path = task_dir / "instruction.md"
    if not toml_path.is_file():
        return None
    try:
        with toml_path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        print("task.toml 解析失败 %s: %s" % (task_dir.name, exc),
              file=sys.stderr)
        return None
    # 关键字段在 [metadata] 段
    meta = data.get("metadata", {})
    task_id = meta.get("task_id", task_dir.name)
    repo = meta.get("repository_url", "")
    base_commit = meta.get("base_commit_hash", "")
    language = meta.get("language", "unknown")
    category = meta.get("category", "unknown")
    display_title = meta.get("display_title", "")
    # [environment] 段
    env = data.get("environment", {})
    docker_image = env.get("docker_image", "")
    # [verifier] 段
    verifier = data.get("verifier", {})
    verifier_timeout = verifier.get("timeout_sec", 1800)
    # 读取 instruction.md
    instruction = ""
    if instr_path.is_file():
        instruction = instr_path.read_text(encoding="utf-8",
                                           errors="replace")[:5000]
    # 测试命令
    test_cmd = "bash tests/test.sh"
    return {
        "id": task_id,
        "task": instruction[:2000],
        "title": display_title,
        "repo": repo,
        "base_commit": base_commit,
        "language": language,
        "category": category,
        "difficulty": category,
        "test_command": test_cmd,
        "docker_image": docker_image,
        "verifier_timeout": verifier_timeout,
        "task_dir": str(task_dir),
    }


def main():
    parser = argparse.ArgumentParser(
        description="DeepSWE 任务清单获取器")
    parser.add_argument("--output", required=True,
                        help="输出 JSONL 路径")
    parser.add_argument("--source", default="github",
                       choices=list(SOURCES.keys()),
                       help="下载源（默认 github；硬约束 8 建议先试 modelscope）")
    parser.add_argument("--no-clone", action="store_true",
                        help="不 clone，用 --repo-path 指定的已有仓库")
    parser.add_argument("--repo-path", default="",
                        help="已有 deep-swe 仓库路径（--no-clone 时使用）")
    parser.add_argument("--lang", default="",
                        help="只输出指定语言的任务")
    argv = parser.parse_args()

    out_path = Path(argv.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 请求来源与实际来源分开记：回退成功时 output.source 必须是真正用的那家，
    # 否则「降级如实记录」成了假账（round-43 修）。
    requested_source = argv.source
    actual_source = "local" if argv.no_clone else argv.source
    fallback_reason = ""

    # 确定仓库路径
    if argv.no_clone:
        if not argv.repo_path:
            _emit({"ok": False, "error": "--no-clone 需要 --repo-path"})
            return 2
        repo_path = Path(argv.repo_path).resolve()
        if not repo_path.is_dir():
            _emit({"ok": False, "error": "仓库路径不存在: %s" % repo_path})
            return 2
    else:
        # 默认 clone 到 skills/eval-harness/data/deep-swe
        default_dest = Path(__file__).resolve().parents[1] / "data" / "deep-swe"
        repo_path = default_dest
        # 先试主源，失败回退
        ok, msg = _clone(argv.source, repo_path)
        if not ok:
            print("主源 %s 失败: %s" % (argv.source, msg),
                  file=sys.stderr)
            # 尝试回退源
            fallback = "modelscope" if argv.source == "github" else "github"
            if fallback != argv.source:
                print("回退到 %s" % fallback, file=sys.stderr)
                ok, msg = _clone(fallback, repo_path)
                if ok:
                    actual_source = fallback
                    fallback_reason = "主源 %s 失败: %s" % (argv.source, msg)
            if not ok:
                _emit({"ok": False, "error": "所有源 clone 失败: %s" % msg,
                       "hint": "可手动 clone 后用 --no-clone --repo-path"})
                return 1

    # 遍历 tasks/ 目录
    tasks_dir = repo_path / "tasks"
    if not tasks_dir.is_dir():
        # 有些仓库直接在根目录放任务
        tasks_dir = repo_path

    tasks = []
    for item in sorted(tasks_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith("."):
            continue
        parsed = _parse_task(item)
        if parsed:
            if argv.lang and parsed["language"].lower() != argv.lang.lower():
                continue
            tasks.append(parsed)

    if not tasks:
        _emit({"ok": False, "error": "未找到任何任务（tasks/ 目录为空或不存在）",
               "repo_path": str(repo_path),
               "tasks_dir": str(tasks_dir)})
        return 1

    # 写 JSONL
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    # 统计
    by_lang = {}
    for t in tasks:
        lang = t["language"] or "unknown"
        by_lang[lang] = by_lang.get(lang, 0) + 1

    _emit({
        "ok": True,
        "output": str(out_path),
        "total": len(tasks),
        "by_language": by_lang,
        "source": actual_source,
        "requested_source": requested_source,
        "degraded": actual_source != requested_source,
        "fallback_reason": fallback_reason,
        "repo_path": str(repo_path),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
