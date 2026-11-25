# dev-agent

> **治理先行的代码智能体**：把「AI 审查代码」变成一条可检查、可签字、可回滚的流水线。
> diff 进入后依次完成意图解析、风险评分、多维审查、证据核验与报告；发现可继续走
> 工单 → 补丁 → 人工批准书 → 五道闸 → 行为回归，任何写入失败自动回滚。
>
> 项目同时提供测试生成、编码循环、SWE-bench 系列评测驱动，以及一套覆盖评审、
> 修复、审核、复盘和发布的可执行治理设施。

> **创建日期**：2026-10-24 ｜ **当前状态**：维护中
> **所有者**：总监 + 迭代官 ｜ **主导模式**：参考
> **权威范围**：项目介绍、定位与边界、快速开始、总体架构摘要、使用入口与文档地图
> **不是权威**：固定契约 [BASELINE.md](BASELINE.md)、硬约束 [AGENTS.md](AGENTS.md)、
> 开发流程 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、命令风险 [docs/06-operations/README.md](docs/06-operations/README.md)
> **复核期限**：2026-12-31 ｜ **上次复核**：2026-11-25

**版本 2.99.0** ｜ Python 治理壳 **≥3.11，纯标准库** ｜ 引擎层 **3.12 `.venv`** ｜
Windows / Linux ｜ GitHub Actions smoke CI 通过

## 当前状态

| 维度 | 当前值 | 权威来源 |
|---|---|---|
| 契约测试 | **848 项**（845 passed + 3 conditional skip） | `unittest discover -s tests` |
| 最近全量 | **550.02 秒**，低于 600 秒硬护栏 | `logs/suite-r221-run1.log` |
| 治理壳 | **13 个技能 × 90 个脚本** | `skills/` |
| MCP 服务器 | **16 个工具** | `mcp/review_mcp.py` |
| 引擎矩阵 | Ruff **973/482/250**；ast-grep **29/2/2**；LibCST **2/2/2** | `engines/*-matrix.json` |
| 坑台账 | **266 条，open 0** | `retro/pitfalls.json` |
| 评审精度 | ReviewBench deterministic precision **0.6667**（地板 0.65） | `skills/eval-harness/precision-baseline.json` |
| 评测口径 | agent 侧 **20/20**；对外硬规则臂 **0.42%**；部分口径与 blocked 单列 | [docs/PROGRESS.md](docs/PROGRESS.md) |

> 当前值以 [docs/PROGRESS.md](docs/PROGRESS.md) 为准；版本沿革见
> [docs/BASELINE-HISTORY.md](docs/BASELINE-HISTORY.md)，路线与逐轮记录见
> [docs/ROADMAP-HISTORY.md](docs/ROADMAP-HISTORY.md)。

## 问题与设计原则

普通 AI 代码评审的常见问题不是「一句意见都给不出」，而是**结论不能用于决策**：

- 只指出问题，不给可复现证据；
- 生成了补丁，但无法证明补丁可应用、不会破坏模块；
- 评审者与批准者是同一个模型或同一个人；
- 报告说「通过」，却没有测试、回归或安全边界证据；
- 评测只看 benchmark 分数，不记录样本量、成本、部分口径与失败归因。

本项目针对这些问题采用五条原则：

1. **先取证再结论**：确定性规则只输出可复现事实，LLM 意见与机械事实分源。
2. **补丁先行、人工签字**：修复补丁只写产物目录；写入被审仓库必须持审核人批准书。
3. **唯一落盘入口**：所有机械补丁、引擎修复和编码循环编辑统一经 `fix-apply.py`。
4. **失败如实**：降级、blocked、部分口径、环境失败与 `NEED_HUMAN` 都显式记录。
5. **数字可复算**：报告必须带样本量、分母、成本与失败归因，不把观测当因果。

## 能力边界

**适合**：

- 内部代码仓库的 PR 前评审与安全返修分诊；
- 需要「补丁一定经过审批与行为回归」的修复流程；
- 需要离线、可复现、可审计的代码评审流水线；
- 需要失败归因与成本记录的代码智能体评测。

**不适合**：

- 希望 AI 直接、自动合并生产代码的场景；
- 不设审核人的全自动修复流程；
- 期望一次生成完整大型架构改造的任务；
- 将 benchmark 观测值直接外推为通用能力结论的场景。

