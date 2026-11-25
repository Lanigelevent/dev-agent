# SWE-bench Pro / Live 可行性实测（round-48，2026-10-28）

> 结论先行：**数据集与镜像源都可用，真正卡住试点的是评测 harness 兼容性**，
> 不是网络。本轮下线两份独立基线（各 10 条 Python，status=not_run），
> 未伪报任何 resolved。

## 1. 国内镜像优先（硬约束 8）实测

| 对象 | 源 | 结果 | 证据 |
|---|---|---|---|
| SWE-bench Pro 数据集 | hf-mirror.com | HTTP 200，0.212s | `curl https://hf-mirror.com/api/datasets/ScaleAI/SWE-bench_Pro` |
| SWE-bench Live 数据集 | hf-mirror.com | HTTP 200，数据集存在 | `curl .../api/datasets/SWE-bench-Live/SWE-bench-Live` |
| Pro default parquet | hf-mirror.com | 6,511,689 B，**4.13 MB/s** | 1.58s 完成；sha256 与 X-Linked-Etag 一致 |
| Pro v1 parquet | hf-mirror.com | 7,816,820 B，7.43 MB/s | 1.05s |
| Live lite parquet | hf-mirror.com | 14,442,471 B，7.49 MB/s | 1.93s |
| Live verified parquet | hf-mirror.com | 24,696,977 B，11.84 MB/s | 2.09s |
| Pro 镜像 manifest | ghcr.nju.edu.cn（国内） | HTTP 200，0.14s | 匿名拉 manifest 可用 |
| Pro 镜像首层 8MB | ghcr.nju.edu.cn（国内） | **16.71 MB/s** | HTTP 206，8,388,608 B / 0.50s |
| Pro 镜像首层 8MB | ghcr.io（国际直连） | **0.14 MB/s**（58.0s） | HTTP 206；慢 119 倍，仅作回退 |
| GitHub clone | github.com | `git ls-remote` 成功 | round-46 已实测可 clone |
| ECR（DeepSWE 镜像） | public.ecr.aws | HTTP 401 /v2/，1.18s | 认证挑战=可达；round-46 实拉 3.86GB |

判定：Pro 镜像**必须走 ghcr.nju.edu.cn 国内镜像**；ghcr.io 直连慢即判死
（缺省 2 分钟纪律下会一路拖垮批量跑）。本轮只抽测一个 tag 的 8MB 首层段，
不等于整镜像可拉满速；正式试点前按铁律再跑整层速度。

## 2. 数据集事实（已落盘 datasets/swebench/，不入库）

| 数据集 | 文件 | 行数 | Python | 备注 |
|---|---|---|---|---|
| SWE-bench Pro | `pro/default.parquet` | 642 | 237 | 语言：go 256 / python 237 / js 145 / ts 4；含 `docker_image`（ghcr.io） |
| SWE-bench Pro | `pro/v1.parquet` | 731 | 266 | 旧版 schema，无 `docker_image` 字段 |
| SWE-bench Live | `live/lite.parquet` | 300 | 300 | 全部 pytest；无预构建镜像，需按 `test_cmds` 建环境 |
| SWE-bench Live | `live/verified.parquet` | 500 | 500 | 全部 pytest；同上 |

源文件 sha256（与镜像 ETag 一致）：
- Pro default：`1067f72c1f43bbc578276888625db3b836cebb535546c9eaf824c5d5dd104a7f`
- Live lite：`7ee0a75c41bfc954fd441b67ce738fc5c1cbae00721c4e30e7db4d893057c9ab`

## 3. 独立基线（本轮新建）

- `reports/swebench/pro-baseline-v1.49.0.json`：10 条 Python，**3 个仓库**
  （ansible 4 / openlibrary 3 / qutebrowser 3——Python 子集只有这 3 仓，
  跨 3 仓是实测下限而非选样偏好），确定性选样规则写在文件内；全部
  `status=not_run`。
- `reports/swebench/live-baseline-v1.49.0.json`：10 条 Python（pytest），
  10 个不同仓库；全部 `status=not_run`。
- 两份基线只存元数据（instance_id / repo / base_commit / 判分点数量 /
  镜像或 test_cmds），**不存补丁与问题文本**，按 gate 语料不入库的纪律处理。

## 4. 真实阻塞：harness 兼容性（不是网络）

1. **Pro**：判分依赖 `before_repo_set_cmd` 与 `selected_test_files_to_run`
   的自定义执行顺序；本项目 `agent/swe_run.py` 面向 SWE-bench Lite 的
   `FAIL_TO_PASS/PASS_TO_PASS` 口径，不能直接吃 Pro 的字段。需要适配层
   （或在容器内调用 Pro 官方 harness）。
2. **Live**：无预构建镜像，需 clone 后按 `test_cmds`（`poetry run pytest -rA`
   等）装依赖；比 Pro 重，且依赖解析受镜像源影响。适合放在 Pro 之后。
3. **判分对齐**：两条线都要求「reward/判定只认测试结果」，与 DeepSWE 同口径；
   适配层不得引入新的判分分支，除非像 patch integrity 一样走 DECISIONS 记录。

## 5. 下一步（round-49）

1. 先做 Pro 的 1 条端到端试跑：容器内手动执行 `before_repo_set_cmd` +
   `selected_test_files_to_run`，验证判分可复现，再谈 10 条批量。
2. 镜像拉取强制 `ghcr.nju.edu.cn`，并记录整层速度；ghcr.io 直连只作回退且
   写降级原因。
3. Live 试点顺延到 Pro 打通之后；先选 `pytest -rA` 且无 poetry 的 10 条里
   最轻的 1 条验证环境构建。
4. 污染风险：两条线都只报自有实跑样本；对外不引用厂商自报数字。

## 6. 局限（如实声明）

- 镜像速度只测了一个 tag 的首层 8MB，未测完整层与多 tag 并发；
- 数据集下载时点 2026-10-28，上游 revision 变化后需重新对 sha256；
- 本轮没有跑出任何 Pro/Live resolved，基线全部 `not_run`。
