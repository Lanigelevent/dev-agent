# 文档树索引与唯一权威映射

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：迭代官
> **权威范围**：docs/ 树内导航、每类事实的唯一权威、引用关系与失效文档处置规则
> **不是权威**：任何正文事实；冲突时以下表「唯一权威」列为准
> **复核期限**：2026-12-31（文档增删/挪位时随轮同步）｜ **上次复核**：2026-11-25
> **主导模式**：参考

本文件只回答三件事：**某类事实去哪里读、哪些文件是唯一正文、文档增删时改哪些引用**。
仓根访客入口是 [README.md](../README.md)。

## 唯一权威映射

| 事实类别 | 唯一权威 | 不是权威 / 只放指针 |
|---|---|---|
| 项目介绍、定位、总体架构摘要、快速开始、使用与文档导航 | [README.md](../README.md) | 细节以 01/02/06 与契约权威为准 |
| 智能体主流程 0–10、硬约束 1–8、维护红线、组织架构、脚本清单 | [AGENTS.md](../AGENTS.md) | RULES 只做读者视图 |
| 固定契约、输出 schema、退出码、评分/闸门/评测/互操作契约 | [BASELINE.md](../BASELINE.md) | 代码实现不得反向覆盖契约 |
| 文档归属、取代关系、引用规则 | 本文件 | 其他文档不复制本表 |
| 产品定位、能力清单、适用与不适用场景 | [01-overview/README.md](01-overview/README.md) | README 只留摘要 |
| 分层、组件职责、数据流、集成点、架构性局限 | [02-architecture/README.md](02-architecture/README.md) | DEVELOPMENT §2 只讲目录导航 |
| 决策理由、候选方案、代价与状态 | [DECISIONS.md](DECISIONS.md) | 只追加，不追改历史条目 |
| 当前版本、契约数、台账、最近验证等工作状态 | [PROGRESS.md](PROGRESS.md) | 历史在 BASELINE-HISTORY / ROADMAP-HISTORY |
| 版本发布沿革与逐轮证据 | [BASELINE-HISTORY.md](BASELINE-HISTORY.md) | 冻结层，只增不改 |
| 路线阶段、方向与逐轮路线回填 | [ROADMAP.md](ROADMAP.md)、[ROADMAP-HISTORY.md](ROADMAP-HISTORY.md) | 现行卷管方向，沿革卷只增不改 |
| 全项目待办、每轮开局检查单 | [../retro/next-round.md](../retro/next-round.md) | 轮报与 ROADMAP 不得复制待办 |
| 坑的现象、根因、对策与结案口径 | [../retro/pitfalls.json](../retro/pitfalls.json) | 05 排障只做人类可读导航 |
| 每轮完成记录与复盘候选 | `retro/round-N-report.md` | 由 retro-report.py 生成 |
| 环境搭建、扩展、测试、发布流程 | [DEVELOPMENT.md](DEVELOPMENT.md) | 06 运维管命令面 |
| 命令使用、风险档、配置与操作入口 | [06-operations/README.md](06-operations/README.md)、[06-operations/使用说明与配置.md](06-operations/使用说明与配置.md) | 环境/发布全文仍在 DEVELOPMENT |
| 引用的开源项目、能力、上游仓库与跟踪要点 | [06-operations/开源依赖与上游跟踪.md](06-operations/开源依赖与上游跟踪.md) | 声明版本看 pyproject/uv.lock |
| 术语一句话定义与权威指针 | [GLOSSARY.md](GLOSSARY.md) | 不展开正文事实 |
| 硬约束/红线的读者索引 | [RULES.md](RULES.md) | 正文在 AGENTS/BASELINE |
| 高频上下文与数值取数命令 | [08-memory/INDEX.md](08-memory/INDEX.md) | 不手抄会变的数值 |
| 当前类入口与导航 | [04-progress/README.md](04-progress/README.md)、[05-troubleshooting/README.md](05-troubleshooting/README.md)、[07-tasks/README.md](07-tasks/README.md) | 类入口只导航，不建第二正文 |
| 证据与运行产物 | `reports/`、`logs/`、`runs/` | 非文档正文，按需引用于轮报 |

## 引用规则

1. 同一事实只在「唯一权威」处写正文；其他文档必须改为链接或一句摘要。
2. 修改权威文件后，必须同轮检查本表、README 文档地图与相关类入口。
3. 会变化的数字必须给取数命令或脚本真值来源，不手抄多份。
4. 历史文件（两份 HISTORY、轮报、发布证据）只增不改；不得把历史记录当待办。
5. **失效、过期或被取代的文档直接删除并清除引用**；不新建归档目录、不保留占位文件。
   仍在使用的历史证据文件不属于失效文档，继续保留在唯一历史权威位置；
   冻结历史条目中出现的旧路径是当时记录，不构成活动引用，不要求追改。

## 类入口清单

| 类 | 入口 | 管什么 |
|---|---|---|
| 01 概述 | [01-overview/README.md](01-overview/README.md) | 定位、能力总览与边界 |
| 02 架构 | [02-architecture/README.md](02-architecture/README.md) | 结构、数据流与局限 |
| 03 决策 | [03-decisions/README.md](03-decisions/README.md) | 决策编号与记录规则 |
| 04 进度 | [04-progress/README.md](04-progress/README.md) | 当前快照与历史证据导航 |
| 05 排障 | [05-troubleshooting/README.md](05-troubleshooting/README.md) | 坑台账导航与常见问题 |
| 06 运维 | [06-operations/README.md](06-operations/README.md) | 命令风险、使用与配置、开源跟踪 |
| 07 任务 | [07-tasks/README.md](07-tasks/README.md) | 路线与待办权威指针 |
| 08 记忆 | [08-memory/INDEX.md](08-memory/INDEX.md) | 高频上下文与取数命令 |