**明确不做**：

- 不自动合并修复分支；
- 不绕过五道闸写被审仓库；
- 不在没有反向验证和精度基线的情况下改评分口径或阈值；
- 不把厂商自报数字或未复跑的基准当成本项目能力。

## 核心治理保证

| 保证 | 实现机制 | 权威定义 |
|---|---|---|
| 写入必须批准 | 工单 → `approval.json`（sha256 绑定补丁字节） → `fix-apply.py` | [AGENTS.md](AGENTS.md) 硬约束 7 |
| 五道闸 | 批准书、工作树干净、HEAD 与 base_sha 一致、`git apply` 预检、行为回归 | [BASELINE.md](BASELINE.md) |
| 任一步失败自动回滚 | 落盘前预检 + 失败回滚并记录 `ROLLED_BACK` | `skills/repair/scripts/fix-apply.py` |
| 提案与批准分离 | RACI 固定 A 唯一；任何一方不得自审自批 | `skills/director/org.json` |
| 凭据零明文 | 命中密钥形态的 snippet 一律 `<redacted>` | [AGENTS.md](AGENTS.md) 硬约束 5 |
| 依赖合规 | MIT/Apache/BSD 可 import；MPL 仅 test-only；LGPL 仅 subprocess；GPL 禁入 | `license-check.py`、[BASELINE.md](BASELINE.md) |
| 报告可审计 | 统一事件账本 + JSONL 哈希链 + 发布闸证据 | `event-ledger.py`、`release-gate.py` |

## 总体架构

```text
┌─ 治理壳（Python ≥3.11，纯标准库）─────────────────────────────┐
│ skills/  评审 / 修复 / 审核 / 迭代 / 总监 13 个技能 × 90 脚本 │
│ mcp/     JSON-RPC 2.0 stdio 服务器，16 个工具                   │
│ llm/     OpenAI 兼容端点 + 宿主文件协议                         │
└───────────────────────────┬────────────────────────────────────┘
                            │ subprocess + JSON（唯一跨层通道）
┌─ 引擎层（项目 .venv，Python 3.12）────────────────────────────┐
│ engines/ Ruff / LibCST / ast-grep 适配器 + 测试生成            │
│ agent/   仓库地图 / 编辑格式 / 编码循环 / trace / SWE-bench 编排│
└───────────────────────────┬────────────────────────────────────┘
                            │ 唯一写入入口
                  repair/scripts/fix-apply.py
                  批准书 → 五道闸 → 行为回归 → 失败回滚
```

详细分层、模块职责、数据流与架构局限见
[docs/02-architecture/README.md](docs/02-architecture/README.md)。

## 主要工作流

### 1. 评审

`intent-parse` → `preflight` → `edge-detect` → `deterministic-rules` → `score`
→ `dispatch-plan` → 多维并行审查 → `findings-check` → 高风险多轮查证
→ `coverage` / `perspective-scan` 反向验证 → `report-check` + `schema-check`。

确定性部分包含 11 类边界形态、38 条硬规则与跨文件污点分析；审查材料按函数体与
hunk 截窗，不把整棵仓库直接塞入上下文。

### 2. 修复

评审发现 → 审核人闸 1 签发工单 → 修复团队生成补丁 → 审核人闸 2 五项核验并签发
批准书 → `fix-apply.py` 过五道闸落盘 → 重扫原规则且无新增 + 仓库测试通过；
验证失败自动回滚。

### 3. 编码循环

`agent/code-task.py` 在独立 worktree 中执行 `read/list/search/edit/probe/done`：
按定义点取窗、SEARCH/REPLACE 唯一命中、修改后双语法校验、按改动选择测试子集，
失败回退全量；产出补丁经修复链落盘，不直接写被审仓库。

### 4. 测试生成

`engines/testgen.py` 支持确定性骨架、宿主 LLM 真用例、`pytest` 验证与新文件补丁。
生成物必须通过验证测试才算完成。

### 5. 评测

- SWE-bench gold / agent / Pro / Live 四类驱动；
- DeepSWE 113 任务解析与执行；
- ReviewBench / SWRBench 评审精度；
- 合成语料、CVEfixes 真实语料与成本归一；
- 每条结论记录样本量、判分口径、成本、blocked 与完整性告警。

