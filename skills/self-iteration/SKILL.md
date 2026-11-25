---
name: self-iteration
description: 文档漂移十五问、六视角反向验证、死代码扫描与开局探针分诊。也用于口语说法：扫一下死代码、开局自检一下项目状态
---

# self-iteration — 自迭代与生产护栏探针

## 目的与边界

让智能体检查自己：文档漂移、反向验证可信度、死代码、收敛判定、
改进候选排序、端到端链路。所有检查器都要先通过反向验证
（造违规样例确认抓得住），漏检的检查器本身不可信。

边界约定：

- 检查器只读项目树，修复动作由人或编排层执行。
- 探针退出码语义固定：0 全绿 / 1 有信号 / 2 检查器故障，session-probe 聚合时不许混淆。
- 一切判定可机械复算；需要语义判断的部分标 needs_human。

## 何时用 / 何时不用

用：主流程步骤 0（开局探针）、步骤 8（perspective-scan 反向验证）、
每次改动后（doc-drift + dead-code）、自迭代循环（pick-candidate → 修 → convergence-check）。
不用：被审仓库的业务代码——本 skill 只扫项目自身。

## 脚本与用法

### doc-drift.py（文档漂移十五问）

```bash
python skills/self-iteration/scripts/doc-drift.py --root /path/dev-agent
```

十五问：

| # | 问题 | 判定方法 |
| --- | --- | --- |
| 1 | 孤儿脚本 | 脚本名是否被任何 md 提及 |
| 2 | 副本分叉 | 共享定义（redact/parse_diff 等）多副本是否一致 |
| 3 | 死代码 | 顶层函数定义后是否有引用 |
| 4 | 行为覆盖 | 脚本名是否出现在 tests/test_scripts.py |
| 5 | 主线接入 | 脚本名是否出现在 AGENTS.md |
| 6 | 退出码说明 | docstring 是否含「退出码」 |
| 7 | 审计覆盖 | AGENTS.md 是否提及 audit-log |
| 8 | 问数表述 | 规则/维度/边界/问 的计数是否与基线一致 |
| 9 | 硬编码行数 | 文档散落的 SKILL.md 行数断言是否与实际一致 |
| 10 | 参数漂移 | docstring 与 SKILL.md 的 flags 是否都在 argparse 里定义过 |
| 11 | 孤儿 references | references/ 文件是否被文档引用 |
| 12 | 行数基线 | BASELINE 行数表 vs 实际 wc -l |
| 13 | 基线常量 | 权重/维度数/规则数/边界类别数 vs 脚本 ast 提取值 |
| 14 | args 覆盖 | agent.json args 每个键是否被脚本或 AGENTS.md 消费 |
| 15 | README 引用 | README/AGENTS 里的 skills/...py 路径是否真实存在 |

退出码：0 全绿；1 有待处理项；2 根目录非法。
第 2 问的共享定义清单是契约：redact、SECRET_PATTERNS、HUNK_RE、parse_diff、
locate_agent_json、load_args——多副本必须逐字符一致（归一化空白后比对）。

### perspective-scan.py（六视角反向验证）

```bash
python skills/self-iteration/scripts/perspective-scan.py --findings findings.json --diff-file change.diff
python skills/self-iteration/scripts/perspective-scan.py --self-check
```

六视角：证据真实性、因果一致性、重复检测、范围越界、误报模式、完备性。
可机械判定部分：证据是否在 diff 原文、定位是否在 hunk 范围、定位+描述是否重复、
是否命中误报模式库、hunk 覆盖空洞（提示级）。
`--self-check` 内置四类篡改样例（伪造证据/越界/重复/干净项），
检查器漏检任何一类即退出 1——检查器先自证可信再上岗。

### dead-code-scan.py

```bash
python skills/self-iteration/scripts/dead-code-scan.py --root /path/dev-agent
```

三类发现：unused_import、dead_param（形参从未在函数体出现）、
dead_switch（argparse 定义了但从未读取的参数）。基于 ast，零误报优先。

### session-probe.py（开局探针）

```bash
python skills/self-iteration/scripts/session-probe.py --root /path/dev-agent
```

并行跑 doc-drift / perspective-scan --self-check / dead-code-scan，
按 triage 分诊：

