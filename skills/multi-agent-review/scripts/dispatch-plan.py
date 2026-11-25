#!/usr/bin/env python3
"""机械定维度：对 diff 按 7 个固定维度判启用/跳过，输出 dimensions_enabled/skipped。

用途:
    主流程步骤 4。机械计划只负责「该跑的一路不少」；
    异常集中时的动态增派不在此文件，且不拿本计划当路数上限。

用法:
    python dispatch-plan.py --diff change.diff --intent "修复支付回调逻辑"

退出码:
    0 = 正常
    1 = diff 读不到或解析不出文件（无 +++/@@ 头）
    2 = 参数错误（缺 --diff）
"""
import argparse
import json
import re
import sys
from pathlib import Path

DIMENSIONS = [
    "正确性与逻辑缺陷",
    "跨文件影响",
    "回退风险与影响面",
    "测试覆盖",
    "性能与资源",
    "安全与敏感信息",
    "意图一致性",
]
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


DEP_FILE_RE = re.compile(
    r"(requirements[^/]*\.txt|package\.json|package-lock\.json|go\.(mod|sum)|pom\.xml|"
    r"Cargo\.toml|pyproject\.toml|setup\.(py|cfg)|Dockerfile|Makefile|\.github/|"
    r"\.gitlab-ci|Jenkinsfile|\.sql$|migrat)", re.I
)
SIG_RE = re.compile(r"\bdef\s+\w+\s*\(|\bfunc\s+\w+|\bclass\s+\w+")
TEST_RE = re.compile(r"(?:^|/)(?:tests?/|test_[^/]*\.py|[^/]*_test\.(?:py|go|js)|[^/]*\.spec\.[jt]s)", re.I)
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".c", ".cc", ".cpp",
            ".h", ".hpp", ".rb", ".rs", ".cs", ".php", ".sql"}
IMPORT_RE = re.compile(r"\bimport\s+\w+|#include\s*<|\brequire\s*\(")
PERF_SEC_RE = re.compile(r"query|render|serialize|escape", re.I)
SEC_RE = re.compile(r"password|api[_-]?key|secret|token\s*\"?\s*[:=]|AKIA[0-9A-Z]{16}|"
                    r"BEGIN [A-Z ]*PRIVATE KEY|(?<![.\w])eval\s*\(|(?<![.\w])exec\s*\(|"
                    r"shell\s*=\s*True|pickle\.loads|yaml\.load|os\.system|os\.popen|os\.environ|mysql://", re.I)


def plan(files, intent):
    added_lines = [t for f in files for _, t in f["added"]]
    all_paths = [f["path"] for f in files]
    top_dirs = {p.split("/")[0] for p in all_paths}
    has_new_import = any(IMPORT_RE.search(t) for t in added_lines)
    dep_hit = [p for p in all_paths if DEP_FILE_RE.search(p)]
    sig_hit = [t for f in files for _, t in f["added"] if SIG_RE.search(t)]
    test_files = [p for p in all_paths if TEST_RE.search(p)]
    src_files = [p for p in all_paths if Path(p).suffix.lower() in CODE_EXT]
    perf_sec = [t for t in added_lines if PERF_SEC_RE.search(t)]

    enabled, skipped = {}, {}
    enabled["正确性与逻辑缺陷"] = "任何 diff 必启"
    if len(top_dirs) >= 2 or has_new_import:
        enabled["跨文件影响"] = "跨 %d 个目录或存在新增 import" % len(top_dirs)
    else:
        skipped["跨文件影响"] = "单目录且无新增 import"
    if dep_hit or sig_hit:
        reason = []
        if dep_hit:
            reason.append("改到依赖/配置/迁移: %s" % ", ".join(dep_hit[:3]))
        if sig_hit:
            reason.append("新增函数/类签名")
        enabled["回退风险与影响面"] = "；".join(reason)
    else:
        skipped["回退风险与影响面"] = "未触依赖/配置/迁移/公开签名"
    if test_files:
        enabled["测试覆盖"] = "存在测试改动: %s" % ", ".join(test_files[:3])
    elif src_files:
        enabled["测试覆盖"] = "源码改动无对应测试改动"
    else:
        skipped["测试覆盖"] = "无源码与测试改动"
    if perf_sec:
        enabled["性能与资源"] = "新增行含 query/render/serialize/escape"
    else:
        skipped["性能与资源"] = "新增行不含 query/render/serialize/escape"
    sec_hit = [t for t in added_lines if SEC_RE.search(t)]
    if perf_sec or sec_hit:
        reason = "新增行含 query/render/serialize/escape" if perf_sec \
            else "新增行命中凭据/危险函数形态 %d 处" % len(sec_hit)
        enabled["安全与敏感信息"] = reason
    else:
        skipped["安全与敏感信息"] = "新增行无安全敏感形态"
    if intent and len(intent.strip()) >= 10:
        enabled["意图一致性"] = "意图说明 >= 10 字符"
    else:
        skipped["意图一致性"] = "无有效意图说明"
    return enabled, skipped


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="机械定维度")
    parser.add_argument("--diff", required=True, help="diff 文件路径")
    parser.add_argument("--intent", default="", help="意图说明（>=10 字符启用意图一致性）")
    parser.add_argument("--experience", default="", help="误报模式库 JSON 或目录（按维度输出举证等级）")
    argv = parser.parse_args()
    p = Path(argv.diff)
    if not p.is_file():
        _emit({"ok": False, "error": "diff 文件不存在: %s" % p})
        return 1
    files = parse_diff(p.read_text(encoding="utf-8", errors="replace"))
    if not files:
        _emit({"ok": False, "error": "diff 解析不出文件（缺 +++/@@ 头）"})
        return 1
    enabled, skipped = plan(files, argv.intent)
    evidence_levels = {}
    if argv.experience:
        xp = Path(argv.experience)
        if xp.is_dir():
            xp = xp / "experience.json"
        if xp.is_file():
            try:
                xdata = json.loads(xp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                xdata = {"entries": []}
            for dim in enabled:
                counts = [e.get("rejected_count", 0) for e in xdata.get("entries", [])
                          if e.get("dimension") == dim]
                if counts:
                    best = max(counts)
                    evidence_levels[dim] = ("严格" if best >= 5 else
                                            "加强" if best >= 2 else "常规")
    _emit(
        {
            "ok": True,
            "dimensions_total": len(DIMENSIONS),
            "dimensions": list(DIMENSIONS),
            "dimensions_enabled": [d for d in DIMENSIONS if d in enabled],
            "enable_reasons": enabled,
            "dimensions_skipped": [{"name": d, "reason": skipped[d]} for d in DIMENSIONS if d in skipped],
            "evidence_levels": evidence_levels,
            "routes": len(enabled),
            "files": len(files),
            "note": "机械计划管「该跑的一路不少」；动态增派上限另受 max_dynamic_dispatches 约束",
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
