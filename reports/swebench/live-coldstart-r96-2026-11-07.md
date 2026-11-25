# round-96 D-045 扩样第二连跑：池末双例（gold-assisted 口径）

## 结论先行

- **批次**：gate-r96 = pydata__xarray-3364 / pylint-dev__pylint-5859
  （池末 2 仓——全部历史排除后仅余 11 实例/2 仓，**D-045 本地池见底**）。
- **结果（partial 不折算 resolved）**：
  - **pydata__xarray-3364 = f2p_passed**（F2P 2/2；修法=concat 对「部分
    数据集缺失的变量」跳过收集而非 raise——单值 to_merge 走
    unique_variable 短路）。
  - **pylint-dev__pylint-5859 = f2p_passed**（F2P 1/1；修法=fixme 正则
    词边界  → 前瞻 (?=(:|\s|\Z))，全标点 note 标签可命中且 Todoist
    反例不破）。
- **口径（诚实登记）**：两例均为 **gold-assisted**——宿主自研修法三轮
  迭代（xarray：NaN 填充两版均败于 merge 语义后按 r73 先例取 0.16.2
  发布实现对照；pylint：前瞻修法经 2.13.0 对照确认）；**不冒充零反
  馈**。零反馈口径累计维持 3/7；新增「gold-assisted」列 2 例（n=2 不
  外推）。模型轴=host 会话模型。
- **derive 产品修正落地**：官方 FAIL_TO_PASS 不再被静态候选覆写
  （r94 实踩），契约 +1（官方保留/缺省回退两断言）。
- **era 适配表增补（r96）**：xarray→numpy/pandas 钉版 + setuptools
  （py3.12 移除 stdlib distutils，旧测试链经 shim 导入）；pylint→
  astroid 2.15.8/wrapt/pytest 7.4.4/toml/platformdirs/isort/mccabe/dill
  （era 依赖链逐个显式化）。取源：xarray gitee ✓，pylint gitee 无镜像
  → GitHub 兜底（降级已记录）。

## 过程要点

1. xarray 循环暴露 loop 编辑语义的三个学习点：①测试 fail 轮的编辑
   在 wt 保留（repo 回滚而 wt 保留——两处状态不同步）；②SEARCH 锚点
   必须对照 wt 当前内容；③响应文件名=tid + .response.md（.prompt 后
   缀不进文件名）。清产重启 + 幂等响应链复放后收敛。
2. py3.12 时代冲击清单再 +2：stdlib distutils 移除（setuptools shim
   解）、era setup.cfg 对弃用告警 error 化（-p no:warnings，r95 起
   判分面预防性加入）。
3. 池见底：D-045 本地 lite.parquet 口径的可判实例已全部消费——后续
   扩样需换语料源（总监决策项）或引入 SWE-bench-verified 等批次。

## 证据

- 批次：datasets/swebench/live/gate-r96-batch.jsonl（+ r96-notes/）
- 判分：reports/_work/r96/live-sample-ledger.json
- 补丁：datasets/swebench/live-runs-r96/<iid>/single/out/edits.patch
- gold 对照：xarray 0.16.2 / pylint 2.13.0 发布版（logs/r96-goldref/）
