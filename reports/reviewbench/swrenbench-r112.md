# round-112 P0-2：SWRBench 中立语料接入 + 确定性评审器首跑（2026-11-07）

## 结论先行

- **中立语料接入完成**：ZZR0/SWRench（MIT，1000 真实 PR：500 缺陷 + 500 干净，12 仓）→ swrenbench-import.py import 1000/0 坏行；数据 84.8MB 经 API blobs raw 断点续传拉取（raw 直连/加速镜像均不可达，降级记录在案）。
- **确定性评审器中立首跑（n=1000 全量）**：point_recall **0.42%**（3/713 ground-truth 变更被 38 规则命中）；clean-PR 零噪声率 **97.4%**（500 干净 PR 仅 15 条 findings）。
- **解读（观测 ≠ 因果）**：38 规则针对代码生成反模式（可变默认参等），SWRBench 是评审确认的逻辑/设计缺陷——分布错配，recall 近零属预期；clean 零噪声 97.4% 说明确定性层噪声极低（precision 侧优点、recall 侧短板）。这组数字是中性基线，LLM 评审臂跑分（对标 CodeRabbit 59.4%/F1 36.2%）为下一步。
- **适配要点**：SWRBench diff 为「剥头」形态（路径行+@@，无标准头）——标准化器按 hunk 新旧行数精确重建标准 unified diff；code_snippet 带 @@ 头直接解析行号（span 计算）；修复 _HUNK_RE 单 @ 截断 bug（重建头曾畸变为 `@ @@`）。
- **双轨纪律**：自建 ReviewBench 保留；SWRBench 为中立轨；LLM judge 臂（evaluation_struct 语义）留待下轮接宿主评审器。
- **证据**：reports/_work/swr-score-full.json；datasets/swrenbench/（不入库）；tests/test_swrenbench.py（5 契约）。
