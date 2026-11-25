# round-117：依赖刷新第四跑——零升级 + 引擎矩阵复核（2026-11-08）

## 结论先行

- **零升级**：11 个跟踪项（ruff / libcst / tree-sitter×4 / ast-grep-py /
  pytest / pytest-xdist / coverage / hypothesis）清华镜像 --upgrade --dry-run
  全部 no changes；ruff/pytest/hypothesis 三项加 --refresh 绕缓存真联网复验
  （321ms 实际索引解析）仍零变化——r110（2026-11-07）刚刷过 pytest 9 等
  9 项，上游一日内无新发布。
- **引擎矩阵口径不变**：ruff 970/480/250、libcst 2/2/2、astgrep 规则数与
  安全档逐字段 identical（三矩阵全新生成 vs 入仓 JSON 对比，零漂移）。
- **降级记录**：无（主镜像一次命中，无降级）。

## 盘点基线（r116 备好的真值）

- .venv 110 个已装发行版；跟踪 18 项见 reports/_work/dep-inventory-r116.json。
- scipy、semgrep 未装如实 N/A（isolated 档不进运行时 import 链，硬约束 1）。

## 后续

- round-118+ 候选不变（第 77 条①全量 n=1000 续跑 / ②第三方 judge 待 key）。
- **证据**：/tmp/r117/{ruff,astgrep}.json（临时目录，不入库）+ libcst stdout
  比对（一次性内联）；uv dry-run 输出见本轮执行记录。
