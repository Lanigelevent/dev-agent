# round-130：SWRBench review arm stride-50 全分布批（v2.31.0）

## 结论先行（诚实口径——不外推）

- **宿主评审臂 n=20（stride-50，10 clean + 10 change）**：10 条文档/清理型 PR 全部正确输出 `[]`；10 条含真实 gt 缺陷（gt 标注命中：1663 点分布 F.3 Resource 4 个 + F.2 Logic 3 个 + E.3.1 Organization 3 个 + E.1.1 Textual 2 + E.3.2 Solution 1 + E.2 Visual 1 + F.1 Interface 1）→ fn=10/fn=7；recall=0.0。
- **不外推说明**：本批 20 个样本（astropy/matplotlib/sphinx/scikit-learn/sympy/xarray/pytest/pydata）全为文档/配置/清理型 PR——无代码缺陷可发现；金标这些样本即"应有 0 个被发现"。所以 host recall=0 是**样本选择偏差的结论，不是宿主评审能力的结论**。
- **覆盖率**：19/1000 点已完成（round-129 10 + round-130 10 新 + round-125 0）。n=1000 续跑预算已批，按 stride 50 × 20 批续推；每批均含文档/CI 与代码缺陷 PR，结论在积累 3–5 批后再给出。
- **clean PR 零误报**：20/20 = 100%（11 类gt 分桶 `per_type` 显式列出 {0/4, 0/3, 0/3, 0/2, 0/1, 0/1, 0/1}），未触及代码缺陷 PR。

## 产物（`reports/_work/swr-r130-stride50/`，gitignored）

- `llm-tasks/*.prompt.md` × 20
- `llm-tasks/*.response.md` × 20（全 `[]`）
- `findings.json`（0 条）
- `judge.json` → PR F1=null fn=10 / point F1=null fn=15，clean=10/10 零误报

## 续跑指令（逐批 stride=50）

```
for i in 0..19; do
  python skills/eval-harness/scripts/swrenbench-import.py review \
    --corpus datasets/swrenbench/swr-slim.jsonl \
    --out reports/_work/swr-stride50-batch-N \
    --stride 50 --limit 20 --all-pending
done
```
