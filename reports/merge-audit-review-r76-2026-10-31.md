# round-76 merge-audit 人工复核销账 + 在账长项盘点（v1.77.0）

日期：2026-10-31 ｜ 状态：**merge-audit 5/5 复核完成（schema 2，28 轮挂账销账）；Pro 单发 blocked 确认（无固定端点）；镜像面刷新仍不可达**

## 结论

1. **merge-audit 人工复核完成（reports/swebench/merge-audit-r48.json，
   schema 1→2，human_review pending→done）**——round-48 挂账、next-round
   第 20 条追踪 28 轮的 5 例判定：
   - **3 例 mergeable_with_nits 全部可合并**：
     - astropy-14182：nit（header_rows 父类兜底）属可维护性建议，不阻塞；
     - scikit-learn-13241：nit（random_state=None→0 改变随机语义）为实质
       变更但属稳定性测试常见做法——**合并须在提交说明与文档中显式交代
       语义变更**（文档义务，非代码阻塞）；更保守替代（只做符号归一）留
       作后续选择；
     - sympy-13146：nit（helper 内联重建）只影响微小性能与单测便利性。
   - **2 例 not_mergeable 的 incomplete_fix 归因均被后续 resolved 实证
     成立**：astropy-14365（round-63 第 6 版官方容器 resolved，F2P 1/1、
     P2P 8/8——「需按数据段单独归一」的修复面判断准确）；django-11019
     （round-64 第 3 版 resolved，F2P 16/16、P2P 58/58，与上游字节级
     一致——「属修错而非坏补丁、需重做合并算法」判断正确）。
   - merge_rate 0.9 维持（nits 可合并口径不变）。
2. **Pro 固定端点「单发」口径：blocked 确认**——REVIEW_LLM_BASE_URL /
   REVIEW_LLM_MODEL 未配置、agent.json 无端点参数；单发口径需固定端点
   （总监决策项：提供 API 端点 + 模型后即可按 D-030 分离口径跑）。
3. **镜像面刷新（今日实测）**：hub.docker.com 连接被强关、registry-1
   超时——DeepSWE 余 19 条 blocked 维持、Live/D-045 resolved 口径维持。
4. **D-046 4.1 复验：预算未批不动**（跨模型端点或 n≥10 语料，维持 ◐）。

## 1. 复核明细（逐例判定见 merge-audit-r48.json verdicts[].human_review）

| 实例 | r48 判定 | 复核结论 |
| --- | --- | --- |
| astropy-14182 | mergeable_with_nits | **acceptable**（nit 不阻塞） |
| scikit-learn-13241 | mergeable_with_nits | **acceptable_with_followup**（语义变更须文档交代） |
| sympy-13146 | mergeable_with_nits | **acceptable**（nit 不阻塞） |
| astropy-14365 | not_mergeable（incomplete_fix） | **confirmed**（round-63 resolved 实证） |
| django-11019 | not_mergeable（incomplete_fix） | **confirmed**（round-64 resolved 实证） |

## 2. 在账长项终态盘点

| 长项 | 状态 | 依赖 |
| --- | --- | --- |
| merge-audit 人工复核 | ✅ 本轮销账 | — |
| Pro「单发」口径 | blocked | 固定端点（总监决策） |
| DeepSWE 余 19 条 | blocked（今日刷新） | 镜像可达性 |
| D-046 4.1 复验 | 未动（按判据） | 跨模型端点或 n≥10 预算 |
| reflex / instructlab | blocked | reflex 自身 bug / Python<3.12 |
| D-045 扩样 | 收束（round-75） | 换语料批次（总监决策） |

## 3. 边界（不宣称的部分）

- 复核人以「总监全权委托的 delegated-reviewer」身份执行，判定依据逐例
  记录于 verdicts[].human_review.judgment 可复查；非独立第三方评审。
- 13241 的 acceptable_with_followup 是有条件判定：合并前文档义务须履行。
- 2 例 confirmed 依赖 round-63/64 的 resolved 事实（官方容器判分，可复算）。
