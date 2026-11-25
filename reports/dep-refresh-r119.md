# round-119：依赖刷新第五跑——7 项小升 + pytest 降级拒绝 + 引擎矩阵零漂移（2026-11-09）

## 结论先行

- **7 项升级（全部无降级、主镜像一次命中）**：click 8.5.0→8.5.1、mypy-extensions 1.1.0→1.2.0、pandas 3.1.0→3.1.1、platformdirs 4.13.5→4.14.5、python-dateutil 3.0.0→**4.0.0**（大版本，双跑验证）、typeshed-client 2.14.0→2.15.0、tzdata 2026.5→2026.6。
- **pytest 9.2.0 维持不变（拒绝 8.4.2 降级）**：清华镜像 dry-run 在 18 跟踪项整体解析时提议把 pytest 降到 8.4.2——根因是 pynguin 0.48.0 的安装元数据硬约束 `pytest>=8.3.5,<9.0.0`（已从 .venv 实读 dist-info METADATA 证实）。round-110 有意落地 pytest 9（round-117 复验零变化）；pynguin 仅作 isolated 档 subprocess 隔离基线（不进运行时 import 链，硬约束 1，D-022 边界同款），该约束与本仓套件无关。单独 dry-run pytest 显示 "Would make no changes"（9.2.0 即镜像最新），不接受降级。
- **--refresh 绕 uv 缓存真联网复验**：ruff / pytest / hypothesis 三项零变化。
- **其余跟踪项零升级**：ast-grep-py 0.51.1、coverage 7.17.2、hypothesis 6.170.15、libcst 1.9.0、mpmath 1.4.1、networkx 3.7、numpy 2.5.4、packaging 26.3、pynguin 0.48.0、pytest 9.2.0、pytest-xdist 3.8.0、ruff 0.17.4、tree-sitter 0.26.0 / tree-sitter-go 0.25.0 / tree-sitter-python 0.25.0 / tree-sitter-typescript 0.23.2。scipy、semgrep 未装如实 N/A（isolated 档不进运行时 import 链）。
- **引擎矩阵口径不变**：ruff 970/480/250、libcst 2/2/2、ast-grep 29（安全档 2），三矩阵全新生成对比入仓 JSON——ruff JSON 等价（仅尾换行差）✓、ast-grep 逐字节 identical ✓、libcst JSON 等价 ✓，零漂移。
- **双跑全绿**：**436.193 / 395.945 秒**（`logs/suite-r119-run1/2.log`，688 项全绿，各 1 skip）；升级集（含 python-dateutil 大版本）双跑验证通过。
- **降级记录**：无（主镜像一次命中，无降级）。

## 盘点基线（r116 备好的真值 reports/_work/dep-inventory-r116.json）

.venv 110 个已装发行版；本轮对 18 个跟踪项逐项核对（镜像 simple 索引 PEP 503 逐一确认最新发布 + uv dry-run 解析 + --refresh 真联网复验）。

## 过程备注

- 上一交接点踩坑记录（本轮日志按 r117 同款口径 cmd /c 落盘为 GBK 字节，gate 按 utf-8 errors=replace 读取，ASCII 证据行完整可解析；曾有一版日志被误判 GBK→utf-16 重写损毁，按此口径全套重跑补救）。
- 升级落地后 .venv 现值：click 8.5.1 / mypy-extensions 1.2.0 / pandas 3.1.1 / platformdirs 4.14.5 / python-dateutil 4.0.0 / typeshed-client 2.15.0 / tzdata 2026.6。
- 与 round-110 的 pytest 9 裁决一致：pynguin <9 约束不构成降级理由；若未来 pynguin 升级解除 pytest<9 约束，届时复评。

## 后续

- round-120 依赖刷新仍按锚点（第 79 条①）；round-119 已提前消化磁盘级 7 项。
- pytest 9.2.0 + pynguin 0.48.0 并存属既有状态（pynguin 仅 isolated 档 subprocess），如需彻底一致应在 isolated 档移除或升级 pynguin 时裁决（总监项）。
