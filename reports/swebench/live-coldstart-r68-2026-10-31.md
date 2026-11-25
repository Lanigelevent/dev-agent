# round-68 冷启动资源面推进：七条候选基线（2/7 可判）+ 第二个冷启动数据点（pdm-3237，failed）

日期：2026-10-31 ｜ 版本：v1.69.0 ｜ 状态：**两项 failed 如实记录（n=2 冷启动零 resolved）；基线面 1→3 可判（含 round-65 llama_deploy）**

## 结论

1. **余下七条候选基线（f2p-only 部分口径）**：pdm-3237 与 conan-17092
   `baseline_ok`（2/7），instructlab `env_failed`（pip -e . 构建失败，待
   任务级适配），pvlib/reflex/haystack/keras 四条 `baseline_unexpected`——
   根因是 **F2P 测试为 test_patch 新增**（base 快照里不存在 → 判分点
   missing → 严格基线语义不可判）；该四条的可行通路是 gold 先行验证
   （round-51 matplotlib 同型）。另实测发现**七条候选的 P2P 全部含上游截断
   id（9–194 条）**——与 cfn-lint/matplotlib 同源的上游数据缺陷，完整
   `resolved` 口径在本语料上对所有这些实例都不可得，f2p-only 是唯一可判
   口径。
2. **第二个冷启动数据点（pdm-3237，f2p-only 候选里基线可判且修复面最小）**：
   **failed（0 编辑）**——编码循环 11 轮探索后按预算收束，根因不是任务难度
   而是**材料面可达性**：`read` 动作的取窗只返回文件头部（builders/base.py
   恒取 19–181 行），隔离构建区（195–330 行，含 322 行的隔离环境创建点）
   经 9 次 search 只能拿到单行命中，深段代码全程不可见；75 行/2 文件的
   修复面在可得材料下无法唯一确定，按预算纪律收束不盲改。
3. **冷启动累计 n=2（llama_deploy-330 / pdm-3237）均 failed**——两次失败
   形态不同（传输语义不可推导 / 深文件段不可达），共同点是**带反馈口径
   20/20 与零反馈能力之间的真实差距**；二项区间口径下不宣称任何成功率。

## 1. 基线结果（datasets/swebench/live-runs-r68/live-sample-ledger.json）

| 实例 | 基线（f2p-only） | 耗时 | 说明 |
| --- | --- | --- | --- |
| pdm-project__pdm-3237 | **baseline_ok** | 36.1 s | F2P 1 条 base 即存在（test_patch 修改型） |
| conan-io__conan-17092 | **baseline_ok** | 31.0 s | F2P 6 条同上 |
| instructlab__instructlab-2526 | env_failed | 43.4 s | `pip install -e .` 构建失败（依赖适配待做） |
| pvlib__pvlib-python-2249 | baseline_unexpected | 65.9 s | F2P 7 条全 missing（test_patch 新增型） |
| reflex-dev__reflex-4087 | baseline_unexpected | 59.7 s | 同上（F2P 1 条） |
| deepset-ai__haystack-8489 | baseline_unexpected | 87.8 s | 同上（F2P 4 条） |
| keras-team__keras-20389 | baseline_unexpected | 31.5 s | 同上（F2P 1 条） |

任务级适配（记录在各 gate-r68-*.jsonl 的 adaptation_note）：test_cmds 由上游
命令归一为 `python -m pytest -rA`（f2p-only 只判 F2P 节点，避免 conan/keras
的整仓收集）；setup 为清华镜像 `-e .` + 各仓测试依赖。

## 2. 冷启动 #2（pdm-3237）失败分析

- 预算对账：`--rounds 12` 用 11（宿主侧三次响应写错 id 消耗约 3 轮——
  宿主协议纪律已在 round-67 入册，本轮仍复发，对策升格见台账）；≤20 编辑
  用 0；D-045 的 ≤1 整轮重试已在 llama_deploy 用掉（本实例单次尝试）。
- 材料面事实（全部来自循环内材料）：`search 'use_uv'` 16 处命中把范围收敛
  到 core.py:211/375/942/952 与 builders/base.py:171-322；`read` base.py
  两次返回同一窗口（19–181），`search … glob=base.py` 只给单行；行为探针
  未开（--allow-probe 默认关闭）。
- **改进候选（结构改造）**：编码循环 read 动作应支持「按行区间取窗」或
  「按符号锚定取窗」（tree-sitter 定义点已可用），否则深文件（>180 行）
  修复任务在当前材料面下系统性不可解。

## 3. 对 D-045 的影响

- 候选资源面：源 9/9 → 基线可判 **3/9**（llama_deploy round-65 + pdm/conan
  本轮）；`f2p_passed` 通路全部可用（F2P 零坏 id）。
- 冷启动累计 **n=2 failed**——样本量口径：n<9 如实标注，二项区间随 n 收敛；
  后续数据点应优先「gold 先行验证 + 基线 unexpected（F2P 新增型）」的实例
  （reflex/pvlib/keras 修复面最小 1–4 行）。
- resolved 口径不变：官方镜像不可达（round-66 判死）+ 本语料 P2P 截断
  （本轮实测 7/7 含坏 id）双重阻塞。

## 4. 证据与复跑

```
# 基线（七条，f2p-only）
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-pdm.jsonl --mode baseline --f2p-only \
  --out datasets/swebench/live-runs-r68 --source-root datasets/swe-repos \
  --no-network --setup-timeout 900 --exec-timeout 600

# 冷启动 #2 产物（11 轮 / 0 编辑 / done 收束）
datasets/swebench/live-runs-r68/coldstart-pdm-3237/
```

## 5. 边界（不宣称的部分）

- n=2 冷启动零 resolved 不构成任何能力结论；两次 failed 的根因分别指向
  传输语义推导与材料可达性，是**工具面可改进项**，不是「协议不可行」证明。
- 基线 unexpected 的四条（F2P 新增型）不是环境失败——gold 先行可验证其
  判分链路，本轮未跑（预算），如实留待。
- P2P 截断结论基于括号平衡体检（round-65 机制），未逐条对照上游原表。
