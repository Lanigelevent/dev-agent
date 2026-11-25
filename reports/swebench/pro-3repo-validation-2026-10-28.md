# SWE-bench Pro 适配层 3 仓对照验证（round-50，2026-10-28）

> 结论先行：Pro 适配层已代码化为 `skills/eval-harness/scripts/pro-sample.py`
> （stdlib-only，单命令批量/复跑/归因）。3 仓 3 条实例全部
> **baseline_ok → gold resolved**：ansible（1/1 F2P、15/15 P2P）、
> openlibrary（5/5、15/15）、qutebrowser（3/3、46/46）。镜像只走国内源
> ghcr.nju.edu.cn，8MB blob 测速 5.13 / 5.38 MB/s，两条镜像 1021.3 / 713.6 MiB
> 分别 35 s / 20 s 拉取落盘。本轮是 **gold 口径的 harness 对照**，不是 agent
> 能力，不折算 resolved 率；基线文件 `status` 仍为 `not_run`。

## 0. 五列摘要

| 基准 | 样本量 | 判分口径 | 成本 | 完整性告警 |
|---|---|---|---|---|
| SWE-bench Pro v2（Python 子集） | 3 仓 3 条（gold 对照，非 agent） | 容器内 `before_repo_set_cmd` → 候选补丁 → `pytest -rA` 选定文件 → F2P/P2P 逐 node 对账 | 拉镜像 35 s / 20 s（1021.3 / 713.6 MiB）；单次判分 pytest 0.07–1.92 s，容器全流程 2.8–5.9 s | 0（malformed 0 / integrity_flagged 0 / blocked_source 0） |

## 1. 交付物

`skills/eval-harness/scripts/pro-sample.py`（新增，治理壳 stdlib-only）：

- **单命令驱动**：`--tasks`（Pro 任务 JSONL）+ `--mode baseline|gold|predictions`
  → 选样 → 补丁双闸 → 镜像就位 → 容器判分 → 台账。
- **判分口径**：`docker run -d` 挂载临时 `tests/` 到 `/tests` → exec 执行
  `before_repo_set_cmd`（含 reset/clean/checkout + 应用 test_patch）→
  可选应用候选补丁 → 可选 `pre_test_cmd` → `python -m pytest -rA <选定文件>`
  → 解析 `PASSED/FAILED/ERROR/...` 行，F2P/P2P 逐 node 对账；SKIPPED 不算过。
- **状态机**（入台账，互斥可归因）：`resolved / unresolved / baseline_ok /
  baseline_unexpected / baseline_p2p_failed / malformed_test_patch /
  malformed_patch / integrity_flagged / blocked_source / patch_apply_failed /
  prepare_failed / infra_error`。任何未完成样本都有状态，不静默丢。
- **补丁双闸**：复用 `deepswe-sample` 的结构校验（hunk 行数/结构）与完整性
  校验（改删既有测试/conftest/pytest 配置/解释器钩子 → critical，默认拒绝，
  `--allow-test-edits` 才放行且留 `waived_critical` 痕迹）。
- **环境适配**：任务级 `pre_test_cmd` / `env` / `pytest_args`（变量名白名单
  校验），不做实例硬编码。
- **台账续跑**：`<out>/pro-sample-ledger.json`，key=`<instance_id>|<mode>`；
  done 状态跳过，`--force` 重跑；重跑本轮 3 条 gold 输出 `run_this_time=0`，
  证明幂等。
- **镜像铁律**：`ghcr.nju.edu.cn/<repo>:<tag>` 优先 → 原名 → 短名；缺失时
  `docker-image-fetch.py` 四阶段（plan/fetch/assemble/load）；失败落
  `blocked_source` 而不是崩。

契约测试 `tests/test_pro_sample.py` 10 项（CLI 参数错误、dry-run 计划、
补丁闸短路、blocked_source 降级、integrity 拦截、台账续跑、pytest 解析、
judge 三分支、镜像名切分、适配字段校验），全过。

## 2. 任务与环境

