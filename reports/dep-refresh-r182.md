# round-182：依赖刷新第十二跑——零升级 + 三引擎矩阵零漂移（2026-11-18）

## 结论先行

- **零升级（14/14）**：清华主镜像逐项 `--upgrade --dry-run --refresh` 全部 `rc=0`、除下列传递提议外 no changes；无降级、无国际直连回退。
- **拒 1 项传递升级**：`pandas` dry-run 连带提议 `numpy 2.5.4 → 2.5.5`——numpy 不在 14 项 tracker 面，按 r173 同型先例不静默升级，如实记录。
- **三引擎矩阵零漂移**：ruff 973/481/251、ast-grep 29 条、libcst 2/2/2 与入仓 JSON 全等（落盘产物比对纪律延续）。
- **版本真值**：ruff 0.17.5 / libcst 1.9.0 / tree-sitter 0.26.1（+python 0.25.0 / typescript 0.23.2 / go 0.25.0）/ ast-grep-py 0.51.3 / pytest 9.2.0 / pytest-xdist 3.8.0 / coverage 7.17.3 / hypothesis 6.170.15 / click 8.5.1 / pandas 3.1.1 / tzdata 2026.6。
- 契约 794 / 脚本 86 / 工具 16 不变；对外口径不变（0.42% / 宿主臂 unavailable）。

## 证据与后续

- `reports/_work/dep-inventory-r182.json`（14 项真值 + probes + decisions 块）；
- 矩阵落盘 `reports/_work/m182/{ruff/ruff-matrix.json,astgrep/astgrep-matrix.json,libcst-utf8.json}`（工作产物，不入库）；
- 下一依赖刷新锚点按 ~10 轮节奏（约 r192）；本轮无代码变更，仅版本交付。
