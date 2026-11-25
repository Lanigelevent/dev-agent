# -*- coding: utf-8 -*-
"""tests/_scripts_common.py — test_scripts 拆分族共享夹具与 runner（round-88 P2-8）。

原 tests/test_scripts.py（4102 行巨石）按域拆为 test_scripts_*.py 八个模块；
本模块承载全部共享状态：SCRIPTS 路径表、V1/V2/V3 夹具内容、FIXTURE dict、
run() 子进程 runner、snapshot_repo 源码快照、setUpModule（经 ensure_fixture
每进程只构建一次）；tearDownModule 取消——临时目录清理交 tmpspace 的
atexit 兜底（原 eager release 在共享单例下会掐断后续模块的夹具）。
"""
import json
import importlib.util
import ast
import urllib.error
import urllib.parse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tmpspace

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "skills"

# 仓级门禁（fingerprint / doc-drift / dead-code）要一份「项目树的可写副本」，
# 但不能把整个工作树搬进临时目录：本机工作树里 datasets/ 实测 47GB / 11.9 万文件，
# 加上 .venv/ .mimosa/ logs/ 一次全量 copytree 单条测试就 90 秒以上，
# 且把「这台机器的工作树碰巧有什么」混进「项目内容」——门禁口径应当只看源码树。
# round-45 实测：reports/（含 _work 探针产物）与 skills/eval-harness/data/ 让快照
# 副本达 77.6MB/8129 项、单次复制 6.01s；按 fingerprint 的 skip_dirs 口径排除五个
# 运行产物目录后为 2.4MB/1675 项、1.03s（两次快照共省 ~10s）。两个调用方都不读
# 这些目录，指纹与漂移结论逐一复跑不变（见 test_fingerprint_stable_and_sensitive
# 的反向断言与 round-45 画像报表）。
SNAPSHOT_IGNORE = shutil.ignore_patterns(
    "__pycache__", ".git", ".venv", "datasets", ".mimosa", "logs",
    ".tmp-sympy-ref", ".pytest_cache", "node_modules", "*.egg-info", ".idea",
    "reports", "retro", "runs", "llm-tasks", "data")


def snapshot_repo(dest):
    """把项目源码树（去掉外部资产）拷成可写副本 dest，返回 Path(dest)。"""
    shutil.copytree(ROOT, dest, ignore=SNAPSHOT_IGNORE)
    return Path(dest)

