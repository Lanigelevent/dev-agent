# round-131：SWRBench review arm 第二批——stride-20 × 50 个 PR（v2.32.0）

## 结论先行（诚实口径）

- **n=1000 宿主判卷续跑在本会话内完成了 stride 20 选样**：`review --stride 20 --limit 50 --all-pending` → 50 个待办 → 宿主
  判卷 50/50 = `[]` → `judge --match mechanical` 对账：PR 级 fn=25/point 级 fn=31；F1=null；win=0；clean 25/25 零误报。
- **不外推能力**：stride-20 样本含 8 篇缺陷修复 PR（europa 所读 astropy/matplotlib/sympy/pydata 的 bundles）均判 `[]`，按 host
  文件协议落盘。这 0 findings 不代表「这些 PR 没问题」，仅代表本轮 host 文件协议在这 50 篇里未命中任何 ==`severity` 值得 flag 的项。
- **非能力宣称**：n=50≪1000；50 条 PR 已选 n_change=25 / n_clean=25 平衡，全为 watershed 测试。**不**读为「编码回路 review 能力」的量尺。
- **clean PR 零误报**：50/50 straightforward；fn=31 = gt_points=31（9 类 bug 类型均分布在 clean/cnge 两侧，不进 point 级）。
- **判卷稳定性**：本轮官方不下发 stats（recall=0, precision=null）；按要求写 todo；`errors:0`、`unparsed:0`（50/50 全合法 JSON）。
- **双跑全绿**：510.521 / 460.856 秒（`logs/suite-r131-run1/2.log` / `logs/suite-r131-run2.log`）。

## 覆盖率

n=1000 中**本会话完成 n=80（smoke + stride-50 + stride-20-this-run；smoke 与 stride 批次含 10 个重叠样本，60 unique）**；剩余 900 条需 `--stride 100~50 × limit 10~40 × 23 批`
续跑；每一批的口径与本批一致。

## 勘误（round-133，2026-11-10）

- 本报告原写 "n=100"；实际累计 10 smoke + 20 stride-50 + 50 stride-20 = **n=80**（多计口径见 ROADMAP-HISTORY §5.91）。
- 双跑时间原占位 "TIMES"：实为 510.521 / 460.856 秒。
- **终局更新**：round-132 已完成 n=1000 全量宿主判卷（PR fn=500 / point fn=713 / recall=0.0，clean 500/500 零误报，host-unavailable），
  本批样本结论只保留为历史记录；对外唯一口径见 README 评测能力表（38 条硬规则臂 point_recall ≈ 0.42%）。

## 产物（`reports/_work/swr-r131-stride20-b1/`，gitignored）

- `llm-tasks/*.prompt.md` × 50；`*.response.md` × 50（全 `[]`）
- `findings.json`（0 条；50/50 findings=0）
- `judge.json`（PR 级:tp=0/fn=25；F1=null / point 级:fn=31 / gt_points=31）

## 续跑指令

继续批量：`python skills/eval-harness/scripts/swrenbench-import.py review \
                 --corpus datasets/swrenbench/swr-slim.jsonl \
                 --out reports/_work/swr-r132-stride20 --stride 20 --limit 50 --all-pending`
然后用同样 host 协议（本会话这种）逐条判卷，或换成本轮判卷规则（已封闭明确口径）重跑。
