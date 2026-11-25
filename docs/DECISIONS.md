# 关键决策记录（ADR）

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：总监 ｜ **主导模式**：记录
> **权威范围**：见下方原始头注详述
> **不是权威**：决策的执行进度（docs/PROGRESS.md）
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 创建：2026-10-28 ｜ 状态：维护中 ｜ 权威范围：不可逆或高成本决策的
> 「背景 / 候选 / 决策 / 代价 / 状态」。
> **使用规则**：决策做出时立即追加；旧决策被推翻时**不删除**，只把状态改为
> 「已被替代（链向新编号）」或「已废止（注明原因）」；每条必须至少有一个
> 备选方案与真实取舍，禁止写成事后美化。
>
> **证据等级说明（诚实标注）**：D-001..D-010 为 2026-10-28 一次性事后重建
> （据 BASELINE 沿革、轮报与代码），日期取版本落地日，等级「观测」；
> D-011..D-014 为当轮记录。

## 决策索引（D-001..D-053，含 D-049 两条：提案 + 裁决）

> 快速定位用。完整论证、选项、裁决与证据见各条正文；
> 「轮次/版本」列仅标注标题自带信息（无标注者见正文头注）。

| ID | 摘要 | 轮次/版本 |
|---|---|---|
| D-001 | 写被审仓库的唯一入口：五道闸 + 批准书 | — |
| D-002 | 治理壳零依赖、引擎层白名单的分层依赖 | — |
| D-003 | 复用成熟引擎，而不是自研全部规则 | — |
| D-004 | 评测双指标 + 有效样本分母 | — |
| D-005 | 邻近测试 C 路谓词改为「引用形状」 | — |
| D-006 | 全量测试 5 分钟红线保留，判定口径补「连续两次同负载」 | — |
| D-007 | 结案口径从「形状对」升级为「机器全量实跑」 | — |
| D-008 | 模糊意图三键 + 阻塞才追问 | — |
| D-009 | 多候选补丁 + 回归过滤 + 投票排序 | — |
| D-010 | 临时快照自建自删，历史遗留不擅动 | — |
| D-011 | 编码记忆默认关闭（opt-in） | — |
| D-012 | DeepSWE 语料不入库，只入索引与基线 | — |
| D-013 | SRE 预算如实上报，不批量关坑换绿灯 | — |
| D-014 | 规则集按误报率裁剪（js-implicit-global 下线） | — |
| D-015 | 台账整改走「按类型过滤 + 逐条验证」，不走批量关坑 | — |
| D-016 | 测试快照只含源码树：忽略运行产物与 gate 语料 | — |
| D-017 | 编码循环允许「新建文件」：空 SEARCH 只对不存在的目标生效 | — |
| D-018 | 评测判分以语料 reward.txt 为准，退出码只表「脚本跑完」 | — |
| D-019 | 评测完整性闸：补丁改测试/pytest 配置/解释器钩子不参加 resolved | — |
| D-020 | 编码循环新增 search 动作：只读、有界、脱敏 | — |
| D-021 | CI 必须安装引擎依赖并覆盖本地实际 Python 版本 | — |
| D-023 | 补丁结构完整性闸：截断/无法应用的补丁不计 resolved 且不可豁免 | — |
| D-024 | 评测成本归一与合并率抽检的报告口径 | — |
| D-025 | SWE-bench Pro/Live 试点只落基线、不硬凑样本 | — |
| D-026 | Pro 判分链路用 gold 对照验证，但不折算 agent resolved | — |
| D-027 | Live 环境可行性探针不并入基线通过率 | — |
| D-028 | Pro 适配层落地：3 仓 gold 对照全通，状态机归因而非命令模板 | — |
| D-029 | Live 口径：本地源 + venv 复现 test_cmds，部分口径单列不折算 | — |
| D-030 | Pro agent 口径：有反馈迭代按 attempts 单列，成本分列不相加 | — |
| D-031 | ACI 阶段二生产口径：搜索排序/子集/语法校验转正，图排序保持默认关 | — |
| D-032 | 统一事件账本口径：runner 默认写、只读脚本才可重放、故障不阻塞评审 | — |
| D-033 | 成本账本口径：totals 按进程结算、token 来源如实、tokens 不设预算上限 | — |
| D-034 | CI 工程门禁口径：覆盖率只测固定子集、凭据豁免必须带理由、MPL 只许 test-only | — |
| D-035 | 发布边界：main 上打 `v<version>` 附注 tag 是唯一发布动作，release-gate 全绿才签发 | — |
| D-036 | 子代理分解的裁决口径：机械测试优先、返工有上限、升级不留假 DONE（4.1） | — |
| D-037 | 多语言编码的语言包与测试引擎口径：MIT 语法包 import、按仓库信号选引擎（4.2） | — |
| D-038 | 工作区抽象：容器与本地同接口、远程只交付接口不假跑（4.3） | — |
| D-039 | 评审闭环口径：差异率可复算、fail-closed、OCR 只作覆盖信号（4.4） | — |
| D-040 | 4.1 uplift 的独立语料口径：公开上游提交 + 机械判分 + 同一宿主模型的双臂对照 | — |
| D-041 | 300s 红线改线：降级为观测指标 + 600s 挂死护栏（已批准） | — |
| D-042 | 评审精度护栏：固定语料 + precision 下限 0.65 + 基线 0.01 容差 | v1.63.0 |
| D-043 | agent 口径真值：以 agent-diagnosis 为源、caliber 只承载 gold 口径 | v1.64.0 |
| D-044 | 评测台账复评：DONE 行按送评补丁摘要去冗 | v1.65.0 |
| D-045 | 冷启动评测协议：Live 九条候选、零反馈任务文本、冻结与判据 | v1.66.0 |
| D-046 | 4.1 uplift 复验判据：跨模型或 n≥10、paired 对照 + 成本比 | v1.66.0 |
| D-047 | precision 护栏语料：不入库、不进 CI，基线钉 revision+sha256 | v1.66.0 |
| D-048 | 语料设计条款：协议附录必含失败测试指针 | v1.80.0 |
| D-049 | 分层套件提案（smoke/full 拆分）——待总监裁决 | v1.87.0，round-86 |
| D-050 | 文档体系按通用手册三层结构重构 | round-91，v1.92.0 |
| D-049（第 2 条） | 裁决：分层套件 | round-92，v1.93.0 |
| D-051 | 三项裁决：e2e 提案 B+A / verified 评估 / 锚点确认 | round-98，v1.99.0 |
| D-052 | D-041 触线复盘：450s→540s 升级线 + 600s 强制挂死（B+C 已批准；round-135 落地） | round-135，v2.37.0 |
| D-053 | SWRBench 宿主臂归因修正：协议不胜任 → 执行质量无保障，门禁为对策 | round-137，v2.39.0 |

## D-001 写被审仓库的唯一入口：五道闸 + 批准书

- **日期**：2026-10-24（v1.2.0 修复能力 → v1.3.0 三方分立 → v1.4.0 加固）
- **状态**：生效中
- **背景**：智能体会生成补丁写回被审仓库。直接落盘无法证明「补丁就是被批准
  的那份」，失败也无法干净回滚；多个阶段各写各的会让责任链断裂。
- **候选**：
  1. 各阶段自行 `git apply`——最快，但无批准绑定、无统一回滚；
  2. 只靠 git 分支保护——回滚可行，但批准与补丁无字节级绑定；
  3. 唯一落盘脚本 `fix-apply.py` + 审核人批准书（sha256 绑定补丁）+ 五道闸
     （批准书 / 工作树干净 / HEAD 与 base_sha 一致 / apply 预检 / 行为回归）
     + 任一失败自动回滚。
- **决策**：方案 3。写入是最高风险动作，值得为它付流程成本；批准书绑定字节
  可防「批准 A 落 B」；自动回滚 + `apply-log` 留下可采集证据。
- **代价**：流程变重、速度变慢；凭据类发现不能出补丁（硬约束 5），只能转人工；
  回滚率成为 SRE 预算指标（数据不足时如实 N/A）。
- **证据**：`AGENTS.md` 硬约束 7；`skills/repair/scripts/fix-apply.py`；
  README §九；`BASELINE.md` 版本沿革 v1.2.0–v1.4.0。

## D-002 治理壳零依赖、引擎层白名单的分层依赖

- **日期**：2026-10-24（v1.14.0 立宪）
- **状态**：生效中
- **背景**：既要「任何机器直接能跑」的评审/治理脚本（插件与 CLI 分发），
  又要复用成熟引擎（Ruff/LibCST/ast-grep 等）做真实修复。
- **候选**：
  1. 全仓统一第三方依赖——能力最强，但治理壳失去零依赖可分发性；
  2. 全仓纯标准库——可分发，但放弃成熟引擎，自研成本与误报不可控；
  3. 分层：治理壳仅标准库；引擎层按许可证白名单（MIT/Apache/BSD 可 import，
     LGPL 仅 subprocess 隔离，GPL 禁入）；新增依赖经总监批准并登记 pyproject。
- **决策**：方案 3。分发面与能力面分开守：跨层只走 subprocess + JSON。
- **代价**：跨层接口成本高（每个能力都要序列化协议与错误契约）；引擎能力受
  许可证约束（如 Pynguin/Rope 只能外挂）。
- **证据**：`AGENTS.md` 硬约束 1；`docs/DEVELOPMENT.md` §3；`BASELINE.md`
  「依赖白名单契约」；`pyproject.toml`。

## D-003 复用成熟引擎，而不是自研全部规则

- **日期**：2026-10-24（v1.14.0 起步）→ 2026-10-25（v1.23.0 LibCST）
  → 2026-10-27（v1.39.0 ast-grep）
- **状态**：生效中
- **背景**：确定性规则只能覆盖形状类问题；逻辑/风格/跨语言缺陷需要真实引擎。
- **候选**：
  1. 纯自研 AST 扫描——可控但规则面窄、误报治理成本高；
  2. 只接 Ruff——Python lint/autofix 足够，但覆盖不到 JS/TS 与结构性 codemod；
  3. 三层组合：Ruff（lint+autofix）/ LibCST（语义等价 codemod）/
     ast-grep（多语言 AST 模式，跨 JS/TS + Python）。
- **决策**：方案 3。每个引擎都以 subprocess+JSON 接入同一修复链（发现前缀
  `ruff:` / `libcst:` / `astgrep:`，同链分诊/混合修复/闸五复扫）；能力矩阵
  （`engines/*-matrix.json`）入仓，规则数以矩阵为准。
- **代价**：三套引擎的行为边界要分别理解；同文件双引擎出现时保守转人工；
  引擎升级可能改变规则矩阵（须重跑契约）。
- **证据**：`engines/ruff_adapter.py`、`libcst_adapter.py`、`astgrep_adapter.py`
  与对应 `*-matrix.json`；`AGENTS.md` 工程基座节。

## D-004 评测双指标 + 有效样本分母

- **日期**：2026-10-24（BASELINE 勘误新增）
- **状态**：生效中
- **背景**：只报命中数会掩盖误报；把无效样本计入分母会虚高成绩。
- **候选**：
  1. 只报 recall（漏报视角）——简单但可被「全报」刷分；
  2. 只报 precision——可被「不报」刷分；
  3. recall + precision 双指标，缺一即不合格；分母只用有效样本；跨编号体系
     只对齐不可变 sha。
- **决策**：方案 3。另定 precision = grounded / claimed（claimed = 报了非空
  findings 的样本数），并输出细分字段。
- **代价**：每例失败必须归因（PATCH_APPLY_FAILED / F2P_MISSED / REGRESSION…），
  统计与维护成本上升；小样本必须标注不作上限宣称。
- **证据**：`BASELINE.md`「评测双指标契约」；README §八。

## D-005 邻近测试 C 路谓词改为「引用形状」

- **日期**：2026-10-26（round-30，v1.31.0）
- **状态**：生效中
- **背景**：真实仓（django/sympy/matplotlib）300 模块样本上，C 路「裸词提及」
  判真率仅 0.348，噪声大量进入材料包。
- **候选**：
  1. 砍掉 C 路——最简单，但丢掉真实的跨文件线索；
  2. 保留裸词提及——噪声持续污染上下文；
  3. 谓词改为「引用形状」：完整点分路径或 `from 包 import 模块`；
     判定规则先写死进脚本常量，再看数字。
- **决策**：方案 3。结果：判真率 0.348 → **1.000**，噪声返回 125 → 59；
  诚实代价：覆盖率 191 → 174/300（掉的 17 个模块原本只拿到纯噪声材料，
  现在改为「无材料」而不是「假材料」）。
- **代价**：覆盖率下降 17 个模块；谓词更严格后需持续用真实仓回归。
- **证据**：README §八「邻近测试精度用真实仓库定案」；
  `scripts/sibling-test-realbench.py` 常量；`reports/` 归因产物。

## D-006 全量测试 5 分钟红线保留，判定口径补「连续两次同负载」

- **日期**：2026-10-26（round-30 复测定案）
- **状态**：生效中
- **背景**：同一份代码五次落在 261–318 秒，两次越线三次未越；新增测试只占约
  20 秒，越线与未越的代码量相同——差异只能来自跑间抖动/机器负载。
- **候选**：
  1. 删红线——失去预算约束；
  2. 放宽到 6–8 分钟——把抖动写进口径；
  3. 保留 5 分钟红线 + 补判定口径：单次超线只入册并复测，**连续两次同负载
     超线才升级处置**。
- **决策**：方案 3。不把抖动写成口径，也不悄悄改红线。
- **代价**：仍需人工确认「同负载」；偶发超线会带来一次复测成本。
- **证据**：README §八 测试预算段；`retro/next-round.md` 第 9–10 条。

## D-007 结案口径从「形状对」升级为「机器全量实跑」

- **日期**：2026-10-26（round-31，v1.32.0）
- **状态**：生效中
- **背景**：台账 `closure_note` 里写的命令从来没人真跑；«已修» 可能不可复算。
- **候选**：
  1. 人工声明——成本低，但无法证伪；
  2. 抽样实跑——折中，但漏掉的恰可能是最脆的那几条；
  3. 全量抽取 + 在 `.venv` 下逐条真跑（`scripts/verify-closure-commands.py`），
     抽取判据四轮补严并各带反向验证；`self_reference` 只登记不执行；
     缺省 dry-run 不动盘。
- **决策**：方案 3。首轮真台账抽出 10 条命令、10/10 通过；round-33 起增加结案
  三分类（machine_checkable / human_conclusion / weak_closure）；round-34 起
  识别 `tests/...::test_` 散文钉法并合成命令（weak 10 → 4）。
- **代价**：结案更慢；抽取器本身成为需要维护与被验证的对象。
- **证据**：`scripts/verify-closure-commands.py`；BASELINE round-31 段；
  README §八。

