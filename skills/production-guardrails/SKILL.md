---
name: production-guardrails
description: 审计日志、断点、人工门、报告与产物双闸、误报模式库与反馈闭环
---

# production-guardrails — 生产护栏

## 目的与边界

本 skill 承载评审全程的护栏：审计、断点、人工门、报告与产物校验、参数读取、误报模式库。
护栏的原则是「不过不交付」：审计缺条目、断点产物缺失、报告缺段、产物未脱敏，
都在交付前拦下，而不是事后补救。

边界约定：

- 护栏脚本只落自己 `--dir` 指定的目录，绝不写被审仓库。
- 所有文本字段入库前过脱敏函数，凭据形态统一 `<redacted>`。
- 全部脚本只用标准库；stdout 只有一个 JSON 文档。

## 脚本清单与用法

### audit-log.py（审计日志）

```bash
python skills/production-guardrails/scripts/audit-log.py --log --step step4 --actor dispatcher \
  --input-ref diff.patch --finding-id cred-1 \
  --output-summary "启用 5 路" --basis "dispatch-plan 输出" --disposition 采纳 \
  --dir runs/run-20261024
```

- `--log` 为动作开关；`--step`、`--actor` 必填。
- `--disposition` 枚举固定 {采纳, 驳回, 降级, 重试, 熔断, None}，越界退出 2。
- 文本字段（input_ref/finding_id/output_summary/basis）入库前统一脱敏。
- 追加写 `<dir>/audit.jsonl`，每行一个 JSON 对象。

### checkpoint.py（断点）

```bash
python skills/production-guardrails/scripts/checkpoint.py write --dir runs/run-1 --step step4 --rounds 2 --artifacts a.json,b.json
python skills/production-guardrails/scripts/checkpoint.py read --dir runs/run-1
python skills/production-guardrails/scripts/checkpoint.py verify --dir runs/run-1
```

- write 记 `last_complete_step` / `rounds_used` / artifacts 清单。
- read 给续跑位置（无断点时返回 resume_from=step0，退出码 0）。
- verify 校验产物齐全，缺则退出 1——产物缺失的状态不能沿用，必须重跑。
- 步骤编号固定 step0..step10，与 AGENTS.md 主流程一致。

### human-gate.py（人工门）

```bash
python skills/production-guardrails/scripts/human-gate.py --situation preflight_rejected
python skills/production-guardrails/scripts/human-gate.py --situation style_suggestion
```

五类触发（退出码 1）：

| situation | 含义 |
| --- | --- |
| preflight_rejected | 预检拒绝（对象不可解析或预算两档都超） |
| budget_both_exceeded | 预算两档都超 |
| conclusions_unconverged | 结论未收敛 |
| verification_incomplete | 查证未完成 |
| downgrade_two_levels | 降级跨两级以上 |

四类不算门（退出码 0）：

| situation | 含义 |
| --- | --- |
| single_low_confidence_finding | 单个低置信度发现 |
| material_insufficient | 材料不足 |
| style_suggestion | 风格建议 |
| test_suggestion | 测试建议 |

未知 situation 退出 2。

### report-check.py（报告模板校验）

```bash
python skills/production-guardrails/scripts/report-check.py report.md
cat report.md | python skills/production-guardrails/scripts/report-check.py -
```

