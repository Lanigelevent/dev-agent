# round-60 工作区抽象（4.3）验收实跑

ROADMAP 4.3 验收标准：**同一任务在本地与容器跑出的补丁一致（除环境差异）**。

## 口径

- 任务与宿主响应完全一致：同一 `--task`，同一份 `edits` JSON（由
  `run-workspace-bench.py` 写入宿主协议响应文件），唯一变量是工作区后端。
- 本地档 = 缺省路径（不传 `--workspace`）；容器档 =
  `--workspace container:cra-pytest:3.12`。
- 判据：两档 `state=DONE`、`tests=pass`、`edits.patch` 字节级 sha256 相同；
  登记两档环境（Python 版本/平台/镜像）。

## 结果（`tasks/bench.json`）

| 档位 | 状态 | 测试 | 补丁字节 | sha256 前 16 | 墙钟 |
| --- | --- | --- | --- | --- | --- |
| local | DONE | pass | 232 | 820b56a2e804b2b8 | 2.281s |
| container | DONE | pass | 232 | 820b56a2e804b2b8 | 3.890s |

补丁一致：**是**（字节数与 sha256 均相同，2 个 hunk 的 `calc.py` 修复）。

环境差异（如实登记，不作为不一致）：

| 项 | 本地 | 容器 |
| --- | --- | --- |
| 后端 | local | container |
| 镜像 | 无 | `cra-pytest:3.12`（`sha256:ce76ca15acd9…`，FROM `python:3.12-slim`） |
| Python | 3.12.13（项目 `.venv`，Windows） | 3.12.16（Linux） |
| 测试执行位置 | 宿主机 worktree | 容器内 `/wt`（同一份挂载） |

容器档 `test_scope` 带工作区标签：
`子集 1 项（原范围 1 项）（工作区 cra-pytest:3.12）：2 passed in 0.08s（未抽检）`。

## 三档接入边界（不夸大）

- **local**：`Workspace` 对象与既有本地路径等价（`LocalWorkspace` 复用
  `sys.executable`，缺省不传 `--workspace` 时仍走原 git 路径）。
- **container**：`code-task --workspace container:<image>` 已接入，测试/探针/
  补丁自检/补丁取数都在容器里执行（本报告即证据）。
- **remote**：接口（prepare/run/read/write/diff/close）与 CLI 已实现，但
  **没有真实远端可跑**，故编码循环对 `remote:` 显式拒绝（退出码 2）；只有
  「假 ssh 传输」的契约测试（命令拼装/引用/幂等准备），不得当作真机实跑。
- 容器镜像由国内源（清华 PyPI）构建，构建脚本见 `tooling/Dockerfile`；
  镜像只含 pytest，不含项目依赖——被审仓库测试若依赖第三方包需换镜像。

## 复跑

```
py reports/workspace-round60/run-workspace-bench.py          # 全跑并写 bench.json
py reports/workspace-round60/run-workspace-bench.py --check  # 只判一致（0/1）
```

前置：本机 Docker 有 `cra-pytest:3.12`（`docker build -t cra-pytest:3.12
reports/workspace-round60/tooling`）。
