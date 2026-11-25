# round-177：MCP 异步扩面回归 + `runs/jobs/` 审计（v2.76.0）

## 1. 结论先行

- **Unix 进程组终止路径已用模拟契约覆盖**（Windows 本机无法真跑 POSIX 信号）：
  `test_kill_pid_posix_process_group` 断言 `os.getpgid(pid)` → `os.kill(pgid, SIGTERM)`；
  `test_kill_pid_missing_process` 断言 `ProcessLookupError` → `False` 不抛异常；
  `test_cancel_falls_back_to_worker_pid` 断言 `runner.pid` 缺失时回退 `job.json.worker_pid`。
  +3 契约（783→786），async 专项 17/17 全绿。Windows 侧取消在 r176 已用真作业验证 `killed_pids=[49504]`。
- **`runs/jobs/` 目录审计（只读，不清理）**：当前 6 个作业目录（cancelled 2 / done 4），111 文件、**0.2 MB**，
  4 个留存 runner.pid / worker_pid；磁盘压力可忽略，**不构成阶段 C（purge）的迫切理由**——C 仍未批准，不实现清理 API。
- **附带观测（item 137③ 依赖锚点）**：r173 依赖刷新第十一跑后第 4 轮，距 ~10 轮锚点尚早，本轮不刷新；无降级、无国际直连回退。
- 对外口径不变（0.42% / 宿主臂 unavailable，D-053 归因）；工具数 15、脚本 86 不变。

## 2. 审计明细

| 项 | 值 |
|---|---|
| job 目录 | 6（`runs/jobs/<32hex>`），状态 cancelled×2 / done×4 |
| 文件/体积 | 111 文件 / 185,341 字节 ≈ 0.2 MB |
| pid 元数据 | 4 目录有 runner.pid；4 目录有 worker_pid（cancelled 作业为竞态前留下的旧目录，无 runner.pid，属 r176 首跑历史） |
| 清理需求 | 无迫切性；purge 阶段 C 未批准，保持现状 |

## 3. 验证范围与边界

- 本轮新增契约只验证**进程终止语义与回退路径**，不验证真实 POSIX 运行时行为（平台限制，如实标注）；
  Unix 真机信号回归须在 Linux 宿主执行（可列为后续条件项，非本轮承诺）。
- 既有 Windows 真作业冒烟证据：`reports/mcp-cancel-smoke-r176.md`（cancel→cancelled→后续 submit done step=10）。
- `runs/jobs/` 审计为只读快照，未删除任何作业目录。

## 4. 证据

- `tests/test_mcp_async.py`（17 条 async 契约）；
- `reports/mcp-cancel-smoke-r176.md`（Windows 真作业取消）；
- 本文件（目录审计 + 平台边界 + 依赖锚点观测）。