- 校验七段：运行信息、变更摘要、风险评分、测试建议、优化步骤手册、行内评论、修复补丁建议。
- 另校验标题 `# 代码评审报告`、口径行 `【评审口径】`、阅读顺序说明（建议阅读顺序）。
- 补丁段规则：要么含「未生成补丁」说明，要么含 unified diff 内容（```diff / diff --git / --- a/）。
- 缺段/格式不符退出 1。

### schema-check.py（产物校验）

```bash
python skills/production-guardrails/scripts/schema-check.py --dir runs/run-20261024
```

- 按 `references/schemas.md` 校验 8 个产物：step2~step8 的 7 个产物 + checkpoint.json。
- 三类失败：产物缺失、缺必填字段、枚举越界。
- 脱敏兜底：任一字符串值命中密钥形态且未脱敏为 `<redacted>` 即判失败。
- schemas.md 是唯一 schema 来源；schema-check.py 不内嵌副本。

### manifest_args.py（参数读取）

```bash
python skills/production-guardrails/scripts/manifest_args.py
python skills/production-guardrails/scripts/manifest_args.py --agent-json /path/agent.json --key max_review_minutes
```

- 定位顺序：显式 `--agent-json` > CWD > 项目根（脚本位置上溯）。
- 其他脚本需要 args 时按同一顺序自行定位；本脚本是参考实现与校验入口。
- 定位不到 / JSON 非法 / 键不存在均退出 2。

### experience.py（误报模式库）

```bash
python skills/production-guardrails/scripts/experience.py record --dir runs --pattern "npe-optional" --dimension "边界与空值"
python skills/production-guardrails/scripts/experience.py read --dir runs --dimension "边界与空值"
```

- 条目上限 50，按 last_hit 淘汰最旧；单条 rejected_count 上限 50。
- 三档举证：>=5 严格、>=2 加强、=1 常规；read 输出附 evidence_level。
- pattern 入库前脱敏。

### feedback-close.py（反馈闭环入口）

```bash
python skills/production-guardrails/scripts/feedback-close.py --findings rejects.json --experience runs
```

- 读驳回清单（数组或含 items 键；pattern 或 rule_id + dimension + count）。
- 逐项走 experience.record：同维度同 pattern 累计 rejected_count，不新增条目。
- 输出 recorded/skipped 与按 pattern 聚合后的条目（含最新举证等级）。

## 与主流程的接入点

| 主流程 | 脚本 | 动作 |
| --- | --- | --- |
| 步骤 0 | session-probe.py / audit-log.py | 开局探针 + 开始审计 |
| 全程 | checkpoint.py | 每步完成即 write |
| 步骤 2/6 | human-gate.py | 五类触发暂停 |
| 步骤 4 | experience.py | 下发已知误报模式 |
| 步骤 10 | report-check.py / schema-check.py | 交付双闸 |
| 步骤 10 | experience.py record | 用户驳回项入库 |

## 退出码汇总

| 脚本 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| audit-log.py | 写入成功 | - | 参数错误/枚举越界 |
| checkpoint.py | 正常 | verify 失败 | 参数错误 |
| human-gate.py | 不触发 | 触发 | 未知 situation |
| report-check.py | 通过 | 校验失败 | 参数错误 |
| schema-check.py | 通过 | 有产物不合格 | 参数错误 |
| manifest_args.py | 正常 | - | 定位不到/键不存在 |
| experience.py | 正常 | - | 参数错误 |

## 检查清单

1. audit.jsonl 每行一个 JSON，文本字段已脱敏。
2. disposition 枚举越界被拒。
3. checkpoint verify 产物缺失退出 1。
4. 无断点时 read 返回 step0 而不是报错。
5. human-gate 五类触发、四类不算门，未知 situation 退出 2。
6. report-check 七段清单与 AGENTS.md 报告模板一致。
7. schema-check 只认 schemas.md，不内嵌第二份 schema。
8. schema-check 脱敏兜底覆盖嵌套结构。
9. manifest_args 定位顺序固定且可被显式参数覆盖。
10. experience 三档举证与 BASELINE.md 一致。
11. 条目上限 50 按 last_hit 淘汰。
12. 所有护栏脚本不写被审仓库。

## runs 目录布局

```text
runs/
├── <run_id>/
│   ├── checkpoint.json
│   ├── audit.jsonl
│   ├── step2_collect.json
│   ├── step3_risk.json
│   ├── step4_dispatch.json
│   ├── step5_findings.json
│   ├── step6_verification.json
│   ├── step7_summary.json
│   ├── step8_backverify.json
│   └── report.md
└── experience.json
```

## 产物生成责任表

| 产物 | 生成步骤 | 内容 |
| --- | --- | --- |
| step2_collect.json | 步骤 2 | repo/range/files/source_lines/commits |
| step3_risk.json | 步骤 3 | regions/overall（score.py 输出） |
| step4_dispatch.json | 步骤 4 | dimensions_enabled/skipped |
| step5_findings.json | 步骤 4 | findings（过 findings-check） |
| step6_verification.json | 步骤 5/6 | adopt/reject |
| step7_summary.json | 步骤 7 | change_summary/test_suggestions/risk |
| step8_backverify.json | 步骤 8 | uncovered/crosschecked |
| checkpoint.json | 每步 | last_complete_step/rounds_used/artifacts |

## 审计字段说明

| 字段 | 说明 |
| --- | --- |
| ts | 本地时区 ISO 时间戳 |
| step | 主流程步骤标识 |
| actor | 执行者（dispatcher/verifier/gate 等） |
| input_ref | 输入产物引用 |
| finding_id | 关联发现标识 |
| output_summary | 输出摘要（脱敏后） |
| basis | 判定依据（脱敏后） |
| disposition | 采纳/驳回/降级/重试/熔断/None |

## 断点续跑流程

1. 每步完成立即 checkpoint write（step + rounds + artifacts）。
2. 中断后 checkpoint read 取 resume_from。
3. 恢复前 checkpoint verify；产物缺失必须重跑，不得沿用。
4. 重跑的步骤重新 write，覆盖 last_complete_step。

## 人工门处置表

| 触发 | 建议处置 |
| --- | --- |
| preflight_rejected | 补材料或缩小范围后重跑 |
| budget_both_exceeded | 提高预算或降档，需人工确认 |
| conclusions_unconverged | 增加查证轮数或交人判断 |
| verification_incomplete | 补齐核验/反向验证缺口 |
| downgrade_two_levels | 确认是否接受降档 |

四类不算门的情形：记录并继续，写入审计（disposition=None）。

## 报告模板（report-check 校验目标）

```markdown
# 代码评审报告

