# dev-agent 协作手册

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：总监 ｜ **主导模式**：参考
> **权威范围**：见下方原始头注详述
> **不是权威**：命令用法（docs/06-operations）、评测证据（reports/）
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 文档状态：维护中（M3 约定权威源）｜创建：2026-10-24 ｜ 权威范围：智能体主流程 0–10 步、硬约束 1–8、维护红线、组织架构与脚本清单；文档体系见 `docs/INDEX.md`（树内索引与取代关系）。

全能代码智能体（治理先行）：评审/修复/重构/测试生成与编码循环，Python 深耕优先；
复用成熟开源引擎（Ruff/LibCST/ast-grep），一切写操作经五道闸安全落盘。
本文件是 agent 的主流程与硬约束来源；skill 目录下的 SKILL.md 是各阶段的操作细则。

## 硬约束

1. 分层依赖策略：治理壳（skills/*/scripts、llm/）只用 Python 标准库，保持零依赖
   可分发；引擎层（engines/、agent/）按依赖白名单引入第三方——MIT/Apache/BSD
   许可证可嵌入 import；MPL-2.0 仅限测试/生成侧（optional-dependencies.dev，
   如 hypothesis：不随治理壳分发、不进运行时 import 链）；LGPL 组件
   （Rope/Pynguin/Semgrep 引擎等）仅以 subprocess
   隔离调用，不得 import；GPL 系禁入。新增依赖须经总监批准并登记 pyproject.toml
   与许可证；本项目自研脚本不因引擎引入而放松本条。（MPL 边界：D-022，
   2026-10-31 总监批准）
2. 每个脚本：shebang 开头、模块 docstring 写清「用途 + 用法示例 + 退出码」、输出 JSON 到 stdout（stdout 只有一个 JSON 文档，诊断信息走 stderr）。带主入口的 Python 脚本须对 sys.stdout 执行 reconfigure(encoding="utf-8")；无主入口的库模块除外（doc-structure S10 机械校验）。
3. 退出码：0=成功；1=有可处理的问题（不是崩溃，含 NEED_HUMAN 与 WAIT_HOST_LLM）；2=输入/环境错误；intent-parse 另有 3=需追问。
4. 路径参数必须显式可指定，不得硬编码绝对路径。
5. 产物不得出现明文凭据：命中密钥形态时 snippet 脱敏为 `<redacted>`。
6. 所有扫描 diff 内容的正则不得依赖行首锚定（`^\s*`），因为 diff 的 +/- 前缀会让它失配。
7. 修复与审核分立（科层制）：补丁先行；写入被审仓库一律经五道闸治理框架
   （唯一落盘入口 repair/scripts/fix-apply.py——修复团队的机械补丁、引擎团队的
   Ruff/LibCST 修复产物、重构 codemod 与编码循环的编辑全部经它落盘），必须持
   审核人批准书并过五道闸（批准书、工作树干净、HEAD 与 base_sha 一致、
   git apply 预检、行为回归=重扫原规则消失且无新增 + 仓库测试），任一失败自动
   回滚；修复分支永不自动合并；任何一方不得自审自批；每轮工作末尾由迭代官
   复盘入坑台账；疑难杂症先查案例库，未命中由总监签发研究简报走联网调研；
   行为级优化（配置/代码）必须过反向验证与精度基线。
8. 镜像下载铁律（2026-10-25 增补）：任何镜像/模型权重/大文件数据集下载前，
   **必须联网先实测确认国内可达性，必须优先选择国内镜像源**。镜像源判定一律跑
   `scripts/docker-mirror-probe.py`（SSRF 校验 + token/manifest/blob 分段实测，
   blob 段速度才是判死依据——manifest 可达 ≠ 镜像可拉，v1.22.0 实测教训）；
   国际直连仅作回退，且必须记录降级原因；慢即判死（缺省 2 分钟纪律），不傻等。

## 下载策略（2026-10-24 增补；铁律见硬约束 8）

所有外部下载（数据集/依赖/语料/模型）**先联网搜索国内镜像源，直连国际源
仅作回退**——实测 Zenodo 12KB/s vs hf-mirror 560KB/s（46 倍差距）。已验证
可用源：Gitee 镜像（git clone，mirrors/<repo>，须逐仓验证存在性）、
hf-mirror.com（HuggingFace 数据集/模型，公开仓库无需认证，支持 Range 断点
续传）、清华 PyPI 镜像（pip/uv）、OpenDataLab（数据集，部分需登录）、
Kaggle（需 API key）。大文件下载一律 curl -C - 断点续传循环（每段限时自动
重试）挂后台，不阻塞主线程；Zenodo/GitHub 直连仅在国内源缺失时使用并记录
降级原因。**Docker 镜像另有专项铁律（硬约束 8）：下载前必须联网实测国内
可达性并优先国内源。**

**主镜像缺包时的降级顺序（2026-10-25 增补）**：国内主镜像没有该包时
（如清华 PyPI 对 mpmath 无匹配版本，`from versions: none`），按
「主镜像 → 其他国内镜像（阿里云等）→ 国际直连」依次降级，**每次降级都要
记录原因**；不得因为主镜像缺失就跳过国内源直连国际。被审仓库需要更老的
Python（如 sympy 1.1 需 ≤3.9）时，用 `agent/legacy_compat.py` 垫片在本机
运行（不改被审仓库、不改全局解释器），最终判定仍以 harness 容器为准。

## 组织架构（科层制 v2，事实源 skills/director/org.json）

对标大公司实践的三层管理与治理机制：

- **三层管理**：总监（上级，只分派与验收）→ 各团队首席 lead（runner.py /
  fix-apply.py / approve-patch.py / retro-report.py / research-brief.py，
  守门与守口径）→ 成员技能（members）。
- **RACI 签字权**：每类交付物在 org.json raci 表中固定 R=负责执行 /
  A=唯一签字人 / C=咨询 / I=知会；补丁包由修复团队 R、审核人 A，
  行为级优化由迭代官 R、总监 A（提案人≠批准人的两人规则）。
- **SRE 错误预算**：各团队预算口径（修复回滚率≤0.2、审核每轮拒绝≤3、
  未结坑≤8、无链接案例=0）由 org-scorecard.py 每轮结算；WARN 整改关注、
  EXCEEDED 整队进入整改冻结（只修质量不扩功能）；无数据如实标 N/A。
- **主观能动性注册表**：每个角色的 initiatives 声明"事件 → 主动动作"，
  分派回执必须下发；已代码化的主动伸手——审核人拒绝时自动查案例库附
  reuse_hints，修复回滚时同样；其余动作由宿主按 SKILL.md 主动执行。
- **值班式升级链**：L1 团队首席（查案例库自行处理）→ L2 总监（签发研究
  简报/审批优化）→ L3 人工（预算超限/安全争议转 NEED_HUMAN）。
- **案例库 v2（链接型档案）**：本地只存轻索引（title/category/takeaway/
  verification + 链接），完整内容存公开档案/仓库链接（url）或本仓库档案
  （local_ref，如轮报与验收测试），无链接不得入库。
- 交接物链与跨团队协作约束同前：CLI + JSON 产物，批准书 sha256 绑定，
  补丁任何变动即作废重审。

## 主流程（0–10 步，评审团队）

### 0. 生产护栏 + 开局探自我迭代信号
先跑 session-probe.py：退出码 0=全绿不做事；1=有信号（按 triage 处理）；2=检查器故障先修。
评审全程调用 audit-log.py 记录关键决策；断点用 checkpoint.py write/read/verify；
统一事件账本由 event-ledger.py 写 ledger.jsonl（runner 自动记录脚本/判定/LLM 指纹事件），replay 可重放关键判定并给出路径级差异。

### 1. 意图解析
intent-parse.py --request "<用户原话>" --repo <路径> → 对象/范围/深度档/意图分级/依据。
C 级（对象无法确定或请求自相矛盾，退出码 3）必须追问，不得擅自开审。
A/B 级读三键：ambiguity（被裁决掉的多解读，落选信号供复核）、assumptions
（采用的假设，带依据与错了的代价）、confirmations（非阻塞待确认项）——
confirmations 必须在报告口径段列出并带回用户，不得静默当作已澄清。
模糊意图要拆子任务时走 task-pipeline.py --from-intent（拆解带 DoD/依赖/
产出物；派发 --dispatch 经 org-route；汇总 --collect 不吞遗留）。

### 2. 一次取数
preflight.py 过预检门（仓库可读、rev 可解析、定档 S/M/L/XL、预算两档估计）。
edge-detect.py 机械检测 11 类边界形态并标注 evidence。
收集变更数据、影响模块、历史稳定性、跨文件依赖、意图声明。
deterministic-rules.py 出「已证事实」（38 条硬规则，snippet 一律脱敏）。
graph-cache.py build/update 维护代码图缓存（mtime+size 增量，超限截断并标 truncated）。
版本锚定（硬规则）：diff 之外引用的代码必须用 `git show <rev>:<路径>` 取自评审对象那一版，禁止读工作区。

### 3. 风险评分
score.py → 区域等级 + 整次综合 + 高风险区域清单。权重固定 规模 0.3 / 耦合 0.4 / 稳定 0.3，不得调整。

### 4. 启动并行审查
先跑 score.py，再 dispatch-plan.py --diff <diff文件> 定维度与路数。
机械计划管「该跑的一路不少」；动态增派另管「异常集中时再加」（上限 max_dynamic_dispatches），不拿计划当上限。
构造材料包：区域等级/综合分/高风险清单必须粘贴 score.py 输出，不得手工填写。
材料按目标函数或 hunk 截窗口（函数体 + 3 行上下文），不把整文件当材料。
派发前跑 material-check.py：needed_context 走 A/B/C 档；completeness_hints 要求附核对表。
子代理按七要素提交：定位（文件:行号）、问题描述、证据、严重度、置信度、原因、初步修复建议。
提交结果先过 findings-check.py 校验，缺项打回。

### 5. 流式核验
哪路先回先核验；逐项过六问（证据成立/引用真实/重复/超范围/误报/完备性核对做过没）。

### 6. 高风险项多轮查证
多个高风险项并行、同一项多轮串行；每轮换角度但同一命题；连续两轮一致才定稿（上限 max_verification_rounds）。

### 7. 第一轮汇总
变更摘要 + 测试建议 + 风险评分；作为反向验证的比对基线。

### 8. 分级反向验证
高风险逐项交叉核对（可用 perspective-scan.py 做可机械判定部分）；
中低风险用 coverage.py 查 hunk 覆盖，函数名定位进 unresolved 不得静默忽略；
无缺陷的高风险区域做反向抽样。

### 9. 汇总生成优化步骤手册
按严重度降序；每项五要素（定位/证据/原因/修复步骤/证据等级）；
高风险项修复步骤含四要素（怎么改/影响面/怎么验证/替代方案）。

### 10. 交付收尾
report-check.py 校验模板（七段齐全 + 补丁格式 + 阅读顺序说明）；
报告附运行信息（档位、轮数、token/时间预算、降级记录、审计条数）；
用户驳回项用 experience.py record 记入误报模式库。

## 修复阶段（可选，评审完成后；修复团队 + 审核人）

评审发现清单可继续走三方链路（交接物见组织架构）：

1. 审核人闸 1：approve-plan.py 分诊叠加严重度政策，签发工单
   work-order.json（拒绝项必带原因；凭据类一律拒绝——补丁会复制明文，
   违反硬约束 5）。
2. 修复团队施工：fix-plan.py 已被闸 1 调用完成分诊；fix-patch.py 凭工单
   生成 unified diff 补丁与 fix-manifest.json（只写产物目录）。
3. 审核人闸 2：approve-patch.py 五项独立核验（工单绑定/三方基线一致/
   git apply 预检/补丁新增行零命中/路径安全），签发批准书 approval.json
   （sha256 绑定补丁包）；REJECTED 必给 reasons，退回返工。
4. 修复团队落盘：fix-apply.py --apply 持批准书过五道闸，第五道为行为回归
   （逐文件重扫原规则消失且无新增规则 + 发现仓库测试时执行 pytest，
   测试失败等同验证失败）；验证失败自动回滚 ROLLED_BACK（回滚也落
   apply-log 供迭代官采集）；--undo 撤销修复分支。APPLIED 后修复在
   review-fix/<id> 分支上，是否合并由人工决定。

## 复盘阶段（每轮工作末尾；迭代官）

每轮工作结束必须跑（可用 MCP 工具 code_review_retro）：

1. retro-ledger.py --events <轮内事件> --scan <runs/修复产物目录> --out retro：
   手工事件 + 产物痕迹（REJECTED/ROLLED_BACK/skipped/误报）去重入坑台账。
   事件带 type ∈ feature/test/doc/confirmation 视为完成记录不入册；已入错的
   「非坑」条目用 --archive ID --archive-note 理由归档（保留原文，只对 open 生效）。
2. retro-report.py --ledger retro/pitfalls.json --out retro --round N：轮报
   round-<N>-report.md + 机器候选清单 round-<N>-candidates.md + 改进候选排序
   （真仓必须显式 --round N——缺省自动编号在真仓被护栏拒绝，r155 坑对策）。
3. 轻量收官（round-142）：零代码变更轮走 `round-gate.py close --round N
   --round-type light`（单跑 run1 全绿即可，其余五检查不减）；版本交付轮
   维持 full 双跑。
4. 事件账本哈希链（round-153 起）：轮收官后向 runs/rounds-ledger/ledger.jsonl
   追加一条 round-summary（event-ledger.py record --kind note --replay opaque，
   observation 记轮号/版本/结局）；账本 verify 链完好即轮次证据链闭合。

每轮开局先读 next-round.md（人工维护的开局检查单，report **不写它**——历史上
report 每次重写它会把人工增补的口径与来源覆盖掉）；同 category 反复新增坑视为对策无效，
应升级为结构改造候选。细则见 skills/retro/SKILL.md。

MCP 侧对应 code_review_approve（mode=scope|patch）、code_review_fix
（只吃工单）、code_review_apply（confirm=true 且持批准书才落盘）。
细则见 skills/repair/SKILL.md 与 skills/approval/SKILL.md。

## 触发人工介入（human-gate.py）

五类触发：预检拒绝、预算两档都超、结论未收敛、查证未完成、降级跨两级以上。
四类不算门：单个低置信度发现、材料不足、风格建议、测试建议。

## 编排执行（orchestrator/scripts/runner.py）

runner.py 把本主流程代码化：预算四参数（分钟/轮数/查证轮数/动态增派）逐次扣减、
每步写断点、--resume 续跑、误报模式库下发到派发、--feedback 驳回项回流、
交付双闸失败即 NEED_HUMAN。LLM 端点走白名单校验（公网 https 或本地回环）。

## 脚本清单（90 个）

| skill | 脚本 | 用途 | 主流程接入 |
| --- | --- | --- | --- |
| orchestrator | runner.py | 0-10 步编排执行（预算/轮数/断点/反馈闭环强制/报告风格变体） | 全流程 |
| prompt-enhancement | intent-parse.py | 意图解析与分级（三键：ambiguity/assumptions/confirmations） | 步骤 1 |
| director | task-pipeline.py | 任务流水线：拆解带 DoD/派发经 org-route/汇总不吞遗留 | 步骤 1（模糊意图承接） |
| git-change-analysis | preflight.py | 预检门与定档 | 步骤 2 |
| git-change-analysis | edge-detect.py | 11 类边界形态机械检测 | 步骤 2 |
| git-change-analysis | graph-cache.py | 代码图缓存增量维护 | 步骤 2 |
| risk-scoring | score.py | 三维风险评分 | 步骤 3、4 |
| multi-agent-review | deterministic-rules.py | 38 条硬规则出已证事实 | 步骤 2 |
| multi-agent-review | taint-cross.py | 跨文件污点两遍分析（摘要+调用方） | 步骤 2 |
| multi-agent-review | dispatch-plan.py | 机械定维度与路数 | 步骤 4 |
| multi-agent-review | material-check.py | 材料完备性校验 | 步骤 4 |
| multi-agent-review | rules-select.py | 规则文档选择（路径→蒸馏规则文档，进评审材料） | 评审 |
| multi-agent-review | repo-rules-inject.py | 被审仓库团队规范注入器（惯例名发现+有界摘录+脱敏，AB-22 rules 注入面） | 评审 |
| multi-agent-review | coverage.py | hunk 覆盖度反向验证 | 步骤 8 |
| multi-agent-review | findings-check.py | 七要素与四项校验 | 步骤 4 |
| production-guardrails | audit-log.py | 审计日志（脱敏） | 全程 |
| production-guardrails | event-ledger.py | 统一事件账本（Action/Observation JSONL + sha256 哈希链 + 重放对账） | 全程 |
| production-guardrails | cost-ledger.py | 统一成本账本（totals.json cost 块 + C1–C8 预算对账） | 全程 |
| production-guardrails | checkpoint.py | 断点读写与续跑校验 | 全程 |
| production-guardrails | human-gate.py | 人工介入门 | 步骤 0、2、6 |
| production-guardrails | report-check.py | 报告模板校验 | 步骤 10 |
| production-guardrails | schema-check.py | 8 个产物 schema 校验 | 步骤 10 |
| production-guardrails | manifest_args.py | 读取 agent.json 的 args | 各脚本 |
| production-guardrails | experience.py | 误报模式库 | 步骤 4、10 |
| production-guardrails | feedback-close.py | 驳回项入库并按 pattern 聚合 | 步骤 10 |
| eval-harness | collect-samples.py | 采集修复提交样本 | 评测 |
| eval-harness | extract-window.py | 按 hunk 取窗口材料 | 评测 |
| eval-harness | forward-bench.py | 前向基准 prepare/judge | 评测 |
| eval-harness | run-regression.py | 回归评测 | 评测 |
| eval-harness | fingerprint.py | 项目内容指纹 | 评测 |
| eval-harness | reviewbench-bridge.py | 外部基准桥接 | 评测 |
| eval-harness | run-samples.py | 样本批量跑分（评审缺陷引入态，评测链第三环） | 评测 |
| eval-harness | cve-corpus.py | CVEfixes 语料适配（发现式 schema → samples.json） | 评测 |
| eval-harness | plan-distill.py | 修复计划蒸馏（resolved 实例→家族级修复形状，接 code-task 材料） | 评测 |
| eval-harness | reviewbench-import.py | ReviewBench 语料导入（MIT，github 主域可达实测） | 评测 |
| eval-harness | swrenbench-import.py | SWRBench 适配（slim 语料 + 确定性/host 双评审臂 + LLM-judge 语义臂：score 中立基线 + review 跑批 + judge 双级 F1/语义命中对照（同片段 gt 归一化为组）） | 评测 |
| eval-harness | reviewbench-eval.py | ReviewBench 评测适配（golden 判定清单 + 确定性/宿主双评审器跑分 + 双指标） | 评测 |
| eval-harness | cve-dump-scan.py | CVEfixes SQL dump 流式扫描（gzip 不落盘） | 评测 |
| eval-harness | precision-report.py | 公开精度报告生成器（可选 --cost-report/--merge-audit 并入成本归一与合并率章节） | 评测 |
| eval-harness | precision-gate.py | 评审精度护栏（ReviewBench 固定语料：precision ≥0.65 + 基线趋势 + 样本/评审器一致性；语料不入库） | 护栏 |
| eval-harness | trace-export.py | trace JSONL → 评测集导出器（AB-01：span/score 聚合 + 质检；judge 重跑路径消费） | 评测 |
| eval-harness | prompt-optimizer.py | 提示优化循环（变体矩阵→评估协议→采纳闸不许降，AB-06） | 评测 |
| eval-harness | review-quality-gate.py | 评审响应质量门禁（D-053 对策：全 [] 批次须附 batch_note 依据 + evidence 覆盖率 + unparsed 率；judge 内置前置硬校验 rc=1） | 护栏 |
| eval-harness | eval-cost-report.py | 评测成本归一报告（耗时/轮数/编辑数/每 resolved 成本，缺失项如实 N/A） | 评测 |
| eval-harness | gold-sample.py、deepswe-fetch.py、deepswe-sample.py | SWE-bench gold 扩样单命令驱动（映射→下载→load→eval→report→台账，断点续跑；补丁前置完整性/结构双闸，malformed 不计 resolved） | 评测 |
| eval-harness | gate-corpus-build.py | gate 语料构建（derive 静态 F2P 推导/refine 基线回填+blocked 识别/notes D-048 附录生成） | 评测 |
| eval-harness | f2p-quality.py | F2P 数据质量预检 + 10880 选批（静态四检查，闸前拦截坏批） | 评测 |
| eval-harness | gate-run.py | gate 评测运行面驱动（prepare 种子 worktree/run 协议 v4 编码循环/judge 委托 live-sample/report 聚合；key 只过环境变量） | 评测 |
| eval-harness | agent-sample.py | SWE-bench **agent 侧**口径驱动器（收集编码循环补丁→结构完整性闸→预测装配→委托 gold-sample 评测→成本台账） | 评测 |
| eval-harness | pro-sample.py | SWE-bench **Pro** 口径驱动器（镜像就位→before_repo_set_cmd→候选补丁→pytest -rA→F2P/P2P 逐 node 对账；12 态状态机 + 补丁双闸 + 幂等台账，blocked_source 不静默丢；含 agent 补丁 predictions 通路） | 评测 |
| eval-harness | live-sample.py | SWE-bench **Live** 口径驱动器（本地源缓存/gitee/GitHub 降级→worktree→venv/test_cmds→pytest 判分；超时杀进程树，`--f2p-only` 部分口径单列不冒充 resolved，blocked_source 保留样本；runtests 判分支持 docstring 折行格式；`--export-sbcli` 导出官方 predictions 通路） | 评测 |
| self-iteration | doc-drift.py | 文档漂移十五问 | 步骤 0 |
| self-iteration | trigger-audit.py | Skill 触发词覆盖度静态体检（MUST/SOFT 判别力自检 + 跨技能抢词） | CI 门禁 |
| self-iteration | doc-freshness.py | 文档新鲜度对账（计数/版本/台账 vs 仓库真值；F10=BASELINE 行数基线 vs SKILL.md 实际行数，r158） | CI 门禁 |
| self-iteration | perspective-scan.py | 六视角反向验证 | 步骤 8 |
| self-iteration | dead-code-scan.py | 死代码扫描 | 步骤 0 |
| self-iteration | session-probe.py | 开局探针与分诊 | 步骤 0 |
| self-iteration | convergence-check.py | 收敛判定 | 自迭代 |
| self-iteration | pick-candidate.py | 改进候选排序 | 自迭代 |
| self-iteration | e2e-check.py | 端到端链路验证 | 自迭代 |
| self-iteration | coverage-gate.py | 覆盖率基线测量与对账（measure/check；0.5pp 容差，CI 单格） | CI 门禁 |
| self-iteration | secret-scan.py | 凭据形态扫描（7 规则 + 行内/文件级豁免 + stale + 脱敏） | CI 门禁 |
| self-iteration | license-check.py | 依赖许可证三档校验（import/subprocess/test-only） | CI 门禁 |
| self-iteration | release-gate.py | 发布闸（版本六处同步/文档真值/双跑/干净树与 tag 预检；只读不打 tag） | 交付 |
| self-iteration | bump-version.py | 版本/计数真值同步（六处版本 + 可选计数；--apply 落盘、失败零写入） | 发布 |
| self-iteration | round-gate.py | 轮次工作流闸（open 开局门/ close 收官门：台账对账/复盘产物/文档约定/双跑日志/收官行计数对账/SRE 预算结算，r159/r164；账本追加幂等守卫——同轮防双记，r186） | 步骤 0、复盘 |
| self-iteration | doc-structure.py | 文档结构判据（手册 §7.1 九条 + S10 脚本 UTF-8 stdout 自防御） | CI 门禁 |
| self-iteration | mutation-sampler.py | 变异采样器（AST 算子单点翻转 × 聚焦测试 → 杀手分数；mutmut Windows 不可用的 stdlib 自研替代；原文件 finally 恢复） | 按需抽检（r144 轮任务性质，非常设门禁——r165 登记修正） |
| self-iteration | latency-bench.py | scan 延迟基准与 SLO 门禁（三档合成 diff 实跑 38 规则臂 → p50/p95 分档；check 动词对 latency-slo.json 逐档断言 p95 上限，nightly 接线，r155） | CI 门禁 |
| repair | fix-plan.py | 修复分诊（可修复/转人工） | 修复阶段 |
| repair | fix-patch.py | 补丁生成（unified diff + manifest） | 修复阶段 |
| repair | fix-apply.py | 补丁落盘（五道闸 + 回滚 + undo） | 修复阶段 |
| approval | approve-plan.py | 审核人闸 1：范围裁定 → 修复工单 | 修复阶段 |
| approval | approve-patch.py | 审核人闸 2：补丁准出 → 批准书 | 修复阶段 |
| orchestrator | pr-kit.py | 评审结果 → PR 标题/正文/行内评论包 | 交付 |
| orchestrator | report-adapter.py | 报告输出适配器（三维度：详细程度/受众/行业术语，内置 executive/engineering/audit preset） | 交付 |
| orchestrator | pr-publish.py | 经托管 API 创建 PR（token 走环境变量，不合并） | 交付 |
| orchestrator | github-poster.py | pr-kit 行内评论包 → GitHub PR 行内评论（REST，token 环境变量，422 如实计失败，dry-run） | 交付 |
| retro | retro-ledger.py | 坑台账（事件+产物痕迹去重合并；按 type 过滤完成记录，--archive 带理由更正） | 复盘阶段 |
| retro | retro-report.py | 轮报 + 下一轮改进候选（真仓强制 --round N：缺省自动编号在真仓被护栏拒绝，r156） | 复盘阶段 |
| retro | memory_retrieval.py | 记忆检索（TF-IDF + cosine，供 few-shot 注入） | 编码循环 |
| retro | compact-memory.py | 记忆压缩与老化（TF-IDF 聚类 + 冷记忆清理） | 复盘阶段 |
| retro | memory-pipeline.py | 记忆三级管线（抽取→合并决策→检索；UPDATE/ADD 双臂，AB-20） | 编码循环 |
| director | org-route.py | 科层调度：分派/RACI/能动性下发 | 全程 |
| director | case-match.py | 案例库 v2：链接型档案匹配与入库 | 全程 |
| director | research-brief.py | 疑难杂症研究简报（检索由宿主联网） | 全程 |
| director | org-scorecard.py | SRE 错误预算结算（超限整改冻结；r164 起并入 close 门机械执行，WARN 关注不阻断/EXCEEDED 判红） | 每轮末尾（close 门强制） |
| director | case-archive.py | 档案员：成败双轨案例摘抄归档与 Git 发布 | 全程 |

## 互操作层（2026-10-24 新增，不计入 51 脚本清单）

## 工程基座（2026-10-24 转向后新增目录）

- `engines/`——复用引擎适配层（ruff_adapter.py：scan/fix-dry/matrix/
  clean-fp；能力矩阵 ruff-matrix.json 入仓：973 规则/482 可修复/250 safe（r200 随 ruff 0.17.6 重分类同步）；
  引擎一律 subprocess+JSON，修复产物经五道闸）；库函数 ruff_fix_text/
  ruff_scan_codes 供修复链 import。
- `engines/libcst_adapter.py`——LibCST codemod/重构引擎（Phase 2A 计划项，
  v1.23.0 落地）：scan/fix-text/fix-dry/matrix/clean-fp 五子命令；codemods
  ref-eq-none（==None→is None）与 ref-in-keys（in d.keys()→in d），结构
  保序、语义等价；能力矩阵 libcst-matrix.json 入仓；库函数自举子进程到
  .venv（全局解释器 import 安全）；发现前缀 libcst:<code>，与 ruff 同链
  分诊/混合修复/闸五复扫；同文件双引擎保守转人工。
- `engines/astgrep_adapter.py`——ast-grep 多语言 AST 模式引擎（Phase 2B，
  v1.39.0 落地，v1.44.0 规则集扩展到 29 条）：scan/fix-dry/matrix/clean-fp
  四子命令；内置规则按三族组织——安全类（innerHTML 赋值 / document.write /
  eval / 正则注入 / 原型污染 / setTimeout 字符串参数）、代码质量类
  （console.log / debugger / 空块 / var / 空 catch / 宽松相等 / throw 字符串
  等）、类型卫生类（any 断言 / 空接口 / typeof-undefined 等），跨 JS/TS +
  Python；js-implicit-global 因误报率过高下线；扫描超时 30 秒防挂死；能力
  矩阵 astgrep-matrix.json 入仓；发现前缀 astgrep:<code>，与 ruff/libcst
  同链分诊（fix-plan 按引擎后缀白名单分诊 .js/.ts/.py）；引擎矩阵第一枚
  多语言引擎（v2 覆盖 JS/TS + Python）。
- `engines/testgen.py`——测试生成引擎（Phase 3A）：skeleton 确定性骨架
  （loop 零依赖冒烟 / hypothesis 属性模板两风格）、llm 宿主协议真用例、
  verify pytest 验证（生成物必须通过才算数）、patch 新文件补丁；Pynguin
  （LGPL）仅 subprocess 基线对照。
- `agent/`——编码循环（repo_map.py tree-sitter 符号地图 + **任务关键词候选文件**
  + **按定义点取窗**、edit_formats.py SEARCH/REPLACE 唯一命中（空 SEARCH 仅
  用于新建不存在的文件，自动补尾换行）、code-task.py read/list/edit/done 循环 +
  worktree + 宿主协议（补丁出 `git diff HEAD` 前先 `git add -A -N`，否则新建
  文件不进补丁、即时校验误报 file_missing——round-46 实踩）；
  **上下文工程**：稳定前缀（prompt
  caching）+ 工具输出外置（超 20000 字符/500 行写 tool-outputs/）+ 历史压缩
  （280K tokens 触发、保留最近 12 条）+ 记忆 few-shot 注入（--memory-file /
  CRA_MEMORY_FILE，默认关闭）+ stderr 流式进度帧；trace.py 输出 Langfuse
  兼容 JSONL 埋点；运行于 .venv Python；**不直接写被审仓库**，补丁走修复链；
  **阶段四 4.1（v1.59.0）**：`phases.py` 三角色状态机（locate 只读 → fix
  可编辑 → verify 只读裁决）——角色动作面门禁、机械测试结果优先于 verify
  自评、返工上限后升级（ESCALATED 不写 manifest）、决策台账 `phases.json`
  跨 `--resume` 持久化；编辑即时校验未过时**回滚本轮改动**（工作区保留
  已应用编辑，提示词同口径）；
  **阶段四 4.2（v1.60.0）**：repo map 与编辑校验扩到 TS/TSX/JS 与 Go
  （tree-sitter-typescript / tree-sitter-go，MIT）；code-task 测试引擎自动
  识别（--test-cmd > go.mod > package.json/npm/node 内置测试 > pytest，
  manifest 记 test_engine）；
  **阶段四 4.3/4.4（v1.61.0）**：`workspace.py` 三档工作区统一接口（本地
  worktree / 容器 docker exec / 远程 ssh BatchMode；`--workspace
  local|container:<image>|remote:<target>`，未知规格 code=2，远程档在
  code-task 显式拒绝、只留接口与假壳契约）；`review_loop.py` 评审闭环
  （自评臂 + 他评臂 ruff/ast-grep/OCR 文件覆盖/命令评审器，两臂去重后按
  「同文件 + 行号 ±2」配对，`diff_rate` 超阈值或高严重度或覆盖缺口或外部臂
  全不可用一律转人工；`--review --review-threshold --review-cmd --review-ocr`，
  NEED_HUMAN 不写 manifest、明细落 review.json）；
  **ACI 阶段二（v1.54.0）**：search 按「定义>引用>注释→候选路径距离」排序；
  list 只读目录树（限深 3 / 条目上限 200 / 越界拒绝）；测试按改动走 A/B 映射、失败回退
  全量、1/3 确定性抽检；编辑后 tree-sitter+ast 双网语法校验（Python 双网、
  TS/Go 单网；非末轮退回）；
  repo map `--rank graph` 图排序默认关（真实 Top-8 无增益，见 D-031）；
  `agent/legacy_compat.py`——老仓库（需更老 Python）运行垫片（sitecustomize
  注入，不改被审仓库/不改全局解释器）。
- `llm/`——模型提供者抽象（provider.py：openai 兼容 / host 宿主文件
  协议；治理壳 stdlib）。
- 依赖：pyproject.toml + .venv（Python 3.12，uv 清华镜像）；fingerprint
  覆盖 engines/llm/agent/mcp 与 pyproject。

| 文件 | 作用 |
|---|---|
| mcp/review_mcp.py | MCP stdio 服务器：16 工具（run/scan/plan/feedback/approve/fix/retro/director/testgen/coding/refactor/apply/submit/status/cancel/purge，submit+status+cancel+purge 为 D-055/D-176/D-180 异步作业），JSON-RPC 2.0（2025-06-18；2026-11-14 对账 4→12，round-154） |
| interop/deepseek-harness/cordis.yml.example | dsh 接线：@deepseek-ai/dsh-mcp-client stdio 拉起 MCP 服务器 |
| interop/deepseek-harness/README.md | 两种宿主（dsh / ZCode）接线说明与安全模型 |

接入依据 DeepSeek Harness 公开文档：插件=insert 块（docs/user/develop/basic），
外部能力走第一方 MCP 桥（packages/mcp/mcp-client，stdio，工具名
mcp__<serverName>__<raw>）。ZCode 侧经 .zcode-plugin/plugin.json 的
mcpServers 暴露同一服务器；协议契约见 BASELINE.md「互操作契约」。

## 维护红线（八条易错点）

1. 扫描 diff 的正则不得用行首锚定。
2. 剥 diff 前缀时只保留 + 行，否则符号计数翻倍。
3. 跨编号体系对齐只用不可变标识（sha），不用序号。
4. 汇总层必须输出有效样本数；分母错了不会报错只会算错。
5. 两组数字完全相同 = 一定是 bug。
6. 每个检查器都要有反向验证（造违规样例确认抓得住）。
7. 改结论时搜索所有引用处（README/SKILL.md/BASELINE 可能各有一份）。
8. 结论要标证据等级：观测 ≠ 因果；单变量实验 ≠ 独立复现。
