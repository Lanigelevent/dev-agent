# -*- coding: utf-8 -*-
"""tests/test_workflow_injection.py — review.yml 表达式注入防线（round-118）。

背景：GitHub Actions 的 ${{ }} 在 run 块内直接插值时，事件数据（PR 标题/
评论正文/分支名）会被当作 shell 源解析——官方修法是一律经 env 中转。
review.yml 曾漏三处（REQUEST/PR_NUMBER 经 env 修复；base_ref 构造
REVIEW_RANGE 与 --repo 仓库名本轮一并修复）。本契约把该形态锁死：

1. review.yml 中任何含 ${{ }} 的行，必须为 env 赋值行（KEY: ${{ ... }}）
   或注释行——run 块内不允许出现表达式插值；
2. 反向验证：同一判定器对历史违规形态（run 行直接插值）必须报违规。
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "review.yml"

_ENV_ASSIGN = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*:\s*\$\{\{")


def _violations(text):
    """返回违规行列表：含 ${{ }} 且既非 env 赋值行也非注释行的非空行。"""
    bad = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if "${{" not in line:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        hash_idx = line.find("#")
        if hash_idx != -1 and hash_idx < line.find("${{"):
            continue  # 表达式位于注释内
        if _ENV_ASSIGN.match(line):
            continue  # env 中转赋值（官方修法）
        bad.append((lineno, line.rstrip()))
    return bad


class TestWorkflowInjectionGuard(unittest.TestCase):

    def test_review_yml_no_interpolation_in_run_blocks(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        bad = _violations(text)
        self.assertEqual(bad, [],
                         "run 块内发现 ${{ }} 直接插值（注入面）：%s" % bad)

    def test_detector_catches_historical_bad_patterns(self):
        # round-118 修复前的三种违规形态必须被本判定器抓住（反向验证）。
        historical = (
            '            --request "${{ github.event.pull_request.title }}" \\\n'
            '          echo "REVIEW_RANGE=origin/${{ github.base_ref }}...${{ github.sha }}" >> "$GITHUB_ENV"\n'
            '          --repo "${{ github.repository }}"\n'
        )
        self.assertEqual(len(_violations(historical)), 3)

    def test_env_relay_lines_accepted(self):
        good = (
            '          REQUEST: ${{ github.event.pull_request.title }}\n'
            '          PR_NUMBER: ${{ github.event.pull_request.number }}\n'
            '          # 注释内 ${{ github.event.* }} 不计\n'
            '        run:\n'
            '          python poster.py --pr "$PR_NUMBER"\n'
        )
        self.assertEqual(_violations(good), [])


if __name__ == "__main__":
    unittest.main()
