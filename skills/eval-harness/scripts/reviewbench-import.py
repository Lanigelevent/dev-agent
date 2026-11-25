#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReviewBench 语料导入（round-34，升级计划阶段 1-B；MIT 许可，署名保留）。

用途:
    把 ReviewBench（github.com/review-bench/ReviewBench）的 golden 标注转成
    本仓前向基准样本：每例 = {sample_id=pr_key, repo, fix_commit=head,
    defect_class="reviewbench", files=[finding 文件], diff_path, expect_findings}。
    PR diff 从 github.com/<owner>/<repo>/pull/<n>.diff 拉取（raw 域不可达，
    实测 WinError 10054；git/网页主域可达——硬约束 8 的实测结论）。

    --offline：不触网，只用已落盘的 diffs/ 目录装配样本（契约测试与复跑用）。

用法:
    python reviewbench-import.py --corpus datasets/reviewbench --out datasets/reviewbench/samples.json
    python reviewbench-import.py --corpus datasets/reviewbench --out samples.json --lang .py --limit 12
    python reviewbench-import.py --corpus datasets/reviewbench --out samples.json --offline

退出码:
    0 = 正常
    1 = 输入结构不合格（manifest/golden 缺失或形状不符）
    2 = 参数/环境错误（含离线模式缺 diff）
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "dev-agent-reviewbench-import"}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_corpus(corpus):
    """读 manifest + golden → [(pr_meta, findings)]；形状不合格即 None。"""
    mpath = corpus / "corpus" / "manifest.json"
    if not mpath.is_file():
        return None
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, list):
        return None
    golden_dir = corpus / "golden"
    rows = []
    for pr in manifest:
        if not isinstance(pr, dict) or "repo" not in pr or "pr_number" not in pr:
            continue
        # golden 命名实测：<owner>_<repo>_<pr号>-<head8>.json（编号前是下划线）
        key = "%s_%s_%s" % (pr["repo"].rstrip("/").split("/")[-2],
                            pr["repo"].rstrip("/").split("/")[-1],
                            pr["pr_number"])
        # golden 文件名带 head 短哈希后缀：<owner>_<repo>_<n>-<head8>.json
        gfile = None
        if golden_dir.is_dir():
            for g in golden_dir.glob(key + "-*.json"):
                gfile = g
                break
        findings = []
        if gfile:
            try:
                gd = json.loads(gfile.read_text(encoding="utf-8"))
                findings = gd.get("findings") or []
                key = gd.get("pr_key") or key
            except (OSError, ValueError):
                findings = []
        rows.append({"pr": pr, "pr_key": key, "findings": findings})
    return rows


def _diff_url(repo_url, pr_number):
    return "%s/pull/%d.diff" % (repo_url.rstrip("/"), pr_number)


def main():
    ap = argparse.ArgumentParser(description="ReviewBench 语料导入")
    ap.add_argument("--corpus", required=True, help="克隆的 ReviewBench 仓库目录")
    ap.add_argument("--out", required=True, help="samples.json 落盘路径")
    ap.add_argument("--lang", default="", help="只收 finding 文件含该后缀的 PR（如 .py）")
    ap.add_argument("--limit", type=int, default=0, help="最多导入多少例（0=不限）")
    ap.add_argument("--offline", action="store_true",
                    help="不触网，只用已落盘 diffs/ 装配")
    ap.add_argument("--sleep", type=float, default=1.0, help="抓取间隔秒数")
    argv = ap.parse_args()

    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        _emit({"ok": False, "error": "corpus 目录不存在: %s" % corpus})
        return 2
    rows = _load_corpus(corpus)
    if rows is None:
        _emit({"ok": False, "error": "manifest 缺失或形状不合格"})
        return 1

    diffs_dir = corpus / "diffs"
    diffs_dir.mkdir(exist_ok=True)
    picked, skipped_lang, fetched, offline_missing = [], 0, 0, 0
    for row in rows:
        pr, findings = row["pr"], row["findings"]
        if argv.lang:
            files = [f.get("file", "") for f in findings]
            if not any(f.endswith(argv.lang) for f in files):
                skipped_lang += 1
                continue
        if argv.limit and len(picked) >= argv.limit:
            break
        key = row["pr_key"]
        diff_path = diffs_dir / (key + ".diff")
        if not diff_path.is_file():
            if argv.offline:
                offline_missing += 1
                continue
            url = _diff_url(pr["repo"], pr["pr_number"])
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                if not body.startswith("diff") and "diff --git" not in body[:400]:
                    continue  # 非 diff 内容（404 页面等），跳过
                diff_path.write_text(body, encoding="utf-8", newline="\n")
                fetched += 1
                time.sleep(argv.sleep)
            except Exception:  # noqa: BLE001 - 单 PR 抓取失败不拖垮整批
                continue
        picked.append({
            "sample_id": key,
            "repo": pr["repo"],
            "fix_commit": pr.get("head", ""),
            "defect_class": "reviewbench",
            "files": sorted({f.get("file", "") for f in findings if f.get("file")}),
            "diff_path": str(diff_path),
            "expect_findings": len(findings),
            "title": pr.get("title", ""),
        })

    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(picked, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    _emit({"ok": True, "samples": len(picked), "fetched": fetched,
           "skipped_lang": skipped_lang, "offline_missing": offline_missing,
           "out": str(out)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
