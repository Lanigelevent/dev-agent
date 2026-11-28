# round-223：cancel runner.pid 竞态定位与加固报告（v2.100.0）

## 1. 现象与定位

- r222 light 首跑：`tests/test_mcp_async.py::test_cancel_running_job` 失败——
  `cancel result.killed_pids == []`（断言 "running 取消必须拿到并终止 runner pid"），日志留档
  `logs/suite-r222-run1-first-failed.log`；同测单独复测即通过，清理完成后重跑全绿。
- **时序证据**：失败那次套件与清理脚本**并发**——清理同时删除 `__pycache__`（25 处）、
  `reports/_work` 与 `corpus`，且 `git clean -ffdX` 触及嵌套 `.git` 对象；这类并发文件系统变更可造成导入/落盘时序异常。
- **复现实验**：清理完成后 xdist 连续 **5 跑** `pytest tests/test_mcp_async.py -n 2 -q` → 27/27 全绿
  （11.91 / 12.20 / 12.22 / 12.26 / 11.94 秒）；单测、test_interop 19/19 全绿。
  **结论**：未在干净树上复现稳定竞态，最可能是并发清理导致的环境噪声；不作因果断言（维护红线 8：观测 ≠ 因果）。
- **代码面可加固点**：`_cancel_tool` 原逻辑在 `status=running` 后若 `runner.pid` 尚未可见，
  会直接回退 `worker_pid` 而不等待——高并发/跨进程落盘延迟时可能误判「无 runner 可终止」。

## 2. 加固（最小面）

- `mcp/review_mcp.py::_cancel_tool`：当状态为 running 且 `runner.pid` 暂不存在时，有界等待
  **20 × 0.1s = 2s** 再回退 worker_pid；超时仍如实回退，不静默伪造 kill。
- `tests/test_mcp_async.py`：+1 契约 `test_cancel_waits_for_runner_pid`——延迟 0.4s 才落 pid，
  校验 cancel 捕获该 pid 并终止；async 专项 28/28。契约 **848→849**。
- 无接口/工具数变化（16 工具），无阈值改动，对外口径不变（0.42% / 宿主臂 unavailable）。

## 3. 结论与后续

- 加固为防御性，不声称已消除根因（根因未能确定性复现）；如后续在干净树上再现 `killed_pids=[]`，
  应记录当时进程树与文件时间戳，再定位 worker 与 cancel 的真实交错点。
- 清理与测试**不得并发**作为操作纪律：后续清理轮先完成删除、再启动套件（本轮已遵守）。

## 4. 证据

- `logs/suite-r222-run1-first-failed.log`（首跑失败）；`logs/suite-r222-run1.log`（重跑全绿）；
- 5 次 xdist 复跑输出（本文件第 1 节记录）；
- `mcp/review_mcp.py::_cancel_tool`、`tests/test_mcp_async.py`（+1 契约）。
