#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SWRBench 适配器：中立评审语料导入 + 双评审臂打分桥（round-112，P0-2；round-114，P0 延伸）。

用途
----
把 ZZR0/SWRench（MIT，1000 真实 PR：500 有缺陷 + 500 干净）适配为仓内
slim 语料；确定性评审臂（deterministic-rules.py，38 规则）出 point-level
中立基线（round-112）；宿主评审臂（LLM host 文件协议）出 PR 级/point 级
F1（round-114，对标 SWR-Bench 论文 best overall F1 19.38% 与仓内记录的
CodeRabbit 59.4%/36.2%）。语料不入库（datasets/），只入 schema 校验产物。

检查项
------
  import 子命令  schema 校验 + slim 化（字段容错映射）+ 计数如实。
  score 子命令   已发布基线不动：逐样本确定性扫描（deterministic-rules
                 的 diff 通道，新文件行号）→ point-level recall + clean
                 噪声（round-112 已发布，代码与口径保持不变）。
  review 子命令  宿主评审臂跑批（CRA_LLM_PROVIDER=host 文件协议，幂等
                 id 缓存；--all-pending 一次写全部 prompt 后退出，宿主
                 批量填响应后重跑全命中续跑）；逐样本七要素 findings。
  judge 子命令   findings vs slim 语料 → 双级 F1：
                 PR 级=整 PR 二分类（change PR 有 ≥1 finding 记正例，
                 clean PR 有 ≥1 finding 记假正例，micro 聚合）；
                 point 级=变更点命中（论文口径：gt 变更被 ≥1 finding
                 命中记 TP、finding 不落任何 gt span 记 FP、gt 变更未
                 被命中记 FN；行号落 span 判命中，文件维度不要求——
                 slim 化时文件维度已压平，见 _snippet_spans）；
                 micro 主口径 + per-PR macro 平均参考口径并行输出。
                 --match semantic：LLM-judge 语义命中判定（rubric 写死：
                 finding 指向 gt 同一处代码且同一缺陷机制，行号偏移可容忍）；
                 host 协议跑批判卷，judge 与评审员同为宿主模型（自评上限）。

用法示例：
    python swrenbench-import.py import --data swr.jsonl --out datasets/swrenbench
    python swrenbench-import.py score --corpus datasets/swrenbench/swr-slim.jsonl \
        --out reports/_work/swr-score.json --limit 50
    python swrenbench-import.py review --corpus datasets/swrenbench/swr-slim.jsonl \
        --out reports/_work/swr-r114 --stride 10 --all-pending
    python swrenbench-import.py judge --corpus datasets/swrenbench/swr-slim.jsonl \
        --findings reports/_work/swr-r114/findings.json --match semantic \
        --out reports/_work/swr-r115 --all-pending

退出码：0=完成；1=WAIT_HOST_LLM（review：宿主待填响应，填好后原样重跑即续）与 judge 前置门禁拦截（empty_batch_no_evidence，D-053）；2=参数/输入错误。
stdout 输出单个 JSON 文档。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SELF = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
DR = SELF.parent.parent / "multi-agent-review" / "scripts" / "deterministic-rules.py"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _first_key(obj, candidates):
    for k in candidates:
        if k in obj:
            return k
    return None


def map_instance(raw):
    """SWRBench 原始字段 → slim schema（字段名容错：snapshot 键名可能演化）。"""
    diffs = []
    commits = raw.get("pr_commits") or []
    if isinstance(commits, dict):
        commits = commits.get("commits") or []
    for c in commits if isinstance(commits, list) else []:
        if not isinstance(c, dict):
            continue
        # SWRBench 实测：整提交 diff_text/diff 为「剥头」形态（路径行后
        # 直接 @@ hunk），需先标准化为标准 unified diff
        patch = c.get("diff_text") or c.get("diff") or ""
        if isinstance(patch, str) and patch.strip():
            for np in _normalize_stripped(patch):
                diffs.append({"file": "", "patch": np})
            continue
        fkey = _first_key(c, ("files", "diffs", "changed_files"))
        files = (c.get(fkey) or []) if fkey else []
        if isinstance(files, dict):
            files = list(files.values())
        for f in files if isinstance(files, list) else []:
            if not isinstance(f, dict):
                continue
            fp = f.get("patch") or f.get("diff") or ""
            fname = f.get("filename") or f.get("file") or ""
            if fp and fname:
                diffs.append({"file": fname, "patch": fp})
    changes = []
    for ch in raw.get("changes") or []:
        if not isinstance(ch, dict):
            continue
        intro = ch.get("change_introducing") or {}
        if not isinstance(intro, dict):
            intro = {}
        snippet = _first_key(intro, ("code_snippet", "snippet", "code")) or ""
        snippet = intro.get(snippet) if snippet else ""
        if not isinstance(snippet, str):
            snippet = json.dumps(snippet, ensure_ascii=False)
        changes.append({"change_type": ch.get("change_type", "?"),
                        "snippet": snippet or ""})
    return {
        "instance_id": raw.get("instance_id", "?"),
        "repo": raw.get("repo", "?"),
        "pr_title": raw.get("pr_title", ""),
        "change_introduced": bool(raw.get("change_introduced")),
        "changes": changes,
        "diffs": diffs,
    }