## D-008 模糊意图三键 + 阻塞才追问

- **日期**：2026-10-26（round-32，v1.33.0）
- **状态**：生效中
- **背景**：指代（「评审那块」）与复合子句被猜着执行，事后无法复核 agent 的假设。
- **候选**：
  1. 一律追问——安全但打断流程；
  2. 直接执行——快但假设不可追溯；
  3. 三键输出：`ambiguity`（被裁决掉的多解读）/`assumptions`（采用的假设，
     带依据与错了的代价）/`confirmations`（非阻塞待确认项）；仅阻塞（C 级）
     才追问（questions ≤1 + 退出码 3）。
- **决策**：方案 3。假设随报告带回用户，不得静默当作已澄清。
- **代价**：输出更长；假设错误时要付「错了的代价」（如实写明）；
  悬空指代与「顺便」类复合子句仍需持续补强（round-35 已消化三缺陷）。
- **证据**：`skills/prompt-enhancement/scripts/intent-parse.py`；
  `skills/director/scripts/task-pipeline.py`；README v1.33.0 段。

## D-009 多候选补丁 + 回归过滤 + 投票排序

- **日期**：2026-10-27（round-37，v1.38.0）
- **状态**：生效中
- **背景**：编码循环只交付最后编辑态，一次失误即整例失败；多次 LLM 重采样
  （Agentless 式）成本高。
- **候选**：
  1. 只交最后编辑态——零成本，但没有纠错机会；
  2. 多次 LLM 重采样——质量可能更高，但要额外调用与预算；
  3. 把编辑循环的**自然副产品**保存为候选快照（每次成功 edit + 测试后），
     收束时按「测试通过 > 失败 > 跳过 > 空补丁」四档排序，同档内校验 ok 优先
     + 最小补丁；最优候选替代最后编辑态交付。
- **决策**：方案 3。不增加 LLM 调用；排序理由进 manifest `provenance.candidates`
  可复算。**明确不按 manifest 的 tests 字段排序**——老仓库的 tests=fail 系统性
  来自环境缺失（django-14999 tests=fail 仍 resolved），拿它排序会误伤好补丁。
- **代价**：候选存储与 provenance 维护成本；排序规则本身需要契约测试。
- **证据**：`agent/code-task.py` 候选收集与排序；`tests/test_agent.py`；
  README v1.38.0 段。

## D-010 临时快照自建自删，历史遗留不擅动

- **日期**：2026-10-26（round-30/31 批次，v1.31.0→v1.32.0）
- **状态**：生效中
- **背景**：本机 Temp 下积累 3,490 个无标记历史遗留（repair- 1533 /
  cra-tests- 1240 / code-task- 195 / mcp- 186 …）。按前缀清理不可靠：前缀一多
  必然漏，且可能删掉非本模块的目录。
- **候选**：
  1. 继续按前缀清——不可靠且有误删风险；
  2. 永不清——磁盘持续膨胀；
  3. 新跑次自建自删：`tests/tmpspace.py` 建目录即落归属标记，atexit 兜底，
     中断也回收**带标记**目录；无标记历史遗留一律不碰。
- **决策**：方案 3。历史遗留的删除需人工决定：先
  `scripts/sweep-test-tmp.py` 出报表，确认后 `--apply --purge-unmarked <前缀>`
  逐前缀收（next-round 第 12 条）。
- **代价**：历史残留仍在；报表与人工确认流程需要守。
- **证据**：`tests/tmpspace.py`；`scripts/sweep-test-tmp.py`；README v1.31.0 段。

## D-011 编码记忆默认关闭（opt-in）

- **日期**：2026-10-28（round-43，v1.44.0）
- **状态**：生效中
- **背景**：历史相似案例可作 few-shot 提升材料质量，但未验证的记忆会污染编辑
  决策；测试与临时任务不应写入长期记忆。
- **候选**：
  1. 默认开启——上手即有收益，但会污染评测与测试；
  2. 默认关闭，`--memory-file` / `CRA_MEMORY_FILE` 显式开启——默认安全；
  3. 只在评测外开启——需要区分运行场景，边界模糊。
- **决策**：方案 2。注入限流：top-k + max-chars（few-shot ≤2000 字符）。
- **代价**：主动开启才有收益；已知局限——共享通用词即得分 >0，未设最小分阈值
  （以 top-k + max-chars 限流，入台账留观）。
- **证据**：`skills/retro/scripts/memory_retrieval.py`、`compact-memory.py`；
  `agent/code-task.py` `--memory-file`；`tests/test_retro.py`。

## D-012 DeepSWE 语料不入库，只入索引与基线

- **日期**：2026-10-28（round-43，v1.44.0）
- **状态**：生效中
- **背景**：DeepSWE 是 113 任务的 gate 基准（Harbor 格式，5 语言）。全量语料
  体积大，且属受控评测数据，入库会臃肿并污染训练语料。
- **候选**：
  1. 全量入库——复现最方便，但体积与污染风险不可接受；
  2. 入库索引 JSONL + 基线 JSON（ID/URL/任务数），语料本地生成；
  3. 完全不入库——最干净，但新环境无法知道基准构成。
- **决策**：方案 2。`skills/eval-harness/data/` 进 `.gitignore`；
  `reports/deepswe/baseline-v1.44.0.json` 入仓（20 个 Python 任务 / 10 个回归 ID，
  status=not_run，待首次实跑）；语料缺失时测试 skip 并标注原因。
- **代价**：新环境需跑 `deepswe-fetch.py`（遵守硬约束 8 的镜像纪律）；
  首次实跑前基线只是清单不是成绩。
- **证据**：`reports/deepswe/baseline-v1.44.0.json`；`.gitignore`；
  `tests/test_gold_sample.py` TestDeepSWE。

## D-013 SRE 预算如实上报，不批量关坑换绿灯

- **日期**：2026-10-28（round-43）
- **状态**：生效中
- **背景**：README 一度写「迭代官未结坑 0/8、无整队冻结」，而
  `org-scorecard.py` 实算为 open 32/8 = EXCEEDED、`freeze_teams=[retro]`。
  批量把历史坑标 closed 可以让指标立刻变绿。
- **候选**：
  1. 批量关坑让指标过线——最快，但等于用假账换绿灯；
  2. 如实 EXCEEDED + 按制度冻结 retro + 排期清理；
  3. 调阈值——改口径迁就现状。
- **决策**：方案 2。台账纪律改为「入册即验、验过即结」；冻结期 retro 团队
  只修质量不扩功能；历史未结项列为首要清理目标（next-round 第 14 条）。
- **代价**：retro 团队进入整改冻结，相关功能暂停；清理 32 项需多轮投入；
  「预算数字由脚本生成而非手抄」列为待批准候选（next-round 第 16 条）。
- **证据**：`skills/director/scripts/org-scorecard.py` 实算输出；
  `retro/pitfalls.json`；README 状态行（已改报）；BASELINE round-43 段。

## D-014 规则集按误报率裁剪（js-implicit-global 下线）

- **日期**：2026-10-28（round-43，v1.44.0）
- **状态**：生效中
- **背景**：ast-grep 规则集扩到 29 条后，`js-implicit-global` 在真实语料上
  误报率过高；同时旧扫描超时 300 秒会挂死。
- **候选**：
  1. 保留规则并降级为提示——噪声仍进材料；
  2. 下线该规则——规则数少一条，但信号纯度提升；
  3. 调阈值/加例外——需要维护例外表，复杂度上升。
- **决策**：方案 2，并把单次扫描超时收紧到 30 秒防挂死。原则与 D-005 同源：
  宁可无材料，不给假材料；规则数、可修复数、safe 数以
  `engines/astgrep-matrix.json` 为准。
- **代价**：漏报面扩大（隐式全局将不再被标注）；矩阵数字随之下调。
- **证据**：`engines/astgrep_adapter.py` BUILTIN_RULES；
  `engines/astgrep-matrix.json`；`tests/test_engines.py`。

## D-015 台账整改走「按类型过滤 + 逐条验证」，不走批量关坑

- **日期**：2026-10-28（round-44，v1.45.0）
- **状态**：生效中
- **背景**：D-013 之后 retro 团队冻结，open 32/8。逐条复核发现其中 22 条
  根本不是坑——是 feature/test/doc/confirmation 类工作完成事件：入册器
  只看 `description`，不看事件 `type`，把「做了什么」写成了「哪里会踩」。
  若沿用 D-013 之前的做法，批量 closed 能让指标当天变绿。
- **候选**：
  1. 批量关坑——最快，但等于把「入册错误」包装成「已修复」；
  2. 逐条补结案证据——22 条完成事件本就没有根因/对策可验，越补越假；
  3. 结构修复 + 有依据的归档——入册器按 type 过滤（规则先于数字），
     历史污染条目用 `--archive` 带理由归档（保留原文，不删除），真正的
     坑逐条验证后才 closed。
- **决策**：方案 3。入册器新增 `NON_PITFALL_EVENT_TYPES` 白名单并在输出里
  报 `skipped_events`（跳过要可见，不许静默）；`--archive` 与 `--close`
  互斥、只对 open 生效、理由必填；台账只增不改（archived 保留原字段）。
  数字：155→157 条，open 32→5（轮末全量计时又新记 1 条红线越线，留观待
  计时画像）；24 条归档 / 4 条验证后结案 / 1 条新缺陷当场结案。retro SRE
  回到 PASS，冻结解除。
- **代价**：台账出现第三种状态（archived），统计口需要区分
  closed/archived/open；「补齐理由」这条路从此关闭——不存在的坑不该被
  补成存在过的坑。
- **证据**：`skills/retro/scripts/retro-ledger.py`（白名单 + `--archive`）；
  `tests/test_retro.py::test_ledger_skips_completion_events`、
  `test_archive_requires_note_and_only_open`；
  `skills/self-iteration/scripts/verify-closure-commands.py --run` 0 违规；
  `skills/director/scripts/org-scorecard.py` retro=PASS。

## D-016 测试快照只含源码树：忽略运行产物与 gate 语料

- **日期**：2026-10-28（round-45，v1.46.0）
- **状态**：生效中
- **背景**：fingerprint 与 doc-drift 的门禁用例通过 `snapshot_repo()` 复制整棵
  工作树做可写副本。`reports/_work` 的探针产物（~75MB）与
  `skills/eval-harness/data` 的 gate 语料（~15MB）也被复制：单次副本
  77.6MB / 8129 项 / 6.01s，两次快照测试共多付约 10s；更严重的是把
  「这台机器的工作树碰巧有什么」混进了本应只看源码树的门禁输入。
- **候选**：
  1. 维持整树复制——省事，但成本随机器状态漂移，门禁输入不可控；
  2. 按 `fingerprint.py` 的 `skip_dirs` 口径排除运行产物目录
     （reports/retro/runs/llm-tasks/data），与指纹的「源码树」定义对齐；
  3. 改成 git archive 或 mock 仓库——隔离更彻底，但两份门禁都读取真实
     工作树文本（含未提交改动），改动面大、收益不成比例。
- **决策**：方案 2。`SNAPSHOT_IGNORE` 增列五个目录；两个调用方
  （fingerprint 对比、doc-drift 注入）都不读它们，指纹与漂移结论逐一复跑
  不变；`test_fingerprint_stable_and_sensitive` 增加反向断言（快照不得含
  上述目录与 gate 语料），防止日后有人把忽略项删掉而无人察觉。
  用例总数仍为 401（断言加在既有用例内，不新增计数）。
- **代价**：快照从此不含运行产物——未来若有测试需要 reports/retro/data，
  必须显式建夹具或加入忽略白名单；`SNAPSHOT_IGNORE` 与 `fingerprint.py`
  的 `skip_dirs` 需人工保持同口径。
- **证据**：`tests/test_scripts.py`（`SNAPSHOT_IGNORE` 与反向断言）；
  `reports/suite-profile-round-45.md`（6.01s/77.6MB → 1.03s/2.4MB 实测，
  命令 `measure_snapshot.py`）；红线数值未改，另案待批。

## D-017 编码循环允许「新建文件」：空 SEARCH 只对不存在的目标生效

- **日期**：2026-10-28（round-46，v1.47.0）
- **状态**：生效中
- **背景**：DeepSWE 首次真实评测的任务（tomlkit 表格互转）要求新增
  `tomlkit/convert.py`，而编辑面只支持「旧文件内唯一命中替换」——模型
  给出了正确的新建内容也无处可写；同时即时校验用 `git diff HEAD` 收集
  补丁，未跟踪文件天然缺席，即便写成也会被判 `file_missing` / `missing_change`。
- **候选**：
  1. 只在评测侧把新文件塞进补丁——治标，编码循环仍不能建文件；
  2. 编辑面支持空 SEARCH 新建（目标必须不存在），校验前
     `git add -A -N` 让未跟踪文件进入 `git diff HEAD`；
  3. 放开「空 SEARCH = 追加」——会改变既有替换语义，误伤面大。
- **决策**：方案 2。空 SEARCH + 目标不存在 → 以 `replace` 全文创建并补尾
  换行；空 SEARCH + 已存在文件仍拒绝（避免把「追加」误当「新建」）；
  `_worktree_diff()` 统一三处调用点。两处行为各配端到端反向测试
  （`test_edit_format_create_new_file`、`test_new_file_edit_lands_in_patch`）。
- **代价**：编辑格式多一条隐式规则（空 SEARCH 的合法性取决于目标是否存在），
  提示词需同步说明（AGENTS.md 已写）；`git add -A -N` 会给工作区加
  intent-to-add 标记（可被 `git reset` 清除，不改变内容）。
- **证据**：`agent/edit_formats.py`、`agent/code-task.py` `_worktree_diff`；
  `tests/test_agent.py`；`tests/test_scripts.py`；round-46 实跑 resolved。

## D-018 评测判分以语料 reward.txt 为准，退出码只表「脚本跑完」

- **日期**：2026-10-28（round-46，v1.47.0）
- **状态**：生效中
- **背景**：DeepSWE 语料的 `test.sh` 在写完 `/logs/verifier/reward.txt` 后
  以 0 收尾——无论 baseline/新测是否通过。round-46 首跑把「baseline 收集
  失败、reward=0」误报成 resolved（退出码 0），属于最坏的假绿形态。
- **候选**：
  1. 继续用退出码判分——会把所有「跑完但失败」的样本记成 resolved；
  2. 只认 reward.txt（1=通过），退出码仅区分装载/注入故障（3/4/5/6/8）；
  3. 额外解析日志文本找 pass/fail——脆且重复实现语料自身的判定。
- **决策**：方案 2。`_verdict(exit_code, reward)` 为唯一判分函数；
  reward 缺失记 None（不通过），退出码 8（补丁注入失败）单列原因；
  反向测试四组（0/0、0/None、8/None、5/0）锁死口径。
