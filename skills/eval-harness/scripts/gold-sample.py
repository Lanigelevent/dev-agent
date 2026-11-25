#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gold 扩样驱动器：把「镜像映射 → 逐层下载 → docker load → 官方评测 →
报告 → 台账」串成单命令（SWE-bench Phase 3B 扩样的批量化入口）。

编排的既有脚本（本驱动不实现任何下载/评测逻辑）：
    scripts/docker-image-fetch.py  plan/fetch/assemble/load 四阶段
    agent/swe_run.py               eval（官方 harness）/ report
数据源：
    --map      实例→镜像映射 CSV（instance_id,image 两列，至少表头）；
               缺省 datasets/swebench/lite-test-image-map.csv
    --predictions  gold 预测 jsonl（含多实例时按 instance_id 过滤）
断点续跑语义：已 resolved 或已 APPLIED 镜像的实例自动跳过（--force 重跑）；
单实例失败不阻断后续（失败记入台账 state，退出码 1）。

用法示例:
    py gold-sample.py --instances django__django-12284 --out datasets/swe-out/gold-sample
    py gold-sample.py --all-from predictions-gold6.jsonl --out <目录> --segments 16

退出码: 0 = 全部实例完成（resolved/unresolved 均算完成）；1 = 存在失败实例；
2 = 参数或输入错误。stdout 单 JSON 文档。
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FETCH = ROOT / "scripts" / "docker-image-fetch.py"
SWE_RUN = ROOT / "agent" / "swe_run.py"
DEFAULT_MAP = ROOT / "datasets" / "swebench" / "lite-test-image-map.csv"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _run(cmd, timeout=7200, input_text=None):
    p = subprocess.run([str(c) for c in cmd], shell=False, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, input=input_text)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    return p.returncode, data, p.stderr


def load_map(path):
    """读实例→镜像映射；返回 {instance_id: image_tag}。"""
    mapping = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            iid = (row.get("instance_id") or "").strip()
            img = (row.get("image") or "").strip()
            if iid and img:
                mapping[iid] = img
    return mapping


def load_predictions(path):
    """读 gold 预测；返回 {instance_id: 行 dict}。"""
    preds = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        preds[row["instance_id"]] = row
    return preds


