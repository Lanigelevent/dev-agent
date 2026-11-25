#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""engines/artifact_names.py — 引擎补丁产物的**唯一命名**（round-30 同类排查）。

缺陷形状（与 round-29 的「轮号按文件数自增盖掉历史轮报」同源）：三个引擎都拿
`Path(rel).name` 当补丁名的键——
    ruff_adapter.py     ruff-<basename>.patch
    libcst_adapter.py   patch-<basename>.diff
    testgen.py          testgen-<basename>.patch
于是 `services/util.py` 与 `tasks/util.py` 两路修复落进同一个 `--out` 目录时，
**后写者原地吃掉前者的补丁**，而 fix-manifest 与批准书里的 sha256 已经和落盘内容
不再对应：批准的是 A 的补丁，落盘的是 B 的补丁。这不是「重跑刷新同一份结果」
的幂等覆盖，是跨对象撞名丢产物。

口径：键必须是**整条相对路径**，不是 basename。
    `<prefix>-<basename>-<sha256(rel)[:8]><suffix>`
basename 保留是为了人眼可读，哈希后缀保证不同目录同名不撞；文件名只做 ASCII
清洗（与「生成补丁内容/注释纯 ASCII」同一条纪律），非 ASCII 字符逐字节换成 `_`。
同一 rel 永远得到同一个名字 → 重跑仍幂等；不同 rel 永远不同名 → 不再互相吃掉。
"""
import hashlib
import re

_NON_ASCII_SAFE = re.compile(r"[^A-Za-z0-9._+\-]+")


def normalize_rel(rel):
    """反斜杠归一为正斜杠——同一模块在不同写法下必须是同一个键。"""
    return str(rel).replace("\\", "/")


def patch_artifact_name(prefix, rel, suffix=".patch"):
    """按相对路径全键生成补丁产物文件名（唯一且可重放）。"""
    key = normalize_rel(rel)
    basename = _NON_ASCII_SAFE.sub("_", key.rsplit("/", 1)[-1]) or "artifact"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return "%s-%s-%s%s" % (prefix, basename, digest, suffix)


def is_unique(names):
    """给测试用的自查：一批名字有没有内部重复。"""
    return len(set(names)) == len(names)
