# 运维（06）

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：开发者
> **权威范围**：本类管「环境怎么搭、命令怎么跑、风险在哪」——环境搭建/命令清单/风险标注/发布流程
> **不是权威**：设计理由（02/03）、进度（04）；环境/扩展/发布全文权威源 [docs/DEVELOPMENT.md](../DEVELOPMENT.md)
> **复核期限**：2026-12-06 ｜ **上次复核**：2026-11-06
> **主导模式**：操作指南

## 本类管什么

命令清单与风险标注（只读 / 有副作用 / 不可逆）；DEVELOPMENT.md 是环境/扩展/发布全文权威源，本类入口提供「任务 → 命令」速查与 README 收敛来的使用面。

## 类内文档清单

| 文档 | 权威范围 |
|---|---|
| [docs/DEVELOPMENT.md](../DEVELOPMENT.md) | 环境/架构/扩展指南/测试/发布全文（权威源） |
| [使用说明与配置.md](使用说明与配置.md) | 评审/修复/复盘/SWE-bench 使用命令 + LLM 配置 |
| [开源依赖与上游跟踪.md](开源依赖与上游跟踪.md) | 开源项目能力、仓库/发布页、版本核对与跟踪要点 |
| 本 README | 类入口 + 命令风险速查 |

## 命令风险速查

| 命令 | 风险档 |
|---|---|
| `runner.py --repo <仓库> --range A..B` | 只读评审 |
| `docker-mirror-probe.py --image <owner/repo>` | 只读探测（硬约束 8 前置） |
| `session-probe.py` / `doc-drift.py` / `doc-freshness.py` / `round-gate.py open` | 只读自检 |
| `release-gate.py` | 只读（不打 tag；`--out` 证据除外） |
| `round-gate.py close --round N` | 只读校验 |
| `bump-version.py --apply` | 有副作用（六处版本+计数落盘；失败零写入） |
| `retro-ledger.py`（无 --close/--archive） | 有副作用（台账追加） |
| `fix-apply.py --apply` | 不可逆级（受治理写仓库；任一闸失败自动回滚） |
| `fix-apply.py --undo` | 不可逆级（撤修复分支） |
| `pr-publish.py` | 有副作用（只创建 PR 不合并；token 只走环境变量） |
| `round-gate.py close --round N --round-type light` | 只读校验（轻量收官：零代码轮单跑 run1 全绿即可，r142） |
| `review-quality-gate.py check --findings <f.json>` | 只读校验（D-053 门禁：全 [] 批次须附 batch_note；evidence 覆盖 / unparsed 率，r138） |
| `mutation-sampler.py run --target <m.py> --tests <t.py> --max-mutants N` | 有副作用（临时翻转 target 后 finally 恢复；聚焦 pytest 逐变异运行，r144） |
| `swrenbench-import.py review --batch-note <text>` | 有副作用（写 findings.json；全 [] 批次无 batch_note 时 judge rc=1 拦截，r138） |
| `pip-audit -l`（.venv 内） | 只读探测（OSV CVE 扫描；nightly 已固化，r148） |

## 故障入口

排障与常见问题 → [05 排障](../05-troubleshooting/README.md)；台账真值 → [retro/pitfalls.json](../../retro/pitfalls.json)。

## 事件账本哈希链（round-153 起）

轮收官后向 `runs/rounds-ledger/ledger.jsonl` 追加一条轮摘要（append-only +
sha256 哈希链，任一篡改 verify 即断）：

```bash
python skills/production-guardrails/scripts/event-ledger.py record \
  --dir runs/rounds-ledger --actor iterator --action round-summary \
  --kind note --replay opaque \
  --argv-json '["round-<N>"]' \
  --observation-json '{"round": <N>, "version": "X.Y.Z", "outcome": "closed"}'
python skills/production-guardrails/scripts/event-ledger.py verify \
  --ledger runs/rounds-ledger/ledger.jsonl
```

风险档：有副作用（append-only 追加；不重写不改历史行）。
