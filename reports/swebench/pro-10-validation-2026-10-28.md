# SWE-bench Pro 10 条基线 + gold 对照（round-51，2026-10-28）

> 结论先行：同一驱动 `skills/eval-harness/scripts/pro-sample.py` 在 3 仓 10 条
> 实例上全部走通 **baseline_ok → resolved**：ansible 4 条、openlibrary 3 条、
> qutebrowser 3 条；判分点合计 **32 F2P + 269 P2P**。基线 10/10 呈「F2P 全
> 不过、P2P 全过」，gold 10/10 判分点全过。10 张镜像全部本地就位（本轮新拉
> 7 张，合计 5.29 GiB layers，域名一律 `ghcr.nju.edu.cn`）；单条 pytest
> 0.56–21.88 s，容器全流程 1.72–23.91 s。**这是 gold 口径的 harness 对照，
> 不是 agent 能力**（D-028）：agent 侧本轮只有通路代码与回归测试，真实产出
> n=0，不报任何 agent resolved。

## 0. 五列摘要

| 基准 | 样本量 | 判分口径 | 成本 | 完整性告警 |
|---|---|---|---|---|
| SWE-bench Pro v2（Python，gold 对照，非 agent） | 3 仓 10 条（ansible 4 / openlibrary 3 / qutebrowser 3） | 容器内 `before_repo_set_cmd` → 候选补丁 → `pytest -rA <选定文件>` → F2P/P2P 逐 node 对账；SKIPPED/缺失不算过 | 镜像 10 张本地（本轮新拉 7 张 5.29 GiB layers）；baseline 总 pytest 38.078 s / 总 elapsed 61.518 s；gold 13.563 s / 31.688 s | 0（malformed 0 / integrity_flagged 0 / blocked_source 0） |

## 1. 交付物与本轮改动

`pro-sample.py`（治理壳 stdlib-only）本轮修正与增强：

- **`NODE_RE` 支持含空格的参数化 node 与 ` - reason` 后缀**：
  `^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(.+?)\s*$`；`lookup_node`
  增加「去 reason 后缀 + 双向后缀匹配」兜底。此前 `\S+` 会把
  `test_data[Hello World! This is a test.]` 截断，导致 P2P 丢失、基线被误判
  为 `baseline_unexpected`。
- **台账 `--force` 不再覆盖其他行**：无论是否 `--force` 都先读回既有台账，
  `--force` 只影响「目标 key 是否跳过」。修复前单实例 `--force` 会把 20 行
  台账覆盖成 1 行（真坑，见 §5）。
- **agent 侧 predictions 通路**：`--mode predictions --patches <agent补丁根>`
  从 `agent-sample` 的补丁收集器取 `<iid>/edits.patch`，装配
  `predictions-agent.jsonl`，并复用同一套补丁双闸与判分流程，输出与 gold
  分开记账（`patch-provenance.json` 留痕）。真实 agent 补丁本轮未产出
  （无可用 LLM 端点），只完成通路与测试。

回归测试 `tests/test_pro_sample.py` **15 项**全过（新增：参数化 node 空格 +
reason 解析、`--force` 保留其他台账行、agent 补丁 predictions、零 P2P 实跑）。

## 2. 任务与环境

任务清单为 gate 语料（`datasets/swebench/pro/gate-10.jsonl`，不入库）。
镜像原名 `ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`，统一改写为
`ghcr.nju.edu.cn/...`（硬约束 8）。`docker images` 的口径是未压缩虚拟大小。

| 实例（短） | 仓库 | F2P / P2P | 镜像大小 | 任务级适配 |
|---|---|---|---|---|
| ansible `0ea40e09` | ansible/ansible | 1 / 15 | 2.13 GB | —（round-49 拉取并复用） |
| ansible `0fd88717` | ansible/ansible | 4 / 26 | 2.19 GB | `PYTHONPATH=/app/lib` |
| ansible `106909db` | ansible/ansible | 4 / 5 | 2.13 GB | — |
| ansible `11c1777d` | ansible/ansible | 1 / 0 | 2.15 GB | —（零 P2P 合法形态） |
| openlibrary `00bec1e7` | internetarchive/openlibrary | 5 / 15 | 4.20 GB | — |
| openlibrary `03095f26` | internetarchive/openlibrary | 2 / 1 | 4.88 GB | — |
| openlibrary `08ac40d0` | internetarchive/openlibrary | 7 / 119 | 3.26 GB | — |
| qutebrowser `01d1d149` | qutebrowser/qutebrowser | 3 / 46 | 2.47 GB | `Xvfb :99` + `DISPLAY=:99` + `QTWEBENGINE_DISABLE_SANDBOX=1` + `-p no:xvfb` |
| qutebrowser `0833b5f6` | qutebrowser/qutebrowser | 1 / 9 | 2.29 GB | 同上 |
| qutebrowser `0aa57e4f` | qutebrowser/qutebrowser | 4 / 33 | 2.15 GB | 同上 + `QT_QPA_PLATFORM=offscreen` |

