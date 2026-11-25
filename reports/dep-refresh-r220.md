# round-220：依赖刷新第十六跑（2026-11-24）

## 结论先行

- **直接升级 2 项**：`tree-sitter 0.26.1→0.27.0`、`coverage 7.17.4→7.17.5`；其余 9 个直接依赖 `Would make no changes`。
- **拒绝非跟踪传递升级**：`pyyaml 6.0.3→6.0.4`、`packaging 26.3→26.4` 不静默纳入。
- **双面锁验**：`uv.lock` / `requirements-lock.txt` / `.venv` 11 个直接依赖逐包一致；`uv.lock` 项目版本从 2.93.0 同步到 2.99.0。
- **三引擎矩阵零漂移**：Ruff `973/482/250`、ast-grep `29/2/2`、LibCST deep-equal。
- **isolated 仅盘点不安装**：semgrep `1.186.0`、pynguin `0.48.0` 可由清华镜像解析；保持 LGPL subprocess 边界。

## 证据

- `reports/_work/dep-inventory-r220.json`：11 项真值、dry-run 原始尾部、决策与矩阵结论。
- `reports/_work/m220/`：三引擎矩阵落盘产物。
- 定向回归：`test_agent.py` 136 项（1 skip）、`test_engines.py` 24 项全绿。
- 性能诊断：顺序 unittest 首跑 803.734s 超 600s；tree-sitter 0.26.1/0.27.0 同组 `test_agent` 对照为 289.18s/264.42s，无升级回归。改用项目批准的 xdist 全量路径；600.18s 越线复测，已知 MCP `test_purge_guards` 偶发失败隔离 2.42s 通过后重跑。
- **有效全量双跑**：`pytest -n 2`，845 passed + 3 skipped，**470.29 / 463.80 秒**，均低于 600s；发布闸六项 PASS。
