# round-226：剩余缓存清理 1.92GB + 依赖刷新第十七跑（v2.101.0）

## 任务① 缓存清理（用户裁定 item 189①）

- 删除 1.92 GB / 216,155 文件：`verified-runs-v99/v103/v107/v108` 0.947 GB、`swe-work` 0.642 GB、
  `live-runs-extra` 0.117 GB、`live-work` 0.054 GB、`swe-out/harness` 0.107 GB、`swe-out/django__django-14999` 0.053 GB。
- 保留：imagecache、swe-repos、pro-work、live-cache、swrenbench/reviewbench、swe-out 根索引、全部受控文件与日志。
- 证据：`reports/cleanup-datasets-r226.md`。清理与套件未并发（遵守 r223 操作纪律）。

## 任务② 依赖刷新第十七跑

- 清华主镜像一次命中、零降级、无国际直连回退；**11 个直接依赖**（pyproject + dev）逐项 `--upgrade --dry-run --refresh`：8 项 no changes，3 项仅报**非跟踪传递升级**
  （`pyyaml 6.0.3→6.0.4` 由 libcst 连带；`packaging 26.3→26.4` 由 pytest / pytest-xdist 连带）——按 r220 同型先例拒绝，不静默升级。
- 真值：ruff 0.17.6 / libcst 1.9.0 / tree-sitter 0.27.0（+python 0.25.0 / typescript 0.23.2 / go 0.25.0）/ ast-grep-py 0.51.3 /
  pytest 9.2.0 / pytest-xdist 3.8.0 / coverage 7.17.5 / hypothesis 6.170.17。click/pandas/tzdata 已不在 pyproject，本次从 tracker 面移除（r220 已是 11 项口径）。
- **三引擎矩阵零漂移**：ruff 973/482/250、astgrep 29/2/2、libcst deep-equal（落盘产物比对纪律）。
- 证据：`reports/_work/dep-inventory-r226.json`、`reports/_work/m226/`（工作产物，不入库）。

## 结论

零直接升级、零降级；契约 849 / 脚本 90 / 工具 16 不变；对外口径不变（0.42% / 宿主臂 unavailable）。版本 **v2.101.0**（bump-version + sync-counts）。
