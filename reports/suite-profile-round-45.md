# 全量套件计时画像（round-45）

- 台账条目：`fe97d747b691`（401 项两次 338.617 / 329.185 秒连续超 300 秒红线）
- 目的：定位 round-43（398 项，283.616 / 298.379 秒）到 round-44（401 项，
  338.617 / 329.185 秒）之间 35–55 秒增量，判断「收敛慢测试」还是「红线不适用」，不悄悄改线。
- 结论先行：**没有单点异常用例；耗时随用例数近似线性，并被机器负载大幅放大
  （同一份代码连跑 292s / 370s / 298s，极差 78s）**。已做一项无损收敛（快照副本
  瘦身，实测每次复制 6.01s→1.03s），红线是否调整留待总监决定（本报告只出证据与
  提案，未改线）。

## 方法

- 逐用例计时：`unittest.TextTestResult` 子类在 `startTest/stopTest` 打点，
  `discover(tests)` 全量跑，输出 `by_module / by_class / slowest 40`。
- 快照成本：以当前与拟改的两份 `SNAPSHOT_IGNORE` 各做一次 `copytree(ROOT→系统 temp)`，
  统计耗时、条目数、体积，跑完自删。
- 全部数字由下列命令实跑取得（可直接复算）：

```bash
.venv/Scripts/python.exe reports/_work/profile_suite.py > reports/_work/profile-suite.json 2> reports/_work/profile-suite.err
.venv/Scripts/python.exe reports/_work/measure_snapshot.py
.venv/Scripts/python.exe -m unittest discover -s tests
```

## 画像数据

全量 401 项（1 skip，0 fail / 0 error），画像总耗时 **318.507s**，平均 **0.794s/项**。

### 按模块

| 模块 | 耗时 | 用例数 | 平均 |
|---|---:|---:|---:|
| test_scripts | 134.75s | 158 | 853ms |
| test_dual_reviewer | 37.98s | 6 | 6330ms |
| test_agent | 29.36s | 66 | 445ms |
| test_repair | 25.87s | 10 | 2587ms |
| test_engines | 13.84s | 24 | 577ms |
| test_testgen | 11.76s | 6 | 1960ms |
| test_interop | 10.14s | 18 | 563ms |
| test_taint | 7.81s | 13 | 601ms |
| test_approval | 7.76s | 7 | 1109ms |
| test_director | 7.46s | 32 | 233ms |
| test_retro | 5.89s | 24 | 246ms |
| 其余 5 个模块 | 6.05s | 37 | — |

### 按类（前 12）

| 测试类 | 耗时 |
|---|---:|
| test_scripts.TestOptimizations | 47.47s |
| test_dual_reviewer.TestDualReviewer | 37.98s |
| test_repair.TestRepair | 25.87s |
| test_scripts.TestImageFetch | 22.57s |
| test_scripts.TestEval | 16.80s |
| test_agent.TestPatchInstantValidation | 12.97s |
| test_scripts.TestGuardrails | 10.72s |
| test_interop.TestInterop | 10.14s |
| test_scripts.TestSelfIteration | 9.93s |
| test_scripts.TestScannerFalsePositives | 9.39s |
| test_testgen.TestTestgen | 8.17s |
| test_approval.TestApproval | 7.76s |

### 最慢 10 项

| 耗时 | 用例 |
|---:|---|
| 14.71s | test_dual_reviewer.TestDualReviewer.test_host_mode_pause_and_resume |
| 14.55s | test_scripts.TestOptimizations.test_runner_material_redacted_in_prompts |
| 12.79s | test_scripts.TestImageFetch.test_fetch_redirect_strips_auth |
| 10.98s | test_scripts.TestOptimizations.test_runner_e2e |
| 9.53s | test_scripts.TestOptimizations.test_runner_feedback_loop |
| 8.42s | test_repair.TestRepair.test_per_rule_reversal |
| 7.74s | test_scripts.TestScannerFalsePositives.test_self_scan_zero_hits |
| 7.69s | test_scripts.TestOptimizations.test_self_scan_zero_fp |
| 7.44s | test_scripts.TestGuardrails.test_experience_cap_and_levels |
| 6.71s | test_scripts.TestEval.test_fingerprint_stable_and_sensitive |

分布：最慢 40 项合计 **208.4s**，占 65.5%；其余 361 项合计约 **110.1s**
（其中含 `setUpModule` 等 start/stop 之外的开销），平均上限 0.305s/项。
**单项上限 14.71s，没有任何一项达到可单独解释 35–55 秒增量的量级。**

### 为什么是线性成本

- 套件共约 460 次 `run()` 子进程调用（`tests/test_scripts.py` 158 项即 134.75s），
  每次 Python 解释器启动约 79ms，叠加脚本自身的 git/diff 操作——这是每项 0.3–0.9s 的地板。
