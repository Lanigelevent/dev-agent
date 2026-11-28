# 优化路线：从「治理第一梯队」到「综合第一梯队」

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：总监 + 迭代官 ｜ **主导模式**：参考
> **权威范围**：见下方原始头注详述
> **不是权威**：当前计数快照（docs/PROGRESS.md）
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 创建：2026-10-28 ｜ 状态：维护中 ｜ 版本：v1.50.0 ｜ 更新触发：每轮收官回填
> 「已完成 / 偏差」，阶段目标变更需总监批准。
> 相关权威源：现状索引 `docs/PROGRESS.md`；短期待办 `retro/next-round.md`；
> 决策理由 `docs/DECISIONS.md`；架构与命令 `docs/DEVELOPMENT.md`。
> 本文是**方向与验收标准**的唯一权威源；不重复轮报细节，不替代 next-round。

## 1. 结论摘要

本项目在**治理、安全边界、可复现性**三件事上已经是行业第一梯队：
唯一写入口 + 五道闸 + 批准书 sha256 绑定 + 失败自动回滚、分层依赖白名单、
评审/修复分权（提案人 ≠ 批准人）、数字现取与反向验证纪律。这些在公开的
coding agent 产品里很少同时具备。

差距集中在三处：

1. **编码循环的工具面偏窄**：只有 read / edit / probe / done，没有搜索；
   仓库地图是「被引用次数排序」而非图排序，Python 单语言。行业基线
   （SWE-agent ACI、Aider repo map、OpenHands）都把「搜得到、看得准、
   改得稳」当作 agent 能力的核心，而不是模型能力的外挂。
2. **评测科学性不足**：只看 reward.txt 判分（上轮已改对），但不检查
   「补丁改了什么」；没有每任务成本/轮数/耗时；DeepSWE n=1；没有
   「测试通过 ≠ 可合并」的度量。行业已经证明：10 行 conftest 钩子可刷满
   SWE-bench；METR 人工复核显示约 50% 通过测试的 PR 不会被维护者合并。
3. **工程化与观测是第三梯队**：CI 不装依赖（引擎层测试在 CI 里不构成
   证据）、矩阵缺本地实际的 3.12、无超时/缓存；trace 只在编码循环里，
   评审流水线没有统一事件账本；成本/延迟没有被当成一等指标。

综合评分（0–5，本文自评，证据见 §3/§4）：

| 维度 | 分数 | 判断依据 |
|---|---|---|
| 治理与安全 | 4.8 | 五道闸、批准书绑定、分权、回滚、脱敏；缺少运行时沙箱的默认化 |
| 可复现性 | 4.3 | 快照/指纹/断点/幂等续跑；评测镜像离线补齐；CI 证据链待补 |
| 编码能力 | 3.2 | ACI 缺搜索（本轮补）、repo map 无图排序、无子代理分解 |
| 评测科学性 | 3.0 | 判分口径已对（reward）、完整性闸本轮补；n 小、无成本/合并率 |
| 工程化 / DX | 2.8 | CI 硬化本轮开始；无覆盖率门禁、无 secret/license 扫描 |
| 观测与成本 | 3.0 | JSONL trace + 进度帧；无统一事件账本与成本总账 |

目标不是「把分数刷到 5」，而是把**能力增长变成可验证、可复算、可审计**的
增长：每一轮至少一条主线前进，每条主张带反向验证与获取命令。

## 2. 方法与证据等级

- **观测**：本仓库命令实跑或文件原文（给 `file:line`）；可复算。
- **对标**：公开资料（文末来源）；厂商自测数字一律标注「自报」，与第三方
  复现数字分开。
- **推断**：基于上述两类做的判断，写「预期/推断」，不当事实。
- 行业数字只做**方向校准**，不做本项目能力宣称；本项目对外只报自己
  实跑的数字与样本量。

## 3. 行业对标：值得吸收的七件事

