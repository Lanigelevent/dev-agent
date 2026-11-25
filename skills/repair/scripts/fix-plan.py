#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复分诊：对 38 条硬规则的发现清单判定可修复性（只读，不写任何文件）。

38 条硬规则中仅 5 类缺陷可机械化修复（白名单见 fix-patch.py AUTO_RULES）：
Python 可变默认参数、空 except 吞异常、闭包延迟绑定、is 字面量/==None 误用、
yaml.load 无 Loader。凭据类一律 manual：补丁会复制明文，违反产物红线。

用法示例：
    py fix-plan.py --findings findings.json --repo <被审仓库>

输入 findings.json 为 deterministic-rules.py 的输出（含 findings 键）或其
findings 数组本身。相对路径按 --repo 解析。

退出码：0=成功；2=输入错误（findings 缺失/JSON 非法）。
"""
import argparse
import json
import sys
from pathlib import Path

# 与 fix-patch.py 的 AUTO_RULES 保持一致（成对维护，测试有双向断言）
FIXABLE_RULES = {
    "lang-mutable-default": "None 哨兵 + 函数体首行卫语句",
    "lang-empty-catch": "裸 except 收窄为 Exception；pass 体改为 stderr 记录",
    "lang-closure-late-bind": "循环变量以默认参数绑定进 lambda",
    "lang-is-literal-misuse": "==None 改 is None；is 字面量改 ==",
    "dang-yaml-load": "单参单行调用改 yaml.safe_load",
}

MANUAL_REASONS = {
    "cred": "凭据整改需改密钥管理方式，补丁会复制明文，违反产物红线",
    "dang": "语义级危险调用需人工重构，机械化改写易破坏行为",
    "lang": "需要跨行/跨语义的改写，超出机械修复范围",
}


def _reason_for(rule_id):
    head = rule_id.split("-")[0]
    return MANUAL_REASONS.get(head, "该规则无确定性修复策略")


_ENGINE_MATRICES = (("ruff:", "ruff-matrix.json", "ruff"),
                    ("libcst:", "libcst-matrix.json", "libcst"),
                    ("astgrep:", "astgrep-matrix.json", "astgrep"))

# 引擎→支持的文件后缀（astgrep 是多语言引擎，不限 .py）
_ENGINE_EXTS = {"ruff": (".py",), "libcst": (".py",),
                "astgrep": (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".py")}


def _engine_strategy(rule_id):
    """引擎能力矩阵分诊：<engine>:<code> 且矩阵标记可修复 → 引擎修复策略。

    返回 (策略描述, 引擎名)；未命中返回 ("", "")。
    """
    for prefix, matrix_name, engine in _ENGINE_MATRICES:
        if not rule_id.startswith(prefix):
            continue
        code = rule_id.split(":", 1)[1]
        matrix_path = (Path(__file__).resolve().parents[3]
                       / "engines" / matrix_name)
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "", ""
        if code in matrix.get("fixable_codes", []):
            return ("%s 引擎修复（矩阵标记可修复：%s；产物过五道闸）"
                    % (engine, matrix.get("version", "?")), engine)
        return "", ""
    return "", ""


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _load_findings(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("findings")
    if not isinstance(data, list):
        raise ValueError("findings 需为数组或含 findings 键")
    return data


def main():
    parser = argparse.ArgumentParser(description="修复分诊（只读）")
    parser.add_argument("--findings", required=True, help="发现清单 JSON 文件")
    parser.add_argument("--repo", default="", help="被审仓库根（相对路径解析基准）")
    argv = parser.parse_args()
    fp = Path(argv.findings)
    if not fp.is_file():
        _emit({"ok": False, "error": "findings 文件不存在: %s" % fp})
        return 2
    try:
        findings = _load_findings(fp)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "error": "findings JSON 非法: %s" % exc})
        return 2
    repo = Path(argv.repo) if argv.repo else None
    fixable, manual = [], []
    for item in findings:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id", ""))
        file_path = str(item.get("file", ""))
        if repo and file_path and not Path(file_path).is_absolute():
            file_path = str(repo / file_path)
        entry = {"rule_id": rule_id, "file": file_path,
                 "line": item.get("line"), "reason": item.get("reason", "")}
        strategy = _engine_strategy(rule_id)
        if strategy[0]:
            engine_name = strategy[1]
            allowed_exts = _ENGINE_EXTS.get(engine_name, (".py",))
            if file_path.lower().endswith(allowed_exts):
                entry["strategy"], entry["engine"] = strategy
                fixable.append(entry)
            else:
                entry["strategy"] = "manual"
                entry["blocker"] = ("engine=%s 仅支持 %s 文件"
                                     % (engine_name, ", ".join(allowed_exts)))
                manual.append(entry)
        elif rule_id in FIXABLE_RULES and file_path.lower().endswith(".py"):
            entry["strategy"] = FIXABLE_RULES[rule_id]
            fixable.append(entry)
        else:
            entry["strategy"] = "manual"
            entry["blocker"] = (_reason_for(rule_id)
                                if rule_id not in FIXABLE_RULES
                                else "仅支持 .py 文件")
            manual.append(entry)
    _emit({"ok": True, "total": len(findings),
           "fixable": fixable, "manual": manual,
           "summary": {"fixable_count": len(fixable), "manual_count": len(manual),
                       "fixable_rules": sorted(FIXABLE_RULES)}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
