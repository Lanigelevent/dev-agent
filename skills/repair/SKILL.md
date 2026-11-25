---
name: repair
description: 修复团队：凭审核人工单出补丁，经五道闸落盘到修复分支，失败自动回滚。也用于口语说法：把这些发现自动修掉
---

# repair — 修复团队（凭工单施工，落盘过五道闸）

修复团队与评审团队分立，且只按审核人签发的工单干活：fix-patch.py 的唯一
输入是 work-order.json（闸 1 产物）。写被审仓库的脚本只有 fix-apply.py，
且必须通过五道闸：审核人批准书（approval.json，verdict=APPROVED 且 sha256
绑定当前补丁包）、工作树干净、HEAD 与补丁基线一致、git apply 预检通过、
落盘后逐文件重扫（原规则消失且无新增规则），任一道失败自动回滚。

38 条硬规则中仅 5 类可机械化修复（白名单见 fix-patch.py 的 AUTO_RULES）：
Python 可变默认参数、空 except 吞异常、闭包延迟绑定、is 字面量或 ==None 误用、
yaml.load 无 Loader。凭据类发现一律转人工：补丁会复制明文，违反产物红线。

## 脚本与用法

- fix-plan.py：修复分诊（只读，也是审核人闸 1 的分类依据）。
  `--findings <发现清单 JSON>`（必填）、`--repo <被审仓库>`（相对路径解析基准）。
  输出 fixable/manual 两张清单。
- fix-patch.py：补丁生成（被审仓库只读，只写 --out 产物目录）。
  `--order <工单 JSON>`、`--repo <被审仓库>`、`--out <产物目录>`，三个都必填。
  产出 patches/*.diff 与 fix-manifest.json（携带 order_id 供闸 2 绑定）。
- fix-apply.py：补丁落盘（唯一写仓库的脚本）。`--manifest <fix-manifest.json>`、
  `--repo <被审仓库>` 必填；`--approval <批准书>` 在 --apply 时必填；
  `--apply` 真正落盘（缺省仅预检，状态 PROPOSED）；`--undo` 撤销修复分支。

三方链路（评审发现清单为 findings.json 时；审核人侧见 approval 技能）：

```bash
py approve-plan.py --findings findings.json --repo <仓库> --out <审核产物目录>
py fix-patch.py  --order <审核产物目录>/work-order.json --repo <仓库> --out <补丁目录>
py approve-patch.py --order <工单> --manifest <补丁目录>/fix-manifest.json --repo <仓库> --out <审核产物目录>
py fix-apply.py --manifest <补丁目录>/fix-manifest.json --repo <仓库> --approval <批准书> --apply
```

## 结果判读

- fix-apply 退出码 0 且 state=APPLIED：修复在 review-fix/<id> 分支上，
  未合并；向用户转述分支名、commit 与验证细节，合并由用户决定。
- state=PROPOSED：预检通过（或前置失败说明），尚未写仓库。
- 退出码 1 且 state=ROLLED_BACK：落盘后扫描验证失败已自动回滚，
  把 error 与 details 转述给用户，不要重试同一补丁。
- 退出码 2：输入或前置条件不满足（无批准书、工作树不干净、HEAD 漂移、
  路径越界等），按提示处理后再来。

## 硬约束

- 除 fix-apply.py 外的脚本对被审仓库只读；补丁产物仅落 fix-patch.py 的产物目录。
- 不在脏工作树上落盘；HEAD 与 base_sha 不一致必须重新走闸。
- 修复分支永不自动合并；合并、撤销（--undo）由人工决定。
- 产物不得出现明文凭据：凭据类发现只进 manual 清单，不生成补丁。
- 补丁包任何字节变动后必须重新送审（批准书 sha256 绑定随即失效）。
