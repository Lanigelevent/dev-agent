#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""样本批量跑分器：对每个样本的「缺陷引入态」运行评审器。

补齐评测链的缺失一环：collect → prepare → 【run-samples】 → judge。
方向契约：评审对象是父提交（缺陷态）的代码——与 prepare 的反向 diff
（git show -R）同口径：
- 确定性规则跑 fix 的反向 diff（git diff fix parent），+ 行即缺陷代码；
- 跨文件污点引擎（--cross）在父版本的 git worktree 上扫描（工作区=缺陷态）。
按 sha 分组输出 findings JSON（judge 的输入格式）。

单样本失败不阻塞批量（记入 errors 继续下一个）；退出码 0=全部尝试完成
（含零命中），2=输入错误。

用法示例：
    py run-samples.py --samples samples.json --repo <仓库> --out findings.json
    py run-samples.py --samples samples.json --repo <仓库> --out findings.json --cross

退出码：0=成功；2=输入错误。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "skills" / "multi-agent-review" / "scripts" / "deterministic-rules.py"
TAINT_CROSS = ROOT / "skills" / "multi-agent-review" / "scripts" / "taint-cross.py"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    return proc.returncode, proc.stdout


def _run_json(argv_list):
    proc = subprocess.run([sys.executable] + [str(a) for a in argv_list],
                          shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300,
                          cwd=str(ROOT))
    try:
        return proc.returncode, json.loads(proc.stdout)
    except ValueError:
        return proc.returncode, None


def _one_sample(sample, repo, work, use_cross, errors):
    """单样本跑分：返回 findings 列表（失败返回 None 并记 errors）。

    方向契约：扫缺陷引入态（父提交）。反向 diff 的 + 行 = 缺陷代码；
    跨文件污点在父版本 worktree 上跑（工作区即缺陷态）。
    """
    sha = str(sample.get("fix_commit", ""))
    parent = str(sample.get("parent_rev", ""))
    if not sha or not parent:
        errors.append("样本缺 fix_commit/parent_rev: %s" % sha[:12])
        return None
    # 反向 diff：fix -> parent，+ 行为缺陷代码（与 prepare 的 git show -R 同口径）
    rc, diff_text = _git(repo, ["diff", sha, parent])
    if rc != 0 or not diff_text.strip():
        errors.append("diff 为空或失败: %s" % sha[:12])
        return None
    diff_path = work / ("%s.diff" % sha[:12])
    diff_path.write_text(diff_text, encoding="utf-8", newline="\n")
    findings = []
    rc, data = _run_json([RULES, "--diff-file", diff_path])
    if rc == 0 and data:
        for f in data.get("findings", []):
            f["sample_id"] = sha
            f["engine"] = "deterministic"
            findings.append(f)
    else:
        errors.append("deterministic 失败: %s" % sha[:12])
    if use_cross:
        # 父版本 worktree：跨文件引擎需要文件树，工作区必须是缺陷态
        worktree = work / ("wt-%s" % sha[:12])
        rc_w, _out = _git(repo, ["worktree", "add", "--detach",
                                 str(worktree), parent])
        if rc_w == 0:
            try:
                rc, data = _run_json([TAINT_CROSS, "--root", worktree,
                                      "--diff", diff_path,
                                      "--max-files", "200"])
                if rc == 0 and data:
                    for f in data.get("findings", []):
                        f["sample_id"] = sha
                        f["engine"] = "taint-cross"
                        findings.append(f)
                else:
                    errors.append("taint-cross 失败: %s" % sha[:12])
            finally:
                _git(repo, ["worktree", "remove", "--force", str(worktree)])
        else:
            errors.append("worktree 建立失败（跳过污点引擎）: %s" % sha[:12])
    return findings


def main():
    parser = argparse.ArgumentParser(description="样本批量跑分器（评测链第三环）")
    parser.add_argument("--samples", required=True, help="collect-samples 输出 JSON")
    parser.add_argument("--repo", required=True, help="样本所在仓库")
    parser.add_argument("--out", required=True, help="findings JSON 输出路径")
    parser.add_argument("--work", default="", help="diff 落盘目录（缺省 out 同级）")
    parser.add_argument("--cross", action="store_true", help="追加跨文件污点引擎")
    parser.add_argument("--limit", type=int, default=0, help="样本数上限（0=不限）")
    argv = parser.parse_args()
    samples_path = Path(argv.samples)
    repo = Path(argv.repo).resolve()
    out_path = Path(argv.out)
    if not samples_path.is_file():
        _emit({"ok": False, "error": "样本文件不存在: %s" % samples_path})
        return 2
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库目录不存在: %s" % repo})
        return 2
    try:
        data = json.loads(samples_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "样本 JSON 非法: %s" % exc})
        return 2
    samples = data.get("samples") if isinstance(data, dict) else data
    if not isinstance(samples, list):
        _emit({"ok": False, "error": "样本需为数组或含 samples 键"})
        return 2
    if argv.limit > 0:
        samples = samples[:argv.limit]
    work = Path(argv.work) if argv.work else out_path.resolve().parent / "diffs"
    work.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    grouped, errors = {}, []
    for sample in samples:
        findings = _one_sample(sample, repo, work, argv.cross, errors)
        if findings is None:
            continue
        grouped.setdefault(str(sample.get("fix_commit", "")), findings)
    out_path.write_text(
        json.dumps({"samples": grouped}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    _emit({"ok": True, "samples_total": len(samples),
           "samples_with_findings": sum(1 for v in grouped.values() if v),
           "out": str(out_path), "errors": errors})
    return 0


if __name__ == "__main__":
    sys.exit(main())