- **代价**：不同语料族的 reward 路径/语义可能不同，接入新语料时必须先读
  其 test.sh 的判分方式（已写入 DEVELOPMENT.md 评测链四条硬口径）。
- **证据**：`skills/eval-harness/scripts/deepswe-sample.py`；
  `tests/test_gold_sample.py::test_verdict_requires_reward_one`；
  `reports/deepswe/baseline-v1.44.0.json`（reward=1 实跑）。

## D-019 评测完整性闸：补丁改测试/pytest 配置/解释器钩子不参加 resolved

- **日期**：2026-10-28（round-47，v1.48.0）
- **状态**：生效中（口径收紧，反例已验）
- **背景**：D-018 把判分从退出码改为 reward.txt，堵住了「跑完但失败」的
  假绿；但补丁本身仍可改测试面——公开资料（Berkeley RDI，2026-04）证实
  仅 10 行 conftest.py 钩子即可强制改写 pytest 结果，另有多家机构复现
  「测试通过 ≠ 真正修复」。我们此前不检查补丁改了哪些文件，等于把
  resolved 的可信度交给运气。
- **候选**：
  1. 不做检查，只靠 reward——无法区分产品代码修复与测试黑客；
  2. 全量禁止补丁触碰任何测试文件——会误伤合法的「新增测试」；
  3. 分级：测试基础设施/pytest 配置/解释器钩子/改删既有测试 = critical
     不参加 resolved；新增测试/CI/依赖改动 = warning 仅记录；宿主可用
     `--allow-test-edits` 显式豁免并留下 waived 痕迹。
- **决策**：方案 3。`_patch_integrity` 只读补丁文本、不执行补丁代码；
  命中 critical → `status=integrity_flagged`，跳过 Docker 评测、不计数
  resolved，结果里保留完整 `patch_integrity`（critical/warnings/行数/
  touched）。判定只看补丁头与增删行，不用行首正则（硬约束 6）。
- **代价**：少数真实修复需要同步调整测试夹具的补丁会被拦下；此时要么
  改写为只改产品代码，要么显式 `--allow-test-edits` 并人工复核。
  该口径只用于**本项目评测链**，不改变语料 test.sh 的判定。
- **证据**：`skills/eval-harness/scripts/deepswe-sample.py`；
  `tests/test_gold_sample.py::test_patch_integrity_flags_test_hacking`
  （clean/conftest/改测试/新增测试/pytest.ini/sitecustomize 六样例）。
  D-020 的搜索动作同轮补两条：`test_search_is_bounded_and_redacts_secrets`
  与 `test_query_redacted_in_trace_and_material`（trace 与下一轮材料
  均不得出现明文 query）。

## D-020 编码循环新增 search 动作：只读、有界、脱敏

- **日期**：2026-10-28（round-47，v1.48.0）
- **状态**：生效中
- **背景**：动作面此前只有 read/edit/probe/done；模型不知道目标文件在哪
  时只能猜路径（DeepSWE 实战里「文件不存在」占掉多轮）。SWE-agent 的
  ACI 研究把「搜索」列为最小工具集之一；OpenHands/Claude Code 亦同。
- **候选**：
  1. 不加密搜索，继续靠 read 猜——长任务成本高；
  2. 直接执行 grep 并回传原始输出——Windows/容器可用性不一，输出无限，
     且可能把凭据带进材料；
  3. 实现有界字面搜索：只读、剪运行产物目录、限扩展名/文件大小/命中数，
     命中行与回显查询经 `<redacted>` 脱敏。
- **决策**：方案 3。`search` 与 `read` 同级（只读，不需额外授权）；
  后续如需正则搜索，另立决策并加超时/复杂度限制。新增动作不改
  `--rounds` 语义，不改变补丁产出路径。
- **代价**：字面搜索对复杂模式表达力弱；大仓库首次搜索有 IO 成本
  （已用 2000 文件/40 命中截断兜底）。
- **证据**：`agent/code-task.py` `_search_repo`；
  `tests/test_agent.py::test_search_is_bounded_and_redacts_secrets`。

## D-021 CI 必须安装引擎依赖并覆盖本地实际 Python 版本

- **日期**：2026-10-28（round-47，v1.48.0）
- **状态**：生效中（GitHub 侧首次运行前视为「待实证」）
- **背景**：原 workflow 只 checkout + setup-python 就跑 unittest，不装
  ruff/libcst/tree-sitter/ast-grep；且测试里硬编码 `.venv/Scripts/python.exe`
  （Windows 路径），在 ubuntu runner 上直接 FileNotFoundError。矩阵也缺
  本地 `.venv` 实际使用的 3.12。结论：CI 绿灯不能作为引擎层证据。
- **候选**：
  1. 保持现状，在 README 标注「CI 仅治理壳」——诚实但放弃了 CI 的价值；
  2. 装依赖 + 补 3.12 + 解释器回退 + cache/timeout；
  3. 上容器化 CI——更重，收益不匹配当前规模。
- **决策**：方案 2。workflow 安装运行时依赖与 pytest；测试解释器优先
  `.venv`、否则当前解释器；矩阵 3.11/3.12/3.13；`timeout-minutes: 30`；
  `cache: pip`；`fail-fast: false`。
- **代价**：CI 时长增加（依赖安装）；Linux 平台可能有本地未见的差异，
  首次运行可能暴露新失败——这正是 CI 的用途，不以「本地绿」代替。
- **证据**：`.github/workflows/self-check.yml`；`tests/test_agent.py`、
  `tests/test_testgen.py`、`tests/test_engines.py` 的解释器解析；
  本地全量双跑（见 PROGRESS 当前状态）。

## D-022（批准）许可证白名单与 pyproject 的 MPL 依赖需裁定

- **日期**：2026-10-28（round-47）提案；**2026-10-31（round-77）总监批准方案 1**
- **状态**：批准（已生效）——方案 1：白名单扩为「MIT/Apache/BSD 可嵌入
  import；MPL-2.0 仅 test-only（optional-dependencies.dev，不进运行时
  import 链、不随治理壳分发）；LGPL 仅 subprocess、GPL 禁入」
- **落地（round-77）**：AGENTS.md 硬约束 1、BASELINE.md 依赖契约、
  pyproject.toml 白名单注释三处同步扩 MPL 边界；license-check 三档判定
  （D-034 已实现「MPL 仅 test-only」）与 docs/DEVELOPMENT.md 表述不动
  （与裁定一致）；D-034 的 hypothesis 移位与本次裁定构成同一口径的
  文档-代码闭环。
- **背景**：`AGENTS.md` 硬约束 1 写「MIT/Apache/BSD 许可证可嵌入 import；
  LGPL 仅 subprocess；GPL 禁入」，而 `pyproject.toml` 的 `dependencies`
  含 `hypothesis>=6`（MPL-2.0），`docs/DEVELOPMENT.md` 写「MPL（hypothesis）
  用于测试生成」。三处口径不一致，属于治理漂移而非代码缺陷。
- **候选**：
  1. 把 AGENTS 白名单扩为「MIT/Apache/BSD/MPL（MPL 仅测试生成，不嵌入
     分发物）」——与现状一致，但需明确 MPL 的边界（文件级 copyleft）；
  2. 移除 hypothesis，测试生成改用标准库模板——失去属性测试能力；
  3. 维持现状并只在 DEVELOPMENT 标注例外——文档不一致继续存在。
- **建议**：方案 1，同时要求 MPL 依赖只在测试/生成侧使用、不得进入
  分发运行时；由总监批准后更新 AGENTS 硬约束 1 与 BASELINE 依赖契约。
- **代价**：白名单扩一条，需要持续审计「MPL 文件是否被修改后分发」。
- **证据**：`AGENTS.md` 硬约束 1；`pyproject.toml` dependencies；
  `docs/DEVELOPMENT.md` 第 86 行附近。

## D-023 补丁结构完整性闸：截断/无法应用的补丁不计 resolved 且不可豁免

- **日期**：2026-10-28（round-48，v1.49.0）
- **状态**：生效中
- **背景**：round-47 的完整性闸只看「补丁改了哪些文件」（测试面 / pytest 配置 /
  解释器钩子），不看补丁本身是否**结构完整**。round-48 合并率抽检在
  django-11019 上实踩边缘形态：补丁可解析、能进评测，但 hunk 声明行数与实际
  不符（尾部缺失），harness 只能记成 PATCH_APPLY_FAILED / F2P_MISSED，与
  「修错了」混为一谈；同时测试用的假补丁文本也让这个问题显得「无声」。
- **候选**：
  1. 只依赖 harness 的 `git apply` 失败——真实但晚：要先起容器/跑环境，
     且失败归因与语义错误混在一起；
  2. 用 `git apply --check` 预检——语义最强，但需要工作树与准确的 base
     提交，dry-run 阶段往往拿不到，且 Windows CRLF 场景会引入噪声；
  3. 结构自检：逐个 hunk 核对 `@@ -a,b +c,d @@` 声明行数与正文实际
     行数，另拒空 hunk / 非 diff 行 / hunk 内空行。
- **决策**：方案 3，作为**评测入口的前置闸**（`_patch_well_formed`），
  harness 仍是最终裁判。结构失败记为 `malformed_patch`：不计入 resolved
  分母、不进入 Docker 评测、**不受 `--allow-test-edits` 豁免**（结构损坏
  不是策略选择，豁免它等于把坏产物当好产物）。判定不改变「修错了」的
  归因类别，只把「补丁坏了」单列。
- **代价**：结构正确 ≠ 语义可应用（上下文不匹配仍要 harness 判）；对
  binary diff、无 hunk 的特殊补丁会误判为损坏——本项目编码循环只产文本
  补丁，接受这一边界并在报告注明。
- **证据**：`skills/eval-harness/scripts/deepswe-sample.py::_patch_well_formed`；
  `skills/eval-harness/scripts/agent-sample.py` 的 `malformed_patch` 汇总与
  summary 状态优先级；`tests/test_gold_sample.py::test_malformed_patch_blocked_and_not_waivable`、
  `TestDeepSWE::test_patch_well_formed_detects_truncation`。

## D-024 评测成本归一与合并率抽检的报告口径

- **日期**：2026-10-28（round-48，v1.49.0）
- **状态**：生效中（合并率的人工复核仍 pending，报告已如实标注）
- **背景**：阶段一要求「每一份能力主张都能回答：哪套基准、多少样本、
  判分口径、成本多少、有无完整性告警」。此前精度报告只有合成语料
  precision/recall 与真实语料表，成本散落在 summary、合并率从未测量。
- **候选**：
  1. 只报 resolved 率，成本另见原始 summary——读者要自己拼；
  2. 估算 token/成本（按字符数折算）——好看但虚假；
  3. 两级：`eval-cost-report.py` 从 agent summary 归一（墙钟/轮数/编辑数/
     每 resolved 成本，缺失项 N/A），`precision-report.py` 用
     `--cost-report` / `--merge-audit` 并入同一份报告，合并率由 agent
     按固定判据逐例初筛、人工复核状态原样随附。
- **决策**：方案 3。成本用**墙钟秒**并声明含环境与评测开销、不等于模型
  算力；host 后端 token 一律 N/A，不估算；合并率判据 C1–C5 固定并逐例写
  备注，`human_review: pending` 原样进报告，不拔高为「人工评审」。
  精度报告复现命令必须带全本轮实际入参（`--cost-report` / `--merge-audit`
  / `--real` 等），否则复现不出同一份报告。
- **代价**：墙钟受负载影响，跨轮比较只能看趋势；agent 初筛存在自评偏差，
  人工复核未完成前合并率只能作「可提交评审」的粗指标。
- **证据**：`skills/eval-harness/scripts/eval-cost-report.py`；
  `skills/eval-harness/scripts/precision-report.py`（成本/合并章节与 repro）；
  `reports/evals/eval-cost-report-agent-local7-r48-2026-10-28.md`；
  `reports/swebench/merge-audit-r48.json`；`reports/precision-report-2026-10-28.md`。

## D-025 SWE-bench Pro/Live 试点只落基线、不硬凑样本

- **日期**：2026-10-28（round-48，v1.49.0）
- **状态**：生效中（实跑待 harness 适配器；本轮记偏差）
- **背景**：阶段一 1.3 要求「Pro/Live 各 ≥10 条试点」。实测数据集：
  Pro 默认 v2 共 642 行，Python 子集只覆盖 3 个仓库（ansible 4 /
  openlibrary 3 / qutebrowser 3）；Live lite 300 行，10 个仓库各 1 条。
  若坚持「≥10 条」只能跨语言取样本，或把 Python 子集重复取样。
- **候选**：
  1. 跨语言凑 10 条——评测链与 repo map 均 Python-only，跑了也证明不了
     能力，只会得到一个被误读的数字；
  2. Python 子集全取（Pro 10 条、Live 10 条）——Pro 侧重复取样同一仓，
     样本不独立；
  3. 基线如实入库（Pro 默认 v2 / Live lite 全量索引 + Python 子集清单），
     试点规模按实测下限断言（跨 ≥3 仓），实跑另立任务并先补适配器。
- **决策**：方案 3。Pro 取 Python 子集（3 仓 10 条），Live 取 lite 的
  10 条（每仓 1 条不重复）；契约测试断言「Pro ≥3 仓、Live 每仓 1 条」。
  **实跑阻塞**：Pro/Live 的评测字段（before_repo_set_cmd / test_cmds）与
  现有 harness 适配层不兼容，本轮不伪造运行结果——基线文件
  `reports/swebench/pro-baseline-v1.49.0.json`、`live-baseline-v1.49.0.json`
  与可行性报告 `reports/swebench/pro-live-feasibility-2026-10-28.md` 即为
  本轮交付，ROADMAP §5 记偏差。
- **代价**：阶段一出口的「Pro/Live 实跑数字」推迟；对外不得引用任何
  Pro/Live resolved 数字（目前不存在）。
- **证据**：`tests/test_gold_sample.py::TestProLiveBaselines`；
  `reports/swebench/pro-live-feasibility-2026-10-28.md`。

## D-026 Pro 判分链路用 gold 对照验证，但不折算 agent resolved

- **日期**：2026-10-28（round-49，v1.50.0）
- **状态**：生效中（Pro 适配层待代码化；本轮只做单条人工验证）
- **背景**：round-48 把 Pro 实跑阻塞定性为「harness 字段不兼容」。
  round-49 用 ansible 单条在容器内实际执行 `before_repo_set_cmd` +
  `selected_test_files_to_run`：仅应用 test_patch 时 1 个 F2P 失败、15 个
  P2P 全过；追加 gold patch 后 16 个全过。判分链路可复现。
