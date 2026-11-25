# 术语表（Glossary）

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：迭代官 ｜ **主导模式**：参考
> **权威范围**：见下方原始头注详述
> **不是权威**：术语指向实体本身的权威契约（→ BASELINE.md / AGENTS.md；决策裁定 → docs/DECISIONS.md；命令用法 → docs/06-operations/）；术语增删改裁定亦在 docs/DECISIONS.md
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 创建：2026-10-28 ｜ 状态：维护中 ｜ 权威范围：本项目专属词汇的**一句话定义**与
> 权威源指针。定义不展开细节——细节去「权威源」列指向的文件读。
> 新增术语时同步检查是否与既有术语冲突；同一术语禁止两处定义。

## 治理与流程

| 术语 | 定义 | 权威源 |
|---|---|---|
| 治理壳 | 只用 Python 标准库、零依赖可分发的一层（`skills/*/scripts`、`llm/`、`mcp/`） | AGENTS.md 硬约束 1；DEVELOPMENT §3 |
| 引擎层 | 允许白名单第三方依赖的一层（`engines/`、`agent/`），与治理壳只经 subprocess+JSON 通信 | 同上 |
| 五道闸 | 写被审仓库前必须全过的五道检查：批准书 / 工作树干净 / HEAD 与 base_sha 一致 / `git apply` 预检 / 行为回归；任一失败自动回滚 | AGENTS.md 硬约束 7；DEVELOPMENT §4 写权限与五道闸 |
| 批准书 | 审核人闸 2 签发的 `approval.json`，以 sha256 绑定补丁字节；补丁任何变动即作废重审 | `skills/approval/scripts/approve-patch.py`；BASELINE |
| 工单 | 审核人闸 1 签发的 `work-order.json`，修复团队只吃工单施工 | `skills/approval/scripts/approve-plan.py` |
| 自审自批 | 同一方既产出又批准；本项目明令禁止（RACI 中 A 唯一） | AGENTS.md 组织架构 |
| RACI / 签字权 | 每类交付物固定 R=执行 / A=唯一签字人 / C=咨询 / I=知会 | `skills/director/org.json` |
| SRE 错误预算 | 各团队可量化的超限阈值（修复回滚率、审核拒绝数、未结坑数、无链接案例数） | `skills/director/org.json`；`org-scorecard.py` |
| 整改冻结 | 某团队预算 EXCEEDED 后只修质量、不扩功能的状态 | `org-scorecard.py` 输出 `freeze_teams` |
| NEED_HUMAN | 退出码 1 的一种语义：流程无法自行收敛，转人工决策 | AGENTS.md 硬约束 3 |
| WAIT_HOST_LLM | LLM 未配置/不可用时的降级语义：确定性链路照常，LLM 意见缺席并如实标注 | BASELINE「LLM 提供者契约」 |
| 已证事实 | `deterministic-rules.py` 输出的确定性发现，与 LLM 意见分源标注 | `skills/multi-agent-review/scripts/deterministic-rules.py` |

## 评测与口径

