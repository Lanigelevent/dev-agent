# 升级优化路线（r194 制定，2026-11-21）

> 配套文档：`reports/absorb-list-r194.md`（详细能力吸收列表，AB-01..AB-27）。
> 本路线把吸收项映射到 dev-agent 的轮次节奏，**三阶段 + 横切纪律**；每项含前置依赖与验收口径（详见吸收列表）。
> 总约束：对外口径数字不动（0.42% / 宿主臂 unavailable）；读设计不引依赖；每项过反向验证；双跑/发布闸纪律不变。

## 阶段一（近期，r194-r200：低成本高确定性，全部 S 档）

| 序 | 项 | 对应 | 量 | 前置 | 验收要点 |
|---|---|---|---|---|---|
| 1 | **AB-07 ACI 工具面审计**：16 工具按「短命令/反馈及时/防呆」逐条对照修订 | SWE-agent | S | 无 | 修订前后 precision 护栏数字对照报告 |
| 2 | **AB-08 mcp-scan 投毒扫描进 nightly**：16 工具描述+配置 baseline 快照入仓 | mcp-scan | S | 无 | nightly 新增扫描步；baseline 变更告警演练 |
| 3 | **AB-09 工具描述规范**：副作用显式标注+写类工具审批联动说明 | 指南 2 | S | 与 2 同轮顺路 | 描述审计清单入 docs/06-operations |
| 4 | **AB-12 Plan 阶段工具面收窄**：phases.py locate 只读化查缺补齐 | Cline/CC | S | 无 | locate 写动作被拦契约 |
| 5 | **AB-17 repo_map 中心度复评**：D-031 单变量重验（图排序+预算装填） | aider | S-M | 上游补研 PageRank 细节 | 真 Task 对照实验报告；增益≥阈值才转正，否则维持 D-031 |
| 6 | **AB-03 提示变更回归门**：precision-gate 增 YAML 矩阵声明层 | promptfoo | S-M | AB-02 先行更顺 | 改提示必触发矩阵回归 |
| 7 | **AB-15 原子 Edit/终端闸对照审计**：减法确认无缺口 | opencode | S | 无 | 对照清单（预期=已对齐，输出差异项处置） |

阶段一合计约 5-7 轮（含穿插的依赖刷新锚点 r200 与 light 观察轮）。

## 阶段二（中期，r200-r215：评测闭环成体系）

| 序 | 项 | 对应 | 量 | 前置 | 验收要点 |
|---|---|---|---|---|---|
| 8 | **AB-01 trace.py 补 Langfuse 评分回挂+评测集导出** | Langfuse | M | score API 上游补研 | 导出评测集被 run-samples.py 消费出数 |
| 9 | **AB-02 质量指标 pytest 化**：G-Eval 类 judge 指标进 CI | DeepEval | S-M | 8 的评测集 | CI 指标单测与 precision 护栏并行出数 |
| 10 | **AB-11 影子 git 检查点**：编码循环 workspace 本地档 edit 前快照+一键回滚 | Cline | M | 无 | 构造失败场景实证回滚还原 |
| 11 | **AB-18 Serena 符号级取用对照实验**：符号级 vs 整文件取窗 | Serena | S | 无（uvx 即插） | 材料 token 与命中率对照报告 |
| 12 | **AB-13 Hooks 拦截器对照**：五道闸「改写返回」能力查缺 | Claude Code | M | 7 类清单上游补研 | 对照报告+缺项处置 |
| 13 | **AB-04 评测任务三件套重构**：task/solver/validator 命名与目录约定 | Harbor | M | 上游补研任务包 schema | 现有评测链新约定下回归全绿 |
| 14 | **AB-21 SKILL.md 规范对齐**：frontmatter 触发词+渐进加载 | superpowers | M | 字段 schema 上游补研 | doc-structure 增 frontmatter 判据 |

阶段二约 7-9 轮。**里程碑判定**：阶段二完成=评测闭环成体系（trace→评测集→指标单测→回归门四层贯通），ACI 修订有量化收益。

## 阶段三（远期/条件轮：高价值高成本，逐项总监裁决）

| 序 | 项 | 对应 | 量 | 条件 |
|---|---|---|---|---|
| 15 | AB-06 提示可编译化（DSPy 评估器驱动优化） | DSPy | M-L | 阶段二评测集就绪后才有优化空间；优化前后护栏数字不许降 |
| 16 | AB-20 记忆三级管线（抽取-合并-检索，决策提示自写） | mem0 | M-L | 阶段二 AB-02 指标可量化「重复误报率」后立项 |
| 17 | AB-10 elicitation 批准书交互 | MCP spec | S-M | 先读 2026-07-28 规范原文出可行性评估 |
| 18 | AB-14 内核级沙箱兜底（Landlock 先探） | Codex | L | 容器档不够用才启动；Linux 先行 |
| 19 | AB-22 评审 preset 配方化 + rules 注入 | goose/Continue | M | 多仓多团队场景出现后立项 |
| 20 | AB-16 rail 校验注册表 | Guardrails | M | 远期对照 |
| 21 | RouteLLM 难度路由（⚠️项目已放缓→读设计） | RouteLLM | M | 成本压力出现后评估 |

## 横切纪律（贯穿三阶段）

1. **轮次纪律不变**：开局门/收官门/双跑/发布闸/tag 全流程照旧；吸收项逐轮落地，每轮一项主工作不贪多。
2. **上游补研步**：5 处 schema 缺口（Codex 三档判据 / CC 7 钩子 / SKILL.md 字段 / recipes schema / elicitation）+ AB-01 score API + AB-04 任务包 schema + AB-17 PageRank 细节——实施前先出「上游补研注记」进当轮报告，不盲写。
3. **依赖刷新锚点**：第十四跑约 r200 照旧；若吸收项引入评估性新依赖（如 uvx 即插的 Serena 仅实验态不入仓），按硬约束 1 走总监批准+许可证登记，缺省不引依赖。
4. **对外口径**：0.42% 与宿主臂 unavailable 不动；AB-23 差异化定位只进文档叙述面。
5. **退场跟踪**：Aider/Daytona/gpt-pilot/RouteLLM 放缓项目一律读设计不引依赖；每季度按资料「追踪清单」核对一次。
6. **验收总则**：所有评测类改动（AB-01/02/03/06/07）以 precision 护栏 + review-quality-gate 复测为验收底线；所有治理类改动（AB-08/09/12/13）以反向验证契约为准。
7. **推送节奏**：当前本地领先 17 提交，r194 收官后一并推送。

## 路线总览（一图）

```
r194-r200（阶段一）：ACI 审计→mcp-scan→描述规范→Plan 收窄→中心度复评→回归门→Edit 审计
                                                              │ 依赖刷新 r200
r200-r215（阶段二）：trace 评分/评测集→指标 pytest 化→影子 git→Serena 对照→Hooks 对照→三件套→SKILL.md
                                                              │ 里程碑=评测闭环四层贯通
r215+（阶段三）    ：DSPy 优化→mem0 记忆→elicitation→内核沙箱→配方化→rail→路由（条件轮，逐项裁决）
```
