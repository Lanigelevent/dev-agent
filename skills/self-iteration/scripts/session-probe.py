#!/usr/bin/env python3
"""开局探针：并行跑 doc-drift / perspective-scan 自检 / dead-code-scan 并汇总分诊。

用途:
    主流程步骤 0。退出码 0=全绿不做事；1=有信号（按 triage 处理）；2=检查器故障先修。

用法:
    python session-probe.py --root /path/dev-agent

退出码:
    0 = 三个探针全绿
    1 = 有信号（auto_fixable/needs_work 非空）
    2 = 有检查器自身故障（needs_human 或退出码 >=2）
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SELF = Path(__file__).resolve().parent
DOC_DRIFT = SELF / "doc-drift.py"
PERSPECTIVE = SELF / "perspective-scan.py"
DEAD_CODE = SELF / "dead-code-scan.py"


def _run_probe(cmd):
    """纯参数列表执行探针子进程，shell 恒为 False。"""
    if not all(isinstance(c, str) for c in cmd):
        raise TypeError("命令必须是字符串参数列表")
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None  # 探针输出不是 JSON 时按不可解析处理
    return {"cmd": cmd[1], "exit": p.returncode, "json": data,
            "stderr": p.stderr.strip()[-300:]}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def triage(probes):
    auto, work, human = [], [], []
    for probe in probes:
        name = Path(probe["cmd"]).name
        if probe["exit"] >= 2 or probe["json"] is None:
            human.append({"probe": name, "why": "检查器故障或输出不可解析",
                          "stderr": probe["stderr"]})
            continue
        if name == "dead-code-scan.py" and probe["exit"] == 1:
            auto.append({"probe": name, "count": len(probe["json"].get("findings", [])),
                         "why": "未用 import/死形参/死开关可机械清理"})
        if name == "doc-drift.py" and probe["exit"] == 1:
            failed = probe["json"].get("failed", [])
            auto_ids = [q for q in failed if q in (1, 3, 11)]
            work_ids = [q for q in failed if q not in (1, 3, 11)]
            if auto_ids:
                auto.append({"probe": name, "questions": auto_ids,
                             "why": "孤儿引用/死代码可机械修"})
            if work_ids:
                work.append({"probe": name, "questions": work_ids,
                             "why": "文档漂移需人工核对基线"})
        if name == "perspective-scan.py" and probe["exit"] == 1:
            human.append({"probe": name, "why": "反向验证自检失败，检查器本身不可信"})
    return {"auto_fixable": auto, "needs_work": work, "needs_human": human}


def main():
    parser = argparse.ArgumentParser(description="开局探针")
    parser.add_argument("--root", required=True, help="项目根目录")
    argv = parser.parse_args()
    root = Path(argv.root)
    if not root.is_dir():
        _emit({"ok": False, "error": "root 不存在: %s" % root})
        return 2
    jobs = [
        [sys.executable, str(DOC_DRIFT), "--root", str(root)],
        [sys.executable, str(PERSPECTIVE), "--self-check"],
        [sys.executable, str(DEAD_CODE), "--root", str(root)],
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        probes = list(pool.map(_run_probe, jobs))
    t = triage(probes)
    all_green = all(p["exit"] == 0 for p in probes)
    broken = bool(t["needs_human"])
    _emit({
        "ok": not broken,
        "all_green": all_green,
        "probes": probes,
        "triage": t,
    })
    if broken:
        return 2
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