## 快速开始

### 前置条件

- Python **≥3.11**：直接运行治理壳；
- Python **3.12**：运行引擎层、编码循环与全量测试；
- `uv`：依赖锁定与 `.venv` 创建；
- 不需要 LLM key：确定性评审链可离线运行；
- SWE-bench 类评测需要额外镜像/语料，按 [docs/06-operations/使用说明与配置.md](docs/06-operations/使用说明与配置.md) 配置。

### 安装

```bash
git clone https://github.com/Lanigelevent/dev-agent.git
cd dev-agent
uv sync
# 可选：安装 LGPL 子进程隔离组件
uv sync --extra isolated
```

### 只读评审

```bash
python skills/orchestrator/scripts/runner.py \
  --repo <目标仓库> --range main..feature
```

### 全量验证

```bash
.venv/Scripts/python.exe -m unittest discover -s tests
# 或并行
.venv/Scripts/python.exe -m pytest tests -n 2 -q
```

### MCP 服务器

```bash
python mcp/review_mcp.py
```

服务器使用 stdio JSON-RPC 2.0（协议 2025-06-18），提供 16 个工具，包含同步评审、
修复、审核、编码与异步 `submit/status/cancel/purge` 作业接口。

## 配置

运行参数单一事实源为 `agent.json` 的 `args`；脚本通过 `manifest_args.py` 读取。

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `CRA_LLM_PROVIDER` | LLM 后端：`host` / `openai` / `none` | `host` |
| `REVIEW_LLM_BASE_URL` | OpenAI 兼容端点 | 空 |
| `REVIEW_LLM_API_KEY` | 端点密钥，只走环境变量 | 空 |
| `REVIEW_LLM_MODEL` | 模型名 | 空 |
| `REVIEW_LLM_JSON_MODE` | 请求 JSON response format | 关闭 |
| `CRA_MEMORY_FILE` | few-shot 记忆文件 | 关闭 |
| `CRA_TEST_IMAGE` | 容器档测试镜像 | 未设置则跳过真机用例 |
| `PYTHONUTF8` / `PYTHONIOENCODING` | 影响 Windows 解码基线 | 测试链通常置空 |

完整参数、风险档与配置说明见
[docs/06-operations/README.md](docs/06-operations/README.md) 与
[docs/06-operations/使用说明与配置.md](docs/06-operations/使用说明与配置.md)。

## 安全模型

- **唯一写入口**：`repair/scripts/fix-apply.py`；
- **批准书绑定**：批准书对补丁包做 sha256 绑定，补丁任何变动即作废重审；
- **分权**：提案人 ≠ 批准人；修复分支永不自动合并；
- **网络边界**：LLM 端点仅允许公网 HTTPS 或本地回环，重定向逐跳复验，响应体有上限；
- **凭据卫生**：token 只允许环境变量，产物中的敏感片段脱敏；
- **评测信任边界**：公开 SWE-bench 语料的 `setup_cmds` 只在被评测 worktree 内执行，
  环境失败不冒充任务失败；
- **依赖合规**：许可证三档校验，LGPL 组件禁止 import，GPL 禁入。

## 测试与质量门禁

| 门禁 | 作用 |
|---|---|
| 全量契约测试 | 848 项，含端到端、反向验证与临时 Git 仓库 |
| `session-probe.py` | 文档漂移、死代码、视角反向验证 |
| `doc-structure.py` | 文档元信息、链接、锚点、表格、登记、脚本 UTF-8 输出 |
| `doc-freshness.py` | 版本、计数、台账与文档真值对账 |
| `secret-scan.py` | 凭据形态扫描与脱敏 |
| `license-check.py` | 依赖许可证明细与三档白名单 |
| `coverage-gate.py` | 固定子集覆盖率基线与回归容差 |
| `precision-gate.py` | ReviewBench precision 下限与趋势 |
| `latency-bench.py` | scan 延迟 p95 SLO |
| `release-gate.py` | 版本同步、文档、安全、双跑与干净树签核 |

GitHub Actions 在 push/PR 上运行 smoke 与基础门禁；全量回归、CVE、覆盖率和
mcp-scan 等重检查按 nightly 执行。