SCRIPTS = {
    "runner.py": S / "orchestrator" / "scripts" / "runner.py",
    "intent-parse.py": S / "prompt-enhancement" / "scripts" / "intent-parse.py",
    "preflight.py": S / "git-change-analysis" / "scripts" / "preflight.py",
    "edge-detect.py": S / "git-change-analysis" / "scripts" / "edge-detect.py",
    "graph-cache.py": S / "git-change-analysis" / "scripts" / "graph-cache.py",
    "score.py": S / "risk-scoring" / "scripts" / "score.py",
    "deterministic-rules.py": S / "multi-agent-review" / "scripts" / "deterministic-rules.py",
    "dispatch-plan.py": S / "multi-agent-review" / "scripts" / "dispatch-plan.py",
    "material-check.py": S / "multi-agent-review" / "scripts" / "material-check.py",
    "coverage.py": S / "multi-agent-review" / "scripts" / "coverage.py",
    "findings-check.py": S / "multi-agent-review" / "scripts" / "findings-check.py",
    "audit-log.py": S / "production-guardrails" / "scripts" / "audit-log.py",
    "checkpoint.py": S / "production-guardrails" / "scripts" / "checkpoint.py",
    "human-gate.py": S / "production-guardrails" / "scripts" / "human-gate.py",
    "event-ledger.py": S / "production-guardrails" / "scripts" / "event-ledger.py",
    "cost-ledger.py": S / "production-guardrails" / "scripts" / "cost-ledger.py",
    "coverage-gate.py": S / "self-iteration" / "scripts" / "coverage-gate.py",
    "secret-scan.py": S / "self-iteration" / "scripts" / "secret-scan.py",
    "license-check.py": S / "self-iteration" / "scripts" / "license-check.py",
    "release-gate.py": S / "self-iteration" / "scripts" / "release-gate.py",
    "report-check.py": S / "production-guardrails" / "scripts" / "report-check.py",
    "schema-check.py": S / "production-guardrails" / "scripts" / "schema-check.py",
    "manifest_args.py": S / "production-guardrails" / "scripts" / "manifest_args.py",
    "experience.py": S / "production-guardrails" / "scripts" / "experience.py",
    "feedback-close.py": S / "production-guardrails" / "scripts" / "feedback-close.py",
    "collect-samples.py": S / "eval-harness" / "scripts" / "collect-samples.py",
    "extract-window.py": S / "eval-harness" / "scripts" / "extract-window.py",
    "forward-bench.py": S / "eval-harness" / "scripts" / "forward-bench.py",
    "run-regression.py": S / "eval-harness" / "scripts" / "run-regression.py",
    "fingerprint.py": S / "eval-harness" / "scripts" / "fingerprint.py",
    "reviewbench-bridge.py": S / "eval-harness" / "scripts" / "reviewbench-bridge.py",
    "reviewbench-import.py": S / "eval-harness" / "scripts" / "reviewbench-import.py",
    "reviewbench-eval.py": S / "eval-harness" / "scripts" / "reviewbench-eval.py",
    "plan-distill.py": S / "eval-harness" / "scripts" / "plan-distill.py",
    "deepswe-fetch.py": S / "eval-harness" / "scripts" / "deepswe-fetch.py",
    "deepswe-sample.py": S / "eval-harness" / "scripts" / "deepswe-sample.py",
    "rules-select.py": S / "multi-agent-review" / "scripts" / "rules-select.py",
    "doc-drift.py": S / "self-iteration" / "scripts" / "doc-drift.py",
    "perspective-scan.py": S / "self-iteration" / "scripts" / "perspective-scan.py",
    "dead-code-scan.py": S / "self-iteration" / "scripts" / "dead-code-scan.py",
    "session-probe.py": S / "self-iteration" / "scripts" / "session-probe.py",
    "convergence-check.py": S / "self-iteration" / "scripts" / "convergence-check.py",
    "pick-candidate.py": S / "self-iteration" / "scripts" / "pick-candidate.py",
    "e2e-check.py": S / "self-iteration" / "scripts" / "e2e-check.py",
    "fix-plan.py": S / "repair" / "scripts" / "fix-plan.py",
    "fix-patch.py": S / "repair" / "scripts" / "fix-patch.py",
    "fix-apply.py": S / "repair" / "scripts" / "fix-apply.py",
    "approve-plan.py": S / "approval" / "scripts" / "approve-plan.py",
    "approve-patch.py": S / "approval" / "scripts" / "approve-patch.py",
    "pr-kit.py": S / "orchestrator" / "scripts" / "pr-kit.py",
    "pr-publish.py": S / "orchestrator" / "scripts" / "pr-publish.py",
    "retro-ledger.py": S / "retro" / "scripts" / "retro-ledger.py",
    "retro-report.py": S / "retro" / "scripts" / "retro-report.py",
    "memory_retrieval.py": S / "retro" / "scripts" / "memory_retrieval.py",
    "compact-memory.py": S / "retro" / "scripts" / "compact-memory.py",
    "org-route.py": S / "director" / "scripts" / "org-route.py",
    "case-match.py": S / "director" / "scripts" / "case-match.py",
    "research-brief.py": S / "director" / "scripts" / "research-brief.py",
    "org-scorecard.py": S / "director" / "scripts" / "org-scorecard.py",
    "case-archive.py": S / "director" / "scripts" / "case-archive.py",
    "task-pipeline.py": S / "director" / "scripts" / "task-pipeline.py",
    "taint-cross.py": S / "multi-agent-review" / "scripts" / "taint-cross.py",
    "precision-report.py": S / "eval-harness" / "scripts" / "precision-report.py",
    "run-samples.py": S / "eval-harness" / "scripts" / "run-samples.py",
    "cve-corpus.py": S / "eval-harness" / "scripts" / "cve-corpus.py",
    "cve-dump-scan.py": S / "eval-harness" / "scripts" / "cve-dump-scan.py",
    "gold-sample.py": S / "eval-harness" / "scripts" / "gold-sample.py",
}

SECRET = "hunter" + "2secret"
CJK_PROBE = "支付回调幂等性"
APIKEY = "".join(chr(c) for c in (
    115, 107, 45, 108, 105, 118, 101, 45,
    97, 98, 99, 100, 101, 102, 49, 50, 51, 52, 53, 54))
V1 = "def charge(amount):\n    total = amount * 1\n    return total\n"
V2 = "\n".join([
    "import os",
    "def charge(amount, cache={}):",
    "    password = " + '"' + SECRET + '"',
    "    total = amount * 1",
    '    if amount is "x":',
    "        pass",
    "    api_key = " + '"' + APIKEY + '"',
    "    return total",
]) + "\n"
V3 = "\n".join([
    "import os",
    "def charge(amount, cache=None):",
    "    password = os.environ.get('PAY_PASSWORD', '')",
    "    total = amount * 1",
    "    api_key = os.environ.get('PAY_API_KEY', '')",
    "    return total",
]) + "\n"

FIXTURE = {}


def _git(repo, args):
    p = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


def run(script, *args, stdin=None, env_extra=None):
    """子进程调用脚本：返回 (exit, json|None, stdout, stderr)。"""
    cmd = [sys.executable, str(script)] + [str(a) for a in args]
    env = dict(os.environ)
    if env_extra:
        env.update({k: str(v) for k, v in env_extra.items()})
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input=stdin,
                       timeout=60, env=env)
    data = None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        pass
    return p.returncode, data, p.stdout, p.stderr