三类适配全部写在任务行（`pre_test_cmd/env/pytest_args`），驱动不含实例名：

- ansible 镜像把 `ansible` 装在 `/usr/local/lib/python3.9/dist-packages`，
  会遮蔽 `/app/lib` 的工作树 → `PYTHONPATH=/app/lib` 让 `cd /app` 下的源码
  优先；
- qutebrowser 的 QtWebEngine 在 root + 无 X 环境直接 abort（rc=134），常驻
  `Xvfb :99` + 禁 sandbox 解决；`0aa57e4f` 仍有 xcb 插件初始化失败，追加
  `QT_QPA_PLATFORM=offscreen` 才稳定。

## 3. 结果（基线 → gold）

| 实例（短） | 基线判分 | gold 判分 | pytest 耗时（基线 / gold） | 全流程 elapsed（基线 / gold） |
|---|---|---|---|---|
| ansible `0ea40e09` | F2P 0/1、P2P 15/15 → `baseline_ok` | F2P 1/1、P2P 15/15 → `resolved` | 1.031 s / 0.703 s | 4.703 s / 2.875 s |
| ansible `0fd88717` | 0/4、26/26 → `baseline_ok` | 4/4、26/26 → `resolved` | 1.328 s / 0.937 s | 5.078 s / 3.297 s |
| ansible `106909db` | 0/4、5/5 → `baseline_ok` | 4/4、5/5 → `resolved` | 0.750 s / 0.578 s | 4.391 s / 2.828 s |
| ansible `11c1777d` | 0/1、0/0 → `baseline_ok` | 1/1、0/0 → `resolved` | 0.781 s / 0.563 s | 3.703 s / 2.829 s |
| openlibrary `00bec1e7` | 0/5、15/15 → `baseline_ok` | 5/5、15/15 → `resolved` | 1.687 s / 1.125 s | 2.828 s / 2.219 s |
| openlibrary `03095f26` | 0/2、1/1 → `baseline_ok` | 2/2、1/1 → `resolved` | 1.109 s / 0.718 s | 2.219 s / 1.718 s |
| openlibrary `08ac40d0` | 0/7、119/119 → `baseline_ok` | 7/7、119/119 → `resolved` | 2.657 s / 1.954 s | 3.907 s / 3.047 s |
| qutebrowser `01d1d149` | 0/3、46/46 → `baseline_ok` | 3/3、46/46 → `resolved` | 3.875 s / 3.000 s | 5.844 s / 4.953 s |
| qutebrowser `0833b5f6` | 0/1、9/9 → `baseline_ok` | 1/1、9/9 → `resolved` | 21.875 s / 1.797 s | 23.907 s / 3.750 s |
| qutebrowser `0aa57e4f` | 0/4、33/33 → `baseline_ok` | 4/4、33/33 → `resolved` | 2.985 s / 2.188 s | 4.938 s / 4.172 s |

合计：baseline 10/10 `baseline_ok`（F2P 0/32、P2P 269/269），gold 10/10
`resolved`（F2P 32/32、P2P 269/269）。

判分外残留（如实保留，不影响判分）：qutebrowser `01d1d149` gold 日志里
`1 failed, 97 passed, 5 skipped`，失败项是
`tests/unit/utils/test_version.py::TestModuleVersions::test_existing_attributes[adblock-True]`，
不在该实例 3 条 F2P、46 条 P2P 内（与 round-50 同一现象）。其余 9 条 gold
日志无判分点外失败行。

`0833b5f6` 基线 pytest 21.875 s 明显高于 gold（1.797 s）：Xvfb 常驻 +
QtWebEngine 首次初始化成本落在基线那一跑，gold 复用同一容器流程仍要重新
初始化，属于该实例的固有开销，不应当作回归信号。

## 4. 复现

```bash
# 任务清单（gate 语料，不入库）：datasets/swebench/pro/gate-10.jsonl
# 基线：只打 test_patch，期望 F2P 全不过、P2P 全过
.venv/Scripts/python skills/eval-harness/scripts/pro-sample.py \
  --tasks datasets/swebench/pro/gate-10.jsonl \
  --mode baseline --out datasets/swebench/pro-runs

# gold：候选补丁 = 数据集 gold_patch
.venv/Scripts/python skills/eval-harness/scripts/pro-sample.py \
  --tasks datasets/swebench/pro/gate-10.jsonl \
  --mode gold --out datasets/swebench/pro-runs

# 台账幂等复核：再次执行同一命令 → run_this_time=0，counts 覆盖本模式全部实例
```

