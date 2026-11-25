#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEARCH/REPLACE 编辑格式（agent 层；Aider 验证过的格式）。

块格式（一或多块）：
    <相对路径>
    <<<<<<< SEARCH
    精确原文行
    =======
    替换行
    >>>>>>> REPLACE

契约：SEARCH 必须在目标文件中恰好出现一次（0 次或多于一次都拒绝并报错，
不给 LLM 模糊落点）；替换只动命中片段，其余内容逐字保留。
新建文件：SEARCH 为空且目标文件不存在时创建（round-46，真实评测遇到
「任务要求新模块」而编辑面只能改旧文件）；空 SEARCH + 已存在文件仍拒绝，
避免把「追加」误当「新建」。

用法示例：
    py agent/edit_formats.py --apply --base-dir <目录> --file blocks.txt

退出码：0=成功；1=存在无法应用的块；2=输入错误。
"""
import argparse
import json
import sys
from pathlib import Path

BEGIN = "<<<<<<< SEARCH"
SEP = "======="
END = ">>>>>>> REPLACE"


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def parse_blocks(text):
    """解析编辑块文本 → [{path, search, replace}]；格式错误抛 ValueError。"""
    blocks = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() != BEGIN:
            i += 1
            continue
        if i == 0 or not lines[i - 1].strip():
            raise ValueError("SEARCH 块第 %d 行缺少前置路径行" % (i + 1))
        path = lines[i - 1].strip()
        i += 1
        search, replace = [], []
        target = search
        while i < len(lines) and lines[i].strip() != END:
            if lines[i].strip() == SEP:
                target = replace
            else:
                target.append(lines[i])
            i += 1
        if i >= len(lines):
            raise ValueError("SEARCH 块缺少 %s 结尾" % END)
        i += 1
        blocks.append({"path": path,
                       "search": "\n".join(search),
                       "replace": "\n".join(replace)})
    return blocks


def apply_edits(base_dir, blocks):
    """按序应用编辑块；返回 {applied, errors}（单块失败不影响其他文件）。

    新建文件：SEARCH 为空 + 目标不存在 → 以 replace 为全文创建；目标已存在
    时空 SEARCH 一律拒绝（避免把追加误当新建）。
    """
    base = Path(base_dir)
    return apply_edits_io(
        blocks,
        lambda rel: (base / rel).read_text(encoding="utf-8", errors="replace"),
        lambda rel: (base / rel).is_file(),
        lambda rel, text: _write_local(base, rel, text))


def _write_local(base, rel, text):
    dest = base / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8", newline="\n")


def apply_edits_io(blocks, read_text, exists, write_text):
    """编辑块的 IO 无关实现（供工作区三档复用：本地 / 容器 / 远程）。

    语义与 apply_edits 完全一致：SEARCH 唯一命中、空 SEARCH 仅新建、
    单块失败不影响其他块、同文件多块按序累积。调用方只需提供
    read_text(rel) / exists(rel) / write_text(rel, text) 三个钩子。
    """
    applied, errors = [], []
    contents = {}
    created = set()
    for block in blocks:
        rel = str(block.get("path", "")).replace("\\", "/")
        if not rel or ".." in rel.split("/") or Path(rel).is_absolute() \
                or (len(rel) > 1 and rel[1] == ":"):
            errors.append({"path": rel, "error": "路径非法"})
            continue
        needle = str(block.get("search", ""))
        if rel not in contents:
            if exists(rel):
                contents[rel] = read_text(rel)
            elif not needle:
                contents[rel] = ""
                created.add(rel)
            else:
                errors.append({"path": rel, "error": "文件不存在"})
                continue
        text = contents[rel]
        if not needle:
            if rel in created and text == "":
                body = str(block.get("replace", ""))
                # 新文件补尾换行（块格式不带行尾，POSIX 文本应收在换行上）
                if body and not body.endswith("\n"):
                    body += "\n"
                contents[rel] = body
                applied.append({"path": rel, "created": True})
                continue
            errors.append({"path": rel, "error": "SEARCH 为空"})
            continue
        count = text.count(needle)
        if count == 0:
            errors.append({"path": rel, "error": "SEARCH 未命中"})
            continue
        if count > 1:
            errors.append({"path": rel, "error": "SEARCH 命中 %d 处（需唯一）" % count})
            continue
        contents[rel] = text.replace(needle, str(block.get("replace", "")), 1)
        applied.append({"path": rel})
    for rel, text in contents.items():
        write_text(rel, text)
    return {"applied": applied, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="SEARCH/REPLACE 编辑格式")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--base-dir", dest="base_dir", required=True)
    parser.add_argument("--file", help="编辑块文本文件")
    argv = parser.parse_args()
    if not argv.apply or not argv.file:
        _emit({"ok": False, "error": "用法：--apply --base-dir <目录> --file <块文件>"})
        return 2
    src = Path(argv.file)
    if not src.is_file():
        _emit({"ok": False, "error": "块文件不存在: %s" % src})
        return 2
    try:
        blocks = parse_blocks(src.read_text(encoding="utf-8", errors="replace"))
    except ValueError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    if not blocks:
        _emit({"ok": False, "error": "未解析到任何编辑块"})
        return 2
    result = apply_edits(argv.base_dir, blocks)
    _emit({"ok": not result["errors"], "blocks": len(blocks), **result})
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
