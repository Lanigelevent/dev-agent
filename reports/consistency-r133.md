# round-133：全局口径一致性收尾（v2.35.0）——核验清单与勘误

## 结论先行

- **范围**：tracked 文档全面扫描（README / AGENTS.md / BASELINE.md / docs/\*.md（30+ 页）/ retro/\*.md / reports/\*.md），
  针对 round-124..132 期间播撒的 SWRBench host arm 叙事、TIMES 占位、陈旧版本号与陈旧台账口径做闭环收束。
- **已修 13 处**：前向口径 6 + 占位填充 5 + 勘误修正 4（见下表 A/B/C 节）。
- **历史不改**：round ≤132 已冻结口径（retro round-\*-report、PROGRESS §3/§4、BASELINE-HISTORY/ROADMAP-HISTORY 早期条目、next-round.md 77–90 历史决策项、.zcode 外部笔记）原文保留。
- **基准锚**：README 评测能力表为唯一对外口径——38 条硬规则臂 point_recall ≈ 0.42%（v2.34.0，tests-tracked）；宿主评审臂 host-file-protocol n=1000 结果 recall=0.0（PR fn=500 / point fn=713 / F1=null / clean 500-500 零误报），标 **unavailable**，不作能力宣称。
- **不做**：不动代码、不改口径系数（713 / 83 / 38 / 0.42%）、不回改已 tag release 的 evidence、不动历史账本行。
- **双跑全绿 426.089 / 409.668 秒**（`logs/suite-r133-run1/2.log`，各 1 skip），两跑均 < 450s（本轮同时打破 D-041 升级触发判断窗口：r128–r131 五连 >450s 至此终结——
  但结论不出：观测口径保持 D-041 既有执行方式，见 §F）。

## A. 前向口径修正

| # | 位置 | 旧 | 新 |
|---|---|---|---|
| 1 | README.md:115 | 硬规则臂 point_recall ≈ 0.42%（v2.33.0） | v2.34.0（tests-tracked 实证版本统一） |
| 2 | README.md:366（已知限制第 4 行） | 同上 v2.33.0 | v2.34.0 |
| 3 | docs/PROGRESS.md §1 头 | 截至 2026-11-09 | 2026-11-10 |
| 4 | docs/PROGRESS.md §1 契约测试 cell | 仅到 round-128 双跑 | 前置 round-129..132 双跑真值（474.846/475.514、519.747/471.923、510.521/460.856、416.966/394.449） |
| 5 | docs/PROGRESS.md §1 坑台账 / SRE 预算 | closed 209 / open 8 / 未结坑 3/8 | closed 217 / archived 24 / open 0 / 未结坑 0/8 |
| 6 | retro/next-round.md 第 20 行（r129 topline） | 「全量 n=1000 续跑按 stride 分批确认（预算已批）」 | 「全量 n=1000 已于 round-132 跑毕（host-unavailable）；对外唯一口径见 README」 |

附：retro/next-round.md 第 6 行（r132 topline）「双跑 双跑全绿」文字重叠去重。

## B. 占位符填充（TIMES 类，不可静默通过）

| 位置 | 值 |
|---|---|
| docs/BASELINE-HISTORY.md r132 收尾条目 | 416.966 / 394.449 秒（`logs/suite-r132-run1/2.log`） |
| docs/ROADMAP-HISTORY.md §5.90（r131 条目） | 510.521 / 460.856 秒 |
| reports/swr-r131-batch1.md | 510.521 / 460.856 秒 + 勘误说明块 |
| reports/dep-refresh-r128.md | 450.510 / 455.260 秒 |
| retro/events-round-128.json | title「双跑全绿（TIMES）」→「双跑全绿（450.510 / 455.260 秒）」 |

## C. 事实勘误（带标记，不静默改写）

| 位置 | 旧 | 新 | 方式 |
|---|---|---|---|
| ROADMAP-HISTORY §5.90 标题 | n=100/1000 cumulative | n=80/1000 cumulative | 直接修 +「勘误（round-133）」bullet |
| ROADMAP-HISTORY §5.90 scope 行 | n=100 仅为预算消耗 50/1000 | n=80 仅为贯通验证（本批 +50） | 同前 |
| ROADMAP-HISTORY §5.92 | 「ADR/known-limitations 表格刷新；.」+ 制表符「不\tbottom-up」 | 「README 评测能力表/已知限制表格刷新（v2.34.0）」「不 bottom-up」 | 直接修用词 |
| reports/swr-r131-batch1.md | n=100 / TIMES / 「下一轮可继任」 | n=80（60 unique）/ 实跑时间 / 终局更新（round-132 host-unavailable） | 追加「勘误（round-133）」块 |
| docs/PROGRESS.md r129 bullet | 词语重复「SWRBench review arm smoke v2.31.0」×2 +「按 stride 分批续跑（预算已批）」 | 去重；改「已于 round-132 完成（recall=0.0 → host-unavailable）」 | 直接修 |

## D. 未动（有意保留）

- **retro/round-\*-report.md（round ≤132）**：closed 209 / open N 数字为其时真值，冻结。
- **docs/ROADMAP-HISTORY.md ≤ §5.88、docs/BASELINE-HISTORY.md ≤ 1930、PROGRESS.md §3/§4**：历史 along the same rules。
- **next-round.md 77–90 条历史决策项**里的「①全量 n=1000 续跑」：历史当时候选，不重写。
- **.zcode/batch-plan-executor-lessons.md**：仓外脑笔记，记载 round-127 当时 PROGRESS.md:22「未结坑 3/8」——彼时事实，不回改。
- **events-round-128.json description 里的「我 log-byte 事故」类措辞**：如实记录，保留。

## E. 一致性锚（对外唯一口径）

- `.zcode-plugin/plugin.json` version = 2.34.0（本轮 bump 后见 2.35.0）
- README「未验证/未验收/未结清」表第 4 行：**0.42%（v2.34.0）+ 宿主臂 unavailable**
- 全仓 grep 无残留「double run TIMES」「version 引用 v2.33.0 作为当前值」「n=100/1000」「problems closed 209（当前语境）」类前向不一致
- `doc-freshness.py`：漂移 0；713 tests / 83 scripts / 12 MCP tools / 113 deepswe ✓

## F. D-041 备注（只记录，不处置）

round-128..131（450.510/455.260、474.846/475.514、519.747/471.923、510.521/460.856 连续 ≥450s）按 D-041 执行口径应在第 3 个超线轮触发「连续 3 轮 >450s」升级处置；本轮没有新增处置出口，r132/r133 双跑（416.966/394.449、426.089/409.668）均回落 450s 以下。
本报告仅登记该窗口事实；是否升级为 D-049 改升级阈值（如 450s → 550s）等决策属于总监裁量，不在本轮范围。

## 证据

- `git diff`（本轮提交；触：README / PROGRESS / DEVELOPMENT / BASELINE-HISTORY / ROADMAP-HISTORY / next-round / swr-r131-batch1.md / dep-refresh-r128.md / events-round-128.json）
- `logs/suite-r133-run1/2.log`（713 项全绿，426.089 / 409.668 秒，各 1 skip）
- `reports/consistency-r133.md`（本文件）