| 术语 | 定义 | 权威源 |
|---|---|---|
| 口径（caliber） | 一个指标「怎么算」的固定约定：分母、样本范围、逐例选取规则、归档位置；口径不许人工累加 | `reports/swebench/*.caliber.json`；DECISIONS D-042 precision 护栏 / 评测报告归档 |
| gold 口径 | 用官方 gold 补丁跑 harness，只验证评测管线正确性，不代表 agent 能力 | `skills/eval-harness/scripts/gold-sample.py` |
| agent 侧口径 | 用编码循环产出的补丁送官方 harness 判定；逐例取最近一次判定，来源跑次可复算 | `agent-sample.py`；`code-review-agent.agent-diagnosis.json`（D-043） |
| 严格首跑 | 模型只见 issue 文本、不见 gold/test patch 的首次尝试 | DEVELOPMENT §10 SWE-bench 口径分两档 |
| 有效样本 | 能进入分母的样本（补丁可应用、基线可用等）；分母只用有效样本 | BASELINE「评测双指标契约」 |
| F2P / P2P | fail-to-pass（修复前失败、修复后应通过）与 pass-to-pass（不得回归）测试 | SWE-bench harness 术语；`agent/swe-workflow.md` |
| F2P_MISSED | 归因：补丁可应用且无回归，但目标测试仍未通过（语义未对齐） | `agent-sample.py` 归因；agent-diagnosis 文件 |
| PATCH_APPLY_FAILED | 归因：补丁无法应用到目标基线 | 同上 |
| PATCH_BROKE_MODULE | 归因：补丁使原本可导入的模块不可导入（本地/容器导入冒烟抓出） | `agent/code-task.py` 补丁自检 |
| REGRESSION | 归因：P2P 测试被补丁破坏 | agent-diagnosis 文件 |
| PLAN_FAILED | 归因：编码循环未能产出可用补丁计划 | 同上 |
| 合成基线 | `forward-bench.py synth` 生成的确定性语料基准；clean 误报 0、precision/recall 1.0 是回归下限 | DEVELOPMENT §7 测试与评测 |
| ReviewBench | 真实 Python PR 评审基准（12 例语料），跑确定性规则与宿主 LLM 双口径 recall/precision | `skills/eval-harness/scripts/reviewbench-*.py` |
| DeepSWE | 113 任务的原创 SWE 基准（Harbor 目录格式，5 语言）；gate 语料不入库，只入索引与基线 | `deepswe-fetch.py`；`reports/deepswe/` |
| canary GUID | 评测语料中的防污染标记，用于识别数据是否混入训练语料 | DeepSWE 数据说明；`doc-freshness.py` F8 |
| 项目指纹 | 对源码树内容计算的指纹；改 AGENTS/skills/agent.json args 任一内容必变 | `skills/eval-harness/scripts/fingerprint.py` |

## 编码循环与材料

| 术语 | 定义 | 权威源 |
|---|---|---|
| 材料包 | 派发给审查/编码角色的上下文集合：区域等级、评分、代码窗口、邻近测试、修复计划参考 | AGENTS.md 步骤 4；`material-check.py` |
| 邻近测试三路 | 找模块相关测试的三条映射：同名 → django 路径段 → 内容提及（C 路，已改「引用形状」谓词） | `agent/repo_map.py`；D-005 |
| C 路 | 邻近测试的「内容提及」路：要求完整点分路径或 `from 包 import 模块`，裸词提及不算 | 同上 |
| 候选补丁 | 编码循环每次成功 edit+测试后保存的补丁快照；收束时按四档排序择优交付 | `agent/code-task.py`；D-009 |
| provenance | 产物来源与可复算理由（候选排序依据、补丁来源、镜像降级原因等） | `agent/code-task.py` manifest |
| stale_patch | 收集器发现「最新版补丁为空」时打的标记：拒绝静默评旧版 | `agent-sample.py`；`patch-provenance.json` |
| 行为探针 | `--allow-probe` 打开后允许在动作面（容器/仓库）执行的一次性观测实验 | `agent/code-task.py`；round-34 报告 |
| 任务镜像 / `--probe-docker` | 被审仓库的官方评测镜像；本地依赖不齐时探针与导入自检改在容器内做 | `agent/swe_run.py`；`agent/code-task.py` |
| 稳定前缀 / 工具输出外置 / 历史压缩 | 上下文工程四件套之三：前缀循环外算一次、超长工具输出落盘只留摘要、history 超阈值压缩旧条目 | `agent/code-task.py`；README v1.43.0 段 |
| 记忆层 | `memory_retrieval.py`（TF-IDF+cosine few-shot）与 `compact-memory.py`（聚类合并+老化）；默认关闭 | `skills/retro/scripts/`；D-011 |
| 逐 span 埋点 | `agent/trace.py` 输出的 Langfuse 兼容 JSONL（trace/observation/session id + 耗时与 token） | `agent/trace.py` |

## 复盘与文档

