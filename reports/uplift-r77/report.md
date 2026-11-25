# round-77 D-046 路径 B uplift 对照（DeepSeek 端点 × 公开上游语料）

## 结论先行

- **5 对 paired 对照，差值 0**：single 1/5 resolved，phases 1/5 resolved。
  **按 D-046 判据早停触发（前 5 对差值 ≤0）**——uplift 主张不成立，
  4.1 定案「机制可用、uplift 未证」：三份独立证据方向一致
  （round-58 n=1 自产夹具、round-61 n=2 公开语料、本轮 n=5 对
  DeepSeek 独立语料，差值均 ≤0）。
- **成本比 1.48×**（phases/single 总耗时，判据线 ≤1.5×）——机制成本在
  判据线内，但差值 0 使成本比失去意义。
- **判分全机械**：F2P（种入失败测试）+ P2P（全仓测试）在干净 worktree
  重放补丁后 pytest 对账，不由模型自评。

## 口径

- **语料**：公开上游真实提交（click ×3、tomlkit ×2），题目只给诉求
  （problem.md = 行为需求，无实现暗示），测试补丁开跑前种入两臂；
  语料冻结（`reports/_work/uplift-r77/corpus-frozen.json`：problem.md +
  test.patch 逐项 sha256 + base/target sha）。
- **F2P 双向验证**：种子后基线必败 ∧ 目标提交必过，逐 node id 机械
  枚举（`f2p-nodes.json`；optionparser 与 literal-strings 为收集期
  ImportError 形态，F2P 退化为文件级）。
- **模型轴**：两臂同一模型 deepseek-chat（api.deepseek.com，openai
  兼容端点 + JSON 模式），总监 2026-10-31 提供 key（仅环境变量注入，
  不入任何产物；轮后建议轮换）。
- **协议**（对 D-046 的偏离项，如实记录）：r61 为宿主模型 × rounds 4；
  本轮因 DeepSeek 探索节奏适配为 **rounds 24 / locate-rounds 4 / 两臂
  等额 + 两臂等额的协议提示附录**（预算压力与「先编辑后探索」指引，
  arm-neutral）。协议演进 v1（rounds 4：DSML 劫持全灭）→ v2（16 轮：
  纯探索瘫痪）→ v3（24 轮 + 提示：正式批）。
- **协议附录文本**（两臂逐字节一致，运行时拼接，不进冻结 problem）：
  预算 24 轮声明、ranged-read 指引、尽快编辑指引、测试即完成标准声明。

## 结果（协议 v3 正式批）

| 实例 | single | phases | 差值 | single 耗时 | phases 耗时 | single edits | phases edits |
|---|---|---|---|---|---|---|---|
| click-format-filename | fail | fail | 0 | 39s | 72s | 9 | 20 |
| click-private-deprecations | fail | fail | 0 | 39s | 81s | 16 | 0 |
| click-optionparser-deprecation | **resolved** | **resolved** | 0 | 41s | 37s | 9 | 9 |
| tomlkit-literal-strings | fail | fail | 0 | 22s | 33s | 0 | 0 |
| tomlkit-placement | fail | fail | 0 | 22s | 29s | 0 | 0 |
| **合计** | **1/5** | **1/5** | **+0** | 163s | 252s | | |

- optionparser 两臂 resolved（F2P 7/7、P2P 582 passed）——机制可用、
  端到端链路可信（DeepSeek 能在协议内完成 XL 任务）。
- format-filename single：部分修复（F2P 3/5 失败——test_path_surrogates
  与 test_file_surrogates 两形态未过；P2P 578 passed 无回归）。
- private-deprecations single：补丁不完整（PacifyFlushWrapper 改名后
  core.py 内部调用点漏改 → ImportError）→ 失败；phases 臂 0 编辑
  NO_PATCH。
- tomlkit 两实例**双臂 0 编辑**（24 轮纯探索到预算耗尽）——语料级地板
  效应（DeepSeek 对 tomlkit 材料面的探索节奏失配），两臂同受影响，
  计入差值（0）方向不变。

## 判据对账（D-046 路径 B）

| 判据 | 要求 | 实测 | 结论 |
|---|---|---|---|
| resolved 差值 >0 | 必须 | 0 | ✗ |
| 样本量 | ≥10 独立实例 | 5 对（早停） | 按早停规则终止 |
| 成本比 ≤1.5× | 必须（若主张 uplift） | 1.48× | 达标但无意义 |
| 前 5 对差值 ≤0 早停 | — | 触发 | 终止 |

**判定**：uplift 主张不成立，按判据早停。与 r58/r61 两份独立证据方向
一致，4.1 uplift 问题就此定案（不再按判据继续投预算）；4.1 的机制面
（三角色状态机/角色门禁/裁决台账/机械测试优先仲裁）维持可用状态。

## 实跑暴露并当轮修复的三处适配层加固（附契约 +4）

1. **DSML 劫持**：deepseek-chat 的工具调用先验把结构化协议输出劫持成
   私有 DSML 标记，编码循环整轮不可解析 → `llm/provider.py` 增
   `REVIEW_LLM_JSON_MODE=1` 门控的 `response_format=json_object`
   （round-77 实跑验证有效）。
2. **空内容响应**：JSON 模式下偶发空内容（浪费一轮）→ provider 按可
   重试失败处理。
3. **多 JSON 对象响应**：模型偶发一次输出两个动作对象（草稿+终稿），
   旧解析器贪婪 `re.search` 必败 → `_parse_response` 改逐对象
   `raw_decode` 取最后一个成功解码的 dict。
   契约测试 4 项（`tests/test_agent.py` TestParseResponseMultiObject ×2 +
   TestOpenAIProviderJSONMode ×2），全量套件 530→534。

## 限制（如实）

- n=5 对、单模型族（DeepSeek）、两仓语料（repo 级复用 click/tomlkit，
  与 r61 同仓不同提交）；跨模型复验（路径 A ≥2 家族 × ≥5 实例）本轮
  未做——但路径 B 差值 0 已按判据早停，路径 A 的动机（排除模型轴混杂）
  不再改变判定方向。
- tomlkit 双实例双臂地板效应未解决（材料/协议对 DeepSeek 的适配极限），
  下批语料若继续，需重设计材料窗口（如预置 repo map 高亮）。
- 会话代理的长文写入在本轮多次出现内容污染（与台账既有坑
  daf1a5fc2f9f 同形态），改用小步写入+编译验证绕行，未新增坑。
- key 已在对话明文出现过，轮后应轮换。

## 证据文件

- `reports/_work/uplift-r77/tasks.json`（含冻结 sha256 与 F2P 清单）、
  `corpus-frozen.json`、`f2p-nodes.json`、`probe-stage1/2.json`、
  `judge-results.json`、`d046-account.json`、`runs-progress-v3.log`
- 各臂 `work/<task>/<arm>/out/`（task-meta/history/phases.json/edits.patch）
- 判分明细：judge worktree 逐 node 输出（judge-results.json f2p_tail/p2p_tail）
