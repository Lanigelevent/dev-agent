# dev-agent · 治理先行的代码智能体

[![Version](https://img.shields.io/badge/version-2.105.0-green.svg)](.zcode-plugin/plugin.json)
[![CI](https://github.com/Lanigelevent/dev-agent/actions/workflows/self-check.yml/badge.svg)](https://github.com/Lanigelevent/dev-agent/actions/workflows/self-check.yml)
[![License](https://img.shields.io/badge/license-%E6%9C%AA%E6%8E%88%E4%BA%88%E5%BC%80%E6%BA%90%E8%AE%B8%E5%8F%AF-lightgrey.svg)](#贡献方式与许可)

**版本 2.105.0** ｜ Python 治理壳 **≥3.11，纯标准库** ｜ 引擎层 **3.12 `.venv`** ｜ Windows / Linux

> **创建日期**：2026-10-24 ｜ **当前状态**：维护中
> **所有者**：总监 + 迭代官 ｜ **主导模式**：参考
> **权威范围**：项目介绍、定位与边界、快速开始、架构摘要、使用入口与文档地图
> **不是权威**：固定契约 [BASELINE.md](BASELINE.md)、硬约束 [AGENTS.md](AGENTS.md)、
> 开发流程 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)、命令风险 [docs/06-operations/README.md](docs/06-operations/README.md)
> **复核期限**：2026-12-31 ｜ **上次复核**：2026-11-26

> **一句话**：把「AI 审查代码」变成一条可检查、可签字、可回滚的流水线——diff 进入后依次完成
> 意图解析、风险评分、多维审查、证据核验与报告；发现可继续走工单 → 补丁 → 人工批准书 → 五道闸 → 行为回归，
> 任一写入验证失败自动回滚。技术上是一套 Python 治理壳 + 复用引擎适配层 + 无头 MCP 服务器（stdio），
> 评审、修复、审核、复盘、发布全链路都有机器可复算的证据。

**English TL;DR** — a governance-first code agent: every review conclusion is backed by reproducible
evidence; every patch to the reviewed repository requires an approver's signed authorization and passes
five gates plus behavior regression; failures roll back. Ships 13 skills / 93 scripts, 16 MCP tools,
a deterministic 38-rule review arm, and SWE-bench / ReviewBench evaluation drivers with honest sample
denominators and partial-caliber accounting.

---

## 目录

- [当前状态](#当前状态)
- [它解决的具体问题](#它解决的具体问题)
- [我要用它（使用者）](#我要用它使用者)
- [我要改代码（开发者）](#我要改代码开发者)
- [架构与模块职责](#架构与模块职责)
- [关键设计决策（ADR）](#关键设计决策adr)
- [配置、数据落点与环境变量](#配置数据落点与环境变量)
- [数据与安全](#数据与安全)
- [质量门禁与它的边界](#质量门禁与它的边界)
- [已知限制](#已知限制)
- [CI、签名与交付现状](#cisigning--交付现状)
- [排障速查](#排障速查)
- [发版与版本口径](#发版与版本口径)
- [文档地图](#文档地图)
- [贡献方式与许可](#贡献方式与许可)

**按角色选读**：
- **要用它** → [它解决的具体问题](#它解决的具体问题) → [我要用它（使用者）](#我要用它使用者) → 需要时看 [排障速查](#排障速查)
- **要改它** → [我要改代码（开发者）](#我要改代码开发者) → [架构与模块职责](#架构与模块职责) → [关键设计决策（ADR）](#关键设计决策adr)
- **要评估它** → [数据与安全](#数据与安全) + [质量门禁与它的边界](#质量门禁与它的边界) + [已知限制](#已知限制)

---

## 当前状态

各现值为时点快照，**漂移时以代码与 CI 为准**；「权威出处」指向可重算的落点，禁止抄静态数字：

| 维度 | 现值 | 权威出处 |
|---|---|---|
| 版本号（唯一源） | `2.105.0` | [.zcode-plugin/plugin.json](.zcode-plugin/plugin.json)；`pyproject.toml` / MCP `serverInfo.version` / 本页 / [BASELINE.md](BASELINE.md) 同步 |
| 契约测试 | **894 项**（892 passed + 2 skipped） | `python -m unittest discover -s tests`；最近实跑 `logs/suite-r238-run1.log`（`logs/suite-r238-run1.log`） |
| 治理壳 | **13 个技能 × 93 个脚本** | `skills/`，计数由 `doc-freshness.py` 对账 |
| MCP 服务器 | **16 个工具**（含异步 `submit/status/cancel/purge`） | `mcp/review_mcp.py`，stdio JSON-RPC 2.0（协议 2025-06-18） |
| 引擎矩阵 | Ruff **973/482/250**、ast-grep **29/2/2**、LibCST **2/2/2** | `engines/*-matrix.json`，落盘产物逐项比对 |
| 坑台账 | **273 条，open 6 / closed 243 / archived 24** | `retro/pitfalls.json`，`retro-ledger.py` 机械维护 |
| 评审精度基线 | ReviewBench deterministic precision **0.6667**（地板 0.65，n=12 小样本） | `skills/eval-harness/precision-baseline.json` |
| 评测口径 | agent 侧 **20/20**；对外硬规则臂 **0.42%**；宿主评审臂 **unavailable**（n=1000 recall=0，D-053 归因）；部分口径与 blocked 单列 | [docs/PROGRESS.md](docs/PROGRESS.md)、[docs/DECISIONS.md](docs/DECISIONS.md) |
| 最近发布 | tag `v2.101.0` 已签发；release-gate 七项全绿 | `reports/release-gate/2.101.0/release-gate.json` |
| 许可 | **未授予开源许可**（公开可见不等于可再分发） | 见本页末节 |

> 本页只放常青口径与当前快照，不维护逐版流水、当轮踩坑和机器现场。版本沿革见
> [docs/BASELINE-HISTORY.md](docs/BASELINE-HISTORY.md)，路线与逐轮记录见
> [docs/ROADMAP-HISTORY.md](docs/ROADMAP-HISTORY.md)，当前值与命令现取方式见
> [docs/PROGRESS.md](docs/PROGRESS.md)。

---

## 它解决的具体问题

普通 AI 代码评审的问题不是「给不出意见」，而是**结论不能用于决策**。本项目把三件反复出错的事变成可核对动作：

1. **「这条结论的证据在哪？」**——确定性规则只输出脱敏后的可复现事实（38 条硬规则、11 类边界形态、跨文件污点）；LLM 意见与机械事实分源，七要素 findings 经 `findings-check.py` 校验后才进报告。
2. **「补丁能不能落、会不会破坏模块？」**——补丁先行只写产物目录；落盘必须持审核人批准书（sha256 绑定补丁字节），过五道闸后逐文件重扫原规则消失且无新增，并跑仓库测试；任一失败自动回滚。
3. **「评审者与批准者是同一个模型吗？」**——RACI 固定唯一签字人，提案人 ≠ 批准人；修复分支永不自动合并；发布 tag 由人工签发，脚本只做只读发布闸。

一次典型使用（全部在本地，确定性路径无需 LLM key）：

1. 启动评审：`runner.py --repo <目标仓库> --range main..feature`；
2. 读报告：结论按严重度降序，每项带定位、证据、原因、修复步骤与证据等级；
3. 若要修：评审发现 → 审核人工单 → 补丁 → 五项核验批准书 → `fix-apply.py` 五道闸落盘 → 行为回归。

> **设计内分支（不是失败）**：不配 LLM key 时只有确定性评审链可用；宿主文件协议在 SWRBench 语料上
> n=1000 全空响应、recall=0，按 D-053 归因为执行质量无保障，对外标 unavailable；语料缺失、环境失败、
> `blocked` 与 `NEED_HUMAN` 均显式记录，不冒充能力失败或 resolved。

---

## 我要用它（使用者）

前置：治理壳 Python **≥3.11（纯标准库）**；引擎层与全量测试用项目 `.venv` 的 Python **3.12**；
依赖锁定用 `uv`。确定性评审链不需要 LLM key；SWE-bench 类评测另需镜像/语料，见
[docs/06-operations/使用说明与配置.md](docs/06-operations/使用说明与配置.md)。

### 路线 A · 只读评审（CLI）

```bash
git clone https://github.com/Lanigelevent/dev-agent.git
cd dev-agent
uv sync
python skills/orchestrator/scripts/runner.py --repo <目标仓库> --range main..feature
# 硬规则快扫：.venv/Scripts/python.exe skills/multi-agent-review/scripts/deterministic-rules.py --help
```

### 路线 B · MCP stdio（客户端拉起，进程边界即信任边界）

```bash
.venv/Scripts/python.exe mcp/review_mcp.py
```

MCP 客户端配置：

```json
{
  "mcpServers": {
    "dev-agent": {
      "command": ".venv/Scripts/python.exe",
      "args": ["mcp/review_mcp.py"]
    }
  }
}
```

工具面：同步评审/快扫/规划/反馈/审核/修复/落盘/复盘/调度/测试生成/编码/重构（12 条）+ 异步作业
`code_review_submit` / `code_review_status` / `code_review_cancel` / `code_review_purge`（4 条）。
作业产物经 `review://jobs/{job_id}` 与 `review://jobs/{job_id}/ledger` 只读资源拉取。

### 路线 C · 全量验证与评测

```bash
# 全量契约（Windows/Linux）
.venv/Scripts/python.exe -m pytest tests -n 2 -q
# 单项门禁与现取快照
.venv/Scripts/python.exe skills/self-iteration/scripts/doc-freshness.py --format text
.venv/Scripts/python.exe skills/self-iteration/scripts/release-gate.py --only version_sync
```

评测驱动见 `skills/eval-harness/scripts/`（SWE-bench gold / agent / Pro / Live、DeepSWE、
ReviewBench、SWRBench、CVEfixes、精度与成本归一）；所有结论都带样本量、判分桥、blocked 与部分口径。

---

## 我要改代码（开发者）

```bash
.venv/Scripts/python.exe -m pytest tests -n 2 -q             # 全量契约 + 反向验证
.venv/Scripts/python.exe skills/self-iteration/scripts/session-probe.py --root .   # 开局探针
.venv/Scripts/python.exe skills/self-iteration/scripts/doc-freshness.py --format text  # 计数/版本漂移
.venv/Scripts/python.exe skills/self-iteration/scripts/secret-scan.py --root .      # 凭据形态
.venv/Scripts/python.exe skills/self-iteration/scripts/license-check.py --root .    # 依赖许可证
.venv/Scripts/python.exe skills/self-iteration/scripts/release-gate.py --only version_sync  # 版本六处同步
```

提交使用 Conventional Commits；结构性变更（治理壳依赖口径、写入通道、工具契约、安全模型）先立 ADR
并记入 [docs/DECISIONS.md](docs/DECISIONS.md)。行为级优化必须过反向验证与精度基线；
新依赖须经总监批准并登记 `pyproject.toml` 与
[开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md)。
开发流程、双跑与轮次收官见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

---

## 架构与模块职责

```text
治理壳（Python ≥3.11，纯标准库；零依赖可分发）
  skills/   13 个技能 × 93 个脚本：评审 / 修复 / 审核 / 迭代 / 总监 / 门禁
  mcp/      stdio JSON-RPC 2.0 服务器，16 工具 + jobs 资源
  llm/      OpenAI 兼容端点 + 宿主文件协议（key 只走环境变量）
引擎层（项目 .venv，Python 3.12；按许可证白名单引入）
  engines/  Ruff / LibCST / ast-grep 适配器 + testgen
  agent/    仓库地图 / 编辑格式 / 编码循环 / trace / SWE-bench 编排
被审仓库写入口
  repair/scripts/fix-apply.py  批准书 → 五道闸 → 行为回归 → 失败自动回滚
```

依赖方向单向：治理壳 → 引擎层（一律 subprocess + JSON）；任何对被审仓库的写入都收敛到
`fix-apply.py`。评审链：意图 → 取数 → 评分 → 并行审查 → 流式核验 → 多轮查证 → 反向验证 → 汇总；
修复链：工单 → 补丁 → 批准书 → 五道闸 → 回归。分层细节与架构局限见
[docs/02-architecture/README.md](docs/02-architecture/README.md)。

---

## 关键设计决策（ADR）

| 决策 | 一句话结论 |
|---|---|
| 唯一落盘入口（D-001） | 写被审仓库只经 `fix-apply.py` 五道闸，失败自动回滚 |
| 分层依赖（D-002 / 硬约束 1） | 治理壳零依赖；MPL 仅 test-only，LGPL 仅 subprocess，GPL 禁入 |
| 评审精度护栏（D-042） | 固定语料 precision ≥0.65 + 基线趋势，语料不入库 |
| 精度归因修正（D-053） | 宿主全空响应归因为执行质量无保障，不是协议缺陷；对外只报硬规则臂 0.42% |
| 发布边界（D-035） | 人工在 main 打 `v<version>` 附注 tag 是唯一发布动作，release-gate 七项全绿才签发 |
| 挂死护栏（D-041 / D-052） | 300s 转观测、600s 为硬挂死判红线，升级触发线 540s（双跑中位口径） |
| 分层套件（D-049） | CI/PR 跑 smoke，发布闸与 nightly 跑 full |
| 数字现取（通用纪律） | 会变化的数值只给可重跑命令，不手抄进文档 |
| 单一事实源（通用纪律） | 同一事实只在一处定义，其他位置只放指针 |
| 双向验证（通用纪律） | 修复须证明新行为生效且旧问题可复现（或行为差异） |
| 归档非删除（通用纪律） | 过期内容移入归档区并注明日期，不直接丢弃 |

完整决策、状态与提案见 [docs/DECISIONS.md](docs/DECISIONS.md)；硬约束与维护红线见
[AGENTS.md](AGENTS.md)。

---

## 配置、数据落点与环境变量

- 运行参数单一事实源：`agent.json` 的 `args`，脚本经 `manifest_args.py` 读取；
  六处版本真值同步由 `bump-version.py` 落盘。
- 数据落点：`runs/`（作业、断点、账本）、`reports/`（入仓证据 + gitignored `_work/` 临时产物）、
  `datasets/`（gitignored 评测语料与缓存，当前约 6.6 GB）、`retro/`（台账与轮报）。
  清理历史运行产物不得删受控证据。
- 镜像与模型权重下载：先联网实测国内源，按硬约束 8 跑 `docker-mirror-probe.py`，慢即判死。

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `CRA_LLM_PROVIDER` | LLM 后端：`host` / `openai` / `none` | `host` |
| `REVIEW_LLM_BASE_URL` | OpenAI 兼容端点（仅公网 https 或本地回环） | 空 |
| `REVIEW_LLM_API_KEY` | 端点密钥，只走环境变量，不进产物 | 空 |
| `REVIEW_LLM_MODEL` | 模型名 | 空 |
| `REVIEW_LLM_JSON_MODE` | 请求 JSON response format | 关闭 |
| `CRA_MEMORY_FILE` | few-shot 记忆文件（默认关闭） | 关闭 |
| `CRA_TEST_IMAGE` | 容器档测试镜像 | 未设置则跳过真机用例 |
| `PYTHONUTF8` / `PYTHONIOENCODING` | Windows 解码基线 | 套件链通常置空 |

完整配置与风险档见 [docs/06-operations/README.md](docs/06-operations/README.md) 与
[docs/06-operations/使用说明与配置.md](docs/06-operations/使用说明与配置.md)。

---

## 数据与安全

| 保证 | 实现机制 | 权威定义 |
|---|---|---|
| 写入必须批准 | 工单 → `approval.json`（sha256 绑定补丁） → `fix-apply.py` | [AGENTS.md](AGENTS.md) 硬约束 7 |
| 五道闸 | 批准书、干净工作树、HEAD 与 base_sha、`git apply` 预检、行为回归 | [BASELINE.md](BASELINE.md) |
| 失败自动回滚 | 落盘前预检 + 验证失败 `ROLLED_BACK`（落 apply-log） | `skills/repair/scripts/fix-apply.py` |
| 提案与批准分离 | RACI 唯一 A；任何一方不得自审自批 | `skills/director/org.json` |
| 凭据零明文 | 命中密钥形态的 snippet 脱敏为 `<redacted>` | [AGENTS.md](AGENTS.md) 硬约束 5 |
| 网络白名单 | LLM 端点仅公网 https / 本地回环，重定向逐跳复验，响应体上限 | `llm/provider.py` |
| 依赖合规 | MIT/Apache/BSD 可 import；MPL test-only；LGPL subprocess；GPL 禁入 | `license-check.py`、[BASELINE.md](BASELINE.md) |
| 审计链 | 统一事件账本 JSONL + sha256 哈希链 + 发布闸证据 | `event-ledger.py`、`release-gate.py` |
| 评测信任边界 | 公开语料的 `setup_cmds` 只在被评测 worktree 内执行；环境失败不冒充任务失败 | `skills/eval-harness/scripts/` |

---

## 质量门禁与它的边界

- **机械事实**：38 条硬规则、11 类边界形态、跨文件污点；snippet 一律脱敏，diff 扫描禁止行首锚定。
- **评审闭环**：维度规划 + 并行审查 + 六问核验 + 高风险多轮查证 + hunk 覆盖 / 六视角反向验证。
- **工程门禁**：`session-probe` / `doc-structure` / `doc-freshness` / `secret-scan` / `license-check` /
  `coverage-gate` / `precision-gate` / `latency-bench` / `release-gate`。
- **行为回归**：修复后逐文件重扫原规则消失且无新增，并跑仓库测试；测试失败等同验证失败。
- **证据可复算**：日志 sha256 与 gate 记录对账；轮次收官追加事件账本 round-summary。

**未覆盖（诚实清单）**：
1. 宿主文件协议在 SWRBench 语料的能力宣称（n=1000 recall=0，标 unavailable，见 D-053）。
2. 任何 benchmark 观测值到通用代码评审能力的外推（只报 n 值、口径与判分桥）。
3. 真实厂商模型的服务质量（限流 / 拒答 / 成本）与 macOS 实测；公开 CI smoke 通过不等于全平台可用。
4. Docker / 远程 SSH 档的真机行为（本地只验证接口与假壳契约）。
5. 无第三方安全审计；本项目不提供通用 SLA。

三条红线：**不改判据换绿**、**不静默吞审查失败**、**不把观测或样本上限说成能力**。

---

## 已知限制

每条都注明**怎么核**与性质（设计内未启用 / 外部前提 / 真实缺陷）：

| 限制 | 性质 | 怎么核 |
|---|---|---|
| 不自动合并修复分支、不允许无批准书写入 | 设计内 | 看 `fix-apply.py` 五道闸与批准书 sha256 绑定 |
| 宿主评审臂对外不可用 | 设计内 | `swrenbench-import.py judge` n=1000 recall=0 + D-053 归因 |
| 评测结论 n≤20 不外推能力上限 | 设计内 | `docs/02-architecture/README.md` 信任边界 |
| Docker / 远程 SSH 需目标环境 | 外部前提 | `--workspace container:<image>` / `remote:<target>` 真跑 |
| 公开语料缺失时跳过并标注 | 外部前提 | 评测脚本 code=2 + `blocked_source` 保留样本 |
| 真实 LLM 端点行为靠实跑观察 | 外部前提 | 白名单校验不能替代模型评测 |
| Windows 大段中文宿主编辑可能静默失效 | 真实缺陷/绕行 | 脚本补丁 + 锚点 count==1 + 读回验证（坑 daf1a5fc2f9f） |
| 公开可见但未授予开源许可 | 真实边界 | 见末节，不把可见性当授权 |

---

## CI、签名与交付现状

- GitHub Actions：push / PR 跑 smoke 与基础门禁；nightly 跑全量、CVE、覆盖率与延迟 SLO；
  矩阵 ubuntu / windows × Python 3.11 / 3.12 / 3.13（见 [self-check.yml](.github/workflows/self-check.yml)）。
- 发布闸 `release-gate.py` **只读**：版本六处同步、文档真值、秘密、许可证、双跑、干净树与 tag 预检七项全绿才放行；它不打 tag、不推送。
- tag 由人工在 main 上签发（`v<version>` 附注 tag）；当前 `v2.101.0`，证据入仓
  `reports/release-gate/2.101.0/release-gate.json`。
- 不解决什么：不做自动发版到包管理器、不做 tag 自动发布、不自动合并功能分支。

---

## 排障速查

| 症状（原话） | 动作 |
|---|---|
| cp936 / UnicodeDecodeError 在 Windows 套件里出现 | 以 `PYTHONUTF8= PYTHONIOENCODING=` 置空前缀运行（坑 8cfbcaf7d227；探针已内建净化） |
| `git apply` 失配 / 补丁落不进 | 补丁文件必须 LF，CRLF 会失配（坑 bb6ebd590d5e） |
| Mimosa 提交闸拦第三方克隆 | 评测数据先移出工作区，分三次独立调用：移出 → 提交 → 移回（坑 022913d6c6a4） |
| 大段中文用宿主 Edit/Write 改了没生效 | 脚本补丁 + 锚点 count==1 + 读回验证，禁止 `git checkout` 当复位（坑 daf1a5fc2f9f） |
| Docker Desktop 找不到 | 按 `swe_run.py find_docker`：显式 > PATH > `%LOCALAPPDATA%\Programs\DockerDesktop` |
| 整目录移动后 `.venv` 脚本失效 | `uv pip install --reinstall <包>` 修 uv trampoline |
| Gitee 镜像 401 | 不是所有上游都有 Gitee 镜像；逐仓验证，失败走预构建或记录降级 |
| release-gate 版本不可复用 | tag 已签则必须升版本号；README/BASELINE 沿革同步 |
| 双跑偶发红 | 先查是否并发清理/机器负载，再同树复跑；失败日志留档，不绕闸 |
| 语料缺失或 code=2 | 评测脚本如实报 `blocked` / `unavailable`，不伪造 PASS |

### 常见问题（FAQ）

1. **需要真实模型 Key 吗？** 确定性评审链不需要；宿主/LLM 臂与报告生成需要你自己的端点。
2. **能直接自动合并修复吗？** 不能，修复分支永不自动合并，落盘必须人工批准书 + 五道闸。
3. **SWRBench 的 0.42% 是什么？** 38 条硬规则臂的 point_recall（3/713），是唯一对外数字；宿主臂 unavailable。
4. **评测数字会被编造吗？** 必须带 n 值、判分口径、blocked 与部分口径；样本上限不外推能力。
5. **Windows / Linux 都支持吗？** 双平台矩阵在册；Docker / 远程档需目标环境，本地只验证接口契约。

---

## 发版与版本口径

- 版本单一源：`.zcode-plugin/plugin.json` 的 `version`；`pyproject.toml` / MCP `serverInfo.version` /
  本页头条 / [DEVELOPMENT.md](docs/DEVELOPMENT.md) / [BASELINE.md](BASELINE.md) 六处同步。
- 逐版变更与过程证据见 [docs/BASELINE-HISTORY.md](docs/BASELINE-HISTORY.md) 与
  [docs/ROADMAP-HISTORY.md](docs/ROADMAP-HISTORY.md)；本页不维护逐版流水。
- 当前版本 `2.105.0`；tag 由人工签发，release-gate 只做只读签核。

---

## 文档地图

| 文档 | 内容 |
|---|---|
| [docs/01-overview/README.md](docs/01-overview/README.md) | 能力清单与适用场景 |
| [docs/02-architecture/README.md](docs/02-architecture/README.md) | 分层、数据流、架构局限 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADR 与提案状态 |
| [docs/PROGRESS.md](docs/PROGRESS.md) | 当前状态与计数快照 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 环境、测试、轮次收官 |
| [docs/06-operations/README.md](docs/06-operations/README.md) | 命令、配置、风险档 |
| [docs/06-operations/开源依赖与上游跟踪.md](docs/06-operations/开源依赖与上游跟踪.md) | 依赖与许可证跟踪 |
| [docs/05-troubleshooting/README.md](docs/05-troubleshooting/README.md) | 排障与坑台账入口 |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | 术语 |
| [docs/INDEX.md](docs/INDEX.md) | 文档权威映射 |
| [BASELINE.md](BASELINE.md) | 固定契约与评测口径 |
| [AGENTS.md](AGENTS.md) | 主流程、硬约束、维护红线与组织 |

---

## 贡献方式与许可

开发与提交流程见 [CONTRIBUTING.md](CONTRIBUTING.md)（环境搭建、本地验证、提交规范与治理边界）；
行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)；安全漏洞请勿走公开 issue，报告渠道见
[SECURITY.md](SECURITY.md)。提交使用 Conventional Commits；提交前按「我要改代码」一节跑门禁与反向验证；
结构性改动先立 ADR，新依赖先批准再登记 `pyproject.toml` 与许可证跟踪。

本项目当前为**内部项目公开可见，但未授予任何使用、修改或分发许可**。公开可见不等于获得授权；
未经所有者书面许可，不得将本项目代码用于再分发或商业用途。运行时依赖的许可证与使用范围见
[开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md)，依赖声明以 `pyproject.toml` 为准，
解析版本以 `uv.lock` 与 `requirements-lock.txt` 为准。

## 参考与致谢

工程方法上参考 SWE-agent 的 ACI 设计、Aider 的仓库地图与编辑格式、OpenHands 的事件流、
Ruff / LibCST / ast-grep 的引擎能力，以及 SWE-bench、DeepSWE、ReviewBench、SWRBench 等公开评测工作。
外部项目的准确版本与许可证以 [开源依赖与上游跟踪](docs/06-operations/开源依赖与上游跟踪.md) 与
`license-check.py` 为准。
