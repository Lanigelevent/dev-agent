#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务态持久化（--resume 依赖）。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import json
import time


class TaskState:
    """任务态持久化（--resume 用）。"""

    def __init__(self, out_dir):
        self.path = Path(out_dir) / "task-meta.json"
        self.data = {"repo": "", "task": "", "round": 0, "history": [],
                     "edits_applied": 0, "tests": "skip",
                     "blocks": [], "attempted": [], "allow_probe": False,
                     "probe_docker": "", "rank": "refs", "elapsed_sec": 0.0}
        self._session_mark = None

    def load(self):
        if self.path.is_file():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        return self

    def begin_session(self):
        """开始本进程的计时段（elapsed_sec 跨 --resume 累加，不退化为单次墙钟）。"""
        self._session_mark = time.monotonic()

    def elapsed_now(self):
        total = float(self.data.get("elapsed_sec") or 0.0)
        if self._session_mark is not None:
            total += time.monotonic() - self._session_mark
        return round(total, 3)

    def save(self):
        if self._session_mark is not None:
            now = time.monotonic()
            self.data["elapsed_sec"] = round(
                float(self.data.get("elapsed_sec") or 0.0)
                + (now - self._session_mark), 3)
            self._session_mark = now
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False,
                                        indent=2),
                             encoding="utf-8", newline="\n")
