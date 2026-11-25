# schemas.md — 运行产物 Schema（8 个）

schema-check.py 按本文件校验 `runs/<run_id>/` 下的 8 个产物。
每个产物一节，```json 块内 `required` 为必填字段，`enums` 为「字段名 → 允许值」
（对嵌套 dict/list 递归生效）。改本文件必须同步 schema-check.py 的产物清单。

## step2_collect.json

```json
{"required": ["repo", "range", "files", "source_lines", "commits"]}
```

## step3_risk.json

```json
{"required": ["regions", "overall"], "enums": {"level": ["高", "中", "低"]}}
```

## step4_dispatch.json

```json
{"required": ["dimensions_enabled", "dimensions_skipped"]}
```

## step5_findings.json

```json
{"required": ["findings"], "enums": {"severity": ["高", "中", "低"], "confidence": ["高", "中", "低"]}}
```

## step6_verification.json

```json
{"required": ["adopt", "reject"]}
```

## step7_summary.json

```json
{"required": ["change_summary", "test_suggestions", "risk"]}
```

## step8_backverify.json

```json
{"required": ["uncovered", "crosschecked"]}
```

## checkpoint.json

```json
{"required": ["last_complete_step", "rounds_used"]}
```

## 脱敏兜底

任一产物的任意字符串值若命中密钥形态（password/api_key/secret/token 赋值、
AKIA、Bearer、mysql 连接串、JWT、私钥块）且未被脱敏为 `<redacted>`，直接判失败。
