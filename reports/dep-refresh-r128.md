# round-128：依赖刷新第六跑——tree-sitter 0.26.1 补丁 + pytest 降级拒绝 + 引擎矩阵零漂移（2026-11-10）

## 结论先行

- **升 1 项**：tree-sitter 0.26.0 → **0.26.1**（清华镜像实测；engine 绑定同窗）。
- **pytest 9.2.0 维持不变（拒绝 8.4.2 降级）**：清华镜像整体 dry-run 提议把 pytest 降到 8.4.2——根因 pynguin 0.48.0 安装元数据 `pytest>=8.3.5,<9.0.0`（r119 已实读 .venv dist-info 证实）；单独 dry-run pytest 显示无变化（9.2.0 即镜像最新），r110 有意落地 pytest 9，pynguin 仅 isolated 档 subprocess 基线，该约束与本仓套件无关 → 降级被拒。
- **其余 17 跟踪项零升级**：ast-grep-py 0.51.1 / click 8.5.1 / coverage 7.17.2 / hypothesis 6.170.15 / libcst 1.9.0 / mpmath 1.4.1 / networkx 3.7 / numpy 2.5.4 / packaging 26.3 / pandas 3.1.1 / pynguin 0.48.0 / pytest-xdist 3.8.0 / ruff 0.17.4 / tree-sitter-go 0.25.0 / tree-sitter-python 0.25.0 / tree-sitter-typescript 0.23.2 / click 8.5.1（`--upgrade --dry-run` 输出，逐项一致）。
- **引擎矩阵零漂移**：ruff 970/480/250 / libcst 2/2/2 / ast-grep 29，三矩阵对比入仓 JSON 全 JSON 等价（ruff 970/480/250 identical、libcst via subprocess capture、astgrep identical）。
- **双跑全绿**：450.510 / 455.260 秒（`logs/suite-r128-run1/2.log`，各 1 skip）。
- **台账不变**：241 / closed 128 / open **0**（本轮前置结案全部 8 条未结坑（round-127 尾随 `f2cbdd9`））。
- **降级记录**：无（主镜像一次命中）。
- **版本 2.30.0**（bump-version 单命令 + sync-counts）；契约 **713 不变**；脚本 **83 不变**。

## 盘点基线（r126 后 .venv 108 + 18 跟踪项）

升级发动机矩阵已刷入 `reports/_work/m128/`。

## 过程口径

- 单跑树测试见 `logs/suite-r128-run1/2.log`，不作其他文档引用。
