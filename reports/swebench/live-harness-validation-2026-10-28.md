# SWE-bench Live 环境构建验证（round-49，2026-10-28）

> 结论先行：**Live 的「clone → 装依赖 → pytest -rA」链路可以本地复现**。
> 用 urllib3-3527 验证：基线 3 个 F2P 全失败，套 gold 补丁后 3 个全过。
> 本实例**不在** `live-baseline-v1.49.0.json` 的 10 条基线内，是环境可行性
> 探针，不折算基线通过率。基线 10 条仍全部 `not_run`。

## 1. 为什么换样本

原计划选基线里最轻的 cfn-lint-3749（`pytest -rA`、纯 Python、F2P 3），
但源码获取按硬约束 8 走国内优先后全部不可用：

| 路径 | 结果 |
|---|---|
| gitee mirrors（cfn-lint） | 45 秒无响应，判死 |
| GitHub 直连 clone | 19.6 s 后 `Recv failure: Connection was reset` |
| ghproxy.net 代理 | 约 10.5 KB/s（120 s 只下 1.27 MB），慢即判死 |
| gh-proxy.com | 约 60 KB/s，慢即判死 |
| ghfast.top / github.moeyy.xyz | DNS 不解析 |
| ghproxy.cc | 证书过期 |

改用**已在本机 gitee 镜像缓存**的 urllib3 仓库（`datasets/swe-repos/urllib3`，
origin 为 `https://gitee.com/mirrors/urllib3`），并用 `git worktree` 检出 Live
数据集的 base_commit，全程零外网源码下载。

## 2. 实例与环境

| 项 | 值 |
|---|---|
| instance_id | `urllib3__urllib3-3527` |
| repo / base_commit | urllib3/urllib3 / `e94224931feddf9e12bb25452bf0d0c21da8a7e0` |
| 任务特征 | 4 文件 / 9 hunk / 28 行；F2P 3、P2P 1816；`test_cmds: pytest -rA` |
| 环境 | Windows，Python 3.12.13（独立 venv），editable 安装 |
| 依赖源 | 清华 PyPI 镜像（pip 22 s 装完主依赖） |
| 关键依赖 | pytest 8.0.2、cryptography 43.0.1、pyOpenSSL 24.2.1、trustme 1.2.0、h2 4.1.0、trio 0.26.2、quart 0.19.9、quart-trio 0.11.1、hypercorn 0.17.3、httpx 0.25.2、pytest-timeout 2.1.0、pytest-socket 0.7.0 |

`dev-requirements.txt` 里 Quart/hypercorn 指向 GitHub git 引用，本轮改用 PyPI
等价版本；测试导入与 dummyserver 启动均通过，属于**依赖来源偏差**，已在
局限中声明。

## 3. 复现流程

```bash
git worktree add --detach <work>/repo <base_commit>   # 从 gitee 镜像缓存
python -m venv venv
venv/Scripts/python -m pip install -i <清华> -e ./repo
venv/Scripts/python -m pip install -i <清华> <pytest 等依赖>
cd repo && git apply <test_patch.patch>
pytest -rA <3 个 F2P node id>          # 基线：应 3 失败
git apply <gold.patch>
pytest -rA <3 个 F2P node id>          # gold：应 3 通过
```

## 4. 结果

| 轮次 | 补丁 | 结果 | 耗时 |
|---|---|---|---|
| 基线 | 仅 test_patch | **3 failed**（F2P 全部按预期失败） | 10.61 s |
| gold | test_patch + gold patch | **3 passed** | 0.30 s |

两次均只跑 3 个 F2P node，未跑 1,816 个 P2P 全量；warning 为
`ssl.PROTOCOL_TLS` 弃用提示，与本任务语义无关。

补丁哈希（不存内容）：

- `test_patch.patch`：4,056 B，sha256 `0dc30ecc394b8603a67d4eeab17ba426c9343ff4a1cf4774268c03cd4a10caac`
- `gold.patch`：3,604 B，sha256 `a37df36efa33ec22ec5dbedf4e9bc811b5a93cb17c9b6dfa5b1fead3d4b6f6bc`

原始日志：`datasets/swebench/live-work/urllib3-3527/{baseline,gold}.log`
（gate 语料，不入库）。

## 5. 执行中真坑（入坑台账）

- **`git -C <repo> worktree add <相对路径>` 的相对路径按 `<repo>` 解析**，
  不是按当前目录。首次把 worktree 建进了 gitee 缓存仓内部，导致
  `pip install -e ./repo` 报「not a valid editable requirement」。修法：
  worktree 路径一律用绝对路径；已建错的用 `worktree remove --force` +
  `worktree prune` 清掉重加。
- **pytest 必须在仓库根跑**：从父目录直接跑会因 rootdir 上移报
  node path 找不到；先 `cd repo` 再执行 `pytest -rA <node id>`。
- **隐性测试依赖**：conftest 导入 httpx 失败，`test_cmds` 未列出；
  按报错装 `httpx==0.25.2`（清华 PyPI）后恢复。正式 Live 适配层应把
  conftest 导入失败转成显式环境步骤，而不是人工补依赖。

## 6. 局限与下一步

1. **非基线样本**：urllib3-3527 不在基线 10 条内；基线状态仍为 not_run，
   不得用本结果对外宣称 Live 通过率。
2. **只验证 F2P**：未执行 1,816 个 P2P；正式评测需按 `test_cmds` 全量跑并
   解析，成本更高。
3. **平台差异**：Live 无官方预构建镜像，本次在 Windows 本机建环境；正式
   批量应固定 Linux/Python 版本，避免平台相关失败污染判分。
4. **依赖版本偏差**：Quart/hypercorn 未用 dev-requirements 的 git 引用；
   正式评测应把依赖锁定文件固化进环境清单。
5. **下一步**：把「取源码 → 建环境 → 应用测试补丁 → 跑 test_cmds → 解析
   结果」封装成 Live 适配层；基线 10 条逐条评估，网络不可达的仓库在报告里
   标 `blocked_source`，不静默丢样本。