_ADDED_RE = re.compile(r"^\+([^+].*)$")
_NEWFILE_RE = re.compile(r"^\+\+\+ b/(\S+)")


def _added_lines(patch):
    """unified diff → [(new_line_no, text)]（新文件行号，剥 + 前缀）。"""
    out, lineno = [], 0
    for ln in patch.splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", ln)
        if m:
            lineno = int(m.group(1))
            continue
        if ln.startswith(("---", "+++")) or ln.startswith(("diff --git",
                                                           "index ")):
            continue
        if ln.startswith("+"):
            out.append((lineno, ln[1:]))
            lineno += 1
        elif ln.startswith("-"):
            continue
        elif ln.startswith("\\"):
            continue
        else:
            lineno += 1
    return out


_HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _normalize_stripped(patch):
    """SWRBench 剥头 diff（<path>\n@@ hunk...）→ 标准 unified diff 列表
    （每文件一段）。按 hunk 头的新旧行数精确消费体行，文件边界由计数
    对齐推出；已是标准头则原样返回。"""
    if patch.lstrip().startswith("diff --git"):
        return [patch]
    lines = patch.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        path = lines[i].strip()
        if not path or path.startswith("@@"):
            i += 1
            continue
        i += 1
        hunks = []
        while i < n and lines[i].startswith("@@"):
            m = _HUNK_RE.match(lines[i])
            if not m:
                i += 1
                continue
            oc = int(m.group(2)) if m.group(2) is not None else 1
            nc = int(m.group(4)) if m.group(4) is not None else 1
            body = lines[i + 1:i + 1 + oc + nc]
            i += 1 + oc + nc
            hunks.append((m.group(0).split("@@")[1].strip(), body))
        if not hunks:
            continue
        out.append("diff --git a/%s b/%s" % (path, path))
        out.append("--- a/%s" % path)
        out.append("+++ b/%s" % path)
        for header, body in hunks:
            out.append("@@ %s @@" % header)
            out.extend(body)
    return ["\n".join(out)] if out else []


def _snippet_spans_hunk(snippet):
    """SWRBench code_snippet（<file>
@@ -a,b +c,d @@ ...
<行>）→ 新文件
    行号集合：@@ 头定起点，+ 行计入、- 行不动、其余按上下文推进。"""
    spans = set()
    lineno = None
    for ln in snippet.splitlines():
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", ln)
        if m:
            lineno = int(m.group(1))
            continue
        if lineno is None:
            continue
        if ln.startswith("+++"):
            continue
        if ln.startswith("+"):
            spans.add(lineno)
            lineno += 1
        elif ln.startswith("-"):
            continue
        else:
            lineno += 1
    return spans


def _snippet_spans(patch, snippet):
    """ground-truth 引入代码 → 命中的新文件行号集合（hunk 头优先，
    无头时退回文本锚定）。"""
    spans = _snippet_spans_hunk(snippet)
    if spans:
        return spans
    added = _added_lines(patch)
    if not added or not snippet.strip():
        return set()
    want = [ln.strip() for ln in snippet.splitlines() if ln.strip()]
    if not want:
        return set()
    # 首个非平凡行做锚（strip 相等），随后允许 ±1 行错位连配
    hits = set()
    for i, (no, text) in enumerate(added):
        if text.strip() == want[0]:
            j, k = 1, no + 1
            while j < len(want) and i + j < len(added):
                no2, text2 = added[i + j]
                if text2.strip() != want[j]:
                    break
                k = max(k, no2)
                j += 1
            for m2 in range(j):
                hits.add(added[i + m2][0])
    return hits


