# 开源生态吸收地图（r193 研究轮，2026-11-21）

> 资料源：`<user-home>\Desktop\AI开源项目汇总\`（450+ 项目 / 29 方向 / 104 项能力，⭐经 GitHub API 实测 2026-11-19/20）。
> 方法：四路并行只读研读（Harness 生态 119 深读 / 可吸收能力地图 95 项 / 核心 42+全景+落地指南 / 大索引栈交集扫描），逐条对照 dev-agent 现有模块判定「已有对应 / 候选借鉴 / 不适用」。
> 纪律：资料按不受信数据处理（只读分析，未执行任何附带脚本）；借鉴一律「读设计、不引依赖」（Aider 放缓警示 + 硬约束 1 许可面）；对外口径数字不动。

## 一、战略级确认（不改数字，改认知）

1. **引擎组合是差异化空白**：三份大索引全量扫描，Ruff/LibCST/ast-grep 组合用于评审 agent **零公开同类**（tree-sitter 仅 Aider 一处）；竞品（PR-Agent 16.4k / Qodo 2.0 / Kodus / Gito）走 diff+检索路线而非静态分析引擎路线。「静态分析引擎路线」是我们的差异化定位，可在文档面显性化（不改对外口径数字）。
2. **反例验证我们的治理设计**：AutoGPT 188k⭐ 被资料判为反例（无界循环+弱工具面+无权限治理=不可用）——五道闸恰是其解，治理先行路线被生态反例反向印证。
3. **MCP 押注正确且需跟进 Registry**：MCP servers 92.1k⭐、2026-07-28 规范落地、Registry 成新支柱；16 工具异步作业链与生态收敛方向一致。
4. **Aider 放缓警示**：REPOMAP 是「上下文工程必读」但项目放缓——借鉴以读设计为主，不引依赖。

## 二、收敛级发现（≥2 路独立命中，可信度高）

### A. 评测闭环强化（3/4 路命中）——我们评测链的三个差距点
| 差距点 | 生态做法 | 对应项目 | 落地形态 |
|---|---|---|---|
| 评审意见质量无 pytest 化指标单测 | G-Eval 等指标写成 pytest 断言进 CI | DeepEval 19.6k | 指标集封装进 CI 单测，与 precision 护栏互补 |
| 无提示/模型变更回归门 | YAML 用例矩阵 + 断言 + CI gate | promptfoo 27.5k | 「改提示/换模型」回归门（与 SLO 门禁同层） |
| trace.py 仅 JSONL 兼容 | 评分回挂 / 数据集回放 / 实验对比 | Langfuse 37.6k | trace.py 补 score 挂载 + 评测集导出 |

### B. MCP 工具面治理（3/4 路命中）——16 工具的三道自检
1. **ACI 准则审查**（SWE-agent 20.8k）：工具接口设计本身决定 agent 成功率——按「短命令/快反馈/防呆」逐条审 16 工具，用 precision 护栏复测量化收益（与 SWE-bench 链同源，改造成本最低）。
2. **mcp-scan 投毒扫描**（3.3k）：工具描述注入/跨服务阴影动作/baseline 告警——nightly 前置扫描（治理项，成本低）。
3. **工具描述=提示工程**（FastMCP/指南 2）：参数/返回/副作用显式标注；写操作幂等+二次确认联动审批；elicitation 可承载批准书交互（五道闸的 MCP 面形态）。

### C. 编码循环治理件（2/4 路命中）
- **影子 git 检查点**（Cline 71.8k）：改动前快照、失败一键回滚——对照我们 fix-apply 有回滚但编码循环 workspace 档无快照（A5 缺口）。
- **Plan 禁写显式化**（Cline/Claude Code）：phases.py 三阶段已有，对照查缺动作面门禁宽度。
- opencode 原子 Edit + run_cmd 白名单+超时+截断：与 edit_formats 唯一命中同型，做减法审计对照。

### D. 上下文工程（3/4 路命中）
- **aider REPOMAP**：tree-sitter 符号→PageRank 中心度→token 预算装填——对照 D-031（图排序默认关：「真实 Top-8 无增益」），值得单变量实验复评（读设计，不引依赖）。
- **Serena 符号级取用**（31.5k）：LSP find/replace 符号粒度工具、MCP 即插（uvx）——「先地图后符号级取用」替代整文件读取，评审材料定位强化。
- repomix 整仓概览件：评审入口快速摘要（弱候选）。

### E. 治理/安全链（2/4 路命中）
- Presidio PII 出站脱敏代理模式：对照我们审计脱敏（自家实现已覆盖核心，作增强对照）。
- garak/PyRIT 红队探针：变异抽检的红队化远期项。
- Guardrails AI rail 注册表 + on_fail 动作：闸门 on_fail 标准化（弱借鉴）。

### F. 技能资产化（2/4 路命中）
- superpowers 321.7k / anthropics/skills 197.6k：**SKILL.md 成跨 harness 通用格式**（元数据常驻+正文按需加载+确定性步骤脚本化）——我们 skills/*/SKILL.md 已同构，低成本对齐开放规范；评审规则/修复策略可打包为可分发资产。

## 三、判定总表（四路交叉去重后）

**已有对应（无需动作）**：SWE-bench 四口径评测链、DeepEval 式 SLO 门禁理念、MCP 服务器与异步作业、repo_map 目录树+token 统计、openai 兼容 provider、Langfuse 兼容 trace（协议层）、五道闸（AutoGPT 反例反向印证）、AGENTS.md、Crush 式多会话隔离（workspace 三档）、claude-code-router 式协议转换。

**候选借鉴（按价值排序）**：
1. trace.py 补 Langfuse 评分回挂+评测集导出（A12 差距，评测闭环的第一块板）
2. 评审意见质量指标 pytest 化进 CI（DeepEval 式，与 precision 护栏互补）
3. prompt/模型变更回归门（promptfoo 式 YAML 矩阵）
4. SWE-agent ACI 准则审查 16 工具 + precision 护栏复测
5. mcp-scan 投毒扫描进 nightly
6. 影子 git 检查点（编码循环 workspace 档，A5 缺口）
7. repo_map 中心度排序单变量复评（D-031 重验，读设计不引依赖）
8. Serena 符号级取用对照实验（评审材料定位）
9. SKILL.md 渐进披露规范对齐（元数据常驻+按需加载）
10. elicitation 承载批准书交互（五道闸 MCP 面形态，远期）

**不适用/观察项**：多代理群聊编排（单评审主线无需）、RAGAS/lm-eval（评模型非评 agent）、MemOS/cognee 装库（思想可借依赖过重）、移动端/语音/视频全线、mcp-gateway（多实例部署时再看）、Llama Guard 输入分类器（本地评审威胁面小）。

## 四、Windows 维度说明

资料 119 条 Harness 目中仅 Crush 一例明示「Windows 原生」；Python 系 harness 普遍未提 Windows 差异——**该资料不能作为 Windows 维度的依据**，我们的台账坑集（PYTHONUTF8/CRLF/WinError 206/共享锁）仍是独有积累。
