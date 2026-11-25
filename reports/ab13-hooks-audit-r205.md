# AB-13 Hooks 拦截器对照审计（r205，2026-11-21）

> 对照源：Claude Code Hooks 机制（PreToolUse 等 7 类生命周期钩子，可阻塞/**改写**工具调用）。
> 审计对象：五道闸治理框架（fix-apply.py + approve-patch.py + approve-plan.py）。
> 方法：逐闸面状态机映射 → Claude Code Hooks 能力矩阵 → 差距判定（补齐/保留/反向确认）。

## 一、状态机映射

| 闸面 | Claude Code 对应 | 现有能力 | 改写能力 |
|---|---|---|---|
| approve-plan.py（闸 1） | PreToolUse | 工单签发（APPROVED→工单 / REJECTED→reasons+reuse_hints） | ❌ 不改写 |
| approve-patch.py（闸 2） | PreToolUse | 批准书签发（六项核验全过→APPROVED / 任一不过→REJECTED+reasons） | ❌ 不改写 |
| fix-apply.py（落盘闸） | PostToolUse | 五道闸全过→APPLIED / 任一失败→ROLLED_BACK（自动回滚） | ❌ 不改写 |
| code_review_feedback | PostToolUse | 驳回入库+按 pattern 聚合 | ❌ 只写入 |
| code_review_retro | PostToolUse | 坑台账收集/归档/轮报生成 | ❌ 只写入 |

## 二、Claude Code Hooks「改写」能力差距判定

**差距**：五道闸只支持 PASS（放行）和 FAIL（拒绝/回滚），不支持 **modify-then-approve**（自动修补后放行）。

**判定：保留（不改写是有意设计，非缺陷）**——理由三条：
1. **审核分立硬约束（硬约束 7）**：闸面自动改写补丁内容 = 闸面创建自己随后批准的内容 = 变相自审自批。
2. **补丁不可变原则**：批准书 sha256 绑定当前补丁包——闸面改写会破断 sha256 链。
3. **修正路径已存在**：补丁有问题 → REJECTED → fix-patch.py 重出 → 重新批准。修正由修复团队做（不该由闸面做），责任链清晰。

## 三、Claude Code Hooks 有而五道闸无的模式（信息级）

| 模式 | Claude Code 实现 | 五道闸现状 | 适用性 |
|---|---|---|---|
| 改写返回 | 钩子返回修改后的调用参数 | 无（只有 pass/fail） | **不适用**（见上判定） |
| 阻断传播 | 钩子 stopPropagation | ROLLED_BACK 即等效（git 回滚=阻断） | **已有对应** |
| 逐工具审批 | 每次工具调用前询问 | approve-plan/patch 审批面 | **已有对应** |
| TodoWrite 显式化 | 强制任务分解 | code-task phases.py 三角色+决策台账 | **已有对应** |
| allow/ask/deny 三级 | 权限规则 | APPLIED/PROPOSED/REJECTED 三态 | **已有对应** |

## 四、结论

五道闸 vs Claude Code Hooks：**能力覆盖 4/5**，唯一差距（改写）是**有意排除**——符合治理先行原则。无需改动。

审计结论与 AB-12（Plan 收窄已对齐）、AB-15（原子 Edit 已对齐）同类：**已对齐零缺口**。
