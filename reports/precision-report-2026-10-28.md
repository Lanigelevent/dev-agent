# dev-agent 精度报告（2026-10-28）

## 结果（合成语料 120 样本）

| 指标 | 值 |
|---|---|
| precision（报出的多少是真的） | 1.0 |
| recall（注入缺陷的多少被抓到） | 1.0 |
| 干净样例误报数 | 0 |
| 真命中 | 60 |
| 误报 | 0 |

## 成本归一（agent 侧）

来源：`agent-local7-r48`（agent-summary）

| 指标 | 值 |
|---|---|
| 样本数 | 7 |
| resolved | 7 |
| 完整性拦截 | 0 |
| 补丁结构损坏 | 0 |
| 单次中位耗时（秒） | 36.625 |
| 中位编码轮数 | 3.0 |
| 中位编辑数 | 1.0 |
| 每个 resolved 墙钟成本（秒） | 63.449 |
| tokens | N/A（host 后端不暴露 token 用量，如实留空不猜） |

成本口径：agent-summary 的墙钟只含编码循环，gold/deepswe 含环境准备与评测开销；都不等于模型算力；中位数只描述这一批样本。

## 合并率抽检

- 范围：SWE-bench Lite（历史 agent 补丁 20 例，取每例最终版本）
- 评审人：dev-agent（agent 初筛，按固定判据逐例读补丁）；人工复核：pending
- 抽检 20 例：resolved 18，可合并 18（合并率 0.9）
- 测试通过且可合并：18（0.9）；测试通过但不可合并：0
- 驳回原因：{"incomplete_fix": 2}
- 局限：C3/C4 为 agent 逐例初筛，人工复核待办；判据与逐例备注可复查，结论不是人工评审
- 局限：样本来自单一仓库集（SWE-bench Lite Python），不外推到其他语言/仓库
- 局限：mergeable 指按上述判据「可提交评审」，不代表上游一定合并
- 局限：判定来源不一致已标注：eval19 与 caliber 对 sympy-13437 的结论不同，按补丁同一性核验后取 gold-v6 跑次；caliber 的 source_runs 未列 gold-v6，对账遗留（round-48 发现，未改证据文件）

## 引擎信息

- 内容指纹：`b27a9346f9e4a8679e9a995300f496656d61b8577a41365e17e51c0a357d6fad`
- 污点汇点：4 个 / source：5 个（taint-config.json，总监治理）
- 跨文件两遍分析：taint-cross.py（顶层函数摘要 + 调用方追踪）

## 方法论

- 判分：命中 ground-truth ±1 行计入；weak 样本（gt 标识符不足）剔除分母并单列
- 正/负样例对称生成；clean 样例零误报为回归下限

## 局限（如实声明）

- 本报告为确定性评审器口径（38 条硬规则 + 可配置污点引擎），不含真实模型评审
- 合成语料证明「报出的都是真的」；真实语料测量「规则类覆盖了哪些真实缺陷」，两者互补
- 污点引擎覆盖：同文件直线传播 + 跨文件两遍分析（顶层函数摘要）；无清洗点建模
- 判分口径：命中 ground-truth ±1 行计入；单文件 gt 标识符不足的 weak 样本剔除分母

## 复现

```
py skills/eval-harness/scripts/precision-report.py --count 120 --out <目录> --cost-report reports/evals/eval-cost-report-agent-local7-r48-2026-10-28.json --merge-audit reports/swebench/merge-audit-r48.json
```
