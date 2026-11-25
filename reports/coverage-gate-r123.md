# round-123：report-adapter.py 覆盖率收敛——固定五子集 + 基线重切（v2.24.0）

## 结论先行

- **report-adapter.py 66.67% → 89.39%**：round-122 check 首次把它登记为 new_files（r105 接线经 runner 子进程被收集到 66.67%，其 r104 自有的 12 条契约测试从未在固定子集内被采集）；本轮将 `test_report_adapter.py` 纳入 `DEFAULT_TESTS`（五项，增量 0.4s），覆盖率直接恢复到 89.39%（118/132）。
- **measure（五子集，75 文件）**：overall **78.08%**（vs 基线 77.85%，+0.23pp）；五子集全绿（test_scripts_*.py 301.7s / test_agent.py 177.4s / test_dual_reviewer.py 106.1s / test_provider_ssrf.py 0.39s / test_report_adapter.py 0.42s）。
- **check 复测 PASS**：regressions=0、missing=0；基线按 r120/r122 先例重切（旧基线留档 `reports/coverage-round123/coverage-baseline-pre-r123.json`；generated_at 2026-11-09T19:13:53+08:00）；复测 new_files=0（75/75 文件入基线）。
- **runner.py / doc-freshness.py 维持原位**：86.72%（≥ 基线 86.66%）/ 83.23%（已于 r120 入账），不再追。
- **台账不变**：241 / open 8 / closed 209；契约 690 不变；脚本 83 不变。

## 前后对账

| 指标 | r122 入账值 | round-123（五子集） |
|---|---|---|
| overall_pct | 77.81（r122 实测）/ 77.85（r120 基线） | **78.08**（重切基线） |
| report-adapter.py | 66.67%（new_files） | **89.39%** |
| runner.py | 86.72% | 86.72%（不动） |
| doc-freshness.py | 83.23% | 83.23%（不动） |
| 子集 | 四项 | **五项**（+test_report_adapter.py） |
| CI self-check | check 单格 | 一致；workflow 不改 |

## 过程口径

- round-123 按 open 闸在干净树开局（先发现未提交编辑违反 git_state → git stash 后 open 闸全绿再 pop——本提醒：先开轮再改代码）。
- 重切基线理由（同 r120）：固定子集由四项扩为五项，入仓基线须来自新子集实测；旧基线完整留档，不删不改。
- 五项子集总增量（provider_ssrf 0.39s + report_adapter 0.42s）对总耗时几乎无影响；全量套件耗时仍 ~6 分钟级。
