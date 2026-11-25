# dev-agent

> **一句话**：让「AI 审查代码」变成可回放、可批准、可回滚的流水线 —— 对 Git 变更做只读
> 评审，**修复补丁先行**，任何写入一律过审核人两道闸与五道闸，失败自动回滚。
>
> **治理先行**的全能代码智能体：评审 / 修复 / 重构 / 测试生成与编码循环，Python 深耕优先；
> 复用成熟开源引擎（Ruff/LibCST/ast-grep），修复分支永不自动合并。

> **创建日期**：2026-10-24 ｜ **当前状态**：维护中
> **所有者**：总监 + 迭代官 ｜ **主导模式**：参考
> **权威范围**：项目定位、能力边界、快速开始与文档权威地图
> **不是权威**：任何正文事实——架构 [docs/02-architecture/README.md](docs/02-architecture/README.md)、
> 命令 [docs/06-operations/README.md](docs/06-operations/README.md)、契约 [BASELINE.md](BASELINE.md)、
> 约束 [AGENTS.md](AGENTS.md)、索引 [docs/INDEX.md](docs/INDEX.md)
> **复核期限**：2026-12-31 ｜ **上次复核**：2026-11-25

**版本 2.99.0**（真值源 `.zcode-plugin/plugin.json`；Python 治理壳 ≥3.11 纯标准库 / 引擎层 3.12 `.venv`；Windows / Linux）。

## 当前状态

| 项 | 现值 | 权威取数 |
|---|---|---|
| 契约测试 | **848 项**（845 passed + 3 conditional skip） | `.venv/Scripts/python.exe -m unittest discover -s tests` |
| 最近全量 | **550.02 秒**，低于 600 秒硬护栏 | `logs/suite-r221-run1.log` |
| 治理壳 | **13 个技能 × 90 个脚本**；MCP **16 个工具** | `skills/`、`mcp/review_mcp.py` |
| 坑台账 | **266 条，open 0** | `retro/pitfalls.json` |
| 评审精度 | ReviewBench deterministic precision **0.6667**（地板 0.65） | `skills/eval-harness/precision-baseline.json` |
| 评测口径 | agent 侧 **20/20**；对外硬规则臂 **0.42%**；部分口径与 blocked 单列 | `docs/PROGRESS.md` |

完整当前快照只看 [docs/PROGRESS.md](docs/PROGRESS.md)；逐轮历史在
[docs/BASELINE-HISTORY.md](docs/BASELINE-HISTORY.md)、[docs/ROADMAP-HISTORY.md](docs/ROADMAP-HISTORY.md)
与 `retro/round-*-report.md`。

## 定位与能力边界

**做**：diff 进入 → 意图解析 → 预检与风险评分 → 多维审查 → 证据核验 → 报告；
发现可进入工单 → 补丁 → 批准书 → 五道闸落盘；同时提供测试生成、编码循环与多类评测驱动。

**不做**：不替代人工合并决策、不自动合并修复分支、不承诺未实测的平台或基准外推能力。
三条不可违反的产品约束：

1. **写被审仓库的唯一入口是五道闸**；任一闸失败自动回滚。
2. **凭据零明文**；凭据类发现不出补丁，一律转人工。
3. **修复与审核分立**；RACI 固定签字权，任何一方不得自审自批。

能力清单与适用场景见 [docs/01-overview/README.md](docs/01-overview/README.md)；
系统结构、数据流与架构局限见 [docs/02-architecture/README.md](docs/02-architecture/README.md)。

## 快速开始

```bash
# 只读评审（治理壳，Python >= 3.11）
python skills/orchestrator/scripts/runner.py --repo <仓库> --range main..feature

# 引擎层与编码循环（Python 3.12）
uv sync
uv sync --extra isolated   # 可选：Semgrep/Pynguin 子进程隔离

# 全量回归
.venv/Scripts/python.exe -m unittest discover -s tests
```

常用命令与风险档见 [docs/06-operations/README.md](docs/06-operations/README.md)；
环境搭建、扩展、测试与发布流程见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 文档权威地图

每类事实只保留一个正文权威；入口与索引只放指针。

| 事实类别 | 唯一权威 | 关系 |
|---|---|---|
| 智能体主流程、硬约束、组织与脚本清单 | [AGENTS.md](AGENTS.md) | RULES 是读者视图 |
| 固定契约、输出 schema、退出码、守卫线 | [BASELINE.md](BASELINE.md) | 代码与测试的契约来源 |
| 文档归属、取代关系与引用规则 | [docs/INDEX.md](docs/INDEX.md) | 本页只给高层导航 |
| 产品定位、能力清单与适用边界 | [docs/01-overview/README.md](docs/01-overview/README.md) | README 只留摘要 |
| 分层组件、模块职责、数据流与架构局限 | [docs/02-architecture/README.md](docs/02-architecture/README.md) | DEVELOPMENT 只讲开发操作 |
| 决策理由与历史裁定 | [docs/DECISIONS.md](docs/DECISIONS.md) | 只追加 |
| 当前状态快照 | [docs/PROGRESS.md](docs/PROGRESS.md) | 历史看两份 HISTORY |
| 版本与路线历史 | [docs/BASELINE-HISTORY.md](docs/BASELINE-HISTORY.md)、[docs/ROADMAP-HISTORY.md](docs/ROADMAP-HISTORY.md) | 只增不改 |
| 排障与坑台账 | [docs/05-troubleshooting/README.md](docs/05-troubleshooting/README.md) → `retro/pitfalls.json` | 入口导航，台账为机器真值 |
| 命令使用、配置与发布操作 | [docs/06-operations/README.md](docs/06-operations/README.md)、[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 06 管命令面，DEVELOPMENT 管开发流程 |
| 开源依赖与上游跟踪 | [docs/06-operations/开源依赖与上游跟踪.md](docs/06-operations/开源依赖与上游跟踪.md) | pyproject/uv.lock 管声明与锁定 |
| 路线、待办与每轮检查单 | [docs/ROADMAP.md](docs/ROADMAP.md)、[retro/next-round.md](retro/next-round.md) | next-round 是 D7 待办唯一源 |
| 术语 | [docs/GLOSSARY.md](docs/GLOSSARY.md) | 定义指针，不复述正文 |

## 贡献与许可证

**内部项目**：无 LICENSE，不附带任何使用、修改或分发授权。
提交遵循 Conventional Commits；每轮以 `round-gate` 开局/收官，以 `release-gate` 签核。
提交前运行文档结构、文档新鲜度、凭据扫描、许可证检查与全量回归。

- 我要加依赖：先读 [开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md) 与 `licenses.json`。
- 我要排障：先查 [docs/05-troubleshooting/README.md](docs/05-troubleshooting/README.md) 与 `retro/pitfalls.json`。
- 我要改文档：先改唯一权威，再修索引和引用；无效文件直接删除，不建归档占位。