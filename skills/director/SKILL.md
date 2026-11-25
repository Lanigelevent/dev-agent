---
name: director
description: 总监（第五角色，上级）：三层科层调度与 RACI 签字权、错误预算结算、疑难杂症升级链、链接型案例库与研究简报。也用于口语说法：查一下有没有类似案例
---

# director — 总监（统辖四团队与资料员的上级）

组织事实源是本目录 org.json（v2 科层制，对标大公司实践）：三层管理——
总监（上级，只分派与验收）→ 各团队首席 lead（runner.py / fix-apply.py /
approve-patch.py / retro-report.py / research-brief.py）→ 成员技能；
RACI 矩阵固定每类交付物的唯一签字人（A）；SRE 错误预算由 org-scorecard
每轮结算，EXCEEDED 整队进入整改冻结；每个角色的 initiatives 是主观能动性
注册表（事件 → 主动动作，无需上级指示；其中"拒绝/回滚时主动查案例库"
已代码化在 approve-patch 与 fix-apply 中）。审核人独立，任何一方不得
自审自批。

## 脚本与用法

- org-route.py：按 org.json 分派任务并给出指挥链、RACI 签字权、能动性清单
  与值班升级链（L1 首席 → L2 总监 → L3 人工）。
  `--kind review|fix|approve|retro|research|config-change`、`--payload`
  可选。退出码 0=分派成功；2=输入或组织架构错误。
- case-match.py：案例库 v2（链接型档案，本地轻索引）。
  `--match "<问题>"` 复用匹配（命中失败案例会提示避免同样路径）；
  `--ingest --title ... --takeaway ...` 入库必须附 `--url`（公开档案/仓库）
  或 `--local-ref`（本仓库轮报/验收测试），长文不入本地索引；
  `--from-ledger <pitfalls.json>` 把已结案坑批量转索引。退出码 0/2。
- case-archive.py（档案员）：成败双轨详细整理与发布。
  `--kind success|failure --title ... --digest "<详细摘抄>" --lessons ...`
  入库并把摘抄渲染为 archive/<id>.md；`--from-artifacts --scan <runs>`
  自动把 ROLLED_BACK 落盘台账收为失败案例；`--publish` 渲染全部案例档案
  并在本地档案仓 archive-repo git 提交；`--push --remote <URL>` 推送到
  自选 Git 远端（校验拒绝本地/私有地址；无凭据立即失败不算存储失败）。
  退出码 0/2。
- research-brief.py：研究简报签发。`--description "<疑难>"` 或
  `--from-pitfall <台账ID> --ledger <台账>`，`--out <研究目录>`。
  产出 brief-<id>.md/.json（约束/中英检索词/已知案例/验收口径）。
  脚本不联网——检索由宿主（智能体）执行。退出码 0/2。
- org-scorecard.py：SRE 错误预算结算。`--scan <产物目录>` 可多次
  （缺省 retro/ 与 runs/）。判定 PASS / WARN / EXCEEDED（整队整改冻结），
  无数据如实标 N/A。退出码 0/2。
- task-pipeline.py：任务流水线（模糊意图 → 拆解 → 派发 → 汇总的机械骨干）。
  `--from-intent --request "<原话>" [--repo <路径>] --out <目录>`：吃
  intent-parse 的输出拆成带产出物/依赖/DoD 的子任务并落盘 plan-<id>.json；
  意图阻塞（C 级）退出码 3 带回单问，不拆解，假设与待确认项随 plan 落盘。
  `--dispatch --plan <plan.json>`：重叠/遗漏闸（id 唯一、依赖无环、kind 合法）
  后按拓扑序逐任务经 org-route 派发，附指挥链/RACI/输入输出格式/截止条件。
  `--collect --plan <plan.json> --results <回报.json>`：汇总为整体结论/
  关键改动/遗留风险/待办；未回报与失败一律进遗留，待确认项原样带回。
  退出码 0=成功；3=意图阻塞；2=输入错误。

## 疑难杂症升级链（org.json escalation）

1. L1 团队首席：先 `case-match --match`，命中即按链接取档案复用对策；
2. L2 总监：未命中 → `research-brief` 签发简报（可从台账坑 ID 生成）；
3. 资料员/宿主持简报联网检索（官方文档与权威仓库优先，记录 URL）；
4. 结论经 `case-match --ingest` 入库（必须带链接），附验收口径；
5. 可配置化结论落地为行为级优化（如 taint-config.json，须 _governance
   两人规则元数据），改后必跑反向验证 + synth 精度基线。

## 结果判读

- 分派回执含 assignee（含首席与错误预算）/chain_of_command/raci/
  initiatives/escalation_levels，按预期交接物验收各团队产出；
- scorecard 出现 WARN → 该团队整改关注；EXCEEDED → 冻结扩功能；
- 研究简报的验收口径硬性要求结论落地为配置扩展/测试补充/代码修改之一；
- 案例 id 冲突说明同题已入库，应复用而非重复研究。

## 硬约束

- 总监对被审仓库与各团队产物只读，只写研究/案例目录。
- task-pipeline 派发只到指挥链与回执，不代替团队执行；汇总时未回报任务
  不得当作完成。
- 行为级优化（配置或代码）必须经总监批准（提案人≠批准人）并过验证口径，
  禁止直接改扫描器代码。
- 案例条目禁止包含凭据形态内容（产物红线 5）；无链接的结论不算入库。