【评审口径】对象：<range>｜范围：<scope>｜深度档：<depth>

## 运行信息
执行方式｜启用维度｜资源用量｜档位｜降级记录｜审计条数

## 一、变更摘要
（文件表）

## 二、风险评分
（区域表 + 整次综合）

## 三、测试建议
（按 文件::函数 分组）

## 四、优化步骤手册
建议阅读顺序：先高严重度已证事实 → 需人工复核 → 中低
（每项：定位/证据/原因/修复步骤/证据等级）

## 五、行内评论
loc | severity | 一句话结论

## 六、修复补丁建议
（unified diff 或「未生成补丁」说明）
```

## 脱敏规范

- 六类形态：password/api_key/secret/token 赋值、AKIA、Bearer、mysql 连接串、JWT、私钥块。
- 脱敏为 `<redacted>`，不保留长度、前缀等可推断信息。
- 覆盖范围：审计日志、产物 JSON、报告、材料快照。
- schema-check 兜底：产物中出现未脱敏形态直接判失败。

## 交付双闸

1. report-check：模板完整性（七段 + 口径 + 阅读顺序 + 补丁格式）。
2. schema-check：8 个产物字段与脱敏兜底。
两闸全过才允许交付；任一失败走 human-gate 或修复后重跑。

## 反向验证要求

1. audit-log：disposition 越界必须退出 2；文本含密钥必须已脱敏。
2. checkpoint：删除产物文件后 verify 必须退出 1。
3. human-gate：五类触发/四类不算门逐一钉死；未知情形退出 2。
4. report-check：删任一段落必须退出 1；补丁段无内容必须报问题。
5. schema-check：枚举越界/缺字段/未脱敏三类都要有违规样例。

## 维护注意

- 改报告模板必须同步 report-check 与本文件模板段。
- 改产物 schema 必须同步 references/schemas.md。
- experience 三档阈值改动必须同步 BASELINE.md。
- audit.jsonl 只追加不修改；清理策略由使用方决定。
- 护栏脚本禁止引入第三方依赖。
