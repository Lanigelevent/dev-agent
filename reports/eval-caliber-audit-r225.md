# round-225：评测口径季度对账（零代码，v2.100.0 不增版本）

## 1. 结论先行

- **0.42% 再次复算成立**：当前 v2.100.0 环境重跑 `swrenbench-import.py score --corpus swr-slim.jsonl --limit 1000` →
  `point_recall = 0.0042`、`caught 3 / changes_total 713`、`clean_prs 500`、`clean_zero_noise 0.974`（15 条 findings 均未被判错）——
  与 README/PROGRESS「对外硬规则臂 0.42%」逐位一致。上次复算 r175、中间 r184 `reports/reviewbench/score-r184.json` 同值 0.0042。
- **宿主臂口径稳定**：README/PROGRESS/DECISIONS 一致采用 D-053 因果表述（n=1000 全量空响应 = 执行会话未实质评审，非协议缺陷；协议链路可用性由 r114 PR F1 0.5789 证明）；
  `unavailable` 不作能力宣称。历史卷中的旧因果表述保留并带 D-053 勘误注记，不回改。
- **契约语义边界**：契约数已从 r175 的 778 增至 **849**，新增脚本 86→90（repo-rules-inject / trace-export / prompt-optimizer / memory-pipeline）
  与 MCP 异步作业（submit/status/cancel/purge + resources）的契约均为工具/治理层行为，**未将任何工具层数字外推为评审召回能力**；
  对外唯一数字仍只来自 38 硬规则臂与 SWRBench 机械判分桥。
- **无勘误需要**：tracked 文件扫描 0.42% / point_recall / unavailable / D-053 表述一致；本轮不改任何口径数字与代码。

## 2. 证据可用性（如实）

- 硬规则臂原始结果已重新落盘（`reports/_work/swr-caliber-audit-r225.json`，gitignored 临时产物）。
- 宿主臂原始 judge.json 在 r222/r223 清理中随 `reports/_work/` 删除，**不再可读**；结论以已入仓的 README / PROGRESS / BASELINE-HISTORY / ROADMAP-HISTORY 轮次记录为准，不声称原始 JSON 可读。

## 3. 范围外

- 剩余约 2GB 评测缓存（verified-runs 四轮 / swe-work / live 小产物 / swe-out harness）仍待用户裁定，本轮不碰。
- 依赖刷新锚点 r220 第十六跑后第 5 轮，~10 轮节奏未到，不刷新。
- 对外口径：硬规则臂 0.42%；宿主臂 unavailable；部分口径与 blocked 单列；agent 侧 20/20 为内部口径。

## 4. 证据

- `reports/_work/swr-caliber-audit-r225.json`（复算）；
- `reports/reviewbench/score-r184.json`（历史同值）；
- README.md:31、docs/PROGRESS.md:21、docs/DECISIONS.md D-053、docs/BASELINE-HISTORY.md / ROADMAP-HISTORY.md 相关轮次条目。
