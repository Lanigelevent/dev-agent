#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核人闸 1（范围裁定）：把评审发现清单裁定为修复工单（只读被审仓库）。

审核人独立于评审团队与修复团队：本脚本调用修复团队的分诊（fix-plan.py）
取得 fixable/manual 分类，再叠加严重度政策做裁定，产出 work-order.json——
修复团队唯一合法的施工依据（fix-patch.py 只吃工单）。拒绝项必带原因。

裁定规则：
- 不在修复白名单 → 拒绝（原因取分诊 blocker）；
- 非 .py 文件 → 拒绝（白名单仅覆盖 Python）；
- 严重度不在 --severities 政策内 → 拒绝（默认政策放行全部白名单缺陷）。

用法示例：
    py approve-plan.py --findings findings.json --repo <被审仓库> --out <产物目录>
    py approve-plan.py --findings findings.json --repo <路径> --out <目录> --severities 高,中

退出码：0=成功（含全部拒绝）；2=输入错误。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIX_PLAN = ROOT / "skills" / "repair" / "scripts" / "fix-plan.py"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.returncode, proc.stdout.strip()


def _key(entry):
    return (entry.get("rule_id", ""), entry.get("file", ""), str(entry.get("line")))


def _rel(repo, file_str):
    """把文件路径归一化为仓库相对路径；越出仓库根返回 None。"""
    p = Path(str(file_str))
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo).as_posix()
        except ValueError:
            return None
    return p.as_posix()


def main():
    parser = argparse.ArgumentParser(description="审核人闸 1：修复范围裁定（只读）")
    parser.add_argument("--findings", required=True, help="评审发现清单 JSON 文件")
    parser.add_argument("--repo", required=True, help="被审仓库根")
    parser.add_argument("--out", required=True, help="工单产物目录")
    parser.add_argument("--severities", default="",
                        help="放行的严重度，逗号分隔；缺省放行全部")
    argv = parser.parse_args()
    fp = Path(argv.findings)
    repo = Path(argv.repo).resolve()
    out = Path(argv.out)
    if not fp.is_file():
        _emit({"ok": False, "error": "发现清单不存在: %s" % fp})
        return 2
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库目录不存在: %s" % repo})
        return 2
    rc, head = _git(repo, ["rev-parse", "HEAD"])
    if rc != 0:
        _emit({"ok": False, "error": "仓库非 git 或无提交: %s" % head[:200]})
        return 2
    try:
        raw = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "发现清单 JSON 非法: %s" % exc})
        return 2
    severities = {s.strip() for s in argv.severities.split(",") if s.strip()}

    # 调修复团队的分诊（跨团队协作走 CLI 与产物，不做代码级耦合）
    proc = subprocess.run([sys.executable, str(FIX_PLAN), "--findings",
                           str(fp), "--repo", str(repo)], shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    if proc.returncode != 0:
        _emit({"ok": False, "error": "分诊失败: %s" % proc.stderr[:300]})
        return 2
    try:
        triage = json.loads(proc.stdout)
    except ValueError:
        _emit({"ok": False, "error": "分诊输出非 JSON"})
        return 2

    severity_of = {}
    for item in (raw.get("findings") if isinstance(raw, dict) else raw) or []:
        if isinstance(item, dict):
            rel = _rel(repo, item.get("file", ""))
            severity_of[_key({"rule_id": item.get("rule_id"),
                              "file": rel or str(item.get("file")),
                              "line": item.get("line")})] = item.get("severity", "")

    approved, rejected = [], []
    for entry in triage.get("fixable", []):
        rel = _rel(repo, entry.get("file", ""))
        if rel is None:
            rejected.append(dict(entry, reason="路径越出仓库根，拒绝处理"))
            continue
        entry = dict(entry, file=rel)
        severity = severity_of.get(_key(entry), "")
        if severities and severity not in severities:
            rejected.append(dict(entry, severity=severity,
                                 reason="严重度不在政策内（政策: %s）"
                                        % ",".join(sorted(severities))))
            continue
        approved.append(dict(entry, severity=severity))
    for entry in triage.get("manual", []):
        rel = _rel(repo, entry.get("file", ""))
        entry = dict(entry, file=rel if rel is not None else str(entry.get("file")))
        rejected.append(dict(entry, severity=severity_of.get(_key(entry), ""),
                             reason="分诊结论 manual: %s" % entry.get("blocker", "")))

    out.mkdir(parents=True, exist_ok=True)
    order = {"order_id": head[:12], "repo": str(repo), "base_sha": head,
             "policy": {"severities": sorted(severities)},
             "approved": approved, "rejected": rejected}
    order_path = out / "work-order.json"
    order_path.write_text(json.dumps(order, ensure_ascii=False, indent=2),
                          encoding="utf-8", newline="\n")
    _emit({"ok": True, "order_path": str(order_path), "order_id": head[:12],
           "approved_count": len(approved), "rejected_count": len(rejected),
           "note": "工单已签发；修复团队凭工单出补丁，落盘另需闸 2 批准书"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
