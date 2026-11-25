#!/usr/bin/env python3
"""三维风险评分：规模/耦合/稳定性按固定权重加权，输出区域等级与整次综合。

用途:
    读取区域清单与整次变更统计，按 BASELINE.md 的评分契约打分并分档。
    stdin 与 --input 两条路都按 UTF-8 读，不跟宿主 ANSI locale 走。

用法:
    echo '{"regions":[...],"overall":{...}}' | python score.py
    python score.py --input regions.json

退出码:
    0 = 正常打分
    2 = 输入非法（JSON 解析失败、缺 regions/overall、字段类型错误）
"""
import argparse
import json
import sys

WEIGHTS = {"scale": 0.3, "coupling": 0.4, "stability": 0.3}
LINE_BANDS = (50, 200, 500, 1000)
COUNT_BANDS = (1, 3, 8, 15)
LEVELS = ("高", "中", "低")


def _band(value, bands):
    """按阈值升序查档，返回 1..5。"""
    for i, threshold in enumerate(bands, 1):
        if value <= threshold:
            return i
    return 5


def _int_field(obj, key, where):
    v = obj.get(key, 0)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError("%s.%s 必须是整数" % (where, key))
    return v


def score_region(region):
    lines = _int_field(region, "added", region.get("name", "?")) + _int_field(
        region, "deleted", region.get("name", "?")
    )
    files = _int_field(region, "files", region.get("name", "?"))
    modules = _int_field(region, "modules", region.get("name", "?"))
    callers = _int_field(region, "callers", region.get("name", "?"))
    scale = max(_band(lines, LINE_BANDS), _band(files, COUNT_BANDS))
    if modules > 1:
        scale = 5
    coupling = max(_band(modules, COUNT_BANDS), _band(callers, COUNT_BANDS))
    if region.get("high_impact"):
        coupling = min(5, coupling + 1)
    history3 = _int_field(region, "history_3m", region.get("name", "?"))
    history12 = _int_field(region, "history_12m", region.get("name", "?"))
    stability = max(_band(history3, COUNT_BANDS), _band(history12, COUNT_BANDS))
    if region.get("has_hotfix") or region.get("has_revert"):
        stability = min(5, stability + 1)
    if region.get("intent_deviation"):
        stability = min(5, stability + 1)
    total = round(
        WEIGHTS["scale"] * scale + WEIGHTS["coupling"] * coupling + WEIGHTS["stability"] * stability, 1
    )
    return {
        "scale": scale,
        "coupling": coupling,
        "stability": stability,
        "score": total,
        "level": _level(total),
    }


def _level(score):
    if score >= 4.0:
        return "高"
    if score >= 2.5:
        return "中"
    return "低"


def main():
    parser = argparse.ArgumentParser(description="三维风险评分")
    parser.add_argument("--input", help="输入 JSON 文件路径；缺省读 stdin")
    args = parser.parse_args()
    try:
        if args.input:
            raw = open(args.input, encoding="utf-8").read()
        else:
            # stdin 显式按 UTF-8 读（与 findings-check 同口径）：宿主 ANSI locale
            # 为 cp936 时，sys.stdin 默认 GBK+surrogateescape 会把中文字节解成
            # 代理对，JSON 解析随之失败并伪装成「输入非法」。
            if hasattr(sys.stdin, "reconfigure"):
                sys.stdin.reconfigure(encoding="utf-8")
            raw = sys.stdin.read()
        data = json.loads(raw)
    except OSError as exc:
        _emit({"ok": False, "error": "输入文件不可读: %s" % exc})
        return 2
    except (ValueError, TypeError) as exc:
        _emit({"ok": False, "error": "JSON 解析失败: %s" % exc})
        return 2
    if not isinstance(data, dict) or not isinstance(data.get("regions"), list):
        _emit({"ok": False, "error": "缺少 regions 数组"})
        return 2
    if not isinstance(data.get("overall"), dict):
        _emit({"ok": False, "error": "缺少 overall 对象"})
        return 2
    try:
        regions = []
        for i, r in enumerate(data["regions"]):
            if not isinstance(r, dict):
                raise ValueError("regions[%d] 不是对象" % i)
            item = {"name": str(r.get("name", "region-%d" % i))}
            item.update(score_region(r))
            regions.append(item)
        overall = {"name": "overall"}
        overall.update(score_region(data["overall"]))
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    out = {
        "ok": True,
        "weights": dict(WEIGHTS),
        "regions": regions,
        "overall": overall,
        "high_regions": [r["name"] for r in regions if r["level"] == "高"],
    }
    _emit(out)
    return 0


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
