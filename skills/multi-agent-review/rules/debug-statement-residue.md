# 规则：调试语句不应留在生产代码中

**适用**：JavaScript/TypeScript 中的 `console.log()` 和 Python 中的 `print()`
（`*.js`、`*.jsx`、`*.ts`、`*.tsx`、`*.py` 命中本规则）。

**判据**：`console.log` 和 `print` 是开发期调试工具，生产代码中残留的调试
输出会：①暴露内部数据结构（日志中打印用户凭据、内部 ID、配置密钥的案例
频发）；②污染标准输出/日志通道，干扰结构化日志采集；③在热路径上产生
不必要的 I/O 开销。改动新增了 `console.log` 或 `print` 时，必须确认是
有意的日志输出（经过日志框架）还是遗留调试语句。

**反例形态**：`console.log("user token:", token)` 在生产环境将用户认证
令牌打印到浏览器控制台——前端日志被浏览器扩展或 CSP 报告采集后泄露。
`print(f"query: {sql}, params: {params}")` 在生产环境将含用户数据的 SQL
参数输出到 stdout——被容器日志采集后进入日志聚合系统。

**评审动作**：对含 `console.log` / `print` 新增的 diff，问一句"这是调试
残留还是有意的输出？输出的内容有没有敏感信息？有没有用项目的日志框架
替代？"——答不清就要求删除或改用日志框架。

出处：ast-grep 引擎规则 no-console-log / print-debug（engines/astgrep_adapter.py
BUILTIN_RULES，round-39 引擎落地 + round-40 规则集 v2 扩展；no-console-log
模式 `console.log($$$)` 可自动删除，print-debug 模式 `print($$$)` 标注
不自动删除——Python print 可能是有意日志，需人工判断）。
