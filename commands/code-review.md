---
description: 对指定 Git 仓库与变更范围执行完整代码评审（预检→取数→评分→并行审查→核验→双闸交付）
---

# /code-review

参数格式：`$ARGUMENTS` = `<仓库路径> <A..B 范围> [用户原话]`（空格分隔）。

执行步骤：

1. 解析 `$ARGUMENTS`：第一个参数为仓库路径，第二个为变更范围（如 `HEAD~1..HEAD`、
   `main..feature`），其余拼接为用户原话（可空）。
2. 读取本插件的 `code-review` 技能（skills/code-review/SKILL.md），按其指引调用
   同插件 `skills/orchestrator/scripts/runner.py`：

   ```bash
   python skills/orchestrator/scripts/runner.py --repo <仓库路径> --range <A..B> --request "<用户原话>"
   ```

3. 退出码 0：向用户转述报告要点（风险等级、合并建议、行内评论逐条、报告文件路径）。
4. 退出码 1（NEED_HUMAN）：把 gates 与建议原文转述给用户，等待其选择后再继续。
5. 退出码 2：说明参数/环境问题并给出修正建议。

约束：对被审仓库只读；不绕过编排器手拼单步脚本；结论带证据与来源性质。
