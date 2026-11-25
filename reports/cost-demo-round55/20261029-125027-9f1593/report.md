# 代码评审报告

【评审口径】对象：5b6adf0^..5b6adf0｜深度档：standard｜评审器：deterministic

## 运行信息
轮数 9/32｜动态增派 1/2｜tokens 0｜预算剩 119.7 分钟｜材料校验 通过｜门 无

## 一、变更摘要
文件 36｜增删 +6657/-47｜边界信号 无

## 二、风险评分
整次综合 4.2（高）｜高风险区域 无

## 三、测试建议
- 为 .zcode-plugin/plugin.json 补充边界用例：覆盖新增分支与错误处理
- 为 AGENTS.md 补充边界用例：覆盖新增分支与错误处理
- 为 BASELINE.md 补充边界用例：覆盖新增分支与错误处理
- 为 README.md 补充边界用例：覆盖新增分支与错误处理
- 为 docs/DECISIONS.md 补充边界用例：覆盖新增分支与错误处理
- 为 docs/DEVELOPMENT.md 补充边界用例：覆盖新增分支与错误处理
- 为 docs/PROGRESS.md 补充边界用例：覆盖新增分支与错误处理
- 为 docs/ROADMAP.md 补充边界用例：覆盖新增分支与错误处理
- 为 mcp/review_mcp.py 补充边界用例：覆盖新增分支与错误处理
- 为 pyproject.toml 补充边界用例：覆盖新增分支与错误处理

## 四、优化步骤手册
建议阅读顺序：先高严重度已证事实 → 需人工复核 → 中低
| 编号 | 严重度 | 置信度 | 来源 | 维度 | 定位 | 证据 | 原因 | 修复步骤 | 证据等级 | 复核 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 高 | 高 | 多轮共识 | 安全与敏感信息 | tests/test_scripts.py:756 | self._record("script.echo", {"exit": 0, "json": {"api_key": <redacted>, | deterministic-rules cred-api-key 命中（已证事实） | 按 cred-api-key 规则的标准处置修复，上下文需人工确认 | 观测 | - |

## 五、行内评论
tests/test_scripts.py:756 | 高 | 源码出现 api_key 赋值形态

## 六、修复补丁建议
未生成补丁：上下文逐字核对未通过前不放 diff，只给文字修复步骤。

---
每项结论标注证据等级：观测 ≠ 因果；单变量实验 ≠ 独立复现。