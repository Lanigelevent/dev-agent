# 依赖刷新第十八跑提前提案（round-230 提案，round-231 裁定：不提前）

> **裁定（2026-11-26）**：总监接受提案建议——**不提前跑第十八跑**，维持原锚点约 r236。若期间批准新增依赖、镜像缺包或安全公告，再临时提前。

## 背景

r226 已执行第十七跑（零直接升级、三矩阵零漂移）；按 ~10 轮节奏，第十八跑原锚点约 r236。item 193① 询问是否提前提案。

## 只读实测（不安装、零变更）

清华主镜像 `uv pip install --upgrade --dry-run --refresh` 逐项探测 11 个直接依赖（pyproject + dev，与 r220/r226 同口径）：

| 结果 | 数量 | 包 |
|---|---:|---|
| 直接依赖无变化 | 8 | ruff 0.17.6 / tree-sitter 0.27.0 / tree-sitter-python 0.25.0 / tree-sitter-typescript 0.23.2 / tree-sitter-go 0.25.0 / ast-grep-py 0.51.3 / coverage 7.17.5 / hypothesis 6.170.17 |
| 仅非跟踪传递升级 | 3 | libcst→pyyaml 6.0.3→6.0.4；pytest / pytest-xdist→packaging 26.3→26.4 |

`pyyaml` / `packaging` 不在 11 项 tracker 面，按 r220/r226 先例**拒绝静默升级**。无降级、无国际直连回退，无镜像缺包。原始探测：`reports/_work/dep-probe-r230.json`（gitignored 工作产物）。

## 建议

**不提前跑第十八跑**：镜像与 r226 时相比无新增直接漂移，提前跑只会重做同样的 dry-run 与矩阵校验，净收益为零；维持原锚点约 r236。若期间总监批准新增依赖或出现镜像缺包/安全公告，再临时提前。

## 边界

- 本轮只写案，不改 pyproject / .venv / uv.lock，不 bump 版本；对外口径不变（0.42% / 宿主臂 unavailable）。
- 依赖锚点、MCP cancel 竞态、D-052 触发线仅随本轮双跑观察，未再现不预判。
