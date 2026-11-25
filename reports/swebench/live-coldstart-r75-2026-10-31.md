# round-75 gold 对照校准 + D-045 语料边界收束：归因双双证实

日期：2026-10-31 ｜ 版本：v1.76.0 ｜ 状态：**gold 对照实验完成（pvlib 语义等价 / haystack 跨层判断精确）；九候选语料见底，能力边界如实收束**

## 结论

1. **gold 对照实验（判分侧，冷启动已完、口径分离）**：从 lite.parquet 提取
   两例 gold patch 与本轮补丁逐点对照——
   - **pvlib-2249（零反馈成功）**：gold 修法为
     `jd = ...- 1524.5; if jd > 2299160.0: jd += b`（2299160.0 = 1582-10-15
     的儒略日数）——与本轮的日期元组条件化**语义等价**（同 bug、同修点、
     不同等价机制）。「零反馈成功非运气」得到 gold 实证。
   - **haystack-8489（零反馈失败）**：gold 恰为给 `trace()` 全链路加
     `parent_span: Optional[Span]` 参数——ABC（tracer.py）+ 三实现
     （datadog/logging_tracer/opentelemetry）+ pipeline.py 调用点传参，
     6 文件与本轮「跨层重构」判断**逐文件吻合**。「跨层重构超出单点零
     反馈能力」的归因被 gold 结构证实（gold 用显式 parent_span 线程化
     而非 contextvar——机制细节与本轮推测不同，但面完全一致）。
2. **D-045 语料边界收束（如实）**：九候选全部走完——4 条可信判分链跑完
   冷启动（n=6 对照面板：零反馈 1/5、带反馈 1/1）、2 条 blocked
   （reflex compat bug / instructlab Python<3.12）、1 条不可判
   （cfn-lint 上游截断）+1 条剔除（matplotlib 仓库级暴露）。**本机资源面
   下冷启动评测能力边界已测得**：失败/成功分界线 = 修复面规模与跨层
   程度（n=6 形态一致）；继续扩样需换语料批次并重走「补源 → 判分链
   gold 验证 → 冻结 → 冷启动」全流程（D-045 协议可复用）。
3. **对照面板终态**（全部可复算）：

| 实例 | 反馈 | 修复面（gold 证实） | 结果 |
| --- | --- | --- | --- |
| pvlib-2249 | 零 | 1 文件代码（+whatsnew） | **f2p_passed**（语义等价修复） |
| keras-20389 | 带反馈 | 1 文件/2 行 | **f2p_passed** |
| conan-17092 | 零 | 2 文件/41 行 | failed |
| pdm-3237 | 零 | 2 文件/75 行 | failed |
| haystack-8489 | 零 | **6 文件/45 行（gold 证实跨层）** | failed |
| llama_deploy-330 | 零 | 5 文件/128 行 | failed |

## 1. 方法论沉淀（冷启动评测的可复用资产）

- **gold 先行验证**（判分链可信前置）三轮兑现；**结构改造双件**（read
  取窗、PENDING 指针）由实跑失败驱动并实战闭环；**gold 对照校准**
  （本轮）为每次失败/成功归因提供可复算的实证——四件构成完整的
  「冷启动评测方法链」，换语料批次即可复用。
- 宿主协议 stale-id 本轮再犯 1 次（PENDING 指针即时暴露、cp 归位）——
  机制持续有效；宿主纪律内化仍靠人。

## 2. 证据与复跑

gold 对照文件：`datasets/swebench/live-runs-r72/gold-compare/`
（pvlib_pvlib-python-2249.patch、deepset-ai_haystack-8489.patch，判分侧
提取自 lite.parquet 的 patch 列）；冷启动产物
`datasets/swebench/live-runs-r72/coldstart-{pvlib-2249,haystack-8489}/`。

## 3. 边界（不宣称的部分）

- gold 对照只校准「归因是否准确」，不改变任何冷启动判分（零反馈 n=5、
  带反馈 n=1 的数字不变）。
- pvlib 修复与 gold 语义等价但实现机制不同（日期元组 vs JDN 阈值）——
  「等价」由 F2P 7/7 全过与公式边界（同一 1582-10-15 断点）共同支撑，
  非逐字对照。
- 「语料见底」限于 D-045 冻结的九候选 + 本机资源面；换批次扩样是
  新决策（需重走全流程，D-045 协议可复用）。