- **候选**：
  1. 把 gold 结果当作 Pro resolved 报出去——会把「判分链路通」误读为
     「agent 能力」，且数据集自带补丁，毫无信息量；
  2. 只写「跑通了」不落证据——无法复算，等于状态宣告；
  3. 记录为 **gold 口径 harness 验证**：写清命令、镜像 digest、基线与
     gold 两轮逐项结果，基线状态保持 `not_run`，另立适配层任务。
- **决策**：方案 3。Pro 基线文件新增 `harness_validation` 块，
  `status` 仍为 `not_run`；报告
  `reports/swebench/pro-harness-validation-2026-10-28.md` 只声明判分可
  复现，不声明通过率。镜像强制国内源（ghcr.nju.edu.cn，711.2 MB /
  35.025 s），ghcr.io 未参与。
- **代价**：阶段一出口仍无 Pro agent 数字；适配层与批量实跑顺延。
- **证据**：`reports/swebench/pro-harness-validation-2026-10-28.md`；
  `reports/swebench/pro-baseline-v1.49.0.json` 的 `harness_validation`。

## D-027 Live 环境可行性探针不并入基线通过率

- **日期**：2026-10-28（round-49，v1.50.0）
- **状态**：生效中（Live 适配层待代码化）
- **背景**：Live 无预构建镜像，需 clone 后按 `test_cmds` 建环境。基线首选的
  cfn-lint 源码获取链全灭（gitee 超时、GitHub reset、代理 10–60 KB/s、
  证书过期）；改用本机 gitee 镜像缓存的 urllib3 建环境，baseline 3 个
  F2P 全失败、gold 后 3 个全过。该实例不在基线 10 条内。
- **候选**：
  1. 把 urllib3 结果写进 Live 基线并算 resolved——样本替换后基线不再是
     确定性选样，等于篡改口径；
  2. 因网络不可达直接报「Live 不可评」——掩盖了环境构建本身可行的事实；
  3. 基线保持 10 条 `not_run`，另记 `harness_feasibility` 探针（非基线
     样本），只声明环境链路可复现，并写清依赖来源偏差与未跑 P2P。
- **决策**：方案 3。`live-baseline-v1.49.0.json` 新增
  `harness_feasibility` 块；报告
  `reports/swebench/live-harness-validation-2026-10-28.md` 记录探针命令、
  依赖来源（清华 PyPI，Quart/hypercorn 用 PyPI 等价版本替代 git 引用）、
  基线/gold 结果与「未跑 1,816 P2P」的边界。
- **代价**：Live 基线 10 条仍无任何实跑数字；正式批量前要把「源码获取 →
  建环境 → 全量 test_cmds → 解析」代码化并固定 Linux 环境。
- **证据**：`reports/swebench/live-harness-validation-2026-10-28.md`；
  `reports/swebench/live-baseline-v1.49.0.json` 的 `harness_feasibility`。

## D-028 Pro 适配层落地：3 仓 gold 对照全通，状态机归因而非命令模板

- **日期**：2026-10-28（round-50，v1.51.0）
- **状态**：生效中（Pro 适配层 ✅；Live 适配层未动；agent 侧仍 not_run）
- **背景**：round-49 用 ansible 单条人工命令证明 Pro 判分链路可复现（D-026），
  但不可批量、不可复跑、异常只能看日志。round-50 把流程代码化为
  `pro-sample.py`，并以 3 仓 3 条做 gold 对照：ansible（1/1 F2P、15/15 P2P）、
  openlibrary（5/5、15/15）、qutebrowser（3/3、46/46）全部
  `baseline_ok → resolved`。
- **候选**：
  1. 把 3 条 gold resolved 报成 Pro 通过率——仍是数据集自带补丁，等于把
     「判分链路通」当「agent 能力」，无信息量且误导；
  2. 适配层写成固定命令模板（无状态机、无台账）——失败样本只能人工看日志，
     无法归因，也无法续跑；
  3. 状态机 + 补丁双闸 + 任务级环境适配 + 幂等台账；gold 只作对照，
     agent 侧另走 `--mode predictions`，基线 `status` 保持 `not_run`。
- **决策**：方案 3。12 态互斥状态机（含 malformed_*/integrity_flagged/
  blocked_source/patch_apply_failed/prepare_failed/infra_error）；补丁双闸
  复用 `deepswe-sample`（`--allow-test-edits` 豁免必须留 `waived_critical`
  痕迹）；环境差异走任务级 `pre_test_cmd/env/pytest_args`（变量名白名单），
  不硬编码实例；镜像只走国内源（ghcr.nju.edu.cn），缺失按 `blocked_source`
  保留样本，不静默丢；台账 key=`<instance_id>|<mode>`，重跑幂等
  （`run_this_time=0`）。
- **代价**：gold 口径不能对外折算通过率；Live 适配层、Pro 扩 10 条、agent
  侧 predictions 均为后续轮次；qutebrowser 判分外残留失败如实保留在日志。
- **证据**：`reports/swebench/pro-3repo-validation-2026-10-28.md`；
  `skills/eval-harness/scripts/pro-sample.py`；
  `tests/test_pro_sample.py`（10 项）；
  `reports/swebench/pro-baseline-v1.49.0.json` 的 `harness_validation`。

## D-029 Live 口径：本地源 + venv 复现 test_cmds，部分口径单列不折算

- **日期**：2026-10-28（round-51，v1.52.0）
- **状态**：生效中（Live 适配层 ✅；gate-10 本地仅 1 条有源、1 条补充样本
  部分口径；agent 侧仍 n=0）
- **背景**：SWE-bench Live 不提供官方镜像，只有 `test_cmds`、`test_patch`、
  `patch` 与 F2P/P2P；且 10 条任务横跨 plain pip / hatch / poetry / pdm
  四种运行器，`test_cmds` 多为整仓或整包 pytest（最大 8,227 P2P）。round-49
  已用手工命令验证「建环境 → 判分」可行（D-027），但不可批量、不可归因。
  round-51 把流程代码化为 `live-sample.py`。
- **候选**：
  1. 只跑 F2P 并把通过直接记 `resolved`——P2P 未跑等于放弃回归判据，
     与「resolved 必须是判分点全过」冲突；
  2. 10 条里 9 条源码不可达就丢弃样本、只报 1 条——样本完整性被破坏，
     也无法区分「基准难」与「我们没跑」；
  3. 适配层 + 状态机：源码 cache→gitee→GitHub 降级，不可达落
     `blocked_source` 保留样本；环境构建走 worktree 外 venv +
     任务级 `setup_cmds`；`--f2p-only` 只算 `f2p_passed`（partial=True），
     `resolved` 仅在全量 P2P 跑完且全过时给出。
- **决策**：方案 3。包括——
  - 子进程超时杀整棵进程树（Windows `taskkill /F /T /PID`、POSIX
    `os.killpg`），git 操作禁交互（`GIT_TERMINAL_PROMPT=0`），否则
    `git-remote-https` 子进程会拖住整轮；
  - venv 建在 worktree 之外、`pip/setup_cmds` 的 cwd 必须是仓库根、
    PATH 用绝对路径（三处均为实测真坑）；
  - 台账 key=`<instance_id>|<mode>`，`--force` 只重跑目标样本、不覆盖
    其他行；
  - 源码不可达不静默丢：`blocked_source` 计数进台账与报告；
  - 部分口径与 gold 对照严格分开，报告禁止把 `f2p_passed` 写成 resolved。
- **代价**：Live 10 条中 9 条本轮无本地源（`--no-network` 只吃缓存），
  只能保留样本；matplotlib 的 meson 可编辑安装需要 ninja/meson +
  `python3` shim + `--no-build-isolation`，且整仓 8,227 P2P 在 Windows
  本地不具备可操作性；urllib3 补充样本只跑 3 个 F2P，1,816 P2P 未跑，
  因此只能报 `f2p_passed`。以上均如实记录，不作 Live 通过率。
- **证据**：`reports/swebench/live-10-2026-10-28.md`；
  `skills/eval-harness/scripts/live-sample.py`；
  `tests/test_live_sample.py`（10 项）；
  `datasets/swebench/live-runs/live-sample-ledger.json`（不入库）。

## D-030 Pro agent 口径：有反馈迭代按 attempts 单列，成本分列不相加

- **日期**：2026-10-29（round-52，v1.53.0）
- **状态**：生效中（Pro agent 侧 10/10 resolved；gold 10/10 另 key；Live
  仍为部分口径）
- **背景**：round-51 的 `--patches` predictions 通路只有代码、真实补丁
  n=0。round-52 以宿主会话模型充当编码循环后端，仅给 `problem_statement`
  跑完 10 条：10/10 resolved（F2P 32/32、P2P 269/269），但 4 条实例经过
  多次尝试（`03095f26` 8 次、`106909db` 3 次、`11c1777d`/`01d1d149` 各
  2 次），且每轮之间模型能看到自产 pytest 失败日志。
- **候选**：
  1. 把 10/10 直接写成「单发通过率」——隐瞒跨尝试反馈，口径失真；
  2. 只认第一次尝试、其余作废——会丢掉可复算的解题过程，且与
     `code-task` 的迭代设计冲突；
  3. 允许有反馈迭代，但 attempts、每次运行与成本全部单列，gold 与 agent
     分 key，不折算。
- **决策**：方案 3。包括——
  - 每次新尝试从基线重建全新 run 目录，旧产物归档
    `runs-archive/<iid>__attemptN`；attempts 计数以归档目录为准；
  - 报告必须逐实例列出 attempts、终版轮数/编辑数、F2P/P2P、pytest 与
    elapsed；「10/10」只能与 attempts 一起出现；
  - 台账 key=`<instance_id>|<mode>`，`baseline/gold/predictions` 三组
    各 10 行，互不覆盖、禁止折算；
  - 成本分列：编码循环活跃时间（183.550s，仅终版）、判分 pytest
    （18.188s）、判分 elapsed（43.033s；整轮 48.141s）；宿主往返与人工
    编排未计量并明确声明，禁止相加成单一「总成本」；
  - `code_task.tests` 字段是 worktree 内仓库自有测试，缺镜像依赖时
    fail，**不是判分信号**；判分只认容器内 F2P/P2P 逐 node 对账。
- **代价**：10/10 不能当单发能力或总体通过率；n=10、3 仓不外推；宿主
  模型无 token 计量，每 resolved 成本仍 N/A。
- **证据**：`reports/swebench/pro-agent-10-2026-10-29.md`；
  `datasets/swebench/pro-work/agent/runs/` 与 `runs-archive/`（不入库）；
  `datasets/swebench/pro-runs/pro-sample-ledger.json`、
  `patch-provenance.json`（不入库）。

## D-031 ACI 阶段二生产口径：搜索排序/子集/语法校验转正，图排序保持默认关

- **日期**：2026-10-29（round-53，v1.54.0）
- **状态**：生效中（2.2/2.4/2.5 进入生产默认；2.1 opt-in；2.3 能力就绪）
- **背景**：`docs/ROADMAP.md` 阶段二要求用真实语料回答四项能力问题。判据在
  跑数前写死在 `scripts/aci-retrieval-bench.py`（`VERDICT_RULES`），数字见
  `reports/aci-round53-bench.json` 与 `reports/aci-stage2-round53.md`。
- **候选与决策**：
  1. **2.1 图排序**：候选（a）默认启用；（b）reserved6+2 替换低分 refs；
     （c）默认关、显式 `--rank graph`。真实任务 Top-8：refs/graph@8/graph@12/
     reserved 均为 9/11，构造样本均 7/9——无增益且构图 1.8–10.0s/仓，选
     **（c）**。`graph@12` 是 12 槽位上界，不代表 token 不增，未转正。
  2. **2.2 搜索排序**：21 个查询前 5 条含目标定义点 13→17（无丢失），转正
     「定义 > 引用 > 注释 → 与候选文件路径距离」排序；先收 `max_hits×10`
     再取前 40，命中行仍脱敏。
  3. **2.3 list 动作**：只读、限深 ≤3、≤200 项、剪运行产物、不跟符号链接、
     路径 resolve 必须在工作区。**探索轮数下降未测**，不报已验收。
  4. **2.4 测试子集**：只走 A（同名测试）/B（目录段映射），C 路内容扫描关闭
     （每轮都扫 tests/ 太贵）；映射不出回退全量，不猜。映射非空 7/11（4 条
     django 落回退），合成控时 1.62→1.05s（-35.2%），故转正。**漏测兜底**：
     1/3 确定性抽检（seed=轮次|改动文件）再跑全量，失败按 fail；未抽检的
     pass 必须标注「未抽检」，不得当全量通过。抽检不是全覆盖，报告不宣称
     「漏测率 0」。
  5. **2.5 语法校验**：tree-sitter `has_error` + `ast.parse` 双网，只查本次
     编辑过的 `.py`；非末轮退回重做，收束前再查并进 `patch_validation`。
     变异语料 10/10 拦截、8 个合法样本 0 误报。
- **代价**：2.1 的图能力未被真实语料证明有效，只作为显式实验开关；2.3 的
  阶段出口指标仍欠宿主实跑；2.4 的映射覆盖 63.6%，子集标注里的「N 项」是
  pytest 路径条目数而非用例数；1/3 抽检有漏检概率。
- **证据**：`reports/aci-round53-bench.json`（20 样本 × 四策略 + 21 查询 +
  11 仓映射 + 控时/抽检探针 + 10 坏样本）；
  `reports/aci-stage2-round53.md`；`tests/test_agent.py::TestAciStageTwo`。

## D-032 统一事件账本口径：runner 默认写、只读脚本才可重放、故障不阻塞评审

- **日期**：2026-10-29（round-54，v1.55.0）
- **状态**：生效中（阶段三 3.1 交付；repair/eval 侧接入随 3.2 成本账本）
- **背景**：`docs/ROADMAP.md` 阶段三出口要求「任何人拿到一个 run 目录，不读
  聊天记录也能回答做了什么、为什么、花了多少、能不能复现」。此前 trace 只
  存在于编码循环（agent/trace.py），评审流水线靠 audit.jsonl 的散文摘要，
  「为什么」与「能不能复现」两问无从回答（G8）。
- **候选**：
  1. 把 agent/trace.py 的 JSONL 格式直接铺到评审流水线——两套 schema、
     两套读者，口径分叉；
  2. 每个动作都强制重放——LLM 判定、审计、断点这类动作天然不可重放，
     强跑会制造假差异；
  3. append-only 事件账本：统一 schema，重放分级（deterministic 白名单 +
     opaque 默认跳过），账本故障降级不阻塞评审。
