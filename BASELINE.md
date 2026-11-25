# BASELINE — 契约基线（2026-10-24）

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：总监 + 迭代官 ｜ **主导模式**：参考
> **权威范围**：见下方原始头注详述
> **不是权威**：命令用法与参数（→ docs/06-operations/使用说明与配置.md、docs/DEVELOPMENT.md）；契约变更的裁定（→ docs/DECISIONS.md D-0xx）；逐轮版本沿革（→ docs/BASELINE-HISTORY.md）
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 文档状态：维护中（契约权威源）｜创建：2026-10-24 ｜ 权威范围：全部固定契约与 SKILL.md 行数基线（现行卷；版本沿革见 `docs/BASELINE-HISTORY.md`，v1.87.0 起分卷）。

本文件记录项目全部固定契约。改动任何一项，必须同步搜索 README.md / AGENTS.md / SKILL.md / tests 的所有引用处。

## 依赖白名单契约（2026-10-24 立宪修订，v1.14.0）


- 分层策略：治理壳（skills/*/scripts、llm/）仅标准库，零依赖可分发；
  引擎层（engines/、agent/）允许白名单第三方。
- 许可证分级：MIT/Apache/BSD 可嵌入 import（当前：ruff、libcst、
  tree-sitter 系、ast-grep-py）；MPL-2.0 仅 test-only（hypothesis 入
  optional-dependencies.dev，不进运行时 import 链、不随治理壳分发）；
  LGPL（semgrep 引擎、rope、pynguin）仅
  subprocess 隔离，禁 import；GPL 系禁入。（MPL 边界：D-022 方案 1，
  2026-10-31 总监批准，与 license-check 三档判定口径一致）
- 新增依赖须总监批准，登记 pyproject.toml（含许可证注释）；LGPL 组件入
  [project.optional-dependencies].isolated，不进运行时 import 链。
- 依赖安装于项目根 .venv（uv/pip + 国内镜像）；fingerprint 排除
  .venv/llm-tasks/__pycache__。

## 引擎能力矩阵契约（v1.14.0 立骨架，v1.16.0 填充实数）


- 每个引入引擎在 engines/ 有 adapter，并声明能力矩阵：可自动修复的
  规则集、风险级（safe/unsafe fix 分级启用）、目标语言。
- **Ruff 实数（engines/ruff-matrix.json 入仓）**：973 规则 / 482 可修复
  （fix_availability Always+Sometimes）/ 250 safe（Always only）；引擎经
  subprocess+JSON 调用（pip 包无 Python API，实测）；扫描映射
  rule_id=ruff:<code>，F821→高、F811/F841→中、其余→低；fix-dry 在临时
  副本真跑 --fix 后 difflib 产 a/ b/ LF 补丁。
- 修复链接擎化（v1.16.0）：fix-plan 按矩阵分诊 ruff: 码（engine=ruff）；
  fix-patch 自研变换后对同文件跑引擎修复（混合规则同补丁），manifest 记
  engine 与 before_codes（修复前默认集码集）；闸五按引擎复扫——修复码
  消失且 after_codes ⊆ before_codes（无新增码）才过闸；approve-patch 结构
  检查允许「新增行与删除行相同」的 import 移动（ruff isort 重排），
  真新导入仍受白名单约束。
- 引擎修复产物不经自研白名单豁免：与机械补丁同链（工单→补丁包→
  批准书→五道闸→行为回归）落盘；引擎在干净样例上的误报（engine_clean_fp）
  是错误预算口径，超限整队整改冻结。
- **LibCST 重构引擎实数（engines/libcst-matrix.json 入仓，v1.23.0）**：
  2 codemods 全可修复全 safe——ref-eq-none（==None→is None / !=None→
  is not None，PEP 8，保序）与 ref-in-keys（in d.keys()→in d，仅单目标
  无参调用）；结构保序（LibCST 保留格式注释），语义等价；adapter 五子命令
  scan/fix-text/fix-dry/matrix/clean-fp（fix-text 为 JSON 信封管道接口，
  消费方 fix-patch）；libcst 仅 .venv 可用——库函数 libcst_fix_text/
  libcst_scan_codes 自举子进程到 .venv（全局解释器 import 安全，顶层零
  libcst 依赖）；扫描映射 rule_id=libcst:<code>；fix-plan 矩阵分诊泛化为
  多引擎表（ruff:/libcst: 各读各矩阵）；fix-patch 同文件双引擎保守转人工
  （混合变换顺序无契约）；闸五 _verify_libcst 复扫口径与 ruff 一致
  （修复码消失且 after ⊆ before）；clean-fp 干净样例误报计入错误预算。
- **ast-grep 引擎实数（engines/astgrep-matrix.json 入仓，v1.39.0 落地）**：
  29 条内置规则 / 2 可修复 / 2 safe，覆盖 JS/TS 与 Python；扫描前缀
  rule_id=astgrep:<code>，与 ruff/libcst 同链分诊、混合修复与闸五复扫；
  修复产物同样经工单→补丁包→批准书→五道闸。

## 编码循环契约（agent/，v1.17.0）


- agent 层运行于项目 .venv Python（tree-sitter 依赖）；治理壳仍全局 py。
- repo_map.py：tree-sitter 符号地图（定义 + 引用计数 + 热度排序，
  Aider 思路），render_material 在字符预算内渲染给 LLM。
- edit_formats.py：SEARCH/REPLACE 块（Aider 验证格式）；SEARCH 必须
  全文件唯一命中（0 或 >1 均拒绝，不给模糊落点）；替换仅动命中片段。
- code-task.py：任务→（read/list/edit/done 动作；search 按定义>引用>注释与
  候选路径距离排序；list 只读、限深 ≤3/≤200 项/越界拒绝）→worktree 编辑→
  仓库测试（pytest；有改动时先跑 A/B 映射的测试子集，未映射或子集失败回退
  全量，1/3 确定性抽检再跑全量，未抽检的 pass 标注「未抽检」）→语法双网
  （tree-sitter ERROR + ast.parse）→产出 edits.patch（a/ b/ 头 LF）+
  task-manifest（engine=agent；含 rank/test_scope）+ task-report.md；上限
  --rounds；LLM 走 llm/provider 宿主协议（WAIT_HOST_LLM 退出码 1 → 宿主填
  llm-tasks → --resume）。
- repo_map.py 另有 `--rank graph`（import 图 + 个性化 PageRank 补充邻居），
  **默认 refs**；真实语料 Top-8 无增益（round-53，D-031），仅作显式实验开关。
- **治理红线：编码循环不直接写被审仓库**——编辑发生在临时 worktree，
  补丁落盘必须走修复链（工单/批准书/五道闸）。

## 风险评分契约（risk-scoring/scripts/score.py）


- 权重：规模 0.3 / 耦合 0.4 / 稳定 0.3，固定不得调整。
- 规模分：行数档（<=50→1,<=200→2,<=500→3,<=1000→4,否则5）与文件档（<=1→1,<=3→2,<=8→3,<=15→4,否则5）取大；modules>1 直接抬到 5。
- 耦合分：modules 与 callers 用文件档各查取大；high_impact 非空 +1（上限 5）。
- 稳定分：history_3m/history_12m 用文件档各查取大；has_hotfix 或 has_revert +1；intent_deviation +1（上限 5）。
- 综合分 = 加权和，保留 1 位小数；等级 >=4.0 高、>=2.5 中、否则低。

## 评审维度契约（multi-agent-review/scripts/dispatch-plan.py）


- 评审维度：7 个。全集固定：正确性与逻辑缺陷、跨文件影响、回退风险与影响面、测试覆盖、性能与资源、安全与敏感信息、意图一致性。
- dimensions_enabled 与 dimensions_skipped 恰好划分全集，skipped 必须带 reason。

## 硬规则契约（multi-agent-review/scripts/deterministic-rules.py）


- 硬规则共 38 条 = 凭据 8 + 危险函数 15 + 语言 15。
- 污点流引擎另计（不占 38 口径）：sources/sinks 经总监治理的
  taint-config.json 配置化（缺省内置 eval/exec/os.system/os.popen 四汇点，
  坏配置或缺失回退内置缺省并写 stderr 警告）；输出 findings 中 rule_id
  前缀 taint-，rule_count 字段仍为 38，taint_rules 字段=生效汇点数。
- 跨文件两遍分析（taint-cross.py，2026-10-24 落地案例 ed5c32b6187d）：
  pass1 对顶层函数生成过程间摘要（param→sink / param→return）；
  pass2 解析 import 别名追踪调用方，实参污染命中摘要即在调用方行报流，
  param→return 命中则返回值继续传播（链式流）；--diff 可仅报变更文件。
  覆盖：直接流/经返回值链式流/from-import 别名；局限：仅顶层函数摘要、
  文件级污点集近似、无清洗点建模、不追循环携带。
- 跨文件引擎接入主线（2026-10-24）：runner step2 在确定性规则后调用
  taint-cross.py --root <repo> --diff <patch> --max-files 200，发现并入
  facts（经 RULE_DIM 流入安全维度）；引擎失败/超限降级不阻塞，审计如实记录。
- PR 原生集成面（pr-publish.py，2026-10-24）：消费 pr-kit 素材 POST
  {remote}/repos/{repo}/pulls 创建 PR；token 只走 PUBLISH_GIT_TOKEN 环境
  变量不落盘；远端白名单 https 公网或 http 回环（测试），内网/明文拒绝；
  只创建不合并。
- 真实语料口径（2026-10-24 接入，1.13.0 勘误修正方向）：评测链第三环
  run-samples.py 的方向契约——评审「缺陷引入态」：确定性规则跑 fix 的
  反向 diff（git diff fix parent，与 prepare 的 git show -R 同口径，+ 行
  即缺陷代码）；跨文件污点在父版本 git worktree 上扫描（工作区=缺陷态）；
  方向由 TestRealCorpusChain 契约测试锁定（缺陷态带已知形态、修复态干净，
  扫错方向则断言落空）。
  修正后五仓聚合（urllib3/werkzeug/paramiko/pyyaml/requests，36 个月窗口）：
  **61 个真实修复提交，claimed 2、grounded 1 → recall 0.016 /
  precision 0.5**；类覆盖 逻辑58/空引用2/资源1；真命中仅 paramiko
  （缺陷态测试代码里的真实凭据形态）。**v1.11/v1.12 发布的数字
  （recall 0.04/precision 0.667）为方向错误测量，作废**（run-samples 曾
  扫修复后代码：该抓的漏报 + 修复新增形态被误记为命中，失败案例
  8b26199b0a71 已归档）。残余低 recall 是真实能力边界：确定性规则面对
  逻辑类缺陷（95%）无覆盖，出路是双意见评审器或新规则族。
  已知折衷：snippet 脱敏（红线）会丢失 gt 标识符致个别真命中无法 ground，
  不为指标放宽脱敏。工件留档 reports/real-corpus-urllib3/（w36 修正口径）。
- 公开精度报告（precision-report.py，2026-10-24）：编排 synth+fp 生成
  reports/precision-report-<date>.md/.json（指标+引擎指纹+污点配置摘要+
  方法论+如实局限+复现命令）；真实 CVE 语料接入前口径为合成基线。
- 危险函数 15 条按「eval、exec」拆为两条规则计。
- 命中密钥形态时 snippet 一律脱敏为 `<redacted>`。

## 边界类别契约（git-change-analysis/scripts/edge-detect.py）


- 边界类别：11 类。merge_commit、binary_file、lfs_pointer、empty_commit、submodule_change、
  worktree、shallow_clone、sparse_checkout、monorepo_multi_package、oversized_single_file、pure_rename。
- 每类必须给 evidence（未检出时给探查方法说明）。

## 自迭代契约（self-iteration/scripts/doc-drift.py）


- doc-drift 检查：15 问。孤儿脚本、副本分叉、死代码、行为覆盖、主线接入、退出码说明、审计覆盖、
  问数表述、硬编码行数、参数漂移、孤儿 references、行数基线、基线常量、args 覆盖、README 引用。
- 退出码 1 = 有待处理项；0 = 全绿；2 = 根目录非法。

## 评测契约（eval-harness）


- judge 命中阈值：finding 提到 >=2 个 fix 改动行的 >=6 字符标识符（--min-tokens 可调）。
- 单文件 gt 标识符 <2 的样本标 weak，单列，不计入 recall 分母；汇总层必须输出 valid_samples。
- 跨编号体系对齐只用 sha（fix_commit/evidence_commit），不用序号。
- 回归默认样本数 eval_regression_sample_size=5，预算 eval_regression_budget_minutes=10。

## 人工介入契约（production-guardrails/scripts/human-gate.py）


- 五类触发：preflight_rejected、budget_both_exceeded、conclusions_unconverged、
  verification_incomplete、downgrade_two_levels。
- 四类不算门：single_low_confidence_finding、material_insufficient、style_suggestion、test_suggestion。

## 退出码契约


- 0=成功；1=有可处理的问题（不是崩溃）；2=输入/环境错误；intent-parse 另有 3=需追问。

## SKILL.md 行数基线

由 doc-freshness F10 机械对账（r158：改 SKILL.md 行数必须同步本块，否则开局门/CI 直接判红，r157 实踩的机械拦截）。

- prompt-enhancement: 153
- git-change-analysis: 188
- risk-scoring: 116
- multi-agent-review: 404
- production-guardrails: 290
- eval-harness: 481
- self-iteration: 255
- orchestrator: 78
- code-review: 44
- repair: 55
- approval: 43
- retro: 92
- director: 76
- 清单总数 64（见 AGENTS.md 脚本清单）。

doc-drift.py 的行数基线问与硬编码行数问按本表核对实际行数；改 SKILL.md 必须同步改本表。

> 本节自 2026-10-25 起的版本沿革已分卷至 `docs/BASELINE-HISTORY.md`（v1.87.0 / round-86 起分卷）；本卷只保留现行契约与行数基线。

## 评测双指标契约（2026-10-24 勘误新增）


- judge 汇总必须同时输出 recall 与 precision，只报一个视为不合格。
- precision = grounded / claimed；claimed = 报了非空 findings 的样本数；
  grounded = 其中真命中（>=阈值标识符）的样本数。
- 细分字段：grounded_but_not_claimed、claimed_but_not_grounded。
- run-regression 的 current 指标同样携带 recall 与 precision。

## 反馈闭环契约（2026-10-24 勘误新增）


- feedback-close.py：驳回项（pattern/rule_id + dimension + count）逐项走
  experience.record，同维度同 pattern 累计 rejected_count、不新增条目。
- dispatch-plan.py --experience：读取经验库，命中的维度在输出
  evidence_levels 中给举证等级（常规/加强/严格，按 rejected_count 分档）。
- runner.py：run 目录写 totals.json（caps / steps / rounds / tokens / minutes_used），
  每步 checkpoint 时刷新，结束时总账与 args 上限一致。

## 编排器契约（orchestrator/scripts/runner.py，2026-10-24 优化新增）


- 预算四参数（max_review_minutes / max_total_rounds / max_verification_rounds /
  max_dynamic_dispatches）由 runner.py 代码强制扣减，不再只是文档建议。
- 断点：每步写 checkpoint，产物经 ARTIFACT_MAP 对齐；--resume 校验失败即 NEED_HUMAN。
- 评审器可插拔：deterministic（默认）/ llm（OpenAI 兼容；端点白名单 =
  公网 https 或本地回环，内网/明文拒绝）/ both 双意见（1.9.0）：确定性
  优先（已证事实），LLM 项 loc 去重后并入并标 source=llm；LLM 未配置、
  不可用或端点被白名单拦截 → 降级纯确定性不阻塞，note 如实标注；
  token 计入 totals。
- 反馈闭环：派发前下发误报模式；命中项降置信并标人工复核，查证不得升回高；
  --feedback 驳回项回流 experience 库。
- 交付双闸（report-check + schema-check）失败即 NEED_HUMAN，不静默降级。
- 断点回灌（1.15.0 修复既有缺陷）：resume-state.json 形状保真地保存各步
  返回值（diff 从 diff.patch 回灌）；产物摘要文件（step2_collect.json 等）
  是展示形状（如 files 为计数），不得用于回灌。--resume 从 run_meta 恢复
  reviewer，无需重复 --reviewer。

## 阴性与精度基线（2026-10-24 优化新增）


- 49 个评审脚本自扫发现数 = 0（此前 12 条自指误报已修：tokenize 数据区掩码 +
  Python 五条语言规则 AST 化 + 拼接值排除 + 规则文案去赋值号；repair/approval/
  retro/director 各脚本、pr-kit 与 MCP 服务器同口径零命中）。

## 复盘契约（retro/scripts，2026-10-24 业界对标新增）


- 迭代官为第四角色（独立于评审/修复/审核），每轮工作末尾运行；对仓库与
  产物只读，只写复盘目录。
- 台账 pitfalls.json：id=sha256(category|description) 前 12 位去重合并，
  保留历史状态；--close 结案须带可验证验收口径（`--close-note`，缺失即退出码 2，
  口径随 `closure_note` 落在台账里供下一轮审计）。「供下一轮审计」从 v1.32.0 起是
  机器动作而非人工抽查：`scripts/verify-closure-commands.py --run` 抽出全部口径命令
  逐条实跑，形状不合规（`unrunnable_shape`）、含占位符（`placeholder`）、口径就是
  「再跑一遍本检查器」（`self_reference`，永不执行）都算违规，退出码 1。
- 事件两类：轮内手工事件 JSON（category/description/root_cause/
  countermeasure/source）+ 产物痕迹（approval REJECTED → 补丁返工、
  apply-log ROLLED_BACK → 回滚、fix-manifest skipped → 转人工、
  experience entries → 误报）。回滚痕迹两路都采：`apply-log-history.jsonl` 的
  live 窗口（定长 50）加上窗口外折叠进去的 `apply-log-history.archived.jsonl`，
  只采 live 等于让被挤出的回滚自动销账。
- 轮报：round-<N>-report.md + 机器候选清单 round-<N>-candidates.md +
  改进候选（权重×数量排序：行为回归/回滚 3、补丁返工/误报 2、其余 1）；
  类别→对策知识库 CATEGORY_SUGGESTION 随复盘补充。轮号缺省 = **已有轮号最大值 + 1**
  （不是文件数 + 1：归档缺 round-9 时按个数会算出已存在的轮号并原地覆盖历史轮报，
  round-29 实踩）；显式 `--round` 撞到**已存在**的轮号时默认拒绝（退出码 2 +
  「拒绝覆盖历史」），确要重写这一轮必须明说 `--force`，stdout 如实打 `forced_overwrite`。
  开局检查单 next-round.md **归人工维护，report 不写**（历史上双写入者覆盖人工正文）。
- 迭代有效口径：open 数下降且同 id 坑不复发；同 category 反复新增 =
  对策无效，升级为结构改造候选。

## 调度与案例契约（director/scripts，2026-10-24 科层制新增，1.6.0 治理升级）


- 组织事实源 skills/director/org.json（v2）：三层管理（总监→团队首席→成员
  技能）；RACI 矩阵固定签字权（A 唯一）；每角色 error_budget（可计算阈值）
  与 initiatives（能动性注册表，分派回执必须下发）。director 只分派与验收，
  不代替团队执行；审核人独立。
- org-route.py：kind → 团队 + 首席 + 错误预算 + RACI + initiatives + 值班
  升级链（L1 首席/L2 总监/L3 人工）；未知 kind、组织非法、团队技能失联 →
  退出码 2。
- 案例库 v2（链接型档案）retro/cases.json：本地轻索引字段 = id/title/
  category/takeaway/verification/status + url 或 local_ref（至少一项，无
  链接不得入库）；根因/对策长文存链接指向的公开档案/仓库/本仓库轮报与
  验收测试；v1 旧字段（description/countermeasure）读取时自动映射。
  id=sha256(category|title) 前 12 位去重；入库三路：--ingest（须附链接）、
  --from-ledger（仅台账 closed，local_ref 指向台账）、--match 复用。
- 成败双轨（1.7.0）：案例带 kind=success|failure；失败案例（试过什么/为何
  失败/教训）与优秀案例同权入库与匹配，命中失败案例提示「避免同样路径」；
  from-artifacts 自动收 ROLLED_BACK 落盘台账为失败案例。
- 档案发布（1.7.0，case-archive.py）：详细摘抄渲染为 retro/archive/<id>.md
  （背景/摘抄/教训/验收/链接），本地档案仓 retro/archive-repo git 提交，
  可 --push 推送任意 Git 远端（URL 校验：仅 https/http 或 git@ 形式，拒绝
  localhost/环回/私有/保留地址；GIT_TERMINAL_PROMPT=0 禁交互凭据挂死）；
  推送失败不算存储失败（本地提交成立，pushed=false 如实回执）。
- 研究简报 brief-<id>.md/.json：约束（stdlib 只读/产物红线/验证口径）+
  中英检索词 + 已知案例 + 验收口径；脚本不联网，检索由宿主执行；结论
  落地形态必须三选一：配置扩展/测试补充/代码修改，只记不算完成。
- 行为级优化入口：taint-config.json（sources/sinks + _governance 治理
  元数据：proposed_by≠approved_by 两人规则 + cosign + 验证结果），改动必过
  污点反向验证 + synth 精度基线（1.0/1.0/0）。
- 主观能动性（代码级）：approve-patch REJECTED 与 fix-apply ROLLED_BACK
  自动调用 case-match 附 reuse_hints（查不到为空，键必须在；案例库故障
  不阻塞裁定/回滚本身）。
- org-scorecard.py：SRE 错误预算结算——repair 回滚率≤0.2、approval 每轮
  拒绝≤3、retro 未结坑≤8、research 无链接案例=0；WARN=整改关注、
  EXCEEDED=整队整改冻结（只修质量不扩功能）；无数据如实标 N/A。
- 凭据检测双轨：键名形态（password 赋值等）+ 值形态信号
  （sk-[A-Za-z0-9]{16,}、ghp_[A-Za-z0-9]{20,}、>=16 位大小写数字混杂随机串），
  占位符（*** / <redacted> / your_key_here 等）与注释区不报，键命中同行去重。
- 合成语料基线：`forward-bench.py synth --count 120 && fp --corpus` 应得
  clean 误报 0、precision 1.0、recall 1.0（确定性评审器口径；接入真实模型后此值是回归下限）。
- dispatch-plan 安全维度触发条件扩展：凭据/危险函数形态命中即启用（不再只看
  query/render/serialize/escape）。
- findings-check 支持 stdin（位置参数 -），供编排器流式校验。

## SWE-bench 契约（Phase 3B；首评 resolved，2026-10-25）


- 状态：**全链路打通并首评 resolved**。django__django-14999 经官方
  swebench 5.0.2 harness 判定 resolved（FAIL_TO_PASS
  test_rename_model_with_db_table_noop 转绿、PASS_TO_PASS 全保；
  run_id=cra-first2，单实例评测 25 秒）。n=1 为首跑基线，非代表性
  分数；扩样按实例逐个走已定型路径。
- 镜像获取（八加速器实测全灭后定型）：基础镜像 ubuntu:jammy 走
  mirror.nju.edu.cn ubuntu-base rootfs（30MB，57MB/s）docker import；
  task 镜像 sparse clone swe-bench-tasks 后用 Dockerfile.local 构建——
  官方 Dockerfile 的 BuildKit heredoc 与 import 基镜像不兼容（exit 127
  /dev/pipes/EOF_x），heredoc 块逐字抽 setup1.sh/setup2.sh + COPY/RUN
  bash 替代；apt/miniconda→NJU、conda 渠道/pip→TUNA（版本 pin 不变）。
- Windows harness CRLF 坑（已修）：harness 写 eval.sh/model patch 用
  文本模式被翻译成 CRLF 再进容器，bash 全线炸（表象 ambiguous failure
  无 infra failure）；.venv 内 run_evaluation.py 两处补 newline="\n"
  （约 L291/L360），**swebench 重装/升级后必须重打**。
- 数据集：SWE-bench/SWE-bench_Lite（HF 2.0 格式，image/eval_script 列；
  princeton-nlp 旧格式 KeyError: image）；HF_ENDPOINT=hf-mirror.com
  必设；predictions 必须含 model_name_or_path 字段。
- 完整命令序列与实录见 agent/swe-workflow.md；四阶段已代码化为
  `agent/swe_run.py`（v1.22.0：prepare 自动 heredoc 抽取 + 国内源改写 /
  build / eval 含 CRLF 自检闸 / report 解析实例级 report.json）；
  分数用于校准，治理是差异化。

## LLM 提供者契约（llm/provider.py，v1.15.0）


- 后端选择（select）：显式 CRA_LLM_PROVIDER=host|openai|none 优先；未显式
  且已配置 REVIEW_LLM_BASE_URL+REVIEW_LLM_MODEL → openai；否则 none
  （保持既有降级语义：不可用不阻塞评审）。
- openai 后端：泛化自 runner._llm_call——SSRF 白名单（公网 https 或回环；
  内网/私有/保留地址拒绝）、重试（retry_max_attempts/retry_backoff_base_seconds
  读 agent.json args）、usage.total_tokens 经 on_tokens 回调计入 totals。
- host 宿主模型后端（桌面端会话内推荐，零 API key）：提示词文件进出协议——
  complete() 计算 id=sha256(system+"\\0"+user)[:12]，写 <run_dir>/llm-tasks/
  <id>.prompt.md 与 .meta.json（status=waiting）后抛 HostLLMPending；宿主模型
  按 SKILL.md 义务填写 <id>.response.md（仅 JSON 数组，可带代码栅栏），
  调用方 --resume 续跑；续跑时同材料 → 同 id → 命中既有 response 直接返回
  （幂等，不重复等待）。host 模式 token 计 0（无法观测），note 如实标注。
- WAIT_HOST_LLM 状态：退出码 1（有可处理的问题）；回执含 llm_task（prompt
  路径）与 llm_response（待填路径）；审计记录"等待宿主模型"。
- 响应消费纪律：LLM 输出仍须过 findings-check/证据锚定才可采纳（误报治理
  不因后端而放松）；响应文件留档于 run 目录供审计。

## 互操作契约（2026-10-24 DeepSeek Harness 调研新增）


依据 dsh 公开文档（万物皆插件 / Cordis / 第一方 MCP 桥）落地的接入层，目录
`mcp/` + `interop/deepseek-harness/`，不占用 32 个评审脚本清单名额：

- MCP 服务器 `mcp/review_mcp.py`：stdio 换行分隔 JSON-RPC 2.0，协议版本
  2025-06-18，serverInfo.name=dev-agent；initialize/ping/tools/list/
  tools/call 必答，resources/list、prompts/list 回空，通知帧不回复，坏帧回
  -32700 后继续，未知方法回 -32601。
- 四工具只读固定名：code_review_run（repo+range 或 resume 二选一路径）、
  code_review_scan（path/diff_path 二选一）、code_review_plan（diff_path 必填）、
  code_review_feedback（findings_path+experience_path 必填）。
- 审核人工具：code_review_approve（mode=scope 需 findings_path；mode=patch 需
  order_path+manifest_path；repo/out_dir 必填；退出码 1=REJECTED 不算工具错误）。
- 迭代官工具：code_review_retro（mode=collect 坑台账需 out_dir，可选
  events_path/scan_paths/close_id；mode=report 轮报需 out_dir）。
- 总监工具：code_review_director（mode=route 分派需 kind，mode=match 案例
  匹配需 problem，mode=brief 研究简报建议给 description 与 out_dir；
  out_dir 缺省项目 retro/）。
- 修复两工具：code_review_fix（order_path+repo+out_dir 必填，只吃工单）；
  code_review_apply（manifest_path+repo 必填，--apply 需 confirm=true 且
  approval_path；undo=true 走 --undo；isError 语义为非 0 退出码均算错误）。
- 重构工具（v1.24.0）：code_review_refactor（mode=scan 需 file，可选
  rel/codes；mode=fix-dry 需 repo+rel+out，可选 codes；子进程经
  VENV_PYTHON 调 engines/libcst_adapter.py（libcst 仅 .venv），退出码 1
  不算工具错误）；落盘仍走修复链，本工具只产发现与补丁建议。
- isError 语义：脚本退出码 2 → isError true；退出码 1（NEED_HUMAN）不是错误。
- 子进程：显式参数列表 + shell=False，脚本目标白名单常量，超时 run 600s 其余 60s。
- dsh 接线为声明式：interop/deepseek-harness/cordis.yml.example 用官方
  @deepseek-ai/dsh-mcp-client（stdio，serverName=code-review，工具名
  mcp__code-review__<tool>）拉起本服务器；不随附 spawn 型 TS 源码（本地安全
  策略禁止，原生变体做法记录于该目录 README）。
- ZCode 清单：plugin.json version>=1.19.0，mcpServers["code-review"] 指向
  mcp/review_mcp.py，与 marketplace.json 版本一致。

## 测试生成契约（engines/testgen.py，v1.18.0）


- 四模式：skeleton（确定性 AST 骨架，--style loop 零依赖纯 pytest 可移植
  / hypothesis 属性模板需目标环境装 hypothesis）/ llm（宿主协议真用例，
  WAIT_HOST_LLM 退出码 1 幂等续跑，义务=具体断言不是冒烟）/ verify（生成
  物复制进临时目录跑 pytest，**通过才算生成成功**——错误断言必须被拒）/
  patch（新文件补丁 /dev/null→b/rel，git apply 可创建文件）。
- 未类型化函数出 skip+TODO 占位（不假装覆盖）；verify 是生成的验收闸，
  生成测试喂行为回归闸（五道闸第五道）。
- Pynguin（LGPL）仅 subprocess 基线对照（isolated 依赖层），不进产品链。

## CVE 语料契约（eval-harness/scripts/cve-corpus.py，v1.18.0）


- 数据源：CVEfixes v1.0.8（Zenodo 13118970，zip 内 SQLite，约 12GB——
  一次性下载属运维步骤，网络已验证可达）。
- 发现式 schema：不锁定列名，识别含提交哈希/仓库 URL/文件列的表；
  语言后缀过滤；同提交文件聚合（上限 20）；输出 run-samples 兼容
  samples.json（defect_class=cve）。
- parent 解析：--resolve 需 --repos-dir（owner__name 布局），git 取父
  提交；无克隆/解析失败标 pending_parent，run-samples 如实跳过。
- 安全口径：zip 成员仅纯文件名（白名单正则）且解压目标 mkstemp 生成
  （零路径拼接）；sqlite 表/列名经标识符白名单校验后引用；值参数化。
- **Phase 3B（SWE-bench）首评完成**（2026-10-25）：Docker 就绪后全链路
  打通，django__django-14999 官方 harness 判定 resolved（详见 SWE-bench
  契约节）；镜像获取/CRLF 两坑入台账（27→29 条）。
- 互操作层自身纳入自扫：mcp/review_mcp.py 硬规则零命中。

## 审核人契约（approval/scripts，2026-10-24 三方分立新增）


- 审核人独立于评审团队与修复团队：不产发现、不出补丁、不落盘；
  跨团队协作只走 CLI 与 JSON 产物；任何一方不得自审自批。
- 闸 1 范围裁定（approve-plan.py）：调用修复团队分诊取白名单分类，叠加
  --severities 政策（缺省全放行），签发 work-order.json（order_id=base_sha
  前 12 位；approved 条目带 severity；拒绝项必带原因；路径一律归一化为
  仓库相对路径）。凭据类必拒（补丁会复制明文，违反硬约束 5）。
- 闸 2 补丁准出（approve-patch.py）：六项独立核验——工单绑定（补丁触及
  文件与规则均出自工单）、三方基线一致（工单/补丁包/HEAD）、git apply
  预检、补丁新增行硬规则零命中（防补丁引入缺陷或明文凭据）、路径安全、
  结构不变量（与值形态扫描去相关的第二意见：新增 import 限于
  sys/json/re/math 白名单，新增行禁裸 except）；
  签发 approval.json，manifest_sha256 绑定补丁包字节。
- 批准书只对送审时字节有效：manifest 任何变动 → sha256 失配 → 落盘拒绝，
  必须重新送审。

## 修复契约（repair/scripts，2026-10-24 新增）


- 白名单 5 类（仅 .py，fix-plan.FIXABLE_RULES 与 fix-patch.AUTO_RULES 成对维护，
  测试断言一致）：lang-mutable-default（None 哨兵+卫语句）、lang-empty-catch
  （收窄 Exception + stderr 记录，兼容扫描器的同行/AST 两种报行口径）、
  lang-closure-late-bind（循环变量默认参数绑定）、lang-is-literal-misuse
  （==None 改 is None / is 字面量改 ==）、dang-yaml-load（单参单行改 safe_load）。
  其余发现一律 manual：凭据类补丁会复制明文，违反硬约束 5。
- 补丁先行：修复团队唯一施工依据是审核人工单（fix-patch.py 只吃
  --order），只写 --out 产物目录（LF 行尾，CRLF 会使 git apply 失配）；
  绝对路径发现先归一化为仓库相对路径，越出仓库根拒绝。
- 落盘五道闸（fix-apply.py，唯一写仓库脚本）：审核人批准书（verdict=
  APPROVED + manifest_sha256 绑定 + 工单/基线一致）→ 工作树干净 →
  HEAD==base_sha → git apply 预检 → 行为回归（逐文件重扫原 rule_id 全
  消失、无新增规则、总数不增；发现仓库测试即执行 pytest，失败等同验证
  失败；无测试/无 pytest 时跳过并给据）；任一失败自动回滚并删分支，
  退出码 1 state=ROLLED_BACK；APPLIED 与 ROLLED_BACK 均写 apply-log.json
  （含 tests 状态，供迭代官采集）。
- 状态机：PROPOSED（预检/前置不满足）→ APPLIED（review-fix/<id> 分支，
  不自动合并）→ UNDONE（--undo 回原分支删修复分支）。
- MCP 侧 confirm 闸：code_review_apply 仅 confirm=true 且持批准书才 --apply；
  其 isError 语义为非 0 退出码均算错误（区别于评审工具的退出码 1 不算错）。

> 本节自 2026-10-25 起的版本沿革已分卷至 `docs/BASELINE-HISTORY.md`（v1.87.0 / round-86 起分卷）；本卷只保留现行契约与行数基线。

## 测试预算


- **红线语义（D-041，2026-10-30 批准，round-67 起生效）**：300s 总时长
  降级为**观测线**（逐轮照记、不升级处置）；**600s 为硬挂死护栏**（套件以
  `timeout 600` 包裹，超时判红按挂死处置）；单测预算每断言 60s 保留；
  升级触发=连续 3 轮 >450s 或任一单项超线；环比上一轮中位 >20% 须归因。
  历史 300s 记录是当时事实，不回改。
- 每条断言 60 秒内跑完；round-33 收官全量实测 **276.900 秒 / 275.028 秒两次一致**（305 项，
  2026-10-26；历史沿革：round-32 曾测 291.221 / 290.289 秒两次一致（当时 302 项）、round-31
  曾测 265.104 / 313.198 秒两次一致（当时 291 项）——同一份代码
  沿革：「<= 5 分钟」在仓级门禁脚本改为真扫本仓产物后不成立（涨到 8 分钟），round-29 把
  tests/test_scripts.py 两处夹具的整树 copytree 换成带忽略清单的源码快照（SNAPSHOT_IGNORE +
  snapshot_repo），实测 512–528 秒 → 222–243 秒；round-30 涨到 235–262 秒是新增的
  临时快照生命周期套件（tests/test_tmpspace.py 9 例，含只读树删除与异常退出子进程）
  与 C 路 / 覆盖闸门 / 落盘台账的契约断言，加上套件启动时一次带标记目录扫描，
  仍在 5 分钟红线内。口径变化如实记录，不悄悄改红线。
  **round-31 复测定案**：round-30 留的「越线归因未定」已按同一负载口径复测——五次实测
  261–318 秒、两次越线三次未越，新增测试实测只占约 20 秒（结案口径实跑 4.0 秒 + 落盘
  轮转 8.8 秒 + stdin 契约 7 例约 7 秒），按上轮高水位 261.9 秒推算代码量贡献约 280 秒
  上限；越线的那两次与未越线的几次**代码量相同**，差异只能来自跑间抖动/机器负载。
  结论：5 分钟红线**保留**，判定口径补一条明文——**连续两次同负载超线才升级处置**
  （收敛代码或正式改线），单次超线只入册记录并复测，不把抖动写成代码量、也不悄悄改线。
- **两次一致才认绿**：同一模块至少两次一致复跑才判绿，且跑之前确认没有并发重负载
  （runner 的分钟级评审预算被挤占时会「正常收束但产出更少」，退出码仍是 0）。
- **解释器契约**：全量测试必须用项目 `.venv`（Python 3.12）。`tests/test_agent.py`
  会 import 引擎层 `agent/repo_map.py`（tree-sitter 系），全局 python 下 14 例
  `ModuleNotFoundError` 会伪装成代码回归（round-28 实踩）。
- 指纹命令：`python skills/eval-harness/scripts/fingerprint.py --root .`（改 AGENTS.md/skills/agent.json args 后指纹必变）。

> 本节自 2026-10-25 起的版本沿革已分卷至 `docs/BASELINE-HISTORY.md`（v1.87.0 / round-86 起分卷）；本卷只保留现行契约与行数基线。
