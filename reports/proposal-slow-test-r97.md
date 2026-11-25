# e2e 慢项瘦身提案（round-97，待总监裁决）

> **性质**：提案（未实施）｜ **依据**：round-91 画像 + round-97 复测
> （logs/pytest-durations-r97.log，603 项 / 总 call 419.8s / 全量 432.9s）

## 现状（r97 复测）

top 慢项全部为**多步异构 e2e 流程**（每项 5-9 个串行子进程步骤，
r91 静态扫描 run()×7-9）：

| 慢项 | 时长 |
|---|---|
| TestDualReviewer::test_host_mode_pause_and_resume | 18.4s |
| TestOptimizations::test_runner_material_redacted_in_prompts | 16.1s |
| TestImageFetch::test_fetch_redirect_strips_auth | 13.4s |
| TestOptimizations::test_runner_e2e | 12.2s |
| TestOptimizations::test_runner_feedback_loop | 10.5s |

top-15 合计 ~140s（占 33%）。D-049 C 的「循环合并」杠杆**不适用**
（步骤各异构命令，非同脚本矩阵）；smoke 清单已隔离 CI 时长
（383 项 <0.5s，19.2s 口径），full 仅在 nightly/发布闸。

## 选项

- **A pytest-xdist 并行**：预计 432s → ~120-180s（2-4 worker）；
  代价=新 dev 依赖（pytest-xdist，MIT）+ 需审计夹具隔离
  （tmpspace/共享夹具单例在并行下的正确性需专项验证）+ CI 两平台矩阵
  回归。提案：round-100 依赖刷新专属轮一并裁决（同轮装新依赖成本最低）。
- **B 维持现状**：零成本；smoke 已保 CI 体验，full 时长由负载主导
  （D-041 观测线语义），600s 挂死护栏未触发。
- **C e2e 步骤合并**：不可行——各步骤断言依赖前序产物，合并会破坏
  失败定位粒度（round-45 画像同结论）。

## 建议

**B 维持现状 + A 列入 round-100 议程**（与依赖刷新同轮裁决，避免
单独一轮的开关成本）。
