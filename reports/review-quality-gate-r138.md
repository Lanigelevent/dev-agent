# round-138：评审质量门禁落地（D-053 对策，2026-11-12）

## 结论先行

- **review-quality-gate.py 落地**（第 84 个脚本）：run/check 双动词四项检查——
  empty_batch_note（全 [] 批次必附依据）/ evidence_coverage（≥0.8）/
  unparsed_rate（≤0.1）/ batch_shape；退出码 0=PASS / 1=护栏失败 /
  2=输入错误（仿 precision-gate.py 口径）。
- **judge 前置硬校验**：swrenbench-import.py 的 cmd_judge 与
  cmd_judge_semantic 输入校验段末各插「全 [] 批次且无 batch_note → rc=1
  empty_batch_no_evidence」（judge 新增退出码 1 语义，docstring 已同步）；
  review 子命令增 --batch-note（两处写盘点落 findings.json 顶层）。
- **反向验证（红线 6）**：契约 10 条（test_scripts_review_quality_gate.py）
  含 test_empty_batch_without_note_fails / test_judge_empty_no_note_rc1
  两条抓得住样例；10/10 全绿。
- **真数据回归**：judge 对 r114 findings.json 复跑，F1 0.5789 / 0.3656 与
  r114 报告逐位一致（门禁插入不改变判定口径）；r114 真批过门禁
  （evidence 覆盖 1.0 / unparsed 1%）；原 97③ 实弹冒烟即此双验。

## 轮内实踩（如实）

- **判卷范围险些误扩**：semantic 前置校验首次插入时把零 findings 的 change
  PR 也卷进了判卷集——当即纠正为「前置校验扫全量 change 集（判空），判卷
  order 仍按原过滤（有 findings 才进）」，范围零变化。
- **doc-drift 问 10 实抓**：门禁 docstring 的用法示例行引用了
  `swrenbench-import.py judge --corpus`，被参数漂移检查判「未定义」——
  删除该行后全绿。检查器抓自己的检查器，红线 6 的活证据。
- **覆盖率测量两连败**：①全量 measure 因脏树计数漂移（83→84 未同步）
  作废——先 bump --sync-counts 再测；②focused measure rc=5（no-data），
  该用法不在 gate 支持面内，全量 measure 才是正路。

## 验收对照（第 99 条 DoD）

| DoD | 结果 |
|---|---|
| 造全 [] 无依据样例确认抓住 | ✅ 两条反向验证契约 |
| 713→721+ 双跑全绿 | 待双跑（本轮 +10 契约） |
| 脚本 84 六处真值同步 | ✅ bump --sync-counts；AGENTS 表已加行 |
| coverage-baseline 登记 | ✅ 重测基线（含新模块） |

**证据**：skills/eval-harness/scripts/review-quality-gate.py；
tests/test_scripts_review_quality_gate.py（10 条）；reports/_work/rqg 报告；
r114/r132 批次产物复跑记录。
