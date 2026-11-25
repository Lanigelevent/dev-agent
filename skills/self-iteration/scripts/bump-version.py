#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本 bump 单命令：同步六处版本真值 + 可选计数真值（P1-5，round-86）。

背景
----
发布时「版本七处与计数多处靠人工 + 事后门禁同步」，每轮 1-2 循环损耗
（reports/project-review-r85.md 维度 5）。本脚本把**确定性同步**收口为一条
命令；BASELINE 本轮沿革条目与 README「更新」行（日期/round）由作者随本轮
沿革写入，不在本脚本职责内——release-gate.py version_sync 仍负责最终对账。

同步面（--set 时逐个重写，每个模式必须恰好命中 1 处，否则拒绝执行）：
  [S1] .zcode-plugin/plugin.json       "version": "X.Y.Z"
  [S2] pyproject.toml                  ^version = "X.Y.Z"
  [S3] mcp/review_mcp.py               SERVER_INFO "version": "X.Y.Z"
  [S4] README.md                       **版本 X.Y.Z**
  [S5] docs/DEVELOPMENT.md             「版本唯一事实源 …（当前 X.Y.Z）」行
  [S6] docs/PROGRESS.md                「| 版本 | X.Y.Z |」行

计数同步（--sync-counts，可选）：
  实算 skills/ 目录数、skills/*/scripts/*.py 数、unittest discover 用例数，
  重写 README/DEVELOPMENT/AGENTS 中无歧义的「N 个技能」「N 个脚本」，以及
  README/DEVELOPMENT 中**含「unittest discover」或「契约测试」的行**上的
  「N 项」；带 →/当时/原为/曾/上一轮/历史/沿革 的历史值行不动；无差异的
  行原样保留。BASELINE/ROADMAP/PROGRESS/next-round 不动（历史文档，
  计数为当时真值）。

两阶段落盘：先全部演算（内存中），任一校验失败则**不写任何文件**。

用法示例：
    python bump-version.py --root . --set 1.87.0                # 干跑，只出计划
    python bump-version.py --root . --set 1.87.0 --apply        # 落盘
    python bump-version.py --root . --set 1.87.0 --apply --sync-counts

退出码：0 = 成功（干跑输出计划 / --apply 已落盘）；
        1 = 有待处理问题（模式未命中或多命中、版本形态非法、计数采集失败；
            失败时不写任何文件）；
        2 = 参数或环境错误。
stdout 输出单个 JSON 文档。
"""
import argparse
import json
import re
import sys
import unittest
from pathlib import Path

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
HIST_MARK = re.compile(r"→|当时|原为|曾|上一轮|历史|沿革")

# (id, rel_path, pattern)；每个 pattern 必须在当前文本命中恰好 1 处
VERSION_TARGETS = (
    ("S1", ".zcode-plugin/plugin.json",
     re.compile(r'"version"\s*:\s*"\d+\.\d+\.\d+"')),
    ("S2", "pyproject.toml",
     re.compile(r'(?m)^version\s*=\s*"\d+\.\d+\.\d+"\s*$')),
    ("S3", "mcp/review_mcp.py",
     re.compile(r'SERVER_INFO\s*=\s*\{[^}\n]*?"version"\s*:\s*"\d+\.\d+\.\d+"')),
    ("S4", "README.md", re.compile(r"\*\*版本 \d+\.\d+\.\d+\*\*")),
    ("S5", "docs/DEVELOPMENT.md", re.compile(r"当前 \d+\.\d+\.\d+")),
    ("S6", "docs/PROGRESS.md", re.compile(r"\| 版本 \| \d+\.\d+\.\d+ \|")),
)
COUNT_TARGETS = (
    ("skills", re.compile(r"\d+ 个技能"), "{n} 个技能",
     ("AGENTS.md", "README.md", "docs/DEVELOPMENT.md")),
    ("scripts", re.compile(r"\d+ 个脚本"), "{n} 个脚本",
     ("AGENTS.md", "README.md", "docs/DEVELOPMENT.md")),
)
COUNT_TESTS_LINE = re.compile(r"\d+ 项")
COUNT_TESTS_LINE_GUARD = re.compile(r"unittest discover|契约|共 \d+ 项")
COUNT_TESTS_FILES = ("README.md", "docs/DEVELOPMENT.md")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "check": "bump-version", "error": error})
    return 2


def _read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _sub_count_lines(text, pattern, replacement, guard=None):
    """逐处替换；历史值跳过按「数值前 12 字内命中 HIST_MARK」判定（与
    doc-freshness.py F5 同口径），不因整行含历史标记豁免现状数字。"""
    lines = text.splitlines(keepends=True)
    changes, skipped = [], []
    for i, line in enumerate(lines, 1):
        if guard is not None and not guard.search(line):
            continue

        def _repl(m):
            ctx = line[max(0, m.start() - 12):m.start()]
            if HIST_MARK.search(ctx):
                skipped.append({"line": i, "reason": "历史值（数值前 12 字内命中）",
                                "text": line.strip()[:60]})
                return m.group(0)
            if m.group(0) == replacement:
                return m.group(0)
            changes.append({"line": i, "before": m.group(0),
                            "after": replacement})
            return replacement

        new_line = pattern.sub(_repl, line)
        if new_line != line:
            lines[i - 1] = new_line
    return "".join(lines), changes, skipped


def _count_truth(root):
    scripts = len(list(root.glob("skills/*/scripts/*.py")))
    skills_dir = root / "skills"
    skills = len([d for d in skills_dir.iterdir() if d.is_dir()]) \
        if skills_dir.is_dir() else 0
    loader = unittest.defaultTestLoader
    suite = loader.discover(str(root / "tests"), pattern="test_*.py",
                            top_level_dir=str(root / "tests"))
    return {"skills": skills, "scripts": scripts,
            "tests": suite.countTestCases()}


def _plan_version(text, pattern, version):
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        return None, "模式命中 %d 处（必须恰好 1 处）" % len(matches)
    m = matches[0]
    new_text = (text[:m.start()] +
                re.sub(r"\d+\.\d+\.\d+", version, m.group(0)) +
                text[m.end():])
    return new_text, None


def main():
    parser = argparse.ArgumentParser(description="版本/计数真值同步（确定性六处）")
    parser.add_argument("--root", default=".")
    parser.add_argument("--set", dest="version", required=True,
                        help="目标版本 X.Y.Z")
    parser.add_argument("--apply", action="store_true",
                        help="落盘（缺省只干跑出计划）")
    parser.add_argument("--sync-counts", action="store_true",
                        help="同时同步计数真值（技能/脚本/契约测试）")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        return _param_error("项目根不存在: %s" % root)
    version = args.version.strip()
    if not SEMVER.match(version):
        return _param_error("版本必须是 X.Y.Z 形态: %r" % version)

    truth = None
    if args.sync_counts:
        try:
            truth = _count_truth(root)
        except (OSError, ValueError) as exc:
            return _param_error("计数真值采集失败: %s" % exc)

    # 阶段一：内存演算（不落盘）
    errors = []
    file_edits = {}   # rel -> {"changes": [...], "text": evolving_text}

    def _apply_to(rel, fn):
        path = root / rel
        if not path.is_file():
            errors.append({"id": "-", "path": rel, "error": "文件缺失"})
            return
        cur = file_edits.get(rel, {"changes": [], "text": _read(path)})
        new_text, changes, skipped = fn(cur["text"])
        cur["text"] = new_text
        cur["changes"].extend(changes)
        cur.setdefault("skipped", []).extend(skipped)
        file_edits[rel] = cur

    for sid, rel, pattern in VERSION_TARGETS:
        def fn(text, sid=sid, pattern=pattern):
            new_text, err = _plan_version(text, pattern, version)
            if err:
                errors.append({"id": sid, "path": rel, "error": err})
                return text, [], []
            return new_text, [{"id": sid, "detail": "version→%s" % version}], []
        _apply_to(rel, fn)

    if truth is not None:
        for key, pattern, repl, files in COUNT_TARGETS:
            body = repl.format(n=truth[key])
            for rel in files:
                def fn(text, pattern=pattern, body=body, key=key):
                    new_text, changes, skipped = _sub_count_lines(
                        text, pattern, body)
                    for c in changes:
                        c["id"] = "C-" + key
                    return new_text, changes, skipped
                _apply_to(rel, fn)
        for rel in COUNT_TESTS_FILES:
            def fn(text):
                new_text, changes, skipped = _sub_count_lines(
                    text, COUNT_TESTS_LINE, "%d 项" % truth["tests"],
                    guard=COUNT_TESTS_LINE_GUARD)
                for c in changes:
                    c["id"] = "C-tests"
                return new_text, changes, skipped
            _apply_to(rel, fn)

    if errors:
        _emit({"ok": False, "version": version, "errors": errors,
               "note": "存在校验失败，未写入任何文件"})
        return 1

    # 阶段二：落盘
    report_targets = []
    all_skipped = []
    for rel, edit in file_edits.items():
        changed = edit["text"] != _read(root / rel)
        if args.apply and changed:
            (root / rel).write_text(edit["text"], encoding="utf-8",
                                    newline="\n")
        report_targets.append({"path": rel, "changed": changed,
                               "changes": edit["changes"]})
        all_skipped.extend({"doc": rel, **s} for s in edit.get("skipped", []))

    _emit({
        "ok": True,
        "version": version,
        "applied": bool(args.apply),
        "targets": report_targets,
        "count_truth": truth,
        "count_skipped": all_skipped,
        "note": ("BASELINE.md 本轮沿革条目立版本并人工写入后，"
                 "release-gate.py --only version_sync 对账"),
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
