# round-79 tomlkit 地板效应实验（协议 v4：附录加失败测试指针）

## 结论先行

- **假设证实（placement 侧）**：`--protocol-notes` 附录加一行失败测试
  指针后，tomlkit-placement 从 r77 v3 双臂 0 编辑（探索瘫痪）转为
  进入编辑行为（1 编辑 / 334s / 24 轮），机械判分 **resolved**
  （F2P 1/1 + P2P 173 passed，补丁 1844 B）。
- **literal-strings 侧负结果（归因端点/模型层，非材料设计）**：两次
  跑（初次 28s + 重试 37s）均 0 编辑，形态不是探索瘫痪也不是模型
  fast-done，而是 **deepseek-flash 在 JSON 模式下的空内容流**——22 条
  history 中 4+ 条「empty content (retryable)」/不可解析，重试 3 次
  全空后循环终止。r77 坑 d6332f1fd795 的空内容重试对策生效但该模型
  下空内容率过高，属端点/模型层限制。
- **语料设计条款升级（按 PENDING 预案）**：凡种子失败测试的语料，
  协议附录必须含失败测试指针行（文件 + 已知 node id）——已写入
  样例模板 `agent/protocol-notes-example.md`（含依据注记）。

## 口径

- 实例：r77 冻结语料复用（problem.md / test.patch 不动，sha256 同
  `corpus-frozen.json`）；臂：single + 附录（v4 = v3 + 附录模板 +
  测试指针行）；对照基线 = r77 v3 数据（不重跑）。
- 模型：deepseek-flash（总监 2026-11-03 提供的测试用 key，仅 flash；
  环境变量注入，不入产物）；JSON 模式开；rounds 24。
- 预算：≤6 跑（PENDING 约定），实际用 3 跑（placement 1 +
  literal-strings 2）；预算内结论充分，提前收束。

## 结果

| 实例 | r77 v3（无附录） | r79 v4（附录+指针） | 判定 |
|---|---|---|---|
| tomlkit-placement | 0 编辑 / failed（双臂同） | 1 编辑 / 334s / **resolved**（F2P 1/1、P2P 173 passed） | **地板解除** |
| tomlkit-literal-strings | 0 编辑 / failed（双臂同） | 0 编辑 ×2 / 空内容流 | 未解除（端点层归因） |

- placement v4 判分明细：种子失败节点 test_adding_an_element_to_
  existing_table_with_ws_remove_ws 通过；P2P 全仓 173 passed 无回归。
- literal-strings 空内容流证据：`out-v4-retry/task-meta.json` history
  （22 条中 4+ 条 empty/unparseable）；与 placement 同端点同 key 同
  模式下 placement 正常 334s——空内容率是任务相关（或随机）的端点
  行为，非全局配置问题。

## 解读与限制

1. **单实验不外推**：n=2 实例、单模型（flash）、单端点；placement
   的 resolved 证明「指针解锁编辑行为」机制成立，但「附录指针 ⇒
   resolved」的强度需扩样验证（下批语料扩面时自然扩样）。
2. **flash 模型适配限制如实记录**：空内容流 + 28-37s 快速终止，
   deepseek-chat 无此形态（r77 v3 全 10 跑零复现）。flash 若继续
   用于评测，建议每跑前置 1 次空内容探测，或轮数预算内允许空内容
   不计轮（当前实现：空内容按可重试失败，3 次全空即终止循环）。
3. r79 用的 key 为测试用 key（仅 flash），实验后建议轮换或限定用途。

## 证据文件

- 本实验：`reports/_work/uplift-r78/`（notes-*.md、v4-progress.log、
  PENDING.md）与 `reports/_work/uplift-r77/work/tomlkit-*/single/
  out-v4*/`（task-meta/edits.patch）——gitignored 工作区
- 判分：placement v4 judge-v4 worktree 实跑（F2P/P2P 输出见上文）
- 产品化落点：`agent/protocol-notes-example.md`（测试指针占位行 +
  依据注记）
