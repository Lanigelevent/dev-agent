# AB-04 Harbor 三件套概念映射（r207，2026-11-21）

> 对照源：Harbor 7.2k（任务/求解器/验证器三件套 + 矩阵并行 + 缓存）。
> 审计对象：eval-harness 评测链（forward-bench.py / reviewbench-eval.py / run-samples.py）。

## 一、Harbor 三件套 → eval-harness 逐面映射

| Harbor 角色 | Harbor 实现 | eval-harness 对应 | 判定 |
|---|---|---|---|
| **Task**（任务包：语料+环境+预期） | 任务格式抽象（含 Docker 镜像+验证器） | `prepare` 动词：forward-bench prepare / reviewbench-eval prepare / collect-samples | **已对齐** |
| **Solver**（被评 agent 求解） | Agent×环境×模型矩阵并行 | `run` 动词：reviewbench-eval run（逐样本跑评审器）/ run-samples（批量跑分）/ gate-run（编码循环实跑） | **已对齐** |
| **Validator**（判定器：pass/fail 或 F1） | 验证器判分 | `judge` 动词：forward-bench judge / reviewbench-eval judge（F1 双指标）/ precision-gate / review-quality-gate | **已对齐** |

## 二、动词三段式 = 三件套同型

评测链所有脚本已按 **prepare → run → judge** 三动词结构组织——与 Harbor 的 task/solver/validator 三件套**同型对齐**。命名差异仅是动词名（prepare vs task、run vs solve、judge vs validate），不改也能精确映射。

## 三、矩阵并行与缓存差距

| Harbor 能力 | eval-harness 现状 | 差距判定 |
|---|---|---|
| Agent×环境×模型矩阵并行 | 单链顺序跑分（xdist 仅用于测试） | **真实差距**——但当前评测量（n≤1000）未达需要矩阵并行的规模 |
| 跨 run 缓存 | 确定性评测幂等（同输入同输出） | **已覆盖**（幂等即缓存） |
| 统一 runner 入口 | 各脚本独立 CLI（无统一 dispatcher） | **弱差距**——gate-run.py 已是 gate 口径统一入口 |

**判定**：矩阵并行是真实差距但在当前评测量下 ROI 低；统一入口已有部分覆盖。**三件套概念映射本身已对齐**——命名约定重构（文件改名）从路线图移除（终局：概念已对齐，改名 ROI 不值打破引用面）。

## 四、结论

AB-04（Harbor 三件套重构）判定为**概念已对齐，改名不值得**。eval-harness 的 prepare/run/judge 动词三段式与 Harbor 的 task/solver/validator 同型——命名差异仅是术语选择，不构成功能差距。矩阵并行留观察（评测量增长后启动）。

与 AB-07/12/13/15/17/21 审计同类：**已有对齐零缺口**。
