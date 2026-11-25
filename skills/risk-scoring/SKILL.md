---
name: risk-scoring
description: 规模/耦合/稳定性三维风险评分，输出区域等级与高风险区域清单。也用于口语说法：这次改动风险多高、哪些区域是高风险、给变更打个风险分
---

# risk-scoring — 三维风险评分

## 目的与边界

把一次变更拆成区域，按「规模 / 耦合 / 稳定性」三维打分，输出区域等级、
整次综合分与高风险区域清单。权重是契约，不是调节旋钮：
规模 0.3 / 耦合 0.4 / 稳定 0.3，任何脚本与文档不得改动。

边界约定：

- 本 skill 只做评分，不做取证；输入数据由取数步骤提供，口径以 BASELINE.md 为准。
- 输入字段缺省按 0 处理，但类型必须为整数，否则退出码 2。
- 全部计算确定性、可复算；同一输入两次运行结果逐字节一致。

## 何时用 / 何时不用

用：主流程步骤 3（区域等级）、步骤 4（材料包需粘贴 score.py 原始输出）。
不用：没有区域划分的纯问答；或用户明确只要 diff 摘要。

## 脚本与用法

### score.py

```bash
echo '{"regions":[...],"overall":{...}}' | python skills/risk-scoring/scripts/score.py
python skills/risk-scoring/scripts/score.py --input regions.json
```

- 输入：stdin 或 `--input` 文件，结构见下。
- 输出：`weights`（回显契约）、`regions[]`（各区域 scale/coupling/stability/score/level）、
  `overall`、`high_regions`（等级为高的区域名）。

## 输入结构

```json
{"regions":[{"name":"payments","files":2,"added":41,"deleted":9,"modules":1,"callers":6,
  "high_impact":["signature"],"history_3m":4,"history_12m":6,
  "has_hotfix":true,"has_revert":false,"intent_deviation":false}],
 "overall":{"files":4,"added":78,"deleted":41,"modules":3,"callers":6,
  "history_3m":6,"history_12m":9}}
```

## 评分规则（与 BASELINE.md 逐条一致）

权重固定：规模 0.3、耦合 0.4、稳定 0.3。

规模分：

- 行数档（added+deleted）：<=50→1，<=200→2，<=500→3，<=1000→4，否则 5。
- 文件档：<=1→1，<=3→2，<=8→3，<=15→4，否则 5。
- 规模分 = 两个档取大；modules > 1 直接抬到 5。

耦合分：

- modules 与 callers 各按文件档查档取大。
- high_impact 非空 +1，上限 5。

稳定分：

- history_3m 与 history_12m 各按文件档查档取大。
- has_hotfix 或 has_revert +1；intent_deviation +1；上限 5。

综合分 = 0.3×规模 + 0.4×耦合 + 0.3×稳定，保留 1 位小数。
等级：>=4.0 高；>=2.5 中；否则低。

## 整次变更分

overall 用同一套公式；调用方如需「整次综合不高于最高区域」的兜底，
由编排层用 max(整体, 0.8×最高区域) 计算，score.py 本身不混合口径。

## 与主流程的接入点

| 主流程 | 用法 |
| --- | --- |
| 步骤 3 | 区域表 + 整次综合 + 高风险清单写入 step3_risk.json |
| 步骤 4 | 材料包必须粘贴 score.py 输出原文，不得手工转抄等级 |
| 步骤 9 | 手册排序参考区域等级，高风险区域优先交叉核对 |

## 消费注意

1. 等级是「回退难度」的代理：高=存在跨模块或数据影响，需迁移/回滚预案。
2. high_impact 填高危语义字段名（如 signature）；不确定就留空，不要臆造。
3. history_3m/history_12m 来自 git log 统计；浅克隆会低估，edge-detect 的
   shallow_clone 信号必须一并呈报。
4. 等级阈值 >=4.0 / >=2.5 属契约；调阈值等于换模型，必须先改 BASELINE.md。

## 退出码汇总

| 退出码 | 含义 |
| --- | --- |
| 0 | 正常打分 |
| 2 | 输入非法（JSON 解析失败、缺 regions/overall、字段类型错误） |

## 检查清单

1. 权重 0.3/0.4/0.3 与 BASELINE.md 一致。
2. 输出 weights 字段回显契约，测试钉死。
3. modules>1 的区域规模分必须为 5。
4. high_impact 只加耦合分，不影响稳定分。
5. 综合分保留 1 位小数后再比等级阈值。
6. 输入缺省按 0，但非整数立即退出 2。
7. high_regions 只收等级为「高」的区域。
8. 等级只有 高/中/低 三档，无「极高」。
9. overall 不参与 high_regions。
10. 输出顺序：regions 按输入顺序，不重排。

## 常见误用

- 把 intent_deviation 当耦合信号（它属于稳定分维度）。
- 用 modules>1 抬耦合分（modules>1 抬的是规模分）。
- 手工改 weights 后重新打分（等价于换模型，必须先改基线）。
