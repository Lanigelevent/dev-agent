#!/usr/bin/env python3
"""端到端验证：「发现问题 → 分诊 → 修 → 收敛」全链 + 两条安全边界。

用途:
    自迭代链路。在临时目录构造带缺陷的 git 仓库，验证：
    边界1 脱敏——findings snippet 不含明文凭据；
    边界2 只读——评审管线不改动被审仓库（评审期间 git status 干净）。

用法:
    python e2e-check.py

退出码:
    0 = 全链与边界均通过
    1 = 链路或边界失败
    2 = 环境错误（缺 git、临时目录不可用）
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES = ROOT / "skills" / "multi-agent-review" / "scripts" / "deterministic-rules.py"
PICK = ROOT / "skills" / "self-iteration" / "scripts" / "pick-candidate.py"
CONV = ROOT / "skills" / "self-iteration" / "scripts" / "convergence-check.py"

SECRET = "hunter" + "2secret"
KEY = "sk-live-abc" + "def123456"
V1 = "def charge(amount):\n    total = amount * 1\n    return total\n"
V2 = "\n".join([
    "import os",
    "def charge(amount, cache={}):",
    "    password = " + '"' + SECRET + '"',
    "    total = amount * 1",
    "    api_key = " + '"' + KEY + '"',
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


def _git(repo, args):
    p = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout.strip()


def _run(cmd):
    if not all(isinstance(c, str) for c in cmd):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    return p.returncode, data, p.stderr


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    steps = []
    tmp = tempfile.mkdtemp(prefix="cra-e2e-")
    try:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        rc, _ = _git(repo, ["init", "-q"])
        if rc != 0:
            _emit({"ok": False, "error": "git 不可用"})
            return 2
        (repo / "svc").mkdir()
        (repo / "svc" / "payment.py").write_text(V1, encoding="utf-8")
        _git(repo, ["add", "-A"])
        _git(repo, ["-c", "user.name=e2e", "-c", "user.email=e2e@local", "commit", "-q", "-m", "init"])
        (repo / "svc" / "payment.py").write_text(V2, encoding="utf-8")
        _git(repo, ["add", "-A"])
        _git(repo, ["-c", "user.name=e2e", "-c", "user.email=e2e@local", "commit", "-q", "-m", "feat: rework"])

        diff_path = Path(tmp) / "change.diff"
        rc, _ = _git(repo, ["diff", "HEAD~1..HEAD"])
        diff_path.write_text(_git(repo, ["diff", "HEAD~1..HEAD"])[1], encoding="utf-8")

        # 步骤1 发现问题（评审管线只读：git diff/show）
        rc_r, rules, _ = _run([sys.executable, str(RULES), "--diff-file", str(diff_path)])
        findings = rules.get("findings", []) if rules else []
        found = [f["rule_id"] for f in findings]
        ok1 = rc_r == 0 and any(r.startswith("cred-") for r in found)
        steps.append({"step": "发现问题", "ok": ok1, "rules_hit": found})

        # 边界2 只读：评审期间被审仓库干净
        rc_s, status = _git(repo, ["status", "--porcelain"])
        ok_readonly = rc_s == 0 and status == ""
        steps.append({"step": "安全边界2-只读", "ok": ok_readonly,
                      "status": status or "clean"})

        # 边界1 脱敏：snippet 不含明文凭据
        raw = json.dumps(findings, ensure_ascii=False)
        ok_redact = (SECRET not in raw) and (KEY not in raw) \
            and all("<redacted>" in f["snippet"] for f in findings if f["rule_id"].startswith("cred-"))
        steps.append({"step": "安全边界1-脱敏", "ok": ok_redact})

        # 步骤2 分诊：按严重度给 ROI，pick-candidate 排出首位
        items = [{"id": "f%d" % i, "title": f["rule_id"],
                  "roi": 3 if f["severity"] == "高" else 1,
                  "evidence": "%s:%d" % (f["file"], f["line"])}
                 for i, f in enumerate(findings)]
        items_file = Path(tmp) / "items.json"
        items_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        rc_p, picked, _ = _run([sys.executable, str(PICK), "--items", str(items_file)])
        ok2 = rc_p == 0 and picked and picked["ranked"][0]["roi"] == 3
        steps.append({"step": "分诊", "ok": ok2,
                      "top": picked["ranked"][0]["id"] if picked and picked.get("ranked") else None})

        # 步骤3 修：模拟修复提交（发生在评审结论之后，属被审方动作）
        (repo / "svc" / "payment.py").write_text(V3, encoding="utf-8")
        _git(repo, ["add", "-A"])
        _git(repo, ["-c", "user.name=e2e", "-c", "user.email=e2e@local", "commit", "-q", "-m", "fix: remove embedded secrets"])
        rc_d, fix_diff = _git(repo, ["diff", "HEAD~1..HEAD"])
        fix_file = Path(tmp) / "fix.diff"
        fix_file.write_text(fix_diff, encoding="utf-8")
        rc_f, rules2, _ = _run([sys.executable, str(RULES), "--diff-file", str(fix_file)])
        left = [f["rule_id"] for f in (rules2.get("findings", []) if rules2 else [])
                if f["rule_id"].startswith("cred-")]
        ok3 = rc_f == 0 and not left
        steps.append({"step": "修", "ok": ok3, "cred_left": left})

        # 步骤4 收敛：四维指标全绿
        metrics_file = Path(tmp) / "metrics.json"
        metrics_file.write_text(json.dumps({
            "tests_passed": True, "consistency_clean": True,
            "queue_empty": True, "metrics_stable": True}, ensure_ascii=False), encoding="utf-8")
        rc_c, conv, _ = _run([sys.executable, str(CONV), "--root", tmp,
                              "--metrics", str(metrics_file)])
        ok4 = rc_c == 0 and conv and conv.get("can_stop")
        steps.append({"step": "收敛", "ok": ok4})

        ok = all(s["ok"] for s in steps)
        _emit({"ok": ok, "steps": steps, "workdir": tmp})
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