- **决策**：方案 3。口径——
  - schema `action-observation/1`；每行 seq 从 1 连续、prev 等于上一行
    digest、digest=sha256(去 digest 后的规范 JSON，sort_keys/无空格)；任一
    不符 `verify` 退出码 1 并给 `first_bad`；
  - runner 进程内 importlib 加载 event-ledger（不为 21 次调用额外起子进程），
    脚本调用 / audit 决策 / LLM 往返各记一条；
  - **默认 opaque**，只有 15 个只读脚本（intent-parse / preflight /
    edge-detect / deterministic-rules / taint-cross / score / dispatch-plan /
    material-check / rules-select / experience / findings-check / coverage /
    perspective-scan / report-check / schema-check）标 deterministic；
    audit-log / checkpoint / human-gate / event-ledger 自身排除（日志套日志）；
  - 路径令牌化 `$REPO`/`$ROOT`/`$RUN`/`$PYTHON`，匹配 Windows 反斜杠与
    POSIX 斜杠双形态；易变键（ts/elapsed*/run_id/session_id 等）重放比对时
    忽略；
  - 观察体超 200000 字节不落全文（`{"oversized": true, "bytes": n}`）并降
    opaque；密钥形态一律 `<redacted>`（硬约束 5）；
  - LLM 事件只记 provider/model/prompt_sha256/response_sha256/字符数，
    不落提示词与响应正文；
  - 账本任何写失败只 stderr 告警并自动停写，`totals.json.ledger.errors`
    如实计数，评审主流程不受影响。
- **代价**：deterministic 白名单是人工判断（漏标少报可重放动作，错标生
  假差异）；重放按 argv 原样执行，外部环境漂移（依赖/网络）仍可致 DIFF；
  同名 action 多轮出现时需 `--only` 或按 seq 定位；repair/eval 链路尚未
  接入，阶段出口的「花了多少」由 3.2 成本账本补齐。
- **证据**：`skills/production-guardrails/scripts/event-ledger.py`；
  `tests/test_scripts.py::TestEventLedger`（2 项）与 `test_runner_e2e`
  账本断言；演示 run `reports/ledger-demo-round54/20261029-095326-14093d/`
  （31 条记录、verify 链完好、replay 20/20 MATCH、11 条 opaque 跳过、
  0 错误）。

## D-033 成本账本口径：totals 按进程结算、token 来源如实、tokens 不设预算上限

- **日期**：2026-10-29（round-55，v1.56.0）
- **状态**：生效中（阶段三 3.2 交付）
- **背景**：阶段三出口要求回答「花了多少」。runner 此前只报
  `minutes_used` 与 tokens 两个裸数字：tokens 在 host 后端恒为 0（与
  「没用 token」不可区分），轮数只在内存，耗时没有分步画像；无法与
  caps 对账，也无法回答续跑段的成本归因。
- **决策**：`totals.json.cost` 采用**进程口径**并如实标注来源——
  - `scope=current_process（--resume 各段另行起算）`：预算执行（minutes/
    rounds/dynamic_dispatches）按段判定，跨段不合并，避免续跑的宿主
    问答重放把轮数预算吃穿；
  - `tokens_status ∈ {not_used, provider_usage, unavailable, n/a_host,
    no_provider}`：host 后端没有用量一律 `n/a_host`，provider 未上报是
    `unavailable`，**不得记 0 冒充已计量**；`provider_usage` 必须伴随
    `tokens_reported_calls > 0`；
  - `llm_calls_baseline`：进程启动时账本里的 LLM 记录条数，`llm_calls`
    只统计本段，C3 用「账本累计 − 基线」对账；账本是全 run 累计，两者
    口径差异显式化；
  - tokens **不设预算上限**（不引入 token cap），budget 行恒 N/A；
  - 旧 totals（无 cost 块）由 cost-ledger 退化为 derived 视图，相关
    一致性检查标 skipped，不伪造来源。
- **代价**：跨续跑段没有单一总账（需要把各段 cost 相加或等后续轮次的
  合并视图）；derived 视图无法证明 token 来源；分钟数为墙钟，含脚本
  子进程开销，不等于 LLM 思考时间。
- **证据**：`skills/production-guardrails/scripts/cost-ledger.py`；
  `skills/orchestrator/scripts/runner.py`（_write_totals/_budget_rows/
  _track_llm/checkpoint）；`llm/provider.py`；
  `tests/test_scripts.py::TestCostLedger`（4 项）与 `test_runner_e2e`
  成本断言；演示 run `reports/cost-demo-round55/20261029-125027-9f1593/`
  （check 8/8 PASS，续跑段同样 8/8）。

## D-034 CI 工程门禁口径：覆盖率只测固定子集、凭据豁免必须带理由、MPL 只许 test-only

- **日期**：2026-10-29（round-56，v1.57.0）
- **状态**：生效中（阶段三 3.3/3.4 交付；G12 裁定落地）
- **背景**：阶段三要求 CI 增加覆盖率与 secret/license 门禁。三个约束互相
  顶着：全量套件测覆盖率实测 2.6× 成本（test_dual_reviewer 50.0→131.5 秒），
  而 300s 红线已连续多轮越线；凭据扫描在真仓首跑 8 命中，全是「本来就该
  存在」的测试夹具与历史复盘文字；pyproject 的 hypothesis（MPL-2.0）与
  硬约束 1 的 import 白名单冲突（G12 挂账多轮未决）。
- **决策**：
  - 覆盖率**只测固定三项测试子集**（test_scripts / test_agent /
    test_dual_reviewer），不测全量套件；基线入仓
    `skills/self-iteration/coverage-baseline.json`，逐文件 + 总体对账，
    **0.5pp 容差**抗平台抖动；基线内文件消失判 REGRESSION，新增文件
    单列不判红；跨平台差异只走 `platform_optional` 显式豁免；
  - 基线生成与对账都带 `scope`（source / tests / python / platform），
    CI 只在 **windows-latest × 3.12 单格**跑 check——基线平台与 CI 平台
    对齐，其他矩阵格不跑覆盖率（避免跨平台假回退）；
  - 凭据扫描的**豁免必须可审计**：行内 `secret-scan: allow` 或文件级
    `path + rule（或 *）+ reason`；缺理由判违规，过期条目单列
    `allowlist_stale`；命中片段一律 `<redacted>`；
  - 许可证按 **三档**（dependencies→import / optional.isolated→
    subprocess / optional.dev→test-only）判定：GPL/AGPL 全档禁入、
    LGPL 仅 subprocess、MPL 仅 test-only；**G12 裁定**：hypothesis
    （MPL-2.0）移入 `optional-dependencies.dev`，不再出现在运行时依赖；
  - 安装版本只作证据，允许 N/A（CI / 本机未装全部引擎依赖时按注册表判定）。
- **代价**：覆盖率数字不代表全仓，只是「固定子集不低于基线」；新增但没
  进子集的路径不会被覆盖率门禁看见（靠测试与评审补）；凭据扫描是形态
  规则不是熵检测；MPL 包仍随 dev 安装进入开发环境（不分发）。
- **证据**：`skills/self-iteration/scripts/coverage-gate.py` /
  `secret-scan.py` / `license-check.py`；`tests/test_scripts.py::
  TestCiGates`（10 项）；`reports/ci-gates-round56/`（基线实测、对账
  PASS、篡改 rc1、secret/license PASS）；`docs/ROADMAP.md` §5.14。

## D-035 发布边界：main 上打 `v<version>` 附注 tag 是唯一发布动作，release-gate 全绿才签发

- **日期**：2026-10-29（round-57，ROADMAP 3.5）
- **背景**：此前「发布」没有定义——版本号靠人工同步、README 真值靠
  doc-freshness 单查、全量双跑只写进轮报、tag 从未打过。ROADMAP 3.5 要求
  「一键脚本全绿才允许打 tag」，但「发布」指什么（打 tag？发镜像？通知下游？）
  没有边界就无法机械判定，也无法审计「哪个提交是发布版」。
- **候选**：
  1. 发布 = 任意时刻的 main HEAD：不 tag、不设闸——零成本，但「发布版」不可
     查询、证据不可复现。
  2. 发布 = 自动流水线（闸绿即自动 tag + push + 发版说明）：省人，但把不可逆
     动作交给脚本，与「修复分支永不自动合并」同一理由（写操作必须有人批准）。
  3. 发布 = 人工在 main 上打 `v<version>` 附注 tag，前置条件是
     release-gate.py 七项全绿并留下证据 JSON——动作仍由人执行，判据全机械。
- **决策**：方案 3。
  - 发布动作只有一件：在 main 的发布提交上打附注 tag `v<version>`（tag 名
    = `v` + plugin.json 的 version）；**不含** push、镜像发布、部署等外部动作；
  - 签核判据 = `release-gate.py` 七项全绿：版本六处同步（plugin 真值 +
    pyproject / review_mcp SERVER_INFO / README 头条 / DEVELOPMENT 发布口径 /
    BASELINE 最近沿革）、doc-freshness、doc-drift、secret-scan、
    license-check、全量双跑（两份日志或 `--run-suite` 当场执行）、git 干净树 +
    tag 预检；证据落 `reports/release-gate/<version>/release-gate.json` 并随
    仓库提交，tag 应打在包含该证据的 main 提交上；
  - 双跑证据优先 `--run-suite`（mode=executed）；复用同轮两份日志时闸记录
    mode=reuse 与 sha256/计数/耗时，「日志与树一致」的声明责任在发布人；
  - `--only` 只用于 CI 分项（当前只接 version_sync），输出 partial=true，
    **不构成发布签核**；
  - tag 一经打上不可移动、版本号不可复用（闸对已存在 tag 判红）；任何变更走
    新版本号；
  - 300s 红线在闸内是观测项（D-006 判定口径不变）：超线记录、不阻断发布。
- **代价**：发布仍需人工一步（打 tag + push），不追求全自动；复用日志模式
  无法机械证明日志来自当前树；闸不含覆盖率 check（约 500s 测量成本，由 CI
  单格承担）；`--only` 是可用但需纪律约束的口子。
- **状态**：生效中（阶段三 3.5 交付）。
- **证据**：`skills/self-iteration/scripts/release-gate.py`；
  `tests/test_scripts.py::TestReleaseGate`（7 项）；
  `reports/release-gate/1.58.0/release-gate.json`（真仓实跑）；
  `docs/ROADMAP.md` §5.15。
- **round-171 断档追认（2026-11-18 总监裁定）**：v2.38.0–v2.72.0 共 **35** 版
  曾只 bump 版本、生成七项全绿 gate 证据却漏打 tag（与「tag 是唯一发布动作」不一致）。
  经逐个预检证据（每版 7/7 PASS + `ok=true`）、确认 tag 不存在后，按证据 JSON
  首次入仓 commit 逐版打附注 tag 并推送（v2.38→18db9392db…、v2.72→0f5d3f1bc4…）；
  tag 不可移动。此次为**追认既有证据**，不追认任何未过闸的版本。
  后续版本不得重演断档：每版 gate 证据入仓即应打 tag。

## D-036 子代理分解的裁决口径：机械测试优先、返工有上限、升级不留假 DONE（4.1）

- **背景**：阶段四 4.1 要求主循环只做裁决，定位/修复/验证由三个角色子代理
  承担。要解决的是「谁说了算」：verify 子代理自评通过、但仓库测试红时算谁赢；
  修复反复失败时要不要继续烧轮数；失败收束该不该产出一个看起来正常的补丁。
- **备选**：
  1. 信任 verify 自评（LLM 裁 LLM）：材料里已有 diff 与测试状态，判断力最
     灵活，但把「测试红」这种机械事实降级成模型意见，评测口径不可复算。
  2. 只认测试（完全去掉 verify 角色）：最机械，但拿不到「改得对不对路」的
     语义意见，返工理由也无法传达给修复角色。
  3. 双轨：**机械测试是硬否决**，verify 只在测试绿时裁决语义层；返工上限
     默认 2 次，用尽升级 ESCALATED；升级态不写 manifest。
- **决策**：方案 3。
  - verify 输出 `verdict.pass=true` 但 `tests != pass` → 一律记
    `reject`，理由写「机械测试未通过」；反之测试绿且 verify 通过才
    `accept` 并置 `resolved=true`；
  - locate 有轮数预算（默认 2）：用尽即 `degrade` 进入修复，不空转；
  - 返工上限默认 2（`--rework-max`）：每次 reject 触发一次返工，用尽即
    `ESCALATED`（退出码 1、`resolved=false`、**不写 task-manifest.json**，
    下游不得把升级态当交付物）；
  - 裁决全部落 `phases.json`（accept/rework/reject/degrade/escalate + 理由
    + 轮号 + 当时的测试状态），跨 `--resume` 持久化，可审计；
  - 单循环（默认、不带 `--phases`）行为与产物保持不变：阶段模式是 opt-in。
- **代价**：三角色比单循环多 2 轮左右的编排开销（XL 单例 4/12 vs 2/12）；
  角色动作面门禁会拒绝「越界但合理」的动作（如 fix 阶段想 search 全仓），
  需要材料质量兜底；升级态需要人类接手，不能自动收敛。
- **状态**：生效中（阶段四 4.1 交付；uplift 未证）。
- **证据**：`agent/phases.py`；`agent/code-task.py`（`--phases`）；
  `tests/test_agent.py::TestAgentPhases`（9 项）；`reports/xl-round58/`
  （bench.json / report.md / fix.patch，n=1 自产夹具，不宣称 uplift）；
  `docs/ROADMAP.md` §5.16。

## D-037 多语言编码的语言包与测试引擎口径：MIT 语法包 import、按仓库信号选引擎（4.2）

- **背景**：阶段四 4.2 要求 TS/Go 的 repo map、搜索与编辑校验，以及至少一个
  TS 与一个 Go 任务端到端 resolved。需要裁定三件事：语法解析器从哪来（许可）、
  仓库测试怎么跑（引擎优先级）、多语言下编辑校验是否仍做 ast 双网。
- **备选**：
  1. 自写 TS/Go 正则或轻量解析：零依赖，但符号边界与语法错误判不准，且
     tree-sitter 已是本仓依赖，收益与成本不匹配。
  2. 引入 tree-sitter 官方语法包（MIT）：解析能力与 Python 同源，许可可
     import 嵌入；代价是两个新依赖与各自的升级节奏。
  3. 只做 Python、TS/Go 任务用文本启发式凑：过不了验收，放弃。
- **决策**：方案 2，并配套三条口径：
  - **依赖**：`tree-sitter-typescript` 0.23 / `tree-sitter-go` 0.25（均 MIT，
    import 档），登记 `pyproject.toml` 与
    `skills/self-iteration/licenses.json`；LGPL/GPL 不进；升级走依赖白名单。
  - **测试引擎优先级**：`--test-cmd`（显式）> `go.mod` → `go test ./...` >
    `package.json` → `npm test`（Windows 用 `COMSPEC /c npm.CMD`；无
    scripts.test 时退 `node --experimental-strip-types --test` 找
    `*.test.ts`）> pytest；都没找到时如实 skip 并写明原因，**不得把「没有
    测试」当通过**；manifest 记 `test_engine` 供评测口径复算。
  - **编辑校验**：Python 维持 tree-sitter + ast 双网（ast 是 CPython 语义
    基线）；TS/Go 只走 tree-sitter 单网——不为校验再装 Node/Go 的 parser；
    `.py` 以外的文件跳过 `_patch_selfcheck` 的导入名检查。
