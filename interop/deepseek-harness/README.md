# DeepSeek Harness（dsh）互操作层

把 dev-agent 的评审能力接入 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
——deepseek-ai 于 2026-08 开源的 TypeScript Agent Harness，基于 Cordis 插件框架，
口号 "Everything is a Plugin"。

## 架构：一个可执行适配器 + 两种接线

```
                       ┌─ dsh ── @deepseek-ai/dsh-mcp-client（官方桥，stdio）
mcp/review_mcp.py ←────┤
（纯标准库 MCP 服务器）  └─ ZCode ── .zcode-plugin/plugin.json 的 mcpServers
                       （其他 MCP 宿主同理：Claude Code / 任意 MCP 客户端）
```

能力只打包一次（MCP 服务器），宿主各自用自家插件机制接线——这正是 dsh
"万物皆插件" 的做法：外部能力 = MCP 服务器，dsh 侧由第一方桥接插件消费。

### dsh 接线（声明式，零 TS 源码）

```bash
pnpm dsh web --patch ./interop/deepseek-harness/cordis.yml.example
```

`insert` 块声明一个 `@deepseek-ai/dsh-mcp-client` 插件实例，stdio 拉起
`mcp/review_mcp.py`；dsh 内工具名为 `mcp__code-review__<tool>`，共 9 个：
`code_review_run`（0-10 步编排评审）、`code_review_scan`（38 条硬规则 +
可配置污点引擎快扫）、`code_review_plan`（7 维度规划）、`code_review_feedback`
（误报模式库入库）、`code_review_approve`（审核人两道闸：mode=scope 范围
裁定→修复工单，mode=patch 补丁准出→批准书）、`code_review_fix`（修复团队
凭工单出补丁，只读被审仓库）、`code_review_retro`（迭代官：mode=collect
坑台账，mode=report 轮报与改进候选）、`code_review_director`（总监：
mode=route 科层分派带 RACI 与能动性清单，mode=match 链接型案例库复用，
mode=brief 研究简报，mode=scorecard SRE 错误预算结算）、
`code_review_apply`（补丁落盘，需 `confirm: true` 且持批准书；五道闸含
行为回归，验证失败自动回滚）。

组织为科层制：总监统辖评审/修复/审核/迭代官/资料员五方（org.json），
审核人独立、任何一方不得自审自批；疑难杂症走「案例匹配→研究简报→宿主
联网调研→结论入库→行为级优化」升级链。`autoApprove: []` 表示每次工具调用
都需人工确认；要免确认可列出工具名（评审/审核/复盘/总监工具可免确认，
code_review_apply 建议保持人工确认）。

### ZCode 接线

`.zcode-plugin/plugin.json` 已声明：

```json
"mcpServers": {
  "code-review": {
    "command": "py",
    "args": ["-3", "${CLAUDE_PLUGIN_ROOT}/mcp/review_mcp.py"],
    "env": { "PYTHONIOENCODING": "utf-8" }
  }
}
```

经插件市场安装后，评审四工具即作为 MCP 工具暴露给 ZCode 会话。

## MCP 服务器契约（mcp/review_mcp.py）

- 传输：stdio 上的换行分隔 JSON-RPC 2.0；协议版本 `2025-06-18`；
  `serverInfo.name = dev-agent`。
- 工具入参均为文件路径/短枚举，直接映射到既有脚本 CLI（`--repo/--range`、
  `--file/--diff-file`、`--diff`、`--findings/--experience`）。
- `isError` 语义：脚本退出码 2（失败/参数错）→ 工具错误；退出码 1
  （NEED_HUMAN，需人工介入）不是错误，原始 JSON 在 text 里。
- 超时：run 600 秒，其余 60 秒；未知方法回 JSON-RPC -32601；坏帧回 -32700 后继续。
- 只读保证：全部工具对被审仓库只读；`code_review_feedback` 只写智能体自身经验库。
- 子进程纪律：显式参数列表 + `shell=False`，命令目标为白名单脚本，不拼接字符串。
- 预算（分钟/轮数/动态增派）经 `code_review_run.config_path` 指向的 agent.json 配置。

## 原生工具插件（可选变体，不随仓库发布）

dsh 官方教程（docs/user/develop/basic/index.md、tool.md）的原生插件形态是
TypeScript 模块：导出 `apply(ctx, config)`、`name`、`inject = ['tools']`，
用 `defineTool({...})` 定义工具并 `ctx.tools.register(...)` 注册。

本仓库**有意不随附**这种 TS 文件：它必须以运行时参数拉起 Python 子进程，
本地安全策略（Mimosa）禁止落盘此类源码；且声明式 MCP 接线已覆盖同一能力，
还少一层进程管理代码。若确需原生变体，按上述官方 API 自行添加约 20 行
`spawnSync(python, argv, { shell: false })` 包装即可，工具入参结构照抄
`mcp/review_mcp.py` 的 `TOOLS` 表。

## 本地验证

```bash
py -m pytest tests/test_interop.py     # 协议端到端 + 契约断言
py mcp/review_mcp.py                   # 手动：逐行喂 JSON-RPC
```

测试覆盖：initialize 握手、tools/list 四工具 schema、scan 干净/缺陷双向、
未知工具报错、坏帧恢复、通知帧不回复、run 工具经临时 git 仓库端到端。

## 依据的公开资料

- DeepSeek Harness 官网页：https://deepseek.com/zh/harness
- 仓库：https://github.com/deepseek-ai/deepseek-harness （MIT，TypeScript）
- 文档站：https://deepseek-harness.github.io/deepseek-harness/
- 插件开发教程：https://github.com/deepseek-ai/deepseek-harness/tree/master/docs/user/develop/basic
- Cordis 入门：https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/cordis-primer.md
- MCP 桥接插件：https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/mcp/mcp-client
- DeepSeek API Tool Calls：https://api-docs.deepseek.com/guides/tool_calls
