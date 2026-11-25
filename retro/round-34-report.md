# 复盘轮报 round-34

open 10 / closed 98

## 本轮主题：升级计划阶段 0 清零 + 阶段 1-A 首批落地

开局检查单三条遗留能力项（1 意图流水线实战 / 4 探针实战 / 6 容器检查前移）本轮全部清零，
另完成 round-33 候选遗留（8 的 weak_closure 消化）与升级计划阶段 1-A 首件（候选证据排序）。

## 分类统计

- 手工：77
- 行为回归：12
- 误报：11
- 补丁返工：4
- 转人工：1
- 能力盲区：1（新增分类：探针/自检的本机执行盲区）
- 能力缺口：1（意图流水线实战三缺陷，open 待消化）
- 口径纪律：2（weak_closure 散文钉法、候选排序新≠能过闸）

## 本轮入册（5 条）

（第 5 条：修复计划蒸馏落地 65a3c4e21eb8，见 BASELINE 沿革 round-34 末节；契约 TestPlanDistill + test_repair_plan_note_lookup_and_material_injection）

| ID | 类别 | 坑 | 状态 |
|---|---|---|---|
| a42954474589 | 能力盲区 | 探针与自检只在本地跑，编译扩展仓库全程盲区 → --probe-docker 容器通道（三约束实测撞出） | closed |
| 791468dc0ca2 | 能力缺口 | 意图流水线实战三缺陷：ambiguity 不收悬空指代 / 复合子句不拆 / collect 形状静默零命中 | open |
| 2bef0ef509f2 | 口径纪律 | 散文式测试钉法机器跑不了 → verifier 合成 discover 命令，weak_closure 10→4 | closed |
| 0fc9d873fe0a | 口径纪律 | 候选补丁纯按时间取新 → 加证据位（校验未过线垫底），理由进 provenance 可复算 | closed |

## 验收证据锚点

- 意图流水线实战：reports/_work/intent-real/（intent/plan/dispatch/collect 四产物 + run-log）
- 探针实战：reports/_work/probe-22711-run/（两轮探针 history、803B 补丁、final-meta）+
  reports/_work/verify-22711-container.py 输出（test_patch+本补丁 → F2P 2 passed）
- 阶段 0 验收总记录：reports/_work/round34-stage0-acceptance.md
- 结案口径：verify-closure-commands --run 19 命令 / 实跑 17 / 全过 / 违规 0
- 变异体四份：mutant-probe-docker / mutant-selfcheck-docker / mutant-candidate-ranking /
  （探针授权闸沿用 round-28 既有反向验证）

## 数字收口

- version 1.34.0 → **1.35.0**；测试 305 → **313**；台账 104 → **109 条 / open 10**
- 全量收官终态：**313 项三次全绿 371.643s（负载离群）/ 300.535s / 305.719s**（2026-10-26；稳态贴 300s 线略越，入册 open 坑 bee217a0da8c，画像后定案，不悄悄改线）
- doc-freshness drift_count=0（README/DEVELOPMENT/BASELINE/plugin.json 同步）

## 本轮自踩自收

结案注里把「再跑一遍本检查器」写成反引号命令，self_reference 闸当场抓住——
round-31 建的防线对自身口径有效（改为散文描述，命令不进反引号）。
