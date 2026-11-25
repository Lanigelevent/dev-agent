# round-65 SWE-bench Live 补源与基线：D-045 候选资源可达性实测

日期：2026-10-29 ｜ 版本：v1.66.0 ｜ 状态：补源 5/7 成功（2 阻塞）+ cfn-lint 判数据缺陷 + llama_deploy 基线 `baseline_ok`

## 结论

1. **补源 5/7 成功**：D-045 九条候选里 7 条尝试取源（matplotlib 已按仓库级
   暴露剔除，haystack/reflex 本轮未尝试），5 条单提交深度 1 取源成功
   （llama_deploy / pdm / conan / keras / cfn-lint），2 条双源超时阻塞
   （instructlab / pvlib-python）。取源一律 gitee 优先、GitHub 回退，单源
   **150 秒上限**（硬约束 8：慢即判死；每次降级原因见 §1 表）。
2. **cfn-lint-3749 不可判——上游数据缺陷**：lite.parquet 把含空格的参数化
   node id 截断（P2P 1223 条里 329 条括号不闭合），exact-match 判分必判
   missing。适配层已加**开跑前体检**：修前要花 192.312 s（pytest 153.68 s）
   跑完整套件才拿到误导性的 `baseline_unexpected`，修后 **0.0 s** 直接判
   `malformed_node_ids`（§2）。
3. **llama_deploy-330 基线 v2 = `baseline_ok`**：v1 因 3 条可选依赖测试
   被 SKIPPED（判分点 missing）判 `baseline_unexpected`；补装 `aiokafka` /
   `aio-pika` 后 v2 **P2P 117/117 passed、F2P 2/2 FAILED（基线预期）、
   0 missing，81.828 s**——该实例的 Live 环境链在本机可判（§3）。
4. **冷启动执行面仍阻塞（如实）**：`resolved` 口径需要实例官方镜像，本机
   docker 仅覆盖已见实例、国内镜像源探测 usable_rank=[]（round-64），本轮
   **不产生任何冷启动 resolved 主张**；D-045 协议已定，执行排在镜像可达性
   解决之后。

## 1. 补源结果（`logs/seed-live-sources.log` 原始输出）

| 仓库（实例） | gitee | GitHub 回退 | 结果 | 大小 |
| --- | --- | --- | --- | --- |
| llama_deploy（llama_deploy-330） | MISS 10 s（rc=128，镜像无此仓） | OK 58 s | 就位 | 2043 KB |
| pdm（pdm-3237） | MISS 150 s（超时） | OK 85 s | 就位 | 2979 KB |
| conan（conan-17092） | MISS 150 s（超时） | OK 37 s | 就位 | 1487 KB |
| keras（keras-20389） | **OK 2 s**（镜像命中） | 未用 | 就位 | 1595 KB |
| cfn-lint（cfn-lint-3749） | MISS（早前段） | OK 73 s | 就位 | 2699 KB |
| instructlab（instructlab-2526） | MISS 27 s（rc=128，无此仓） | MISS 150 s（超时） | **BLOCKED** | — |
| pvlib-python（pvlib-2249） | MISS 150 s（超时） | MISS 151 s（超时） | **BLOCKED** | — |
| haystack（haystack-8489） | 未尝试 | 未尝试 | 未尝试（全量克隆 429 MB，待单独评估单 sha 取法） | — |
| reflex（reflex-4087） | 未尝试 | 未尝试 | 未尝试（全量克隆 211 MB，同上） | — |

取源方法：`git init` + `git remote add origin` + `git fetch --depth 1 origin
<sha>`（直接 `git fetch <url> <sha>` 在 Windows git 上报 invalid refspec，
round-51 已定式）。脚本 `logs/seed-live-sources.sh`（工作件，不入库）。

## 2. cfn-lint-3749：上游数据截断与 fail-fast

**上游形态**（`datasets/swebench/live/lite.parquet`，sha256 7ee0a75c…，D-045
冻结口径）：该实例声明 F2P 3 / P2P 1223；实测 P2P 中 **329 条** node id
括号不闭合，形如

```
test/unit/module/context/conditions/test_equals_sort.py::test_sorted[Different
test/unit/module/context/conditions/test_equals_sort.py::test_sorted[Two
```

即数据集生成时按空格截断了参数化 id（上游原表 0 条含空格）。exact-match
判分对这 329 条只能判 missing，与测试是否真的通过无关。

**修前/修后对照**：

