# round-84 gate-corpus-build.py 端到端演练：产品链 9/9 精确复现手工终版

## 结论先行

- **F2P 等价性 9/9 MATCH**：产品链（derive → refine(r81 台账) →
  refine(r82 台账)）在 gate-r80 全量 9 实例上**零失配**复现 r81/r82
  手工终版 fail_to_pass（含 briefcase 13 个参数化节点经台账 refine
  精确重建）。
- **产品静态推导反超手工版 2 例**：cfn-lint（2 节点）与 conan（1 节点）
  手工版当初推不出（r81 正则只认 tests/ 前缀），产品因「类上下文
  顶格 def 重置」修复 + `/test_` 路径容忍**直接静态命中**——产品化
  修复的增益定量可见。
- **notes 8/9 语义等价**：1 例预期差异（checkov 数据驱动形态——手工
  版带人工增强解释文字，产品指针列出 test_patch 中的具体数据文件
  路径，信息更精确但不复刻解释性文字）。
- 对账脚本自身两轮修正（行尾冒号丢失 / 括号剥除留双空格致伪失配）
  ——对账工具也按「反例钉住」纪律走查。

## 演练口径

- 输入：当前 gate-r80-batch.jsonl 剥离手工成果（fail_to_pass 清空、
  test_cmds 复原、setup_cmds/adaptation_note 移除）的近似 pristine
  版（test_patch 等上游字段未动，sha 与冻结一致）。
- 产品链：`derive` → `refine`（r81 基线台账）→ `refine`（r82 基线
  台账）→ `notes`（example 模板，rounds 24）。
- 对账基准：r81/r82 手工终版（含基线实测回填的 briefcase 13 节点、
  cfn-lint 2 节点、conan 1 节点）。
- blocked 识别：beets 被产品 refine 正确标记 blocked_data（rc=1 如实
  返回「有无可处理问题」）；beancount/checkov 行无 test_log、refine
  按设计跳过（手工版的人工 blocked 结论在其 adaptation_note，产品
  不伪造）。

## 逐实例结果

| 实例 | F2P（exp=got） | 来源链 |
|---|---|---|
| aiogram-1594 | 1=1 | 静态 |
| sh-744 | 1=1 | 静态 |
| arviz-2413 | 1=1 | 静态 |
| cfn-lint-3764 | 2=2 | **静态（反超手工）** |
| beancount-931 | 0=0 | 无信号（env_blocked 手工） |
| beets-5457 | 0=0 | refine 标记 blocked_data |
| briefcase-2075 | 13=13 | refine（r81 台账） |
| checkov-6893 | 0=0 | 无信号（blocked_source 手工） |
| conan-17102 | 1=1 | **静态（反超手工）** |

## 意义与限制

- gate 语料构建从「手工 + 一次性脚本」升级为「产品 + 契约 + 可重放」
  ——换批次扩样（round-85+）的成本从每实例人工适配降为
  derive→refine 两命令。
- 静态推导的边界如实：parametrize 型新增（briefcase）与数据驱动型
  （checkov）仍需基线实测/人工指针，产品 refine/notes 各自兜底。
- n=1 语料批次的等价性验证；换批次重放是下一步自然验证面。

## 证据

- 重放产物与对账明细：`reports/_work/live-r84/`（input-pristine /
  derived / refined-r81 / refined-r82 / replay-f2p.json /
  replay-notes.json / notes-product/——gitignored 工作区）
- 演练脚本：replay.py、notes-diff.py（同目录，含两轮自修正记录）
