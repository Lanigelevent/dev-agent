# round-62 评审精度护栏实跑（ReviewBench 固定语料）

| 基准 | 样本量 | 判分口径 | 成本 | 完整性告警 |
|---|---|---|---|---|
| ReviewBench（MIT）python 子集（`datasets/reviewbench/samples-py.json`） | 12 样例 = **11 valid + 1 weak**（weak 剔除分母，与 reviewbench-eval 同口径） | deterministic 评审器；golden 只取 `tp_fp=="tp"` × `introduced-by-pr`；precision=grounded/claimed、recall=hits/valid；护栏四项 = precision ≥0.65 / ≥基线−0.01 / valid_samples 一致 / reviewer 一致 | 单次 `run` 墙钟 **2.234 秒**（单机本地，含 prepare+run+judge） | 0（prepare `problems=[]`；1 条 weak 如实计入样本量） |

## 结果（PASS）

- precision **0.6667**（4 grounded / 6 claimed）、recall **0.3636**（4 hits / 11 valid）、
  claimed 6 / grounded 4 / hits 4 / weak 1——与
  `reports/reviewbench-precision-2026-10-27.json`（round-36）**同值**，规则经 round-61
  闭包豁免改动后精度未漂移。
- 基线：`skills/eval-harness/precision-baseline.json`（floor 0.65、tolerance 0.01）；
  判定明细 `gate.json`、`judge.json`（每样本 claimed/hit/matched 可复算）。

## 反向验证（四类失败各一，均 rc1）

| 变体 | 期望状态 | 实测 |
|---|---|---|
| 基线 floor 0.9 | BELOW_FLOOR | ✅ `precision_floor` 唯一失败 |
| 基线 precision 0.75 | DRIFT | ✅ `precision_trend` 唯一失败 |
| 基线 valid_samples 12 | SAMPLE_DRIFT | ✅ `sample_drift` 唯一失败 |
| 基线 reviewer host | REVIEWER_MISMATCH | ✅ `reviewer_match` 唯一失败 |

另：缺语料 `run` → rc2（`语料目录不存在`），不伪造 PASS。产物见 `reverse/`。

## 口径边界

- 语料不入库（`datasets/` 被 .gitignore），门禁在本地/发布签核跑，**不进 CI**；
  缺失时 code=2 明示。n=12 小样本，precision 粒度 1/6，只能防显著回退与形态漂移。
- 该护栏不替代人工复核补丁合并性（`merge-audit` 的 `human_review` 仍 pending）。

## 复跑

```
.venv/Scripts/python.exe skills/eval-harness/scripts/precision-gate.py run \
  --corpus datasets/reviewbench --out reports/_work/precision-gate-r62
.venv/Scripts/python.exe skills/eval-harness/scripts/precision-gate.py check \
  --judge reports/_work/precision-gate-r62/judge.json
```
