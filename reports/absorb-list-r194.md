# 详细能力吸收列表（r194，2026-11-21）

> 研究基础：四轮广度提取（Harness 生态 119 深读 / 可吸收能力地图 95 项 / 核心 42+全景+落地指南 / 大索引 374+285+270 栈交集）+ 两轮机制深拆（评测基础设施 8 对象 / 治理与上下文 12 对象）+ 移动端/归档适用性确认。
> **诚实边界**：资料为结论级+机制级描述；标注「上游补研」的条目在实施前需读对应上游仓库源码补 schema 细节（资料明确缺口 5 处：Codex 三档判据 / CC 7 类钩子清单 / SKILL.md 完整字段 / recipes schema / elicitation 机制）。
> **总纪律**：读设计不引依赖（硬约束 1 + Aider 放缓警示）；每项落地须过反向验证（红线 6）；对外口径数字不动。
> 工作量档：S=≤1 轮 / M=1-2 轮 / L=≥3 轮。优先级：P1（阶段一）/ P2（阶段二）/ P3（阶段三/条件轮）。

## A. 评测与观测（对接 eval-harness + trace.py）

| ID | 能力 | 来源 | 机制要点 | dev-agent 落点 | 量 | 补研 | 验收口径 |
|---|---|---|---|---|---|---|---|
| AB-01 | Langfuse 评分回挂+评测集导出 | Langfuse 37.6k MIT | trace=树形 span；评分挂钩（按 trace/span 挂分）；数据集+实验对比；数据可回放成评测集；⚠️高频需采样防存储膨胀 | agent/trace.py 已输出 Langfuse 兼容 JSONL——补 score 挂载字段 + trace 落盘数据回灌 eval-harness 作回归集的导出器。**r199 勘误**：验收口径原写「被 run-samples.py 消费」——schema 核查后 trace 会话与评审缺陷样本不同构，消费者勘误为 judge 重跑路径（AB-02 集成），导出器 trace-export.py（#87）已带 schema 声明与质检 | M | score API 形态需上游补研 | 导出评测集含 score 聚合与质检（trace-export 契约 4 条） |
| AB-02 | LLM 质量指标 pytest 化 | DeepEval 19.6k Apache | LLMTestCase+Metrics=G-Eval/幻觉/忠实度/相关性（LLM-as-judge），断言阈值进 CI | swrenbench-import.py LLM-judge 语义臂：G-Eval 类指标作 judge 指标候选，包装成 pytest 断言进 CI | S-M | 阈值写法/judge 机制需上游补研 | CI 出现指标单测格并与 precision 护栏并行出数 |
| AB-03 | 提示/模型变更回归门 | promptfoo 27.5k MIT | YAML 用例矩阵（providers×prompt 变体×断言）+红队策略集+CI 断言 | precision-gate.py / review-quality-gate.py 增「声明层」：提示或模型变更时按矩阵跑回归并出 PASS/FAIL | S-M | YAML 字段形态需上游补研 | 改提示必触发矩阵回归，红即拦 |
| AB-04 | 评测任务三件套抽象 | Harbor 7.2k | 任务/求解器/验证器三件套+矩阵并行+缓存（细节资料未展开） | eval-harness（forward-bench/run-regression）重构出 task/solver/validator 命名与目录约定 | M | 任务包 schema 需上游补研 | 现有评测链在新命名约定下回归全绿 |
| AB-05 | 终端任务打包格式 | Terminal-Bench 2.6k | 任务=容器镜像+测试脚本+自动判分器，无 GPU 依赖 | gold-sample/pro-sample 容器化跑分的最小任务包格式 | M | 判分器语义需上游补研 | 一个容器化样本端到端判分通过 |
| AB-06 | 提示可编译化 | DSPy 39k MIT | Signature→Module→Optimizer（BootstrapFewShot/MIPROv2/GEPA 评估器驱动改提示与少样本）→产物导出为普通提示；一次性任务不适用 | rules-select.py 与评审链提示词：离线评估器驱动优化，产物固化为静态 md 回主流程 | M-L | GEPA/MIPROv2 差异需上游补研 | 优化前后 precision 护栏数字对照（不许降） |

## B. MCP 工具面（对接 mcp/review_mcp.py 16 工具）