- **代价**：TS/Go 语法错误判定精度低于 CPython ast（结构破损可判，语义级
  不判）；引擎自动识别依赖仓库信号，非标准布局需 `--test-cmd` 兜底；测试
  目录惩罚是启发式，可能误伤名为 test 的源码目录。
- **状态**：生效中（阶段四 4.2 交付；端到端 n=2 只证通路）。
- **证据**：`agent/repo_map.py`；`agent/code-task.py`；`tests/test_agent.py::
  TestMultiLang`（7 项）；`reports/multilang-round59/bench.json`（2/2，
  n=2 自产夹具不外推）；`pyproject.toml`；
  `skills/self-iteration/licenses.json`；`docs/ROADMAP.md` §5.17。

## D-038 工作区抽象：容器与本地同接口、远程只交付接口不假跑（4.3）

- **背景**：阶段四 4.3 要求「本地 worktree / 容器 / 远程三档统一接口」，验收
  是「同一任务在本地与容器跑出的补丁一致（除环境差异）」。需要裁定：抽象放到
  哪一层（命令面还是文件面）、容器怎么起与怎么跑测试、远程档在没有真机时怎么
  如实交付、「一致」怎么判。
- **备选**：
  1. 只抽象 `run()`，读写文件仍走宿主路径：实现小，但容器档的文件读写会绕过
     容器，等于「命令在容器、文件在宿主」的假抽象。
  2. 抽象成 `Workspace`：prepare/run/run_in/read_text/write_text/exists/
     apply_blocks/diff/describe/close 全部按档实现（容器档走 `docker exec`，
     远程档走 ssh 上的 `cat >` / `test -f`）：接口面稍大，但补丁、测试、探针
     全在同一边界内，验收「两档一致」才有意义。
  3. 三档各写一套编码循环：重复且必然漂移，放弃。
- **决策**：方案 2，并配套四条口径：
  - **容器**：`container:<image>` 以 `docker run -d --rm` 起常驻容器，worktree
    挂 `/wt`（读写）、原仓挂 `/repo`（只读），命令经 `docker exec -i` 执行，
    `-w` 指定工作目录；容器名由 out 目录 sha1 派生，`close()` 负责 `rm -f`。
  - **远程**：`remote:<target>` 走 `ssh -o BatchMode=yes -o ConnectTimeout=15`，
    远端 worktree 幂等建立（`if [ ! -d … ]; then git worktree add`）；
    **本轮没有真实远端环境，只在契约测试里用本地 ssh 假壳验证命令构造**，
    `agent/code-task.py` 对 `--workspace remote:` 显式拒绝（exit 2）——不以
    假跑冒充真机，报告里也不把它写成已验收。
  - **一致判据**：同一任务、同一宿主响应（同一份 action JSON），两档都
    state=DONE + tests=pass，且 `edits.patch` 字节级 sha256 相同；环境差异
    （解释器版本/平台）记录进 bench 的 `workspace` 字段，不参与「一致」判定。
  - **编辑落盘**：`edit_formats.apply_edits_io(blocks, read, exists, write)`
    抽出，本地/容器/远程共用同一路径守卫、唯一命中与补空 SEARCH 规则。
- **代价**：容器档每轮命令多一次 docker exec 往返（实测同任务 2.281 s →
  3.890 s）；容器测试依赖本机已构建的 `cra-pytest:3.12` 镜像，镜像缺失时
  契约测试 skip 而非假绿；远程档只覆盖命令构造，真实 ssh 语义（路径映射、
  权限、远端 python 探测）未验证。
- **状态**：生效中（阶段四 4.3 交付；远程档接口-only）。
- **证据**：`agent/workspace.py`；`agent/edit_formats.py`（`apply_edits_io`）；
  `agent/code-task.py`（`--workspace`）；`tests/test_agent.py::
  TestWorkspaceBackends`（4 项）；`reports/workspace-round60/bench.json`
  （identical_patch=true，232 B，sha256 `820b56a2…`）；
  `reports/workspace-round60/report.md`；`docs/ROADMAP.md` §5.18。

## D-039 评审闭环口径：差异率可复算、fail-closed、OCR 只作覆盖信号（4.4）

- **背景**：阶段四 4.4 要求「把 agent 补丁送第三方评审器（Open Code Review
  或等价）」，验收是「自评与他评差异可量化；差异 > 阈值时转人工」。需要裁定：
  两臂各是什么、差异怎么算、什么情况转人工、外部工具许可与成本边界。
- **备选**：
  1. 只调 OCR 的 `review/scan`：需要 LLM 端点与 key，本仓没有；且单臂无法
     算「自评 vs 他评差异」。
  2. 自评臂（作者侧机械核验）+ 多条他评臂（ruff / ast-grep / OCR delegate /
     任意命令评审器）：不依赖 key、发现可定位到文件行、差异可复算。
  3. 只跑静态规则、不做配对：无法区分「两臂一致」与「一臂缺失」，放弃。
- **决策**：方案 2，并配套五条口径：
  - **自评臂**：补丁非空、编辑文件语法树（`repo_map.syntax_issues`）、测试
    状态（pass/fail/skip 由调用方传入）、即时校验问题；严重度透传。
  - **他评臂**：`ruff check --select E,F,W,B` 只统计落在补丁新增行的发现；
    ast-grep 内置规则集经 `engines/astgrep_adapter.py` 逐文件扫描、同样只计
    新增行；OCR **只用 `delegate preview` 的文件清单作覆盖信号**（不调
    `review/scan`，不产生 LLM 成本），列出的覆盖不到补丁文件即转人工；
    `--reviewer-cmd name=command` 支持任意评审器（stdout 必须是
    `{"findings":[…]}`，补丁路径经 `CRA_REVIEW_PATCH` 传入）。
  - **差异度量**：两臂发现先按 (file,line,rule) 去重，再按「同文件 + 行号
    ±2」贪心配对（任一方无行号时按文件配对）；
    `diff_rate=(external_only+self_only)/union`，`union=self+external−matched`。
  - **转人工（fail-closed）**：`diff_rate > 阈值`（默认 0.5，严格大于）、
    出现 high 严重度发现、OCR 覆盖缺口、外部臂全部不可用（error/unavailable）
    ——任一成立即 NEED_HUMAN；`code-task --review` 下 NEED_HUMAN 退出码 1、
    不写 manifest，明细落 `review.json`。
  - **成本/许可**：ruff 与 ast-grep 已是登记依赖（MIT，import/subprocess 档），
    OCR 仅以本地已装 CLI 的 delegate 子命令运行（未调用其 LLM 评审，无 API
    成本）；命令评审器由调用方自供、成本归调用方。
- **代价**：OCR 的发现能力没有被使用，评审深度受 ruff/ast-grep 规则面限制；
  Go 补丁两臂都无规则覆盖（`external_status=skipped`），只能靠自评臂与测试
  状态；行号 ±2 配对会漏掉同文件远距离的同一问题（误判为两条差异，方向是
  「多报差异」而不是漏报）；阈值 0.5 是工程缺省，未在真实语料上标定。
- **状态**：生效中（阶段四 4.4 交付；样例集 n=8 自产夹具只证机制）。
- **证据**：`agent/review_loop.py`；`agent/code-task.py`（`--review` /
  `_review_gate`）；`tests/test_agent.py::TestReviewLoop`（6 项）、
  `TestReviewGateWiring`（1 项）；`reports/review-round60/review-bench.json`
  （8/8）、`gate-bench.json`（2/2）；`reports/review-round60/report.md`；
  `docs/ROADMAP.md` §5.18。

## D-040 4.1 uplift 的独立语料口径：公开上游提交 + 机械判分 + 同一宿主模型的双臂对照

- **日期**：2026-10-29（v1.62.0）
- **状态**：生效中（证据口径）；4.1 uplift 未证
- **背景**：阶段四 4.1 的验收是「XL 任务（跨 ≥5 文件）resolved 提升」。
  round-58 只有一例自产夹具（n=1），两臂均为同一宿主模型，无法排除
  「夹具顺手 / 模型先验」；next-round 要求补独立语料证据，并明确禁止用
  同一宿主模型自评当作跨模型结论。
- **候选**：
  1. 继续用自产夹具扩样——可控但独立性弱，容易把夹具偏差当能力。
  2. 公开上游真实提交 + 提交自带测试补丁预置 + pytest 机械判分 + 两臂同一
     宿主模型：语料独立、判分不经过模型；但模型轴仍单点，知名库存在记忆
     污染风险。
  3. 等第二个模型/宿主再跑——最干净，但本仓没有第二模型端点与预算。
- **决策**：方案 2，并配套四条口径：
  - **XL 操作化**：源文件 ≥4 且含测试文件共 ≥5 个文件改动；
  - **判分**：独立 worktree 上 apply agent 补丁，先跑 F2P node ids、再跑
    任务相关 P2P，`resolved = 两者 rc==0`，不由 verify 角色自评；
  - **基线自检**：种入测试后基线必须红（click 7 failed/635 passed；
    tomlkit 1 failed/743 passed），环境故障重跑不混入结论；
  - **限制标注**：两臂同一宿主模型、n=2、知名库记忆污染风险，报告逐条写明。
- **结果**：两题两臂 **4/4 resolved**、补丁字节级一致（未观测到 uplift）；
  phases 固定 4 轮 vs single 2 轮。**「XL resolved 提升」仍不成立为已证
  主张**，4.1 状态维持 ◐。
- **代价**：没有跨模型对照，样本仍小；结论只能说明「本基准下机制不劣化、
  轮数有界」，不能说明「三角色在其他模型/语料上也无增益」。
- **证据**：`reports/uplift-round61/run-uplift-bench.py`、`tasks.json`、
  `bench.json`、`report.md`；`docs/ROADMAP.md` §5.19。

## D-041 300s 红线改线：降级为观测指标 + 600s 挂死护栏（已批准）

- **日期**：2026-10-29（v1.62.0，提案）；2026-10-30（v1.68.0，批准）
- **状态**：**已批准（round-67 执行）**——总监 2026-10-30 会话内声明
  「后续全权交由你负责推进」，按提案方案 2 落地；批准记录见本条与
  `retro/events-round-67.json`，tag v1.66.0 / v1.67.0 亦同批执行（D-035）。
- **背景**：D-006 规定「连续两次同负载超线才升级处置」。round-48 起连续
  13 轮双跑均超 300s（round-60 454.087 / 424.970 秒、round-58 426.278 /
  447.365 秒、round-52 358.658 / 358.774 秒；round-45 画像显示最慢单测
  14.71s、无单点异常，总时长受负载主导）。每轮都按口径记录「升级处置」，
  但没有处置出口，红线已退化为噪声。
- **候选**：
  1. 维持 300s：不改口径，继续每轮记录超线——零风险，但信号失效。
  2. 300s 降级为观测指标 + 600s 挂死护栏（本提案）：总时长继续逐轮记录，
     仅 600s 判红；另加环比 >20% 归因。
  3. 直接把红线抬到 600s：简单，但把「挂死」与「变慢」混为一个数。
  4. 只设单测预算、不设总时长：漏掉整体性劣化。
- **决策**：提案方案 2，附带三项条件——(a) 套件必须连续两次全绿；
  (b) 每轮总时长与单测最慢项写入 PROGRESS（观测，不参与判分）；
  (c) 环比上一轮中位 >20% 必须归因（代码增量 / 主机负载 / 并发），
  600s 为硬护栏（超即红，疑似挂死）。**批准前保持 300s 红线与 D-006
  判定口径不变**。
- **代价**：失去「总时长一超就报警」的朴素信号，改由环比与画像补足，
  对记录纪律要求更高；若批准，需同步 release-gate 说明与 PROGRESS 口径。
- **执行口径（round-67 起）**：300s 转观测线（逐轮照记，不升级处置）；
  **600s 为硬挂死护栏**（套件以 `timeout 600` 包裹，超时判红按挂死处置）；
  单测预算每断言 60s 保留；升级触发改为「连续 3 轮 >450s 或任一单项超线」。
  环比上一轮中位 >20% 须归因。release-gate 的 `redline_sec=300` 保留为
  观测线不动（其输出已标「不阻断发布」），代码侧改动留待下次代码轮随
  契约一起动；历史链条（README/DEVELOPMENT/PROGRESS 各轮 300s 记录）是
  当时的历史事实，不回改，新语义只在 forward-looking 口径生效。
- **证据**：`docs/PROGRESS.md` 第 12 行 round-48..60 双跑数字；
  `reports/suite-profile-round-45.md`；`docs/ROADMAP.md` §7/§9。

## D-042 评审精度护栏：固定语料 + precision 下限 0.65 + 基线 0.01 容差（v1.63.0）

- **日期**：2026-10-29（v1.63.0）
- **状态**：已落地（实现既有 §7 护栏，不改红线、不改阶段目标）
- **背景**：`docs/ROADMAP.md` §7 写「评审 precision 不低于 0.65（规则口径）
  且趋势不降」，但此前只是文档约定：round-36 的 12 例 ReviewBench 精度报告
  是一次性产物，规则随后改动（含 round-61 的闭包豁免）无人复核。
- **口径**：固定 ReviewBench python 子集（12 样例 = 11 valid + 1 weak，weak
  剔除分母，与 reviewbench-eval.py 同口径），评审器固定 deterministic；
  四项检查——`precision_floor`（≥0.65）、`precision_trend`（≥基线 −0.01）、
  `sample_drift`（valid_samples 必须与基线一致）、`reviewer_match`
  （必须 deterministic）。任一失败 rc1；语料/基线缺失 rc2，不静默跳过。
- **基线**：`skills/eval-harness/precision-baseline.json`
  （`precision-baseline/1`）：precision 0.6667 / recall 0.3636 / claimed 6 /
  grounded 4 / hits 4 / valid 11 / weak 1；与
  `reports/reviewbench-precision-2026-10-27.json` 同值。floor 0.65 引自 §7，
  tolerance 0.01 抗舍入（与 coverage-gate 0.5pp 同思路）。
- **语料边界**：`datasets/reviewbench` 不入库（MIT 许可但体积与外部依赖），
  故门禁不进 CI，在本地/发布签核跑；缺语料以 code=2 明示，不伪造 PASS。
- **变更流程**：改 `deterministic-rules.py` 后跑 `precision-gate.py run`；
  确需改基线时，基线文件与原因同提交，`test_shipped_baseline_shape` 会拦住
  无声改动（形状/关键值）。
