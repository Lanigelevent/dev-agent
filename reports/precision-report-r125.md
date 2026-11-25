# round-125：precision-report.py 覆盖率收敛——纯函数契约 +5（v2.26.0）

## 结论先行

- **precision-report.py 36.07% → 51.14%**（+15.07pp，112/219 statements）：新增 `tests/test_scripts_precision_report.py`（5 条契约，文件名匹配 test_scripts_*.py，自动进入固定覆盖子集），把 r120 入账的 eval-harness 长尾第三项（唯一纯函数可测的一项）收掉。
- **_load_real 两路径**：无 samples → judge 直抽（recall/precision/claimed/grounded/valid_samples/weak/per_sample）；有 samples → 按 `defect_class` 交叉统计覆盖矩阵、按 total 降序。
- **_aggregate_real 三路径**：空 entries → None；两仓合成示例（recall=grounded/valid=2/8，precision=2/4）、class_coverage 合并（按 total 降序）、per_repo 列表；**分母零 → None**（recall/precision 分母分别为 0 时不得抛异常除零）。
- **真实 schema 核验（避免契约砸错）**：合成假数据前先对 `reports/real-corpus-urllib3/judge.json` 实读确认——`per_sample[].sample_id` 即样本的 `fix_commit`（full sha）；因此 `_load_real` 里 `per.get(s.get("fix_commit"))` 查的表键与 `sample_id` 一致，属有效实现、非 bug。
- **measure/check（五子集）**：overall **78.46%**（vs 基线 78.08%，+0.38pp）；regressions=0、missing=0、new_files=0（75/75 入基线）。
- **开局闸流程偏差如实入账**：先改码再开 open 闸 → git_state FAIL；stash 后 open 闸再 FAIL（未跟踪测试文件仍在树 + stash 还原文档计数造成 freshness 表象红）；stash pop 复原 → 最终树 measure/双跑全绿、close 6/6 全绿。
- **契约 694 → 699**（+5）；**版本 2.26.0**；双跑已在最终树完成：**414.151 / 409.522 秒**（`logs/suite-r125-run1/2.log`，699 项全绿，各 1 skip）；台账 **241 / open 8 / closed 209 不变**。

## 前后对账

| 指标 | r123 基线值 | r125 实测（五子集） |
|---|---|---|
| overall_pct | 78.08 | **78.46**（+0.38pp） |
| precision-report.py | 36.07 | **51.14**（+15.07pp） |
| review_gate.py | 93.94 | 93.94（不动） |
| provider.py | 95.27 | 95.27（不动） |
| runner.py | 86.72 | 86.72（不动） |
| doc-freshness.py | 83.23 | 83.23（不动） |
| 契约数 | 694 | **699** |

## 过程口径

- round-125 开局违规：先改码再开 open 闸 → git_state FAIL；stash 后 open 闸再 FAIL；pop 复原后最终树工具链全绿，本轮记录如实、events 自报入账（第 3 条 confirmation）。
- eval-harness 三角余两项（agent-sample.py 21.83% / deepswe-sample.py 35.21%）为宿主 harness 集成点，未列入固定子集补测范围；继续由宿主评阅预算决定是否展开。
