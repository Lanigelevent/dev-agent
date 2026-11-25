# -*- coding: utf-8 -*-
"""sitecustomize：老仓库 Python 版本兼容垫片（被 agent/legacy_compat.py 注入）。

作用范围：只影响通过 agent/legacy_compat.py 启动的进程（PYTHONPATH 注入），
不修改全局解释器，也不改被审仓库。

补回的内容（Python 3.10+ 移除的老别名）：
- collections.Mapping / MutableMapping / Sequence / ... → collections.abc 对应物
- inspect.getargspec（3.11 移除）→ inspect.getfullargspec
- inspect.getargspec 相关老 API 的兼容别名（getcallargs 等保持原样）
"""
import collections
import collections.abc
import inspect

for _name in ("Mapping", "MutableMapping", "Sequence", "MutableSequence",
              "Iterable", "Iterator", "Callable", "Hashable", "Set",
              "MutableSet", "Container", "Sized"):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))

if not hasattr(inspect, "getargspec"):
    inspect.getargspec = inspect.getfullargspec