def setUpModule():
    # 自建自删（round-30 检查单第 12 项）：夹具目录交给 tmpspace 建——带归属标记、
    # atexit 兜底（Ctrl-C/崩溃也会删），并把上一次中断留下的**带标记**陈旧目录回收掉。
    # 回收按标记认归属（不靠前缀清单：前缀一多必然漏，有标记才是「本模块建的」的证据）。
    # 历史遗留的那批没有标记，tmpspace 不碰（删不删是运维决定，见 scripts/sweep-test-tmp.py）。
    tmpspace.sweep(once_per_process=True)
    tmp = str(tmpspace.create(prefix="cra-tests-"))
    FIXTURE["tmp"] = Path(tmp)
    repo = FIXTURE["tmp"] / "repo"
    (repo / "svc").mkdir(parents=True)
    (repo / "svc" / "payment.py").write_text(V1, encoding="utf-8")
    _git(repo, ["init", "-q"])
    _git(repo, ["add", "-A"])
    _git(repo, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"])
    FIXTURE["shaA"] = _git(repo, ["rev-parse", "HEAD"])[1]
    (repo / "svc" / "payment.py").write_text(V2, encoding="utf-8")
    _git(repo, ["add", "-A"])
    _git(repo, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "feat: rework"])
    FIXTURE["shaB"] = _git(repo, ["rev-parse", "HEAD"])[1]
    (repo / "svc" / "payment.py").write_text(V3, encoding="utf-8")
    _git(repo, ["add", "-A"])
    _git(repo, ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "fix: move credentials to env"])
    FIXTURE["shaC"] = _git(repo, ["rev-parse", "HEAD"])[1]
    FIXTURE["repo"] = repo
    p = subprocess.run(["git", "-C", str(repo), "diff", "HEAD~2..HEAD~1"], shell=False,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    (FIXTURE["tmp"] / "change.diff").write_text(p.stdout, encoding="utf-8")
    FIXTURE["change.diff"] = FIXTURE["tmp"] / "change.diff"
    rc, rules, _, _ = run(SCRIPTS["deterministic-rules.py"], "--diff-file", FIXTURE["change.diff"])
    assert rc == 0 and rules, rules
    (FIXTURE["tmp"] / "findings.json").write_text(
        json.dumps(rules["findings"], ensure_ascii=False), encoding="utf-8")
    FIXTURE["findings"] = rules["findings"]
    FIXTURE["findings_path"] = FIXTURE["tmp"] / "findings.json"
    rc, samples, _, _ = run(SCRIPTS["collect-samples.py"], "--repo", repo,
                            "--out", FIXTURE["tmp"] / "samples.json", "--limit", 5)
    assert rc == 0 and samples and samples["count"] >= 1, samples
    FIXTURE["samples"] = samples
    rc, prep, _, _ = run(SCRIPTS["forward-bench.py"], "prepare",
                         "--samples", FIXTURE["tmp"] / "samples.json",
                         "--repo", repo, "--out", FIXTURE["tmp"] / "prepared")
    assert rc == 0 and prep, prep
    per = {}
    manifest = json.loads(Path(prep["manifest"]).read_text(encoding="utf-8"))
    for entry in manifest:
        blob = []
        for name in entry["diffs"]:
            rc_r, rules_r, _, _ = run(SCRIPTS["deterministic-rules.py"],
                                      "--diff-file", FIXTURE["tmp"] / "prepared" / name)
            assert rc_r == 0, rules_r
            blob.extend(rules_r["findings"])
        per[entry["sample_id"]] = blob
    (FIXTURE["tmp"] / "findings-per-sample.json").write_text(
        json.dumps({"samples": per}, ensure_ascii=False), encoding="utf-8")
    FIXTURE["manifest"] = FIXTURE["tmp"] / "prepared" / "manifest.json"
    FIXTURE["findings-per-sample"] = FIXTURE["tmp"] / "findings-per-sample.json"
    rc_j, judge, _, _ = run(SCRIPTS["forward-bench.py"], "judge",
                            "--findings", FIXTURE["findings-per-sample"],
                            "--prepared", FIXTURE["manifest"], "--repo", repo)
    assert rc_j == 0 and judge, judge
    FIXTURE["judge"] = judge
    samples_data = json.loads((FIXTURE["tmp"] / "samples.json").read_text(encoding="utf-8"))
    baseline = {
        "samples": samples_data["samples"],
        "metrics": {"recall": judge["recall"], "hits": judge["hits"]},
        "sample_ids": [s["fix_commit"] for s in samples_data["samples"]],
    }
    (FIXTURE["tmp"] / "baseline.json").write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    FIXTURE["baseline"] = FIXTURE["tmp"] / "baseline.json"

# tearDownModule 有意取消：共享夹具每进程只建一次，逐模块 eager release
# 会在模块 1 结束就掐断后续模块（首跑实踩）；删除交 tmpspace 的 atexit 兜底。




def ensure_fixture():
    """每进程一次的夹具构建（共享单例：首模块构建，后续模块跳过）。"""
    if not FIXTURE.get("tmp"):
        setUpModule()