def _run_deterministic(diffs, tmpdir):
    """把 PR diff 拼成单 diff 文件跑 38 规则，返回 findings。"""
    nl = chr(10)
    lines = []
    for d in diffs:
        patch = d["patch"]
        if not patch.endswith(nl):
            patch += nl
        lines.append(patch)
    fp = Path(tmpdir) / "pr.diff"
    fp.write_text(nl.join(lines), encoding="utf-8")
    p = subprocess.run([sys.executable, "-X", "utf8", str(DR),
                        "--diff-file", str(fp)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return []
    return d.get("findings") or []

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


def cmd_import(args):
    dp = Path(args.data)
    if not dp.is_file():
        _emit({"ok": False, "error": "数据文件不存在: %s" % dp})
        return 2
    n, n_change, n_clean, bad = 0, 0, 0, 0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slim = out / "swr-slim.jsonl"
    with dp.open(encoding="utf-8") as f,             slim.open("w", encoding="utf-8", newline=chr(10)) as g:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                raw = json.loads(ln)
            except ValueError:
                bad += 1
                continue
            s = map_instance(raw)
            if not s["instance_id"] or s["instance_id"] == "?":
                bad += 1
                continue
            n += 1
            n_change += 1 if s["change_introduced"] else 0
            n_clean += 0 if s["change_introduced"] else 1
            g.write(json.dumps(s, ensure_ascii=False) + chr(10))
    _emit({"ok": True, "total": n, "change": n_change, "clean": n_clean,
           "bad": bad, "slim": str(slim)})
    return 0


def cmd_score(args):
    cp = Path(args.corpus)
    if not cp.is_file():
        _emit({"ok": False, "error": "slim 语料不存在: %s" % cp})
        return 2
    samples = []
    with cp.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                samples.append(json.loads(ln))
    if args.limit and args.limit > 0:
        samples = samples[:args.limit]
    caught = total_changes = 0
    missed_types = {}
    clean_noise = {}
    per = []
    import tempfile
    with tempfile.TemporaryDirectory(prefix="swr-") as tmp:
        for s in samples:
            findings = _run_deterministic(s["diffs"], tmp)
            fset = {}
            for fd in findings:
                fset.setdefault(fd.get("file", ""), set()).add(
                    fd.get("line"))
            got = 0
            all_changes = 0
            for ch in s.get("changes") or []:
                spans = set()
                for d in s.get("diffs") or []:
                    spans |= _snippet_spans(d["patch"], ch.get("snippet", ""))
                if not spans:
                    continue
                all_changes += 1
                hit = any((fset.get(f) or set()) & spans
                          for f in fset)
                if hit:
                    got += 1
                else:
                    missed_types[ch.get("change_type", "?")] =                         missed_types.get(ch.get("change_type", "?"), 0) + 1
            caught += got
            total_changes += all_changes
            if not s["change_introduced"]:
                clean_noise[s["instance_id"]] = len(findings)
            per.append({"instance_id": s["instance_id"],
                        "change_introduced": s["change_introduced"],
                        "findings": len(findings),
                        "changes_located": all_changes,
                        "caught": got})
    precision_like = (1.0 if not clean_noise else
                      sum(1 for v in clean_noise.values() if v == 0)
                      / len(clean_noise))
    result = {"ok": True,
           "samples": len(samples),
           "point_recall": (round(caught / total_changes, 4)
                            if total_changes else None),
           "changes_total": total_changes, "caught": caught,
           "missed_by_type": dict(sorted(missed_types.items(),
                                         key=lambda kv: -kv[1])),
           "clean_prs": len(clean_noise),
           "clean_zero_noise": precision_like,
           "clean_noise_findings": sum(clean_noise.values()),
           "per": per[:5]}
    if args.out:
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline="\n")
        result["out"] = args.out
    _emit(result)
    return 0


# ---- 宿主评审臂（round-114）：模板沿用 reviewbench-eval HOST_* 口径（与 runner LLM 评审器同源）+ 只评审引入行约束。
SWR_SYSTEM = "你是只读代码评审员，只输出 JSON。"
SWR_USER_TMPL = ("你是通用维度的评审员，只评审本 PR 引入的变更（diff 的 + 行，新文件行号）。只依据材料，输出 JSON 数组，每项含 loc(文件:行号)/desc/evidence/severity(高|中|低)/confidence(高|中|低)/cause/fix。无问题输出 []。\n材料：\n%s")

def build_review_prompt(sample, max_chars):
    """样本 → (system, user, truncated)；材料先脱敏再截断。"""
    body = chr(10).join(d.get("patch", "") for d in (sample.get("diffs") or []))
    title = sample.get("pr_title") or ""
    head = "## PR: %s（%s）" % (sample.get("instance_id", "?"), sample.get("repo", "?"))
    if title:
        head += "：" + title
    material = redact(head + chr(10) + chr(10) + body)
    truncated = len(material) > max_chars
    return SWR_SYSTEM, SWR_USER_TMPL % material[:max_chars], truncated

def _parse_loc(loc):
    """loc 字符串 → (file, line|None)。"""
    if not isinstance(loc, str) or not loc.strip():
        return "", None
    loc = loc.strip()
    m = re.match(r"^(.*):(\d+)$", loc)
    if m:
        return m.group(1), int(m.group(2))
    return loc, None

FENCE_RE = re.compile(r"^```(?:json)?|```$", re.M)


def _parse_host_response(raw):
    """宿主响应 → findings 列表（容忍代码栅栏，同 reviewbench-eval 口径）。"""
    cleaned = FENCE_RE.sub("", (raw or "").strip()).strip()
    try:
        obj = json.loads(cleaned)
    except ValueError:
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if not m:
            return None
        try:
            fallback = json.loads(m.group(0))
        except ValueError:
            return None
    if isinstance(obj, dict):
        obj = obj.get("findings")
    return obj if isinstance(obj, list) else None

def cmd_review(args):
    cp = Path(args.corpus)
    if not cp.is_file():
        _emit({"ok": False, "error": "slim 语料不存在: %s" % cp})
        return 2
    samples = []
    with cp.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                samples.append(json.loads(ln))
    if args.stride and args.stride > 1:
        samples = samples[::args.stride]
    if args.limit and args.limit > 0:
        samples = samples[:args.limit]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CRA_LLM_PROVIDER"] = "host"
    sys.path.insert(0, str(ROOT))
    from llm import provider  # noqa: E402 - 治理壳 stdlib
    cfg = {}
    try:
        import tomllib
        cfg = tomllib.loads((ROOT / "skills" / "eval-harness" / "eval-config.toml")
                            .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    max_chars = args.max_chars if args.max_chars is not None else             cfg.get("review", {}).get("max_chars", 20000)
    findings_path = out_dir / "findings.json"
    grouped, errors, unparsed, metas, tasks = {}, [], [], [], []
    for s in samples:
        sid = s.get("instance_id", "?")
        system, user, truncated = build_review_prompt(s, max_chars)
        try:
            raw, meta = provider.complete(system, user,
                                          base_dir=out_dir / "llm-tasks")
        except provider.HostLLMPending as pending:
            tasks.append({"task_id": pending.task_id,
                          "prompt": pending.prompt_path,
                          "response": pending.response_path,
                          "sample_id": sid})
            if not args.all_pending:
                break
            continue
        if raw is None:
            errors.append("provider none: %s" % sid)
            continue
        items = _parse_host_response(raw)
        if items is None:
            unparsed.append(sid)
            grouped[sid] = []
            continue
        norm = []
        for f in items:
            if isinstance(f, dict):
                f.setdefault("engine", "host")
                f["sample_id"] = sid
                norm.append(f)
        grouped[sid] = norm
        metas.append({"sample_id": sid, "task_id": meta.get("task_id"),
                      "diff_chars": len(user), "truncated": truncated})
    if tasks:
        fp = findings_path
        fp.write_text(json.dumps({"reviewer": "host", "corpus": args.corpus,
                                  "stride": args.stride,
                                  "max_chars": args.max_chars,
                                  "batch_note": args.batch_note or "",
                                  "samples": grouped, "errors": errors,
                                  "unparsed": unparsed, "metas": metas},
                                 ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        _emit({"ok": False, "wait_host_llm": True,
               "pending_count": len(tasks), "tasks": tasks,
               "done_samples": len(grouped),
               "response_dir": str(out_dir / "llm-tasks"),
               "note": "宿主填响应后原样重跑即续（幂等 id 缓存；findings.json 每次重跑重建，响应改动需删 findings.json 重跑生效）"})
        return 1
    fp = findings_path
    fp.write_text(json.dumps({"reviewer": "host", "corpus": args.corpus,
                              "stride": args.stride, "max_chars": args.max_chars,
                              "batch_note": args.batch_note or "",
                              "samples": grouped, "errors": errors,
                              "unparsed": unparsed, "metas": metas},
                             ensure_ascii=False, indent=2),
                  encoding="utf-8", newline=chr(10))
    _emit({"ok": True, "reviewer": "host", "samples": len(grouped),
           "findings": sum(len(v) for v in grouped.values()),
           "unparsed": len(unparsed), "errors": len(errors),
           "out": str(findings_path)})
    return 0

def cmd_judge(args):
    cp = Path(args.corpus)
    if not cp.is_file():
        _emit({"ok": False, "error": " slim 语料不存在" if False else "slim 语料不存在: %s" % cp})
        return 2
    rows = {}
    with cp.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                s = json.loads(ln)
                rows[s.get("instance_id", "?")] = s
    fp = Path(args.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "findings 不存在: %s" % fp})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except ValueError:
        _emit({"ok": False, "error": "findings 不可解析: %s" % fp})
        return 2
    grouped = data.get("samples") or {}
    if not isinstance(grouped, dict):
        _emit({"ok": False, "error": "findings 形状错误：期望 samples 字典"})
        return 2
    order = [k for k in rows if k in grouped]
    if not order:
        _emit({"ok": False, "error": "findings 与语料无交集"})
        return 2
    # D-053 前置硬校验：全空批次必须有 batch_note（round-138 门禁）
    if all(not (grouped.get(k) or []) for k in order)             and not str(data.get("batch_note") or "").strip():
        _emit({"ok": False, "error": "empty_batch_no_evidence",
               "detail": "全 [] 批次且无 batch_note——宿主执行质量门禁拦截（D-053）；"
                          "重评并附批次依据或 --batch-note 说明"})
        return 1
    n_chg = n_cln = 0
    pr_tp = pr_fp = pr_fn = 0
    pt_tp = pt_fp = pt_fn = 0
    gt_total = findings_chg = unparseable_loc = 0
    macro_f1s = []
    macro_excluded = 0
    gt_by_type, hit_by_type = {}, {}
    for sid in order:
        row = rows[sid]
        flist = grouped.get(sid) or []
        if row.get("change_introduced"):
            n_chg += 1
            pts = []
            for ch in (row.get("changes") or []):
                sp = set()
                for d in (row.get("diffs") or []):
                    sp |= _snippet_spans(d.get("patch", ""), ch.get("snippet", ""))
                if sp:
                    pts.append((ch.get("change_type") or "?", sp))
            gt_total += len(pts)
            for cty, _ in pts:
                gt_by_type[cty] = gt_by_type.get(cty, 0) + 1
            hit_flags = [False] * len(pts)
            f_hits = 0
            for f in flist:
                _, ln = _parse_loc((f or {}).get("loc"))
                if ln is None:
                    unparseable_loc += 1
                    pt_fp += 1
                    continue
                if any(ln in sp for _, sp in pts):
                    f_hits += 1
                    for i, (_, sp) in enumerate(pts):
                        if ln in sp:
                            hit_flags[i] = True
                else:
                    pt_fp += 1
            pt_tp += sum(hit_flags)
            pt_fn += sum(1 for h in hit_flags if not h)
            for i, (cty, _) in enumerate(pts):
                if hit_flags[i]:
                    hit_by_type[cty] = hit_by_type.get(cty, 0) + 1
            if flist:
                pr_tp += 1
                findings_chg += len(flist)
                p_i = f_hits / len(flist)
                if pts:
                    r_i = sum(hit_flags) / len(pts)
                    macro_f1s.append(2 * p_i * r_i / (p_i + r_i)
                                     if (p_i + r_i) > 0 else 0.0)
                else:
                    macro_excluded += 1
            else:
                pr_fn += 1
                macro_f1s.append(0.0)
        else:
            n_cln += 1
            if flist:
                pr_fp += 1
    n_all = n_chg + n_cln
    def _prf(tp, fp, fn):
        p = tp / (tp + fp) if (tp + fp) else None
        r = tp / (tp + fn) if (tp + fn) else None
        f = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else None
        return p, r, f
    pr_p, pr_r, pr_f = _prf(pr_tp, pr_fp, pr_fn)
    pt_p, pt_r, pt_f = _prf(pt_tp, pt_fp, pt_fn)
    macro_mean = (sum(macro_f1s) / len(macro_f1s) if macro_f1s else None)
    per_type = {}
    for k in set(gt_by_type) | set(hit_by_type):
        gt = gt_by_type.get(k, 0)
        hit = hit_by_type.get(k, 0)
        per_type[k] = {"gt": gt, "hit": hit,
                       "recall": round(hit / gt, 4) if gt else None}
    result = {
        "ok": True, "mode": "swrenbench-judge",
        "reviewer": data.get("reviewer"),
        "stride": data.get("stride"),
        "n_evaluated": len(order), "n_change": n_chg, "n_clean": n_cln,
        "pr_level": {"tp": pr_tp, "fp": pr_fp, "fn": pr_fn,
                     "precision": None if pr_p is None else round(pr_p, 4),
                     "recall": None if pr_r is None else round(pr_r, 4),
                     "f1": None if pr_f is None else round(pr_f, 4)},
        "point_level": {"tp": pt_tp, "fp": pt_fp, "fn": pt_fn,
                        "precision": None if pt_p is None else round(pt_p, 4),
                        "recall": None if pt_r is None else round(pt_r, 4),
                        "f1": None if pt_f is None else round(pt_f, 4),
                        "gt_points": gt_total,
                        "findings_on_change_prs": findings_chg,
                        "unparseable_loc": unparseable_loc,
                        "macro_f1_mean": None if macro_mean is None else round(macro_mean, 4),
                        "macro_n": len(macro_f1s),
                        "macro_excluded": macro_excluded},
        "per_type": dict(sorted(per_type.items(), key=lambda kv: -kv[1]["gt"])),
        "errors": len(data.get("errors") or []),
        "unparsed": len(data.get("unparsed") or []),
        "note": "口径：PR 级=micro 二分类（change PR 有 findings 记 TP、clean 有记 FP）；"
                "point 级=论文口径变更点命中（gt 变更被 ≥1 finding 命中记 TP、"
                "finding 不落 gt span 记 FP；行号落 span 判命中，文件维度不要求）；"
                "clean PR 的 findings 不进 point 级；macro=change PR 逐 PR F1 平均"
                "（无预测且 gt 非空记 0，gt 空排除）",
    }
    if args.out:
        op = Path(args.out)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        result["out"] = args.out
    _emit(result)
    return 0

# ---- LLM-judge 臂（round-115）：语义命中判定，机械口径的行号偏移折损对照。
# 判卷 rubric 写死：命中=finding 指向 gt 变更同一处代码且缺陷机制相同（行号
# 偏移可容忍）；泛泛而谈/指向别的变更 = 不命中。循环性如实：judge 与评审员
# 同为宿主模型，语义数字是乐观上限（论文口径=第三方 judge）。
SWR_JUDGE_SYSTEM = "你是评审判定员，只输出 JSON。"
SWR_JUDGE_TMPL = ("你是盲判员：逐对判定预测 findings 是否「语义命中」ground-truth "
                  "变更点。命中=finding 指向 gt 变更同一处代码、描述同一缺陷机制；"
                  "行号有偏移可接受，泛泛而谈或指向其他变更不算。只依据材料，输出 "
                  "JSON 对象 {\"matches\": [{\"gt\": gt 序号, \"findings\": [finding 序号]}]}，"
                  "未命中的 gt 不出现在结果里。\n材料：\n%s")


def _dedupe_gt(sample):
    """gt 变更点归一化：同（片段, 类型）合并为一组（round-115 坑对策）。

    返回组列表 [{"type", "snippet", "members": [原始索引]}]，按首现序；
    不可定位（span 空）的条目剔除。
    """
    groups = []
    seen = {}
    for idx, ch in enumerate(sample.get("changes") or []):
        sp = set()
        for d in (sample.get("diffs") or []):
            sp |= _snippet_spans(d.get("patch", ""), ch.get("snippet", ""))
        if not sp:
            continue
        key = (ch.get("snippet") or "").strip()
        if key in seen:
            groups[seen[key]]["members"].append(idx)
            continue
        seen[key] = len(groups)
        groups.append({"type": ch.get("change_type") or "?",
                       "snippet": (ch.get("snippet") or "").strip(),
                       "members": [idx]})
    return groups


def build_judge_prompt(sample, findings, max_chars):
    """(sample, findings) → (system, user, truncated, groups)：归一化判卷材料。

    groups=[{"type", "snippet", "members": [原始索引]}]；命中组=命中其全部
    成员（同片段重复条目随组一并判定，判定一致性由结构保证）。
    """
    groups = _dedupe_gt(sample)
    lines = ["## ground-truth 变更点（本 PR 引入的缺陷）"]
    for k, g in enumerate(groups):
        extra = ("（同片段重复 x%d，一并判定）" % len(g["members"])
                 if len(g["members"]) > 1 else "")
        lines.append("[%d] 类型 %s%s" % (k, g["type"], extra))
        sn = g["snippet"]
        lines.append("    片段: %s" % (sn[:400] if sn else "(空)"))
    lines.append("")
    lines.append("## 预测 findings（评审器输出）")
    for i, f in enumerate(findings):
        f = f or {}
        lines.append("[%d] loc: %s" % (i, f.get("loc", "?")))
        lines.append("    desc: %s" % (f.get("desc", "") or "")[:400])
        ev = (f.get("evidence", "") or "")[:300]
        lines.append("    evidence: %s" % ev)
    lines.append("")
    lines.append("gt 变更组共 %d 组；预测 findings 共 %d 条。"
                 % (len(groups), len(findings)))
    material = redact(chr(10).join(lines))
    truncated = len(material) > max_chars
    return SWR_JUDGE_SYSTEM, SWR_JUDGE_TMPL % material[:max_chars], truncated, groups


def _parse_judge_response(raw):
    """判卷响应 → matches 列表（容忍代码栅栏；形状错返回 None）。"""
    cleaned = FENCE_RE.sub("", (raw or "").strip()).strip()
    try:
        obj = json.loads(cleaned)
    except ValueError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            return None
    ms = obj.get("matches") if isinstance(obj, dict) else None
    if not isinstance(ms, list):
        return None
    out = []
    for e in ms:
        if not isinstance(e, dict):
            continue
        gt = e.get("gt")
        fds = e.get("findings")
        if isinstance(gt, int) and isinstance(fds, list):
            out.append({"gt": gt,
                        "findings": [i for i in fds if isinstance(i, int)]})
    return out


def cmd_judge_semantic(args):
    cp = Path(args.corpus)
    if not cp.is_file():
        _emit({"ok": False, "error": "slim 语料不存在: %s" % cp})
        return 2
    rows = {}
    with cp.open(encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                s = json.loads(ln)
                rows[s.get("instance_id", "?")] = s
    fp = Path(args.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "findings 不存在: %s" % fp})
        return 2
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except ValueError:
        _emit({"ok": False, "error": "findings 不可解析: %s" % fp})
        return 2
    grouped = data.get("samples") or {}
    order = [k for k in rows if k in grouped
             and rows[k].get("change_introduced")]
    if all(not (grouped.get(k) or []) for k in order)             and not str(data.get("batch_note") or "").strip():
        _emit({"ok": False, "error": "empty_batch_no_evidence",
               "detail": "全 [] 批次且无 batch_note——宿主执行质量门禁拦截（D-053）"})
        return 1
    order = [k for k in rows if k in grouped
             and rows[k].get("change_introduced")
             and (grouped.get(k) or [])]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CRA_LLM_PROVIDER"] = "host"
    sys.path.insert(0, str(ROOT))
    from llm import provider  # noqa: E402 - 治理壳 stdlib
    tasks, judges, errors, unparsed = [], {}, [], []
    for sid in order:
        row = rows[sid]
        findings = grouped.get(sid) or []
        system, user, truncated, groups = build_judge_prompt(row, findings,
                                                             args.max_chars)
        if not groups:
            continue
        try:
            raw, meta = provider.complete(system, user,
                                          base_dir=out_dir / "llm-tasks")
        except provider.HostLLMPending as pending:
            tasks.append({"task_id": pending.task_id,
                          "prompt": pending.prompt_path,
                          "response": pending.response_path,
                          "sample_id": sid})
            if not args.all_pending:
                break
            continue
        matches = _parse_judge_response(raw)
        if matches is None:
            unparsed.append(sid)
            matches = []
        judges[sid] = {"matches": matches, "groups": groups,
                       "truncated": truncated}
    if tasks:
        (out_dir / "judge-tasks.json").write_text(json.dumps(
            {"tasks": tasks, "judges": judges, "errors": errors,
             "unparsed": unparsed}, ensure_ascii=False, indent=2),
            encoding="utf-8", newline=chr(10))
        _emit({"ok": False, "wait_host_llm": True,
               "pending_count": len(tasks), "tasks": tasks,
               "done_samples": len(judges),
               "response_dir": str(out_dir / "llm-tasks"),
               "note": "宿主填判卷响应后原样重跑即续"})
        return 1
    pt_tp = pt_fp = pt_fn = 0
    mem_tp = mem_fn = 0
    per_pr = {}
    for sid, j in judges.items():
        m = j["matches"]
        n_groups = len(j["groups"])
        n_members = sum(len(g["members"]) for g in j["groups"])
        hit_gt = sorted({e["gt"] for e in m if e["findings"]})
        matched_fds = {i for e in m for i in e["findings"]}
        pt_tp += len(hit_gt)
        pt_fn += n_groups - len(hit_gt)
        hit_members = sum(len(j["groups"][k]["members"])
                          for k in hit_gt if 0 <= k < n_groups)
        mem_tp += hit_members
        mem_fn += n_members - hit_members
        per_pr[sid] = {"groups": n_groups, "hit_groups": hit_gt,
                       "findings": len(grouped.get(sid) or []),
                       "matched_findings": sorted(matched_fds)}
        n_fds = len(grouped.get(sid) or [])
        pt_fp += n_fds - len(matched_fds)
    p = pt_tp / (pt_tp + pt_fp) if (pt_tp + pt_fp) else None
    r = pt_tp / (pt_tp + pt_fn) if (pt_tp + pt_fn) else None
    f = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else None
    result = {
        "ok": True, "mode": "swrenbench-judge-semantic",
        "reviewer": data.get("reviewer"),
        "stride": data.get("stride"),
        "n_judged": len(judges),
        "point_level_semantic": {
            "tp": pt_tp, "fp": pt_fp, "fn": pt_fn,
            "precision": None if p is None else round(p, 4),
            "recall": None if r is None else round(r, 4),
            "f1": None if f is None else round(f, 4),
            "gt_groups": sum(len(j["groups"]) for j in judges.values()),
            "gt_members": sum(len(g["members"]) for j in judges.values()
                              for g in j["groups"]),
            "member_ref": {
                "tp": mem_tp, "fn": mem_fn,
                "recall": (round(mem_tp / (mem_tp + mem_fn), 4)
                           if (mem_tp + mem_fn) else None)},
        },
        "per_pr": per_pr,
        "unparsed": unparsed, "errors": errors,
        "note": "口径：语义命中=finding 指向 gt 同一处代码且同一缺陷机制（行号偏移可容忍）；"
                "同（片段,类型）重复条目归一化为组，命中组=命中其全部成员（r115 坑对策）；"
                "主口径按组、member_ref 按成员折算仅参考；judge 与评审员同为宿主模型（自评上限）",
    }
    if args.out_json:
        op = Path(args.out_json)
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8", newline=chr(10))
        result["out"] = args.out_json
    _emit(result)
    return 0
def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="SWRBench 适配 + 确定性打分桥")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_imp = sub.add_parser("import", help="schema 校验 + slim 化")
    ap_imp.add_argument("--data", required=True)
    ap_imp.add_argument("--out", required=True)
    ap_sc = sub.add_parser("score", help="确定性评审器中立打分")
    ap_sc.add_argument("--corpus", required=True)
    ap_sc.add_argument("--out", default="")
    ap_sc.add_argument("--limit", type=int, default=0)
    ap_re = sub.add_parser("review", help="宿主评审臂跑批（host 文件协议）")
    ap_re.add_argument("--corpus", required=True)
    ap_re.add_argument("--out", required=True)
    ap_re.add_argument("--stride", type=int, default=1)
    ap_re.add_argument("--limit", type=int, default=0)
    ap_re.add_argument("--max-chars", type=int, default=None,
                       help="缺省读 eval-config.toml [review].max_chars")
    ap_re.add_argument("--all-pending", action="store_true")
    ap_re.add_argument("--batch-note", default="", help="批次依据说明（全空批次必填，D-053 门禁）")
    ap_ju = sub.add_parser("judge", help="findings → PR 级/point 级 F1（论文口径）")
    ap_ju.add_argument("--corpus", required=True)
    ap_ju.add_argument("--findings", required=True)
    ap_ju.add_argument("--out", default="")
    ap_ju.add_argument("--match", choices=["mechanical", "semantic"],
                       default="mechanical")
    ap_ju.add_argument("--out-json", default="")
    ap_ju.add_argument("--max-chars", type=int, default=20000)
    ap_ju.add_argument("--all-pending", action="store_true")
    args = ap.parse_args()
    if args.cmd == "import":
        return cmd_import(args)
    if args.cmd == "review":
        return cmd_review(args)
    if args.cmd == "judge":
        if args.match == "semantic":
            return cmd_judge_semantic(args)
        return cmd_judge(args)
    return cmd_score(args)


if __name__ == "__main__":
    sys.exit(main())
