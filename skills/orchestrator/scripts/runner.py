#!/usr/bin/env python3
"""评审编排器：把 AGENTS.md 主流程 0–10 步代码化，护栏由代码强制执行。

用途:
    一次调用跑完 意图→取数→评分→派发→核验→查证→汇总→反向验证→交付 双闸。
    预算（分钟/token）、轮数（max_total_rounds/max_verification_rounds）、
    动态增派上限（max_dynamic_dispatches）全部真实扣减；每步写断点，
    --resume 从断点续跑；误报模式库下发到派发、驳回项经 --feedback 回流。

用法:
    python runner.py --repo /path/repo --range A..B --request "评审这次改动"
    python runner.py --repo . --range HEAD~1..HEAD --reviewer deterministic
    python runner.py --resume runs/<run_id>
    python runner.py --repo . --range A..B --reviewer llm --feedback rejects.json

退出码:
    0 = 评审完成（报告与产物落 run 目录）
    1 = NEED_HUMAN（触发人工门：预检拒绝/预算耗尽/C 级意图/双闸失败）
        或 WAIT_HOST_LLM（宿主模型模式等待填写 llm-tasks 响应，--resume 续跑）
    2 = 参数/环境错误
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from llm.provider import HostLLMPending, complete as llm_complete  # noqa: E402 - 项目根包（治理壳 stdlib）

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


STEP_ORDER = ["step0", "step1", "step2", "step3", "step4", "step5",
              "step6", "step7", "step8", "step9", "step10"]
SEV_ORDER = {"高": 0, "中": 1, "低": 2}
MATERIAL_CAP = 60000
WINDOW_PAD = 3
RULE_DIM = {}
for _rid in ("cred-password", "cred-api-key", "cred-secret", "cred-token",
             "cred-aws-akia", "cred-private-key", "cred-db-uri", "cred-jwt",
             "dang-eval", "dang-exec", "dang-shell-true", "dang-pickle-loads",
             "dang-yaml-load", "dang-innerhtml", "dang-dangerously-set",
             "dang-document-write", "dang-os-system", "dang-runtime-exec",
             "dang-unserialize", "dang-system-call", "dang-strcpy-family",
             "dang-gets", "dang-weak-hash-password"):
    RULE_DIM[_rid] = "安全与敏感信息"
for _rid in ("lang-mutable-default", "lang-is-literal-misuse", "lang-closure-late-bind",
             "lang-nil-map-write", "lang-unhandled-err", "lang-defer-in-loop",
             "lang-goroutine-leak", "lang-type-assert-no-ok", "lang-buffer-overflow",
             "lang-empty-catch", "lang-resource-unclosed", "lang-int-overflow-cast",
             "lang-symlink-toctou", "lang-uninit-pointer", "lang-lock-free-read"):
    RULE_DIM[_rid] = "正确性与逻辑缺陷"
for _rid in ("taint-eval", "taint-exec", "taint-os-shell"):
    RULE_DIM[_rid] = "安全与敏感信息"
DEP_FILE_RE = re.compile(r"(requirements[^/]*\.txt|package\.json|go\.(mod|sum)|pom\.xml|"
                         r"Cargo\.toml|pyproject\.toml|setup\.(py|cfg)|Dockerfile|Makefile|"
                         r"\.github/|\.sql$|migrat)", re.I)
PERF_RE = re.compile(r"query|render|serialize|escape", re.I)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
ARTIFACT_MAP = {
    "step2": "step2_collect.json",
    "step3": "step3_risk.json",
    "step4": "step4_dispatch.json",
    "step5": "step5_findings.json",
    "step6": "step6_verification.json",
    "step7": "step7_summary.json",
    "step8": "step8_backverify.json",
    "step10": "report.md",
}
LEDGER_EXCLUDE = {"audit-log.py", "checkpoint.py", "human-gate.py", "event-ledger.py"}
# 可重放动作白名单：只读脚本（不改仓库、不写运行产物、输出不含时间戳）。
# 名单外一律 opaque——安全侧默认，只做完整性校验，不重跑。
LEDGER_DETERMINISTIC = {
    "intent-parse.py", "preflight.py", "edge-detect.py", "deterministic-rules.py",
    "taint-cross.py", "score.py", "dispatch-plan.py", "material-check.py",
    "rules-select.py", "experience.py", "findings-check.py", "coverage.py",
    "perspective-scan.py", "report-check.py", "schema-check.py",
}
OBSERVATION_CAP = 200000


def load_event_ledger():
    """进程内加载 event-ledger 模块（治理壳 stdlib）；失败返回 None，评审降级不阻塞。"""
    path = ROOT / "skills/production-guardrails/scripts/event-ledger.py"
    try:
        spec = importlib.util.spec_from_file_location("event_ledger", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001 - 账本永远不阻塞主流程
        return None


def locate_agent_json(explicit=None):
    """定位 agent.json：显式参数 > CWD > 项目根（脚本位置上溯）。找不到返回 None。"""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path.cwd() / "agent.json")
    candidates.append(Path(__file__).resolve().parents[3] / "agent.json")
    for c in candidates:
        if c.is_file():
            return c
    return None


def load_args(explicit=None):
    """读取 agent.json 的 args；找不到返回空 dict 与 None 来源。"""
    p = locate_agent_json(explicit)
    if not p:
        return {}, None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, str(p)
    return dict(data.get("args") or {}), str(p)


def _run_json(argv_list, stdin=None):
    """以纯参数列表执行子进程并解析 stdout JSON；shell 恒为 False。"""
    if not isinstance(argv_list, list) or not all(isinstance(c, str) for c in argv_list):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(argv_list, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", input=stdin, timeout=600)
    try:
        return p.returncode, json.loads(p.stdout), p.stderr
    except ValueError:
        return p.returncode, None, p.stderr


def _git(repo, git_args):
    p = subprocess.run(["git", "-C", str(repo)] + git_args, shell=False,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _windows(diff_text, pad=WINDOW_PAD):
    """按 hunk 截材料窗口：返回 [(new_lineno, line)]，只含 + 行与上下文行。"""
    out = []
    newln = 0
    hunk_end = 0
    for raw in diff_text.splitlines():
        if raw.startswith("@@"):
            m = re.match(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw)
            if m:
                newln = int(m.group(2))
                count = int(m.group(3) or 1)
                hunk_end = newln + count - 1
            continue
        if raw.startswith(("diff --git", "index ", "--- ", "+++ ", "new file",
                           "deleted file", "old mode", "new mode", "similarity",
                           "rename ", "Binary")):
            continue
        if raw.startswith("+"):
            out.append((newln, raw[1:]))
            newln += 1
        elif raw.startswith(" ") or raw == "":
            if newln <= hunk_end + pad:
                out.append((newln, raw[1:] if raw.startswith(" ") else ""))
            newln += 1
    return out


class Runner:
    def __init__(self, argv):
        self.repo = Path(argv.repo) if argv.repo else None
        self.rev_range = argv.rev_range
        self.request = argv.request
        self.reviewer = argv.reviewer
        self.feedback_file = argv.feedback
        self.args, self.config_source = load_args(argv.config)
        self.root = Path(argv.out)
        self.skip_probe = argv.skip_probe
        self.report_style = getattr(argv, "report_style", None)
        self.deadline_minutes = float(self.args.get("max_review_minutes", 120))
        self.max_rounds = int(self.args.get("max_total_rounds", 32))
        self.max_verify = int(self.args.get("max_verification_rounds", 3))
        self.max_dynamic = int(self.args.get("max_dynamic_dispatches", 2))
        self.tokens = 0
        self.rounds_used = 0
        self.dynamic_used = 0
        self.started = time.monotonic()
        self._step_started = self.started
        self.gates = []
        self.material_check = {}
        self.totals = {"caps": {
            "max_review_minutes": self.deadline_minutes,
            "max_total_rounds": self.max_rounds,
            "max_verification_rounds": self.max_verify,
            "max_dynamic_dispatches": self.max_dynamic,
        }, "steps": [], "rounds": [], "tokens": 0, "minutes_used": 0.0}
        # 成本账本（ROADMAP 3.2）：口径为当前进程；--resume 各段另行起算。
        # tokens 来源如实标注：host 后端没有用量 → n/a_host，不按 0 冒充。
        self.cost = {"llm_calls": 0, "llm_calls_baseline": 0, "llm_providers": [],
                     "tokens_reported_calls": 0, "tokens_status": "not_used",
                     "resume_count": 0}
        if argv.resume:
            self.cost["resume_count"] = 1
            self.run_dir = Path(argv.resume)
            self.run_id = self.run_dir.name
        else:
            self.run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
            self.run_dir = self.root / self.run_id
            self.run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.run_dir / "run_meta.json"
        meta = {}
        if argv.resume and meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.repo = Path(argv.repo) if argv.repo else Path(meta.get("repo", ""))
            self.rev_range = argv.rev_range or meta.get("range", "")
            self.request = argv.request or meta.get("request", "")
        elif not argv.resume:
            meta_path.write_text(json.dumps(
                {"repo": str(self.repo), "range": self.rev_range,
                 "request": self.request, "reviewer": self.reviewer},
                ensure_ascii=False, indent=2), encoding="utf-8")
        # --resume 不必重复 --reviewer：从 run_meta 恢复评审器模式
        if not self.reviewer:
            self.reviewer = meta.get("reviewer") or "deterministic"
        # 统一事件账本（ROADMAP 3.1）：加载失败只降级，不阻塞评审
        self.ledger = load_event_ledger()
        self.ledger_errors = 0
        self._ledger_tokens = {"$ROOT": ROOT}
        if argv.resume:
            self.cost["llm_calls_baseline"] = self._count_ledger_llm()
        if self.repo and str(self.repo).strip():
            self._ledger_tokens["$REPO"] = Path(self.repo).resolve()

    # ---- 预算与断点 ----

    def minutes_left(self):
        return self.deadline_minutes - (time.monotonic() - self.started) / 60.0

    def budget_exhausted(self):
        return self.minutes_left() <= 0

    def use_round(self, tag=""):
        self.rounds_used += 1
        self.totals["rounds"].append({"no": self.rounds_used, "tag": tag})
        return self.rounds_used <= self.max_rounds

    def _budget_rows(self, wall_min):
        """预算对账行（tokens 无上限，恒 N/A；used 不截断，超限即 EXCEEDED）。"""
        rows = []
        for item, used, cap in (
                ("minutes", wall_min, self.deadline_minutes),
                ("rounds", float(self.rounds_used), self.max_rounds),
                ("dynamic_dispatches", float(self.dynamic_used), self.max_dynamic)):
            rows.append({"item": item, "used": round(float(used), 3), "cap": cap,
                         "status": "OK" if float(used) <= float(cap) else "EXCEEDED"})
        rows.append({"item": "tokens", "used": self.tokens, "cap": None,
                     "status": "N/A"})
        return rows

    def _write_totals(self):
        wall_sec = time.monotonic() - self.started
        self.totals["minutes_used"] = round(wall_sec / 60, 3)
        self.totals["tokens"] = self.tokens
        self.totals["ledger"] = {"file": str(self.run_dir / "ledger.jsonl"),
                                 "active": self.ledger is not None,
                                 "errors": self.ledger_errors}
        self.cost.update({
            "wall_sec": round(wall_sec, 3),
            "minutes_used": round(wall_sec / 60, 3),
            "tokens": self.tokens,
            "rounds_used": self.rounds_used,
            "dynamic_used": self.dynamic_used,
            "steps": [{"step": s.get("step"),
                       "rounds_used": s.get("rounds_used"),
                       "dynamic_used": s.get("dynamic_used"),
                       "elapsed_sec": s.get("elapsed_sec")}
                      for s in self.totals["steps"]],
            "budget": self._budget_rows(wall_sec / 60),
            "scope": "current_process（--resume 各段另行起算）",
        })
        self.totals["cost"] = self.cost
        (self.run_dir / "totals.json").write_text(
            json.dumps(self.totals, ensure_ascii=False, indent=2), encoding="utf-8")

    def _persist_resume_state(self, results):
        """形状保真的断点状态：各步返回值原样落盘（diff 除外，过大且已有
        diff.patch）；resume 时整体回灌，避免产物摘要形状与内存形状错配。"""
        payload = {}
        for key, value in results.items():
            if key == "step2" and isinstance(value, dict):
                value = {k: v for k, v in value.items() if k != "diff"}
            payload[key] = value
        try:
            (self.run_dir / "resume-state.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            self.audit("checkpoint", "runner",
                       "resume-state 写入失败: %s" % exc, "降级")

    def checkpoint(self, step):
        artifact = self.run_dir / ARTIFACT_MAP[step] if step in ARTIFACT_MAP else ""
        now = time.monotonic()
        elapsed = round(now - self._step_started, 3)
        self._step_started = now
        self.totals["steps"].append({"step": step, "rounds_used": self.rounds_used,
                                     "dynamic_used": self.dynamic_used,
                                     "elapsed_sec": elapsed})
        self._write_totals()
        self._run([sys.executable,
                   str(ROOT / "skills/production-guardrails/scripts/checkpoint.py"),
                   "write", "--dir", str(self.run_dir), "--step", step,
                   "--rounds", str(self.rounds_used),
                   "--artifacts", str(artifact)])

    def audit(self, step, actor, summary, disposition="None"):
        self._run([sys.executable,
                   str(ROOT / "skills/production-guardrails/scripts/audit-log.py"),
                   "--log", "--step", step, "--actor", actor,
                   "--output-summary", summary, "--disposition", disposition,
                   "--dir", str(self.run_dir)])
        self._ledger_append(actor=actor, action="audit." + str(step),
                            kind="decision", replay="opaque",
                            observation={"exit": 0, "json": {
                                "step": step, "summary": summary,
                                "disposition": disposition}})

    # ---- 事件账本（Action/Observation） ----

    def _ledger_append(self, actor, action, kind, replay, argv=None,
                       observation=None, stdin=None, note=None):
        """追加一条账本记录；失败即停用账本（写 stderr，不递归 audit）。"""
        if self.ledger is None:
            return False
        try:
            self.ledger.append_record(
                self.run_dir, actor=actor, action=action, kind=kind,
                replay=replay, argv=argv, observation=observation,
                stdin=stdin, tokens=self._ledger_tokens, run_id=self.run_id,
                note=note)
            return True
        except Exception as exc:  # noqa: BLE001 - 账本降级不得拖垮评审
            self.ledger_errors += 1
            print("event-ledger 降级停用: %s" % str(exc)[:300], file=sys.stderr)
            self.ledger = None
            return False

    def _ledger_script(self, argv_list, rc, data, err, stdin=None):
        """脚本动作入账：白名单只读脚本记 deterministic，其余 opaque。"""
        script = Path(argv_list[1]).name if len(argv_list) > 1 else ""
        if not script or script in LEDGER_EXCLUDE:
            return
        replay = "deterministic" if script in LEDGER_DETERMINISTIC else "opaque"
        payload = data
        if payload is not None:
            try:
                size = len(json.dumps(payload, ensure_ascii=False))
            except (TypeError, ValueError):
                payload, size = None, 0
            if size > OBSERVATION_CAP:
                payload = {"oversized": True, "bytes": size}
                replay = "opaque"
        actor = script[:-3] if script.endswith(".py") else script
        self._ledger_append(
            actor=actor, action="script." + actor, kind="script", replay=replay,
            argv=list(argv_list), stdin=stdin,
            observation={"exit": rc, "json": payload,
                         "stderr_tail": (err or "").strip()[-500:]})

    def _run(self, argv_list, stdin=None):
        """所有脚本子进程的唯一入口：执行 + 入账（排除项只执行不入账）。"""
        rc, data, err = _run_json(argv_list, stdin=stdin)
        self._ledger_script(argv_list, rc, data, err, stdin)
        return rc, data, err

    def gate(self, situation, details):
        self.gates.append({"situation": situation, "details": details})
        self._run([sys.executable,
                   str(ROOT / "skills/production-guardrails/scripts/human-gate.py"),
                   "--situation", situation, "--details", details[:200]])
        self.audit("gate", "runner", "%s: %s" % (situation, details), "熔断")

    def need_human(self, reason):
        self.audit("need_human", "runner", reason, "熔断")
        self._write_totals()
        return {"ok": False, "state": "NEED_HUMAN", "run_id": self.run_id,
                "run_dir": str(self.run_dir), "reason": reason, "gates": self.gates}

    # ---- LLM 评审器（经 llm/provider 抽象层：openai 兼容 / 宿主模型） ----

    def _count_ledger_llm(self):
        """进程基线：--resume 时账本里已有的 LLM 记录条数（只读，失败归零）。"""
        path = self.run_dir / "ledger.jsonl"
        if self.ledger is None or not path.is_file():
            return 0
        try:
            records, _ = self.ledger.load_ledger(path)
        except Exception:  # noqa: BLE001 - 基线只影响对账，不阻塞评审
            return 0
        return sum(1 for rec in records if rec.get("kind") == "llm")

    def _add_tokens(self, n):
        self.tokens += int(n or 0)
        self.cost["tokens_reported_calls"] += 1
        self.cost["tokens_status"] = "provider_usage"

    def _track_llm(self, meta):
        """LLM 后端来源与调用计数；tokens_status 一旦有真实用量不再降级。"""
        provider = (meta or {}).get("provider") or "?"
        if provider not in self.cost["llm_providers"]:
            self.cost["llm_providers"].append(provider)
        self.cost["llm_calls"] += 1
        if self.cost["tokens_status"] == "provider_usage":
            return
        if provider == "host":
            self.cost["tokens_status"] = "n/a_host"
        elif provider == "none" or provider == "?":
            self.cost["tokens_status"] = "no_provider"
        else:
            self.cost["tokens_status"] = "unavailable"

    def _llm_call(self, system, user):
        """委托 llm/provider；host 等待时 HostLLMPending 上抛给 main 转
        WAIT_HOST_LLM（退出码 1），宿主填写响应后 --resume 幂等续跑。"""
        text, meta = llm_complete(
            system, user, base_dir=self.run_dir / "llm-tasks",
            args=self.args, on_tokens=self._add_tokens)
        self._track_llm(meta)
        self._ledger_llm(system, user, text, meta)
        if text is None and meta.get("provider") == "openai":
            self.audit("llm_retry", "runner",
                       "放弃: %s" % meta.get("error", ""), "重试")
        return text

    def _ledger_llm(self, system, user, text, meta):
        """LLM 调用只记指纹与元数据，不落提示词/响应正文（脱敏之外再收一层）。"""
        prompt_sha = hashlib.sha256(
            ((system or "") + "\n" + (user or "")).encode("utf-8")).hexdigest()
        response_sha = (hashlib.sha256(text.encode("utf-8")).hexdigest()
                        if isinstance(text, str) else None)
        self._ledger_append(
            actor="llm:%s" % ((meta or {}).get("provider") or "?"),
            action="llm.call", kind="llm", replay="opaque",
            observation={"exit": 0 if text is not None else 1, "json": {
                "provider": (meta or {}).get("provider"),
                "model": (meta or {}).get("model"),
                "prompt_sha256": prompt_sha,
                "response_sha256": response_sha,
                "response_chars": len(text) if isinstance(text, str) else 0}})

    # ---- 步骤 ----

    def step0_probe(self):
        if self.skip_probe:
            return None
        rc, data, _ = self._run([sys.executable,
                                 str(ROOT / "skills/self-iteration/scripts/session-probe.py"),
                                 "--root", str(ROOT)])
        if rc >= 2 or data is None:
            self.gate("conclusions_unconverged", "开局探针故障，先修检查器")
            return "NEED_HUMAN"
        self.audit("step0", "runner", "探针全绿" if rc == 0 else "探针有信号")
        return None

    def step1_intent(self):
        if self.request:
            rc, data, _ = self._run([sys.executable,
                                     str(ROOT / "skills/prompt-enhancement/scripts/intent-parse.py"),
                                     "--request", self.request, "--repo", str(self.repo)])
            if rc == 3:
                self.gate("conclusions_unconverged", "意图 C 级需追问: %s"
                          % json.dumps(data.get("questions", []), ensure_ascii=False))
                return "NEED_HUMAN"
            if rc == 0 and data:
                return data
        return {"intent_level": "B", "object": "范围", "object_ref": self.rev_range,
                "depth": "standard",
                "rationale": ["未提供请求或解析失败，默认评审指定范围"]}

    def step2_collect(self):
        rc, pre, err = self._run([sys.executable,
                                  str(ROOT / "skills/git-change-analysis/scripts/preflight.py"),
                                  "--repo", str(self.repo), "--range", self.rev_range,
                                  "--config", self.config_source or ""])
        if rc == 2 or pre is None:
            self.gate("preflight_rejected", "预检环境错误: %s" % (err or "")[:200])
            return "NEED_HUMAN"
        if rc != 0:
            self.gate("preflight_rejected", str(pre.get("reject", pre.get("error", ""))))
            return "NEED_HUMAN"
        rc, edges, _ = self._run([sys.executable,
                                  str(ROOT / "skills/git-change-analysis/scripts/edge-detect.py"),
                                  "--repo", str(self.repo), "--range", self.rev_range])
        diff = _git(self.repo, ["diff", self.rev_range])[1]
        diff_path = self.run_dir / "diff.patch"
        diff_path.write_text(diff, encoding="utf-8")
        rc, rules, _ = self._run([sys.executable,
                                  str(ROOT / "skills/multi-agent-review/scripts/deterministic-rules.py"),
                                  "--diff-file", str(diff_path)])
        facts = rules.get("findings", []) if rules else []
        # 跨文件污点两遍分析（1.10.0 接入主线）：仅报变更文件内的流；
        # 失败/超限降级不阻塞评审，如实审计。
        rc_t, taint, _ = self._run([sys.executable,
                                    str(ROOT / "skills/multi-agent-review/scripts/taint-cross.py"),
                                    "--root", str(self.repo),
                                    "--diff", str(diff_path),
                                    "--max-files", "200"])
        if rc_t == 0 and taint is not None:
            cross = taint.get("findings", [])
            facts.extend(cross)
            self.audit("step2", "taint-cross",
                       "跨文件流 %d 条（摘要 %d）" % (len(cross),
                                                    taint.get("summaries", 0)),
                       "采纳")
        else:
            self.audit("step2", "taint-cross", "引擎不可用，降级", "降级")
        numstat = _git(self.repo, ["diff", "--numstat", self.rev_range])[1].splitlines()
        files = []
        for row in numstat:
            parts = row.split("\t")
            if len(parts) == 3:
                files.append({"path": parts[2], "binary": parts[0] == "-",
                              "added": 0 if parts[0] == "-" else int(parts[0]),
                              "deleted": 0 if parts[1] == "-" else int(parts[1])})
        head = self.rev_range.split("..")[-1]
        for f in files[:50]:
            if f["binary"]:
                continue
            f["history_3m"] = len(_git(self.repo, ["log", "--oneline", "--since=90.days",
                                                   "--", f["path"]])[1].splitlines())
            f["history_12m"] = len(_git(self.repo, ["log", "--oneline", "--since=1.years",
                                                    "--", f["path"]])[1].splitlines())
            stem = Path(f["path"]).stem
            f["refs"] = 0
            if len(stem) >= 3:
                rc_g, out_g = _git(self.repo, ["grep", "-l", "--fixed-strings", stem, head])
                f["refs"] = max(0, len([l for l in out_g.splitlines() if l.strip()]) - 1)
        collect = {"repo": str(self.repo), "range": self.rev_range,
                   "files": len(files), "source_lines": pre["source_lines"],
                   "commits": pre["commits"]}
        (self.run_dir / "step2_collect.json").write_text(
            json.dumps(collect, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"preflight": pre, "edges": edges, "facts": facts, "files": files,
                "diff": diff, "head": head}

    def step3_score(self, ctx):
        regions = {}
        for f in ctx["files"]:
            top = f["path"].split("/")[0] if "/" in f["path"] else "(root)"
            r = regions.setdefault(top, {"name": top, "files": 0, "added": 0, "deleted": 0,
                                         "modules": 1, "callers": 0, "high_impact": [],
                                         "history_3m": 0, "history_12m": 0,
                                         "has_hotfix": False, "has_revert": False,
                                         "intent_deviation": False})
            r["files"] += 1
            r["added"] += f["added"]
            r["deleted"] += f["deleted"]
            r["history_3m"] += f.get("history_3m", 0)
            r["history_12m"] += f.get("history_12m", 0)
        overall = {"files": len(ctx["files"]),
                   "added": sum(r["added"] for r in regions.values()),
                   "deleted": sum(r["deleted"] for r in regions.values()),
                   "modules": len(regions),
                   "callers": max([r["callers"] for r in regions.values()] or [0]),
                   "history_3m": sum(r["history_3m"] for r in regions.values()),
                   "history_12m": sum(r["history_12m"] for r in regions.values())}
        payload = {"regions": list(regions.values()), "overall": overall}
        rc, risk, err = self._run([sys.executable,
                                   str(ROOT / "skills/risk-scoring/scripts/score.py")],
                                  stdin=json.dumps(payload))
        if rc != 0 or risk is None:
            self.gate("preflight_rejected", "评分失败: %s" % (err or "")[:200])
            return "NEED_HUMAN"
        (self.run_dir / "step3_risk.json").write_text(
            json.dumps(risk, ensure_ascii=False, indent=2), encoding="utf-8")
        return risk

    def step4_dispatch(self, ctx, risk):
        rc_m, mat_chk, _ = self._run([sys.executable,
                                      str(ROOT / "skills/multi-agent-review/scripts/material-check.py"),
                                      "--diff-file", str(self.run_dir / "diff.patch"),
                                      "--pattern", r"\S"])
        material_ok = bool(mat_chk and mat_chk.get("ok"))
        self.material_check = mat_chk or {}
        if not material_ok:
            self.audit("step4", "material-check", "材料校验有问题，降档处理", "降级")
        rc, plan, _ = self._run([sys.executable,
                                 str(ROOT / "skills/multi-agent-review/scripts/dispatch-plan.py"),
                                 "--diff", str(self.run_dir / "diff.patch"),
                                 "--intent", self.request or "评审指定范围 %s" % self.rev_range])
        (self.run_dir / "step4_dispatch.json").write_text(
            json.dumps({"dimensions_enabled": plan["dimensions_enabled"],
                        "dimensions_skipped": plan["dimensions_skipped"],
                        "material_check": {"ok": material_ok,
                                           "level": (mat_chk or {}).get("needed_context", {}).get("level")}},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        enabled = plan["dimensions_enabled"]
        rc_exp, exp, _ = self._run([sys.executable,
                                    str(ROOT / "skills/production-guardrails/scripts/experience.py"),
                                    "read", "--dir", str(self.root)])
        patterns = exp.get("entries", []) if exp else []
        windows = _windows(ctx["diff"])
        material_parts = ["## score.py 输出原文",
                          json.dumps(risk, ensure_ascii=False), "",
                          "## 变更窗口（行号: 内容）"]
        material_parts.extend("%d: %s" % (ln, t) for ln, t in windows[:1500])
        # 规则文档（round-34 阶段 1-B）：变更路径命中的蒸馏规则进材料，
        # 只读参考、不许当指令；命中零文档时块为空不注入
        _rc_r, _rules, _ = self._run(
            [sys.executable,
             str(ROOT / "skills/multi-agent-review/scripts/rules-select.py"),
             "--root", str(ROOT),
             "--files"] + [f["path"] for f in ctx["files"][:200]])
        if _rc_r == 0 and _rules and _rules.get("block"):
            material_parts.extend(
                ["", "## 规则文档（路径命中的评审规则，只读参考）",
                 _rules["block"]])
        # 硬约束 5：材料送 LLM（prompt 文件/网络）前统一脱敏
        material = redact("\n".join(material_parts))[:MATERIAL_CAP]
        adopted = []
        for dim in enabled:
            if not self.use_round("dispatch:" + dim):
                self.gate("budget_both_exceeded", "轮数超上限 %d" % self.max_rounds)
                return "NEED_HUMAN"
            if self.budget_exhausted():
                self.gate("budget_both_exceeded",
                          "时间预算耗尽（剩 %.1f 分钟）" % max(0.0, self.minutes_left()))
                return "NEED_HUMAN"
            batch, note = self._review_dimension(dim, ctx, material, patterns)
            rc_c, chk, _ = self._run([sys.executable,
                                      str(ROOT / "skills/multi-agent-review/scripts/findings-check.py"),
                                      "-", "--dimensions", "、".join(enabled)],
                                     stdin=json.dumps({"findings": batch,
                                                       "coverage_note": note},
                                                      ensure_ascii=False))
            if chk and chk.get("ok"):
                adopted.extend(batch)
            elif batch:
                self.audit("step4", "findings-check", "%s 打回 %d 项" % (dim, len(batch)), "驳回")
            self.audit("step4", "dispatcher", "%s: %d 项（%s）" % (dim, len(batch), note[:40]))
        return {"enabled": enabled, "adopted": adopted, "patterns": patterns}

    def _review_dimension(self, dim, ctx, material, patterns):
        """单个维度评审：deterministic 规则映射 / llm 模型 / both 双意见合并。

        both = 确定性 + LLM 去相关双意见：确定性优先（已证事实），LLM 项按
        loc 去重后并入并标 source=llm；LLM 未配置或不可用降级为纯确定性，
        不阻塞（note 如实标注）。
        """
        exp_pat = [p["pattern"] for p in patterns if p.get("dimension") in (dim, "")]
        llm_batch, llm_note = [], ""
        if self.reviewer in ("llm", "both"):
            prompt = ("你是 %s 维度的评审员。只依据材料，输出 JSON 数组，每项含 "
                      "loc(文件:行号)/desc/evidence/severity(高|中|低)/confidence(高|中|低)/"
                      "cause/fix。无问题输出 []。\n材料：\n%s" % (dim, material))
            raw = self._llm_call("你是只读代码评审员，只输出 JSON。", prompt)
            if raw:
                cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
                try:
                    parsed = json.loads(cleaned)
                except ValueError:
                    parsed = []
                for f in parsed if isinstance(parsed, list) else []:
                    if isinstance(f, dict) and f.get("loc"):
                        f["dimension"] = dim
                        f["source"] = "llm"
                        llm_batch.append(f)
            llm_note = "llm %d 项" % len(llm_batch) if llm_batch else "llm 不可用/零发现"
            if self.reviewer == "llm":
                return llm_batch, "llm 评审；%s；误报模式 %d 条" % (llm_note, len(exp_pat))
        mapped = []
        dep_hint = any(DEP_FILE_RE.search(f["path"]) for f in ctx["files"])
        for f in ctx["facts"]:
            target = RULE_DIM.get(f["rule_id"], "正确性与逻辑缺陷")
            if target != dim:
                continue
            if dim == "回退风险与影响面" and not dep_hint:
                continue
            item = {
                "loc": "%s:%d" % (f["file"], f["line"]),
                "desc": f["reason"],
                "evidence": f["snippet"],
                "severity": f["severity"],
                "confidence": "高",
                "cause": "deterministic-rules %s 命中（已证事实）" % f["rule_id"],
                "fix": "按 %s 规则的标准处置修复，上下文需人工确认" % f["rule_id"],
                "dimension": dim,
                "rule_id": f["rule_id"],
                "file": f["file"],
                "line": f["line"],
                "snippet": f["snippet"],
            }
            for pat in exp_pat:
                if pat and pat.lower() in (item["desc"] + item["evidence"]).lower():
                    item["human_review"] = True
                    item["confidence"] = "中"
                    item["note"] = "命中误报模式: %s（历史驳回，需人工复核）" % pat
                    break
            mapped.append(item)
        if dim == "性能与资源":
            has_perf = any(PERF_RE.search(t) for _, t in _windows(ctx["diff"]))
            if not has_perf:
                return [], "本维度无新增 query/render/serialize/escape 行，未派发发现"
        if dim == "意图一致性":
            paths_in_request = re.findall(r"[\w./-]+\.\w+", self.request or "")
            missing = [p for p in paths_in_request
                       if p not in {f["path"] for f in ctx["files"]}]
            if missing:
                return [{"loc": "%s:1" % missing[0], "desc": "意图点名的文件不在变更范围",
                         "evidence": missing[0], "severity": "低", "confidence": "中",
                         "cause": "请求与实际范围可能不一致", "fix": "与用户确认范围",
                         "dimension": dim}], "意图一致性核对完成"
            return [], "意图与范围一致，无偏差发现"
        note = "%s 完成；已下发误报模式 %d 条" % (dim, len(exp_pat))
        if self.reviewer == "both":
            seen_loc = {item["loc"] for item in mapped}
            merged = 0
            for item in llm_batch:
                if item["loc"] in seen_loc:
                    continue
                seen_loc.add(item["loc"])
                mapped.append(item)
                merged += 1
            for item in mapped:
                item.setdefault("source", "deterministic")
            note = "%s 完成；双意见 d+%d/llm+%d（重复剔除）；%s" % (
                dim, len(mapped) - merged, merged, llm_note)
            self.audit("step4", "both", "%s: 确定性 %d + llm 并入 %d"
                       % (dim, len(mapped) - merged, merged), "双意见")
        return mapped, note

    def step5_verify(self, dispatch):
        adopt, reject = [], []
        seen = set()
        diff_text = (self.run_dir / "diff.patch").read_text(encoding="utf-8")
        diff_redacted = redact(diff_text)
        for f in dispatch["adopted"]:
            loc = f.get("loc", "")
            if loc in seen:
                reject.append({"loc": loc, "reason": "重复发现"})
                continue
            seen.add(loc)
            evidence = str(f.get("evidence", "") or f.get("snippet", ""))
            if evidence and evidence not in diff_text and evidence not in diff_redacted:
                reject.append({"loc": loc, "reason": "证据不在 diff 原文中"})
                continue
            adopt.append(f)
        (self.run_dir / "step5_findings.json").write_text(
            json.dumps({"findings": adopt}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (self.run_dir / "step6_verification.json").write_text(
            json.dumps({"adopt": adopt, "reject": reject}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"adopt": adopt, "reject": reject}

    def step6_challenge(self, verification, ctx):
        rounds_log = []
        for f in verification["adopt"]:
            if f.get("severity") != "高":
                continue
            f.setdefault("rounds_log", [])
            verdicts = []
            for angle in range(1, self.max_verify + 1):
                if not self.use_round("challenge:" + str(f.get("loc"))):
                    break
                verdict = self._challenge_angle(f, angle, ctx)
                verdicts.append(verdict)
                f["rounds_log"].append({"angle": angle, "verdict": verdict})
                if len(verdicts) >= 2 and verdicts[-1] == verdicts[-2]:
                    break
            if verdicts and len(verdicts) >= 2 and all(v == "成立" for v in verdicts) \
                    and not f.get("human_review"):
                f["confidence"] = "高"
                f["source"] = "多轮共识"
            elif "材料不足" in verdicts:
                f["confidence"] = "中"
                f["human_review"] = True
            rounds_log.append({"loc": f.get("loc"), "rounds": verdicts})
        return rounds_log

    def _challenge_angle(self, f, angle, ctx):
        if angle == 1:
            evidence = str(f.get("evidence", "") or f.get("snippet", ""))
            diff_blob = ctx["diff"] + redact(ctx["diff"])
            return "成立" if evidence and evidence in diff_blob else "不成立"
        if angle == 2:
            idents = [t for t in IDENT_RE.findall(str(f.get("snippet", ""))) if len(t) >= 4]
            if not idents:
                return "材料不足"
            for tok in idents[:3]:
                rc, out = _git(self.repo, ["grep", "-l", "--fixed-strings", tok, ctx["head"]])
                if rc == 0 and out:
                    return "成立"
            return "材料不足"
        path = str(f.get("file", f.get("loc", ""))).rpartition(":")[0]
        fixes = _git(self.repo, ["log", "--oneline", "--since=90.days", "--", path])[1]
        return "成立" if fixes else "材料不足"

    def step7_summary(self, ctx, risk):
        suggestions = ["为 %s 补充边界用例：覆盖新增分支与错误处理" % f["path"]
                       for f in ctx["files"][:10] if not f["binary"]]
        summary = {"change_summary": "范围 %s，文件 %d，增删 +%d/-%d" % (
            self.rev_range, len(ctx["files"]),
            sum(f["added"] for f in ctx["files"]),
            sum(f["deleted"] for f in ctx["files"])),
            "test_suggestions": suggestions,
            "risk": risk["overall"]["level"]}
        (self.run_dir / "step7_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    def step8_backverify(self):
        findings_file = self.run_dir / "step5_findings.json"
        rc, cov, _ = self._run([sys.executable,
                                str(ROOT / "skills/multi-agent-review/scripts/coverage.py"),
                                "--findings", str(findings_file),
                                "--diff-file", str(self.run_dir / "diff.patch")])
        uncovered = cov.get("uncovered", []) if cov else []
        if uncovered and self.dynamic_used < self.max_dynamic:
            self.dynamic_used += 1
            self.audit("step8", "backverify", "动态补审额度使用 %d/%d，未覆盖 hunk %d 个"
                       % (self.dynamic_used, self.max_dynamic, len(uncovered)))
        rc, persp, _ = self._run([sys.executable,
                                  str(ROOT / "skills/self-iteration/scripts/perspective-scan.py"),
                                  "--findings", str(findings_file),
                                  "--diff-file", str(self.run_dir / "diff.patch")])
        crosschecked = persp.get("problems", []) if persp else []
        backverify = {"uncovered": uncovered, "crosschecked": crosschecked}
        (self.run_dir / "step8_backverify.json").write_text(
            json.dumps(backverify, ensure_ascii=False, indent=2), encoding="utf-8")
        return backverify

    def step10_report(self, ctx, risk, intent, verification, summary):
        findings = sorted(verification["adopt"],
                          key=lambda f: SEV_ORDER.get(f.get("severity"), 3))
        inline = []
        for f in findings:
            loc = str(f.get("loc", ""))
            fpath = loc.rpartition(":")[0] or str(f.get("file", ""))
            try:
                lineno = int(loc.rpartition(":")[2])
            except ValueError:
                lineno = 0
            inline.append({"file": fpath, "line": lineno,
                           "severity": f.get("severity", "中"),
                           "message": f.get("desc", ""),
                           "suggestion": f.get("fix", "")})
        rows = ["| 编号 | 严重度 | 置信度 | 来源 | 维度 | 定位 | 证据 | 原因 | 修复步骤 | 证据等级 | 复核 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for i, f in enumerate(findings, 1):
            loc = f.get("loc", "%s:%s" % (f.get("file", "?"), f.get("line", "?")))
            rows.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s | 观测 | %s |" % (
                i, f.get("severity", "中"), f.get("confidence", "中"),
                f.get("source", "单方推断待确认"), f.get("dimension", "-"), loc,
                str(f.get("evidence", f.get("snippet", "")))[:80],
                str(f.get("cause", f.get("reason", "")))[:80],
                str(f.get("fix", ""))[:80],
                "需人工复核" if f.get("human_review") else "-"))
        inline_lines = ["%s:%d | %s | %s" % (c["file"], c["line"], c["severity"], c["message"])
                        for c in inline] or ["（无结论产出）"]
        body = "\n".join([
            "# 代码评审报告", "",
            "【评审口径】对象：%s｜深度档：%s｜评审器：%s" % (
                self.rev_range, intent.get("depth", "standard"), self.reviewer), "",
            "## 运行信息",
            "轮数 %d/%d｜动态增派 %d/%d｜tokens %d｜预算剩 %.1f 分钟｜材料校验 %s｜门 %s" % (
                self.rounds_used, self.max_rounds, self.dynamic_used, self.max_dynamic,
                self.tokens, max(0.0, self.minutes_left()),
                "通过" if self.material_check.get("ok") else "降档",
                "、".join(g["situation"] for g in self.gates) or "无"), "",
            "## 一、变更摘要",
            "文件 %d｜增删 +%d/-%d｜边界信号 %s" % (
                len(ctx["files"]), sum(f["added"] for f in ctx["files"]),
                sum(f["deleted"] for f in ctx["files"]),
                "、".join(e["type"] for e in ((ctx.get("edges") or {}).get("edges") or [])
                          if e["found"]) or "无"), "",
            "## 二、风险评分",
            "整次综合 %s（%s）｜高风险区域 %s" % (
                risk["overall"]["score"], risk["overall"]["level"],
                "、".join(risk["high_regions"]) or "无"), "",
            "## 三、测试建议",
        ] + ["- " + s for s in summary["test_suggestions"]] + [
            "", "## 四、优化步骤手册",
            "建议阅读顺序：先高严重度已证事实 → 需人工复核 → 中低",
        ] + rows + [
            "", "## 五、行内评论",
        ] + inline_lines + [
            "", "## 六、修复补丁建议",
            "未生成补丁：上下文逐字核对未通过前不放 diff，只给文字修复步骤。", "",
            "---", "每项结论标注证据等级：观测 ≠ 因果；单变量实验 ≠ 独立复现。",
        ])
        report_path = self.run_dir / "report.md"
        report_path.write_text(body, encoding="utf-8")
        rc, chk, _ = self._run([sys.executable,
                                str(ROOT / "skills/production-guardrails/scripts/report-check.py"),
                                str(report_path)])
        if rc != 0:
            self.gate("conclusions_unconverged",
                      "报告校验未过: %s" % json.dumps(chk, ensure_ascii=False)[:200])
            return "NEED_HUMAN"
        rc, sch, _ = self._run([sys.executable,
                                str(ROOT / "skills/production-guardrails/scripts/schema-check.py"),
                                "--dir", str(self.run_dir)])
        if rc != 0:
            self.gate("conclusions_unconverged",
                      "产物校验未过: %s" % json.dumps(sch, ensure_ascii=False)[:400])
            return "NEED_HUMAN"
        self.audit("step10", "runner", "双闸通过，交付 run %s" % self.run_id, "采纳")
        styled = self._render_style_variant(findings)
        return {"report_path": str(report_path), "inline": inline,
                "findings": findings, "styled": styled}

    def _render_style_variant(self, findings):
        """--report-style 报告变体（r105；fail-soft，降级不阻断交付）。"""
        if not self.report_style:
            return None
        p = Path(self.report_style)
        label = p.stem if p.suffix == ".json" else self.report_style
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", label)[:40] or "style"
        findings_path = self.run_dir / "findings.json"
        findings_path.write_text(json.dumps({"findings": findings},
                                             ensure_ascii=False), encoding="utf-8")
        out_path = self.run_dir / ("report-%s.md" % safe)
        rc, out, _ = self._run([sys.executable,
                                str(ROOT / "skills/orchestrator/scripts/report-adapter.py"),
                                "--findings", str(findings_path),
                                "--style", self.report_style,
                                "--out", str(out_path)])
        if rc != 0:
            self.audit("step10", "runner", "报告适配降级: %s" % str(out)[:160], "降级")
            return {"status": "degraded", "style": self.report_style}
        self.audit("step10", "runner", "报告风格变体 %s" % out_path.name, "采纳")
        return {"status": "ok", "path": str(out_path), "style": self.report_style}

    def record_feedback(self):
        if not self.feedback_file:
            return
        fp = Path(self.feedback_file)
        if not fp.is_file():
            return
        rc_f, out_f, _ = self._run([sys.executable,
                                    str(ROOT / "skills/production-guardrails/scripts/feedback-close.py"),
                                    "--findings", str(fp), "--experience", str(self.root)])
        if rc_f == 0 and out_f:
            self.audit("step10", "runner",
                       "驳回项经 feedback-close 入库 %d 条" % out_f.get("recorded", 0), "驳回")
        else:
            self.audit("step10", "runner", "驳回项入库失败", "重试")

    # ---- 主流程 ----

    def run(self):
        if self.budget_exhausted():
            self.gate("budget_both_exceeded", "预算在启动前已耗尽")
            return self.need_human("预算耗尽")
        resume_from = None
        if (self.run_dir / "checkpoint.json").is_file():
            rc, cp, _ = self._run([sys.executable,
                                   str(ROOT / "skills/production-guardrails/scripts/checkpoint.py"),
                                   "verify", "--dir", str(self.run_dir)])
            if rc == 0 and cp:
                resume_from = cp.get("resume_from")
            elif rc == 1:
                self.gate("verification_incomplete", "断点产物缺失，需重跑")
                return self.need_human("断点校验失败")
        start_idx = STEP_ORDER.index(resume_from) if resume_from in STEP_ORDER else 0
        results = {}
        ctx = None
        # 断点回灌：resume-state.json 保存各步返回值的原形状（diff 除外，
        # 单独从 diff.patch 回灌），中途 resume（NEED_HUMAN/WAIT_HOST_LLM
        # 续跑）不依赖进程内存；产物摘要文件（step2_collect.json 等）是
        # 展示形状，不得用于回灌。
        if start_idx > 0 and (self.run_dir / "resume-state.json").is_file():
            try:
                results = json.loads(
                    (self.run_dir / "resume-state.json").read_text(
                        encoding="utf-8"))
            except (OSError, ValueError):
                results = {}
        ctx = results.get("step2")
        if ctx is not None and "diff" not in ctx \
                and (self.run_dir / "diff.patch").is_file():
            ctx["diff"] = (self.run_dir / "diff.patch").read_text(
                encoding="utf-8", errors="replace")
        for step in STEP_ORDER[start_idx:]:
            # D-055 异步作业进度帧（stderr，不污染 stdout 的评审 JSON）：
            # MCP job worker 解析 PROGRESS step=N/10 写 status.json。
            print("PROGRESS step=%d/%d" %
                  (STEP_ORDER.index(step), len(STEP_ORDER) - 1),
                  file=sys.stderr, flush=True)
            if step == "step0":
                r = self.step0_probe()
            elif step == "step1":
                r = self.step1_intent()
            elif step == "step2":
                r = self.step2_collect()
            elif step == "step3":
                r = self.step3_score(ctx)
            elif step == "step4":
                r = self.step4_dispatch(ctx, results.get("step3"))
            elif step == "step5":
                r = self.step5_verify(results.get("step4"))
            elif step == "step6":
                r = self.step6_challenge(results.get("step5"), ctx)
            elif step == "step7":
                r = self.step7_summary(ctx, results.get("step3"))
            elif step == "step8":
                r = self.step8_backverify()
            elif step == "step9":
                r = {"note": "手册在报告内合成"}
            elif step == "step10":
                r = self.step10_report(ctx, results.get("step3"), results.get("step1"),
                                       results.get("step5"), results.get("step7"))
            if r == "NEED_HUMAN":
                return self.need_human(step)
            if step == "step1" and isinstance(r, dict) and r:
                (self.run_dir / "step1_intent.json").write_text(
                    json.dumps(r, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            if step == "step2":
                ctx = r
            results[step] = r
            self._persist_resume_state(results)
            self.checkpoint(step)
        self.record_feedback()
        self._ledger_append(actor="runner", action="run.done", kind="note",
                            replay="opaque",
                            observation={"exit": 0, "json": {
                                "state": "DONE", "rounds_used": self.rounds_used,
                                "dynamic_used": self.dynamic_used,
                                "gates": len(self.gates)}})
        self._write_totals()
        report = results.get("step10") or {}
        return {"ok": True, "state": "DONE", "run_id": self.run_id,
                "run_dir": str(self.run_dir),
                "report_path": report.get("report_path"),
                "inline": report.get("inline", []),
                "findings": report.get("findings", []),
                "uncovered": (results.get("step8") or {}).get("uncovered", []),
                "risk": (results.get("step3") or {}).get("overall"),
                "rounds_used": self.rounds_used,
                "dynamic_used": self.dynamic_used,
                "tokens": self.tokens,
                "gates": self.gates}


def main():
    parser = argparse.ArgumentParser(description="评审编排器（0-10 步代码化）")
    parser.add_argument("--repo", help="被审仓库路径")
    parser.add_argument("--range", dest="rev_range", help="变更范围 A..B")
    parser.add_argument("--request", default="", help="用户原话（意图解析）")
    parser.add_argument("--out", default="runs", help="run 根目录")
    parser.add_argument("--resume", help="续跑已有 run 目录")
    parser.add_argument("--reviewer", choices=["deterministic", "llm", "both"],
                        default=None,
                        help="缺省 deterministic；--resume 时从 run_meta 恢复")
    parser.add_argument("--config", help="agent.json 路径")
    parser.add_argument("--feedback", help="驳回项 JSON 文件（回流误报模式库）")
    parser.add_argument("--skip-probe", dest="skip_probe", action="store_true")
    parser.add_argument("--report-style",
                        help="报告风格变体：preset 名（executive/engineering/audit）或风格 spec JSON 路径；双闸通过后生成 report-<style>.md（适配失败降级不阻断交付）")
    argv = parser.parse_args()
    if not argv.resume and (not argv.repo or not argv.rev_range):
        _emit({"ok": False, "error": "需要 --repo + --range，或 --resume <run_dir>"})
        return 2
    if argv.resume and not Path(argv.resume).is_dir():
        _emit({"ok": False, "error": "resume 目录不存在: %s" % argv.resume})
        return 2
    runner = Runner(argv)
    try:
        result = runner.run()
    except HostLLMPending as pending:
        runner.audit("step4", "host-llm",
                     "等待宿主模型填写: %s" % pending.response_path, "等待")
        _emit({"ok": False, "state": "WAIT_HOST_LLM", "run_id": runner.run_id,
               "run_dir": str(runner.run_dir),
               "llm_task": pending.prompt_path,
               "llm_response": pending.response_path,
               "note": "宿主模型：读取 llm_task，按提示词仅输出 JSON 数组"
                       "（可带代码栅栏）写入 llm_response（UTF-8），然后"
                       " --resume 续跑（保持 CRA_LLM_PROVIDER=host）"})
        return 1
    except Exception as exc:  # noqa: BLE001 - 编排器顶层兜底
        _emit({"ok": False, "state": "FAILED", "error": str(exc)[:500]})
        return 2
    _emit(result)
    if result.get("state") == "NEED_HUMAN":
        return 1
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