产物统一落在 `datasets/swebench/pro-runs/`（全部 gitignored）：

- `pro-sample-ledger.json`：20 行（10 实例 × baseline/gold），含 `judge`
  逐 node 明细、`pytest_sec`、`elapsed_sec`、`image_ref/image_state`；
- `<sha1(instance_id)[:12]>/<mode>/{tests/test_patch.patch,
  tests/candidate.patch, pytest.log, meta.json}`；
- `imagecache/<sha1>/`：`plan.json` + layers + `.tar`（9 张，6.99 GiB）。

## 5. 执行中真坑（已入坑台账）

1. **单实例 `--force` 把 20 行台账覆盖成 1 行**：初版在 `--force` 时跳过读取
   既有台账，重跑一条就把其他 19 行丢掉。修复：无条件读回台账，`--force`
   只控制跳过判定；Pro/Live 两侧都加了回归测试
   （`test_force_preserves_other_ledger_rows`）。本轮用同一命令重建 20 行，
   痕迹在 `round51-pro-force.log`。
2. **`NODE_RE` 的 `\S+` 截断含空格的参数化 node**：qutebrowser `0833b5f6`
   的 `test_data[Hello World! This is a test.]` 被截到第一个空格，P2P 记为
   missing → `baseline_unexpected`。修复：`(.+?)` 贪婪到行尾 + 去
   ` - reason` 后缀 + 双向后缀匹配；新增解析/判分回归测试。
3. **pytest 摘要的 ` - reason` 后缀**：`SKIPPED ... - reason` 与
   `FAILED ... - reason` 会让精确 key 匹配失效。`lookup_node` 容忍后缀，
   测试钉住。
4. **ansible `0fd88717` 的 dist-packages 遮蔽**：镜像里 `/usr/local/lib/
   python3.9/dist-packages/ansible` 先于 `/app/lib`，gold 补丁等于没生效
   （F2P 0/4）。任务级 `PYTHONPATH=/app/lib` 解决，未改驱动。
5. **qutebrowser `0aa57e4f` 的 xcb 初始化失败**：仅 Xvfb + 禁 sandbox 仍有
   `could not load the Qt platform plugin "xcb"`（rc=134，无判分行）。追加
   `QT_QPA_PLATFORM=offscreen` 后 baseline_ok。
6. **零 P2P 不是坏数据**：ansible `11c1777d` 的 P2P 为空，`judge` 只要求
   F2P 非空，P2P 有则核、无则 N/A；gold 1/1 → resolved，不被误判。

## 6. 边界与偏差

1. **gold ≠ agent**：候选补丁来自数据集，只证明判分链路；agent 侧
   `--mode predictions` 通路已代码化并有测试，但**没有可用 LLM 端点，真实
   agent 补丁 n=0**，本报告不报 agent resolved（D-028）。
2. 样本 10 条、3 仓、Python；单条只跑 1–2 个选定测试文件，不能外推通过率。
3. qutebrowser `01d1d149` 的判分外 1 failed 如实保留在日志与本节，不剔除。
4. 10 张镜像本地合计（docker 虚拟大小）27.85 GB；下载层 7.68 GiB
   （9 张 `imagecache` 6.99 GiB + round-49 复用的 0.71 GiB）。清理策略未定，
   不影响仓库。
5. 本轮 7 张新镜像未单独记录 blob 测速；域名全部是 `ghcr.nju.edu.cn`，
   参考 round-50 同源实测 5.13/5.38 MB/s。若需逐张成本，应补
   `plan/fetch` 日志而不是事后估算。
6. 20 行台账里 `0833b5f6` / `0aa57e4f` 两条依赖任务级适配生效；适配字段
   缺失时这两条会以 `prepare_failed`/`infra_error` 显式失败，不会静默变成
   unresolved。

## 7. 下一步

1. **agent predictions 实跑**：接入一个真实模型端点后，对同 10 条产出
   `edits.patch` → `--mode predictions --patches` → 双闸 → 同一判分；结果
   与 gold 分开记账，禁止折算。
2. **Live 适配层**：clone → 建环境（`test_cmds`）→ 判分代码化；源码不可达
   落 `blocked_source` 保留样本（见 `live-10-2026-10-28.md`）。
3. 镜像缓存治理：保留最近 N 条或按需重建，避免 `datasets/` 无限膨胀。
