# 复盘轮报 round-154

open 5 / closed 217 / archived 24

## 分类统计

- 手工：147
- 口径纪律：23
- 评测：20
- 行为回归：19
- 误报：14
- 能力盲区：5
- 补丁返工：4
- 外部依赖：4
- 测试：3
- 转人工：2
- 能力缺口：2
- 门禁自举：2
- 自迭代盲区：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 46239d17c299 | 手工 | libcst 矩阵「管道直比 False、落盘复验 True」——对比基线一律以落盘产物为准，管道直比仅作初筛；与易错点 | - | - | retro\events-round-136.json |
| 85d3d7a66de0 | 手工 | r141 收官时为 release-gate._parse_suite 打 pytest 双格式补丁未带契约——检查器反 | - | - | retro\events-round-152.json |
| 96e51a1b1fff | 手工 | 前置校验首次插入把零 findings 的 change PR 卷进判卷集——违反 r115/r116 既定口径（只判有 | - | - | retro\events-round-138.json |
| ace3d7567ec0 | 手工 | uv lock 在 isolated extra 全图（semgrep 30+ 依赖树/pynguin）解析下把 pyt | - | - | retro\events-round-139.json |
| e0a2a78b058b | 手工 | 收官双跑连续判红（640/766/614/687/983s，同数测试健康基线 406/387s）；归因=宿主外部重负载（ | - | - | retro\events-round-141.json |

## 改进候选（按 权重×数量 排序）

- **手工：5 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
