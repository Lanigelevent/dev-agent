# 记忆（08）

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：迭代官
> **权威范围**：本类管「高频上下文与数值从哪取」——指针索引 + 取数命令速查（只给取法，不抄数值）
> **不是权威**：任何正文事实；各数值的权威源见取数命令所指
> **复核期限**：2026-12-06 ｜ **上次复核**：2026-11-06
> **主导模式**：参考

## 高频上下文

- 当前版本/轮次：取数命令见下表（不抄数值）。
- 活跃约束：硬约束 8 条 + 维护红线 8 条（读者视图 [docs/RULES.md](../RULES.md)）。
- 每轮开局：先读 [retro/next-round.md](../../retro/next-round.md) + `round-gate.py open`（五项全 PASS 才开工）。
- 每轮收官：bump-version → 文档回填 → close 闸 → 发布闸 → 复盘 → 双提交。

## 数值取数命令速查（数字现取，不抄数值）

| 量 | 取数命令 |
|---|---|
| 版本 | `.venv/Scripts/python.exe -c "import json;print(json.load(open('.zcode-plugin/plugin.json'))['version'])"` |
| 契约测试数 | `.venv/Scripts/python.exe -m unittest discover -s tests -v 2>&1 \| grep -aE "^Ran"` |
| 技能/脚本数 | `.venv/Scripts/python.exe -c "from pathlib import Path;print(len([d for d in Path('skills').iterdir() if d.is_dir()]), len(list(Path('skills').glob('*/scripts/*.py'))))"` |
| 台账计数 | `.venv/Scripts/python.exe -c "import json;d=json.load(open('retro/pitfalls.json',encoding='utf-8'));items=d['pitfalls'];from collections import Counter;print(Counter(i['status'] for i in items))"` |
| 覆盖率 | `coverage-gate.py check --root .`（live 实测或 --measured 复用） |
| 最近提交 | `git log --oneline -1` |

## 指针索引

| 指针 | 权威范围 |
|---|---|
| [<host-memory>/memory/MEMORY.md](../../<host-memory>/memory/MEMORY.md) | 项目长期记忆（本地资产不入库；按日追加） |
| [retro/pitfalls.json](../../retro/pitfalls.json) | 坑台账真值 |
| [docs/GLOSSARY.md](../GLOSSARY.md) | 术语表权威源 |
| [docs/INDEX.md](../INDEX.md) | 文档树内索引与取代关系 |