| 术语 | 定义 | 权威源 |
|---|---|---|
| 坑台账 | `retro/pitfalls.json`：每条坑的编号、类别、现象、根因、对策、来源、状态、结案口径 | `skills/retro/scripts/retro-ledger.py` |
| 轮报 | 每轮生成的 `retro/round-<N>-report.md`：完成项、结案证据、未结明细、候选 | `retro-report.py` |
| 候选清单 | `round-<N>-candidates.md`：机器排序的下一轮改进候选 | 同上 |
| 结案三分类 | machine_checkable（抽得出可跑命令）/ human_conclusion（无命令但有复验条件+期限）/ weak_closure（缺信号） | `scripts/verify-closure-commands.py` 常量 |
| 数字现取 | 会变的数值必须写获取方式，禁止手抄；历史值须带「→/当时/原为/曾/上一轮/历史/沿革」标记 | `doc-freshness.py`；docs/INDEX.md 数字规则 |
| 单一权威源 | 同一事实只在一处定义，其他位置只放指针 | docs/INDEX.md「唯一权威映射」 |
| 过期即删除 | 失效、过期或被取代的文档直接删除并清引用；不新建归档目录、不保留占位；仍在使用的历史证据文件保留在唯一历史权威位置 | docs/INDEX.md「引用规则」 |
| 双向验证 | 证明新实现生效 **且** 能复现旧问题/证明行为差异 | AGENTS.md 维护红线 8；docs/INDEX.md「引用规则」 |
| 变异体 | 故意改坏实现以验证测试/检查器真的会转红的反例 | AGENTS.md 维护红线 6 |
| 假设三键 | intent-parse 的 `ambiguity`（落选解读）/`assumptions`（采用假设+代价）/`confirmations`（非阻塞待确认） | `intent-parse.py`；D-008 |
| 开局探针 | `session-probe.py` 的固定问题集；全绿=开工条件，有信号按 triage 处理 | AGENTS.md 步骤 0 |
| 检查单 | `retro/next-round.md`：人工维护的开局检查单与全项目待办唯一事实源；轮报不写它 | AGENTS.md 复盘节；D7 |
| 轮次闸（round-gate） | 轮次工作流机器闸：open 开局门（干净树+探针+对账）/ close 收官门（复盘产物+三方计数对账+下一轮指针+回填检查+双跑日志） | skills/self-iteration/scripts/round-gate.py |
| 文档结构判据（doc-structure） | 手册 §7.1 九条机器判据：元信息/链接/锚点/表格/登记/泛化链接词/跳级/占位符 + 扫描面下限护栏；S10 校验 Python 主入口脚本的 UTF-8 stdout 自防御 | skills/self-iteration/scripts/doc-structure.py |
| smoke 清单 | D-049 分层套件的 CI/PR 预注册测试子集（200 项；发布闸与 nightly 跑全量；每 20 轮 full 对账） | tests/smoke-manifest.json |
| era 适配表 | 被审仓 2020-2021 时代依赖在新解释器上的逐仓钉版与告警豁免记录（r81/r82/r94 增补） | datasets/swebench/live/gate-r94-batch.jsonl 各实例 setup_cmds/adaptation_note |
| host 协议（模型轴） | CRA_LLM_PROVIDER=host 的提示词文件进出协议（prompt.md 写入→宿主填 response.md→--resume 幂等续跑）；与 API 端点轴分开记账 | llm/provider.py；retro/next-round.md 第 55 条 |
| f2p_passed / f2p-only | 部分判分口径：F2P 全过即记 f2p_passed，P2P 未全跑不折算 resolved | BASELINE.md 评测双指标契约；live-sample.py |
| 分卷 | append-only 文档的沿革剥离：现行卷留真值+指针，沿革卷只增不改（BASELINE/ROADMAP/next-round 三处已分卷） | docs/INDEX.md 取代关系登记 |
| worktree 绝对路径 | git worktree add 的路径解析以 -C 目录为 cwd——一律用绝对路径，防嵌套进 repo | retro/pitfalls.json（round-94 坑） |
