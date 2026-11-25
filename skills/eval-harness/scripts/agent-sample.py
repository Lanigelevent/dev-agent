#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent 侧口径驱动器：把「编码循环产出的补丁 → 官方 harness 评测 → 报告 →
台账」串成单命令（SWE-bench 评测链的 agent 侧入口）。

与 gold-sample.py 的分工：
    gold-sample.py   评测 **gold 补丁**（只验管线正确性）
    agent-sample.py  评测 **agent 产出的补丁**（code-task.py 的 edits.patch）
两者共用同一套评测与台账机制——本驱动只做「补丁收集 + 预测文件装配」，
评测一律委托 gold-sample.py（不重复实现下载/评测逻辑）。

补丁产物布局（<patches 根目录> 下每个实例一个目录）：
    <instance_id>/edits.patch          code-task.py 的补丁产物
    <instance_id>-v2/edits.patch       重跑版本（同实例多版本时取最新）
断点续跑语义：台账里已 DONE 的实例自动跳过（由 gold-sample.py 负责）；
单实例失败不阻断后续（失败记入台账 state，退出码 1）。round-64 起复评去冗：
`<out>/_patch-digests.json` 记每例上次实际送评的补丁 sha256，补丁变了就删掉
该例的 DONE 行重跑——实测同一 out 目录换补丁复评会拿回旧结论（假红/假绿
皆可复现）；摘要缺失按「变了」处理，宁可重跑不吃陈旧判分。
收集同时写 <out>/patch-provenance.json：每例的来源目录、更新的版本是否被判空
（stale_patch 标记）、code-task 的补丁即时校验结论、以及补丁完整性结论——
回退评旧补丁不再静默。

口径与 deepswe-sample.py 同源（round-48）：补丁完整性判定直接复用
deepswe-sample 的 `_patch_integrity`（同名同义，不复制实现）；critical 命中
（改/删既有测试、conftest / 解释器钩子、pytest 配置）的补丁不进预测文件、
不参加 resolved，`--allow-test-edits` 可显式豁免但保留 critical/waived 痕迹。
同时做补丁结构自检（`_patch_well_formed`，round-48）：hunk 头声明的行数与
实际不符（截断/损坏）的补丁 git apply 必败，不进预测文件、不可豁免——把
「补丁本身坏了」与「修错了」在归因上分开。
评测完成后另写 <out>/agent-sample-summary.json：每例的判分状态、评测墙钟
耗时、编码轮数/编辑数（取自 task-manifest），供 eval-cost-report.py 做成本
归一；token 用量 host 后端不暴露，如实留空不猜。

用法示例:
    py agent-sample.py --patches datasets/swe-out/agent-sample --out datasets/swe-out/agent-sample/eval
    py agent-sample.py --patches <目录> --instances django__django-14999 --dry-run

退出码: 0 = 全部实例完成（resolved/unresolved 均算完成）；1 = 存在失败实例
或完整性拦截（未豁免）；2 = 参数或输入错误。stdout 单 JSON 文档。
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GOLD = ROOT / "skills" / "eval-harness" / "scripts" / "gold-sample.py"
DEFAULT_MAP = ROOT / "datasets" / "swebench" / "lite-test-image-map.csv"
VER_RE = re.compile(r"^(?P<iid>.+)-v(?P<ver>\d+)$")
_DEEPSWE = None


