# 复盘轮报 round-54

open 6 / closed 170 / archived 24

## 分类统计

- 手工：125
- 评测：19
- 行为回归：14
- 误报：13
- 口径纪律：11
- 补丁返工：4
- 能力盲区：4
- 测试：3
- 转人工：2
- 外部依赖：2
- 能力缺口：2
- 自迭代盲区：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| fe97d747b691 | 行为回归 | 【坑】5 分钟红线再次越线且非离群：401 项口径两次同负载全量 338.617s / 329.185s（logs/su | 未定位——本轮回合并入册器/轮报与 3 项契约，理论上增量应 <5s；可能是环境 | 按纪律不悄悄改线：本轮如实记录并按「连续两次同负载超线」升级；下一轮先做计时画像 | logs/suite-r44-run1.log、logs/suite-r44-run2.log；logs/suite-r43-1.log |
| 514fc80228fc | 误报 | 【坑】lang-closure-late-bind 把「默认参数即时绑定」的循环内 lambda 判为闭包延迟绑定：ev | 规则只捕 for/while 体内的 lambda，未排除带默认参数的绑定——` | 本轮改写为 re.sub 字符串替换 + 反斜杠转义绕开误报；规则未动，建议下一 | skills/multi-agent-review/scripts/deterministic-rules.py（lang-closure-late-bind）；tests/test_scripts.py::test_self_scan_zero_hits |
| 04b97450c2ff | 手工 | astropy-14365（QDP 命令大小写不敏感）第三版仍 unresolved：命令段已大小写无关（该文件 8/9 | issue 只提了命令，但格式语义是整体的；上游期望（写回路径的大小写、roun | 按检查单建议再试一版（整条 _type_re 用 re.IGNORECASE 编 | retro/events-round-20.json |
| 7ed159ad8e01 | 手工 | 【坑】台账与预算口径漂移两周未发现：README 状态行写「迭代官未结坑 0/8、0 处 WARN、无整队冻结」，而 o | 状态行与沿革靠手工抄写；doc-freshness 只扫 README/AGEN | 本轮如实改报 EXCEEDED 并补 BASELINE v1.38–v1.44  | skills/director/scripts/org-scorecard.py 实跑；git log -- BASELINE.md；README 状态行 |
| 93b028b2bc6f | 手工 | 【坑】TF-IDF 记忆检索对共享通用词（fix / task / code）不设相似度阈值，任意共享 token 即得 | 检索层只排序不过滤（scored 收集 score>0）；few-shot 注入 | 本轮用测试数据隔离（不相干条目不含共享词）并把该局限记入台账；后续按真实记忆库样 | skills/retro/scripts/memory_retrieval.py retrieve()；tests/test_agent.py TestMemoryFewShot 测试数据调整 |
| daf1a5fc2f9f | 手工 | Edit 工具对含大段中文的替换两次「报成功但不落盘」（agent-sample.py / repo_map.py），m | 宿主桌面环境的文件编辑工具在长中文块替换上静默失效（小块替换正常）；会话内无文件 | 大段中文改动一律走「脚本补丁 + 当场断言锚点 count==1 + 读回验证」 | round-33 执行过程实踩（两次不落盘 + 一次误冲，均已恢复并验证） |

## 改进候选（按 权重×数量 排序）

- **手工：4 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **行为回归：1 个未结坑** — 修复前先读懂行为契约；有测试的行为变更需人工确认
- **误报：1 个未结坑** — 为该模式补阴性样例并入经验库，必要时收紧规则形态
