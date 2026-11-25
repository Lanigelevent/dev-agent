# round-70 冷启动第 3 数据点：gold 先行验证拦下两条坏判分链 + conan-17092 failed

日期：2026-10-31 ｜ 版本：v1.71.0 ｜ 状态：**reflex/keras blocked_env（gold 先行验证拦截）；conan-17092 failed（0/6 F2P）；冷启动累计 n=3 实例 / 4 次尝试全 failed**

## 结论

1. **gold 先行验证的价值兑现**：reflex-4087 与 keras-20389 的 gold 模式
   f2p-only 判分双双 unresolved（keras F2P missing——保存类测试缺后端依赖；
   reflex F2P gold 仍 fail）——**判分链本身不可信**，按 D-045 记 blocked_env，
   不在坏链上浪费冷启动预算。负结果也是结果：候选资源面的「基线可判」从
   3/9 收窄为「可判且链可信」1/9（仅 conan——llama_deploy 基线 ok 但冷启动
   已用、pdm 已用重试）。
2. **冷启动第 3 数据点（conan-17092，C++26 旗标表扩展）**：**failed**
   （0/6 F2P，判分 31.0 s）——编码循环 7 轮 / 4 编辑（全部「已见文本」编辑：
   gcc ≥14 与 clang ≥17 的 v26 赋值 + gcc 映射字典，+15 行）；失败形状：
   `settings_test::test_possible_values` 证实 settings.yml 需加 cppstd=26
   枚举值（预算内未读）、gold 对旗标表还有测试对齐重构（如 gcc 8 的
   `c++2a`→期望 `c++20` 的门位变化）——41 行 / 2 文件的多文件 API 面
   超出单点零反馈能力，与 pdm 的归因一致。
3. **冷启动累计 n=3 实例 / 4 次尝试全 failed**——三次失败形态：传输语义
   不可推导（llama_deploy）/ 多文件 API 面（pdm、conan）；材料可达性
   （round-69 已修）不再是瓶颈——符号锚定取窗在本轮两次直取完整函数体
   （`#_cppstd_gcc` / `#_cppstd_clang`），read 能力改造的价值得到二次实证。

## 1. 执行记录

| 实例 | 验证 | 结果 | 说明 |
| --- | --- | --- | --- |
| keras-20389 | gold f2p-only | unresolved（36.6 s） | F2P missing：保存类测试缺后端依赖 → blocked_env |
| reflex-4087 | gold f2p-only | unresolved（69.0 s） | gold 后 F2P 仍 fail → blocked_env |
| conan-17092 | 冷启动 7 轮 / 4 编辑 → 判分 | unresolved（31.0 s，0/6 F2P） | 补丁 1 951 B；缺 settings.yml 枚举与 apple-clang/msvc 表 |

宿主协议 id 纪律本轮仍复发 1 次（stale-id 覆写）；编码循环侧新材料面
（行区间 + 符号锚定）使用顺畅，未再出现深文件不可达。

## 2. 对 D-045 的影响

- 可信判分链现存 **1/9**（conan-17092，冷启动已用）——其余或 blocked_env
  （reflex/keras/instructlab）或基线 unexpected 未验证（pvlib/haystack）或
  冷启动预算已用（llama_deploy/pdm）。**冷启动语料在本机资源面基本见底**：
  扩样需先修判分链（测试依赖适配）或等官方镜像。
- 归因口径稳定：三次 failed 均为「修复面设计」（多文件 API 改造），非
  材料可达、非判分缺陷；二项区间口径下不宣称成功率。

## 3. 证据与复跑

```
# gold 先行验证
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-keras.jsonl --mode gold --f2p-only \
  --out datasets/swebench/live-runs-r70 --source-root datasets/swe-repos --no-network

# conan 冷启动判分
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-conan.jsonl --mode predictions \
  --f2p-only --predictions datasets/swebench/live-runs-r70/predictions-conan-17092.jsonl \
  --out datasets/swebench/live-runs-r70/live-judge-conan \
  --source-root datasets/swe-repos --no-network
```

产物：`datasets/swebench/live-runs-r70/coldstart-conan-17092/`（7 轮/4 编辑）、
判分台账 `live-judge-conan/live-sample-ledger.json`。

## 4. 边界（不宣称的部分）

- n=3 零 resolved 不构成能力结论；conan 的部分修复（gcc/clang 旗标赋值）
  未验证正确性（判分 0/6），不宣称「gcc 路径已修好」。
- blocked_env 的判定依据是 gold 判分失败（判分链不可信），不是环境彻底
  不可修——测试依赖适配后可复验（instructlab/reflex/keras 同类）。
- gold patch 全程未读；失败归因基于测试断言形状与 difficulty 字段。
