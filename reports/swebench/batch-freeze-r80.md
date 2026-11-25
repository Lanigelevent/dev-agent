# round-80 D-045 语料扩面离线部分：新批次选择与冻结（n=9）

## 结论先行

- **新批次 9 条冻结**（`datasets/swebench/live/gate-r80-batch.jsonl`）：
  aiogram-1594 / sh-744 / arviz-2413 / cfn-lint-3764 / beancount-931 /
  beets-5457 / briefcase-2075 / checkov-6893 / conan-17102——9 仓分散、
  与历史 gate 语料（gate-10 / extra-1 / r65 / r68）零重叠。
- **选法确定性**（可复现）：池 = lite.parquet 300 − 暴露（gate 并集 11
  + matplotlib 仓库级 12 + urllib3 1）= 278；健康过滤（problem_statement
  / test_patch / test_cmds 非空）后按仓库分组、组内 instance_id 升序取
  首、每仓 1 条，取前 9 仓。无随机性、无难度筛选（修复面规模是测量
  对象不是选批条件，r75 结论不用于挑软柿子）。
- **协议就位声明**：开跑时用 D-045 零反馈口径 + 协议 v4（rounds 24 +
  `--protocol-notes` 附录）+ **D-048 指针条款**（附录必含失败测试指针
  行——从 test_patch 解析新增测试文件）；判分沿用 f2p-only 口径
  （test_cmds 基线对比，P2P 上游截断缺陷由 live-sample.py 的
  malformed_node_ids 体检拦截）。
- **未跑**（本轮无端点，按 next-round 第 40 条 ② 离线部分执行）；
  真连跑待端点提供。

## 冻结字段

每条：instance_id / repo / base_commit / pull_number /
problem_sha256（16 hex 前缀）/ test_patch_sha256（16 hex 前缀）/
problem_len / test_cmds_head / frozen_note（协议与排除依据）。
problem_len 分布 509–3536 字符（与已用九候选同量级）。

## 次项：>450s 套件趋势归因观测（r76–79 四连）

| 轮 | 双跑耗时（s） | 口径 |
|---|---|---|
| r76 | 516.1 / 471.5 | pytest 530 |
| r77 | 457.2 / 482.0 | pytest 534 |
| r78 | 628.7 / 607.0 | pytest 538 |
| r79 | 517.7 / 551.4 | pytest 538 |
| r78 闸内 | 509.4 / 779.1 | unittest 538 |
| r79 闸内 | 424.3 / 485.7 | unittest 538 |

- 同代码相近时段波动幅度 ~90–290s（r79 pytest 551 vs 闸内 unittest
  424；r78 闸内 run2 779s 为极值）；与 r45 画像结论一致——无单点慢
  测试异常，**趋势由环境负载主导**（会话双跑排队/邻居负载），契约
  自然增长（527→538）贡献有限。**结论：负载主导、非代码回归，红线
  不动**；D-041 升级处置维持（连续 4 轮 >450s 属观测指标越线，600s
  挂死护栏未触发）。

## 限制

- 冻结 ≠ 可判分：test_cmds 基线健康（venv 依赖可装、套件可跑）须在
  开跑前逐条实测（live-sample.py 基线体检），本轮未做（无端点不跑）。
- D-048 指针行的 node id 解析质量依赖 test_patch 形态，参数化 id 截断
  缺陷（cfn-lint 型）在开跑前体检兜底。
- n=9 对齐 D-045 原口径；若总监提供端点，真连跑按预算 ≤8h 走。

## 证据

- `datasets/swebench/live/gate-r80-batch.jsonl`（冻结清单，入仓）
- `datasets/swebench/live/_exposed-ids-r80.json`（暴露集中间产物）
- 源数据：`datasets/swebench/live/lite.parquet`（300 实例）
- 协议：D-045（`docs/DECISIONS.md`）、D-048、协议 v4
  （`reports/uplift-r79-floor-effect/report.md`）