| 跑次 | 结果 | 耗时 | 说明 |
| --- | --- | --- | --- |
| baseline #1（`logs/live-cfnlint-baseline.json`） | `baseline_unexpected` | 101.797 s | 环境缺 `defusedxml`，收集失败全 missing（非本缺陷） |
| baseline #2（`logs/live-cfnlint-baseline2.json`） | `baseline_unexpected` | 192.312 s | 套件本身 153.68 s（1666 passed / 6 failed / 4 deselected），P2P 894/1223 passed、**329 missing**——全部由截断 id 造成；6 条失败均**不在**该实例 P2P 清单内 |
| 前置体检（`logs/live-cfnlint-nodecheck.json`） | `malformed_node_ids` | **0.0 s** | 不建环境不跑套件，detail 报「329 条，如 …test_sorted[Different」 |

**修法**（`skills/eval-harness/scripts/live-sample.py`）：新增
`node_id_problems(task)` 在 `run_one` 建 venv 之前体检括号闭合；命中即
`state="malformed_node_ids"` 秒级返回，`failed_states` 与退出码文档同步，
`dry_run` 计划输出 `node_id_problems` 计数。契约
`tests/test_live_sample.py::test_truncated_node_ids_fail_fast` 钉住
（坏 id 立即 rc1、不落 blocked_source、detail 含「括号不闭合」；干净样本
`node_id_problems == 0`）。

## 3. llama_deploy-330 基线

**环境**：`datasets/swe-repos/llama_deploy`（本地缓存，单提交）→ venv →
`pip install poetry` → `pip install -e .` → `pip install pytest
pytest-asyncio pytest-mock exceptiongroup`；测试命令 `poetry run pytest -rA`
（`POETRY_VIRTUALENVS_CREATE=false` 让 poetry 用同一 venv）。

| 跑次 | 结果 | 耗时 | F2P | P2P |
| --- | --- | --- | --- | --- |
| v1（`logs/live-llamadeploy-baseline.json`） | `baseline_unexpected` | 194.625 s | 2/2 FAILED（基线预期） | 114/117 passed + 3 missing |
| v2（`logs/live-llamadeploy-baseline2.json`） | **`baseline_ok`** | 81.828 s | 2/2 FAILED（基线预期） | **117/117 passed、0 missing** |

v1 的 3 条 missing 均为可选消息队列后端的 skipif 测试
（`tests/message_queues/test_apache_kafka.py::test_publish`、
`tests/message_queues/test_rabbitmq.py::{test_establish_connection,
test_publish}`）——`aiokafka` / `aio_pika` 未装时 `pytest.mark.skipif`
把用例整体跳过，判分点取不到；三个测试本身全部 mock、不需要真 broker。
v2 在 setup 里补 `aio-pika aiokafka` 后重跑（`--force` 只重跑目标 key，
台账其他行不动）。

v2：`3 failed, 117 passed, 10 warnings in 66.42s`——3 条失败为 2 条 F2P
（e2e HITL 客户端，基线预期）与 1 条不在上游判分清单内的
`tests/services/test_workflow_service.py::test_hitl_workflow_service`
（同属 HITL e2e 面，上游未把它列进 F2P/P2P，不影响判定）；v1 的 3 条
skipif 测试补装依赖后全部收集并通过，0 missing。

> 判分口径提示：baseline 模式要求「F2P 全失败 + P2P 全通过」才算
> `baseline_ok`；F2P 在基线即通过或判分点未被收集都判 `baseline_unexpected`
> （`pro-sample.py::judge`）。v1 的两条 F2P（e2e HITL 客户端）在基线
> FAILED 属预期，问题只在 P2P 的 3 条 skip。

## 4. 对 D-045（冷启动协议）的影响

- 候选 9 条的资源面：**5 条就位**、2 条阻塞（instructlab / pvlib-python）、
  2 条未尝试（haystack / reflex），matplotlib 按仓库级暴露剔除。
- 可判面：cfn-lint-3749 **不可判**（上游数据缺陷，malformed_node_ids 原样
  保留不补位）；llama_deploy-330 **基线可判**（`baseline_ok`，P2P 117/117）——
  即九条候选里当前「源就位且基线可判」的是 1 条，其余 4 条已就位待跑基线。
- 执行面：`resolved` 口径仍需要官方镜像（本地 docker 覆盖不足、国内镜像源
  usable_rank=[]），故本轮只推进「源就位 + 基线可判性」，不产生任何
  resolved 主张；D-045 的预算（每实例 ≤45 min / ≤20 编辑 / ≤1 次重试 /
  全程 ≤8 h）与四态判据不变，样本量按实际可用资源如实缩水。

## 5. 证据与复跑

证据（均不入库，路径相对仓库根）：

- 补源：`logs/seed-live-sources.log`、`datasets/swe-repos/`（缓存目录）
- cfn-lint：`logs/live-cfnlint-baseline{,2}.json/.err`、
  `logs/live-cfnlint-nodecheck.json`、`datasets/swebench/live-runs-r65/work/945ca629c037/test.log`
- llama_deploy：`logs/live-llamadeploy-baseline{,2}.json/.err`、
  `datasets/swebench/live-runs-r65/work/d3c94e6f310f/test.log`
- 台账：`datasets/swebench/live-runs-r65/live-sample-ledger.json`

复跑命令：

```
# cfn-lint：前置体检立即判 malformed_node_ids（0.0 s，不建环境）
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r65-cfnlint.jsonl --mode baseline \
  --out datasets/swebench/live-runs-r65 --source-root datasets/swe-repos --force

# llama_deploy：baseline（v2 已含 aiokafka/aio-pika）
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r65-llamadeploy.jsonl --mode baseline \
  --out datasets/swebench/live-runs-r65 --source-root datasets/swe-repos --force

# 契约
.venv/Scripts/python.exe -m unittest discover -s tests -p test_live_sample.py
```

## 6. 边界（不宣称的部分）

- 本轮**没有**任何 Live 冷启动 resolved / f2p_passed 结论；补源与基线
  可判性只回答「这套语料能不能在本机判分」，不回答「agent 能不能解」。
- llama_deploy v1/v2 是**同一实例**的两次基线尝试，不是两个样本。
- haystack/reflex 未尝试不等于不可得；instructlab/pvlib 在 150 s 上限下
  双源超时，按硬约束 8 判死并记录降级原因，不重试刷时间。
