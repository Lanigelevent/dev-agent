#!/usr/bin/env python3
"""findings 校验：七要素齐全 + 定位格式/枚举值/指令式文本/完备性核对四项。

用途:
    主流程步骤 4。子代理提交结果先过本校验，缺项即打回；
    空列表若无核对说明同样打回。
    输入可以是文件，也可以是 stdin（`-`）；两条路都按 UTF-8 读，不跟宿主
    ANSI locale（Windows 中文桌面默认 cp936）走。

用法:
    python findings-check.py raw.json --dimensions "正确性与逻辑缺陷、测试覆盖"

退出码:
    0 = 全部通过
    1 = 有发现被拒（缺要素/格式/枚举/注入/维度不符/空列表无说明）
    2 = 参数错误（文件不存在、JSON 非法、缺 --dimensions）
"""
import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ["loc", "desc", "evidence", "severity", "confidence", "cause", "fix"]
ENUMS = {"severity": {"高", "中", "低"}, "confidence": {"高", "中", "低"}}
LOC_RE = re.compile(r".+:\d+$")
INJECTION_RE = re.compile(
    r"忽略(?:之前|以上|前面|上文)(?:的)?(?:指令|说明|提示|要求)|ignore\s+(?:previous|all|prior|above)"
    r"|disregard\s+(?:all|previous)|system\s+prompt|系统提示词",
    re.I,
)


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def check(items, dimensions):
    accepted, rejected, detail = 0, 0, []
    for i, f in enumerate(items):
        problems = []
        if not isinstance(f, dict):
            problems.append("发现不是对象")
        else:
            for key in REQUIRED_FIELDS:
                if key not in f or f.get(key) in (None, ""):
                    problems.append("缺要素:%s" % key)
            loc = str(f.get("loc", ""))
            if loc and not LOC_RE.match(loc):
                problems.append("定位格式须为 文件:行号")
            for key, allowed in ENUMS.items():
                if f.get(key) is not None and f.get(key) != "" and f.get(key) not in allowed:
                    problems.append("枚举越界:%s=%s" % (key, f.get(key)))
            blob = " ".join(str(f.get(k, "")) for k in ("desc", "evidence", "cause", "fix"))
            if INJECTION_RE.search(blob):
                problems.append("检测到指令式文本（按被分析数据处理，不予采纳）")
            dim = f.get("dimension")
            if dim and dim not in dimensions:
                problems.append("维度未在派发清单: %s" % dim)
        ok = not problems
        detail.append({"index": i, "ok": ok, "problems": problems})
        if ok:
            accepted += 1
        else:
            rejected += 1
    if not items and isinstance(items, list):
        rejected += 1
        detail.append({"index": "list", "ok": False, "problems": ["空列表缺少核对说明"]})
    return accepted, rejected, detail


def main():
    parser = argparse.ArgumentParser(description="findings 校验")
    parser.add_argument("raw", help="子代理原始输出 JSON 文件，或 - 读 stdin")
    parser.add_argument("--dimensions", required=True, help="派发维度清单，用 、 或 , 分隔")
    argv = parser.parse_args()
    if argv.raw == "-":
        try:
            # stdin 必须显式按 UTF-8 读：Windows 宿主 ANSI locale 是 cp936 时
            # sys.stdin 默认用 GBK+surrogateescape 解码，上游以 ensure_ascii=False
            # 送来的中文字节会被静默损坏成代理对——本脚本随后打印代理对时炸
            # UnicodeEncodeError，退出码 1 长得像「校验没过」，编排器就把整批发现
            # 丢了（跑成功、产出为空，是最难发现的一种失败）。
            if hasattr(sys.stdin, "reconfigure"):
                sys.stdin.reconfigure(encoding="utf-8")
            data = json.loads(sys.stdin.read())
        except ValueError as exc:
            _emit({"ok": False, "error": "stdin JSON 非法: %s" % exc})
            return 2
    else:
        p = Path(argv.raw)
        if not p.is_file():
            _emit({"ok": False, "error": "文件不存在: %s" % p})
            return 2
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _emit({"ok": False, "error": "JSON 非法: %s" % exc})
            return 2
    dimensions = [d for d in re.split(r"[、,]", argv.dimensions) if d.strip()]
    if isinstance(data, dict):
        items = data.get("findings", [])
        coverage_note = data.get("coverage_note")
    else:
        items = data
        coverage_note = None
    if not isinstance(items, list):
        _emit({"ok": False, "error": "findings 需为数组"})
        return 2
    accepted, rejected, detail = check(items, dimensions)
    if not items and coverage_note:
        rejected -= 1
        detail = [d for d in detail if d.get("index") != "list"]
    _emit(
        {
            "ok": rejected == 0,
            "accepted": accepted,
            "rejected": max(0, rejected),
            "items": detail,
            "dimensions": dimensions,
        }
    )
    return 0 if rejected == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