- auto_fixable：死代码、孤儿引用——可机械清理。
- needs_work：文档漂移需人工核对基线。
- needs_human：检查器自身故障或反向验证自检失败——先修检查器。

退出码：0 全绿；1 有信号；2 检查器故障。

### convergence-check.py

```bash
python skills/self-iteration/scripts/convergence-check.py --root . --metrics metrics.json
```

四维：tests_passed / consistency_clean / queue_empty / metrics_stable。
全绿才可停（退出 0）；缺字段退出 2；任一不满足退出 1。

### pick-candidate.py

```bash
python skills/self-iteration/scripts/pick-candidate.py --items items.json --resolved id1,id2
```

三键排序：ROI 降序 → evidence 具体度降序（含 文件:行号 记 2 分）→ 依赖满足优先。
无可选候选退出 1。依赖满足 = deps 全部落在 resolved 或已 done 集合。

### e2e-check.py

```bash
python skills/self-iteration/scripts/e2e-check.py
```

在临时目录构造带缺陷的 git 仓库，端到端验证「发现问题 → 分诊 → 修 → 收敛」，
外加两条安全边界：

1. 脱敏边界：findings snippet 不含明文凭据，凭据类命中必须已替换 `<redacted>`。
2. 只读边界：评审管线运行期间被审仓库 git status 干净。

任一步失败退出 1。临时目录用完即清。

## 与主流程的接入点

| 主流程 | 用法 |
| --- | --- |
| 步骤 0 | session-probe：0 不做事，1 按 triage，2 先修检查器 |
| 步骤 8 | perspective-scan：机械视角先扫一遍，剩余交六问核验 |
| 自迭代循环 | pick-candidate 选 → 修 → doc-drift/dead-code 复查 → convergence-check 判停 |
| 交付前 | session-probe 必须退出 0 才可交付 |

## 反向验证要求

1. doc-drift：复制项目注入假 flag/错行数 → 对应问必须失败。
2. perspective-scan：--self-check 四类篡改必须全抓到。
3. dead-code-scan：临时注入未用 import 的文件 → 必须报 unused_import。
4. session-probe：任一探针退出 2 → 聚合结果必须 needs_human。
5. e2e-check：本身即全链反向验证；两条边界任一失守即失败。

## 退出码汇总

| 脚本 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| doc-drift.py | 全绿 | 有待处理项 | 根目录非法 |
| perspective-scan.py | 无问题/自检通过 | 有问题或漏检 | 参数错误 |
| dead-code-scan.py | 无死代码 | 有发现 | 根目录非法 |
| session-probe.py | 全绿 | 有信号 | 检查器故障 |
| convergence-check.py | 可停 | 不可停 | 参数错误 |
| pick-candidate.py | 正常 | 无可选 | 参数错误 |
| e2e-check.py | 全链通过 | 链路/边界失败 | 环境错误 |
| coverage-gate.py | 对账通过 / 基线已写 | 覆盖率回退（REGRESSION） | 基线/测量/参数错误 |
| secret-scan.py | 无未豁免命中 | 有凭据形态命中 | 非 git 仓 / 白名单非法 |
| license-check.py | 三档全部合规 | 有违规（缺失/档位/理由） | pyproject / 注册表非法 |
| release-gate.py | 七项全绿（可发布） | 有检查失败（failed 列 id） | 日志缺失/重复/未知 id |
| round-gate.py | 轮次产物/约定全 PASS（开局或收官） | 有检查 FAIL（failed 列 id） | 文件缺失/--round 非法 |

CI 三道工程门禁（round-56）：覆盖率对账只在 windows-latest × 3.12
单格跑（基线平台对齐；基线更新用 measure 子命令写
coverage-baseline.json），凭据扫描与许可证校验全矩阵跑。

发布闸（round-57，D-035）：`release-gate.py --root . --tag v<version>
--suite-log r1.log --suite-log r2.log`（或 `--run-suite`）一次跑七项——
版本六处同步、doc-freshness、doc-drift、secret、license、全量双跑、
干净树与 tag 预检。只读、不打 tag；`--only` 只作 CI 分项
（partial=true 不构成签核），CI 当前只跑 `--only version_sync`。

