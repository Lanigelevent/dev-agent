# round-73 冷启动第 5 数据点：pvlib-2249 零反馈 f2p_passed（首个零反馈收敛）

日期：2026-10-31 ｜ 版本：v1.74.0 ｜ 状态：**pvlib-2249 f2p_passed（零反馈，4 轮/1 编辑/968 B，F2P 7/7）——对照测量：零反馈 1/4、带反馈 1/1**

## 结论

**冷启动首个零反馈收敛数据点**：pvlib-2249（`julian_day_dt()` 对 NREL
A4.1 表的前格里历日期计算错误）零反馈编码跑 **f2p_passed**——编码循环
4 轮 / 1 编辑 / 补丁 968 B，判分 F2P 7/7 PASSED（87.328 s，partial 口径
不计 resolved）。

- 修复内容：`pvlib/spa.py` 的 `julian_day_dt` 把格里历修正
  `b = 2 - a + int(a*0.25)` 无条件应用——837 年等前格里历日期属儒略历应
  `b=0`（报告的 2026867.8 vs 期望 2026871.8 恰差 b=-4）；修法为仅在
  1582-10-15 及之后应用修正（原始月序参与边界比较，兼容 month<=2 的
  年月调整）。
- **round-69/72 两项结构改造的直接验证**：①符号锚定取窗——第 2 轮
  `spa.py#julian_day_dt` 一次拿全函数体（16 行全可见），零盲区；②
  PENDING 指针——宿主第 7 次 stale-id 被指针即时暴露并当场纠正（cp 一次
  归位），未浪费编码轮次。
- **宿主探索策略修正生效**：首轮定向搜索、第 2 轮全函数覆盖、第 3 轮即
  编辑（对照 round-68 attempt-1 的 11 轮 0 编辑）。

## 1. 冷启动对照测量（D-045 数据面板，全部可复算）

| 实例 | 反馈 | 尝试 | 结果 | 失败/成功形态 |
| --- | --- | --- | --- | --- |
| pvlib-2249 | **零** | 1 次（4 轮/1 编辑） | **f2p_passed**（F2P 7/7） | 算法修正条件化（13 行级，教科书形态） |
| llama_deploy-330 | 零 | 2 次（重试用尽） | failed | 事件路由语义不可推导（5 文件/128 行） |
| pdm-3237 | 零 | 1 次（重试后带反馈再试） | failed / unresolved | CLI 签名改造（75 行） |
| conan-17092 | 零 | 1 次 | failed | settings 枚举 + 旗标表重构（41 行） |
| keras-20389 | attempt-2 带判分反馈 | 2 次 | **f2p_passed**（F2P 1/1） | 双 raise 异常类型对齐（2 行） |

**口径（如实）**：零反馈 1/4（pvlib ✓）、带反馈复修 1/1（keras）——
n 均为 1，二项区间极宽，不作成功率宣称；pvlib 的 PS 含 NREL 表链接与
期望值（任务固有材料），修复面为教科书级算法条件化，难度偏易因素如实
标注。f2p_passed 为 partial 口径（pvlib P2P 1177 条含 9 条上游截断 id，
完整 resolved 不可得）。

## 2. 执行记录

- 编码循环：4 轮（search → 符号读 → edit → done）/ 1 编辑 / 968 B，
  D-045 预算内（≤45min 墙钟仍超，宿主往返延迟如实记录；≤20 编辑用 1）。
- 判分：live-sample predictions f2p-only，87.328 s，F2P 7/7 PASSED、
  0 missing。
- PENDING 指针：第 7 次 stale-id 即时暴露（指针与已写 id 不符 → cp 归位，
  零轮次损失）——round-72 结构改造的价值在首次真实使用中兑现。

## 3. 证据与复跑

```
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r68-pvlib-python.jsonl --mode predictions \
  --f2p-only --predictions datasets/swebench/live-runs-r72/predictions-pvlib-2249.jsonl \
  --out datasets/swebench/live-runs-r72/live-judge-pvlib \
  --source-root datasets/swe-repos --no-network --force
```

产物：`datasets/swebench/live-runs-r72/coldstart-pvlib-2249/`（4 轮/1 编辑）、
判分台账 `live-judge-pvlib/live-sample-ledger.json`。

## 4. 边界（不宣称的部分）

- n=1 零反馈收敛不外推（对照面板的另一半是 3 个 failed——失败形态全部
  指向「多文件 API 改造」类修复面）。
- f2p_passed 不计 resolved（partial 口径）。
- gold patch 全程未读；本修复与上游 gold 的相似度未知，判分只证 F2P 全过。
