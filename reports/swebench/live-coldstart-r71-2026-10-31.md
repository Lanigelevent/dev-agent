# round-71 判分链修复 + keras-20389 带反馈复修 f2p_passed（n=1）

日期：2026-10-31 ｜ 版本：v1.72.0 ｜ 状态：**keras-20389 f2p_passed（带反馈复修，n=1 不外推）；reflex 链未修全；instructlab blocked_python**

## 结论

1. **keras-20389 判分链修复成功**：gold f2p-only 判分 `f2p_passed`（F2P 1/1，
   127.0 s）——根因是 conftest 缺 `tensorflow` 后端（gold 先行验证的
   F2P missing），setup 补 `tensorflow-cpu` 后链路可信。可信判分链
   1/9→**2/9**（conan + keras）。
2. **冷启动第 4 数据点（keras-20389）**：
   - **attempt-1（零反馈）failed**：4 轮 / 1 编辑（`convert_revived_tensor`
     的 Unknown layer ValueError→IndexError，与 legacy 分支契约一致）；
     判分 unresolved——失败形状（test.log）暴露第二处 raise：
     `Layer node index out of bounds` ValueError（L702，首次 read 未覆盖
     的 700+ 区）。
   - **attempt-2（带 attempt-1 判分反馈）f2p_passed**：3 轮 / 2 编辑
     （两处 ValueError→IndexError，补丁 1 281 B）——重用层的前向引用在
     加载时被 L534 的重入队机制捕获重试。判分 32.015 s，F2P 1/1
     （partial，**不计 resolved**，D-029/D-045）。
   - **口径（如实）**：attempt-2 用了 attempt-1 判分的失败位置——
     **带反馈复修，n=1 不外推**（与 D-030 的 20/20 同型），不宣称零反馈
     收敛；零反馈口径仍是 n=3 实例 / 3 次尝试全 failed（attempt-1 计入）。
3. **reflex 链未修全**：pydantic 钉 2.7.4 后 F2P 仍 missing（依赖面不止
   pydantic），继续 blocked_env；**instructlab blocked_python**（包要求
   Python <3.12，本机 3.12.13，无 3.11 解释器供应，不硬凑）。

## 1. 判分链修复记录（gold 先行验证驱动）

| 实例 | 根因（gold 验证暴露） | 修复 | gold 复验 |
| --- | --- | --- | --- |
| keras-20389 | conftest `import tensorflow` 失败 | setup 加 tensorflow-cpu（清华镜像） | **f2p_passed**（127.0 s） |
| reflex-4087 | pydantic_v1_patch 崩 + F2P 仍 missing | pydantic 钉 2.7.4 | unresolved（依赖面不止 pydantic） |
| instructlab-2526 | 包要求 Python <3.12 | 不硬凑 | blocked_python 如实记录 |

任务级适配记录在 gate-r68-keras/reflex.jsonl 的 adaptation_note。

## 2. 冷启动第 4 数据点（keras-20389）细节

- 任务：加载含复用权重的模型报 ValueError；报告者在 PS 中直接指出
  functional.py 的 ValueError 应为 IndexError（零反馈材料内的强提示）。
- attempt-1（零反馈）：第 1 轮 search → 第 2 轮行区间直读 495-535/655-700
  （except 契约 + 第一处 raise）→ 第 4 轮交付 1 处修改；判分 94.0 s
  unresolved，失败形状指向未读的 700+ 区第二处 raise。
- attempt-2（带判分反馈）：第 2 轮直读 688-760（两处 raise 全可见）→
  第 3 轮双改 → done；判分 **f2p_passed**（F2P 1/1，32.015 s）。
- D-045 预算对账：每实例 ≤1 次整轮重试——attempt-2 即该重试，已用；
  ≤20 编辑用 3；墙钟超 45min（宿主往返延迟，如实记录）。

## 3. 对 D-045 路线的影响

- 冷启动口径全景：**零反馈 n=3 failed**（llama_deploy/pdm/conan）+
  **带反馈复修 n=1 f2p_passed**（keras）——与 agent 侧 20/20（带反馈）
  并列，正好构成「零反馈 vs 带反馈」的对照测量；不混算、不外推。
- gold 先行验证作为判分链可信前置的价值两轮兑现（round-70 拦坏链、
  round-71 修复后取信）；扩样前置检查成立。
- 符号锚定/行区间取窗持续有效（attempt-2 第 2 轮即完整覆盖两处 raise）；
  宿主协议 stale-id 本轮再犯 2 次（坑对策持续失效，升级为结构改造候选：
  code-task 侧在 WAIT_HOST_LLM 输出里加「勿复用上一跳 id」的显式提示）。

## 4. 证据与复跑

```
# gold 复验（判分链可信）
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-keras.jsonl --mode gold --f2p-only \
  --out datasets/swebench/live-runs-r71 --source-root datasets/swe-repos --no-network

# 冷启动 attempt-2 判分
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-keras.jsonl --mode predictions \
  --f2p-only --predictions datasets/swebench/live-runs-r71/predictions-keras-20389-v2.jsonl \
  --out datasets/swebench/live-runs-r71/live-judge-keras \
  --source-root datasets/swe-repos --no-network --force
```

产物：`datasets/swebench/live-runs-r71/coldstart-keras-20389/`（attempt-2：
3 轮/2 编辑/补丁 1 281 B）、`.../coldstart-keras-20389-attempt1-partial/`
（attempt-1 归档）、判分台账 `live-judge-keras/live-sample-ledger.json`。

## 5. 边界（不宣称的部分）

- f2p_passed 是 partial 口径（F2P 1/1，P2P 未跑——keras P2P 7686 条含 8 条
  上游截断 id，完整 resolved 不可得），不计 resolved、不折算通过率。
- attempt-2 的成功有判分反馈参与（失败位置直接指向第二处 raise），
  n=1 不外推；PS 本身含报告者给出的修法提示（零反馈材料内的强提示），
  keras 任务本身偏易。
- reflex/instructlab 未修复，如实保留 blocked；gold patch 全程未读。
