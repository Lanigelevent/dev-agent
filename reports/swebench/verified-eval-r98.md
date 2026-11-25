# SWE-bench-verified 新池评估报告（round-98，D-052 依据）

> **性质**：评估报告（未开跑）｜ **数据**：princeton-nlp/SWE-bench_Verified
> 500 实例（hf-mirror 取数 ✓ 许可 MIT；本地
> datasets/swebench/verified/swe-bench_verified.parquet）

## 1. 数据面

- 500 实例（人工核验过的 Lite 子集），字段与 Lite 同构 + `difficulty`
  列（<15min 15 / 15min-1h 24 / 1-4h 3 / >4h 1——排除后剩余池的分布）。
- 与本地 lite 实例重叠 93；**与历史消费实例（live/*.jsonl 全部）零重叠**。

## 2. 排除口径——本评估的核心裁定项

r94 起的仓级排除（agent 口径仓 astropy/django/pytest-dev/scikit-learn/
sphinx-doc/sympy + matplotlib/urllib3）在 verified 上**排除 457/500**
（django 231 + sympy 75 + sphinx 44 + matplotlib 34 + sklearn 32 +
astropy 22 + pytest 19 全部出局）→ 仅余 43 实例/5 仓，且这 5 仓正是
r94/r96 已演练过的仓型（xarray/pylint/requests/seaborn/flask）——
**边际价值低**。

三档口径供裁定：

| 档 | 排除规则 | 可用池 | 评估 |
|---|---|---|---|
| 严（现状） | 仓级（agent 口径仓） | 43 / 5 仓 | 边际价值低 |
| **中（建议）** | 实例级（历史消费实例）+ 仓级仅排 matplotlib/urllib3 | **~447 / 12+ 仓** | 实例与历史零直接重叠；仓重叠带来 era 适配表复用红利（django/sympy 适配经验已沉淀） |
| 松 | 无排除 | 500 | 与 agent 口径同实例风险（93 个与 lite 重叠者已核销过） |

## 3. 判分链适配评估

- 官方 verified 判分=容器 harness；本项目 live-sample 走 **venv+era 适配
  表**（r94/r96 已验证通路）。django/sympy 等仓的 py3.12 时代冲击
  （distutils 移除、era setup.cfg、旧 pytest 内部 API）有 r94/r96 对策
  沉淀，但**逐仓适配成本仍显著**（r96 xarray/pylint 各 3-5 轮适配）。
- f2p-only 口径继续适用（P2P 上游截断缺陷不变）。
- 预计适配折损：首批 n=10 中 env_blocked 率可能 30-50%（django 旧版
  在 py3.12 的构建失败面）——如实记 blocked 不补位。

## 4. 建议方案（待总监批）

- **口径**：中档（实例级排除 + mpl/urllib3 仓级）。
- **首批**：n=5，选 difficulty ∈ {<15min, 15min-1h} 且 problem_len
  ≤2500 的最小修复面实例（确定性选法照 r94）。
- **预算**：≤45min/实例、≤20 编辑、≤1 重试（D-045 原口径）；模型轴
  =host 会话（r94 同轴）或总监另供端点。
- **开跑轮次**：round-99（评估获批后）。
