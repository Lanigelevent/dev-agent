# AB-10 elicitation 批准书交互可行性评估（r213，2026-11-27）

> 总监裁决：2026-11-27 用户全量批准阶段三（AB-06/10/14/16/20/22 + RouteLLM 读设计）。
> 规范取证源：@modelcontextprotocol/sdk 1.24.0（npmmirror 国内源实测可达）——吸收列表「必先读规范原文」前置达成；官方站点直连超时（降级记录：国际直连不稳，走国内 SDK 源取证，规范语义以 SDK 类型定义为准）。

## 一、规范机制取证（SDK 类型定义实证）

| 要素 | 定义（SDK 1.24.0） | 备注 |
|---|---|---|
| 能力声明 | client capabilities `elicitation: {create}` | 服务端探测客户端是否支持 |
| 请求 | `elicitation/create`：form 模式（`message: string` + `requestedSchema`）或 url 模式（`mode:"url"` + `elicitationUri`） | 我们实现协议版 2025-06-18 已含 form 模式；url 模式为后续草案面 |
| requestedSchema 约束 | 原语白名单：StringSchema（format: email/date/uri/date-time）/ NumberSchema（number/integer）/ BooleanSchema / EnumStringSchema（含 enumNames）——**禁止嵌套对象** | 结构化表单能力有限 |
| 结果 | `ElicitResult {action: "accept"|"decline"|"cancel", content?: Record<string, string\|number\|boolean\|string[]>}` | 瞬态应答，无持久化语义 |
| 错误面 | `UrlElicitationRequiredError`（URL 模式带外请求）；ElicitationCompleteNotification | — |
| 安全条款 | 服务端不得经 elicitation 收集凭据/敏感信息 | 与硬约束 5（产物零明文凭据）同向 |

## 二、五道闸映射分析

### 2.1 候选映射面

1. **批准书载体**（apply/fix 调用时的实时审批）：服务端在 confirm 缺失时发 elicitation/create（表单：approve 布尔 + confirm_sha256 字符串）。
2. **防呆提示面**：confirm=true 缺失时的结构化提示（替代纯文本错误）。
3. **URL 模式批准页**：带外 web 批准页（闸 2 的 UI 形态）。

### 2.2 三面判定

1. **批准书载体：不采纳（治理冲突）**——elicitation 是瞬态交互原语：应答不落盘、无 sha256 绑定、无审计追溯。批准书（approval.json）是持久化工件 + sha256 绑定 + 工作流状态；两人规则（提案人≠批准人）要求批准行为可审计可复算。用 elicitation 替代批准书 = 把科层制签字权降级为弹窗确认——**结构性冲突，不做**。
2. **防呆提示面：有条件采纳**——apply/fix 类工具 confirm 缺失时，若客户端声明 elicitation 能力（initialize 探测 capabilities.elicitation），发结构化表单提示（approve: BooleanSchema + acknowledged_sha256: StringSchema）；客户端不支持时回退现行 confirm=true 口径。增量价值：防呆交互升级，治理不变。
3. **URL 模式批准页：不采纳**——带外 web 页外置状态，批准结果回传无 sha256 绑定通道；与批准书工件纪律冲突。

## 三、落地判据与建议

**建议：暂不实现**（连防呆面一并缓行）——理由：
1. 防呆面的增量价值有限（现行 confirm=true + 错误文案已防呆，r195 已修订工具描述语义）；elicitation 客户端支持面（dsh / ZCode 插件宿主）未验证——先实现=赌客户端行为。
2. 治理核心（批准书工件）与 elicitation 结构性不兼容（瞬态 vs 持久化）；两人规则不可降级。
3. 若未来 dsh/ZCode 客户端实测支持 elicitation，防呆面按 §2.2-2 的有条件采纳设计落地（能力探测 + 回退），设计已备于此报告。

**AB-10 终局：可行性评估完成，暂不实现**——评估产物即验收口径（吸收列表原文「可行性评估提案（实现与否据评估定）」）；设计面（能力探测+回退的防呆面）备档待客户端支持面成熟。

## 四、降级记录

- 官方规范站 modelcontextprotocol.io 直连超时（10s×2 次）；GitHub raw 连接重置。
- 降级路径：WebSearch 语义取证 + npmmirror SDK tarball 实测（1.24.0）——规范语义以 SDK 类型定义为准，符合「国际直连仅作回退，降级须记录」纪律。