| ID | 能力 | 来源 | 机制要点 | dev-agent 落点 | 量 | 补研 | 验收口径 |
|---|---|---|---|---|---|---|---|
| AB-07 | ACI 工具面审计 | SWE-agent 20.8k MIT | **接口设计本身决定 agent 成功率**（非模型非提示）；三准则=短命令/反馈及时/防呆 | 16 工具逐条按三准则对照（描述/反馈格式/防呆），修订后用 precision 护栏复测量化收益 | S | 接口实例需读 ACI 论文补 | 修订前后评测数字对照报告 |
| AB-08 | MCP 投毒扫描 | mcp-scan 3.3k | ①工具描述投毒 ②跨服务器阴影动作 ③baseline 变更告警；工具描述=提示注入面 | nightly 前置 mcp-scan（16 工具描述+配置 baseline 快照比对） | S | 无 | nightly 出现扫描步且基线文件入仓 |
| AB-09 | 工具描述=提示工程 | FastMCP/指南 2 | 参数/返回/副作用显式标注；写操作幂等+二次确认+审批门控 | 16 工具描述规范化（副作用标注），写类工具（apply/fix）与五道闸联动说明补齐 | S | 无 | 描述审计清单入 docs/06-operations |
| AB-10 | elicitation 批准书交互 | MCP spec 2026-07-28 | 规范新增能力（机制资料未展开） | 五道闸的 MCP 面形态：批准书交互走 elicitation 的可行性评估 | S-M | **必须先读规范原文** | 可行性评估提案（实现与否据评估定） |

## C. 编码循环与治理（对接 agent/phases.py/edit_formats/workspace.py + 五道闸）

| ID | 能力 | 来源 | 机制要点 | dev-agent 落点 | 量 | 补研 | 验收口径 |
|---|---|---|---|---|---|---|---|
| AB-11 | 影子 git 检查点 | Cline 71.8k Apache / 指南 3 | 独立目录影子仓库（--git-dir）与用户 git 解耦；写文件前快照；出错一键回滚；触发粒度（每次 edit/每轮）资料未展开 | 编码循环 workspace 本地档：edit 前影子快照，即时校验失败/评审回滚可一键还原（补 A5 缺口：fix-apply 有回滚但编码循环无快照） | M | 触发粒度自定（建议每轮前） | 构造失败场景实证回滚还原工作区 |
| AB-12 | Plan 阶段工具面收窄 | Cline/Claude Code | Plan/Act 分离：规划阶段禁写工具，批准后放开；实现方式（schema 删除 vs 执行拦截）资料未展开 | phases.py locate 阶段工具面显式只读化（对照现有角色动作面门禁查缺补齐） | S | 无 | locate 阶段写动作被拦的契约 |
| AB-13 | Hooks 拦截器范式 | Claude Code 156k | PreToolUse 等 7 类生命周期钩子可阻塞/改写工具调用；配套 allow/ask/deny | 五道闸对照：pre/post 拦截器结构评审（我们已有闸面——查缺「改写返回」能力而非仅 deny） | M | 7 类清单+返回协议需上游补研 | 对照报告+缺项处置 |
| AB-14 | 内核级沙箱兜底 | Codex 135.9k Apache | 提示层审批+OS 层兜底：macOS Seatbelt profile / Linux Landlock LSM；三档 read-only/auto/full-access | 执行闸远期强化档（Linux Landlock 可先探）；worktree 容器档已有——评估内核档增量价值 | L | 三档判据+隔离范围需上游补研 | 可行性提案（实现与否据评估定） |
| AB-15 | 原子 Edit/run_cmd 对照 | opencode 227.8k MIT | old 唯一匹配（count==1）→原子替换→diff 预览→失败不写；run_cmd 白名单+60s 超时+8000 字符截断 | edit_formats 与终端工具做减法审计对照（我们已有同型实现——确认参数面无缺口） | S | opencode 真实默认值需上游补研 | 对照清单（预期结论=已对齐） |
| AB-16 | rail 校验注册表 | Guardrails AI 7.6k Apache | 可组合校验器+校验失败重试生成+on_fail 动作 | 五道闸输出侧对照：闸面 on_fail 动作标准化评估 | M | on_fail 枚举需上游补研 | 对照报告（远期） |

## D. 上下文工程（对接 agent/repo_map.py + 材料构造）

