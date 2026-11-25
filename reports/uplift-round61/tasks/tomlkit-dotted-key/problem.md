`doc.add(tomlkit.key(['foo', 'bar']), 1)` 应让文档渲染为 `foo.bar = 1\n`；`table.add(tomlkit.key(['foo', 'bar']), 1)` 同理。当前 add 路径未展开 dotted key（解析器侧有类似逻辑），请实现支持。

测试已就绪且当前失败：tests/test_api.py::test_add_dotted_key。