轮次闸（round-87，P1 剩余项）：`round-gate.py --root . open` 开局门（干净树 + session-probe + doc-freshness + next-round 可读 + 收官行台账对账）；`close --round N` 收官门（复盘产物齐 + 轮报头部/收官行/台账三方对账 + 「下一轮（round-N+1）」指针与编号条目 + ROADMAP §5 回填 + logs/suite-rN-run1/2.log 两跑均绿且计数一致）。与发布闸互补：发布闸管版本/密钥/许可证/双跑对账，轮次闸管轮次产物与文档约定；探针子进程环境净化（剥离 PYTHONUTF8/PYTHONIOENCODING，坑 8cfbcaf7d227）。

## 检查清单

1. 十五问数量与 BASELINE.md 一致（15 问）。
2. 共享定义副本无分叉。
3. 检查器先过反向验证再上岗。
4. 探针三档退出码语义不混淆。
5. 分诊三桶（auto_fixable/needs_work/needs_human）互斥。
6. 收敛四维全绿才可停。
7. 候选排序三键次序固定。
8. e2e 两条安全边界内建。
9. 全部检查器只读项目树。
10. 死代码三类：未用 import / 死形参 / 死开关。

## 十五问判定细节（补充）

- 共享定义清单：redact、SECRET_PATTERNS、HUNK_RE、parse_diff、locate_agent_json、load_args。
- 死代码只查顶层函数；常量死值由代码评审兜底，不进机械判定。
- 问数表述同时盯「紧邻表述」（38 条规则）与「行内汇总」（硬规则：38 条）两种写法。
- 参数漂移覆盖两个来源：脚本 docstring 用法行与 SKILL.md 用法行。
- 行数基线表在 BASELINE.md「SKILL.md 行数基线」节。
- 基线常量从脚本 ast 提取，不做文本匹配，防注释误导。

## 分诊处置表

| 分诊桶 | 内容 | 处置 |
| --- | --- | --- |
| auto_fixable | 死代码、孤儿引用 | 可机械清理，改后复跑探针 |
| needs_work | 文档漂移 | 人工核对基线后修 |
| needs_human | 检查器故障、反向验证失败 | 先修检查器，修好前不信任其结论 |

## 自迭代循环示例

```text
session-probe（exit 1）
  → triage: auto_fixable=[dead-code]
  → pick-candidate 排序
  → 机械清理 + 文档修正
  → session-probe（exit 0）
  → convergence-check --metrics metrics.json
  → 可停
```

## 检查器可信度约定

1. 任何检查器上线前必须过反向验证。
2. perspective-scan 的 --self-check 是常驻自证；失败即整器停用。
3. 共享定义清单本身也要进基线，防止改副本不改清单的绕过。
4. 检查器故障（退出 2）优先级高于一切信号：先修尺子再量东西。

## 与评测的关系

- 指纹变化 = 项目漂移；漂移后必须先 session-probe 再跑回归。
- doc-drift 全绿是回归前置条件；带着文档漂移跑回归没有意义。
- 自迭代改完的提交要重录指纹，评测报告引用新指纹。

## 维护注意

- 各问的判定函数一一对应，不许合并问项（否则问数表述会被自己绊倒）。
- 新增共享定义时同步 doc-drift 的 SHARED_NAMES 与 BASELINE。
- 死代码扫描宁可漏报不可误报：拿不准的形态留给人工。
- e2e-check 在临时目录作业，禁止指向真实仓库。

## 常见误报与豁免

| 形态 | 处理 |
| --- | --- |
| 形参只被传给子进程 | 属于使用，不报死形参 |
| 同名常量在不同 skill 语义不同 | 不在共享清单内，不比对 |
| SKILL.md 示例中的省略写法 | 不算参数漂移 |
| 文档中的历史行数描述 | 只查带 SKILL.md 字样的断言 |

## 设计取舍

1. 为什么不自动修复？——改文档要过基线一致性，机械改容易制造新的分叉。
2. 为什么探针并行？——三个检查器互不依赖，串行只是浪费时间。
3. 为什么收敛四维缺一不可？——测试绿但文档漂移，等于交付了一个说谎的项目。
4. 为什么 e2e 自建仓库？——评测边界要可控、可复算、可丢弃。

## 交接

- 自迭代的产出是「可复核的信号 + 处置建议」，不是自动改完的仓库。
- 所有处置落审计：step/actor/basis/disposition 一条不缺。
- 每轮自迭代的探针输出整体归档，供下一轮对照。
