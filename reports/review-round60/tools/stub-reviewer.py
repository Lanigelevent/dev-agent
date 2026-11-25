#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评审器协议桩：演示 --review-cmd 扩展点（stdout 只输出 findings JSON）。

读取环境变量 CRA_REVIEW_PATCH（补丁文件）与 CRA_REVIEW_FILES（逗号分隔
文件清单），固定对 pkg/agg.py:5 报一条「== None」发现——验证 --review-cmd
第三方评审器能被接入、其发现会计入自评/他评差异（该样例自评无对应发现，
差异率因此为 1.0，按阈值转人工）。

用法：py stub-reviewer.py
退出码：0=产出报告；2=环境缺 CRA_REVIEW_PATCH。
"""
import json
import os
import sys

def main():
    patch = os.environ.get("CRA_REVIEW_PATCH") or ""
    files = os.environ.get("CRA_REVIEW_FILES") or ""
    if not patch:
        print(json.dumps({"error": "CRA_REVIEW_PATCH 缺失"}))
        return 2
    findings = []
    if "pkg/agg.py" in files:
        with open(patch, encoding="utf-8", errors="replace") as fh:
            if "== None" in fh.read():
                findings.append({"file": "pkg/agg.py", "line": 5,
                                 "rule": "stub:eq-none", "severity": "medium",
                                 "message": "comparison to None via =="})
    print(json.dumps({"findings": findings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
