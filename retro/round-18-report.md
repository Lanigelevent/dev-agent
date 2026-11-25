# 复盘轮报 round-18

open 1 / closed 49

## 分类统计

- 手工：44
- 误报：3
- 行为回归：2
- 补丁返工：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 23529a460364 | 手工 | 被审仓库 sympy 1.1 要求 Python ≤3.9（from collections import Mappin | 被审仓库运行时约束与宿主解释器版本不匹配；国内主镜像对该包无索引 | 用兼容垫片（collections ABC 别名 + inspect.getar | retro/events-round-18.json |

## 改进候选（按 权重×数量 排序）

- **手工：1 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
