#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""迭代官台账：收集本轮踩坑事件与产物痕迹，去重并入坑台账（只读扫描）。

事件来源两类：
1. --events 手工事件 JSON（数组或含 events 键）：{category, description,
   root_cause?, countermeasure?, source?, type?}——智能体在轮内随时记录的坑。
   type 是「这条记录是什么」：feature / test / doc / confirmation 属完成或
   确认事项，**不入册**（round-37..42 的完成事件就是这样被旧入册器收成
   22 条 open 坑的）；缺 type 或缺省以外的类型（correction / fix / pitfall
   等）一律按坑处理——宁可多收一条待核的坑，不可静默漏收一条真坑；
2. --scan 产物痕迹（只读扫描给定路径）：approval.json verdict=REJECTED
   （补丁返工）、apply-log.json status=ROLLED_BACK（回滚）、
   apply-log-history.jsonl 及归档 apply-log-history.archived.jsonl 里每一条
   ROLLED_BACK（回滚；单文件是「最新状态」会被
   重试盖掉，jsonl 才是「发生过几次回滚」的凭据，与上一条同描述时按 id 自然去重；
   活跃 jsonl 只留最近 50 次，窗口外的回滚由归档接住，两个文件都要采）、
   fix-manifest.json skipped 非空（机械修复转人工）、experience.json
   entries（误报回流）。

台账 pitfalls.json 按 id（category+description 摘要）去重合并，保留历史
状态；--close <id> 结案，且**必须带 --close-note <可验证验收口径>**——
没有口径的结案不可审计，等于把灯灭掉而不是把坑填了（BASELINE 早就写了这条要求，
本轮把它落进脚本，不再只停在文档里）。开局探针与下一轮工作以此台账为先验。

--archive <id> 是「这条从来不是坑」的更正（只对 open 生效），**必须带
--archive-note <为什么不是坑>**；它与 --close 语义不可互换：closed 是「真坑已
填」的证据，archived 是「入册错了」的更正，两者都留痕不删除。归档前请先修
入册根因，否则下轮同一批事件会再被收进来。

用法示例：
    py retro-ledger.py --events round-events.json --scan runs --out retro
    py retro-ledger.py --out retro --close <坑ID> --close-note "三查闸门 + 4 例反向验证测试全绿"
    py retro-ledger.py --out retro --archive <坑ID> --archive-note "feature 完成事件误收，非坑"

退出码：0=成功；2=输入错误（含：只给 --close 没给 --close-note；只给 --archive
没给 --archive-note；--close 与 --archive 同时给；归档非 open 条目；结案已归档
条目；口径里的 unittest 命令写成跑不起来的 `-m unittest tests.test_x` 形态）。
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

CATEGORY_WEIGHT = {"回滚": 3, "补丁返工": 2, "误报": 2, "行为回归": 3,
                   "转人工": 1, "手工": 1}

# 非坑事件类型（规则先于数字，round-44）：事件文件的 type 描述「这条记录是
# 什么」。feature/test/doc/confirmation 是完成或确认事项，不入册；缺 type 的
# 历史事件沿用旧行为按坑处理（向后兼容），correction / fix / pitfall 等其余
# 类型也按坑处理——宁可多收一条待核的坑，不可静默漏收一条真坑。
NON_PITFALL_EVENT_TYPES = {"feature", "test", "doc", "confirmation"}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _pitfall_id(category, description):
    raw = "%s|%s" % (category, description)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _entry(category, description, root_cause="", countermeasure="",
           source=""):
    return {"id": _pitfall_id(category, description),
            "category": category, "description": description[:400],
            "root_cause": str(root_cause)[:400],
            "countermeasure": str(countermeasure)[:400],
            "source": str(source)[:200], "status": "open"}


def _collect_events(path, errors):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append("事件 JSON 非法(%s): %s" % (path, exc))
        return [], []
    items = data.get("events") if isinstance(data, dict) else data
    if not isinstance(items, list):
        errors.append("事件需为数组或含 events 键: %s" % path)
        return [], []
    out, skipped = [], []
    for item in items:
        if not isinstance(item, dict) or not item.get("description"):
            continue
        etype = str(item.get("type", "")).strip().lower()
        if etype in NON_PITFALL_EVENT_TYPES:
            skipped.append({"type": etype,
                            "description": str(item.get("description"))[:120]})
            continue
        out.append(_entry(str(item.get("category", "手工")),
                          str(item.get("description")),
                          item.get("root_cause", ""),
                          item.get("countermeasure", ""),
                          item.get("source", path)))
    return out, skipped