def _deepswe():
    """按路径加载 deepswe-sample.py，复用其完整性/成本 helper（单一实现）。

    两个驱动同在 skills/eval-harness/scripts/，文件名带连字符不能直接 import；
    只共享纯函数，不触发 deepswe 的 main（模块有 `__main__` 保护）。
    """
    global _DEEPSWE
    if _DEEPSWE is None:
        path = Path(__file__).with_name("deepswe-sample.py")
        spec = importlib.util.spec_from_file_location("deepswe_sample_shared",
                                                      path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _DEEPSWE = mod
    return _DEEPSWE


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _patch_digest(patch_text):
    """补丁内容摘要：判断台账结论是否对应本轮实际送评的补丁。"""
    return hashlib.sha256(patch_text.encode("utf-8")).hexdigest()


def prune_stale_ledger(out_dir, digests):
    """清掉与当前补丁不一致的 DONE 台账行，返回被清掉的实例 id。

    gold-sample.py 对 state=DONE 的实例直接跳过（本驱动不透传 --force），
    同一 --out 目录换了补丁再评会原样拿回上一次的判定：round-64 实测第 3 版
    补丁复评返回旧补丁的 9 过 7 失败、elapsed 与上次一字不差（假红）；反过来
    先用好补丁跑出 resolved、再换坏补丁复评同样会假绿。
    摘要来源是 `_patch-digests.json`（上次实际送评的补丁），缺失按不一致处理。
    摘要不变则保留断点续跑语义（多实例续跑不受影响）。
    """
    out_dir = Path(out_dir)
    state_path = out_dir / "_patch-digests.json"
    ledger_path = out_dir / "gold-sample-ledger.json"
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    pruned = []
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except ValueError:
            ledger = {"results": []}
        keep = []
        for row in ledger.get("results", []):
            iid = row.get("instance_id")
            if (row.get("state") == "DONE" and iid in digests
                    and previous.get(iid) != digests[iid]):
                pruned.append(iid)
                continue
            keep.append(row)
        if pruned:
            ledger["results"] = keep
            ledger_path.write_text(
                json.dumps(ledger, ensure_ascii=False, indent=2),
                encoding="utf-8", newline="\n")
    merged = dict(previous)
    merged.update(digests)
    state_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                          encoding="utf-8", newline="\n")
    return pruned


