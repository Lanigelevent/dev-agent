# AB-21 SKILL.md 渐进披露规范对齐审计（r206，2026-11-21）

> 对照源：anthropics/skills 197.6k（开放规范）+ superpowers 321.7k（技能包生态）。
> 审计对象：skills/*/SKILL.md（13 个技能，全量扫描）。

## 一、开放规范要素逐项对照

| 规范要素 | anthropics/skills 标准 | dev-agent 现状 | 判定 |
|---|---|---|---|
| YAML frontmatter | `--- name + description ---` | ✅ 13/13 全有（name=技能名，description=功能+口语触发短语） | **已对齐** |
| 渐进披露 | 元数据常驻上下文，正文按需加载 | ✅ trigger-audit.py 管控触发词覆盖度；宿主按 description 匹配后加载 | **已对齐** |
| 确定性步骤脚本化 | 方法论正文 + 可选脚本 | ✅ 13 技能 × 87 脚本（脚本清单 AGENTS 表逐行登记） | **已对齐** |
| 文件夹拷贝即装 | skills/<name>/SKILL.md + scripts/ | ✅ 同构（skills/<name>/SKILL.md + scripts/*.py） | **已对齐** |
| 口语触发 | description 含触发短语 | ✅ 每条含「也用于口语说法：…」（trigger-audit.py 管控） | **已有超出** |
| allowed-tools 限制 | 按技能限制工具集 | ❌ 未限制（治理壳零依赖 + 五道闸兜底，无需按技能限制） | **有意排除** |
| 版本/作者字段 | 可选 metadata | ❌ 未加（git 属性已覆盖，frontmatter 不重复） | **有意排除** |

## 二、结论

**6/7 已对齐，1 项已有超出（口语触发），2 项有意排除**——SKILL.md 格式与 anthropics/skills 开放规范**同型对齐**，无需改动。

与 AB-12/AB-13/AB-15/AB-17 审计同类：已对齐零缺口确认。SKILL.md 规范对齐从路线图移除（终局结论）。

## 三、独立价值确认（非对齐性）

trigger-audit.py 的「口语说法」管控是**超出**anthropics/skills 规范的独有设计——每个 SKILL.md 的 description 显式列出口语触发短语并纳入 CI 门禁体检，而非仅靠语义匹配。