| ID | 能力 | 来源 | 机制要点 | dev-agent 落点 | 量 | 补研 | 验收口径 |
|---|---|---|---|---|---|---|---|
| AB-17 | REPOMAP 中心度装填 | aider 50.2k Apache ⚠️放缓 | tree-sitter 抽符号→引用图→类 PageRank 中心度→token 预算内截断输出；模块独立可移植 | repo_map 单变量复评 D-031（当时「真实 Top-8 无增益」按 refs 排序裁默认）——按 aider 法重验图排序+预算装填 | S-M | PageRank 参数细节需读上游源码 | 真 Task Top-8 对照实验报告（增益≥阈值才转正） |
| AB-18 | 符号级取用 | Serena 31.5k MIT | SolidLSP 多语言 LSP；find_symbol/references/replace_symbol_body；「先地图后取用」免全文索引；MCP 即插（uvx） | 评审材料定位对照实验：符号级 vs 整文件取窗的上下文成本/漏检对照；工具粒度（find→read→replace 闭环）借鉴 | S | LSP 后端选型需上游补研 | 对照实验报告（材料 token 与命中率） |
| AB-19 | 整仓概览件 | repomix 29.3k MIT | 仓库→单文件（目录树/token 统计/敏感信息检查） | 大仓评审入口快速概览（弱候选，repo_map 已覆盖大半） | S | 无 | 按需 |

## E. 记忆与技能资产（对接 retro/ 记忆 + skills/）

| ID | 能力 | 来源 | 机制要点 | dev-agent 落点 | 量 | 补研 | 验收口径 |
|---|---|---|---|---|---|---|---|
| AB-20 | 记忆三级管线 | mem0 69.2k Apache | 抽取→合并（LLM 判 ADD/UPDATE/DELETE）→检索；三级命名空间 user/agent/run；核心资产=add() 决策提示；每次 add 耗 LLM；PII 先过 Presidio | 误报模式库/评审经验记忆升级：few-shot 注入前加抽取-合并决策（决策提示自写，不装库） | M-L | 判据提示词需读 mem0 源码 | 重复误报率对照（注入质量） |
| AB-21 | SKILL.md 渐进披露 | superpowers 321.7k / anthropics 197.6k | frontmatter 触发描述+正文按需加载+确定性步骤脚本化；文件夹拷贝即装；已成跨 harness 通用格式 | skills/*/SKILL.md 对齐开放规范（我们已同构——补触发词 frontmatter 规范化+按需加载约定） | M | 完整字段 schema 需上游补研 | doc-structure 增 SKILL.md frontmatter 判据 |
| AB-22 | 配方/规则注入 | goose 56.8k recipes + Continue rules | recipes=YAML 任务配方可版本化分发；rules=团队规范声明式注入 | 评审 preset 配方化（report-adapter 三维度已有 spec——评估 YAML 化收益）+被审仓库 rules 注入评估 | M | schema 需上游补研 | 提案级（先评估后做） |

## F. 战略对照（不产生代码，产生认知/文档）

| ID | 结论 | 依据 |
|---|---|---|
| AB-23 | 引擎组合差异化空白：Ruff/LibCST/ast-grep 用于评审 agent 零公开同类；竞品走 diff+检索 | 大索引 374+285+270 全量 grep |
| AB-24 | 五道闸被 AutoGPT 反例反向印证（无界循环+弱工具面+无权限治理=不可用） | Harness 全集 IDE#26 |
| AB-25 | MCP Registry 新支柱 + 工具描述=注入面 → mcp-scan 必要性 | 全景 §2.5 + Harness #61/#100 |
| AB-26 | 退场跟踪纪律：Aider 放缓（REPOMAP 借鉴=读设计）、Flowise 2026-08 停更、Daytona/gpt-pilot 放缓 | 全景 §十二-7 + 归档体检 |
| AB-27 | Windows 维度资料不支撑（仅 Crush 一例明示原生）→ 我们的台账坑集是独有积累 | Harness 全集 Windows 节 |

## G. 明确不吸收（防止重复调研）

多代理群聊编排（单评审主线）、RAGAS/lm-eval/OpenCompass（评模型非评 agent）、MemOS/cognee/Letta 装库（思想可借依赖过重）、Zep/Graphiti 时序图谱（无多跳需求）、HippoRAG、移动端 M1-M9 全线（端侧引擎/GUI 自动化/语音——桌面 CLI 无关）、mcp-gateway（单实例阶段）、NeMo Guardrails（对话场景）、Llama Guard（本地评审威胁面小）、OpenInterpreter/agent-zero（沙箱已有三档）、gpt-pilot/plandex（⚠️放缓+思想已含）。