def _collect_artifacts(root, errors):
    """只读扫描产物痕迹。"""
    out = []
    root = Path(root)
    if not root.exists():
        errors.append("扫描路径不存在: %s" % root)
        return out
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        try:
            if name == "approval.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("verdict") == "REJECTED":
                    out.append(_entry(
                        "补丁返工", "闸 2 拒绝: %s" % "; ".join(
                            data.get("reasons", [])[:3]),
                        countermeasure="按 reasons 返工后重新送审",
                        source=str(path)))
            elif name == "apply-log.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("status") == "ROLLED_BACK":
                    out.append(_entry(
                        "回滚", "落盘回滚: %s" % str(data.get("error", ""))[:200],
                        countermeasure="缩小补丁粒度或补测试后重试",
                        source=str(path)))
            elif name == "apply-log-history.jsonl" or (
                    name.startswith("apply-log-history.")
                    and name.endswith(".jsonl")):
                # 最新态 apply-log.json 会被同目录的下一次落盘盖掉（重试是常态），
                # 历史 jsonl 才是「这一次确实回滚过」的凭据；与上一条同 description
                # 时按 id 自然去重，不会重复记账。
                # round-31 轮转口径：活跃文件只留最近 50 次，溢出压进
                # apply-log-history.archived.jsonl（按签名合并，签名键与本处 id 键同源），
                # 所以两个文件都要采——只采活跃文件等于「窗口外的回滚自动销账」。
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if entry.get("status") != "ROLLED_BACK":
                        continue
                    out.append(_entry(
                        "回滚", "落盘回滚: %s" % str(entry.get("error", ""))[:200],
                        countermeasure="缩小补丁粒度或补测试后重试",
                        source=str(path)))
            elif name == "fix-manifest.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                skipped = data.get("skipped") or []
                if skipped:
                    out.append(_entry(
                        "转人工", "机械修复跳过 %d 处: %s"
                        % (len(skipped), sorted({s.get("rule_id", "-")
                                                 for s in skipped})[:5]),
                        countermeasure="确认策略盲区或扩展白名单",
                        source=str(path)))
            elif name == "experience.json":
                data = json.loads(path.read_text(encoding="utf-8"))
                entries = data.get("entries") or []
                if entries:
                    out.append(_entry(
                        "误报", "经验库累计 %d 条误报模式" % len(entries),
                        countermeasure="补充阴性样例并核对扫描器",
                        source=str(path)))
        except (OSError, ValueError) as exc:
            errors.append("产物解析失败(%s): %s" % (path, exc))
    return out


def _closure_command_is_runnable(note):
    """结案口径里写的 unittest 命令必须能原样跑（round-30 实踩）。

    反例：`-m unittest tests.test_repair -k foo` —— tests/ 下的模块互相 import
    兄弟模块（test_repair.py 顶部 `import test_scripts`），按模块名加载时不在
    sys.path 上，必然 ModuleNotFoundError，跑完还是 `Ran 0 tests / FAILED` 这种
    「看起来像没这个测试」的形状。台账里的验收口径如果跑不起来就不是口径。

    只约束「提到了 -m unittest 就必须是 discover -s tests 形态」，其余口径（人工
    复核、命令行手测）不受影响；缺 discover 或缺 `-s tests` 都判不可跑。
    """
    text = note or ""
    if "-m unittest" not in text:
        return True
    return "discover" in text and "-s tests" in text


