# AB-14 内核级沙箱可行性 + RouteLLM 读设计（r218，2026-11-27）——阶段三收官

> 对照源：Codex 135.9k Apache（提示层审批 + OS 层兜底：macOS Seatbelt profile / Linux Landlock LSM；三档 read-only/auto/full-access）+ RouteLLM（难度路由，⚠️项目已放缓）。
> 总监批准背景：2026-11-27 阶段三全量批准。

## 一、AB-14 内核级沙箱：三层防护现状与缺口

### 1.1 现有防护层

| Codex 层 | dev-agent 现状 | 判定 |
|---|---|---|
| 提示层审批 | 五道闸 + 工具面收窄（locate 只读）+ confirm 语义 | 已对齐 |
| OS 层兜底 | **local 档无内核级兜底**；container 档（docker exec）有容器隔离 | **local 档真实缺口** |
| 工作区隔离 | workspace.py 三档（local worktree / container / remote） | 已对齐 |

### 1.2 平台可行性判定

| 平台 | 机制 | 可行性 |
|---|---|---|
| Linux（Landlock LSM） | 非特权沙箱：限制 FS 写/网络；编码循环 subprocess 面可直接套 | **技术可行**——但 Linux 先行=部署面条件（本机 Windows，Linux 部署留操作员面）；container 档已在 Linux 命名空间内获得等效隔离 |
| Windows（本机） | 无 Landlock/Seatbelt 等效物：AppContainer 过重（MSIX 面）、Job Objects 限进程树不限 FS 写 | **暂不实施**——worktree 隔离 + 五道闸已覆盖当前威胁面（评审/修复只写 review-fix 分支 + 批准书绑定），kernel 档增量价值低于复杂度 |
| macOS（Seatbelt） | profile 白名单 | 同 Linux：留部署面条件 |

### 1.3 AB-14 终局

**可行性评估完成，暂不实施**——理由：
1. **威胁面已覆盖**：写入面被五道闸（唯一落盘入口 fix-apply + 批准书 sha256）+ worktree 分支隔离约束；容器档提供 OS 级隔离（部署需要时 `--backend container:<image>` 即得，无需内核档）。
2. **平台错位**：Landlock=Linux 先行，本机 Windows 无等效机制（Job Objects 不限 FS 写）；内核档的实施前提（Linux 部署 + 容器档不够用）均未成立。
3. **实施条件备档**：Linux 部署场景出现且容器档被证明不够用（如需要非容器化 GPU 负载旁的写约束）→ 按 Codex 三档语义（read-only/auto/full-access）实现 Landlock profile 装载器（设计面已备：`agent/workspace.py` 加 sandbox-tier 维度）。

与 AB-10 同型结论：评估完成暂不实施（吸收列表验收口径=可行性提案）。

## 二、RouteLLM 难度路由读设计

### 2.1 机制要点（读设计）

RouteLLM：查询→难度路由器→强模型/弱模型分派（成本优化 2.8–5x 声称）。
路由器形态：矩阵分解/BERT 分类器/相似度加权——均需**训练语料 + 独立推理面**。

### 2.2 判定

**读设计完成，不采纳**——理由：
1. **成本压力未现**：当前 LLM 臂走宿主协议（零 API 成本）+ 评测臂小 n；路由优化无成本可省。
2. **项目已放缓**（退场跟踪纪律）：依赖引入违反「放缓项目读设计不引依赖」。
3. **将来条件**：多模型 API 计费场景出现后，按「评审任务难度→模型档位」路由评估；届时 gate-run 的任务分派面是天然接入点（备档）。

## 三、阶段三总清点（七项全终局）

| 项 | 终局 | 产物 |
|---|---|---|
| AB-10 elicitation | 评估完成暂不实现（批准书载体结构性冲突） | reports/ab10-elicitation-r213.md |
| AB-22 配方化 | rules 注入落地（#89 脚本）；配方面已对齐 | repo-rules-inject.py |
| AB-16 rails | 已对齐零缺口（2 面有意排除，治理更强） | reports/ab16-rails-r215.md |
| AB-20 记忆管线 | 落地（#89 脚本，双臂诚实口径） | memory-pipeline.py |
| AB-06 DSPy | 落地（#90 脚本，不许降闸+指纹固化） | prompt-optimizer.py |
| AB-14 沙箱 | 评估完成暂不实施（平台错位+威胁面已覆盖） | 本报告 |
| RouteLLM | 读设计完成不采纳（成本压力未现+项目放缓） | 本报告 |

**阶段三收官**：7 项全终局（4 落地 + 3 评估性终局）。吸收列表 27 项 + RouteLLM 全部有终局结论，零悬置。
