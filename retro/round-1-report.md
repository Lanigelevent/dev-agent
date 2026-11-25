# 复盘轮报 round-1

open 4 / closed 0

## 分类统计

- 手工：3
- 行为回归：1

## 未结坑明细

| ID | 类别 | 坑 | 根因 | 对策 | 来源 |
|---|---|---|---|---|---|
| 9d79effaac9d | 行为回归 | 审核人批准书闸定义了校验函数但没插进 fix-apply 调用链，REJECTED 批准书仍 APPLIED | 编辑冲突后未核对调用点，职责分离闸门缺少负路径测试 | 安全闸门必须先写负路径测试（篡改/缺批准书/REJECTED 三态）再算完成 | retro\events-round-baseline.json |
| 07cf8ce1f8cc | 手工 | fix-apply 文档字符串与 SKILL.md 提及其他脚本的旗标拼写，被 doc-drift 参数漂移误判 | 不知道 doc-drift 会把同现脚本名与 --flag 的行当参数断言 | 写文档时散文体不出现 --旗标 拼写，git 旗标改文字描述 | retro\events-round-baseline.json |
| d2c22ec68c70 | 手工 | 测试 fixture 的测试文件未提交导致工作树脏，闸门守卫把行为回归测试用例本身拦下 | 五道闸前置条件与测试夹具准备顺序冲突 | 凡进五道闸链路的夹具先提交再送审 | retro\events-round-baseline.json |
| ea52d73470a7 | 手工 | 污点引擎汇点表用裸名 system，实际调用全路径是 os.system，导致漏报 | 汇点键与 _call_fullname 产物口径不一致，先写引擎后补用例 | 新检测引擎一律先写正反双向用例再实现（红线 6 顺序化） | retro\events-round-baseline.json |

## 改进候选（按 权重×数量 排序）

- **手工：3 个未结坑** — 纳入下一轮改进候选，明确责任与验收口径
- **行为回归：1 个未结坑** — 修复前先读懂行为契约；有测试的行为变更需人工确认
