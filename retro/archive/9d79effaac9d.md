# 案例 9d79effaac9d：审核人批准书闸定义了校验函数但没插进 fix-apply 调用链，REJECTED 批准书仍 APPLIED

- 类别：行为回归 | 类型：优秀案例 | 状态：verified
- 档案链接：tests/test_repair.py::test_apply_requires_approval

## 详细摘抄

安全闸门三件套：定义 + 调用 + 负路径测试（篡改/缺批准书/REJECTED 三态）齐全才算完成

## 教训与对策

安全闸门三件套：定义 + 调用 + 负路径测试（篡改/缺批准书/REJECTED 三态）齐全才算完成

## 验收口径

tests/test_repair.py::test_apply_requires_approval 覆盖三态拒绝

_整理时间：2026-10-24（档案员）_
