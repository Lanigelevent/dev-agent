# 复盘轮报 round-66

open 4 / closed 200 / archived 24

## 分类统计

- 手工：133
- 口径纪律：22
- 评测：20
- 行为回归：18
- 误报：14
- 补丁返工：4
- 能力盲区：4
- 外部依赖：3
- 测试：3
- 转人工：2
- 能力缺口：2
- 门禁自举：2
- 自迭代盲区：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| fe97d747b691 | 行为回归 | 【坑】5 分钟红线再次越线且非离群：401 项口径两次同负载全量 338.617s / 329.185s（logs/su | 未定位——本轮回合并入册器/轮报与 3 项契约，理论上增量应 <5s；可能是环境 | 按纪律不悄悄改线：本轮如实记录并按「连续两次同负载超线」升级；下一轮先做计时画像 | logs/suite-r44-run1.log、logs/suite-r44-run2.log；logs/suite-r43-1.log |
| 022913d6c6a4 | 误报 | 【坑】Mimosa 宿主 L3 扫描把 gitignored 的评测夹具（reports/_work/tooling 的 | 宿主扫描器不区分被 git 跟踪内容与 gitignored 数据目录，扫描面大 | commit 前把 reports/_work/tooling 临时移出工作树（ | Mimosa 拦截消息（173 high 全部指向 reports/_work/tooling/go/src/runtime/crash_test*.go）、git check-ignore 确认该目录 gitignored |
| daf1a5fc2f9f | 手工 | Edit 工具对含大段中文的替换两次「报成功但不落盘」（agent-sample.py / repo_map.py），m | 宿主桌面环境的文件编辑工具在长中文块替换上静默失效（小块替换正常）；会话内无文件 | 大段中文改动一律走「脚本补丁 + 当场断言锚点 count==1 + 读回验证」 | round-33 执行过程实踩（两次不落盘 + 一次误冲，均已恢复并验证） |
| 8cfbcaf7d227 | 外部依赖 | 【坑】ZCode 宿主 shell 向子进程注入 PYTHONUTF8=1 与 PYTHONIOENCODING=utf | 宿主运行环境的全局环境变量注入改变 Python 启动模式，套件契约（cp936 | ZCode 会话内运行全量套件（及任何依赖 locale 解码的子进程链）一律以 | logs/suite-r65-run1.log（两轮红跑）、tests/test_live_sample.py::_pid_alive、docs/PROGRESS.md 契约测试行 |

## 改进候选（按 权重×数量 排序）

- **行为回归：1 个未结坑** — 修复前先读懂行为契约；有测试的行为变更需人工确认
- **误报：1 个未结坑** — 为该模式补阴性样例并入经验库，必要时收紧规则形态
- **手工：1 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **外部依赖：1 个未结坑** — 纳入下一轮改进候选