def main():
    parser = argparse.ArgumentParser(description="迭代官台账（坑收集与去重）")
    parser.add_argument("--out", required=True, help="复盘目录（pitfalls.json）")
    parser.add_argument("--events", default="", help="手工事件 JSON 文件")
    parser.add_argument("--scan", action="append", default=[],
                        help="产物痕迹扫描路径，可多次")
    parser.add_argument("--close", default="", help="结案的坑 ID")
    parser.add_argument("--close-note", default="",
                        help="结案的可验证验收口径（与 --close 同时必填）")
    parser.add_argument("--archive", default="",
                        help="归档的「非坑」条目 ID（入册错误，只对 open 生效）")
    parser.add_argument("--archive-note", default="",
                        help="归档理由：为什么这条从来不是坑（与 --archive 同时必填）")
    argv = parser.parse_args()
    if argv.close and argv.archive:
        _emit({"ok": False,
               "error": "--close 与 --archive 互斥：closed 是「真坑已填」，"
                        "archived 是「入册错了」，同一轮只能二选一"})
        return 2
    if argv.archive and not argv.archive_note.strip():
        _emit({"ok": False,
               "error": "归档必须带理由：--archive %s 需要同时给 --archive-note "
                        "「为什么这条从来不是坑」；无理由归档与灭灯无异。"
                        % argv.archive})
        return 2
    if argv.close and not argv.close_note.strip():
        _emit({"ok": False,
               "error": "结案必须带可验证验收口径：--close %s 需要同时给 --close-note "
                        "「怎么验、验到什么程度才算填了坑」。不带口径的结案不可审计。"
                        % argv.close})
        return 2
    if argv.close and not _closure_command_is_runnable(argv.close_note):
        _emit({"ok": False,
               "error": "结案口径里的 unittest 命令跑不起来：%s。tests/ 下的模块互相 "
                        "import 兄弟模块（test_repair 里 `import test_scripts`），"
                        "`-m unittest tests.test_x` 这种按模块名的写法必然 "
                        "ModuleNotFoundError——写进台账的验收命令必须能原样复制执行，"
                        "正确形态是 "
                        "`-m unittest discover -s tests -p \"test_x.py\" -k <test_name>`"
                        % argv.close_note.strip()[:120]})
        return 2
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "pitfalls.json"
    errors = []
    entries = []
    skipped_events = []
    if argv.events:
        events_path = Path(argv.events)
        if not events_path.is_file():
            _emit({"ok": False, "error": "事件文件不存在: %s" % events_path})
            return 2
        collected, skipped_events = _collect_events(events_path, errors)
        entries.extend(collected)
    for scan_root in argv.scan:
        entries.extend(_collect_artifacts(scan_root, errors))

    existing = {}
    if ledger_path.is_file():
        try:
            old = json.loads(ledger_path.read_text(encoding="utf-8"))
            for item in old.get("pitfalls", []):
                existing[item.get("id", "")] = item
        except (OSError, ValueError):
            existing = {}
    new_count = 0
    for entry in entries:
        if entry["id"] not in existing:
            existing[entry["id"]] = entry
            new_count += 1
        else:
            merged = existing[entry["id"]]
            for key in ("root_cause", "countermeasure"):
                if not merged.get(key) and entry.get(key):
                    merged[key] = entry[key]
    if argv.archive:
        target = existing.get(argv.archive)
        if target is None:
            _emit({"ok": False, "error": "坑 ID 不存在: %s" % argv.archive})
            return 2
        if target.get("status") != "open":
            _emit({"ok": False,
                   "error": "只有 open 条目可归档（当前 %s）：closed 是真坑的结案"
                            "记录、archived 是「入册错了」的更正，两者不可互换"
                            % target.get("status")})
            return 2
        target["status"] = "archived"
        target["archive_note"] = argv.archive_note.strip()
        target["archived_at"] = datetime.date.today().isoformat()
    if argv.close:
        target = existing.get(argv.close)
        if target is None:
            _emit({"ok": False, "error": "坑 ID 不存在: %s" % argv.close})
            return 2
        if target.get("status") == "archived":
            _emit({"ok": False,
                   "error": "已归档条目不可结案（非坑没有「填坑」一说）：%s"
                            % argv.close})
            return 2
        target["status"] = "closed"
        target["closure_note"] = argv.close_note.strip()
    pitfalls = sorted(existing.values(),
                      key=lambda e: (-CATEGORY_WEIGHT.get(e["category"], 0),
                                     e["category"], e["id"]))
    ledger_path.write_text(
        json.dumps({"pitfalls": pitfalls}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    open_count = sum(1 for e in pitfalls if e.get("status") == "open")
    archived_count = sum(1 for e in pitfalls if e.get("status") == "archived")
    _emit({"ok": True, "ledger": str(ledger_path), "total": len(pitfalls),
           "open": open_count, "archived": archived_count, "new": new_count,
           "closed": argv.close or None,
           "closure_note": target.get("closure_note") if argv.close else None,
           "archived_id": argv.archive or None,
           "archive_note": target.get("archive_note") if argv.archive else None,
           "skipped_events": len(skipped_events),
           "skipped": skipped_events[:10], "errors": errors})
    return 0


if __name__ == "__main__":
    sys.exit(main())
