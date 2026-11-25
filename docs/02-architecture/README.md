# 架构（02）

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：总监 + 迭代官
> **权威范围**：本类管「由什么组成、怎么连、有什么约束」——分层组件、数据流、集成点、已知局限
> **不是权威**：命令用法（06 运维）、约束正文（AGENTS.md/BASELINE.md）、依赖清单（pyproject.toml）
> **复核期限**：2026-12-06（结构变化才改）｜ **上次复核**：2026-11-06
> **主导模式**：参考

## 本类管什么

分层与组件划分、关键数据流（按一次典型调用串起来）、外部集成点、已知架构性局限（诚实列出）。结构变化才改；参数与配置以源码为准。

## 本类不管什么

- 每条命令的用法与风险 → 06 运维
- 契约全文 → BASELINE.md；硬约束全文 → AGENTS.md（读者视图见 docs/RULES.md）
- 会变的计数与版本 → docs/08-memory/INDEX.md 的取数命令

## 分层与组件

```
┌─ 治理壳（纯标准库，可分发）────────────────────────────┐
│ skills/ 13 个技能 × 90 个脚本（评审/修复/审核/迭代/总监）│
│ mcp/ MCP 服务器  llm/ 提供者抽象（openai 兼容 / 宿主协议）│
└──────────────┬─────────────────────────────────────┘
               │ subprocess + JSON（唯一跨层通道）
┌─ 引擎层（.venv 白名单依赖）───────────────────────────┐
│ engines/  ruff / libcst / astgrep 适配器 + testgen      │
│ agent/    repo_map / edit_formats / code-task 编码循环  │
│           trace 埋点 / swe_run（SWE-bench 编排）        │
└──────────────────────────────────────────────────────┘
        写被审仓库的唯一入口：repair/scripts/fix-apply.py
        （审核人批准书 → 五道闸 → 行为回归，失败自动回滚）
```

## 组件职责与「不负责什么」

| 组件 | 负责 | 不负责 |
|---|---|---|
| `skills/`（治理壳） | 评审/修复/审核/迭代/总监五类技能脚本，全 stdlib | 不 import 任何第三方（R-001） |
| `engines/`（引擎适配层） | ruff/libcst/astgrep subprocess+JSON 接入、testgen 生成 | 不直接写被审仓库（产物走修复链） |
| `agent/`（编码循环） | repo 地图、编辑格式、code-task 循环、trace、SWE-bench 编排 | 不直接写被审仓库（补丁走修复链） |
| `llm/` | openai 兼容 / host 宿主协议抽象 | 不落盘密钥（key 只过环境变量） |
| `mcp/` | JSON-RPC 2.0 stdio 服务器（16 工具，含异步 submit/status/cancel/purge） | 不承担 CLI 职责 |
| `repair/scripts/fix-apply.py` | 写被审仓库的唯一入口（五道闸） | 不做修复决策（只执行批准书） |

## 关键数据流（一次典型评审调用）

`intent-parse`（意图三键）→ `preflight`（预检/定档）→ `edge-detect`（11 类边界）→ `deterministic-rules`（38 条硬规则）→ `score`（三维评分）→ `dispatch-plan`（定维度路数）→ 子代理按七要素提交 → `findings-check`（校验）→ 流式核验 → 高风险多轮查证 → 反向验证（coverage/perspective-scan）→ `report-check`+`schema-check`（交付双闸）。修复链：工单 → 补丁 → 批准书 → 五道闸落盘。

## 外部集成点

- **MCP**：`mcp/review_mcp.py`（JSON-RPC 2.0 stdio，2025-06-18 协议；ZCode 插件与 DeepSeek Harness 接线见 `interop/deepseek-harness/`）。
- **LLM**：openai 兼容端点或宿主协议（`llm/provider.py`）；端点白名单=公网 https 或本地回环，
  跳转与响应体限制见 BASELINE「LLM 提供者契约」。密钥只过环境变量，不落盘。
- **被审仓库**：只读评审 + 经五道闸的受治理写入，无其他写路径。

## 已知架构性局限（诚实列出）

- 真实 LLM 端点层行为只能实跑暴露（r85 评审维度 6：三坑皆出于此层）。
- host 端到端小 n（评测结论 n≤20 不外推能力上限）。
- 套件时长由负载主导（D-041：300s 观测线 / 600s 挂死护栏）。

## 相关文档

| 文档 | 关系 |
|---|---|
| [docs/DEVELOPMENT.md](../DEVELOPMENT.md) | 目录结构与扩展指南（权威源） |
| [BASELINE.md](../../BASELINE.md) | 全部固定契约 |
| [docs/RULES.md](../RULES.md) | 硬约束读者视图 |
| [docs/06-operations/开源依赖与上游跟踪.md](../06-operations/开源依赖与上游跟踪.md) | 引擎依赖的上游能力与跟踪 |
| [docs/06-operations/README.md](../06-operations/README.md) | 命令与运维 |
