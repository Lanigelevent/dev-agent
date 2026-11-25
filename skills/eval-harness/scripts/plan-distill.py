#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复计划蒸馏（round-34，升级计划阶段 1-A；借 ConRAD 蒸馏思想）。

退出码：
    0 = 蒸馏完成（含 resolved 为 0 的空蒸馏）
    2 = 输入不可读（产物目录 / caliber / 落盘路径错误）

原料：已 resolved 实例的产物（补丁 + manifest + 溯源），不是拍脑袋经验。
判定规则先于数字写死：
  1. 只蒸馏 caliber 判定 resolved=True 的实例——未过实例的补丁形状不进原料；
  2. 每例蒸馏：触及文件清单、hunk 统计、轮数/编辑数（取自 task-manifest，不信叙述）；
  3. 按仓库家族聚合：高频文件前缀、轮数区间、补丁规模区间；
  4. 产物 retro/repair-plans.json 是**只读参考**——code-task 材料装配时命中
     仓库家族就附带，让「这类仓库的修复通常长什么样」先于模型猜测存在。
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 与既有 HUNK_RE（^@@ -n +n @@ 位置形，六脚本共享的位次解析）语义不同——
# 这里要的是 hunk 尾部上下文文本（函数/类名），故独立命名 HUNK_CTX_RE。
HUNK_CTX_RE = re.compile(r"^@@ .*? @@\s*(.*)$", re.M)
DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/", re.M)


def distill_instance(patch_text, manifest):
    """单例蒸馏：文件清单 + hunk 上下文 + 规模与轮次（全部来自产物本身）。"""
    files = DIFF_FILE_RE.findall(patch_text or "")
    hunks = [h.strip() for h in HUNK_CTX_RE.findall(patch_text or "") if h.strip()]
    added = sum(1 for l in (patch_text or "").splitlines()
                if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in (patch_text or "").splitlines()
                  if l.startswith("-") and not l.startswith("---"))
    return {
        "files": files,
        "hunk_contexts": hunks[:20],
        "added_lines": added,
        "removed_lines": removed,
        "rounds": manifest.get("rounds", manifest.get("round")),
        "edits": manifest.get("edits", manifest.get("edits_applied")),
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="修复计划蒸馏")
    ap.add_argument("--patches", required=True, help="agent-sample 产物根")
    ap.add_argument("--caliber", required=True, help="caliber 口径 JSON")
    ap.add_argument("--out", required=True, help="repair-plans.json 落盘路径")
    argv = ap.parse_args()

    patches_dir = Path(argv.patches)
    try:
        caliber = json.loads(Path(argv.caliber).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": "caliber 不可读: %s" % exc},
                         ensure_ascii=False))
        return 2
    if not patches_dir.is_dir():
        print(json.dumps({"ok": False, "error": "产物目录不存在: %s"
                          % patches_dir}, ensure_ascii=False))
        return 2
    instances = caliber.get("detail") or {}
    resolved_ids = sorted(iid for iid, row in instances.items()
                          if bool(row.get("resolved")))

    per_repo = {}
    used = []
    for iid in resolved_ids:
        # 与收集器同源的选版口径：该校验过线的最新非空版本
        cands = []
        for d in sorted(patches_dir.iterdir()):
            if not (d.is_dir() and (d.name == iid
                                    or d.name.startswith(iid + "-v"))):
                continue
            patch = d / "edits.patch"
            if not patch.is_file() or patch.stat().st_size == 0:
                continue
            manifest = {}
            mp = d / "task-manifest.json"
            if mp.is_file():
                try:
                    manifest = json.loads(mp.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    manifest = {}
            ver_m = re.search(r"-v(\d+)$", d.name)
            ver = int(ver_m.group(1)) if ver_m else 1
            val = manifest.get("patch_validation") or {}
            cands.append((val.get("ok") in (True, None), ver,  # 三态：仅显式 False 视为校验未过线
                          patch.stat().st_mtime, d, patch, manifest))
        if not cands:
            continue
        cands.sort()
        _, _, _, d, patch, manifest = cands[-1]
        repo = iid.split("__")[0]
        entry = distill_instance(patch.read_text(encoding="utf-8",
                                                 errors="replace"), manifest)
        entry["instance_id"] = iid
        entry["source_dir"] = d.name
        used.append(entry)
        agg = per_repo.setdefault(repo, {"instances": [], "files": Counter(),
                                         "rounds": [], "added": []})
        agg["instances"].append(iid)
        for f in entry["files"]:
            # 文件前缀到目录级（django/db/migrations），文件级太碎聚合不出形状
            agg["files"]["/".join(f.split("/")[:3])] += 1
        if entry["rounds"] is not None:
            agg["rounds"].append(entry["rounds"])
        agg["added"].append(entry["added_lines"])

    plans = {}
    for repo, agg in sorted(per_repo.items()):
        plans[repo] = {
            "instances": agg["instances"],
            "top_file_prefixes": agg["files"].most_common(5),
            "rounds_minmax": [min(agg["rounds"]), max(agg["rounds"])]
            if agg["rounds"] else None,
            "added_lines_minmax": [min(agg["added"]), max(agg["added"])]
            if agg["added"] else None,
        }

    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rule": "只蒸馏 resolved=True 实例；数据全部取自补丁与 manifest 产物",
               "resolved_count": len(used), "plans": plans,
               "details": used}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"ok": True, "resolved_distilled": len(used),
                      "repo_families": sorted(plans)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
