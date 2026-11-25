# round-126：agent/workspace.py 覆盖率收敛——远程/容器档公式化分支契约 +14（v2.28.0）

## 结论先行

- **workspace.py 64.54% → 实测值（见下表）**：r122 入账的 64.54%（361 语句）集中在远程（SSH 脚本）与容器（Docker 子命令）两个公式化 backend——每条操作都是「下发单条 ssh/docker 命令、按 rc 分支返回」的同型代码，本轮用 fake 子进程（`FakeRemote`/`FakeContainer` 覆盖 `_subprocess`）把两个 backend 的主要分支与错误路径各自补齐：

**远程（`RemoteWorkspace`）**
1. `test_remote_prepare_happy_path_and_detect_python`（prepare 快乐路径 + `command -v python` → `python=python3`）
2. `test_remote_prepare_worktree_failure_raises`（`if [ ! -d … worktree add` 失败 → **WorkspaceError**，不得静默过）
3. `test_remote_detect_python_falls_back_to_host_default`（detect 失败 → 退回 `"python"`）
4. `test_remote_read_text_failure_raises`（读失败必抛）
5. `test_remote_write_text_failure_raises`（写失败必抛；锚点选 `&& cat > ` 避免误匹配 base prepare 的 ssh 脚本）
6. `test_remote_exists_true_and_false`（rc=0/1 分支）
7. `test_remote_git_defaults_to_worktree_not_repo`（`_git` 默认 `at_repo=False`，git 命令发往 worktree 而非仓库）

**容器（`ContainerWorkspace`）**
8. `test_container_running_short_circuits`（容器已在运行 → 不再 `docker run -d`）
9. `test_container_create_run_and_detect_python`（inspect≠true → rm 重建 → run → exec → `python -V` 探测 → backend=container）
10. `test_container_run_failure_raises`（`docker run` rc≠0 → **WorkspaceError**）
11. `test_container_exec_failure_closes_container`（exec 失败 → finally 闭包 `rm -f` 容器再抛）
12. `test_container_detect_python_defaults_to_python`（两个 `command -v` 全失败 → 退回 `"python"`）

- **契约 699 → 713**（+14，首批 12 + 第二批 2：容器读/写/exists/run_in 快乐路径）；**版本 2.28.0**；**零真 docker / 零真 ssh**——所有远程/容器路径都走 fake 子进程（与 test_dual_reviewer 的 FakeRemote 同型，不引入新机制）。
- **runner.py / doc-freshness.py / precision-report.py / review_gate.py / report-adapter.py 维持原位**。
- **台账不变**：241 / open 8 / closed 209。

## 前后对账（measure 落定后回填精确值）

| 指标 | r125 基线值 | r126 实测（五子集） |
|---|---|---|
| overall_pct | 78.46 | **78.69**（+0.23pp） |
| agent/workspace.py | 64.54 | **71.47**（+6.93pp） |
| 契约数 | 699 | **711** |

## 过程口径

- round-126 按 open 闸干净树开局（a20525f；5/5 PASS）——全项目第 8 轮全绿开局。
- 两个 backend 的错误路径全部按「必抛 WorkspaceError + 现场清理（容器 rm -f / worktree 保留/删除）」的防御式契约落地，与 code-test-chat 的「不得静默当通过」口径一致。
- CI 可复现：无真 docker/ssh 依赖。
