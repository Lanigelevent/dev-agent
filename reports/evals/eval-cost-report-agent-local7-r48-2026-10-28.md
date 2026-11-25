# 评测成本归一报告（2026-10-28 · agent-summary）

输入：`reports\_work\r48\agent-eval-local7\agent-sample-summary.json`

## 结果

| 指标 | 值 |
|---|---|
| 样本数 | 7 |
| resolved | 7 |
| unresolved | 0 |
| 未判定（失败/未评） | 0 |
| 完整性拦截 | 0 |
| 补丁结构损坏（截断/无法应用） | 0 |
| resolved 率 | 1.0 |

## 成本（墙钟秒）

| 指标 | 值 |
|---|---|
| 单次中位耗时（全样本） | 36.625 |
| 单次中位耗时（resolved） | 36.625 |
| 单次中位耗时（unresolved） | None |
| 总耗时 | 444.14 |
| 每个 resolved 的墙钟成本 | 63.449 |
| 中位编码轮数 | 3.0 |
| 中位编辑数 | 1.0 |

## token

- N/A：host 后端不暴露 token 用量，如实留空不猜

## 局限（如实声明）

- elapsed_sec 是所记链路的墙钟秒（agent-summary 只含编码循环；gold/deepswe 含环境准备与评测开销），不等于模型算力
- 中位数只描述这一批样本；样本量小，不构成稳定性或跨模型结论
- token 仅当产物带用量时汇总；host 后端标 N/A，不用字符数估算
- 本报告不重算判分：resolved 直接取原台账/汇总的判定
- integrity_flagged 与 malformed_patch 不计入 resolved 分母，单列计数

## 复现

```
py skills/eval-harness/scripts/eval-cost-report.py --input reports\_work\r48\agent-eval-local7\agent-sample-summary.json --out reports\evals --label agent-local7-r48
```