- **代价**：n=12 小样本，precision 粒度为 1/6；该护栏只能防「显著回退与形态
  漂移」，不能替代人工复核补丁合并性。
- **证据**：`skills/eval-harness/scripts/precision-gate.py`、
  `precision-baseline.json`、`reports/precision-gate-round62/`、
  `docs/ROADMAP.md` §5.20。


## D-043 agent 口径真值：以 agent-diagnosis 为源、caliber 只承载 gold 口径（v1.64.0）

- **日期**：2026-10-29（v1.64.0）
- **状态**：已落地（修正检查器与产物回填，不改评测判定口径）
- **背景**：仓库里有两个口径产物——`code-review-agent.agent-diagnosis.json`
  （20 条 agent 侧，含失败归因）与 `code-review-agent.caliber.json`（50 条，
  round-42 扩样后含 30 条 gold-expand30）。README 同时报「gold 46/50 +
  agent 19/20」。doc-freshness 的 F7 取 caliber 做真值、且按整行历史标记跳过
  （README 状态块一行里必有「→」），对真实 README 长期不生效；round-36 的
  sympy-13437 只回填了 README/BASELINE 与 caliber，20 条产物停在 17/20，
  漂移一轮才在 round-63 暴露。
- **裁定**：F7 真值优先取 `agent-diagnosis.json` 的 instances/resolved（20 条
  agent 口径），该文件缺失才回退 caliber；历史判定改为「数值前 12 字」（与
  F5/F6 同口径）。口径更新必须同时回填产物与 README，产物是唯一真值。
- **反向验证**：`TestSkillGates.test_scan_agent_caliber_prefers_diagnosis`——
  行内带「→」的 18/20 必须判红（证不整行豁免）、19/20 放行（证取对产物）；
  旧测试 `test_scan_caliber_must_match_artifact` 保留 caliber 回退分支。
- **边界**：只定「哪个文件是真值」与「检查器怎么豁免历史」，不改变 agent 与
  gold 分 key、不折算、不外推（D-028/D-030）。
- **证据**：`skills/self-iteration/scripts/doc-freshness.py`、
  `tests/test_scripts.py`、
  `reports/swebench/code-review-agent.agent-diagnosis.json`、
  `docs/ROADMAP.md` §5.21。

## D-044 评测台账复评：DONE 行按送评补丁摘要去冗（v1.65.0）

- **日期**：2026-10-29（v1.65.0）
- **状态**：已落地（改 agent-sample 复评语义，不改判分口径）
- **背景**：`agent-sample.py` 委托 `gold-sample.py` 判分，后者对台账
  `state=DONE` 的实例直接跳过且不暴露 `--force`。同一 out 目录换补丁复评时，
  旧结论原样搬回——round-64 首撞即假红（新补丁 F2P 9/7 的旧判决 14.89 s 被
  重放，实际新补丁 resolved），同一机理反向即假绿（补丁变差仍显示旧 resolved）。
- **裁定**：`agent-sample` 每次送评前计算各实例补丁 sha256，与
  `<out>/_patch-digests.json` 记的上次送评摘要比对；不一致（或摘要缺失）的
  实例先清掉台账 DONE 行再委托判分，未变的实例保持断点续跑语义；摘要文件
  在本轮送评后更新，输出增 `ledger_rerun` 列出被清实例。宁可重跑一次判分，
  不拿陈旧结论充当本轮判定。
- **反向验证**：`TestAgentSampleStaleLedger` 3 条——补丁变了只清该例 DONE 行、
  摘要缺失按变了处理、未变实例保留续跑（521→524）；端到端反证：同一 out
  目录换补丁复评，`ledger_rerun` 命中该例且容器重跑 resolved（40.359 s 的
  假红 → 45.937 s 的真 resolved）。
- **边界**：只动 agent-sample 侧的复评入口，不改 gold-sample 的判分逻辑，也不
  把「重跑」当成新样本——同一实例多次判分仍按最近一次记账，样本量不因重跑变大
  （D-030）。
- **证据**：`skills/eval-harness/scripts/agent-sample.py`、`tests/test_scripts.py`、
  `reports/swebench/django-11019-v3-2026-10-29.md`、`docs/ROADMAP.md` §5.22。

## D-045 冷启动评测协议：Live 九条候选、零反馈任务文本、冻结与判据（v1.66.0）

- **日期**：2026-10-29（v1.66.0）
- **状态**：协议已定（执行待资源；本轮不产生任何冷启动 resolved 主张）
- **背景**：agent 侧 20/20 全部是带历史容器判分反馈的复修（round-63/64 各 1，
  余 18 条回填自历史跑次），按 D-030 不能外推为「冷启动解题能力」。要主张
  解题能力，必须换一批任务文本不带历史判分反馈、且仓库未被历史工作暴露的
  实例，先定样本量与预算。
- **语料**：SWE-bench Live lite 10 条（`reports/swebench/live-baseline-v1.49.0.json`，
  来源 SWE-bench-Live rev b51a864…，lite parquet sha256 7ee0a75c…）。按仓库级
  暴露剔除 `matplotlib__matplotlib-28933`（matplotlib 已在 agent 口径
  matplotlib-22711/22835 与 gold 口径多例暴露），候选 **9 条**：conan-17092、
  cfn-lint-3749、haystack-8489、reflex-4087、instructlab-2526、llama_deploy-330、
  keras-20389、pdm-3237、pvlib-2249。
- **冻结**：开跑前把候选清单、每实例 base_commit、问题陈述 sha256、提示词模板
  sha256 写入清单产物并在报告中引用；开跑后不得增删实例或改模板，阻塞的实例按
  blocked 原样保留（沿用 round-51 的 blocked_source 口径）。
- **任务文本**：只给 problem_statement + base_commit 仓库快照；不得带 F2P/P2P
  名称、测试输出、历史判分反馈。测试补丁在判分侧使用，不进入编码材料。
- **预算**：每实例 ≤45 分钟墙钟、≤20 次编辑、≤1 次整轮重试；全程 ≤8 小时；
  跑不动的实例记 blocked 不补位（样本量如实缩水）。
- **判据（报告口径）**：逐实例四种状态——`resolved`（全 F2P+P2P 绿）、
  `f2p_passed`（声明子集全过，partial，不折算 resolved，D-029）、`failed`、
  `blocked_*`（环境/依赖）。结论只报「n 条可判实例中 resolved=k、f2p_passed=m、
  blocked=b」并附二项区间；n<9 时标注真实 n。禁止与 20/20、46/50、10/10 混算。
- **当前阻塞（如实）**：全量判分需要实例官方镜像；本机 docker 仅覆盖已见实例，
  国内镜像源探测 usable_rank=[]（round-64），故 `resolved` 口径暂不可得，只有
  Live 本地 venv pytest 的 `f2p_passed` 通路。执行排在镜像可达性解决之后。
- **证据**：`reports/swebench/live-baseline-v1.49.0.json`、`retro/next-round.md`
  第 25 条、`skills/eval-harness/scripts/live-sample.py`、`docs/ROADMAP.md` §5.23。

## D-046 4.1 uplift 复验判据：跨模型或 n≥10、paired 对照 + 成本比（v1.66.0）

- **日期**：2026-10-29（v1.66.0）；**2026-11-02（round-77）路径 B 定案**
- **状态**：**已定案（round-77）**——路径 B n=5 对 paired 对照
  （deepseek-chat 同模型、公开上游语料、语料冻结 sha256、机械 pytest
  判分）：single 1/5 vs phases 1/5，**差值 0 → 早停触发**，成本比
  1.48×；与 r58（n=1）、r61（n=2）三份独立证据方向一致，
  **uplift 主张不成立，不再投预算**；4.1 维持「机制可用、uplift 未证」，
  机制面（状态机/门禁/台账/仲裁）维持可用。证据：
  `reports/uplift-r77/report.md`。协议对 r61 的偏离（rounds 24 +
  两臂等额协议提示附录）已如实记录于报告口径段。
- **背景**：4.1 三角色状态机（locate→fix→verify，v1.59.0）已有两组独立语料
  证据：XL 单例（n=1 自产夹具，D-036）与公开上游 2 题（click/tomlkit，n=2，
  D-040）——两臂 4/4 resolved、补丁字节级一致，**未观测到 uplift**；两组都是
  同一宿主模型。
- **裁定（再验证协议，二选一）**：
  - 路径 A（跨模型）：≥2 个不同模型家族端点，每端点 ≥5 个独立实例；同一宿主
    模型不得既产补丁又自评。
  - 路径 B（扩样）：同一模型下 ≥10 个独立实例，实例不得与 agent/gold/Live 历史
    语料重叠或被历史工作暴露（按 D-045 仓库级暴露判定），任务文本零反馈。
- **对照与判据**：同实例集 paired 对照「单角色编码循环 vs 三角色」；判分口径、
  轮数预算、测试补丁一致。主张 uplift 须同时满足：① resolved 差值 > 0；
  ② 样本量达路径门槛（A：2×5；B：10）；③ 成本比 ≤1.5× 单角色（墙钟或 token，
  取 cost-ledger 记账值，缺失项如实 N/A）。只报差值区间与 n，不报单点提升率。
- **早停**：前 5 个配对实例差值 ≤0 即终止本轮复验并如实记录「未观测到 uplift」，
  不再扩样刷数字。
- **预算**：路径 B 约 10 实例 × 2 臂，≤10 小时；路径 A 约 2×5 实例，≤6 小时
  （不含模型额度，host 后端按实际用量记）。超预算走 human-gate。
- **边界**：本判据只管「uplift 是否成立」；机制正确性由 12 条契约与 8/8 评审
  样例覆盖，不以机制交付代替效果主张。
- **证据**：`agent/phases.py`、`reports/uplift-round61/`、`reports/xl-round58/`、
  `docs/ROADMAP.md` §5.19/§5.23、D-036/D-040。

## D-047 precision 护栏语料：不入库、不进 CI，基线钉 revision+sha256（v1.66.0）

- **日期**：2026-10-29（v1.66.0）
- **状态**：已落地（precision-gate 增 pin 校验，基线 schema 升 /2）
- **背景**：round-62 的门禁只钉了数字（0.6667/0.3636…），语料本体
  `datasets/reviewbench` 不在库内，`samples-py.json` 与 `diffs/` 还是本地生成
  物——数字与语料的对应关系没有任何机器可验证的绑定；语料换版或重生成后，
  旧数字仍然 PASS。
- **裁定**：
  1. 语料继续不入库、CI 不跑、release-gate 不挂——CI 机器没有语料，强制挂只能
     二选一：伪造 PASS 或常驻 SKIP；门禁保持本地/发布签核口径（round-62 边界不变）。
  2. `precision-baseline.json` 升 `precision-baseline/2`，新增 `corpus` 块：
     revision（语料 git HEAD）+ 26 个输入文件（samples-py.json、
     corpus/manifest.json、12 diff、12 golden）逐文件 sha256 + upstream/revision_date。
  3. `precision-gate.py run` 与 `check --corpus` 先验 pin 再判分；revision 或任一
     sha256 不符一律 code=2，不进入判分。不带 `--corpus` 的 check 保持旧行为。
  4. 换语料/重生成样本必须重跑并把新 pin 写回基线——数字只对产生它的那份语料成立。
- **语料新鲜度**：本地语料浅克隆钉在 `36cc8a8…`（2026-10-26）；2026-10-29 实测
  上游 HEAD 已到 `228f2a8…`。本轮不追新，理由同上。
- **反向验证**：契约测试 6/6（3 反向：改一字节→sha256 不匹配、换 revision→不匹配、
  run 在评测前拦截）；真语料 run PASS（26/26 pin，precision 0.6667 / recall
  0.3636），三份反向基线实跑均 rc=2（`reports/precision-gate-round65/`）。
- **证据**：`skills/eval-harness/scripts/precision-gate.py`、
  `skills/eval-harness/precision-baseline.json`、`reports/precision-gate-round65/`、
  `docs/ROADMAP.md` §5.23。


## D-048 语料设计条款：协议附录必含失败测试指针（v1.80.0）

- **日期**：2026-11-03（round-79）
- **状态**：批准并生效（round-79 实验证据支持，PENDING 预案按计划升级）
- **条款**：凡种子失败测试的评测语料（测试补丁开跑前预置类），编码
  循环的协议附录（`--protocol-notes`）必须含失败测试指针行——列出
  测试文件路径，已知时给 node id。模板样例
  `agent/protocol-notes-example.md` 已含占位行与依据注记。
- **依据（round-79 实验）**：tomlkit-placement 在 r77 v3 双臂 0 编辑
  （探索瘫痪），附录加测试指针行后 1 编辑 / 334s / 机械判分 resolved
  （F2P 1/1 + P2P 173 passed）——指针解锁编辑行为。literal-strings
  侧未解除但归因端点/模型层（flash 空内容流），不影响条款成立。
- **限制**：n=2 单模型实验，不外推强度；条款成本近零（附录一行），
  未见负作用。
- **证据**：`reports/uplift-r79-floor-effect/report.md`、
  `reports/_work/uplift-r78/PENDING.md`、r77 基线
  `reports/uplift-r77/report.md`。

## D-049 分层套件提案（smoke/full 拆分）——待总监裁决（v1.87.0，round-86）

- **日期**：2026-11-06（round-86）
- **状态**：提案（待总监裁决；本轮不实施，仅归档选项）
- **背景**：套件 549 项，round-78/79 双跑超过 450s 趋势线、round-80 归因为负载主导
  后回落线内；但规模每轮 +2~5 项，按当前速率约 20 轮后常态逼近 600s 护栏
  （reports/project-review-r85.md 维度 4）；D-041 600s 挂死护栏与「连续 3 轮 >450s
  升级处置」当前纪律完整保留。
- **选项**：
  - **A. 分层套件**：CI/PR 跑 smoke（~180 项：门禁自举/契约/修复链/编码 e2e 骨架），
    发布闸与 nightly 跑 full（549+ 全量）；省时 ~65%，代价=smoke 漏网风险
    （需预注册 smoke 子集清单 + 每 20 轮回归 full 对账）。
  - **B. 维持现状**：D-041 护栏 + 每 10 轮观察（当前做法）；代价=套件时长继续逼近护栏。
  - **C. 慢测试瘦身**：profile 出 top-10 最慢项，逐一瘦身或并行；收益确定但
    需逐项过反向验证，工作量大。
- **建议（不构成批准）**：C 先行，A 作为 CI 矩阵补充项（CI 只跑 smoke、full 维持
  发布前双跑）；B 作为底线。
- **限制**：n/a（提案）；任一选项落地均须：契约总数不减、smoke 子集预注册入仓、
  全量 full 对账机制不撤、反向验证不降级。
