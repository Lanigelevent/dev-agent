---
name: code-review
description: 一键对 Git 变更跑完整评审（预检→取数→评分→并行审查→核验→交付双闸），产出报告与行内评论。也用于口语说法：review 这次提交有什么问题
---

# code-review — 一键评审入口

本技能是 dev-agent 插件的总入口：调用编排器 runner.py 执行 AGENTS.md
主流程 0–10 步。十二个子技能（意图/取数/评分/并行审查/护栏/评测/自迭代/编排/
修复/审核/复盘/交付）与总监、资料员组成科层制组织（事实源
skills/director/org.json：总监为上级，五方汇报）。评审完成后如需自动修复，
走「审核人闸 1 → 修复出补丁 → 审核人闸 2 → 落盘（五道闸含行为回归）」
的链路；疑难杂症先查案例库（case-match），未命中由总监签发研究简报
（research-brief）走联网调研；每轮工作末尾由迭代官复盘入坑台账，
开局先读 next-round.md。

## 用法

runner.py 相对本技能基目录位于 `../../orchestrator/scripts/runner.py`。
在得到用户提供的仓库路径与变更范围后执行：

```bash
python ../../orchestrator/scripts/runner.py --repo <仓库路径> --range <A..B>
```

可选参数：`--request "<用户原话>"`（意图解析）、`--reviewer llm`（需
REVIEW_LLM_BASE_URL / REVIEW_LLM_API_KEY / REVIEW_LLM_MODEL 环境变量，默认
deterministic 零网络）、`--out <run 根目录>`（默认 runs）、`--resume <run 目录>`、
`--feedback <驳回清单 JSON>`。

## 结果判读

- 退出码 0：报告在 run 目录 report.md，行内评论在结果的 inline 字段
  （file/line/severity/message/suggestion），逐条转述给用户并附风险等级与合并建议。
- 退出码 1：NEED_HUMAN——把 gates 与原因转述给用户，按其建议
  （缩小范围/提高预算/人工确认）询问后再继续，不要静默重试。
- 退出码 2：参数或环境错误——检查仓库路径与 rev 是否存在。

## 硬约束

- 对被审仓库只读；diff 之外的代码一律 `git show <rev>:<路径>` 版本锚定。
- 产物只落 run 目录；报告/审计/材料中的凭据形态已自动脱敏为 `<redacted>`。
- 预算、轮数、动态增派由编排器强制；不要绕过编排器手拼单步脚本
  （单步脚本仅供排障）。
