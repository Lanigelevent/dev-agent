---
name: retro
description: 迭代官（第四角色）：每轮工作末尾收集踩坑并入台账，产出轮报与下一轮改进候选，开局先读检查单。也用于口语说法：复盘一下这一轮踩了哪些坑、生成轮报和下一轮检查单、坑台账在哪
---

# retro — 迭代官（每轮末尾的复盘与自我优化）

迭代官独立于评审、修复、审核三方，负责组织的记忆：把每一轮工作踩到的坑
变成结构化台账，再变成下一轮的改进候选与开局检查单。闭环是
「坑 → 台账 → 轮报 → 下一轮检查单 → 坑变少」。

坑的两个来源：

1. **轮内手工事件**：智能体在工作中随时把坑写成事件 JSON
   （{category, description, root_cause, countermeasure, source}），类别建议：
   回滚 / 行为回归 / 补丁返工 / 误报 / 转人工 / 手工。
2. **产物痕迹自动采集**：approve-patch 的 REJECTED（补丁返工）、
   fix-apply 的 ROLLED_BACK apply-log（回滚，含测试失败）、
   fix-manifest 的 skipped（转人工）、experience.json（误报累计）。

## 每轮末尾的标准动作

```bash
py retro-ledger.py --events <本轮事件.json> --scan <runs 目录> --scan <修复产物目录> --out retro
py retro-report.py --ledger retro/pitfalls.json --out retro --round N
```

- retro-ledger.py：`--out <复盘目录>` 必填；`--events <事件 JSON>`、
  `--scan <路径>`（可多次）、`--close <坑 ID>`、`--archive <非坑 ID>` 可选；
  `--close` 必须同时给 `--close-note <可验证验收口径>`，否则退出码 2
  （结案不可审计 = 灭灯不是填坑）；`--archive` 必须同时给
  `--archive-note <为什么不是坑>`，只对 open 生效，与 `--close` 互斥——
  closed 是「真坑已填」、archived 是「入册错了」，两者不可互换。
  事件 JSON 的 `type` 为 feature/test/doc/confirmation 时不入册（完成/确认
  事项，不是坑；round-44 修的就是旧入册器把 22 条完成事件收成 open 坑）；
  缺 type 或 correction 等其余类型按坑处理。产出/更新 pitfalls.json
  （按 id 去重合并，权重排序），stdout 报 skipped_events 如实列出被跳过条目。
  退出码 0/2。
- retro-report.py：`--ledger <pitfalls.json>`、`--out <复盘目录>` 必填；
  `--round <N>`：真仓必填（缺省自动编号在真仓被护栏拒绝——r155 坑
  a5ba44db35ee 对策，round-156 落地；沙盒无 next-round.md 时缺省自增仍可用，
  确要用加 --confirm-next）。产出 round-<N>-report.md、
  round-<N>-candidates.md 与改进候选 JSON（stdout）。退出码 0/2。
  **不写 next-round.md**：开局检查单归人工维护（带验收口径与来源产物），
  脚本只在 stdout 如实报它存不存在（`next_round` 指针，不存在为 null）。
  round-28 之前 report 每次重写 next-round.md，把 46 行人工正文覆盖成 5 行骨架
  （坑 0ec029ca74bf）；现在机器产出与人工检查单分文件分名字，谁也不再覆盖谁。

## 每轮开头的标准动作

先读 `retro/next-round.md`（上一轮收尾时人工增补，脚本不动它）：逐项核对未结坑的对策，
把"同一坑不踩第二次"作为本轮验收口径之一；机器口径的类别骨架看
`retro/round-<N>-candidates.md`，只当参考、不当检查单。类别 → 对策的知识库在
retro-report.py 的 CATEGORY_SUGGESTION，随复盘持续补充。

## 结果判读

- 台账 open 持续下降且不再复发同 id 坑 = 迭代有效；
- 同一 category 反复新增 = 对策无效，应升级为结构改造（写进改进候选标题）；
- 全部结案时轮报会输出"可全新开工"。

## 硬约束

- 迭代官对被审仓库与产物目录只读，只写自己的复盘目录。
- 台账条目禁止包含凭据形态内容（沿用产物红线 5）。
- 坑的结案（--close）必须带可验证的验收口径，不许"标完成即完成"。

## memory-pipeline.py — 记忆三级管线（round-216 新增，AB-20）

```bash
py skills/retro/scripts/memory-pipeline.py plan --store retro/agent-memory.jsonl \
   --events retro/events-round-N.json --namespace agent
py skills/retro/scripts/memory-pipeline.py add --store retro/agent-memory.jsonl \
   --events retro/events-round-N.json
py skills/retro/scripts/memory-pipeline.py retrieve --store retro/agent-memory.jsonl \
   --query "..." --top-k 3
py skills/retro/scripts/memory-pipeline.py prompt --store retro/agent-memory.jsonl \
   --events retro/events-round-N.json   # 自写决策提示（宿主/LLM 消费面）
```

- 三级分工：抽取（事件→候选事实，completion 类型过滤与台账口径一致）→
  合并决策（TF-IDF cosine ≥0.65 判 UPDATE 合并刷新，否则 ADD 新知识；
  DELETE 归 compact-memory 老化层，不在本层重复）→ 检索（委托
  memory_retrieval.retrieve，阈值标定沿用 round-61 间隙）。
- 决策臂双臂：deterministic 缺省；--decider llm 生成自写决策提示供宿主
  消费，无 key 时 arm_status=blocked_no_key 且**不写 store**（不冒充
  决策已判——诚实口径同 live-sample blocked 语义）。
- namespace 分级（mem0 user/agent/run 同型）：同 namespace 内对照，
  跨级不合并。
- store 原子写（uuid4 tmp + os.replace，对齐 _status_write 惯例）。

退出码：0=成功；1=events/store 不可读；2=输入错误。
