# 复盘轮报 round-31

open 7 / closed 93

## 分类统计

- 手工：74
- 行为回归：11
- 误报：10
- 补丁返工：4
- 转人工：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| e62d848a7d06 | 误报 | 同一个 tests/test_scripts.py 模块，两次全量跑出不同结论：首轮 TestOptimizations | runner.py 带分钟级评审预算与逐步超时，开局时上一轮残留的后台负载（JV | 全量验收固定两条：① 跑之前确认没有并发重负载（后台任务全部先收），② 同一模块 | round-28 全量复跑 |
| 04b97450c2ff | 手工 | astropy-14365（QDP 命令大小写不敏感）第三版仍 unresolved：命令段已大小写无关（该文件 8/9 | issue 只提了命令，但格式语义是整体的；上游期望（写回路径的大小写、roun | 按检查单建议再试一版（整条 _type_re 用 re.IGNORECASE 编 | retro/events-round-20.json |
| 0a290edc8ade | 手工 | sympy-13146（Float 指数的 evalf 结果不抵消）第三版定位并修复：`_aresame` 只用 `!= | evalf 后 x**2.5 的指数是 prec 53（默认精度，未被重新 ev | `_aresame` 追加 Float 精度比较（精度不同即视为不同）→ Mul | retro\events-round-26.json |
| 1336d8bf9067 | 手工 | 扩样到 n=18：sklearn-14087 / sklearn-14092 / matplotlib-22711 /  | 首轮补丁常只修到症状层：14087 两处根因叠加（分支判断用了构造参数、list | 把 harness 反馈当规格用：失败时分桶信息（哪几个参数化过了、哪几个没过） | retro\events-round-24.json |
| 5ca8976ee29f | 手工 | 新增 16 项测试后，门禁 F5（doc-freshness）立刻变红：README 与 docs/DEVELOPMEN | 测试计数是共享事实源的多处引用，加测试的动作与改文档的动作不在同一次编辑里；F5 | 「谁改计数谁全量传播」：同一轮里改完代码就同步 README 状态行 / 目录说 | round-28 doc-freshness 实跑 |
| 7122b4b567a4 | 手工 | sympy-13437 长期未过却没进台账：F2P `test_bell` 在 agent7/agent8/agent1 | 未过实例只在正文叙述里记录，没有与「扩样余量」这类坑条目建立一一对应；口径复算时 | 本轮把三个未过实例（astropy-14365 / django-11019 / | retro\events-round-24.json |
| b0a450995f3d | 手工 | 定位上游语义的一个可复用手法：拿**新版库的实际行为**当规格反推根因，比逐行读上游补丁更快也更不容易被实现细节带偏 | 两处根因都藏在「同一个数学对象在两处的精度/结构不同」这种细节上（sympy 的 | sympy-13146：本地装一份新版 sympy 实测同一段代码的输出差异（1 | retro\events-round-26.json |

## 改进候选（按 权重×数量 排序）

- **手工：6 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **误报：1 个未结坑** — 为该模式补阴性样例并入经验库，必要时收紧规则形态
