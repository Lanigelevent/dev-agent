# 复盘轮报 round-37

open 11 / closed 112

## 分类统计

- 手工：84
- 行为回归：12
- 误报：11
- 口径纪律：6
- 补丁返工：4
- 转人工：2
- 外部依赖：1
- 能力盲区：1
- 能力缺口：1
- 自迭代盲区：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 09913b0339ac | 行为回归 | round-32 新写的 task-pipeline.py --dispatch 首跑即撞死：org-route --k | 技能脚本迁移到别的 skill 目录后（runner.py → orchestr | review.members 全部改为相对 skill 根的路径清单（orche | round-32 task-pipeline --dispatch 首跑（reports/_work/tp-disp.json 首版报错）与 org-route 直接复现对照 |
| 13b3475060fd | 误报 | 死代码扫描对新代码报 5 条：task-pipeline 的三个 store_true 模式旗标判 dead_switc | 两个同源写法：模式分发用 getattr(argv, m) 动态取属性，AST  | getattr 改为字面元组遍历（("from_intent", argv.fr | round-32 死代码扫描（tests/test_scripts.py::test_dead_code_scan_clean_and_catch） |
| 0144f7dba446 | 手工 | 全量传播：版本 1.37.0→1.38.0，测试 335→340，README/DEVELOPMENT/BASELINE | - | - | reports\_work\events-round-37.json |
| 04b97450c2ff | 手工 | astropy-14365（QDP 命令大小写不敏感）第三版仍 unresolved：命令段已大小写无关（该文件 8/9 | issue 只提了命令，但格式语义是整体的；上游期望（写回路径的大小写、roun | 按检查单建议再试一版（整条 _type_re 用 re.IGNORECASE 编 | retro/events-round-20.json |
| 0a290edc8ade | 手工 | sympy-13146（Float 指数的 evalf 结果不抵消）第三版定位并修复：`_aresame` 只用 `!= | evalf 后 x**2.5 的指数是 prec 53（默认精度，未被重新 ev | `_aresame` 追加 Float 精度比较（精度不同即视为不同）→ Mul | retro\events-round-26.json |
| 1336d8bf9067 | 手工 | 扩样到 n=18：sklearn-14087 / sklearn-14092 / matplotlib-22711 /  | 首轮补丁常只修到症状层：14087 两处根因叠加（分支判断用了构造参数、list | 把 harness 反馈当规格用：失败时分桶信息（哪几个参数化过了、哪几个没过） | retro\events-round-24.json |
| 64da6e7f5c5b | 手工 | 候选补丁排序器落地：按测试通过>失败>跳过>空补丁四档排序，同档内校验ok优先+最小补丁原则，最优候选替代最后编辑态交付 | - | - | reports\_work\events-round-37.json |
| b0a450995f3d | 手工 | 定位上游语义的一个可复用手法：拿**新版库的实际行为**当规格反推根因，比逐行读上游补丁更快也更不容易被实现细节带偏 | 两处根因都藏在「同一个数学对象在两处的精度/结构不同」这种细节上（sympy 的 | sympy-13146：本地装一份新版 sympy 实测同一段代码的输出差异（1 | retro\events-round-26.json |
| b0aa7d5f803e | 手工 | 新增 5 项契约测试（TestCandidateRanking）：单候选直通/测试通过优先/空补丁排末尾/最小补丁胜出/ | - | - | reports\_work\events-round-37.json |
| daf1a5fc2f9f | 手工 | Edit 工具对含大段中文的替换两次「报成功但不落盘」（agent-sample.py / repo_map.py），m | 宿主桌面环境的文件编辑工具在长中文块替换上静默失效（小块替换正常）；会话内无文件 | 大段中文改动一律走「脚本补丁 + 当场断言锚点 count==1 + 读回验证」 | round-33 执行过程实踩（两次不落盘 + 一次误冲，均已恢复并验证） |
| fce2844cf2c9 | 手工 | 多候选补丁快照收集机制落地：code-task.py 每次成功 edit + 测试后保存补丁快照到 candidates | - | - | reports\_work\events-round-37.json |

## 改进候选（按 权重×数量 排序）

- **手工：9 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **行为回归：1 个未结坑** — 修复前先读懂行为契约；有测试的行为变更需人工确认
- **误报：1 个未结坑** — 为该模式补阴性样例并入经验库，必要时收紧规则形态