- **证据**：reports/project-review-r85.md（维度 4/7）、DEVELOPMENT 契约套件时长沿革、
  D-041、`logs/suite-r76..85-run*.log`。

## D-050 文档体系按通用手册三层结构重构（round-91，v1.92.0）

- **背景**：《通用说明文档编写手册》提出门面/正文八类/冻结三层与九条
  机器判据；现行体系（DOC-SYSTEM.md 单页 + 权威源散布）存在 README
  承载事实仓库、树内无索引两类手册点名的失败形态。
- **候选**：①权威源文档整体迁入八类目录（DEVELOPMENT→06 正文等）；
  ②权威源原地不动，按手册建索引层（README 收敛 + RULES/INDEX + 八类
  入口 + doc-structure 判据），权威映射在 INDEX 登记。
- **决定**：方案 ②。约束权威保留在 AGENTS.md/BASELINE.md（宪法：78+2
  个脚本的 docstring 与测试逐条引用其编号；迁移成本与漂移风险远大于
  收益）；RULES.md 与八类入口为读者视图索引层。
- **代价与副作用**：①bump-version/doc-freshness/release-gate 的承重
  锚点必须逐处保全（版本行/计数行/口径行已验证）；②DOC-SYSTEM.md
  归档、5 处引用同步；③新增脚本与契约的维护面；④权威源文档的完整
  元信息块本轮不做（目录级豁免登记在 INDEX，后续轮统一）。
- **状态**：生效（2026-11-06 总监派工）。
- **证据**：tests/test_doc_structure.py（11 例含判别力注入）；README
  322→82 行；doc-drift/doc-freshness/round-gate open 全绿。

## 决策附则·D-049 裁决材料（2026-11-06，round-91 收口追加，不构成批准）

- **背景**：D-049 提案（v1.87.0，round-86）选项 A/B/C 已入档。本附则提供
  总监裁决所需的现状数字与代价核对，**未实施任何一项 C 的动作**。
- **现状（round-91 实测）**：597 项契约，全量双跑 414.348 / 431.902 秒
  （`logs/suite-r91-run1/2.log`）；CI 双平台 × 3.11/3.12/3.13 矩阵；
  发布前必过 R5 双跑对账。D-041 口径：300s 红线为观测项（超线不阻断
  发布、按 D-006 升级处置），"连续 3 轮 >450s" 触发分层审议升级。
- **规模趋势（可对账）**：401（round-44，
  `reports/suite-profile-round-45.md`）→ 549（round-85）→ 559（round-86）
  → 585（round-87/88）→ 586（round-89/90）→ **597（round-91，本附则
  实测）**。近 6 轮每轮 +2~5 项；按 0.7-0.8s/项平均成本与 ±20% 负载波动，
  按当前速率预计在 round-110~120 常态逼近 450s 升级观察线、600s 挂死
  护栏前景可期——计数纪律不能只靠约束等待。
- **结构性成因（round-45 画像，方法可复算）**：top-40 最慢项合计
  208.4s（占 65.5%）；套件约 460 次 `run()` 子进程调用（Python 解释器
  启动 ~79ms ×N + git/diff 操作）构成 0.3~0.9s/项 的地板成本；没有任何
  单点异常用例（最慢 14.71s，`test_dual_reviewer.test_host_mode_pause_
  and_resume`）。
- **选项复核（含真实数字）**：
  - **A 分层套件**：CI/PR 跑 smoke（~180 项，预计 ≤2.5 分钟），发布闸与
    nightly 跑 full（597 项）；预估 CI 单轮时长降 ~60%；代价 1：smoke
    漏网风险（需预注册 smoke 清单 + 每 20 轮 full 对账，套件维护面 +1）；
    代价 2：拆分即维护（smoke 选哪些项需要口径纪律，每 20 轮审计）。
  - **B 维持现状**：零成本；round-110/120 前后将触发 D-041 升级线；
    依赖升级轮（round-100 起）的验证成本也会同步上升。
  - **C 慢测试瘦身**：可确认的抓手 =（i）合并脚本级 subprocess 矩阵
    （table-driven，单子进程内多断言，预计省 460 次启动中的 ~30%）；
    （ii）git 操作共享 fixture；（iii）test_dual_reviewer / image-fetch
    类单点瘦身。预估省 15~25%（60~100s/全量）。**风险：改测试即改安
    全网——每处改动必须过反向验证（删断言/造违规样例必须转红）并保
    证全量 countTestCases 不减。**
- **建议（不构成批准，提案人≠批准人红线）**：同意 D-049 原建议——**C
  先行**（先画像 top-40，逐项过反向验证，全量 suite 不减），**A 仅
  CI 补充项**（smoke 只进 CI 矩阵、full 维持发布前双跑），**B 底线
  不动**。若总监裁决 B，则本附则归档不实施。
- **所需裁决 & 截止**：A/B/C 三选一 +（若为 A/C）smoke 子集授权与
  预算；建议在 round-100 依赖刷新专属轮前裁决（该轮的验证成本将直接
  受 D-049 影响）。
- **证据**：`reports/suite-profile-round-45.md`；`logs/suite-r91-run1/
  2.log`、`logs/suite-r91-run2.log`；`docs/DECISIONS.md#D-049`；
  reports/project-review-r85.md（维度 4/7）。

## D-049 裁决：分层套件（round-92，v1.93.0）

- **决定**：总监 2026-11-06 批准附则推荐方案——**C 先行 + A 仅 CI 补充 +
  B 底线不动**。C：脚本级 subprocess 矩阵合并为 table-driven（单子进程
  内多断言，行为字节级不变）；A：smoke 清单预注册（目标 ~180 项 /
  ≤2.5 分钟），CI/PR 跑 smoke，发布闸与 nightly 跑 full（597 项）；
  smoke 清单每 20 轮 full 对账（round-112 审计锚点）。
- **代价**：smoke 漏网风险（预注册清单 + 对账缓解）；套件维护面 +1
  （manifest 文件）；C 的合并使契约计数下降（分母变化随轮登记）。
- **状态**：生效（round-92 实施）。
- **证据**：docs/DECISIONS.md 附则（round-91）；批准记录（本条）。

## D-051 三项裁决：e2e 提案 B+A / verified 评估 / 锚点确认（round-98，v1.99.0）

- **e2e 慢项提案**（proposal-slow-test-r97）：**批准 B+A**——B 维持现状；
  A pytest-xdist 列入 round-100 议程，前置审计
  （proposal-xdist-audit-r98.md：4 阻塞点有条件可行，验证性测试先行），
  审计不过则 A 不落地。
- **扩样续池**：批准「先评估 verified 新池」——评估报告
  verified-eval-r98.md 出（500 实例；核心裁定项=排除口径三档，建议
  中档：实例级排除 + mpl/urllib3 仓级，池 ~447/12+ 仓）；**开跑仍待
  总监批口径与 n 值**。
- **round-100 节奏**：按锚点（round-98/99 其他项）。
- **状态**：生效（2026-11-07 总监裁决）。
- **证据**：reports/proposal-slow-test-r97.md、
  proposal-xdist-audit-r98.md、verified-eval-r98.md。

## D-052 300s 红线提案：450s→540s 升级线 + 600s 强制挂死（已批准 B+C，round-135 落地）

- **日期**：2026-11-10（round-134，v2.36.0，提案人=迭代官；提案人≠批准人红线）
- **状态**：**已批准（B+C，2026-11-10 总监会话内批注）并于 round-135（v2.37.0）落地**——release-gate 红线入参 REDLINE_SEC 300→600 且升格为判红项；CI nightly ubuntu 侧 `timeout 600` 包裹；升级触发线口径 450s→540s（本 D 条批注生效，不单改 D-041 批准文意）。提案人≠批准人红线保持。
- **D-006 → D-041 沿革**：round-67 批准方案 2——300s 降为观测项（超线不阻断发布）、600s 为硬挂死护栏；升级触发改为「连续 3 轮 >450s 或任一单项超线」；环比中位 >20% 必须归因。执行口径（round-67 起）见本节 D-041。
- **本轮触发复盘（完整数据见 `reports/d-041-r134.md`）**：
  1. **连续 3 轮 >450s 实证两次窝口**：round-111..117（7 连轮，中位 461.3→600.3）、round-126..131（6 连轮，450.334 擦线起）——两次均超 D-041 升级线，**零处置留痕**（本轮补齐）。
  2. **600s 挂死护栏被实证贯穿两次且仍为绿**：round-115 run2 **703.774s**（`logs/suite-r115-run2.log`，652 项 OK，各 1+2 skip）、round-117 run2 **650.172s**（`logs/suite-r117-run2.log`，653 项 OK，2 skip）——600s 线被越且套件完跑，release-gate `REDLINE_SEC = 300` 只作观测（`redline_note` 已标「不阻断发布」），**600s 从未在代码层强制执行**（未见 `timeout 600` 包裹 `unittest discover` 的任何脚本/CI 步骤）。
  3. **环比中位 >20% 实证一次未归因**：round-114 中位 523.0 → round-115 中位 632.1（**+20.9%**），当时未归因（本轮只登记事实：增量来自 LLM-judge 语义臂测试 648→652 + 疑似主机负载；无单点回归证据；round-117→118 回落 −28.3% 同窗）。
  4. 反向窗口：round-132（416.966 / 394.449，<450）、round-133（426.089 / 409.668，<450）——升级线窗口自然解除，无连续 >450s 性突发证据。
- **候选（总监裁定，不预设）**：
  1. **A. 维持 D-041 现状**：300s 观测 + 600s 口头护栏；每次触线补 writeup 了事；代价=600s 线继续只读不写，653→703s 型慢跑「绿过」不被见（信号载荷失效复发）。
  2. **B. 代码执行 600s**：`unittest discover` 在 CI/本地两侧包 `timeout 600`（Windows 用 timeout 等价方案），超时判红；同时 release-gate 增挂 `redline_sec=600` 判红（不再是 300 观测）。代价=r115/r117 型慢跑会红，需要先复测基线（或同期判 650→550s 归因确认负载主导后执行）。
  3. **C. 升级触发线 450s→540s**：口径保留，仅把噪声区间上移（实测 r126 450.334 擦线、r128 450.510 擦线说明线位贴住常态）；保留 D-006 判定纪律不变。
- **提案人建议（不构成批准）**：**B+C 组合**——(i) 触发线 450s→540s（连续 3 轮窗口判定不变）；(ii) 600s 挂死线以真实 timeout 强制执行，线权升格为 release-gate 可判红项；(iii) release-gate 红线入参（`redline_sec`）随下一契约轮（而非本 writeup 轮）落款，配反向验证（注入慢测确认判红）；(iv) 口径「超线即 writeup 当轮交付」写入维护纪律，不允许静默累计。
- **决策**：**B+C 批准**——(i) 触发线 450s→540s（连续 3 轮窗口判定不变）；
  (ii) 600s 挂死线代码强制执行：release-gate 判红（任何一跑 >600s → suite_double_run FAIL 阻断发布）；
  CI nightly ubuntu 以 `timeout 600 python -m pytest tests -n 2 -q` 执行，windows 以 job timeout-minutes: 45 兜底（无 GNU timeout）；
  (iii) 反向验证已跑：fixture（r133 双跑同款，run1 替换为 601.313s）→ suite_double_run **FAIL**（第 1 跑 601.313 秒 > 600s 挂死护栏）；
  干净 fixture（双跑均 <600s）→ **PASS**；`reports/release-gate/fixtures-r135/{ok,hang}.json` 入仓为证。
- **维护落款**：release-gate.py REDLINE_SEC=600（判红）；self-check.yml nightly 双分支分派；
  redline_note 改为「600s 挂死护栏（D-052）」。代价：r115/r117 型 600s+ 慢跑从此被判红阻断发布——预期内（D-052 批准语义）。
- **证据**：`reports/d-041-r134.md`（完整触线矩阵 r108..r134）；`logs/suite-r115-run2.log`、`logs/suite-r117-run2.log`；
  `docs/DEVELOPMENT.md`（r108..r133 双跑沿革）；`docs/PROGRESS.md` §1 契约测试单元格；`skills/self-iteration/scripts/release-gate.py:71` `REDLINE_SEC = 300`。
- **判定粒度勘误（round-176，维护决定）**：D-052 的「连续 3 轮 >540s」统一按**双跑中位 >540s**判定，不是「任一一跑 >540s」——理由：单跑抖动不代表一轮变慢，且单跑 >600s 已有 D-052 硬挂死护栏独立判红；按此定义 r166–r168 不触线（r168 中位 531.0），与 r175 审计的两种口径登记一致。本勘误只明确判定粒度，不改 540s/600s 数值、不改 D-041 批准文意；历史窗口记录保留不回改。

## D-053 SWRBench 宿主臂归因修正：执行质量无保障，门禁为对策（round-137，v2.39.0）

- **日期**：2026-11-12（round-137；提案人=迭代官，批准=总监 2026-11-12 会话内批准，提案人≠批准人保持）
- **状态**：已批准并当轮落地（归因表述修正）；门禁对策（review-quality-gate）排期 round-138。
- **背景（两次执行结果分歧）**：同一宿主评审机制、同一语料，r114 stride-10 批（round-114，n=100，50/50）实跑出 PR 级 F1 0.5789 / point 级 F1 0.3656 / 27 条 findings（`reports/reviewbench/swrenbench-r114.md`）；r129–r132 全量 n=1000（`reports/swr-r13*.md`、ROADMAP-HISTORY §5.90–§5.92）1000/1000 响应全空 → recall=0。r132 将其归因为「host 文件协议不胜任此语料」并收缩对外口径。
- **归因修正（本决策核心）**：全空响应是**执行会话未实质评审**（把 [] 当稳妥默认输出），不是协议缺陷——协议的 prompt/缓存/落盘链路在 r114 已被证明可用且出正数。原归因会让未来读者错误弃用一个可用机制。
- **候选**：
  1. A. 维持原归因：对外数字不变、因果表述保留——代价=归因与仓内证据（r114 报告）直接冲突，协议被错误弃用，同类黑洞（千级评阅预算产出零 findings）无防复发机制。
  2. B. 归因修正为「执行质量无保障」+ 门禁对策（review-quality-gate，r138 排期）——代价=对外数字不变（0.42% 唯一对外裁定维持），只改因果表述；承认执行侧流程缺陷；历史记录不回改（勘误后缀模式）。
- **决策**：采纳 B（总监 2026-11-12 批准）。
- **代价与影响**：①README 两处 + PROGRESS 两处对外口径行改因果表述，数字不动；②历史记录（events/ROADMAP-HISTORY/批次报告）不回改；③r138 落地 review-quality-gate 后，宿主臂全量评测预算恢复须持门禁通过凭证；④round-132 未登记 DECISIONS 的缺口由本条补齐。