def collect_patches(patches_dir, instances=None):
    """收集 agent 补丁 → ({instance_id: patch_text}, provenance 列表)。

    同实例多版本（<iid>-vN）取 edits.patch 最新者；mtime 相同（文件系统
    时间戳精度不足）时取版本号更高者，避免「谁先建谁赢」的偶然性。
    空补丁视为未产出。

    口径纪律（round-28 第 7 项，v1.28.0 实踩）：新版目录补丁为空时回退评
    上一版**不是错误，但必须可回答**——每个实例记录来源目录与被判空的版本，
    输出 `stale_patch` 标记与被携带的 patch_validation，避免「评的是旧补丁
    而台账写着这一版过了」这类静默失真。

    round-33 复核修正（真实语料人为触发实测）：`newer_versions_empty` 必须
    真的是**比来源版本更新**（-vN 编号更大）的空版本——旧实现只排除来源自身，
    于是「v2 无补丁文件、v3 已补齐」这类**已结案的历史空窗**也会把最新版
    误标 stale（真实补丁集上 4 例全属此形）。编号按目录名 -vN 解析（基目录
    为 0），与收集键（mtime, ver, name）同源的确定性口径；较旧的空版本仍
    记录在 `older_versions_empty`，只是不再误举 stale 旗。
    """
    latest = {}
    versions = {}
    for d in sorted(patches_dir.iterdir()):
        if not d.is_dir():
            continue
        patch = d / "edits.patch"
        m = VER_RE.match(d.name)
        iid = m.group("iid") if m else d.name
        ver = int(m.group("ver")) if m else 0
        if instances and iid not in instances:
            continue
        empty = (not patch.is_file()) or not patch.read_text(
            encoding="utf-8", errors="replace").strip()
        versions.setdefault(iid, []).append(
            {"dir": d.name, "empty": empty, "ver": ver})
        if empty:
            continue
        manifest = {}
        mpath = d / "task-manifest.json"
        if mpath.is_file():
            try:
                manifest = json.loads(mpath.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = {}
        text = patch.read_text(encoding="utf-8", errors="replace")
        validation = manifest.get("patch_validation") or {}
        # 证据排序键：校验不过线垫底；其余按版本号/时间取新
        key = (validation.get("ok") is not False, ver, patch.stat().st_mtime,
               d.name)
        if iid not in latest or key > latest[iid][0]:
            latest[iid] = (key, text, d.name, ver, validation)
    patches, provenance = {}, []
    for iid, (_key, text, src_dir, src_ver, validation) in sorted(latest.items()):
        patches[iid] = text
        src_path = patches_dir / src_dir
        integrity = _deepswe()._patch_integrity(src_path / "edits.patch")
        well_formed = _deepswe()._patch_well_formed(src_path / "edits.patch")
        stats = _deepswe()._code_task_stats(src_path)
        empties = [v for v in versions.get(iid, []) if v["empty"]]
        newer_empty = [v["dir"] for v in empties if v["ver"] > src_ver]
        older_empty = [v["dir"] for v in empties
                       if v["ver"] < src_ver or (v["ver"] == src_ver
                                                 and v["dir"] != src_dir)]
        # 候选透明化：每个非空版本的证据（校验结论/版本号）+ 落选原因
        candidates = []
        for v in versions.get(iid, []):
            if v["empty"]:
                continue
            vdir = patches_dir / v["dir"]
            vmanifest = {}
            mpath = vdir / "task-manifest.json"
            if mpath.is_file():
                try:
                    vmanifest = json.loads(mpath.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    vmanifest = {}
            vval = (vmanifest.get("patch_validation") or {})
            candidates.append({
                "dir": v["dir"], "ver": v["ver"],
                "validation_ok": vval.get("ok") is not False,
                "chosen": v["dir"] == src_dir,
                "reason": ("选中：校验过线且版本最新" if v["dir"] == src_dir
                           else ("落选：即时校验未过线"
                                 if vval.get("ok") is False
                                 else "落选：有更过线且更新的版本"))})
        provenance.append({"instance_id": iid, "source_dir": src_dir,
                           "newer_versions_empty": sorted(newer_empty),
                           "older_versions_empty": sorted(older_empty),
                           "stale_patch": bool(newer_empty),
                           "patch_validation": validation,
                           "patch_integrity": integrity,
                           "patch_well_formed": well_formed,
                           "code_task": stats,
                           "candidates": candidates})
    return patches, provenance


def _ledger_map(path, ids):
    """读 gold-sample 台账 → {iid: 判定/耗时}（只取本批实例，不串旧批）。"""
    try:
        ledger = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for row in ledger.get("results") or []:
        if isinstance(row, dict) and row.get("instance_id") in ids:
            out[row["instance_id"]] = {
                "state": row.get("state"),
                "resolved": row.get("resolved"),
                "diagnosis": row.get("diagnosis"),
                "elapsed_sec": row.get("elapsed_sec"),
            }
    return out


def write_summary(out_dir, provenance, ledger_path, ledger, dry_run,
                  eval_elapsed):
    """写 agent-sample-summary.json：判分状态 + 成本字段（与 deepswe 同名同义）。"""
    ids = {p["instance_id"] for p in provenance}
    evals = _ledger_map(ledger_path, ids) if (ledger and not dry_run) else {}
    details = []
    for p in provenance:
        integ = p.get("patch_integrity") or {}
        malformed = not (p.get("patch_well_formed") or {}).get("ok", True)
        blocked = not integ.get("ok", True) or malformed
        ev = evals.get(p.get("instance_id", "")) or {}
        stats = p.get("code_task") or {}
        if malformed:
            status = "malformed_patch"
        elif blocked:
            status = "integrity_flagged"
        elif dry_run:
            status = "not_evaluated"
        else:
            state = ev.get("state")
            if state == "DONE":
                status = "resolved" if ev.get("resolved") else "unresolved"
            else:
                status = (state or "not_evaluated").lower()
        details.append({
            "instance_id": p["instance_id"],
            "source_dir": p["source_dir"],
            "status": status,
            "resolved": (ev.get("resolved") if not blocked and ev else None),
            "diagnosis": ("malformed_patch" if malformed
                          else ("patch_integrity" if blocked
                                else ev.get("diagnosis"))),
            "elapsed_sec": ev.get("elapsed_sec"),
            "rounds": stats.get("rounds"),
            "edits": stats.get("edits"),
            "tests": stats.get("tests"),
            "code_task_elapsed_sec": stats.get("elapsed_sec"),
            "patch_integrity": {
                "ok": bool(integ.get("ok", True)),
                "waived": bool(integ.get("waived")),
                "critical": [c.get("code") for c in integ.get("critical") or []
                             if isinstance(c, dict)],
                "warnings": [c.get("code") for c in integ.get("warnings") or []
                             if isinstance(c, dict)],
            },
            "patch_well_formed": {
                "ok": bool((p.get("patch_well_formed") or {}).get("ok", True)),
                "issues": (p.get("patch_well_formed") or {}).get("issues") or [],
            },
            "stale_patch": bool(p.get("stale_patch")),
        })
    summary = {
        "schema": 1,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "instances": len(details),
        "submitted": (0 if dry_run else
                      sum(1 for d in details
                          if d["status"] not in ("integrity_flagged",
                                                 "malformed_patch"))),
        "resolved": sum(1 for d in details if d["resolved"] is True),
        "integrity_flagged": [d["instance_id"] for d in details
                              if d["status"] == "integrity_flagged"],
        "malformed_patch": [d["instance_id"] for d in details
                            if d["status"] == "malformed_patch"],
        "integrity_waived": [p["instance_id"] for p in provenance
                             if (p.get("patch_integrity") or {}).get("waived")],
        "stale_patch": [d["instance_id"] for d in details if d["stale_patch"]],
        "validation_flagged": [
            p["instance_id"] for p in provenance
            if (p.get("patch_validation") or {}).get("ok") is False],
        "eval_elapsed_sec": (None if dry_run else round(eval_elapsed, 3)),
        "tokens": {"available": False,
                   "reason": "host 后端不暴露 token 用量，如实留空不猜"},
        "details": details,
    }
    path = Path(out_dir) / "agent-sample-summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
    summary["summary_path"] = str(path)
    return summary


def main():
    parser = argparse.ArgumentParser(description="Agent 侧口径驱动器")
    parser.add_argument("--patches", required=True,
                        help="agent 补丁产物根目录（每实例一个子目录）")
    parser.add_argument("--instances", default="",
                        help="逗号分隔实例 id；缺省取目录中全部")
    parser.add_argument("--map", default=str(DEFAULT_MAP),
                        help="实例→镜像映射 CSV")
    parser.add_argument("--out", required=True, help="评测台账目录")
    parser.add_argument("--run-prefix", dest="run_prefix", default="agent")
    parser.add_argument("--model-name", dest="model_name",
                        default="dev-agent", help="model_name_or_path 字段")
    parser.add_argument("--eval-timeout", dest="eval_timeout", type=int,
                        default=1800)
    parser.add_argument("--cwd", default=str(ROOT / "datasets" / "swe-out" /
                                            "harness"),
                        help="harness 工作目录（汇总与日志落此处，勿用仓库根）")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="只装配预测文件并列出实例，不评测")
    parser.add_argument("--allow-test-edits", dest="allow_test_edits",
                        action="store_true",
                        help="允许补丁触碰测试/pytest 配置（patch_integrity "
                             "仍记录 critical，但标记 waived 不拦评测；"
                             "默认关闭——与 deepswe-sample 同口径）")
    argv = parser.parse_args()

    patches_dir = Path(argv.patches)
    if not patches_dir.is_dir():
        return _param_error("补丁目录不存在: %s" % patches_dir)
    map_path = Path(argv.map)
    if not map_path.is_file():
        return _param_error("映射 CSV 不存在: %s" % map_path)
    wanted = [i.strip() for i in argv.instances.split(",") if i.strip()]
    try:
        patches, provenance = collect_patches(patches_dir, wanted or None)
    except OSError as exc:
        return _param_error("补丁收集失败: %s" % exc)
    if not patches:
        return _param_error("补丁目录内无有效补丁: %s" % patches_dir)
    stale = [p["instance_id"] for p in provenance if p["stale_patch"]]
    flagged = [p["instance_id"] for p in provenance
               if (p.get("patch_validation") or {}).get("ok") is False]
    # 补丁完整性（与 deepswe-sample 同名同义）：critical 命中不进预测文件；
    # --allow-test-edits 只豁免拦截，critical/waived 仍留痕供审计
    integrity_flagged, integrity_waived = [], []
    for p in provenance:
        integ = p.get("patch_integrity") or {}
        if argv.allow_test_edits and not integ.get("ok", True):
            integ["waived"] = True
            integ["ok"] = True
            integrity_waived.append(p["instance_id"])
        if not integ.get("ok", True):
            integrity_flagged.append(p["instance_id"])
    # 结构自检（round-48）：截断/损坏的补丁 git apply 必败，进预测文件只会
    # 把「补丁本身坏了」混进 F2P_MISSED——不可豁免，与测试改动性质不同
    malformed = [p["instance_id"] for p in provenance
                 if not (p.get("patch_well_formed") or {}).get("ok", True)]
    blocked = set(integrity_flagged) | set(malformed)
    evaluable = {iid: text for iid, text in patches.items()
                 if iid not in blocked}

    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    preds = out_dir / "predictions-agent.jsonl"
    with preds.open("w", encoding="utf-8", newline="\n") as fh:
        for iid, text in evaluable.items():
            fh.write(json.dumps({"instance_id": iid,
                                 "model_name_or_path": argv.model_name,
                                 "model_patch": text},
                                ensure_ascii=False) + "\n")
    # 来源留档：每例评的是哪个版本目录、补丁即时校验结论、完整性结论、
    # 是否有更新的版本被判空——口径可复算，不靠人记
    (out_dir / "patch-provenance.json").write_text(
        json.dumps({"stale_patch": stale, "validation_flagged": flagged,
                    "integrity_flagged": integrity_flagged,
                    "integrity_waived": integrity_waived,
                    "malformed_patch": malformed,
                    "instances": provenance},
                   ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    if argv.dry_run:
        summary = write_summary(out_dir, provenance,
                                out_dir / "gold-sample-ledger.json",
                                False, True, 0.0)
        _emit({"ok": True, "dry_run": True, "predictions": str(preds),
               "instances": list(patches),
               "evaluable": list(evaluable),
               "stale_patch": stale, "validation_flagged": flagged,
               "integrity_flagged": integrity_flagged,
               "integrity_waived": integrity_waived,
               "malformed_patch": malformed,
               "provenance": str(out_dir / "patch-provenance.json"),
               "summary": summary["summary_path"],
               "patch_bytes": {k: len(v) for k, v in patches.items()}})
        return 0

    if not evaluable:
        summary = write_summary(out_dir, provenance,
                                out_dir / "gold-sample-ledger.json",
                                False, False, 0.0)
        _emit({"ok": False,
               "error": "全部补丁被拦截（完整性红线或补丁结构损坏）: %s"
                        % ", ".join(integrity_flagged + malformed),
               "integrity_flagged": integrity_flagged,
               "malformed_patch": malformed,
               "summary": summary["summary_path"]})
        return 1

    # 复评去冗（round-64）：补丁变了的 DONE 行先清掉，否则 gold-sample 会
    # 直接跳过并把上一次的判定原样搬回来
    ledger_rerun = prune_stale_ledger(out_dir, {
        iid: _patch_digest(text) for iid, text in evaluable.items()})

    cmd = [sys.executable, str(GOLD), "--all-from", str(preds),
           "--predictions", str(preds), "--map", str(map_path),
           "--out", str(out_dir), "--run-prefix", argv.run_prefix,
           "--eval-timeout", str(argv.eval_timeout), "--cwd", str(argv.cwd)]
    eval_started = time.monotonic()
    proc = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=7200)
    eval_elapsed = time.monotonic() - eval_started
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"raw_stdout": proc.stdout[-2000:]}
    summary = write_summary(out_dir, provenance,
                            out_dir / "gold-sample-ledger.json",
                            True, False, eval_elapsed)
    data["ok"] = proc.returncode == 0 and not (integrity_flagged or malformed)
    data["predictions"] = str(preds)
    data["stale_patch"] = stale
    data["validation_flagged"] = flagged
    data["integrity_flagged"] = integrity_flagged
    data["integrity_waived"] = integrity_waived
    data["malformed_patch"] = malformed
    data["ledger_rerun"] = ledger_rerun
    data["summary"] = summary["summary_path"]
    _emit(data)
    return 0 if (proc.returncode == 0
                 and not (integrity_flagged or malformed)) else 1


if __name__ == "__main__":
    sys.exit(main())
