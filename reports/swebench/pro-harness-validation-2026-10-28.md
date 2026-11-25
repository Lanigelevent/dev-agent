# SWE-bench Pro harness 单条验证（round-49，2026-10-28）

> 结论先行：**Pro 的判分字段可以在容器内复现**——ansible 单条基线为
> F2P 失败 1 / P2P 全过 15，套用 gold 补丁后 16 全过。round-48 记的
> 「harness 字段不兼容」是缺适配层，不是不可评测。本轮为 **gold 口径
> 的 harness 验证**，不是 agent 能力，不折算 resolved 率。

## 1. 实例与环境

| 项 | 值 |
|---|---|
| instance_id | `instance_ansible__ansible-0ea40e09d1b35bcb69ff4d9cecf3d0defa4b36e8-v30a923fb5c164d6cd18280c02422f75e611e8fb2` |
| repo / base_commit | ansible/ansible / `f7234968d241d7171aadb1e873a67510753f3163` |
| 判分点 | F2P 1 个、P2P 15 个，均在 `test/units/utils/test_vars.py` |
| 镜像 | `ghcr.nju.edu.cn/scaleapi/swe-bench_pro-v2:<instance>`（国内镜像） |
| 本地镜像 digest | `sha256:af7d28fe6608951bf88e39b6a24d5574dcd1b5b82a6c983147666289f8014f18` |
| amd64 manifest | `sha256:7cae127d37e28600d08026f70cbc2aef029ab2c9daf0bba67c912cec5fb4d0d0` |
| 镜像大小 / 拉取 | 711.2 MB（18 层）/ **35.025 s**（≈20.3 MB/s 平均，含解压） |
| 8MB blob 段测速 | 18.93 MB/s（HTTP 206，ghcr.nju.edu.cn；未用 ghcr.io 回退） |
| 容器内环境 | Python 3.11.13、pytest 7.4.2；镜像自带 `PYTEST_ADDOPTS=--tb=short -v --continue-on-collection-errors --reruns=3` |

镜像内 `/app` 已在 base_commit，`/tests` 默认不存在，判分时以 bind mount 提供；
这与数据集 `before_repo_set_cmd` 引用 `/tests/test_patch.patch` 一致。

## 2. 复现的判分流程

```bash
# 容器启动：-v <work>/tests:/tests，镜像默认 cmd 为 tail -f /dev/null
cd /app
git reset --hard <base_commit>
git clean -fd
git checkout <base_commit>
git apply --verbose /tests/test_patch.patch     # 基线判分
git apply --verbose /tests/gold.patch           # gold 口径追加
python -m pytest -rA test/units/utils/test_vars.py
```

`selected_test_files_to_run` 直接作为 pytest 文件参数；F2P/P2P 是 node id，
按 `PASSED/FAILED <node id>` 逐项对账。

## 3. 结果

| 轮次 | 补丁 | 结果 | 判分 |
|---|---|---|---|
| 基线 | 仅 test_patch | **1 failed, 15 passed**（3 rerun）：`test_combine_vars_replace` 失败，15 个 P2P 全过 | F2P 按预期未过 |
| gold | test_patch + gold patch | **16 passed** | F2P 1/1、P2P 15/15 |

基线与 gold 两次结果互斥且完全对齐数据集判分点，说明字段到 pytest 的映射正确。
原始日志留在 `datasets/swebench/pro-work/ansible-0ea40e09/tests/`
（`baseline-pytest.log` / `gold-pytest.log`，按 gate 语料不入库）。

补丁哈希（用于复核，不存内容）：

- `test_patch.patch`：1,230 B，sha256 `7de812e77770f2cf22ffe8441294ec99330dc36a20ac01517d606b5c1caaa99f`
- `gold.patch`：1,906 B，sha256 `59a87bfccdfec081873ba2381668e1af6f336a19d3dc64ae10b9ef976c9856a0`

## 4. 结论与偏差

1. **判分可复现**：Pro v2 的 `before_repo_set_cmd` + `selected_test_files_to_run`
   能直接落地为「重置 → 应用测试补丁 → 应用候选补丁 → pytest -rA 选定文件」。
2. **适配层是工作量，不是阻塞**：需要把上述流程代码化（批量、结果解析、
   patch integrity 闸、成本台账），并处理多文件/多语言实例的命令差异。
3. **本轮只验证 1 条**：单仓库、单测试文件、Python；不能外推为 Pro 通过率。
4. **gold 口径 ≠ agent 口径**：gold 补丁由数据集提供，仅证明判分链路；agent
   侧 resolved 仍需真实编码循环产出补丁后复跑同一流程。
5. 镜像只走了国内镜像；ghcr.io 直连未参与本轮，符合硬约束 8。

## 5. 执行中真坑（入坑台账）

- **MSYS/Git Bash 路径转换会改写 docker 参数**：`-v <win路径>/tests:/tests`
  被 MSYS 改写成 `C:/Program Files/Git/tests`，容器内挂载点错位（首次
  `docker run` 报 destination 不存在）。修法：`MSYS_NO_PATHCONV=1` +
  Windows 风格路径（`-v 'C:\...\tests:/tests'`），`docker exec` 同理。
  判据：`docker inspect` 看 Mounts 的 Destination 是否恰为 `/tests`。
- 验收：同一命令序列在修正后跑出 §3 的两组互斥结果（1F/15P → 16P），
  说明挂载与判分链路真实生效，而非空跑。

## 6. 下一步

1. 把流程封装为 `pro-sample.py`（或现有 sample 脚本的 Pro 适配层），先跑
   3 条不同仓库的基线 + gold 对照，确认命令可泛化。
2. 通过后再对 `pro-baseline-v1.49.0.json` 的 10 条做批量，判分只认测试结果。
3. 与 DeepSWE 同口径：结构损坏 / 完整性标记不计 resolved，成本单独归集。