- `round-44` 只新增 3 项契约测试（入册器过滤 / 归档 / 轮报三态），每项约 0.2s，
  **合计 ~0.6s，无法解释 35–55s**。
- 同一份 401 项代码：round-44 两次 338.617 / 329.185s，本次画像 318.507s，快照
  瘦身后三跑 292 / 370 / 298s——**极差 78s，比 round-43→44 的 35–55s 增量还大**；
  即负载波动足以完整覆盖该增量，不能把 35–55s 归因于 +3 项测试。
- 按本次画像 0.794s/项折算，300s 红线约等于 **378 项**规模；当前 401 项已超
  23 项，叠加负载波动后红线更难稳定满足——是口径与规模/环境不匹配，而非某条
  测试变慢。

## 本轮已落地的无损收敛

`tests/test_scripts.py` 的 `snapshot_repo()` 原先会把 `reports/`（含 `_work`
探针产物）与 `skills/eval-harness/data/` 一起拷进临时副本。这既不必要（两个调用方
——fingerprint 对比与 doc-drift 注入——都不读这些目录），也把「本机工作树碰巧
有什么」混进本应只看源码树的门禁口径。

- 实测（`measure_snapshot.py`）：

| 口径 | 耗时 | 条目 | 体积 |
|---|---:|---:|---:|
| 现状 | 6.01s | 8129 | 77.6MB |
| 排除 reports/retro/runs/llm-tasks/data | 1.03s | 1675 | 2.4MB |

- 两次快照测试合计约省 **10s**；同时与 `fingerprint.py` 的 `skip_dirs` 口径对齐。
- 反向验证：`test_fingerprint_stable_and_sensitive` 增加断言——快照不得含上述
  运行产物目录与 gate 语料；三个受影响用例（fingerprint×1、doc-drift×2）实跑
  通过，指纹与漂移结论不变。用例总数仍为 401。

### 瘦身后连续三跑复测（同一份代码）

```bash
.venv/Scripts/python.exe -m unittest discover -s tests   # 连跑三次
```

| 跑次 | 结果 | 耗时 |
|---|---|---:|
| run1 | 401 项全绿（RC=0） | **292s**（低于 300s） |
| run2 | 401 项全绿（RC=0） | **370s**（超线 70s） |
| run3（v1.46.0 收官，文档/版本已定） | 401 项全绿（RC=0） | **298s**（低于 300s） |

日志：`logs/suite-r45-run1.log`、`logs/suite-r45-run2.log`、
`logs/suite-r45-final.log`。
**同一份代码连跑三次落在 292–370 秒（极差 78s，27%）**——这比 round-43→44
的 35–55s 增量更大，直接说明总时长由机器负载/跑间抖动主导，与用例增减基本无关。
也说明「连续两次超线」的判定在当前机器上并不稳：三次中两次未越、一次越 70s。

## 红线结论与提案（需总监批准，未改线）

在「不改产品行为、不删测试」的前提下，按总时长判定 300s（乃至 360s）对
当前机器与 401 项规模都不是稳定信号。候选：

| 方案 | 内容 | 代价 | 备注 |
|---|---|---|---|
| A 保持 300s | 沿用「连续两次同负载超线才升级」 | 292/370/298 三跑已证明连跑可差 78s，会持续误报 | 现状，不推荐长期 |
| B 总预算 300→360s | 简单加 60s | 370s 负载下仍越线，只降低误报频率 | 次选 |
| C 总时长改为监控指标 + 挂死护栏（推荐） | 总时长每轮记录趋势；硬护栏 600s；保留单项 60s 预算；连续 3 次 >450s 或单项 >60s 才升级 | 放弃「总时长硬红线」，靠趋势与单项预算兜底 | 需批准 |
| D 快慢双道 | 默认快道 ~110s（排除最慢 40 项），提交/CI 全量并记录总时长 | 流程复杂化，需维护慢项清单 | 可与 C 组合 |

建议：**C（总时长降级为观测指标 + 600s 挂死护栏 + 单项 60s 保留）**，
如仍希望保留一道总时长闸，则取 **B+C 组合**（360s 作为告警线而非阻断线）。
本报告不修改任何门禁数值；批准后再同步 `AGENTS.md` / `docs/DEVELOPMENT.md` /
`README.md` 的红线口径与 tests 说明。

## 附：可复算的入口

- 画像原始 JSON：`reports/_work/profile-suite.json`（一次性产物，不入库）
- 快照测量原始 JSON：`reports/_work/measure-snapshot.json`（一次性产物，不入库）
- 计时脚本：`reports/_work/profile_suite.py`、`reports/_work/measure_snapshot.py`
