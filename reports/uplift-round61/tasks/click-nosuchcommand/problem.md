Group 解析遇到未知子命令时直接 ctx.fail 退出。请改为抛出新的 NoSuchCommand 异常（UsageError 子类，`from click import NoSuchCommand` 可用），默认消息 `No such command 'x'.`；当存在相近命令时追加建议：单个 `Did you mean 'push'?`，多个 `(Did you mean one of: 'declare', 'refine'?)`（用 difflib.get_close_matches 取相近项）。同时 NoSuchOption 的默认消息改为 `No such option '--foo'.`，建议格式与上一致（不再用 `(Possible options: ...)`）。

测试已就绪且当前失败：tests/test_commands.py::test_suggest_possible_commands、tests/test_options.py::test_unknown_options、tests/test_options.py::test_suggest_possible_options。