## 评测与证据口径

- 对外只报告本项目实跑的数字与样本量；
- 部分口径（例如仅 F2P）单列，不折算为 resolved；
- `blocked`、`env_failed`、`setup_failed` 与环境问题不冒充能力失败；
- 补丁是否可应用、是否破坏模块、是否回归、是否命中目标测试分别归因；
- 本仓的 ReviewBench precision `0.6667` 是小样本观测，不外推为通用精度上限；
- SWE-bench gold 口径只验证评测管线，agent 侧口径验证编码循环产出的补丁。

## 已知限制

- 真实 LLM 端点的行为只能通过实跑观察，协议白名单不能替代模型评测；
- 宿主端到端评测样本量有限，结论不外推到任意模型或仓库；
- Docker / 远程 SSH 工作区需要目标环境，本地默认只验证接口与假壳契约；
- 部分评测依赖官方或外部语料，语料缺失时跳过并标注，不伪装通过；
- 本项目不提供通用 SLA，公开 CI 的 smoke 通过不等于所有平台或所有任务均可用；
- 当前仓库为内部项目公开可见，但**未授予开源许可证**，公开可见不等于获得使用、
  修改或分发授权。

## 目录结构

```text
agent/       编码循环、仓库地图、编辑格式、trace、SWE-bench 编排
engines/     Ruff / LibCST / ast-grep 适配器与测试生成
llm/         LLM provider（OpenAI 兼容 / 宿主协议）
mcp/         MCP stdio 服务器
skills/      13 个治理技能 × 90 个脚本
tests/       契约、端到端与反向验证
docs/        概述、架构、决策、进度、排障、运维、任务、记忆
reports/     评测、发布闸与审计证据
retro/       坑台账、轮报与下一轮检查单
```

## 开源依赖

本项目的运行时引擎、测试工具与子进程隔离组件均登记在
[开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md)，包含能力、使用范围、
GitHub 仓库、发布页、版本核对时间与跟进要点。依赖声明以 `pyproject.toml` 唯一为准，
解析版本以 `uv.lock` 与 `requirements-lock.txt` 为准。

## 文档导航

| 目标 | 文档 |
|---|---|
| 能力清单与适用场景 | [docs/01-overview/README.md](docs/01-overview/README.md) |
| 分层、数据流与架构局限 | [docs/02-architecture/README.md](docs/02-architecture/README.md) |
| 决策记录 | [docs/DECISIONS.md](docs/DECISIONS.md) |
| 当前状态 | [docs/PROGRESS.md](docs/PROGRESS.md) |
| 环境、扩展、测试与发布 | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| 命令、配置、风险档 | [docs/06-operations/README.md](docs/06-operations/README.md) |
| 开源依赖与上游跟踪 | [docs/06-operations/开源依赖与上游跟踪.md](docs/06-operations/开源依赖与上游跟踪.md) |
| 排障与坑台账 | [docs/05-troubleshooting/README.md](docs/05-troubleshooting/README.md) |
| 术语 | [docs/GLOSSARY.md](docs/GLOSSARY.md) |
| 文档权威映射 | [docs/INDEX.md](docs/INDEX.md) |
| 固定契约 | [BASELINE.md](BASELINE.md) |
| 主流程、硬约束与组织 | [AGENTS.md](AGENTS.md) |

## 贡献与许可

- 提交使用 Conventional Commits；
- 修改行为、契约、计数或文档权威前，先运行对应门禁与反向验证；
- 新依赖必须经批准、登记 `pyproject.toml`、更新许可证注册表和
  [开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md)；
- 公开仓接受问题报告和讨论，但**未授予任何使用、修改或分发许可**；
  未经所有者书面授权，不得将本项目代码用于再分发或商业用途。

## 参考与致谢

本项目在工程方法上参考了 SWE-agent 的 ACI 设计、Aider 的仓库地图与编辑格式、
OpenHands 的事件流、Ruff/LibCST/ast-grep 的引擎能力，以及 SWE-bench、DeepSWE、
ReviewBench、SWRBench 等公开评测工作。外部项目的准确版本、许可证和跟踪方式以
[开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md) 与 `license-check.py` 为准。