#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ReviewBench 评测适配器：golden 判定清单 + 确定性/宿主评审跑分 + 双指标判定。

用途:
    把 ReviewBench 语料（round-34 接入，datasets/reviewbench/）接进评测链，
    补「语料在盘、判定缺环」的空档：
    - prepare: 本地 diffs/ + golden/ → manifest.json（每样本 gt 标识符集合，
      取自 golden tp × introduced-by-pr 标注行区间内的 diff + 行；gt 直接来自
      PR diff 本身，无需克隆 12 个外部仓库）。
    - run: 对每个样本的 PR diff 跑评审器。--reviewer deterministic（默认，
      子进程调 deterministic-rules.py）；--reviewer host 走宿主文件协议
      （CRA_LLM_PROVIDER=host：写 prompt 文件后 WAIT_HOST_LLM 暂停，宿主填
      <id>.response.md 后原样重跑即命中缓存续跑——provider.py 幂等 id，
      评审口径与 runner 的 LLM 评审器一致：loc/desc/evidence/severity/
      confidence/cause/fix 七要素）。
    - judge: findings vs manifest → 双指标（recall=hits/valid_samples、
      precision=grounded/claimed；与 forward-bench judge 同口径，weak 剔除
      分母——易错点 4）。

    判定口径（先写死再看数字）：golden 侧只取 tp_fp=="tp" 且 scope==
    "introduced-by-pr" 的标注（fp 与非本 PR 引入的不算 ground truth）；
    gt 标识符 = 标注行区间内 diff + 行的 >=6 字符标识符（剔除关键词与
    注释行）；finding 文本 blob 提到 >= min-tokens 个 gt 标识符（不区分
    大小写）算命中。golden 行号按新文件行号解释；标注区间与 diff + 行
    零交集的条目记进 manifest.unmatched（口径透明，不静默）。

用法示例:
    py reviewbench-eval.py prepare --corpus datasets/reviewbench --out <dir>
    py reviewbench-eval.py run --corpus datasets/reviewbench --out <dir>
    py reviewbench-eval.py run --corpus datasets/reviewbench --out <dir> --reviewer host
    py reviewbench-eval.py judge --findings <dir>/findings.json --prepared <dir>/manifest.json

退出码:
    0 = 成功
    1 = host 等待宿主模型填写响应（WAIT_HOST_LLM；填好后原样重跑即续）
    2 = 输入/环境错误（语料缺失/形状不符/评审器失败）
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "skills" / "multi-agent-review" / "scripts" / "deterministic-rules.py"

# 以下为跨脚本共享定义（doc-drift 问 2 追踪分叉）：IDENT_RE / COMMENT_PREFIX /
# KEYWORDS 复制自 forward-bench.py；SECRET_PATTERNS / redact / HUNK_RE /
# parse_diff 复制自 deterministic-rules.py，改动必须四处同步。
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{5,}")
COMMENT_PREFIX = ("#", "//", "/*", "*", "<!--")
KEYWORDS = {
    "return", "import", "from", "print", "self", "none", "true", "false", "while",
    "break", "except", "finally", "lambda", "global", "assert", "yield", "raise",
    "class", "def", "pass", "elif", "async", "await", "string", "number", "object",
    "public", "private", "protected", "static", "final", "func", "const", "var",
    "let", "package", "interface", "extends", "throws", "catch", "throw", "switch",
    "typeof", "instanceof", "select", "insert", "update", "delete", "where", "table",
    "values", "order", "group", "limit", "offset", "error", "value", "count",
    "index", "result", "length", "range", "dict", "list", "format", "encode",
    "decode", "print", "input", "super", "print", "type", "bool", "int", "float",
    "struct", "defer", "chan", "null", "void", "main", "printf", "println",
}

SECRET_PATTERNS = [
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|authorization)\s*\"?\s*[:=]\s*)([^\s,;#]{3,})"), r"\1<redacted>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"mysql://[^\s/:]+:[^@\s]+@"), "mysql://<redacted>@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted>"),
]


def redact(text):
    """密钥形态统一脱敏为 <redacted>。"""
    if not text:
        return text
    t = str(text)
    for pat, rep in SECRET_PATTERNS:
        t = pat.sub(rep, t)
    return t


HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(text):
    """解析 unified diff，返回 [{"path": str, "added": [(new_lineno, line_text)]}]。

    易错点 2：- 行一律丢弃，只保留 + 行参与符号统计，避免计数翻倍。
    """
    files = []
    cur = None
    newln = 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0].strip()
            if path.startswith('"') and path.endswith('"') and len(path) >= 2:
                path = path[1:-1]
            if path.startswith("b/"):
                path = path[2:]
            if path in ("", "/dev/null"):
                cur = None
            else:
                cur = {"path": path, "added": []}
                files.append(cur)
        elif raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m and cur is not None:
                newln = int(m.group(2))
        elif raw.startswith("+") and cur is not None:
            cur["added"].append((newln, raw[1:]))
            newln += 1
        elif (raw.startswith(" ") or raw == "") and cur is not None:
            newln += 1
    return files


# 宿主评审口径与 runner.py 的 LLM 评审器一致（system/user 措辞原样沿用）
HOST_SYSTEM = "你是只读代码评审员，只输出 JSON。"
HOST_USER_TMPL = ("你是通用维度的评审员。只依据材料，输出 JSON 数组，每项含 "
                  "loc(文件:行号)/desc/evidence/severity(高|中|低)/confidence(高|中|低)/"
                  "cause/fix。无问题输出 []。\n材料：\n%s")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_corpus(corpus, samples_path):
    """载入 samples 清单，形状不合格返回 (None, 原因)；成功返回 (样本列表, "")。"""
    samples_file = Path(samples_path) if samples_path else corpus / "samples-py.json"
    if not samples_file.is_file():
        return None, "样本清单不存在: %s" % samples_file
    try:
        raw = json.loads(samples_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, "样本清单不可读: %s" % exc
    samples = raw.get("samples") if isinstance(raw, dict) else raw
    if not isinstance(samples, list) or not samples:
        return None, "样本需为非空数组或含 samples 键"
    golden_dir = corpus / "golden"
    if not golden_dir.is_dir():
        return None, "golden 目录不存在: %s" % golden_dir
    return samples, ""


def _gt_identifiers(files, findings):
    """golden tp × introduced-by-pr 标注 → 该文件标注区间内 + 行的标识符。

    返回 (gt_tokens, matched_lines, unmatched_findings 数)。注释行剔除
    （它们不构成代码事实），关键词剔除（IDENT_RE 命中的 COMMON 词不算证据）。
    """
    added = {}
    for entry in files:
        added[entry["path"]] = entry["added"]
    gt, matched, unmatched = set(), 0, 0
    for f in findings:
        if f.get("tp_fp") != "tp" or f.get("scope") != "introduced-by-pr":
            continue
        path = str(f.get("file", "")).replace("\\", "/")
        lo, hi = int(f.get("start_line", 0)), int(f.get("end_line", 0))
        rows = added.get(path, [])
        in_range = [text for (no, text) in rows if lo <= no <= hi]
        if not in_range:
            unmatched += 1
            continue
        matched += 1
        for text in in_range:
            stripped = text.strip()
            if not stripped or stripped.startswith(COMMENT_PREFIX):
                continue
            for tok in IDENT_RE.findall(stripped):
                if tok.lower() not in KEYWORDS:
                    gt.add(tok)
    return gt, matched, unmatched


def mode_prepare(argv):
    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        _emit({"ok": False, "error": "语料目录不存在: %s" % corpus})
        return 2
    loaded, why = _load_corpus(corpus, argv.samples)
    if loaded is None:
        _emit({"ok": False, "error": why})
        return 2
    samples = loaded
    golden_dir = corpus / "golden"
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest, problems = [], []
    for sample in samples:
        pr_key = str(sample.get("sample_id", ""))
        diff_rel = str(sample.get("diff_path", "")).replace("\\", "/")
        diff_path = Path(diff_rel) if Path(diff_rel).is_absolute() else ROOT / diff_rel
        golden_path = golden_dir / ("%s.json" % pr_key)
        if not pr_key or not diff_path.is_file() or not golden_path.is_file():
            problems.append("样本不完整（缺 diff 或 golden）: %r" % pr_key)
            continue
        try:
            golden = json.loads(golden_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append("golden 不可读 %s: %s" % (pr_key, exc))
            continue
        gt, matched, unmatched = _gt_identifiers(
            parse_diff(diff_path.read_text(encoding="utf-8", errors="replace")),
            golden.get("findings") or [])
        manifest.append({
            "sample_id": pr_key,
            "files": sorted({str(f.get("file", "")).replace("\\", "/")
                             for f in golden.get("findings") or []}),
            "gt": sorted(gt),
            "golden_tp": matched,
            "golden_unmatched": unmatched,
            "expect_findings": sample.get("expect_findings"),
            "weak": len(gt) < 2,
        })
    out_path = out_dir / "manifest.json"
    out_path.write_text(json.dumps({"manifest": manifest}, ensure_ascii=False,
                                   indent=2), encoding="utf-8", newline="\n")
    _emit({"ok": True, "manifest": str(out_path), "samples": len(manifest),
           "weak": sum(1 for m in manifest if m["weak"]),
           "problems": problems,
           "note": "gt 只取 tp × introduced-by-pr 标注；golden_unmatched=标注"
                   "区间与 diff + 行零交集的条目数（行号坐标系或语料噪声）"})
    return 0


def _run_deterministic(diff_path, errors):
    proc = subprocess.run([sys.executable, str(RULES), "--diff-file",
                           str(diff_path)], shell=False, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=300, cwd=str(ROOT))
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        errors.append("deterministic 输出非 JSON: %s" % diff_path.name)
        return []
    return [dict(f, engine="deterministic") for f in data.get("findings", [])]


def _host_items_from_obj(obj):
    """obj → findings 列表或 None（dict 取 findings 键，list 直取）。"""
    if isinstance(obj, dict):
        obj = obj.get("findings")
    return obj if isinstance(obj, list) else None


def _host_findings_valid(obj):
    """complete_json 校验器：宿主 findings 必须是 list（或 dict 包装）。"""
    return isinstance(obj, (list, dict))


def mode_run(argv):
    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        _emit({"ok": False, "error": "语料目录不存在: %s" % corpus})
        return 2
    loaded, why = _load_corpus(corpus, argv.samples)
    if loaded is None:
        _emit({"ok": False, "error": why})
        return 2
    samples = loaded
    if argv.limit > 0:
        samples = samples[:argv.limit]
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    findings_path = out_dir / "findings.json"
    grouped, errors, metas = {}, [], []
    if argv.reviewer == "host":
        sys.path.insert(0, str(ROOT))
        from llm import provider  # noqa: E402 - 治理壳 stdlib
    for sample in samples:
        pr_key = str(sample.get("sample_id", ""))
        diff_rel = str(sample.get("diff_path", "")).replace("\\", "/")
        diff_path = Path(diff_rel) if Path(diff_rel).is_absolute() else ROOT / diff_rel
        if not pr_key or not diff_path.is_file():
            errors.append("样本缺 sample_id 或 diff: %r" % pr_key)
            continue
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
        if argv.reviewer == "host":
            # 硬约束 5：材料送宿主前统一脱敏，后截断（与 runner 同序）
            material = redact("## PR: %s\n\n## Diff（+ 行为本 PR 引入的变更）\n\n%s"
                              % (sample.get("title", pr_key), diff_text))
            truncated = len(material) > argv.max_chars
            user = HOST_USER_TMPL % material[:argv.max_chars]
            try:
                obj, meta = provider.complete_json(HOST_SYSTEM, user,
                                                   base_dir=out_dir / "llm-tasks",
                                                   validate=_host_findings_valid)
            except provider.HostLLMPending as pending:
                findings_path.write_text(
                    json.dumps({"samples": grouped, "reviewer": argv.reviewer,
                                "errors": errors},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
                _emit({"ok": False, "wait_host_llm": True,
                       "task_id": pending.task_id,
                       "prompt": pending.prompt_path,
                       "response": pending.response_path,
                       "pending_sample": pr_key,
                       "done_samples": sorted(grouped),
                       "note": "宿主填写响应文件后原样重跑即续（幂等 id 缓存）"})
                return 1
            items = _host_items_from_obj(obj)
            if items is None:
                errors.append("host 响应不可解析（记零 findings）: %s" % pr_key)
                items = []
            for f in items:
                if isinstance(f, dict):
                    f.setdefault("engine", "host")
                    f["sample_id"] = pr_key
            grouped[pr_key] = [f for f in items if isinstance(f, dict)]
            metas.append({"sample_id": pr_key, "provider": meta.get("provider"),
                          "task_id": meta.get("task_id"),
                          "diff_chars": len(diff_text), "truncated": truncated})
        else:
            entries = _run_deterministic(diff_path, errors)
            for f in entries:
                f["sample_id"] = pr_key
            grouped[pr_key] = entries
            metas.append({"sample_id": pr_key, "engine": "deterministic",
                          "findings": len(entries)})
    findings_path.write_text(
        json.dumps({"samples": grouped, "reviewer": argv.reviewer,
                    "errors": errors}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    _emit({"ok": True, "findings": str(findings_path),
           "reviewer": argv.reviewer, "samples_total": len(samples),
           "samples_with_findings": sum(1 for v in grouped.values() if v),
           "errors": errors, "meta": metas})
    return 0


def mode_judge(argv):
    ppath = Path(argv.prepared)
    if ppath.is_dir():
        ppath = ppath / "manifest.json"
    if not ppath.is_file():
        _emit({"ok": False, "error": "manifest 不存在: %s" % ppath})
        return 2
    try:
        manifest = json.loads(ppath.read_text(encoding="utf-8")).get("manifest", [])
        findings = json.loads(Path(argv.findings).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "输入不可读: %s" % exc})
        return 2
    grouped = findings.get("samples", findings) if isinstance(findings, dict) else findings
    if not isinstance(grouped, dict):
        _emit({"ok": False, "error": "findings 形状错误：期望 {\"samples\": {样本: [...]}}"})
        return 2
    per_sample, weak = [], []
    hits, valid = 0, 0
    for entry in manifest:
        sha = entry["sample_id"]
        gt = entry.get("gt", [])
        sample_findings = grouped.get(sha) or []
        claimed = bool(sample_findings)
        blob = json.dumps(sample_findings, ensure_ascii=False).lower()
        matched = [t for t in gt if t.lower() in blob]
        if entry.get("weak") or len(gt) < 2:
            weak.append({"sample_id": sha, "gt_tokens": len(gt),
                         "matched": matched})
            per_sample.append({"sample_id": sha, "claimed": claimed,
                               "hit": None, "matched": matched, "weak": True})
            continue
        valid += 1
        hit = len(matched) >= argv.min_tokens
        if hit:
            hits += 1
        per_sample.append({"sample_id": sha, "claimed": claimed, "hit": hit,
                           "matched": matched, "weak": False,
                           "golden_tp": entry.get("golden_tp")})
    claimed_n = sum(1 for p in per_sample if p["claimed"])
    grounded_n = sum(1 for p in per_sample if p["claimed"] and p["hit"])
    claimed_not_grounded = claimed_n - grounded_n
    recall = round(hits / valid, 4) if valid else None
    precision = round(grounded_n / claimed_n, 4) if claimed_n else None
    _emit({
        "ok": valid > 0,
        "mode": "reviewbench-judge",
        "reviewer": findings.get("reviewer") if isinstance(findings, dict) else None,
        "recall": recall,
        "precision": precision,
        "claimed": claimed_n,
        "grounded": grounded_n,
        "claimed_but_not_grounded": claimed_not_grounded,
        "hits": hits,
        "valid_samples": valid,
        "weak_samples": len(weak),
        "weak": weak,
        "per_sample": per_sample,
        "threshold": argv.min_tokens,
        "note": "口径：golden tp × introduced-by-pr；recall=hits/valid_samples；"
                "precision=grounded/claimed；weak 剔除分母；双指标必须同时输出",
    })
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="ReviewBench 评测适配器")
    sub = parser.add_subparsers(dest="mode", required=True)
    p_prep = sub.add_parser("prepare", help="golden → 判定清单 manifest.json")
    p_prep.add_argument("--corpus", required=True, help="datasets/reviewbench 目录")
    p_prep.add_argument("--samples", default="", help="样本清单（缺省 corpus/samples-py.json）")
    p_prep.add_argument("--out", required=True)
    p_run = sub.add_parser("run", help="逐样本跑评审器（findings.json）")
    p_run.add_argument("--corpus", required=True)
    p_run.add_argument("--samples", default="", help="样本清单（缺省 corpus/samples-py.json）")
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--reviewer", default="deterministic",
                       choices=("deterministic", "host"),
                       help="deterministic=硬规则；host=宿主文件协议（CRA_LLM_PROVIDER=host）")
    p_run.add_argument("--max-chars", dest="max_chars", type=int, default=8000,
                       help="宿主材料截断上限（脱敏后）")
    p_run.add_argument("--limit", type=int, default=0, help="样本数上限（0=不限）")
    p_judge = sub.add_parser("judge", help="findings vs manifest 双指标")
    p_judge.add_argument("--findings", required=True)
    p_judge.add_argument("--prepared", required=True, help="manifest.json 或其目录")
    p_judge.add_argument("--min-tokens", dest="min_tokens", type=int, default=2,
                         help="命中所需 gt 标识符个数下限")
    argv = parser.parse_args()
    if argv.mode == "prepare":
        return mode_prepare(argv)
    if argv.mode == "run":
        return mode_run(argv)
    return mode_judge(argv)


if __name__ == "__main__":
    sys.exit(main())
