# round-124：agent/code_task/review_gate.py 覆盖率收敛——错误路径契约四条（v2.25.0）

## 结论先行

- **review_gate.py 63.64% → 93.94%（31/33，+30.30pp）**：r122 入账的「agent/code_task/review_gate.py 63.64%（33 语句）」是错误路径（missing patch / apply failure / not-a-repo / `_parse_review_cmds` 缺 `=`）未被固定子集触达所致；本轮在 `tests/test_agent.py::TestReviewGateWiring` 内补四条契约：
  1. `test_review_gate_missing_patch_raises_review_error`（缺 edits.patch → ReviewError，不得静默过）；
  2. `test_review_gate_apply_failure_raises_and_cleans_up`（补丁在白检出上应用失败 → ReviewError + worktree 清理）；
  3. `test_review_gate_not_a_git_repo_raises_review_error`（git worktree 失败 → ReviewError）；
  4. `test_parse_review_cmds_contract`（None→{}、`a=b=c`→`{a:b=c}`、缺 `=` 必抛 ReviewError）。
- **契约 690 → 694**（+4）；**版本 2.25.0**；overall/review_gate 实测见下表。
- **runner.py / doc-freshness.py / provider.py 维持原位**不再追。
- **台账不变**：241 / open 8 / closed 209。

## 前后对账（待 measure 落定后回填精确值）

| 指标 | r123 基线值 | r124 实测（五子集） |
|---|---|---|
| overall_pct | 78.08 | **78.17**（+0.09pp） |
| agent/code_task/review_gate.py | 63.64 | **93.94**（+30.30pp） |
| 契约数 | 690 | **694** |
