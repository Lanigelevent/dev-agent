#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一事件账本：Action/Observation JSONL（append-only + sha256 哈希链 + 脱敏）。

用途（ROADMAP 阶段三 3.1）：
    把 review/repair/eval 的关键动作统一记成「谁（actor）做了什么
    （action/argv）、观察到什么（exit/JSON）、能不能重放
    （deterministic/opaque）」。账本按行追加、逐行哈希链校验，任一有账本的
    run 不读聊天记录也能回答：做了什么、为什么、能不能复现。`replay` 只重跑
    标记为 deterministic 的动作并逐项对账，差异带路径与新旧值，不静默吞。

判定规则（先写死再看数字）：
    - 链：seq 从 1 连续；prev 等于上一行 digest；digest = sha256(去掉 digest
      后的规范 JSON)。任一不符即 CHAIN_BROKEN，first_bad 指首个坏行。
    - 重放：exit 必须一致；JSON 深度相等（忽略 VOLATILE_KEYS 与令牌化后的
      路径差异）。记录 observations 为 null 时只对 exit。
    - opaque 动作只做完整性校验，不重跑，逐条计 skipped。

用法：
    # runner 在每次脚本调用后写入（也支持手工补录）
    python event-ledger.py record --dir runs/run-x --actor score --action score \\
        --kind script --replay deterministic \\
        --argv-json '["$PYTHON","$ROOT/skills/risk-scoring/scripts/score.py"]' \\
        --observation-json '{"exit":0,"json":{"overall":"中"}}'

    python event-ledger.py verify  --ledger runs/run-x/ledger.jsonl
    python event-ledger.py replay  --ledger runs/run-x/ledger.jsonl --root . \\
        --token '$REPO=/path/to/repo'
    python event-ledger.py summary --ledger runs/run-x/ledger.jsonl

退出码：
    0 = 成功（record 已写入 / verify 链完好 / replay 全部一致 / summary 产出）
    1 = 有问题（verify 链断或坏行 / replay 有差异或执行错误）
    2 = 输入或环境错误（文件缺失、JSON 非法、参数矛盾）
"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "action-observation/1"
LEDGER_NAME = "ledger.jsonl"
GENESIS = "0" * 64
KINDS = {"script", "decision", "llm", "note"}
REPLAY_MODES = {"deterministic", "opaque"}
VOLATILE_KEYS = {
    "ts", "timestamp", "time", "date", "elapsed", "elapsed_ms", "elapsed_sec",
    "duration", "duration_ms", "minutes_used", "generated_at", "started_at",
    "finished_at", "run_id", "session_id",
}
TOKEN_RE = re.compile(r"^\$[A-Z][A-Z0-9_]*$")

SECRET_PATTERNS = [
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|authorization)\s*\"?\s*[:=]\s*)([^\s,;#]{3,})"), r"\1<redacted>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"mysql://[^\s/:]+:[^@\s]+@"), "mysql://<redacted>@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted>"),
]
SECRET_KEY_RE = re.compile(
    r"(?i)^(api[_-]?key|secret|token|password|passwd|authorization|access[_-]?token)$")


def redact(text):
    """密钥形态统一脱敏为 <redacted>。"""
    if not text:
        return text
    t = str(text)
    for pat, rep in SECRET_PATTERNS:
        t = pat.sub(rep, t)
    return t


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def redact_obj(obj):
    """递归脱敏：敏感键的标量值整体替换，所有字符串过密钥模式。"""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if SECRET_KEY_RE.match(str(key)) and isinstance(value, (str, int, float)) \
                    and not isinstance(value, bool) and value not in ("", None):
                out[key] = "<redacted>"
            else:
                out[redact(str(key)) if isinstance(key, str) else key] = redact_obj(value)
        return out
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return redact(str(obj))


def _norm_path(p):
    return str(p).replace("\\", "/").rstrip("/")


def parse_tokens(pairs):
    """`NAME=PATH` 列表 → {`$NAME`: Path}；路径取绝对形式。"""
    tokens = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise ValueError("令牌必须是 NAME=PATH 形式: %s" % raw)
        name, path = raw.split("=", 1)
        if not TOKEN_RE.match(name):
            raise ValueError("令牌名必须形如 $NAME: %s" % name)
        if not path:
            continue
        tokens[name] = Path(path).resolve()
    return tokens


