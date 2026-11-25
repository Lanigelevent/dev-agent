# 规则：var 声明的作用域陷阱

**适用**：JavaScript/TypeScript 中使用 `var` 声明变量的代码（`*.js`、`*.jsx`、
`*.ts`、`*.tsx` 命中本规则）。

**判据**：`var` 声明的变量有**函数作用域**（而非块作用域）且会被**提升**
（hoisting）到函数顶部。这意味着 `var` 变量在声明语句之前即可访问（值为
`undefined`），且在块级结构（`if`/`for`/`while`）内部声明的 `var` 会泄漏到
外部。改动涉及 `var` 声明时，必须确认作用域边界是否与预期一致。

**反例形态**：`for (var i = 0; i < arr.length; i++) { ... }` 循环结束后
`i` 仍然可访问且值为 `arr.length`——如果后续代码依赖 `i` 不存在（如严格
模式检查或闭包捕获），会产生非预期行为。`var x = 1; if (cond) { var x = 2; }`
中 `if` 块内的 `var x` 不是新声明而是**重新赋值**，即使 `cond` 为 `false`。

**评审动作**：对含 `var` 声明的 diff，问一句"这个变量的作用域是函数级还是
块级？有没有被闭包捕获？提升后声明前访问会拿到什么？"——答不出就要求改用
`let`/`const`。

出处：ast-grep 引擎规则 no-var（engines/astgrep_adapter.py BUILTIN_RULES，
round-40 规则集 v2 扩展；ast-grep MIT，模式 `var $NAME = $$$`）。
