# round-69 结构改造落地：read 行区间/符号锚定取窗 + pdm-3237 复跑验证

日期：2026-10-31 ｜ 版本：v1.70.0 ｜ 状态：**工具改造验证通过（深文件可达）；
pdm-3237 判分 unresolved 维持 failed（n=3 次尝试、2 实例）；契约 528→530**

## 结论

1. **结构改造落地（open 坑对策）**：编码循环 read 动作新增两种取法——
   `路径:起-止` 行区间（1 基含端、逐行行号前缀、单段 ≤400 行超限标注续取）
   与 `路径#符号` 锚定（词法缩进跨度：def/class 起至同级缩进，未命中退回
   关键词取窗）；SYSTEM_PROMPT 同步文档化；契约 +2（`slice_lines` 钳制/
   截断/行号 + `extract_symbol_span` 跨度/未命中/1 基行号），528→530。
2. **pdm-3237 复跑对比（D-045 重试口径）**：
   - attempt-1（round-68，改造前）：11 轮探索 / **0 编辑** / 深文件段
     （builders/base.py 195–330）全程不可见 → 按预算收束。
   - attempt-2（round-69，改造后）：**第 1 轮即用 `:195-330` 直读深区**，
     第 3 轮锁定崩点链（use_uv 下构建隔离安装走 UvSynchronizer 项目级
     uv sync 管道），第 9 轮交付补丁（`UvSynchronizer.synchronize` 对无
     依赖组的构建隔离安装回退 `BaseSynchronizer`，+7 行）——**材料可达性
     障碍已移除**。
   - 判分（f2p-only，45.61 s）：**unresolved**——F2P（test_build_command）
     期望 `do_build(..., verbose=0, ...)` 新签名：上游修复（difficulty
     2 文件/5 hunks/75 行）连带改 CLI 管道签名，13 行外科回退未覆盖该
     API 面。pdm-3237 维持 failed（重试预算已用）。
3. **冷启动口径**：n=2 实例（llama_deploy-330 / pdm-3237）、累计 3 次尝试
   全部 failed——两次 attempt 对比把失败归因从「材料不可达」（工具缺陷，
   已修）收窄到「修复面设计」（75 行级 API 改造超出当前单点零反馈能力）。

## 1. 对 open 坑（read 取窗）的结案依据

- 机制修复：code-task read 处理器解析 `:start-end` / `#Symbol`，未命中
  与超限均有明确反馈；默认（无后缀）路径行为不变（round-19/20 语义保留）。
- 验证：契约 test_slice_lines_numbered_and_clamped /
  test_extract_symbol_span_full_body 绿；attempt-2 实跑 trace 显示第 1 轮
  深区直读、第 9 轮交付补丁（对比 attempt-1 的 11 轮 0 编辑）。
- 残余风险：行区间取窗依赖模型主动使用——SYSTEM_PROMPT 已带示例；宿主
  协议纪律（响应写对 id）本轮仍复发 3 次，已在上轮坑内升级对策。

## 2. 证据与复跑

```
# 契约
.venv/Scripts/python.exe -m unittest discover -s tests -p test_agent.py

# pdm-3237 attempt-2 判分
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-pdm.jsonl --mode predictions \
  --f2p-only --predictions datasets/swebench/live-runs-r68/predictions-pdm-3237.jsonl \
  --out datasets/swebench/live-runs-r68/live-judge-pdm \
  --source-root datasets/swe-repos --no-network \
  --setup-timeout 900 --exec-timeout 600
```

产物：`datasets/swebench/live-runs-r68/coldstart-pdm-3237/`（attempt-2，
8 轮/2 编辑/补丁 1 031 B）、`.../coldstart-pdm-3237-attempt1-window-blind/`
（attempt-1 归档）、判分台账 `live-judge-pdm/live-sample-ledger.json`。

## 3. 边界（不宣称的部分）

- unresolved ≠ 回退修法错误——F2P 断言的是改造后的 CLI 签名（verbose=0），
  我的补丁与上游修法不同面；未对照 gold patch（判分侧未读），归因基于
  测试断言与 difficulty 字段。
- 冷启动 n=2 零 resolved 不构成能力结论；材料面改造的效果以「可达性」
  度量（轮数/编辑数对比），不以 resolved 折算。
- 全套件门在本 venv 不可达（缺 pytest-httpserver 等测试依赖，收集期
  ERROR）——循环内测试门对 pdm 语料形同关闭，交付判据完全依赖判分侧
  f2p-only，如实记录。