| 实例 | 仓库 | F2P / P2P | 本地镜像 | 下载量（layers 合计） | plan→tar | blob 测速（ghcr.nju.edu.cn） |
|---|---|---|---|---|---|---|
| ansible `0ea40e09` | ansible/ansible | 1 / 15 | 2.13 GB（round-49 拉取，711.2 MB / 35.025 s） | 711.2 MiB | 本地复用 | round-49 记 18.93 MB/s |
| openlibrary `00bec1e7` | internetarchive/openlibrary | 5 / 15 | 4.2 GB | 1021.3 MiB（22 层） | 20:16:03 → 20:16:38（35 s，≈29 MiB/s 下限） | 5126.4 KB/s |
| qutebrowser `01d1d149` | qutebrowser/qutebrowser | 3 / 46 | 2.47 GB | 713.6 MiB（18 层） | 20:18:04 → 20:18:24（20 s，≈36 MiB/s 下限） | 5384.8 KB/s |

镜像原名 `ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>`，统一改写为
`ghcr.nju.edu.cn/...`；ghcr.io 直连未参与（硬约束 8）。下载量取
`plan.json` 的 layers 之和，与落盘 tar 大小一致（1,071,022,080 B /
748,349,440 B）；plan→tar 含组装耗时，故聚合速率为下限。

容器内环境：镜像自带 `PYTEST_ADDOPTS=--tb=short -v --continue-on-collection-errors
--reruns=3`（rerun 数即日志里的 `3 rerun` 来源）。qutebrowser 有任务级适配：
`Xvfb :99` 常驻 + `DISPLAY=:99` + `QTWEBENGINE_DISABLE_SANDBOX=1` +
`-p no:xvfb`（见 §5）。

## 3. 结果（基线 → gold）

| 实例 | 基线（仅 test_patch） | gold（test_patch + gold patch） | 判分（gold） | pytest 耗时（harness） | 全流程 elapsed |
|---|---|---|---|---|---|
| ansible | 1 failed, 15 passed, 3 rerun（0.29 s） | **16 passed**（0.19 s） | F2P 1/1、P2P 15/15 → `resolved` | 0.969 s / 0.672 s | 4.438 s / 2.829 s |
| openlibrary | 5 failed, 15 passed, 4 warnings, 15 rerun（0.13 s） | **20 passed**（4 warnings, 0.07 s） | F2P 5/5、P2P 15/15 → `resolved` | 1.282 s / 1.922 s | 120.297 s* / 3.891 s |
| qutebrowser | 4 failed, 94 passed, 5 skipped, 12 rerun（1.92 s） | **1 failed, 97 passed, 5 skipped, 3 rerun**（1.63 s） | F2P 3/3、P2P 46/46 → `resolved` | 3.844 s / 3.625 s | 5.891 s / 5.844 s |

\* openlibrary 基线首次运行含镜像拉取（35 s）+ 容器准备，故 120.297 s；
gold 复用本地镜像后 3.891 s。

qutebrowser gold 残留的 1 failed 是
`tests/unit/utils/test_version.py::TestModuleVersions::test_existing_attributes[adblock-True]`，
**不在 F2P/P2P 判分点内**（已对该实例数据逐 node 核对：F2P 3 条、P2P 46 条均不含，
仅与判分点同文件），按数据集口径不影响 resolved。

三条实例基线均为预期失败形态（F2P 全失败、P2P 全过），gold 后判分点全过，
两轮互斥对齐，说明「任务字段 → 容器命令 → pytest 解析」映射正确。

## 4. 复现

```bash
# 任务清单（gate 语料，不入库）：datasets/swebench/pro/gate-3.jsonl
# gold 对照（候选补丁 = 数据集 gold patch）
.venv/Scripts/python skills/eval-harness/scripts/pro-sample.py \
  --tasks datasets/swebench/pro/gate-3.jsonl \
  --predictions datasets/swebench/pro-runs/predictions.json \
  --mode gold --out datasets/swebench/pro-runs
# 台账幂等复核：再次执行输出 run_this_time=0、counts.resolved=3

# 基线对照（同一台账，key 区分 mode）
... --mode baseline ...
```

产物（`datasets/swebench/pro-runs/`，全部不入库）：

- `pro-sample-ledger.json`：6 行结果（3 实例 × baseline/gold），含 judge 明细；
- `<sha1(instance_id)[:12]>/<mode>/{tests/test_patch.patch, tests/candidate.patch,
  pytest.log, meta.json}`；
- `imagecache/<sha1>/`：`plan.json` + layers + `.tar`（共 3.4 GB）。

