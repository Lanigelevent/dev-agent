# 概述（01）

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：总监 + 迭代官
> **权威范围**：本类管「这是什么、给谁用、边界在哪、有哪些能力」——定位、能力总览、术语导航
> **不是权威**：命令用法（见 06 运维）、架构组件（见 02 架构）、固定契约（见 BASELINE.md）、任务状态（见 07 任务）
> **复核期限**：2026-12-06（定位或术语变化时才改）｜ **上次复核**：2026-11-06
> **主导模式**：参考

## 本类管什么

- 一句话定位与能力边界（下方「定位与边界」节，自 README §一 收敛而来）
- 能力总览表（自 README §二 收敛而来）
- 术语导航（权威表在 docs/GLOSSARY.md）

## 本类不管什么

- 「怎么跑起来、每条命令的风险」→ 06 运维
- 「由什么组成、怎么连」→ 02 架构
- 「为什么这样定」→ 03 决策；「做到了哪」→ 04 进度

## 定位与边界

**dev-agent** 是一个对 Git 变更做全流程治理的代码智能体：评审（0-10 步主流程，
确定性规则 + LLM 双意见）→ 修复（工单-补丁-批准书链路）→ 落盘（五道闸）→
复盘（坑台账与轮报），并带合成语料 / 真实 CVE 语料 / SWE-bench 三环评测。

设计前提：**治理先行、产物可溯、失败如实**——补丁任何变动即作废重审，
降级与 NEED_HUMAN 如实上报，评测分母只用有效样本、双指标（recall 与
precision）缺一即不合格。

**能力边界（务必先读）**：本项目负责**评审、修复建议与受治理的落盘**，
**不替代人工决策**——修复分支永不自动合并，是否采纳由人工决定。
三条不可违反的产品约束：

| 约束 | 含义 |
|---|---|
| **写被审仓库的唯一入口是五道闸** | 机械补丁、引擎修复、编码循环编辑全部经 `fix-apply.py` 落盘；任一闸失败自动回滚 |
| **凭据零明文** | 命中密钥形态的 snippet 一律脱敏 `<redacted>`；凭据类发现不出补丁，一律转人工 |
| **修复与审核分立** | RACI 固定签字权（A 唯一），任何一方不得自审自批 |

## 能力总览

| 能力 | 说明 | 入口 |
|---|---|---|
| 代码评审 | 意图解析 → 一次取数 → 风险评分 → 并行审查（7 维度）→ 流式核验 → 高风险多轮查证 → 反向验证 → 结构化报告 | `runner.py` / MCP `code_review_run` |
| 修复 | 工单-补丁-批准书链路 + 五道闸落盘，失败自动回滚 | `fix-plan/fix-patch/fix-apply.py` / MCP `code_review_fix` |
| 引擎修复 | Ruff（973 规则 / 482 可修复 / 250 safe）+ LibCST 重构 codemod + ast-grep 多语言 AST 模式引擎（JS/TS+Python 29 规则 / 2 可修复），均经 subprocess+JSON 接入修复链 | `engines/ruff_adapter.py`、`engines/libcst_adapter.py`、`engines/astgrep_adapter.py` |
| 测试生成 | 确定性骨架（loop/hypothesis 两风格）、宿主 LLM 真用例、pytest 验收闸、新文件补丁 | `engines/testgen.py` / MCP `code_review_testgen` |
| 编码循环 | repo 符号地图 + SEARCH/REPLACE 唯一命中编辑 + worktree 内改代码 + 多候选补丁快照收集与回归过滤投票排序 + 稳定前缀/输出外置/历史压缩 + stderr 流式进度帧，补丁走修复链落盘 | `agent/code-task.py` / MCP `code_review_coding` |
| SWE-bench 评测 | 单实例编排 prepare/build/eval/report 四阶段，CRLF 补丁机器自检，docker 三级发现 | `agent/swe_run.py` |
| SWE-bench 口径 | gold 口径（验管线）与 **agent 侧口径**（验编码循环产出的补丁）双驱动，共用 harness 与台账；Pro/Live 另设独立驱动与 key（不折算） | `skills/eval-harness/scripts/gold-sample.py`、`agent-sample.py`、`pro-sample.py`、`live-sample.py` |
| DeepSWE 评测 | Harbor 格式 113 任务（5 语言）解析为 JSONL 索引 + clone/checkout/编码循环/Docker 验证/台账单命令；gate 语料不入库 | `skills/eval-harness/scripts/deepswe-fetch.py`、`deepswe-sample.py` |
| 编码记忆 | 记忆检索（TF-IDF + cosine）few-shot 注入 + 相似条目聚类合并与冷记忆老化；读写默认关闭 | `skills/retro/scripts/memory_retrieval.py`、`compact-memory.py` |
| 评测 | 合成语料、真实 CVE 语料、SWE-bench 官方 harness、DeepSWE 四类基准 | `skills/eval-harness/` |
| 治理 | 科层制组织（总监/评审/修复/审核/迭代官）、RACI 签字权、SRE 错误预算、复盘台账 | `skills/director/`、`skills/retro/` |

## 相关文档

| 文档 | 关系 |
|---|---|
| [README.md](../../README.md) | 统一入口（第一屏定位与导航） |
| [docs/GLOSSARY.md](../GLOSSARY.md) | 术语表权威源（本类只导航不复述） |
| [docs/02-architecture/README.md](../02-architecture/README.md) | 由什么组成、怎么连 |
| [开源依赖与上游跟踪](../06-operations/开源依赖与上游跟踪.md) | 引擎与测试依赖的上游仓库、能力与跟踪方式 |
