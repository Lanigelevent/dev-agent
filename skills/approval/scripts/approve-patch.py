#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核人闸 2（补丁准出）：对修复团队的补丁包做独立核验并签发批准书。

核验不信任修复团队自述，六项检查全部通过才签 APPROVED：
1. 工单绑定：manifest.order_id 与工单一致；补丁触及的文件与规则均出自工单
   approved 清单，不得夹带；
2. 基线一致：工单、补丁包、被审仓库 HEAD 三方 base_sha 相同；
3. 可应用：git apply 预检对每个补丁通过；
4. 内容红线：对每个补丁的新增行跑硬规则扫描，必须零发现（防止补丁自身
   引入缺陷或明文凭据）；
5. 路径安全：所有触及路径均为仓库相对路径且不越出仓库根；
6. 结构不变量：与值形态扫描去相关的第二意见——新增 import 限于白名单
   （修复器只会补 sys），新增行不得出现裸 except。

产出 approval.json（含 manifest 的 sha256 绑定，防篡改）；修复团队脚本的
落盘必须持本批准书，否则拒绝施工。

用法示例：
    py approve-patch.py --order work-order.json --manifest fix-manifest.json \
        --repo <被审仓库> --out <产物目录>

退出码：0=APPROVED；1=REJECTED（reasons 列明）；2=输入错误。
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RULES_SCRIPT = (ROOT / "skills" / "multi-agent-review" / "scripts"
                / "deterministic-rules.py")
CASE_MATCH = (ROOT / "skills" / "director" / "scripts" / "case-match.py")
CASE_DIR = ROOT / "retro"