补丁指纹（sha256 前 16 位，存哈希不存内容）：

| 实例 | test_patch.patch | candidate.patch（gold） |
|---|---|---|
| ansible | 1,230 B / `7de812e77770f2cf` | 1,906 B / `59a87bfccdfec081` |
| openlibrary | 2,355 B / `24e83ef05aa9c583` | 4,004 B / `ce896c9a27145ab4` |
| qutebrowser | 1,789 B / `89d1421c28bf6149` | 5,884 B / `0fc7cb031719bd9b` |

## 5. 执行中真坑（入坑台账）

1. **`manifests/latest` 写死导致按实例 tag 的镜像 404**：`docker-image-fetch.py`
   与 `docker-mirror-probe.py` 都用 `/manifests/latest` 拼 URL，Pro 镜像按
   `instance_id` 打 tag，plan 阶段直接 404——测速可达 ≠ 镜像可拉的同型坑
   （v1.22.0 的 blob 段教训换了个位置重演）。修复：两处支持显式 tag
   （probe 新增 `--tag`；fetch 的 `resolve_amd64_manifest` 增参、`cmd_plan`
   切分 `repo[:tag]`），并各加回归测试（断言 `/manifests/<tag>` 被请求）。
2. **qutebrowser 容器内 QtWebEngine 整进程退出**：root + 无 X 环境下
   `TestChromiumVersion` 初始化直接退出，pytest 停在 74%、无 `-rA` 摘要
   （rc=1 但无判分行 → 会被误判 prepare_failed）。`xvfb-run` 不够（teardown
   断连仍 rc=1），最终解：任务级 `pre_test_cmd` 常驻 `Xvfb :99` + `DISPLAY` +
   `QTWEBENGINE_DISABLE_SANDBOX=1` + `-p no:xvfb`。结论：容器型判分必须允许
   **任务级环境适配字段**，不能假设「一套 pytest 命令打天下」。
3. **`--image` 与 `--tag` 参数切分不一致会假 404**：probe 的 `--image` 不含
   tag（`scaleapi/swe-bench_pro-v2`），fetch 接受 `repo[:tag]`；排查时把带 tag
   的字符串塞给 probe 得到 404，误以为镜像挂了。已在 docstring 写清用法，
   `split_ref` 统一「首段含 `.`/`:` 或 localhost 才算 registry」。
4. **pytest 摘要里的 `SKIPPED [1] ...` 第二列是计数不是 node**：初版解析把它
   当 node id，后缀匹配可能误吸。修复：`[` 开头的 token 直接跳过。
5. **零 P2P 任务永远 unresolved**：初版判分要求 F2P 与 P2P 都非空；P2P 缺失
   是合法形态，改为只要求 F2P 非空，P2P 有则核、无则 N/A。

## 6. 边界与偏差

1. **gold 口径 ≠ agent 能力**：候选补丁由数据集提供，只证明判分链路；
   agent 侧需 `--mode predictions` 接编码循环产物，本轮未做。
2. **样本 3 仓 3 条**，均为 Python、单/少测试文件；不外推通过率。扩到 10 条
   是下一轮任务。
3. **qutebrowser 的判分外失败**如实保留在复盘材料里，不剔除日志；它是
   「数据集判分点只覆盖选定 node」的正常现象，不是适配层缺陷。
4. 镜像与运行产物 3.4 GB 全部 gitignored；本地 docker 三镜像合计 8.8 GB，
   清理策略未定（不影响仓库）。
5. openlibrary 基线 120.297 s 是首次拉镜像的一次性成本，不应当作单次判分成本
   引用；报告成本列已按「拉取 / 判分」分开。

## 7. 下一步

1. **Pro 扩到 10 条**：剩余 7 条按仓库均衡补齐（同一驱动，先 baseline 再 gold，
   新仓库如遇环境差异走任务级适配字段，不硬编码）。
2. **agent 侧口径**：编码循环产出补丁 → `--mode predictions` → 同一判分流程；
   agent 补丁同样过双闸并记 `integrity_flagged`。
3. **Live 适配层**：clone → 建环境（`test_cmds`）→ 判分代码化；源码不可达
   落 `blocked_source` 并保留样本，不静默丢。
4. 镜像缓存治理：保留最近 N 条或按需重建，避免 `datasets/` 无限膨胀。
