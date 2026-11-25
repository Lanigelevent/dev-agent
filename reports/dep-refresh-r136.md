# round-136：依赖刷新第七跑——零升级 + 三引擎矩阵零漂移（2026-11-11）

## 结论先行

- **零升级（14/14 tracker 面）**：ruff / libcst / tree-sitter×4 / ast-grep-py /
  pytest / pytest-xdist / coverage / hypothesis / click / pandas / tzdata
  清华镜像 --upgrade --dry-run --refresh 全部 no changes（ruff 抽验 238ms
  真网络解析，绕 uv 缓存）；r120 以来各刷新轮已把 tracker 面刷到
  镜像最新，上游三日窗口内无新发布。
- **三引擎矩阵零漂移**：ruff 970/480/250、astgrep 逐字段 identical、
  libcst 整字典 identical（入仓 JSON vs 全新生成，落盘产物复验——
  首次管道直比出现瞬时 False 伪影，落盘复验为真，已记录比对方法教训）。
- **降级记录**：无（主镜像一次命中，无降级）。

## 版本真值（r136 落盘）

- reports/_work/dep-inventory-r136.json：14 项 tracked 真值
  （ruff 0.17.4 / libcst 1.9.0 / tree-sitter 0.26.1 / ast-grep-py 0.51.1 /
  pytest 9.2.0 / pytest-xdist 3.8.0 / coverage 7.17.2 / hypothesis 6.170.15 /
  click 8.5.1 / pandas 3.1.1 / tzdata 2026.6 等）；scipy、semgrep 未装
  如实 N/A（isolated 档，硬约束 1）。
- click 8.5.1 / pandas 3.1.1 / tree-sitter 0.26.1 / tzdata 2026.6 为 r120+
  中间刷新轮次成果，本轮确认仍为镜像最新。

## 比对方法教训（如实）

- 引擎矩阵对比曾出现「管道直比 False、落盘复验 True」的瞬时伪影——
  对比基线一律以**落盘产物**为准，管道直比仅作初筛；与易错点 4/8 同族
  （结论要可复算）。

## 后续

- 第 97 条候选不变：①F2P / precision-gate 复测回血；②D-052 执行面精修；
  ③下一刷新锚点（第 140 轮）按原锚执行。
- **证据**：reports/_work/dep-inventory-r136.json；/tmp/r136/{ruff,astgrep}.json
  与 libcst-stdout.json（临时目录，不入库）；本轮执行记录。
