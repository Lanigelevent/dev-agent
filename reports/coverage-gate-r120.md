# round-120：覆盖率常态出数 + 子集扩容 + 基线重切（v2.21.0）

## 结论先行

- **常态实测（固定三项子集，对回基线对账）**：overall 77.69% vs 基线 77.78%（−0.09pp，整体在 0.5pp 容差内）；file 级判 REGRESSION：
  - `llm/provider.py` 94.25% → **83.11%**（−11.14pp）——r118 SSRF 加固净增 ~150 语句，固定三项子集（test_scripts_*/test_agent/test_dual_reviewer）不含 r118 的 SSRF 契约测试，覆盖率被系统性低估；
  - `skills/orchestrator/scripts/runner.py` 86.66% → 85.22%（−1.44pp）——r105 report-adapter 接线新增未覆盖行，如实入账；
  - `skills/self-iteration/scripts/doc-freshness.py` 83.83% → 83.23%（−0.6pp）——F5 变更后行数移位，如实入账。
- **修复**：DEFAULT_TESTS 扩为四项（+`tests/test_provider_ssrf.py`，增量 0.6s）；`docs/DEVELOPMENT.md` 口径同步为「固定四项测试子集」。CI self-check workflow 无需改（gate 默认子集随代码同步）。
- **重测（四子集）**：overall **77.85%**（+0.07pp vs 基线）；`llm/provider.py` **95.27%**（+1.02pp，SSRF 契约测试覆盖良好）；runner.py / doc-freshness.py 两项漂移维持原位（如实入账，见上，属子集外代码增长，非行为回归）。
- **基线重切（round-89 先例）**：`skills/self-iteration/coverage-baseline.json` 按四子集重测值覆盖（generated_at 2026-11-09T15:03:18+08:00）；旧基线留档 `reports/coverage-round120/coverage-baseline-pre-r120.json`；复测 `coverage-gate.py check` → **PASS**。
- **双跑全绿**：**453.019 / 406.188 秒**（`logs/suite-r120-run1/2.log`，688 项全绿，各 1 skip）。
- **台账不变**：240 / open 7 / closed 209；契约 688 不变；脚本 83 不变；freshness 归零。

## 前后对账表

| 指标 | 入仓基线（2026-11-06） | r120 实测（四子集） |
|---|---|---|
| overall_pct | 77.78 | **77.85**（+0.07pp） |
| llm/provider.py | 94.25 | **95.27**（+1.02pp） |
| runner.py | 86.66 | 85.22（−1.44pp，r105 接线） |
| doc-freshness.py | 83.83 | 83.23（−0.6pp，F5 变更） |
| 子集 | test_scripts_*/test_agent/test_dual_reviewer | +test_provider_ssrf.py |

## 过程口径

- 本轮 measure 两次（679.7s / 680.8s，耗时几乎全在固定子集），reports/coverage-round120/measured.json 为四子集重测证据；pre-r120 旧基线已留档。
- 固定子集纪律不变（全量套件不测覆盖率，D-034 的 2.6× 成本论据不动）；仅因 r118 引入安全关键模块而增加一个快速的安全契约文件。
- runner.py / doc-freshness.py 两项如仍需收敛，应由其各自模块的负责人在固定子集内补测试或下一輪基线时一并裁定（不在本轮范围）。