def _path_pattern(path):
    """令牌路径 → 匹配正/反斜杠双形态的正则（Windows 记录、POSIX 记录都能命中）。"""
    parts = _norm_path(path).split("/")
    return re.compile(r"[/\\]".join(re.escape(p) for p in parts) + r"(?=[/\\]|$)",
                      re.IGNORECASE)


def tokenize(value, tokens):
    """把令牌路径替换成 `$NAME`（最长路径优先，按路径段边界匹配，双分隔符）。"""
    if not tokens:
        return value
    if isinstance(value, dict):
        return {tokenize(k, tokens) if isinstance(k, str) else k: tokenize(v, tokens)
                for k, v in value.items()}
    if isinstance(value, list):
        return [tokenize(item, tokens) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    ordered = sorted(tokens.items(), key=lambda kv: len(_norm_path(kv[1])), reverse=True)
    for name, path in ordered:
        prefix = _norm_path(path)
        if not prefix:
            continue
        text = _path_pattern(path).sub(name, text)
    return text


def detokenize(value, tokens):
    if not tokens:
        return value
    if isinstance(value, dict):
        return {k: detokenize(v, tokens) for k, v in value.items()}
    if isinstance(value, list):
        return [detokenize(item, tokens) for item in value]
    if not isinstance(value, str):
        return value
    text = value
    for name, path in sorted(tokens.items(), key=lambda kv: len(kv[0]), reverse=True):
        # 替换串里的反斜杠按 re.sub 语义转义；不用 lambda（循环内 lambda 会被
        # lang-closure-late-bind 规则判为延迟绑定，即使默认参数已即时绑定）
        replacement = str(path).replace("\\", "\\\\")
        text = re.sub(re.escape(name) + r"(?![A-Z0-9_])", replacement, text)
    return text


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest_of(record):
    payload = {k: v for k, v in record.items() if k != "digest"}
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _stderr_tail(text, limit=500):
    text = (text or "").strip()
    return text[-limit:]


def _truncate_stdin(text, limit=200000):
    if text is None:
        return None
    text = str(text)
    if len(text) > limit:
        return text[:limit] + "\n<truncated>"
    return text


def build_record(seq, prev, run_id, actor, action, kind="script",
                 replay="deterministic", argv=None, observation=None,
                 stdin=None, tokens=None, note=None):
    """组装一条账本记录（不含落盘）。observation 形如
    {"exit": 0, "json": {...}, "stderr_tail": "..."}。"""
    tokens = tokens or {}
    entry = {
        "schema": SCHEMA,
        "seq": int(seq),
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_id,
        "actor": str(actor),
        "action": str(action),
        "kind": kind if kind in KINDS else "note",
        "replay": replay if replay in REPLAY_MODES else "opaque",
        "argv": tokenize([str(a) for a in (argv or [])], tokens),
        "stdin_sha256": (hashlib.sha256(stdin.encode("utf-8")).hexdigest()
                         if isinstance(stdin, str) and stdin else None),
        "observation": redact_obj(tokenize(observation or {}, tokens)),
        "prev": prev,
    }
    if stdin:
        entry["stdin"] = redact(_truncate_stdin(stdin))
    if note:
        entry["note"] = redact(str(note))
    entry = redact_obj(entry)
    entry["digest"] = digest_of(entry)
    return entry


def _read_lines(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return [line for line in f.read().splitlines() if line.strip()]
    except OSError as exc:
        raise ValueError("账本不可读: %s (%s)" % (path, exc))


def load_ledger(path):
    """返回 (records, problems)；problems 每项 {seq, reason}。"""
    records = []
    problems = []
    for idx, line in enumerate(_read_lines(path), 1):
        try:
            rec = json.loads(line)
        except ValueError:
            problems.append({"seq": idx, "reason": "json_invalid"})
            continue
        if not isinstance(rec, dict):
            problems.append({"seq": idx, "reason": "not_object"})
            continue
        records.append(rec)
    return records, problems


def verify_records(records, parse_problems=None):
    """逐行校验 schema/seq/prev/digest；返回 {ok, records, first_bad, problems}。"""
    problems = list(parse_problems or [])
    prev = GENESIS
    expected = 1
    first_bad = None
    for rec in records:
        seq = rec.get("seq")
        reason = None
        if rec.get("schema") != SCHEMA:
            reason = "schema"
        elif not isinstance(seq, int):
            reason = "seq_shape"
        elif seq != expected:
            reason = "seq_gap"
        elif rec.get("prev") != prev:
            reason = "prev_mismatch"
        elif rec.get("digest") != digest_of(rec):
            reason = "digest_mismatch"
        if reason:
            bad_seq = seq if isinstance(seq, int) else expected
            problems.append({"seq": bad_seq, "reason": reason})
            if first_bad is None:
                first_bad = bad_seq
            # 链已断：prev 从坏行开始不再具可比性，但 digest 继续逐行验，便于一次报全
        prev = rec.get("digest") if isinstance(rec.get("digest"), str) else prev
        expected = (seq + 1) if isinstance(seq, int) else expected + 1
    return {
        "ok": not problems,
        "records": len(records),
        "first_bad": first_bad,
        "problems": problems,
    }


def verify_ledger(path):
    records, problems = load_ledger(path)
    result = verify_records(records, problems)
    result["ledger"] = str(path)
    return result


def _next_seq_and_prev(path):
    path = Path(path)
    if not path.is_file():
        return 1, GENESIS
    records, _ = load_ledger(path)
    if not records:
        return 1, GENESIS
    last = records[-1]
    seq = last.get("seq")
    prev = last.get("digest")
    if not isinstance(seq, int) or not isinstance(prev, str):
        raise ValueError("账本末行缺少 seq/digest，拒绝续写")
    return seq + 1, prev


def append_record(directory, actor, action, kind="script", replay="deterministic",
                  argv=None, observation=None, stdin=None, tokens=None,
                  run_id=None, note=None, filename=LEDGER_NAME):
    """追加一条记录并返回落盘后的 record（供 runner 进程内调用）。"""
    directory = Path(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError("账本目录不可建: %s (%s)" % (directory, exc))
    path = directory / filename
    seq, prev = _next_seq_and_prev(path)
    full_tokens = {"$PYTHON": Path(sys.executable).resolve(),
                   "$RUN": directory.resolve()}
    full_tokens.update(tokens or {})
    rec = build_record(seq, prev, run_id or directory.name, actor, action, kind,
                       replay, argv, observation, stdin, full_tokens, note)
    with open(path, "a", encoding="utf-8") as f:
        f.write(canonical(rec) + "\n")
    return rec


def _drop_volatile(obj):
    if isinstance(obj, dict):
        return {k: _drop_volatile(v) for k, v in obj.items()
                if not (isinstance(k, str) and k.lower() in VOLATILE_KEYS)}
    if isinstance(obj, list):
        return [_drop_volatile(item) for item in obj]
    return obj


def _first_diff(recorded, current, path=""):
    """深度比较，返回首个差异 {path, recorded, current}；无差异返回 None。"""
    if type(recorded) is not type(current) and not (
            isinstance(recorded, (int, float)) and isinstance(current, (int, float))):
        return {"path": path or "$", "recorded": recorded, "current": current}
    if isinstance(recorded, dict):
        keys = sorted(set(recorded) | set(current))
        for key in keys:
            if key not in recorded:
                return {"path": "%s.%s" % (path, key), "recorded": "<missing>",
                        "current": current[key]}
            if key not in current:
                return {"path": "%s.%s" % (path, key), "recorded": recorded[key],
                        "current": "<missing>"}
            diff = _first_diff(recorded[key], current[key],
                               "%s.%s" % (path or "$", key))
            if diff:
                return diff
        return None
    if isinstance(recorded, list):
        if len(recorded) != len(current):
            return {"path": "%s.length" % (path or "$"), "recorded": len(recorded),
                    "current": len(current)}
        for idx, (old, new) in enumerate(zip(recorded, current)):
            diff = _first_diff(old, new, "%s[%d]" % (path or "$", idx))
            if diff:
                return diff
        return None
    if recorded != current:
        return {"path": path or "$", "recorded": recorded, "current": current}
    return None


def _expand_argv(argv, tokens):
    out = []
    for token in argv or []:
        expanded = detokenize(token, tokens)
        out.append(expanded)
    return out


def replay_ledger(path, tokens, timeout=300, only=None, max_diff=5, cwd=None):
    """重跑 deterministic 动作并与记录对账。

    返回 {ok, state, records, replayed, matched, diffs, skipped, errors,
          items, elapsed_sec}；state ∈ {MATCH, DIFF, CHAIN_BROKEN, ERROR}。
    """
    started = _now()
    tokens = dict(tokens or {})
    tokens.setdefault("$PYTHON", Path(sys.executable).resolve())
    tokens.setdefault("$RUN", Path(path).resolve().parent)
    verify = verify_ledger(path)
    if not verify["ok"]:
        return {"ok": False, "state": "CHAIN_BROKEN", "ledger": str(path),
                "verify": verify, "records": verify["records"], "replayed": 0,
                "matched": 0, "diffs": 0, "skipped": 0, "errors": 0,
                "items": [], "elapsed_sec": 0.0}
    records, _ = load_ledger(path)
    items = []
    matched = diffs = skipped = errors = replayed = 0
    for rec in records:
        action = rec.get("action")
        if only and action != only:
            continue
        if rec.get("replay") != "deterministic":
            skipped += 1
            items.append({"seq": rec.get("seq"), "action": action,
                          "status": "skipped", "note": "opaque"})
            continue
        argv = _expand_argv(rec.get("argv"), tokens)
        if not argv:
            errors += 1
            items.append({"seq": rec.get("seq"), "action": action,
                          "status": "error", "note": "no_argv"})
            continue
        replayed += 1
        stdin = rec.get("stdin")
        try:
            proc = subprocess.run(argv, shell=False, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  input=stdin, timeout=timeout,
                                  cwd=str(cwd) if cwd else None)
        except (OSError, subprocess.SubprocessError) as exc:
            errors += 1
            items.append({"seq": rec.get("seq"), "action": action,
                          "status": "error", "note": str(exc)})
            continue
        recorded = rec.get("observation") or {}
        current = {"exit": proc.returncode,
                   "json": _parse_json(proc.stdout),
                   "stderr_tail": _stderr_tail(proc.stderr)}
        status, detail = _compare_observation(recorded, current, tokens)
        if status == "match":
            matched += 1
        else:
            diffs += 1
        item = {"seq": rec.get("seq"), "action": action, "status": status,
                "recorded_exit": (recorded or {}).get("exit"),
                "current_exit": current["exit"]}
        if detail:
            item.update(detail)
        items.append(item)
        if diffs and max_diff and diffs >= max_diff:
            items.append({"status": "note", "note": "diff 达到 --max-diff，后续未重跑"})
            break
    state = "MATCH" if diffs == 0 and errors == 0 else (
        "DIFF" if diffs else "ERROR")
    return {"ok": state == "MATCH", "state": state, "ledger": str(path),
            "records": len(records), "replayed": replayed, "matched": matched,
            "diffs": diffs, "skipped": skipped, "errors": errors,
            "items": items,
            "elapsed_sec": round(_now() - started, 3)}


def _compare_observation(recorded, current, tokens):
    if (recorded or {}).get("exit") != current.get("exit"):
        return "diff", {"first_diff": {"path": "$.exit",
                                       "recorded": (recorded or {}).get("exit"),
                                       "current": current.get("exit")}}
    rec_json = tokenize(_drop_volatile((recorded or {}).get("json")), tokens)
    cur_json = tokenize(_drop_volatile(current.get("json")), tokens)
    if (recorded or {}).get("json") is None:
        return "match", None
    diff = _first_diff(rec_json, cur_json)
    if diff:
        return "diff", {"first_diff": redact_obj(diff)}
    return "match", None


def summarize_ledger(path):
    verify = verify_ledger(path)
    records, _ = load_ledger(path)
    by_kind, by_actor, decisions = {}, {}, []
    replayable = 0
    for rec in records:
        by_kind[rec.get("kind", "?")] = by_kind.get(rec.get("kind", "?"), 0) + 1
        by_actor[rec.get("actor", "?")] = by_actor.get(rec.get("actor", "?"), 0) + 1
        if rec.get("replay") == "deterministic":
            replayable += 1
        if rec.get("kind") == "decision":
            decisions.append({"seq": rec.get("seq"), "actor": rec.get("actor"),
                              "action": rec.get("action"),
                              "disposition": (rec.get("observation", {})
                                              .get("json", {}) or {}).get("disposition"),
                              "summary": (rec.get("observation", {})
                                          .get("json", {}) or {}).get("summary")})
    return {"ok": verify["ok"], "ledger": str(path), "records": len(records),
            "replayable": replayable, "opaque": len(records) - replayable,
            "by_kind": by_kind, "by_actor": by_actor,
            "decisions": decisions, "verify": verify}


def _parse_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _now():
    import time
    return time.monotonic()


def _load_json_arg(raw, field):
    if raw is None:
        return None
    if raw == "-":
        raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ValueError("%s 不是合法 JSON: %s" % (field, exc))


def main():
    parser = argparse.ArgumentParser(description="统一事件账本")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="追加一条 Action/Observation 记录")
    p_rec.add_argument("--dir", required=True, help="run 目录（ledger.jsonl 所在目录）")
    p_rec.add_argument("--run-id", dest="run_id", help="run 标识（缺省取目录名）")
    p_rec.add_argument("--actor", required=True)
    p_rec.add_argument("--action", required=True)
    p_rec.add_argument("--kind", default="script", choices=sorted(KINDS))
    p_rec.add_argument("--replay", default="deterministic", choices=sorted(REPLAY_MODES))
    p_rec.add_argument("--argv-json", dest="argv_json", help="argv 数组 JSON")
    p_rec.add_argument("--observation-json", dest="observation_json",
                       help='observation JSON，形如 {"exit":0,"json":{...}}；传 - 读 stdin')
    p_rec.add_argument("--stdin-file", dest="stdin_file",
                       help="被记录动作的 stdin 内容文件（重放时回灌）")
    p_rec.add_argument("--token", action="append", default=[],
                       help="NAME=PATH 令牌（如 $REPO=/path/repo），可多次")
    p_rec.add_argument("--note")
    p_rec.add_argument("--filename", default=LEDGER_NAME)

    p_ver = sub.add_parser("verify", help="校验哈希链与 schema")
    p_ver.add_argument("--ledger", required=True)

    p_rep = sub.add_parser("replay", help="重跑 deterministic 动作并对账")
    p_rep.add_argument("--ledger", required=True)
    p_rep.add_argument("--root", default=".", help="默认工作目录（不回灌 cwd）")
    p_rep.add_argument("--repo", help="被评审仓库（供 $REPO 令牌）")
    p_rep.add_argument("--token", action="append", default=[])
    p_rep.add_argument("--timeout", type=int, default=300)
    p_rep.add_argument("--only", help="只重放该 action")
    p_rep.add_argument("--max-diff", dest="max_diff", type=int, default=5,
                       help="差异达到 N 条即停（0 表示不限）")

    p_sum = sub.add_parser("summary", help="账本摘要（种类/执行者/判定时间线）")
    p_sum.add_argument("--ledger", required=True)

    argv = parser.parse_args()
    try:
        if argv.cmd == "record":
            tokens = parse_tokens(argv.token)
            stdin_text = None
            if argv.stdin_file:
                stdin_text = Path(argv.stdin_file).read_text(encoding="utf-8")
            rec = append_record(
                argv.dir, argv.actor, argv.action, kind=argv.kind,
                replay=argv.replay, argv=_load_json_arg(argv.argv_json, "--argv-json"),
                observation=_load_json_arg(argv.observation_json, "--observation-json"),
                stdin=stdin_text, tokens=tokens, run_id=argv.run_id,
                note=argv.note, filename=argv.filename)
            _emit({"ok": True, "seq": rec["seq"], "digest": rec["digest"],
                   "ledger": str(Path(argv.dir) / argv.filename)})
            return 0
        if argv.cmd == "verify":
            result = verify_ledger(Path(argv.ledger))
            _emit(result)
            return 0 if result["ok"] else 1
        if argv.cmd == "replay":
            ledger = Path(argv.ledger)
            tokens = parse_tokens(argv.token)
            tokens["$ROOT"] = Path(argv.root).resolve()
            repo = argv.repo
            if not repo:
                meta = ledger.parent / "run_meta.json"
                if meta.is_file():
                    try:
                        repo = json.loads(meta.read_text(encoding="utf-8")).get("repo")
                    except (OSError, ValueError):
                        repo = None
            if repo:
                repo_path = Path(repo)
                if not repo_path.is_absolute():
                    repo_path = Path(argv.root) / repo_path
                tokens["$REPO"] = repo_path.resolve()
            result = replay_ledger(ledger, tokens, timeout=argv.timeout,
                                   only=argv.only, max_diff=argv.max_diff,
                                   cwd=Path(argv.root))
            _emit(result)
            return 0 if result["ok"] else 1
        if argv.cmd == "summary":
            result = summarize_ledger(Path(argv.ledger))
            _emit(result)
            return 0 if result["ok"] else 1
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    _emit({"ok": False, "error": "未知子命令"})
    return 2


if __name__ == "__main__":
    sys.exit(main())
