# 当前状态与进度索引

> **创建日期**：2026-10-28 ｜ **当前状态**：维护中 ｜ **所有者**：迭代官
> **权威范围**：当前版本、契约数、台账、最近验证与交付状态的**当前快照**
> **不是权威**：历史沿革（BASELINE-HISTORY / ROADMAP-HISTORY）、待办（retro/next-round.md）、决策理由（DECISIONS）
> **复核期限**：2026-12-31（每轮收官替换本快照）｜ **上次复核**：2026-11-25
> **主导模式**：记录

本文件只保留**当前值**；历史轮次不再在本文累抄，避免与两份 HISTORY 和轮报形成多源。

## 当前快照（round-221 收官）

| 项 | 当前值 | 真值来源 |
|---|---|---|
| 版本 | 2.99.0 | `.zcode-plugin/plugin.json` |
| 契约测试 | 848 项（845 passed + 3 conditional skip） | `unittest discover -s tests` |
| 最近全量 | 550.02 秒，低于 600 秒硬护栏 | `logs/suite-r221-run1.log` |
| 治理壳 | 13 个技能 × 90 个脚本 | `skills/` |
| MCP | 16 个工具 | `mcp/review_mcp.py` |
| 坑台账 | 266 条（open 0 / closed 242 / archived 24） | `retro/pitfalls.json` |
| 评测口径 | agent 侧 20/20；对外硬规则臂 0.42%；部分口径与 blocked 单列 | `reports/swebench/`、`docs/BASELINE-HISTORY.md` |
| SRE 预算 | 全项 PASS；无数据项如实 N/A | `org-scorecard.py` |
| 覆盖率 | 以 `coverage-gate.py check` 当场结果为准，不在文档手抄 | `coverage-baseline.json` |
| 最近提交 | 以 `git log -1` 为准（r219–r221 已推送功能分支） | git |
| 探针 / 死代码 | 全绿 / 0 | `session-probe.py`、`dead-code-scan.py` |

## 当前交付状态

- 代码与文档验证已通过；功能分支 `task/round-219-maintenance` 已推送，尚未合并到 `main`。
- 发布闸版本、文档、秘密、许可证、双跑五项通过；`git_state` 需在提交后的干净树执行。
- tag 与合并由人工决定，不由脚本自动执行。

## 当前待办与观察

唯一待办清单是 [retro/next-round.md](../retro/next-round.md)。当前观察项：

- CI nightly mcp-scan 首次实跑复核（操作员）。
- CII 注册与 Gitea runner 接入（操作员）。
- key 轮换检查（操作员）。
- MCP async `test_purge_guards` 偶发，已隔离复跑通过，继续留观但不阻塞。
- 下一依赖刷新锚点约 r230。

## 历史与证据去哪读

| 内容 | 唯一来源 |
|---|---|
| 版本发布沿革 | [BASELINE-HISTORY.md](BASELINE-HISTORY.md) |
| 路线阶段与逐轮方向回填 | [ROADMAP.md](ROADMAP.md)、[ROADMAP-HISTORY.md](ROADMAP-HISTORY.md) |
| 每轮完成、证据与候选 | `retro/round-N-report.md`、`retro/round-N-candidates.md` |
| 发布签核证据 | `reports/release-gate/<version>/` |
| 全量运行日志 | `logs/suite-rNN-runK.log` |
| 当前待办 | [retro/next-round.md](../retro/next-round.md) |