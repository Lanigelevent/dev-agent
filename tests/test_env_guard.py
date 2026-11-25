# -*- coding: utf-8 -*-
"""tests/test_env_guard.py — 编码环境哨兵（round-118 B1-02，离线）。

坑 8cfbcaf7d227 对策锚点：宿主向子进程注入 PYTHONUTF8/PYTHONIOENCODING 会
改变 Python 解码基线（cp936 仓库契约建立在无注入环境上，历史两连红）。
本文件模块级检测非默认组合时向 stderr 发警告，默认组合零输出；一条用例
把判定逻辑钉住。判定口径与 round-65 对策一致：空串置空（PYTHONUTF8=
PYTHONIOENCODING=）视为默认，非空值视为非默认。
"""
import os
import sys
import unittest

_ENV_KEYS = ("PYTHONUTF8", "PYTHONIOENCODING")


def _non_default_reasons(env):
    """返回 env 中非默认编码组合的原因列表；默认组合（两键缺省或空串）为空。"""
    reasons = []
    for key in _ENV_KEYS:
        value = env.get(key, "")
        if value:
            reasons.append("%s=%s" % (key, value))
    return reasons


def _emit_guard_warnings(env=None):
    """检测 env（缺省读 os.environ）并逐条向 stderr 发警告；返回原因列表。"""
    if env is None:
        env = os.environ
    reasons = _non_default_reasons(env)
    for reason in reasons:
        print("[env-guard] 检测到非默认编码组合 %s（坑 8cfbcaf7d227："
              "subprocess text=True 会按 UTF-8 严格解码 Windows 工具的 "
              "ANSI 输出；套件对策=置空前缀 PYTHONUTF8= PYTHONIOENCODING=，"
              "详见 retro/pitfalls.json）" % reason, file=sys.stderr)
    return reasons


_emit_guard_warnings()


class TestEnvGuard(unittest.TestCase):
    def test_non_default_env_detection(self):
        """默认/置空组合零警告；任一键非空即命中（round-65 置空口径）。"""
        self.assertEqual(_non_default_reasons({}), [])
        self.assertEqual(_non_default_reasons(
            {"PYTHONUTF8": "", "PYTHONIOENCODING": ""}), [],
            "空串置空应与缺省同口径")
        self.assertEqual(_non_default_reasons({"PYTHONUTF8": "1"}),
                         ["PYTHONUTF8=1"])
        self.assertEqual(_non_default_reasons(
            {"PYTHONUTF8": "0", "PYTHONIOENCODING": "utf-8"}),
            ["PYTHONUTF8=0", "PYTHONIOENCODING=utf-8"])
