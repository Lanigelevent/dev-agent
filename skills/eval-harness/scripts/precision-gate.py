#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评审精度护栏：ReviewBench 固定语料上的 precision 下限与基线趋势对账。

用途:
    把 ROADMAP §7 的护栏「评审 precision 不低于 0.65（规则口径）且趋势不降」
    从口头约定变成可执行门禁：在固定 ReviewBench 语料（MIT，python 子集
    12 样例）上跑确定性评审器，判分后与入仓基线（precision-baseline.json）
    对账。检查四项：
    - precision_floor：precision ≥ floor（缺省 0.65，来自 ROADMAP §7）；
    - precision_trend：precision ≥ 基线 − tolerance（缺省 0.01，抗舍入抖动）；
    - sample_drift：valid_samples 必须与基线一致（分母变了不可比）；
    - reviewer_match：评审器必须与基线一致（缺省 deterministic）。
    D-047 语料 pin（schema precision-baseline/2）：基线 corpus 块钉住上游
    revision（git HEAD）与逐文件 sha256（样本清单 / manifest / 选定 diff /
    golden），run 与 check --corpus 先验 pin 再对账——pin 不符即 code=2，
    防止「悄悄换了语料、数字仍然漂亮」。
    语料在 datasets/（不入库、CI 不跑）；门禁在语料缺失时明确 code=2，
    不静默跳过、不伪造 PASS。

用法示例:
    py precision-gate.py run --corpus datasets/reviewbench --out reports/_work/precision-r62
    py precision-gate.py check --judge reports/_work/precision-r62/judge.json
    py precision-gate.py check --judge <judge.json> --corpus datasets/reviewbench

退出码:
    0 = PASS（四项检查全过；带语料时 pin 也通过）
    1 = 护栏失败（BELOW_FLOOR / DRIFT / SAMPLE_DRIFT / REVIEWER_MISMATCH）
    2 = 输入/环境错误（语料或文件缺失、pin 不符、评测器失败、聚合形状不符）
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EVAL = Path(__file__).resolve().parent / "reviewbench-eval.py"
DEFAULT_BASELINE = ROOT / "skills" / "eval-harness" / "precision-baseline.json"
PROMPT_WATCH = ROOT / "skills" / "eval-harness" / "prompt-watch.json"