def image_loaded(image):
    """镜像是否已在本地（docker images 查询；docker 缺席返回 False）。"""
    docker = None
    import os
    import shutil
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cand = Path(local) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if cand.is_file():
            docker = str(cand)
    if not docker:
        docker = shutil.which("docker") or ""
    if not docker:
        return False
    p = subprocess.run([docker, "images", "--format", "{{.Repository}}:{{.Tag}}"],
                       shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    return image in (p.stdout or "")


def process_instance(iid, image, pred, argv):
    """单实例全链计时包装：elapsed_sec 计整条链（下载缓存命中时只含评测）。"""
    started = time.monotonic()
    out = _process_instance(iid, image, pred, argv)
    out["elapsed_sec"] = round(time.monotonic() - started, 3)
    return out


def _process_instance(iid, image, pred, argv):
    """单实例全链：fetch 四阶段 → eval → report。返回结果 dict。"""
    cache = Path(argv.out) / "imagecache"
    out = {"instance_id": iid, "image": image, "state": "?"}
    if not argv.force and image_loaded(image):
        out["image_state"] = "already-loaded"
    else:
        rc, plan, err = _run([sys.executable, FETCH, "plan",
                              "--image", image, "--mirror", argv.mirror,
                              "--out", str(cache)], timeout=120)
        if rc != 0:
            out.update(state="PLAN_FAILED", error=(err or "")[:200])
            return out
        rc, fetched, err = _run([sys.executable, FETCH, "fetch",
                                 "--image", image, "--mirror", argv.mirror,
                                 "--plan", str(cache / "plan.json"),
                                 "--out", str(cache),
                                 "--retries", argv.retries,
                                 "--segments", argv.segments,
                                 "--workers", argv.workers])
        if rc != 0:
            out.update(state="FETCH_FAILED",
                       error=str((fetched or {}).get("error", err))[:200])
            return out
        archive = cache / ("%s.tar" % iid)
        rc, assembled, err = _run([sys.executable, FETCH, "assemble",
                                   "--plan", str(cache / "plan.json"),
                                   "--blobs", str(cache),
                                   "--out", str(archive),
                                   "--image", image], timeout=1800)
        if rc != 0:
            out.update(state="ASSEMBLE_FAILED", error=(err or "")[:200])
            return out
        rc, loaded, err = _run([sys.executable, FETCH, "load",
                                "--archive", str(archive)], timeout=1800)
        if rc != 0:
            out.update(state="LOAD_FAILED",
                       error=str((loaded or {}).get("error", err))[:200])
            return out
        out["image_state"] = "loaded"
        out["fetch_kbps"] = (fetched or {}).get("kbps")
    # 单实例预测文件（**绝对路径**：harness 在 --cwd 下运行，相对路径会找不到）
    pred_file = (Path(argv.out) / ("pred-%s.jsonl" % iid)).resolve()
    pred_file.parent.mkdir(parents=True, exist_ok=True)
    pred_file.write_text(json.dumps(pred, ensure_ascii=False) + "\n",
                         encoding="utf-8", newline="\n")
    run_id = "%s-%s" % (argv.run_prefix, iid)
    rc, evaled, err = _run([sys.executable, SWE_RUN, "eval",
                            "--predictions", str(pred_file),
                            "--run-id", run_id, "--cwd", str(Path(argv.cwd).resolve()),
                            "--timeout", argv.eval_timeout], timeout=7200)
    if rc != 0:
        out.update(state="EVAL_FAILED",
                   error=str((evaled or {}).get("error", err))[:200])
        return out
    rc, report, err = _run([sys.executable, SWE_RUN, "report",
                            "--run-id", run_id,
                            "--logs-root", str((Path(argv.cwd) / "logs/run_evaluation").resolve())],
                           timeout=120)
    if rc != 0 or not report:
        out.update(state="REPORT_FAILED", error=(err or "")[:200])
        return out
    inst = next((i for i in report.get("instances", [])
                 if i["instance_id"] == iid), None)
    out.update(state="DONE", resolved=bool(inst and inst["resolved"]),
               fail_to_pass=inst["fail_to_pass"] if inst else None,
               pass_to_pass=inst["pass_to_pass"] if inst else None,
               infra_failure=bool(inst and inst["infra_failure"]),
               diagnosis=(inst or {}).get("diagnosis"))
    return out


def main():
    parser = argparse.ArgumentParser(description="Gold 扩样驱动器（单命令全链）")
    parser.add_argument("--instances", default="",
                        help="逗号分隔实例 id；与 --all-from 二选一")
    parser.add_argument("--all-from", dest="all_from", default="",
                        help="gold 预测 jsonl，取其全部实例")
    parser.add_argument("--predictions", required=True,
                        help="gold 预测 jsonl（含 model_patch）")
    parser.add_argument("--map", default=str(DEFAULT_MAP),
                        help="实例→镜像映射 CSV")
    parser.add_argument("--out", required=True, help="产物目录")
    parser.add_argument("--mirror", default="docker.1ms.run")
    parser.add_argument("--segments", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=12)
    parser.add_argument("--eval-timeout", dest="eval_timeout", type=int,
                        default=1800)
    parser.add_argument("--cwd", default=str(ROOT / "datasets" / "swe-out" /
                                            "harness"),
                        help="harness 工作目录（汇总与日志落此处，勿用仓库根）")
    parser.add_argument("--run-prefix", dest="run_prefix", default="gold")
    parser.add_argument("--force", action="store_true",
                        help="镜像已存在也重拉（缺省跳过下载直接评测）")
    argv = parser.parse_args()

    if not argv.all_from and not argv.instances:
        return _param_error("--instances 与 --all-from 至少给一个")
    map_path = Path(argv.map)
    if not map_path.is_file():
        return _param_error("映射 CSV 不存在: %s" % map_path)
    pred_path = Path(argv.predictions)
    if not pred_path.is_file():
        return _param_error("预测文件不存在: %s" % pred_path)
    try:
        mapping = load_map(map_path)
        preds = load_predictions(pred_path)
    except (OSError, ValueError, csv.Error) as exc:
        return _param_error("输入解析失败: %s" % exc)
    if argv.all_from:
        wanted = list(preds)
    else:
        wanted = [i.strip() for i in argv.instances.split(",") if i.strip()]
    missing_map = [i for i in wanted if i not in mapping]
    missing_pred = [i for i in wanted if i not in preds]
    if missing_map or missing_pred:
        return _param_error("缺映射: %s；缺预测: %s" % (missing_map, missing_pred))

    Path(argv.out).mkdir(parents=True, exist_ok=True)
    # harness 工作目录必须存在：官方 harness 把汇总报告写进 CWD
    # （默认落仓库根会污染工作树——round-7/round-18 同坑两次复发）
    Path(argv.cwd).mkdir(parents=True, exist_ok=True)
    ledger_path = Path(argv.out) / "gold-sample-ledger.json"
    ledger = {"results": []}
    if ledger_path.is_file() and not argv.force:
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ledger = {"results": []}
    done_ids = {r["instance_id"] for r in ledger["results"]
                if r.get("state") == "DONE"}
    for iid in wanted:
        if iid in done_ids:
            continue  # 断点续跑：已完成实例跳过
        result = process_instance(iid, mapping[iid], preds[iid], argv)
        ledger["results"] = [r for r in ledger["results"]
                             if r["instance_id"] != iid] + [result]
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2),
                               encoding="utf-8", newline="\n")
    resolved = sum(1 for r in ledger["results"] if r.get("resolved"))
    done = sum(1 for r in ledger["results"] if r.get("state") == "DONE")
    failed = [r["instance_id"] for r in ledger["results"]
              if r.get("state") not in ("DONE",)]
    _emit({"ok": not failed, "total": len(ledger["results"]), "done": done,
           "resolved": resolved, "failed": failed,
           "ledger": str(ledger_path),
           "results": ledger["results"]})
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