def _reuse_hints(reasons):
    """主观能动性：拒绝时主动查案例库，帮修复团队一次改对（查不到即为空）。"""
    if not reasons or not CASE_MATCH.is_file():
        return []
    try:
        proc = subprocess.run(
            [sys.executable, str(CASE_MATCH), "--match",
             " ".join(reasons)[:400], "--out", str(CASE_DIR)],
            shell=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60)
        if proc.returncode != 0:
            return []
        hits = json.loads(proc.stdout).get("hits", [])
        return [{"title": h.get("title", ""), "takeaway": h.get("takeaway", ""),
                 "url": h.get("url", ""), "local_ref": h.get("local_ref", "")}
                for h in hits[:2]]
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []  # 案例库不可用不阻塞裁定本身


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _git(repo, args):
    proc = subprocess.run(["git", "-C", str(repo)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_order_binding(order, manifest, reasons):
    """检查 1：补丁包必须完全出自工单 approved 清单。"""
    approved_files = {}
    for entry in order.get("approved", []):
        rel = Path(str(entry.get("file", ""))).as_posix()
        approved_files.setdefault(rel, set()).add(str(entry.get("rule_id")))
    approved_ids = {str(e.get("rule_id")) for e in order.get("approved", [])}
    ok = True
    if manifest.get("order_id") != order.get("order_id"):
        reasons.append("manifest.order_id(%s) 与工单(%s)不一致"
                       % (manifest.get("order_id"), order.get("order_id")))
        ok = False
    for item in manifest.get("files", []):
        rel = Path(str(item.get("path", ""))).as_posix()
        if rel not in approved_files:
            reasons.append("补丁触及工单外文件: %s" % rel)
            ok = False
            continue
        stray = set(item.get("rules", [])) - approved_files[rel]
        if stray:
            reasons.append("文件 %s 含工单外规则: %s" % (rel, sorted(stray)))
            ok = False
    stray_rules = set()
    for item in manifest.get("files", []):
        stray_rules |= set(item.get("rules", []))
    extra = stray_rules - approved_ids
    if extra:
        reasons.append("补丁含工单外规则: %s" % sorted(extra))
        ok = False
    return ok


def _check_base_sha(order, manifest, repo, reasons):
    """检查 2：三方基线一致。"""
    rc, head = _git(repo, ["rev-parse", "HEAD"])
    if rc != 0:
        reasons.append("无法读取仓库 HEAD: %s" % head[:200])
        return False
    if not (order.get("base_sha") == manifest.get("base_sha") == head):
        reasons.append("基线不一致: 工单 %s / 补丁包 %s / HEAD %s"
                       % (str(order.get("base_sha"))[:12],
                          str(manifest.get("base_sha"))[:12], head[:12]))
        return False
    return True


def _check_apply(repo, manifest, manifest_dir, reasons):
    """检查 3：git apply 预检。"""
    for item in manifest.get("files", []):
        patch = (manifest_dir / item.get("patch_file", "")).resolve()
        if not patch.is_file():
            reasons.append("补丁文件缺失: %s" % item.get("patch_file"))
            return False
        rc, out = _git(repo, ["apply", "--check", str(patch)])
        if rc != 0:
            reasons.append("git apply 预检失败(%s): %s" % (item.get("path"), out[:300]))
            return False
    return True


def _check_content(manifest, manifest_dir, reasons):
    """检查 4：新增行零命中（补丁不得引入缺陷或明文凭据）。"""
    for item in manifest.get("files", []):
        patch = (manifest_dir / item.get("patch_file", "")).resolve()
        proc = subprocess.run([sys.executable, str(RULES_SCRIPT),
                               "--diff-file", str(patch)], shell=False,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        if proc.returncode != 0:
            reasons.append("补丁新增行扫描失败(%s): %s" % (item.get("path"),
                                                          proc.stderr[:200]))
            return False
        try:
            findings = json.loads(proc.stdout).get("findings", [])
        except ValueError:
            reasons.append("补丁新增行扫描输出非 JSON(%s)" % item.get("path"))
            return False
        if findings:
            reasons.append("补丁新增行引入问题(%s): %s"
                           % (item.get("path"),
                              sorted({f.get("rule_id", "") for f in findings})))
            return False
    return True


def _check_paths(manifest, reasons):
    """检查 5：路径安全（相对路径、不越出仓库根）。"""
    ok = True
    for item in manifest.get("files", []):
        raw = str(item.get("path", ""))
        p = Path(raw)
        if p.is_absolute() or ".." in p.parts or raw.startswith("/"):
            reasons.append("路径不安全: %s" % raw)
            ok = False
    return ok


STRUCTURE_IMPORT_ALLOW = {"sys", "json", "re", "math"}
IMPORT_RE = re.compile(r"^(?:import\s+([.\w]+)|from\s+([.\w]+)\s+import\b)")
BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:")


def _check_structure(manifest, manifest_dir, reasons):
    """检查 6：结构不变量（与值形态扫描去相关的第二意见）。

    引擎补丁（ruff isort 等）会重排既有 import：新增行与删除行相同的
    import 视为移动而非新引入，放行；真正的新导入仍受白名单约束。
    """
    ok = True
    for item in manifest.get("files", []):
        patch = (manifest_dir / item.get("patch_file", "")).resolve()
        if not patch.is_file():
            continue
        patch_lines = patch.read_text(encoding="utf-8",
                                      errors="replace").splitlines()
        added = [line[1:] for line in patch_lines
                 if line.startswith("+") and not line.startswith("+++")]
        removed = {line[1:].strip() for line in patch_lines
                   if line.startswith("-") and not line.startswith("---")}
        for line in added:
            m = IMPORT_RE.match(line)
            if m:
                module = (m.group(1) or m.group(2) or "").split(".")[0]
                if module not in STRUCTURE_IMPORT_ALLOW \
                        and line.strip() not in removed:
                    reasons.append("补丁引入白名单外导入(%s): %s"
                                   % (item.get("path"), module))
                    ok = False
            if BARE_EXCEPT_RE.match(line):
                reasons.append("补丁新增裸 except(%s)" % item.get("path"))
                ok = False
    return ok


def main():
    parser = argparse.ArgumentParser(description="审核人闸 2：补丁准出（只读）")
    parser.add_argument("--order", required=True, help="闸 1 签发的工单 JSON")
    parser.add_argument("--manifest", required=True, help="修复团队的 fix-manifest.json")
    parser.add_argument("--repo", required=True, help="被审仓库根")
    parser.add_argument("--out", required=True, help="批准书产物目录")
    argv = parser.parse_args()
    order_path = Path(argv.order)
    manifest_path = Path(argv.manifest)
    repo = Path(argv.repo).resolve()
    out = Path(argv.out)
    for label, path in (("工单", order_path), ("补丁清单", manifest_path)):
        if not path.is_file():
            _emit({"ok": False, "error": "%s不存在: %s" % (label, path)})
            return 2
    if not repo.is_dir():
        _emit({"ok": False, "error": "仓库目录不存在: %s" % repo})
        return 2
    try:
        order = json.loads(order_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "JSON 非法: %s" % exc})
        return 2

    reasons = []
    checks = [
        ("order-binding", _check_order_binding(order, manifest, reasons)),
        ("base-sha", _check_base_sha(order, manifest, repo, reasons)),
        ("apply", _check_apply(repo, manifest, manifest_path.resolve().parent,
                               reasons)),
        ("content", _check_content(manifest, manifest_path.resolve().parent,
                                   reasons)),
        ("path-safety", _check_paths(manifest, reasons)),
        ("structure", _check_structure(manifest, manifest_path.resolve().parent,
                                       reasons)),
    ]
    verdict = "APPROVED" if all(ok for _n, ok in checks) else "REJECTED"
    hints = _reuse_hints(reasons) if verdict == "REJECTED" else []
    out.mkdir(parents=True, exist_ok=True)
    approval = {"verdict": verdict, "order_id": order.get("order_id"),
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": _sha256_file(manifest_path),
                "base_sha": manifest.get("base_sha"),
                "checks": [{"name": name, "ok": ok} for name, ok in checks],
                "reasons": reasons,
                "reuse_hints": hints}
    approval_path = out / "approval.json"
    approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2),
                             encoding="utf-8", newline="\n")
    _emit({"ok": verdict == "APPROVED", "verdict": verdict,
           "approval_path": str(approval_path), "checks": approval["checks"],
           "reasons": reasons, "reuse_hints": hints})
    return 0 if verdict == "APPROVED" else (1 if reasons else 2)


if __name__ == "__main__":
    sys.exit(main())
