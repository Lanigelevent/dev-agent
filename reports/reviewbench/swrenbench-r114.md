# round-114 P0 延伸：SWRBench 宿主评审臂首跑（2026-11-08）

## 结论先行

- **宿主评审臂机制落地**：swrenbench-import.py 新增 review（host 文件协议
  跑批，--all-pending 一次写全部 prompt、宿主批量填响应、重跑全命中续跑）
  与 judge（PR 级/point 级 F1，论文口径变更点命中）子命令。契约测试
  11/11（5 旧 + 6 新）全绿。
- **首批 stride-10 宿主评阅（n=100，50 change + 50 clean）**：
  PR 级 F1 **0.5789**（P 0.8462 / R 0.44；TP22/FP4/FN28），
  point 级 F1 **0.3656**（P 0.68 / R 0.25；TP17/FP8/FN51，gt 68 点），
  per-PR macro F1 0.2546（n=47，3 排除）。
- **解读（观测 ≠ 因果，n=100 不外推）**：与仓内记录的对标值（CodeRabbit
  59.4%/36.2%，round-112 登记）量级吻合，但这是 **n=100 步长抽样 + 单一宿主
  模型 + 机械 span 匹配**下的首跑数字，不构成能力结论；确定性层对照基线
  （r112：point_recall 0.42%）的交叉价值成立——同一语料上 LLM 臂 recall 显著
  高于 38 规则臂。
- **诚实记录**：1 例响应 JSON 转义损坏计 unparsed（sympy-755，宿主自己写的
  evidence 里有非法 \l 转义——评审员也会写坏 JSON，如实入档）；clean 侧
  4/50 PR 误报（badges http、widgets 链式比较、repr 移除、Shcaling 笔误——
  均为真实代码味道但非 SWRBench gt 缺陷）。

## 判定口径（先写死再看数字）

- **评审任务**：只评审本 PR 引入的变更（diff 的 + 行），七要素 findings
  （loc/desc/evidence/severity/confidence/cause/fix），无问题输出 []。
  材料先脱敏再截断（max_chars=20000，本批零截断；100 例 diff 中位 1.7KB）。
- **PR 级**（整 PR 二分类，micro）：change PR 有 ≥1 finding 记 TP、
  clean PR 有 ≥1 finding 记 FP、change PR 零 finding 记 FN。
- **point 级**（论文口径变更点命中）：gt 变更被 ≥1 finding 命中记 TP、
  finding 行号不落任何 gt span 记 FP、gt 变更未被命中记 FN；行号落 span
  判命中、文件维度不要求（slim 化时文件维度已压平）。clean PR 的 findings
  不进 point 级。macro=change PR 逐 PR F1 平均（无预测且 gt 非空记 0，
  gt 空排除）。
- **与论文（arXiv 2509.01494）的差异**：论文用 LLM judge 做语义命中判定
  （Gemini-2.5-Flash，human agreement ~90%）；本仓用机械行号-span 包含判定
  （无 LLM judge，更保守——语义命中但行号偏移的 finding 记 miss）。论文聚合
  为 per-PR 后跨 PR 平均（macro），本仓 micro 主口径 + macro 参考并行。
  **两套数字不可直接互比**，对标值仅作量级参照。
- **对标值出处**：59.4%/36.2%（PR 级/point 级）来自仓内 round-112/第 74 条
  登记（CodeRabbit）；SWR-Bench 论文自身最高 Overall-F1 为 19.38%
  （LLM-judge 口径），不可与本仓机械口径直接互比。

## 跑批定义（可复算）

- 语料：datasets/swrenbench/swr-slim.jsonl（1000 例，change 0-499 在前、
  clean 500-999 在后）；--stride 10 → 100 例（50/50，覆盖 12 仓均匀分布）。
- 评审器：宿主模型（GLM，CRA_LLM_PROVIDER=host 文件协议，幂等 id 缓存），
  每例独立评阅 100 份 prompt（100 份响应文件在 reports/_work/swr-r114/llm-tasks/，
  语料不入库目录，按惯例不提交）。
- 数据：reports/_work/swr-r114/findings.json（27 findings / 100 样本）
  与 judge.json（judge --out 落盘，全口径字段含 per_type）。

## 数字（n=100 首批）

| 指标 | 本仓宿主臂 | r112 确定性臂 | 仓内登记对标值 |
|---|---|---|---|
| PR 级 F1 | **0.5789** | —（未算 PR 级） | 59.4%（CodeRabbit，登记值） |
| PR 级 P / R | 0.8462 / 0.44 | — | — |
| point 级 F1 | **0.3656** | —（r112 只出 recall） | 36.2%（CodeRabbit，登记值） |
| point 级 P / R | 0.68 / 0.25 | recall 0.0042 | — |
| point 级 macro F1 | 0.2546（n=47） | — | — |
| clean PR 零噪声 | 46/50 = 92% | 97.4% | — |

per-type recall（gt≥4 的类型）：E.3.2 Solution Approach 0.20（3/15）、
E.1.1 Textual Changes 0.46（6/13）、F.3 Resource 0.375（3/8）、
F.1 Interface 0.25（2/8）、F.5 Support 0.17（1/6）、F.2 Logic 0.17（1/6）、
E.3.1 Organization 0.00（0/6）、E.2 Visual Representation 0.25（1/4）。

## 局限与后续

- **n=100（stride-10）是首批而非全量**：全量 n=1000 用同一命令即可续跑
  （review --stride 1 全量重跑，幂等 id 缓存使已评样本零成本命中；宿主评阅
  预算另批）。机械口径把「语义命中但行号偏移」记 miss——论文的 LLM judge
  会放行这类，本仓数字因此系统性偏低。
- **单模型单温度**：宿主模型单一（GLM），温度语义由 provider 层固定；
  跨模型对比（对齐论文多评审器矩阵）未做。
- **纯删除变更在本口径下不可定位**：gt 片段锚定在 + 行上，纯删除变更的
  gt span 为空、自动排除出 gt 点集（本批 change 侧 gt 68 点中含此类排除；
  如 sphinx 8085 类以删除为主的 PR——若 gt 全空则该 PR 的 recall 分母不含它）。
- **下一步候选（供 round-115）**：①全量 n=1000 续跑（宿主评阅预算另批）；
  ②LLM-judge 臂（论文同款语义命中判定，与机械口径对照出「行号偏移折损」）；
  ③确定性臂补 PR 级指标对齐双臂可比性。