def _prompt_fingerprints():
    """AB-03（r198，promptfoo「声明式变更即红」概念的确定性形态）：
    对声明面逐文件 sha256；未声明 prompt-watch.json → 返回 None（不检查）。"""
    if not PROMPT_WATCH.is_file():
        return None
    try:
        watch = json.loads(PROMPT_WATCH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("prompt-watch.json 不可读: %s" % exc)
    out = {}
    for rel in watch.get("watched", []):
        p = ROOT / rel
        if not p.is_file():
            out[rel] = "missing"
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def _prompt_regression_check(baseline):
    """第五项检查：提示面指纹 vs 基线。返回检查 dict（PASS/FAIL/SKIPPED）。"""
    current = _prompt_fingerprints()
    if current is None:
        return {"id": "prompt_regression", "status": "SKIPPED",
                "note": "未声明 prompt-watch.json（提示面回归门未启用）"}
    base_fp = baseline.get("prompt_fingerprints")
    if not base_fp:
        return {"id": "prompt_regression", "status": "FAIL",
                "note": "声明了提示面但基线无指纹——请跑 record-baseline 固化",
                "current": current}
    changed = [rel for rel, fp in current.items() if base_fp.get(rel) != fp]
    return {"id": "prompt_regression",
            "status": "FAIL" if changed else "PASS",
            "changed": changed,
            "note": ("提示面已变更（fingerprint 不一致）——请重跑基线评测并 "
                     "record-baseline 固化新指纹与指标") if changed else
                    "提示面指纹与基线一致"}


def _emit(payload):
    posix = {k: (str(v).replace("\\", "/") if isinstance(v, Path) else v)
             for k, v in payload.items()}
    sys.stdout.write(json.dumps(posix, ensure_ascii=False, indent=2) + "\n")
    return 0 if posix.get("ok") else 1


def _read_json(path, what):
    p = Path(path)
    if not p.is_file():
        raise ValueError("%s 不存在: %s" % (what, p))
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("%s 不可读: %s (%s)" % (what, p, exc))


def _eval_step(args, what):
    """调用 reviewbench-eval.py 子命令，返回其 stdout JSON；失败抛 ValueError。"""
    try:
        proc = subprocess.run(
            [sys.executable, str(EVAL)] + args,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("%s 调用失败: %s" % (what, exc))
    if proc.returncode != 0:
        raise ValueError("%s 退出码 %d: %s" % (
            what, proc.returncode, (proc.stderr or proc.stdout or "").strip()[:400]))
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise ValueError("%s 输出不是单个 JSON: %s" % (what, exc))


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_corpus_pin(corpus, baseline):
    """D-047：按基线 corpus 块校验语料 revision 与逐文件 sha256。

    返回 (pin_info, problems)；基线未钉 pin 时返回 (None, [])（旧基线兼容，
    交接物检查由发布签核口径兜底）。problems 非空由调用方转 code=2。
    """
    pins = baseline.get("corpus")
    if not isinstance(pins, dict):
        return None, []
    revision = str(pins.get("revision") or "")
    files = pins.get("files") or {}
    problems = []
    if not revision or not isinstance(files, dict) or not files:
        raise ValueError("基线 corpus 块缺 revision/files，无法校验语料 pin")
    try:
        proc = subprocess.run(
            ["git", "-C", str(corpus), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("语料 pin 校验无法执行 git: %s" % exc)
    actual = (proc.stdout or "").strip()
    if proc.returncode != 0:
        problems.append("语料目录不是可解析的 git 仓库（git rev-parse 失败）")
    elif actual != revision:
        problems.append("revision 不匹配: 期望 %s 实得 %s" % (revision, actual))
    verified = 0
    for rel, expect in sorted(files.items()):
        target = Path(corpus) / rel
        if not target.is_file():
            problems.append("语料缺文件: %s" % rel)
            continue
        got = _sha256_file(target)
        if got != expect:
            problems.append("sha256 不匹配: %s（期望 %s 实得 %s）"
                            % (rel, expect, got))
            continue
        verified += 1
    pin = {
        "status": "PASS" if not problems else "PIN_MISMATCH",
        "revision": revision,
        "actual_revision": actual,
        "files_expected": len(files),
        "files_verified": verified,
        "problems": problems,
    }
    return pin, problems


def _verdict(judge, baseline):
    """四项检查。返回 (ok, checks, failed)。"""
    if not isinstance(judge, dict) or not judge.get("ok"):
        raise ValueError("judge 结果形状不符（ok!=true）")
    for key in ("precision", "valid_samples", "reviewer"):
        if key not in judge:
            raise ValueError("judge 结果缺字段: %s" % key)
    floor = float(baseline.get("floor", 0.65))
    tolerance = float(baseline.get("tolerance", 0.01))
    precision = float(judge.get("precision"))
    valid = int(judge.get("valid_samples"))
    reviewer = str(judge.get("reviewer"))
    base_precision = float(baseline.get("precision"))
    base_valid = int(baseline.get("valid_samples"))
    base_reviewer = str(baseline.get("reviewer", "deterministic"))

    checks = [
        {
            "id": "precision_floor",
            "status": "PASS" if precision >= floor else "BELOW_FLOOR",
            "value": precision, "floor": floor,
        },
        {
            "id": "precision_trend",
            "status": "PASS" if precision >= base_precision - tolerance else "DRIFT",
            "value": precision, "baseline": base_precision,
            "tolerance": tolerance,
        },
        {
            "id": "sample_drift",
            "status": "PASS" if valid == base_valid else "SAMPLE_DRIFT",
            "value": valid, "baseline": base_valid,
        },
        {
            "id": "reviewer_match",
            "status": "PASS" if reviewer == base_reviewer else "REVIEWER_MISMATCH",
            "value": reviewer, "baseline": base_reviewer,
        },
    ]
    failed = [c["id"] for c in checks if c["status"] != "PASS"]
    return (not failed), checks, failed


def _payload(judge, baseline, judge_path, pin=None):
    ok, checks, failed = _verdict(judge, baseline)
    status = "PASS" if ok else checks[[c["id"] for c in checks].index(failed[0])]["status"]
    payload = {
        "ok": ok,
        "status": status,
        "failed": failed,
        "checks": checks,
        "metrics": {
            "precision": judge.get("precision"),
            "recall": judge.get("recall"),
            "valid_samples": judge.get("valid_samples"),
            "weak_samples": judge.get("weak_samples"),
            "claimed": judge.get("claimed"),
            "grounded": judge.get("grounded"),
            "hits": judge.get("hits"),
            "reviewer": judge.get("reviewer"),
        },
        "baseline_precision": baseline.get("precision"),
        "judge": str(judge_path).replace("\\", "/"),
        "note": "语料不入库，本门禁在本地/发布签核跑；格式：基准/样本量/判分口径/成本/完整性告警",
    }
    if pin is not None:
        payload["corpus_pin"] = pin
    return payload


def cmd_run(argv):
    out_dir = Path(argv.out)
    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        raise ValueError("语料目录不存在: %s" % corpus)
    baseline = _read_json(argv.baseline, "基线")
    pin, problems = _verify_corpus_pin(corpus, baseline)
    if problems:
        raise ValueError("语料 pin 校验失败（D-047）: " + "；".join(problems))
    out_dir.mkdir(parents=True, exist_ok=True)
    common = ["--corpus", str(corpus), "--out", str(out_dir)]
    if argv.samples:
        common += ["--samples", str(Path(argv.samples))]
    prep = _eval_step(["prepare"] + common, "prepare")
    if not prep.get("ok"):
        raise ValueError("prepare 失败: %s" % prep.get("problems"))
    run = _eval_step(["run"] + common, "run")
    if not run.get("ok"):
        raise ValueError("run 失败: %s" % run.get("errors"))
    findings = run.get("findings") or str(out_dir / "findings.json")
    judge = _eval_step(
        ["judge", "--findings", str(findings),
         "--prepared", str(out_dir / "manifest.json")], "judge")
    judge_path = out_dir / "judge.json"
    judge_path.write_text(
        json.dumps(judge, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _emit(_payload(judge, baseline, judge_path, pin))


def cmd_check(argv):
    judge = _read_json(argv.judge, "judge 结果")
    baseline = _read_json(argv.baseline, "基线")
    pin = None
    corpus = str(getattr(argv, "corpus", "") or "")
    if corpus:
        if not Path(corpus).is_dir():
            raise ValueError("语料目录不存在: %s" % corpus)
        pin, problems = _verify_corpus_pin(Path(corpus), baseline)
        if problems:
            raise ValueError("语料 pin 校验失败（D-047）: " + "；".join(problems))
    payload = _payload(judge, baseline, Path(argv.judge), pin)
    # AB-03（r198）：第五项检查——提示面指纹回归（声明式变更即红）
    payload["checks"].append(_prompt_regression_check(baseline))
    if payload["checks"][-1]["status"] == "FAIL":
        payload["ok"] = False
        payload["status"] = "PROMPT_DRIFT"
        payload["failed"] = payload.get("failed", []) + ["prompt_regression"]
    return _emit(payload)


def cmd_record_baseline(argv):
    """AB-03：固化提示面指纹 + judge 指标到基线（增量更新，保留 floor/tolerance）。"""
    judge = _read_json(argv.judge, "judge 结果")
    baseline = _read_json(argv.baseline, "基线")
    fps = _prompt_fingerprints()
    baseline["prompt_fingerprints"] = fps or {}
    baseline["prompt_recorded"] = fps is not None
    for key in ("precision", "valid_samples", "reviewer"):
        if key in judge:
            baseline[key] = judge[key]
    Path(argv.baseline).write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return _emit({"ok": True, "recorded": True,
                  "watched": sorted((fps or {}).keys()),
                  "metrics": {k: baseline.get(k) for k in
                              ("precision", "valid_samples", "reviewer")}})


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="评审精度护栏（ReviewBench 固定语料）")
    sub = parser.add_subparsers(dest="verb", required=True)
    p_run = sub.add_parser("run", help="跑确定性评测并对账基线")
    p_run.add_argument("--corpus", default="datasets/reviewbench",
                       help="ReviewBench 语料目录（缺省 datasets/reviewbench）")
    p_run.add_argument("--samples", default="", help="样本清单（缺省语料内 samples-py.json）")
    p_run.add_argument("--out", required=True, help="评测产物目录（manifest/findings/judge）")
    p_run.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    p_run.set_defaults(func=cmd_run)
    p_check = sub.add_parser("check", help="对既有 judge.json 对账基线")
    p_check.add_argument("--judge", required=True)
    p_check.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    p_check.add_argument("--corpus", default="",
                         help="可选：给语料目录则先校验 D-047 pin（revision + sha256）")
    p_check.set_defaults(func=cmd_check)
    p_rec = sub.add_parser("record-baseline",
                           help="固化提示面指纹 + judge 指标到基线（AB-03）")
    p_rec.add_argument("--judge", required=True)
    p_rec.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    p_rec.set_defaults(func=cmd_record_baseline)
    argv = parser.parse_args()
    try:
        return argv.func(argv)
    except ValueError as exc:
        sys.stderr.write("[precision-gate] %s\n" % exc)
        _emit({"ok": False, "status": "ERROR", "error": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