| # | 对标对象 | 他们的做法 | 我们的现状 | 吸收方式 | 来源 |
|---|---|---|---|---|---|
| 1 | SWE-agent（ACI） | 为模型设计少量、可预期、带护栏的工具：查看/搜索/编辑/执行，输出格式为模型优化 | 动作面 4 个，**无搜索**；read 取窗 3000 字；edit 唯一命中 | 本轮加 `search`（字面、有界、脱敏）；下一步加 `list` 与「只跑相关测试」 | [SWE-agent 论文页](https://hyper.ai/cn/papers/2405.15793) |
| 2 | Aider（repo map） | tree-sitter 建符号图 → 文件为节点、引用为边 → PageRank + 对话个性化权重 → 固定 token 预算 | `repo_map.py` 按 `total_refs` 排序，**无图、无个性化**；预算按字符粗截断 | 新增 `--rank graph`：构图 + 个性化 PageRank + 预算内选符号；默认仍用现路径 | [Aider repo map 机制](https://m.blog.csdn.net/gitblog_00417/article/details/151489226)、[token 预算](https://fast.io/resources/aider-token-limit/) |
| 3 | OpenHands | 事件流（Action/Observation）、确定性重放、不可变配置、工作区抽象、沙箱、子代理委派 | worktree + JSONL trace；无事件溯源/重放；probe 可选 Docker；无子代理 | 先把 trace 升级为「事件账本」并支持 replay 校验；子代理放到阶段 4 | [OpenHands 平台论文](https://hyper.ai/cn/papers/iclr__2025__OJd3ayDDoF)、[SDK 设计](https://baike.baidu.com/item/OpenHands/67237854) |
| 4 | CodeRabbit（评审） | 精度优先：每基准约 2 个误报；只看 diff，跨文件 bug 抓不到 | 七维派发 + 污点跨文件 + 双指标（recall/precision）；精度 0.667（规则）/0.75（宿主） | 保持「精度优先」；补跨文件证据链（调用方摘要） | [工具对比](https://www.jdon.com/94308-ai-code-review-tools-benchmarks-and-comparison.html) |
| 5 | Greptile（评审） | 全库索引 + 多跳调查，召回高但噪声大（约 11 误报/基准）；自报 82%，第三方复现 45% | 无全库语义索引；已有调用图缓存 | 学它的图，不学它的噪声：新增发现必须带可达性证据 | 同上 |
| 6 | 评测科学（SWE-bench 饱和/污染/测试黑客） | Verified 头部≈94–96% 饱和；OpenAI 2026-02 弃用；约 59% 被审计问题测试有缺陷；10 行 conftest 钩子可刷分；约 50% 通过测试的 PR 不被合并 | 判分已改 reward.txt；**不检查补丁是否改测试**；只有 DeepSWE 一个基准、n=1 | 本轮加 patch integrity；路线加 SWE-bench Pro/Live、成本、合并率 | [基准通胀综述](https://cloud.tencent.com/developer/article/2716210)、[审计与刷分综述](https://www.tmtpost.com/agent/ai-article/19782)、[SWE-bench 条目](https://baike.baidu.com/item/SWE%20bench/67614096) |
| 7 | Open Code Review（独立基准） | 公开 43.0% precision / 35.8% recall / F1 39.0（gpt-5.2 judge） | ReviewBench 12 例、双口径；自建评审器 | 把「独立评审器」纳入回归，防自评自夸 | [HN 讨论](https://news.ycombinator.com/item?id=48406358) |

三条直接结论：

- **工具面是能力乘数**：ACI 论文的核心不是换模型，而是「搜索/查看/编辑/
  执行」的交互设计；我们缺搜索这一项，长任务里的「找不到文件」成本很高。
- **图比计数强**：Aider 的 PageRank + 个性化权重是「大仓库里把对的符号
  顶到前面」的成熟答案；我们现在的引用计数在 django/sympy 这类仓库里
  容易把工具函数排到业务函数前面。
- **评测必须防作弊、报成本、看合并**：只报 pass@1 会被 conftest 钩子和
  数据污染同时欺骗；只说「通过测试」会被「不可合并」打脸。

### 3.1 开源项目库对标（2026-11-28 调研快照）

> 来源：《AI开源项目汇总》991 项索引（2026-11-25~27 GitHub API 快照），
> 筛 A（执行循环）/B（工具接入）/I（安全合规）三方向；星标与许可证为
> 快照参考值（观测≠因果），落地前以官方 LICENSE 复核。处置落 §4
> G16-G23 与 §6 阶段 5。

| # | 对标对象 | 他们的做法 | 我们的现状 | 吸收方式 | 来源 |
|---|---|---|---|---|---|
| 1 | pi-mono / opencode（MIT） | 循环边界三件套：终止判定统一、工具结果回填裁剪、失败熔断降级 | `llm/provider.py` 257 行单端点、无降级链 | stdlib 自研补齐（批次一 M2、批次二 M5） | A 方向 |
| 2 | mem0（Apache-2.0） | `add()`：抽取事实→与存量比对→ADD/UPDATE/DELETE/归档 | memory-pipeline AB-20 仅 UPDATE/ADD 双臂且默认关 | stdlib 补比对与归档臂（批次二 M8） | A 方向 |
| 3 | instructor（MIT） | 校验失败→错误信息回填重试闭环 | JSON mode 默认关；宿主臂曾全空响应（D-053） | **stdlib 自研版**（`llm/` 属治理壳禁第三方 import），批次一 M3 | A 方向 |
| 4 | agent-scan（Apache-2.0） | 工具描述哈希跨会话固化，防 rug-pull 篡改 | 16 工具（`mcp/review_mcp.py` TOOLS）无自扫描/防篡改 | stdlib 自研 mcp-selfscan（批次一 M1） | B 方向 |
| 5 | codex（Apache-2.0） | 内核层工具分级：自动/需审批/禁止 | 仅子进程目标白名单+超时 | 三级清单入仓+执行层拦截（批次一 M4） | A 方向 |
| 6 | presidio / privacy-filter（MIT） | PII 出站脱敏：预过滤+正则+熵兜底 | secret-scan 仅 7 条凭据规则、无个人信息面 | stdlib pii-scan（批次二 M7）；presidio 引擎层待批（D-054） | I 方向 |
| 7 | garak / PyRIT（Apache-2.0/MIT） | 探针化 LLM 端点红队（注入/越狱探针库） | 无 LLM 端点红队 | garak subprocess CI job 待批（D-054）；注入启发式 stdlib 自研（批次二择机） | I 方向 |
| 8 | defender（Apache-2.0） | 工具输出回灌 LLM 前注入扫描（本地分类器 <10ms） | 无 | stdlib 启发式进 MCP 响应管道（借设计自研，批次二择机） | I 方向 |
| 9 | codebase-memory-mcp（MIT） | 变更感知测试选择：diff→被改符号→import 反查→最小必跑子集 | fix-apply 闸五 pytest 全量跑（编码循环侧 ACI 阶段二已有 A/B 映射） | stdlib 自研提速闸五（批次二 M6） | B 方向 |
| 10 | repomix / serena / E2B / GEPA / deepeval / OpenLLMetry / harbor / inspector | 借设计或外部进程：整仓脱敏快照/符号级编辑/microVM 沙箱/反思式提示优化/评测面扩充/OTel 双写/任务格式统一/协议一致性测试 | — | 批次四 backlog；许可落地前核（serena/inspector NOASSERTION 必核） | A/B 方向 |

## 4. 差距清单（按优先级）

| ID | 优先级 | 差距 | 证据 | 影响 | 本轮处置 |
|---|---|---|---|---|---|
| G1 | P0 | 补丁可改测试/pytest 配置/解释器钩子而无人检查 | `deepswe-sample.py` 原判分只看 reward | 测试黑客面，resolved 不可信 | **已修**：`_patch_integrity` + `integrity_flagged` |
| G2 | P0 | 无每任务成本/轮数/耗时 | 结果只有 status/reward | 无法比较 scaffold，无法做成本归一 | **已修**：`elapsed_sec` + `code_task` 统计 |
| G3 | P0 | CI 不装依赖、缺 3.12、无超时/缓存 | `.github/workflows/self-check.yml` 原文 | CI 绿灯不含引擎层证据 | **已修**：装依赖 + 3.12 + cache + timeout |
| G4 | P1 | 编码循环无搜索工具 | `SYSTEM_PROMPT` 动作面 | 多轮浪费在猜路径 | **已修**：`search` 动作（有界+脱敏） |
| G5 | P1 | repo map 无图排序/个性化 | `agent/repo_map.py` 排序键 | 大仓库材料命中率低 | 阶段 2（`--rank graph`） |
| G6 | P1 | 基准样本量与口径仍小：DeepSWE 1/20、Pro agent 10/10（宿主模型、有反馈迭代）、Live 仅部分口径 | `reports/deepswe/baseline-v1.44.0.json`、`reports/swebench/pro-agent-10-2026-10-29.md` | 能力结论外推弱 | 部分达成：Pro 10/10 已入报告；仍待扩样与固定端点复跑 |
| G7 | P1 | 无「测试通过 ≠ 可合并」度量 | 无 merge-rate 字段 | 可能优化了错目标 | 阶段 1（人工抽检 + 接受率） |
| G8 | P1 | 评审流水线无统一事件账本 | trace 只在 code-task | 复盘靠轮报，重放不了 | **已修**：event-ledger.py + runner 接入（§5.12） |
| G9 | P2 | 无 `list`/目录树工具 | 动作面 | 探索大仓靠 read 猜路径 | 阶段 2 |
| G10 | P2 | 测试一律整跑，成本高 | `_run_tests` 全量 pytest | 大仓每轮慢 | 阶段 2（相关测试子集） |
| G11 | P2 | CI 无覆盖率/secret/license 扫描 | workflow 原文 | 回归与合规靠人工 | 阶段 3 |
| G12 | P2 | 依赖白名单与 pyproject 不一致（hypothesis MPL-2.0） | `AGENTS.md` 硬约束 1 vs `pyproject.toml` | 治理口径漂移 | 已裁定：hypothesis 移入 optional-dependencies.dev（round-56、D-034） |
| G13 | P2 | 300s 红线缺画像后的语义决策 | `reports/suite-profile-round-45.md` | 计时噪声被当回归 | **已改线**（D-041，2026-10-30；D-052，2026-11-10：升级触发线 450s→540s；600s 升格为 release-gate 判红挂死护栏，CI nightly ubuntu `timeout 600` / Windows job timeout-minutes: 45 兜底） |
| G14 | P2 | 无子代理分解 | code-task 单循环 | XL 任务上下文压力 | 阶段 4 |
| G15 | P2 | 多语言仅 ast-grep 扫描，编码侧 Python-only | `repo_map.py` 只解析 Python | TS/Go 任务无法进编码循环 | 阶段 4 |
| G16 | P0 | MCP 16 工具无清单哈希固化与分级门控 | BASELINE.md:391、`mcp/review_mcp.py:142` TOOLS | 自身即攻击面，无防篡改/分级 | 阶段 5 批次一（M1/M4） |
| G17 | P0 | LLM 供应层无循环边界三件套与多端点降级链 | `llm/provider.py` 257 行、host 臂 token 计 0（BASELINE.md:357） | 循环失控/成本不可观测 | 阶段 5 批次一（M2）+批次二（M5） |
| G18 | P0 | 结构化输出无「校验失败→错误回填重试」闭环 | 宿主臂曾全空响应（BASELINE.md:360-361、D-053） | 大预算零产出黑洞无防复发 | 阶段 5 批次一（M3） |
| G19 | P1 | 无 PII 出站脱敏面 | secret-scan 仅 7 条凭据规则、无个人信息面 | 个人信息出域风险 | 阶段 5 批次二（M7） |
| G20 | P1 | 无端点红队与工具输出注入防护 | 无 garak/defender 类机制 | 注入/越狱无探测与拦截 | 阶段 5 批次二（启发式）+批次三（garak 待批，D-054） |
| G21 | P1 | fix-apply 闸五 pytest 全量跑，无变更感知测试选择 | 修复链第五闸行为回归 | 大仓回归慢 | 阶段 5 批次二（M6；编码循环侧 ACI 阶段二已有 A/B 映射） |
| G22 | P2 | 记忆无比对决策/归档臂 | memory-pipeline AB-20 仅 UPDATE/ADD | 误报模式库膨胀/失活 | 阶段 5 批次二（M8） |
| G23 | P2 | 无默认运行时沙箱 | §1 自评「缺少运行时沙箱的默认化」、AB-14「评估完成暂不实施」 | 不可信补丁验证无隔离 | 维持 AB-14 结论，登记观察项，总监重启才动 |

## 5. 逐轮回填（已分卷）

> 自 v1.96.0（round-95）起，逐轮「已完成 / 偏差」回填分卷至
> [docs/ROADMAP-HISTORY.md](ROADMAP-HISTORY.md)（§5.1..§5.52 沿革）；
> 收官回填写入该卷末尾（round-gate close 的 roadmap_section 检查兼容回退
> 两卷）。本卷只保留现行路线（§1-4、§6-11）。

## 6. 分阶段路线

### 阶段 1（round 47–49）：评测可信化——先让数字可信

| 项 | 动作 | 验收标准 | 风险/依赖 |
|---|---|---|---|
| 1.1 | DeepSWE 20 条 Python 基线补跑（回归集优先） | 每条有 status/reward/elapsed/code_task；resolved 率与失败归因可复算 | 需 GitHub/ECR 或逐任务本地镜像；离线不可推 |
| 1.2 | `agent-sample.py` 同口径接入 patch integrity 与成本字段 | 与 deepswe 字段同名同义；反向样例一致 | 复用本轮 helper 思路 |
| 1.3 | 新增 SWE-bench Pro/Live 子集（各 ≥10 条） | 有独立基线文件、判分口径与 DeepSWE 对齐；标注污染风险 | 数据集/镜像下载必须遵守硬约束 8 |
| 1.4 | 合并率抽检（≥20 个历史上的 agent 补丁） | 输出「测试通过且可合并」比例与驳回原因分类 | 需人工评审，可能慢 |
| 1.5 | 评测报告加成本归一 | 报告并列 resolved、median elapsed、median rounds、tokens/次 | token 仅 openai 后端可得；host 侧标 N/A |

**阶段出口**：任一对能力的主张都能回答「哪套基准、多少样本、判分口径、
成本多少、有无完整性告警」。

**阶段一进度（round-49 收口；round-50 补适配层）**：1.2 ✅ 结构闸 + 成本字段同口径（malformed
不可豁免）；1.5 ✅ 成本归一脚本 + 真实报告 + 精度报告并入；1.4 ✅ 20 例
初筛（人工复核 pending，`human_review` 原样保留）；1.3 ✅ 基线 + harness
可行性验证（Pro gold 口径 1 failed/15 passed → 16 passed；Live 非基线
urllib3-3527 3 failed → 3 passed；**agent 侧实跑未做**，status 仍
not_run）；round-50 补：Pro 适配层代码化（`pro-sample.py`，3 仓 gold 对照
全通，§5.8）；round-51 补：Pro 扩 10 条 baseline→gold 全通（`--patches`
agent 通路就位、真实补丁 n=0；§5.9）+ Live 适配层就位（9 条
`blocked_source` 待补源、matplotlib/urllib3 部分口径不折算；§5.9）；
round-52 补：**Pro agent 侧 10/10 resolved（F2P 32/32、P2P 269/269）**，
宿主会话模型 + 仅 problem_statement，多轮尝试与成本口径单列（D-030，§5.10）；
1.1 ◐ 1/20 resolved（余 19 待 GitHub/ECR 可达或本地镜像逐任务
就位，ECR 实测 <0.14MB/s 判死）。阶段出口「哪套基准、多少样本、判分口径、
成本多少、有无完整性告警」五问已能逐项回答；能力结论仍受 1.1 样本量、
Pro n=10 与「有反馈迭代」口径、1.4 人工复核限制，不外推。

### 阶段 2（round 50–53）：ACI 与上下文——把「找得到、看得准」做实（round-53 收口）

**开局项 2.0（round-50）**：Pro/Live 适配层代码化——Pro ✅（`pro-sample.py`，
3 仓 gold 对照全通，§5.8）；Live ✅（`live-sample.py`，gate-10 9 条
`blocked_source` 保留 + matplotlib `baseline_ok`→`f2p_passed`、urllib3 补充
样本 3/3 F2P，均为部分口径，§5.9）。

| 项 | 动作 | 验收标准 | 风险/依赖 |
|---|---|---|---|
| 2.1 | repo map 增 `--rank graph`：文件/符号图 + 个性化 PageRank，默认关 | 三个真实仓（django/sympy/matplotlib）上目标文件 Top-8 命中率 ≥ 现路径；材料 token 不增 | 构图成本；需缓存 |
| 2.2 | 搜索排序：命中按「定义 > 引用 > 注释」与路径距离排序 | 同一查询的前 5 条含定义点比例提升 | 需要 AST 辅助 |
| 2.3 | 新增 `list` 动作（目录树，限深限宽） | 大仓探索轮数下降；无越界路径 | 路径安全检查 |
| 2.4 | 测试子集：按改动文件映射相关测试，失败再回退全量 | 单轮测试耗时下降 ≥30%，漏测率为 0（以全量为金标准抽检） | 映射准确性 |
| 2.5 | 编辑后校验增强：语法树级最小校验（ast-grep/tree-sitter） | 语法破坏在本地拦截率 100% | 引擎层可用性 |

**阶段出口**：DeepSWE 上「因路径/文件不存在浪费的轮次」占比下降一半；
同一任务的中位轮数下降；无新增回归。

**阶段二进度（round-53 收口）**：2.0 Pro/Live 适配层 ✅；2.1 ✅ 能力与显式
开关（真实 Top-8 无增益，按判据保持默认关）；2.2 ✅（13→17/21，转正）；
2.3 ✅ 能力与边界（探索轮数未测）；2.4 ✅ 机制转正（映射 7/11、控时 -35.2%、
1/3 抽检）；2.5 ✅（10/10、0 误报）。**阶段出口两项实跑指标未测**（路径浪费
轮次、中位轮数），留待编码循环宿主实跑；「无新增回归」以双跑为准。证据与
边界见 §5.11、D-031。

### 阶段 3（round 54–57）：观测与工程化——让系统可复盘、可交付

| 项 | 动作 | 验收标准 | 风险/依赖 |
|---|---|---|---|
| 3.1 | 事件账本：review/repair/eval 统一 Action/Observation JSONL，支持 replay 校验 | 任一历史 run 可用账本重放关键判定；差异可见 | 需要统一 schema |
| 3.2 | 成本账本：每次 run 汇总 tokens/耗时/轮数，写 `totals.json` | 与 runner 预算上限对账一致 | host 模式 token N/A |
| 3.3 | CI 增加覆盖率门禁（仅治理壳 + agent 关键路径） | 覆盖率不低于基线，且不因平台漂移误报 | 基线已入仓（round-56） |
| 3.4 | CI 增加 secret 扫描与 license 清单校验 | 命中凭据形态即失败；依赖许可证与白名单一致 | 已裁定（D-034） |
| 3.5 | 发布闸：版本六处同步 + README 真值 + 全量双跑 + 文档新鲜度 | 一键脚本全绿才允许打 tag | 已定义（D-035，round-57） |

**阶段出口**：任何人拿到一个 run 目录，不读聊天记录也能回答「做了什么、
为什么、花了多少、能不能复现」。

**阶段三进度（round-55 起）**：3.1 ✅ 事件账本与 replay（§5.12、D-032；
演示 run 31 条、verify 链完好、replay 20/20 MATCH）；3.2 ✅ 成本账本与
预算对账（§5.13、D-033；演示 run 8/8 PASS、续跑段同样 8/8）；3.3 ✅
覆盖率门禁（§5.14；基线入仓、第二次实测容差内 PASS、篡改样例 rc1）；
3.4 ✅ secret+license 门禁（§5.14、D-034；全仓 0 未豁免命中、10 包三档
PASS）；3.5 ✅ 发布闸与「发布」边界（§5.15、D-035；七项检查真仓全绿、四类反向验证判红；tag 不可复用版本号）。

### 阶段 4（round 58–60）：顶层能力——长任务与多语言

| 项 | 动作 | 验收标准 | 风险/依赖 |
|---|---|---|---|
| 4.1 | 子代理分解：定位/修复/验证三角色，主循环只做裁决 | XL 任务（跨 ≥5 文件）resolved 提升；轮数不失控 | 上下文与成本上升 |
| 4.2 | 多语言编码：TS/Go 的 repo map + 搜索 + 编辑校验 | 至少一个 TS 与一个 Go 任务端到端 resolved | tree-sitter 语言包依赖 |
| 4.3 | 工作区抽象：本地 worktree / 容器 / 远程三档统一接口 | 同一任务在本地与容器跑出的补丁一致（除环境差异） | 与 probe-docker 合并 |
| 4.4 | 评审闭环：把 agent 补丁送第三方评审器（Open Code Review 或等价） | 自评与他评差异可量化；差异 > 阈值时转人工 | 外部工具许可与成本 |

**阶段出口**：在「治理不放松」的前提下，能力指标进入公开可比区间；
对外表述只引用自有实跑与样本量。

**阶段四进度（round-60 收口）**：4.1 ◐ —— 三角色状态机、角色门禁、机械测试
优先仲裁、返工/升级预算、`phases.json` 裁决台账（跨 `--resume`）已交付并
有 10 条契约；XL 单例（跨 5 文件）两臂 resolved、轮数 2/12 与 4/12；
「resolved 提升」未证（n=1 自产夹具 + 同一宿主模型，D-036），不宣称。
round-61 补独立语料对照（公开上游提交、测试补丁预置、机械 pytest 判分、
两臂同一宿主模型）：4/4 resolved、补丁字节级一致、未观测到 uplift
（phases 4 轮 vs single 2 轮；n=2 不外推，D-040）——两份独立证据方向
一致，「提升」仍不宣称。
4.2 ✅ —— TS/Go 的 repo map、搜索与编辑校验落地，测试引擎按仓库信号自动
选择；ts-calc 与 go-stack 两条自产任务端到端 2/2 resolved（n=2 夹具自产，
只证通路可用、不外推成功率，D-037）。4.3 ✅ —— 本地 worktree / 容器 / 远程
三档统一接口；同一任务同一宿主响应本地 vs 容器补丁字节级一致（232 B，
sha256 相同，D-038）；remote 档仅接口与假壳契约，code-task 显式拒绝，
不以假跑冒充真机。4.4 ✅ —— 自评/他评差异量化（同文件 ±2 行配对、
`diff_rate` 可复算）且超阈值/高严重度/覆盖缺口/外部臂全不可用一律转人工；
样例集 8/8 符合预期、端到端门禁 2/2（n=8 自产夹具，只证机制与判定口径，
不外推评审准确率，D-039）。阶段四四项全部交付（4.1 留 uplift 未证）。

### 阶段 5（round 233–236）：开源对标强化——P0 门控与边界、P1 深化

| 项 | 动作 | 验收标准 | 风险/依赖 |
|---|---|---|---|
| 5.1 M1 | `mcp-selfscan.py`（production-guardrails）：TOOLS 16 工具名/描述/Schema 的 sha256 固化入 `mcp/tools-pin.json`，CI/启动比对，漂移拒服务 | 篡改样例必命中（反向验证）；漂移 rc=1；self-check 接线 | 工具清单演进时 pin 文件须同轮刷新 |
| 5.2 M2 | `llm/provider.py` 循环边界三件套：终止判定统一、工具结果回填裁剪（超限外置 tool-outputs/）、连续失败熔断+降级记录 | 熔断样例必命中；裁剪外置可查；行为级→precision-gate 基线不回退（≥0.65 地板） | host 臂成本仍 N/A；D-053 门禁语义不变 |
| 5.3 M3 | 结构化输出回填重试（`llm/` stdlib 版）：解析/校验失败→错误回填重试 1 次→仍失败如实计 unparsed | 全空响应样例：重试后有产出或如实 unparsed；D-053 门禁语义不变 | 重试入预算逐次扣减 |
| 5.4 M4 | 工具分级门控：`mcp/tools-policy.json` 三级清单入仓，执行层按级拦截，审批级无批准书拒执行 | 审批级无批准书拒执行（反向样例）；清单与 TOOLS 键一致 | 与 M1 pin 范式同构；清单演进须同轮刷新 |
| 5.5 M5 | 多端点 fallback 链：配置化多端点轮换+降级记录（口径与下载策略同源） | 降级原因必记、路径可复算；端点白名单校验不放松 | host 臂成本仍 N/A |
| 5.6 M6 | 变更感知测试选择（stdlib ast+git diff→受影响测试子集→闸五提速） | 受影响测试样例必选入；漏测率 0（每次抽检对照全量金标准） | 映射准确性；子集过 ≠ 闸五过 |
| 5.7 M7 | pii-scan.py（privacy-filter 三层：预过滤+正则+熵兜底） | PII 样例必命中；secret-scan 语义不变；CI 接线 self-check | 与 secret-scan 费责边界（凭据 vs 个人信息） |
| 5.8 M8 | 记忆比对臂：抽取→与存量比对→ADD/UPDATE/DELETE/归档（mem0 思想 stdlib 强化 memory-pipeline） | 比对决策可复算；归档不丢原文；AB-20 默认关维持 | 默认关维持 |
| 5.9 | 批次三（待 D-054 批准，建议并入 r236 依赖刷新锚点轮一并裁定）：presidio（MIT）/garak（Apache-2.0 subprocess）/traceloop-sdk（Apache-2.0）/deepeval（Apache-2.0 dev 侧）→ licenses.json + pyproject optional-deps 落位 | D-054 批准后落位；license-check 三档 PASS | 总监裁决；serena（NOASSERTION）未核不入 |
| 5.10 | 批次四 backlog（借设计）：E2B microVM（AB-14 维持暂不实施）/repomix 整仓脱敏快照（D-031 终局不重议）/GEPA（AB-06 底座升级）/inspector 协议一致性测试/harbor 任务格式/OpenLLMetry 全量观测 | 登记为 backlog，总监点名才动 | 许可落地前核 |

**阶段出口**：批次一 P0 四项（M1-M4）落盘 + 门禁全绿 + 反向验证全命中；
precision-gate 基线不回退（≥0.65 地板）；SRE 预算未超（EXCEEDED 则整改
冻结只修质量）。批次二/三各自验收口径见表内；批次三须持 D-054 批准书
（提案人≠批准人）方可动 pyproject/licenses.json。

**阶段五进度（round-233 批次一收口，v2.102.0）**：5.1 ✅ `mcp-selfscan.py`
（pin/check 双动词 + serve() 启动比对漂移拒服务 + CI self-check 步骤；篡改/
缺失/多余/pin 损坏 4 类漂移反向验证入契约，9 条测试）；5.2 ✅ 循环边界
（`trim_tool_result` 统一裁剪助手 + 跨调用连续失败熔断 threshold=3/冷却
300s + stderr 降级记录；6 条裁剪 + 3 条熔断契约）；5.3 ✅ `complete_json`
回填重试（损坏/校验失败→错误回填重试 1 次→仍失败如实 unparsed；D-053 全空
[] 语义锁定测试；reviewbench-eval 宿主臂接线）；5.4 ✅ `tools-policy.json`
三级清单（auto×14/gated×2=apply、purge 自带闸；未知工具 fail-closed；deny
拦截反向验证）。批次一四项 24 条新契约全绿；M2/M3 行为级反向验证=评审器/
判分面零改动（precision 基线结构性不回退，host 臂 unavailable 维持）；
批次二（M5-M8）与批次三（D-054 待批）留后续轮。

**阶段五批次三/四处置（round-237 裁决，D-054 第 2 条）**：批次三=方案 C 终局
（四依赖条件激活：presidio=自由文本 PII 泄漏实证；garak=openai 端点实配；
traceloop-sdk=外部 OTel 网关需求；deepeval=现有门禁覆盖不足实证）；批次四
维持 backlog 不点名激活——E2B（AB-14 维持暂缓）、repomix（D-031 边界不破）、
GEPA（AB-06 底座升级候选）、inspector/harbor/OpenLLMetry（协议回归/终端任务
面/外部观测需求各自出现时再议）。**阶段 5 至此收口**：批次一+二 8 项全落地
（r233-r235，44 条契约），批次三/四按上述条件处置。


## 7. 度量体系（North Star 与护栏）

**North Star（能力）**

1. DeepSWE / SWE-bench Pro / ReviewBench 三线的 resolved（或 F1）与样本量；
2. 每个 resolved 的成本：`elapsed_sec`、`rounds`、`tokens`（可得时）；
3. 补丁质量：`integrity_flagged=0`、回归=0、补丁破坏模块=0。

**护栏（不许为了指标牺牲）**

- 评审 precision 不低于 0.65（规则口径）且趋势不降（round-62 起由
  `eval-harness/precision-gate.py` 机械执行：固定 ReviewBench 语料 +
  基线 `precision-baseline.json`，语料缺失 code=2，见 §5.20）；
- 全量套件连续两次全绿；总时长作为**观测指标**，挂死护栏 600s（待批）；
- 任何 patch integrity critical 必须人工复核或显式豁免；
- 治理五道闸、分权、脱敏、镜像铁律一条不改。

**报告格式（固定五列）**：基准 / 样本量 / 判分口径 / 成本 / 完整性告警。
缺任一列视为不合格报告。

## 8. 不做什么（反目标）

- 不把 SWE-bench Verified 当主战场：已饱和且污染，继续刷分只增加自欺。
- 不引入 GPL 系依赖；LGPL 继续 subprocess 隔离；不因「别人都内置」而破例。
- 不为了召回放宽评审精度到「噪声级」；不复制 Greptile 的高误报模式。
- 不自动合并修复分支；不跳过五道闸；不让任何一方自审自批。
- 不在没有反向验证与精度基线的情况下改评分口径/阈值/红线。
- 不把行业厂商自报数字当自己的成绩；对外只报自有实跑与 n。

## 9. 风险、依赖与待决策

1. **网络与镜像**：DeepSWE 余量依赖 GitHub/ECR 或本地镜像；按硬约束 8
   先实测国内源，慢即判死，降级必须记录原因。
2. **300s 红线**：已改线（D-041，2026-10-30 round-67 总监批准方案 2）：300s
   降观测线 + 600s 挂死护栏；原「连续 13 轮双跑超线」降级为告警线，不再产生
   违规升级；本页与 ROADMAP 第 6 节同时同步，旧 300s 数值均视为历史记录，不回改；
3. **许可证口径**：~~三处不一致需裁定~~ **D-022 已裁定（2026-10-31
   round-77 总监批准方案 1）**：MIT/Apache/BSD 可嵌入 import；MPL-2.0
   仅 test-only（optional-dependencies.dev，不进运行时 import 链、
   不随治理壳分发）；LGPL 仅 subprocess、GPL 禁入。三处文档已同步
   （AGENTS 硬约束 1 / BASELINE 依赖契约 / pyproject 注释）。
4. **模型与宿主差异**：host 协议无 token/成本数据；跨模型比较必须同
   scaffold、同判分口径，报告标 N/A 而不是估算。
5. **Windows 特有路径**：CRLF、盘符挂载、权限锁已在 round-46 踩过；
   新工具（search/list/graph）必须带路径归一与越界检查。
6. **Windows 编码链**：cp936/GBK stdin、CRLF/LF 补丁、UTF-16 日志坑（8cfbcaf7d227、bb6ebd590d5e）；阶段 5 新脚本一律沿用既有对策：PYTHONUTF8/PYTHONIOENCODING 置空纪律、补丁 LF、stdout 单 JSON + utf-8 reconfigure（S10）。
7. **MCP async 家族 flaky 留观**：cancel/status 竞速三例三因（r184/r190/r197），`test_purge_guards` 第 5 例仍在留观（next-round.md）；阶段 5 新增 MCP 面（M1/M4）不新增竞速面，pin/清单演进须与 TOOLS 同轮刷新，防 pin 漂移误报。
8. **D-053 门禁语义保持**：M3 回填重试不改变 review-quality-gate 与 D-053 门禁语义（全空响应仍判红）；重试产物仍过 findings-check 七要素校验。

## 10. 维护与验收

- 每轮收官：在 §5 追加「本轮已内化」，在 §6 勾掉完成项并写偏差；
  若阶段目标变化，先改本文再开工，不做事后追认。
- 每阶段末：按 §6 出口做一次独立复验（另一会话/另一模型），结论写
  `reports/` 并从 `docs/PROGRESS.md` 索引。
- 本文与 `retro/next-round.md` 的分工：本文管 3–6 轮的方向与验收，
  next-round 管下一轮的具体动作与顺序；冲突时以本文的阶段目标为准，
  以 next-round 的执行顺序落地。

## 11. 来源

- SWE-agent（ACI）：[论文页](https://hyper.ai/cn/papers/2405.15793)、
  [解读](https://bbs.csdn.net/topics/620501218)
- Aider repo map：[机制详解](https://m.blog.csdn.net/gitblog_00417/article/details/151489226)、
  [token 预算](https://fast.io/resources/aider-token-limit/)
- OpenHands：[平台论文](https://hyper.ai/cn/papers/iclr__2025__OJd3ayDDoF)、
  [SDK 与设计原则](https://baike.baidu.com/item/OpenHands/67237854)
- SWE-bench 饱和/污染/测试黑客：[基准通胀综述](https://cloud.tencent.com/developer/article/2716210)、
  [审计与刷分综述](https://www.tmtpost.com/agent/ai-article/19782)、
  [SWE-bench 条目](https://baike.baidu.com/item/SWE%20bench/67614096)
- 评审工具精度与复现差异：[五款工具对比](https://www.jdon.com/94308-ai-code-review-tools-benchmarks-and-comparison.html)、
  [独立基准综述](https://screencli.sh/blog/best-ai-pr-review-tools-2026)、
  [Open Code Review 讨论](https://news.ycombinator.com/item?id=48406358)
- 开源项目库对标来源：《AI开源项目汇总》（991 项索引，2026-11-25~27 GitHub API 快照）A/B/I 三方向；本轮对标矩阵（§3.1）与批次设计以该快照为准，星标/许可证为快照参考值。
- 2026-11-28 审查报告：W1-W10 弱点矩阵与四批强化路线（§3.1/§4 G16-G23/§6 阶段 5 即其入册形态）。

> 版权与使用：以上仅作技术路线参考；未复制其代码或语料。厂商自报数字
> 已在正文标注「自报」，不并入本项目能力结论。
