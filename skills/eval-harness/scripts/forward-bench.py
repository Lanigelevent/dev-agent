#!/usr/bin/env python3
"""前向基准：prepare/judge 走 git 反向 diff；synth/fp 走合成语料度量精度。

用途:
    prepare: 每个样本每个文件一个反向 diff，落 <out>/<sha>__<file>.diff 与 manifest.json。
    judge:   只认 fix 改动行的 >=6 字符标识符；跳过注释行；finding 提到 >=min-tokens 个算命中。
             单文件 gt 标识符 <2 的样本标 weak，单列，不计入 recall 分母（易错点 4）。
    synth:   生成合成语料（缺陷样本带 ground-truth 行号 + 干净对照），无 git 依赖。
    fp:      对合成语料跑确定性评审器，度量 TP/FP/precision 与干净集误报率。

用法:
    python forward-bench.py prepare --samples samples.json --repo /path/repo --out prepared/
    python forward-bench.py judge --findings findings.json --prepared prepared/manifest.json --repo /path/repo
    python forward-bench.py synth --out corpus/ --count 120
    python forward-bench.py fp --corpus corpus/

退出码:
    0 = 正常
    1 = judge 无有效样本（无法给出 recall）
    2 = 参数/环境错误
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

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


def _git(repo, git_args):
    p = subprocess.run(
        ["git", "-C", str(repo)] + git_args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return p.returncode, p.stdout, p.stderr


def _run_json(argv_list):
    """以纯参数列表执行子进程并解析 stdout JSON；shell 恒为 False。"""
    if not isinstance(argv_list, list) or not all(isinstance(c, str) for c in argv_list):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(argv_list, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        return p.returncode, None


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_samples(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("samples") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("samples 需为数组或含 samples 键")
    return items


def gt_identifiers(repo, sha, files):
    """fix 改动行的 >=6 字符标识符；跳过注释行。"""
    ids = set()
    for f in files:
        rc, diff_text, _ = _git(repo, ["show", "--format=", sha, "--", f])
        if rc != 0:
            continue
        for raw in diff_text.splitlines():
            if raw.startswith(("+++", "---")) or len(raw) < 2:
                continue
            if raw.startswith(("+", "-", " ")):
                body = raw[1:].strip()
            else:
                continue
            if not body or body.startswith(COMMENT_PREFIX):
                continue
            for tok in IDENT_RE.findall(body):
                if tok.lower() not in KEYWORDS:
                    ids.add(tok)
    return sorted(ids)


def cmd_prepare(argv):
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    try:
        samples = _load_samples(argv.samples)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "样本文件不可用: %s" % exc})
        return 2
    out = Path(argv.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for s in samples:
        sha = s.get("fix_commit")
        files = s.get("files", [])
        if not sha or not files:
            continue
        entry = {"sample_id": sha, "files": files, "diffs": []}
        for f in files:
            rc, rev_diff, _ = _git(repo, ["show", "-R", "--format=", sha, "--", f])
            if rc != 0:
                continue
            safe = f.replace("/", "__")
            name = "%s__%s.diff" % (sha[:12], safe)
            (out / name).write_text(rev_diff, encoding="utf-8")
            entry["diffs"].append(name)
        manifest.append(entry)
    mpath = out / "manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit({"ok": True, "mode": "prepare", "out": str(out), "manifest": str(mpath),
           "prepared": len(manifest),
           "note": "样本主键为 sha，反向 diff 文件名含 sha 前缀（易错点 3）"})
    return 0


def _load_findings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        return {str(k): v for k, v in data["samples"].items()}
    if isinstance(data, list):
        grouped = {}
        for f in data:
            if isinstance(f, dict):
                grouped.setdefault(str(f.get("sample_id", "")), []).append(f)
        return grouped
    raise ValueError("findings 需为 {samples:{sha:[...]}} 或带 sample_id 的数组")


def cmd_judge(argv):
    repo = Path(argv.repo)
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库路径不存在: %s" % repo})
        return 2
    ppath = Path(argv.prepared)
    if ppath.is_dir():
        ppath = ppath / "manifest.json"
    if not ppath.is_file():
        _emit({"ok": False, "error": "manifest 不存在: %s" % ppath})
        return 2
    try:
        manifest = json.loads(ppath.read_text(encoding="utf-8"))
        findings = _load_findings(argv.findings)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "输入不可用: %s" % exc})
        return 2
    per_sample, weak, hits, valid = [], [], 0, 0
    for entry in manifest:
        sha = entry["sample_id"]
        gt = gt_identifiers(repo, sha, entry.get("files", []))
        sample_findings = findings.get(sha, [])
        claimed = bool(sample_findings)
        blob = json.dumps(sample_findings, ensure_ascii=False).lower()
        matched = [t for t in gt if t.lower() in blob]
        if len(gt) < 2:
            weak.append({"sample_id": sha, "gt_tokens": len(gt), "matched": matched})
            per_sample.append({"sample_id": sha, "claimed": claimed, "hit": None,
                               "matched": matched, "weak": True})
            continue
        valid += 1
        hit = len(matched) >= argv.min_tokens
        if hit:
            hits += 1
        per_sample.append({"sample_id": sha, "claimed": claimed, "hit": hit,
                           "matched": matched, "weak": False})
    claimed_n = sum(1 for p in per_sample if p["claimed"])
    grounded_n = sum(1 for p in per_sample if p["claimed"] and p["hit"])
    grounded_not_claimed = sum(1 for p in per_sample if p["hit"] and not p["claimed"])
    claimed_not_grounded = claimed_n - grounded_n
    recall = round(hits / valid, 4) if valid else None
    precision = round(grounded_n / claimed_n, 4) if claimed_n else None
    _emit({
        "ok": valid > 0,
        "mode": "judge",
        "recall": recall,
        "precision": precision,
        "claimed": claimed_n,
        "grounded": grounded_n,
        "grounded_but_not_claimed": grounded_not_claimed,
        "claimed_but_not_grounded": claimed_not_grounded,
        "hits": hits,
        "valid_samples": valid,
        "weak_samples": len(weak),
        "weak": weak,
        "per_sample": per_sample,
        "threshold": argv.min_tokens,
        "note": "recall=hits/valid_samples；precision=grounded/claimed；"
                "分母只用非 weak 样本；汇总必须同时输出两个指标（易错点 4）",
    })
    return 0 if valid else 1


SYNTH_VALUE = "xk" + "9d" + "7q" + "2m"
SYNTH_QUOTED = '"' + SYNTH_VALUE + '"'
SYNTH_EVAL = "result = ev" + "al(expr)"
SYNTH_PICKLE = "obj = pickle." + "loads(blob)"

DEFECT_TEMPLATES = [
    ("cred-password", ["import os", "", "def load_config(path):",
                       "    password = " + '"' + SYNTH_VALUE + '"',
                       "    return path"]),
    ("cred-api-key", ["import os", "", "def client(host):",
                      "    api_key = " + '"' + SYNTH_VALUE + '"',
                      "    return host"]),
    ("cred-token", ["import os", "", "def session(user):",
                    "    token = " + '"' + SYNTH_VALUE + '"',
                    "    return user"]),
    ("dang-eval", ["import os", "", "def compute(expr):", SYNTH_EVAL,
                   "    return result"]),
    ("dang-pickle-loads", ["import pickle", "", "def decode(blob):", SYNTH_PICKLE,
                           "    return obj"]),
    ("lang-mutable-default", ["def merge(store, extra=[]):",
                              "    store.update(extra)",
                              "    return store"]),
    ("lang-is-literal-misuse", ["def speed(mode):",
                                '    if mode is "fast":',
                                "        return 1",
                                "    return 0"]),
    ("lang-empty-catch", ["def parse(raw):",
                          "    try:",
                          "        return int(raw)",
                          "    except ValueError:",
                          "        pass"]),
    ("lang-resource-unclosed", ["def read_config(path):",
                                "    fh = open(path)",
                                "    data = fh.read()",
                                "    return data"]),
    ("lang-closure-late-bind", ["def build():",
                                "    fns = []",
                                "    for i in range(3):",
                                "        fns.append(lambda: i)",
                                "    return fns"]),
]

CLEAN_TEMPLATES = [
    ["import os", "", "def load_config(path):",
     '    password = os.environ.get("PW", "")', "    return path"],
    ["import os", "", "def session(request):",
     '    token = request.headers.get("t", "")', "    return token"],
    ["import os", "", "def assemble():",
     '    marker = "pre" + "fix"', "    return marker"],
    ["import ast", "", "def compute(expr):",
     "    result = ast.literal_eval(expr)", "    return result"],
    ["import json", "", "def decode(blob):",
     "    obj = json.loads(blob)", "    return obj"],
    ["def merge(store, extra=None):",
     "    extra = extra or []", "    store.update(extra)", "    return store"],
    ["def speed(mode):", "    if mode is None:", "        return 1", "    return 0"],
    ["def parse(raw):", "    try:", "        return int(raw)",
     "    except ValueError:", "        return 0"],
    ["def read_config(path):", "    with open(path) as fh:",
     "        return fh.read()"],
    ["def build(items):", "    out = []", "    for it in items:",
     "        out.append(sorted(items, key=lambda x: x))", "    return out"],
]


def _synth_sample(idx):
    """交替生成缺陷/干净样本；缺陷样本带 ground-truth 行号与规则 id。"""
    if idx % 2 == 0:
        rule, body = DEFECT_TEMPLATES[(idx // 2) % len(DEFECT_TEMPLATES)]
        lines = ["# synth defect sample %d" % idx, ""] + body
        marker = body[-2] if rule in ("lang-mutable-default",) else None
        gt = [i for i, l in enumerate(lines, 1)
              if SYNTH_QUOTED in l or l in (SYNTH_EVAL, SYNTH_PICKLE)
              or l.startswith("def merge(store, extra=[])")
              or l.startswith('    if mode is "fast"')
              or l.strip() == "pass" and "except" in lines[i - 2]
              or l.startswith("    fh = open(")
              or l.startswith("        fns.append(lambda: i)")]
        return {"lines": lines, "clean": False, "gt_lines": gt, "defect_rule": rule}
    body = CLEAN_TEMPLATES[(idx // 2) % len(CLEAN_TEMPLATES)]
    lines = ["# synth clean sample %d" % idx, ""] + body
    return {"lines": lines, "clean": True, "gt_lines": [], "defect_rule": ""}


def cmd_synth(argv):
    out = Path(argv.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for idx in range(argv.count):
        sample = _synth_sample(idx)
        name = "synth_%03d.py" % idx
        (out / name).write_text("\n".join(sample["lines"]) + "\n", encoding="utf-8")
        manifest.append({
            "id": "synth-%03d" % idx,
            "file": name,
            "clean": sample["clean"],
            "gt_lines": sample["gt_lines"],
            "defect_rule": sample["defect_rule"],
        })
    mpath = out / "manifest.json"
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    clean_n = sum(1 for m in manifest if m["clean"])
    _emit({"ok": True, "mode": "synth", "out": str(out), "manifest": str(mpath),
           "samples": len(manifest), "clean": clean_n, "defective": len(manifest) - clean_n,
           "note": "缺陷样本带 ground-truth 行号，可做 precision 度量；凭据值运行时组装"})
    return 0


def cmd_fp(argv):
    cdir = Path(argv.corpus)
    mpath = cdir / "manifest.json"
    if not cdir.is_dir() or not mpath.is_file():
        _emit({"ok": False, "error": "corpus 目录或 manifest.json 不存在: %s" % cdir})
        return 2
    rules = Path(__file__).resolve().parents[2] / "multi-agent-review" / "scripts" / "deterministic-rules.py"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    tp = fp_count = clean_n = defect_n = det_hit = 0
    per = []
    for entry in manifest:
        fpath = cdir / entry["file"]
        rc, data = _run_json([sys.executable, str(rules), "--file", str(fpath)])
        if rc != 0 or data is None:
            _emit({"ok": False, "error": "deterministic-rules 失败: %s" % entry["file"]})
            return 2
        finds = data.get("findings", [])
        if entry["clean"]:
            clean_n += 1
            fp_count += len(finds)
            if finds:
                per.append({"id": entry["id"], "kind": "fp", "rules": [f["rule_id"] for f in finds]})
        else:
            defect_n += 1
            gt = set(entry["gt_lines"])
            matched = [f for f in finds if any(abs(f["line"] - g) <= 1 for g in gt)]
            if matched:
                tp += 1
                det_hit += 1
            fp_count += len(finds) - len(matched)
            if len(matched) < len(finds):
                per.append({"id": entry["id"], "kind": "fp-or-miss",
                            "rules": [f["rule_id"] for f in finds if f not in matched]})
    precision = round(tp / (tp + fp_count), 4) if (tp + fp_count) else None
    recall = round(det_hit / defect_n, 4) if defect_n else None
    _emit({
        "ok": True,
        "mode": "fp",
        "samples": len(manifest),
        "clean": clean_n,
        "defective": defect_n,
        "tp": tp,
        "fp": fp_count,
        "precision": precision,
        "recall_injected": recall,
        "clean_fp": sum(1 for p in per if p["kind"] == "fp"),
        "fp_rate_clean": round(sum(1 for p in per if p["kind"] == "fp") / clean_n, 4) if clean_n else None,
        "per_sample": per,
        "note": "TP=命中 gt ±1 行的发现；分母口径见 BASELINE（易错点 4：有效样本必须可见）",
    })
    return 0


def main():
    parser = argparse.ArgumentParser(description="前向基准 prepare/judge")
    sub = parser.add_subparsers(dest="mode")
    p_prep = sub.add_parser("prepare")
    p_prep.add_argument("--samples", required=True)
    p_prep.add_argument("--repo", required=True)
    p_prep.add_argument("--out", required=True)
    p_judge = sub.add_parser("judge")
    p_judge.add_argument("--findings", required=True)
    p_judge.add_argument("--prepared", required=True, help="manifest.json 或其目录")
    p_judge.add_argument("--repo", required=True)
    p_judge.add_argument("--min-tokens", dest="min_tokens", type=int, default=2,
                         help="命中阈值，默认 2（可调）")
    p_synth = sub.add_parser("synth")
    p_synth.add_argument("--out", required=True)
    p_synth.add_argument("--count", type=int, default=120)
    p_fp = sub.add_parser("fp")
    p_fp.add_argument("--corpus", required=True)
    argv = parser.parse_args()
    if argv.mode == "prepare":
        return cmd_prepare(argv)
    if argv.mode == "judge":
        return cmd_judge(argv)
    if argv.mode == "synth":
        return cmd_synth(argv)
    if argv.mode == "fp":
        return cmd_fp(argv)
    _emit({"ok": False, "error": "缺少子命令 prepare|judge|synth|fp"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
