# round-173：依赖刷新第十一跑——ast-grep-py 0.51.2→0.51.3（清华镜像）+ 三引擎矩阵零漂移（2026-11-18）

## 结论先行

- **升 1 项**：`ast-grep-py 0.51.2 → 0.51.3`（清华镜像 `--upgrade --dry-run --refresh` 发现，patch 升级；装后二次 dry-run 已无 "Would install"，即镜像最新）。
- **拒绝 1 项传递升级**：`pandas` dry-run 连带提议 `numpy 2.5.4 → 2.5.5`——numpy 不在 r173 的 14 项 tracker 面，按纪律不静默升级传递依赖，如实记录（`reports/_work/dep-inventory-r173.json` 的 decisions 块）。
- **tracker 面 14/14 探测完成**：ruff / libcst / tree-sitter×4 / ast-grep-py / pytest / pytest-xdist / coverage / hypothesis / click / pandas / tzdata——除上述 1 升 1 拒外均 no changes；全部 `rc=0`，无降级。
- **三引擎矩阵零漂移**：ruff **973 / 481 / 251** JSON 全等；ast-grep **29 条** identical（版本升级后规则集未变）；libcst **2/2/2** 矩阵全等（注意 libcst matrix 子命令输出包裹在 `{"ok": true, "matrix": {...}}` 中，比对取 `.matrix`）。
- **降级记录**：无（清华主镜像一次命中，无国际直连回退）。
- **比对方法纪律**：以落盘产物为准（r136 管道直比瞬时伪影的教训延续）；PowerShell `>` 重定向会把 matrix stdout 写成 UTF-16，故 libcst 用 Python subprocess 捕获 UTF-8 落盘。

## 版本真值（r173 落盘）

`reports/_work/dep-inventory-r173.json` 14 项 installed truth：ruff 0.17.5 / libcst 1.9.0 / tree-sitter 0.26.1 / tree-sitter-python 0.25.0 / tree-sitter-typescript 0.23.2 / tree-sitter-go 0.25.0 / ast-grep-py **0.51.3** / pytest 9.2.0 / pytest-xdist 3.8.0 / coverage 7.17.3 / hypothesis 6.170.15 / click 8.5.1 / pandas 3.1.1 / tzdata 2026.6。
pyproject 约束（`ast-grep-py>=0.4` 等）不变，无需改依赖表；scipy / semgrep / pynguin 不在 tracker 面，如实 N/A（isolated 档，硬约束 1）。

## 证据与后续

- 矩阵落盘：`reports/_work/m173/{ruff.json/ruff-matrix.json, astgrep.json/astgrep-matrix.json, libcst-utf8.json}`（临时工作产物，不入库）。
- 后续：第 134 条候选不变（②MCP 异步扩面提案 / ③评测口径复核）；下一依赖刷新锚点按 ~10 轮节奏（约 r183）。
