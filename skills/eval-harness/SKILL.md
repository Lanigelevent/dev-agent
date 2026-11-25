---
name: eval-harness
description: 修复提交采样、前向基准、合成语料精度度量、回归评测与项目指纹。也用于口语说法：跑一下回归评测、量一下评审精度
---

# eval-harness — 评测与基准

## 目的与边界

回答一个问题：这评审智能体到底行不行？靠真实修复提交做前向基准，
靠确定性评审器跑回归，靠内容指纹锁定「被测对象到底是谁」。

边界约定：

- 全链零外部依赖：样本来自 git 历史，评审器用 deterministic-rules 充当。
- 跨编号体系对齐只用 sha（fix_commit/evidence_commit），不用序号。
- 汇总层必须输出 valid_samples；分母错了不会报错只会算错（易错点 4）。
- 两组数字完全相同 = 一定是 bug（易错点 5），run-regression 内置该断链检查。

## 何时用 / 何时不用

用：改动 AGENTS.md、skills/、agent.json args 之后；交付前的回归门槛。
不用：只改 runs/ 产物或文档错别字（指纹不变即无需回归）。

## 链路总览

```text
collect-samples → extract-window（按需取窗口）
       ↓
forward-bench prepare（git show -R 构造「PR 引入缺陷」材料）
       ↓
deterministic-rules（确定性评审器，产出 findings）
       ↓
forward-bench judge（gt 标识符比对 → recall）
       ↓
run-regression（抽样回归 + 基线对比）
```

## 脚本与用法

### collect-samples.py

```bash
python skills/eval-harness/scripts/collect-samples.py --repo /path/repo --out samples.json --limit 30
```

- 扫描窗口 `eval_scan_window_months`（默认 12 个月）、上限 `eval_scan_max_commits`（默认 5000）。
- 样本上限 `--limit`（默认 `eval_initial_sample_size`=30）。
- 只收修复提交：subject 命中 fix/bugfix/hotfix/修复/修正/修补。
- 过滤噪音：docs/注释/CI/格式化/测试稳定性修复全部跳过并计入 skipped。
- 去重键 =（文件集合, defect_class）；重复计入 deduped。
- 样本字段：fix_commit、parent_rev、summary、files、type_keywords、defect_class、
  context_type、collected_at、evidence_commit。evidence_commit = fix_commit（同 sha 双名，
  供不同编号体系各自引用，值恒等）。
- defect_class 机械分类：边界/资源/并发/安全/空引用/逻辑。

### extract-window.py

```bash
python skills/eval-harness/scripts/extract-window.py --repo . --sha <fix> --file svc/payment.py
python skills/eval-harness/scripts/extract-window.py --repo . --sha <fix> --file a.py --rev <parent>
```

- 按 fix diff 的全部 hunk 取窗口：hunk 区间 ± pad（默认 `eval_window_pad`=25），
  单窗口上限 `eval_window_max_lines`=120。
- 输出行带行号索引（`144: 代码`），供 finding 定位对齐。
- 自检覆盖：每个 hunk 必须有完整覆盖它的窗口；hunk 比窗口上限还大、
  或文件在 rev 不存在 → material_defect，退出 1。
- `--rev` 默认 = `--sha`；对齐到引入缺陷前的版本时传 parent_rev。

### forward-bench.py — prepare

```bash
python skills/eval-harness/scripts/forward-bench.py prepare --samples samples.json --repo . --out prepared/
```

- 每个样本每个文件：`git show -R <fix> -- <file>` 生成反向 diff（把修复撤回 = 引入缺陷）。
- 落盘 `<out>/<sha前12>__<文件名>.diff` + `manifest.json`。
- manifest 条目：sample_id（sha）、files、diffs。

### forward-bench.py — judge

```bash
python skills/eval-harness/scripts/forward-bench.py judge --findings findings.json \
  --prepared prepared/manifest.json --repo . [--min-tokens 2]
```

- gt 标识符：只认 fix 改动行里的 >=6 字符标识符；注释行（# // /* * <!--）跳过。
- 关键词表过滤（return/import/self/None/public 等语言关键字与高频噪音）。
- 命中判定：finding 文本提到 >=min-tokens 个 gt 标识符（默认 2，`--min-tokens` 可调）。
- weak 样本：单文件 gt 标识符 <2 → 标 weak 单列，不计入 recall 分母。
- 输出必须含 valid_samples；recall = hits / valid_samples，分母只用非 weak 样本。
- valid_samples=0 → 退出 1（评测无法给出 recall，属可处理问题）。

findings 输入格式（两种均可）：

```json
{"samples": {"<sha>": [finding, ...]}}
[{"sample_id": "<sha>", "loc": "...", "evidence": "..."}]
```

### run-regression.py

```bash
python skills/eval-harness/scripts/run-regression.py --repo . --baseline baseline.json --sample-size 5
```

- 回归样本数默认 `eval_regression_sample_size`=5；按 sha 排序取前 N（确定性抽样）。
- 链路：forward-bench prepare → deterministic-rules 逐反向 diff 出 findings
  → forward-bench judge → 与基线 metrics 对比。
- 回归判定：recall 下降 >0.05 → 退出 1。
- 断链判定：recall 与 hits 与基线完全相同、但样本集不同 → 退出 1（易错点 5）。
- 输出 current/baseline_metrics/picked_ids/valid_samples；预算参考
  `eval_regression_budget_minutes`=10。

baseline 文件结构：

```json
{"samples": [...collect-samples 输出...],
 "metrics": {"recall": 1.0, "hits": 1},
 "sample_ids": ["<sha>", "..."]}
```

### fingerprint.py

```bash
python skills/eval-harness/scripts/fingerprint.py --root /path/dev-agent
```

- 指纹 = sha256(AGENTS.md 内容 + skills/ 整树逐文件哈希 + agent.json args 规范化 JSON)。
- 改文档、脚本、参数任意一处，指纹必变；评测报告必须记录生成时指纹。
- 输出 components（agents_md/skills/args 三个分哈希）与 files 数。

### gold-sample.py / agent-sample.py — SWE-bench 双口径

```bash
# gold 口径：评 gold 补丁（只验管线正确性）
python skills/eval-harness/scripts/gold-sample.py \
  --all-from datasets/swe-out/predictions-gold6.jsonl \
  --predictions datasets/swe-out/predictions-gold6.jsonl \
  --out datasets/swe-out/gold-sample

# agent 侧口径：评编码循环产出的补丁（code-task 的 edits.patch）
python skills/eval-harness/scripts/agent-sample.py \
  --patches datasets/swe-out/agent-sample \
  --out datasets/swe-out/agent-sample/eval
```

- **gold-sample.py**：实例→镜像映射 CSV → 逐层下载（`scripts/docker-image-fetch.py`
  plan/fetch/assemble/load，绕开 docker 客户端假启动）→ `agent/swe_run.py` 官方
  harness 评测 → 报告 → 台账（断点续跑：已 DONE 跳过、已载镜像直评、单实例失败
  不阻断）。
- **agent-sample.py**：只做「补丁收集 → 预测装配 → 委托 gold-sample 评测」，
  **不重复实现下载/评测逻辑**。补丁目录布局 `<instance_id>[-vN]/edits.patch`；
  同实例多版本取最新（mtime 相同则取版本号高者）。
- **口径纪律**：agent 侧必须分档记录——「严格首跑（模型只见 issue 文本）」与
  「按 harness 失败反馈迭代后」是两件事，不得混谈（v1.25.0 实测 6/7 → 7/7）。
- harness 工作目录默认 `datasets/swe-out/harness`（**勿用仓库根**：官方 harness
  会把汇总报告写进 CWD，污染工作树——round-7/round-18 同坑两次复发）。

### pro-sample.py — SWE-bench Pro 口径

```bash
python skills/eval-harness/scripts/pro-sample.py   --tasks datasets/swebench/pro/gate-3.jsonl   --predictions datasets/swebench/pro-runs/predictions.json   --mode gold --out datasets/swebench/pro-runs
```

- 自管容器：镜像就位（国内镜像优先，失败落 `blocked_source`）→ `docker run`
  挂载 `tests/` → `before_repo_set_cmd` → 候选补丁（gold/predictions）→ 可选
  `pre_test_cmd` → `pytest -rA` 选定文件 → F2P/P2P 逐 node 对账。
- 12 态状态机 + 补丁双闸（结构 / 改测试 critical）；台账
  `<out>/pro-sample-ledger.json` 幂等续跑，`--force` 重跑。
- 任务级环境适配：JSONL 的 `pre_test_cmd` / `env` / `pytest_args`
  （qutebrowser 实测需常驻 Xvfb + 禁 sandbox + `-p no:xvfb`）。
- gold 口径只验判分链路，不折算 agent resolved；基线 `status` 保持 `not_run`，
  agent 侧走 `--mode predictions`。

### reviewbench-bridge.py

```bash
python skills/eval-harness/scripts/reviewbench-bridge.py --input prepared/manifest.json --out cases.json
python skills/eval-harness/scripts/reviewbench-bridge.py --input samples.json --validate-only
```

- 只做格式转换与结构校验，不执行外部基准。
- 用例 id 取样本 sha；prepared manifest 转 diff 引用，样本清单转 expect 结构。
- 输入结构不合格退出 1；`--validate-only` 只校验不落盘。

## gt 标识符细则

1. 范围：fix 提交的改动行（+ 与 - 行都要；它们共同刻画缺陷位置）。
2. 长度：>=6 字符（IDENT_RE `[A-Za-z_][A-Za-z0-9_]{5,}`）。
3. 注释行跳过：行首（剥 diff 前缀后）为 #、//、/*、*、<!--。
4. 关键词表：语言关键字 + 高频噪音（error/value/count/index 等）不入 gt。
5. 大小写不敏感比对（finding 文本与 gt 都转小写后包含即算提到）。

## 指标口径

| 指标 | 定义 | 分母 |
| --- | --- | --- |
| recall | hits / valid_samples | 仅非 weak 样本 |
| hits | 命中样本数 | - |
| valid_samples | 非 weak 且有 gt 的样本数 | - |
| weak_samples | gt 不足 2 个标识符的样本 | 单列 |
| skipped / deduped | 采集期过滤与去重计数 | collect 输出 |

汇总红线：输出里必须能看到 valid_samples；weak 不进分母但不许消失。

## 与主流程的接入点

| 主流程 | 用法 |
| --- | --- |
| 步骤 0 | fingerprint 先行：确认被测对象没漂移 |
| 交付前 | run-regression 回归门槛，退出码 0 才可交付 |
| 步骤 10 | 运行信息记录指纹与最近一次回归结论 |
| 自迭代 | doc-drift 第 14 问核对 args 与脚本默认值一致 |

## 反向验证要求

1. judge：构造只提到 1 个 gt 标识符的 finding → 不得算命中（阈值 2）。
2. weak：构造 gt 不足 2 的样本 → 必须进 weak 列表且不进分母。
3. 断链：换样本集但强行填相同 metrics → run-regression 必须退出 1。
4. 指纹：复制项目改一个字符 → 指纹必须变化。
5. bridge：喂不合格结构 → 退出 1，不得产出空用例集。

## 评测样本筛选判据

收：subject 以 fix/bugfix/hotfix 开头（或含 修复/修正/修补），且改动含源码文件。
不收：docs/readme/注释/文档/typo/chore/CI/格式化/测试稳定性修复；
空文件集（纯删除空提交等）；重复（文件集合 + defect_class 相同）。

## 退出码汇总

| 脚本 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| collect-samples.py | 正常（0 样本也算） | - | 参数/环境错误 |
| extract-window.py | 窗口齐全 | material_defect | 参数/环境错误 |
| forward-bench.py | 正常 | judge 无有效样本 | 参数/环境错误 |
| run-regression.py | 无回归 | 回归/断链 | 参数/环境错误 |
| fingerprint.py | 正常 | - | root 非法 |
| reviewbench-bridge.py | 正常 | 结构不合格 | 参数/环境错误 |

## 检查清单

1. 样本主键只有 sha，无序号。
2. valid_samples 出现在所有汇总输出。
3. weak 样本单列且不进分母。
4. 命中阈值默认 2 且可调。
5. 反向 diff 文件名含 sha 前缀，可溯源。
6. 回归抽样确定性（按 sha 排序取前 N）。
7. 断链检查（相同数字 + 不同样本集 → 拒绝）。
8. 指纹覆盖 AGENTS.md + skills 整树 + args。
9. bridge 只转换不执行。
10. 窗口自检失败必须报 material_defect。
11. 注释行不入 gt。
12. collect 过滤噪音计数可见（skipped/deduped）。

## 端到端示例

以下是一次最小可复算的评测会话（仓库里有一个修复提交）：

```bash
# 1. 采集样本
python skills/eval-harness/scripts/collect-samples.py --repo . --out samples.json --limit 5

# 2. 构造「引入缺陷」材料
python skills/eval-harness/scripts/forward-bench.py prepare --samples samples.json --repo . --out prepared/

# 3. 确定性评审器对反向 diff 出 findings
python skills/multi-agent-review/scripts/deterministic-rules.py --diff-file prepared/<sha>__a.py.diff

# 4. 判命中并算 recall
python skills/eval-harness/scripts/forward-bench.py judge --findings findings.json \
  --prepared prepared/manifest.json --repo .

# 5. 回归
python skills/eval-harness/scripts/run-regression.py --repo . --baseline baseline.json
```

## 样本字段表

| 字段 | 说明 |
| --- | --- |
| fix_commit | 修复提交 sha（主键） |
| parent_rev | 父提交，用于对齐引入缺陷前版本 |
| summary | 提交标题原文 |
| files | 变更文件列表（去重排序） |
| type_keywords | 标题关键词（<=6 个） |
| defect_class | 边界/资源/并发/安全/空引用/逻辑 |
| context_type | 单文件/多文件 |
| collected_at | 采集时间（ISO） |
| evidence_commit | = fix_commit，供外部编号体系引用 |

## judge 输出字段表

| 字段 | 说明 |
| --- | --- |
| recall | hits / valid_samples；无有效样本为 null |
| precision | grounded / claimed；报出的结论里有多少是真的 |
| claimed | 报了结论（非空 findings）的样本数 |
| grounded | claimed 中真命中（>=阈值标识符）的样本数 |
| grounded_but_not_claimed / claimed_but_not_grounded | 命中与结论的错位细分 |
| hits | 命中样本数 |
| valid_samples | 非 weak 样本数（recall 分母） |
| weak | gt 标识符 <2 的样本清单 |
| per_sample | 逐样本命中明细与匹配到的标识符 |
| threshold | 命中阈值（默认 2） |

## 回归判定细则

1. 抽样：样本按 sha 升序取前 N（默认 5），保证可复算。
2. 链路：prepare → deterministic-rules → judge，全部子进程退出码必须收敛。
3. 回归：current.recall < baseline.recall - 0.05 → 退出 1。
4. 断链：recall 与 hits 与基线全同、样本集不同 → 退出 1（易错点 5）。
5. 输出：current、baseline_metrics、picked_ids、valid_samples 全部可见。

## 指纹对照表

| 变更 | 指纹是否变化 |
| --- | --- |
| AGENTS.md 任一字符 | 变 |
| skills/ 任一文件内容 | 变 |
| agent.json args 任一键值 | 变 |
| runs/ 产物 | 不变 |
| 新增未跟踪临时文件（skills 外） | 不变 |

## 常见故障与处置

| 现象 | 处置 |
| --- | --- |
| collect 0 样本 | 检查提交标题是否含 fix 词缀；放宽 --limit |
| judge recall=null | 有效样本不足，gt 太少；换样本或降 --min-tokens |
| extract-window material_defect | hunk 超窗或 rev 无此文件；调 pad/--rev |
| run-regression 断链告警 | 基线 metrics 与样本集不匹配；重建基线 |
| 指纹突变 | 确认改动范围；评测报告必须重记录指纹 |

## 与 BASELINE 的契约点

- 命中阈值默认 2，--min-tokens 可调。
- weak 样本单列且不进分母。
- 汇总强制同时输出 recall 与 precision，只报一个视为不合格。
- 样本 9 字段名固定（含 evidence_commit 双名）。
- 回归抽样按 sha 排序，确定性可复算。
- 指纹三组件：AGENTS.md + skills 整树 + args。

## 判定细节：为什么是标识符比对

- 真实模型的 findings 是自然语言；机械判定只能锚定「具体符号是否被提到」。
- >=6 字符过滤掉 if/for/err 这类无区分度的短名。
- >=2 个标识符避免「一个热词命中一切」的假阳性。
- 注释行剔除避免把「TODO: fix null check」当缺陷证据。
- 关键词表剔除 return/import 等语言噪音。
- 该判定是下界：机械 recall 低不代表真实评审差，但机械 recall 掉了一定有问题。

## 判定细节：反向 diff 的正确姿势

- `git show -R` 输出的是「撤回修复」的 diff，即把修复行删掉、把缺陷行加回来。
- deterministic-rules 只扫 + 行，因此反向 diff 中被加回来的正是缺陷行。
- 多文件样本逐文件出反向 diff，文件名含 sha 前缀防串样本。
- 样本主键永远是 sha；文件名只是展示层。
- 判定材料是 fix 的改动行（+/- 都算），它们共同刻画缺陷位置。

## 扩展：接真实模型

链路不变，只替换第 3 步的评审器：

1. findings 仍按七要素输出，sample_id 标注所属样本。
2. judge 逻辑与阈值不变，保证新旧评审器可比。
3. 建议先跑 5 样本对齐，再全量；两边都记录指纹。
4. 真实模型的 recall 应显著高于确定性基线，否则派发有问题。

## 评测纪律

1. 改任何契约（阈值/关键词表/字段）必须先升 BASELINE 指纹。
2. 评测报告必须含：指纹、样本数、valid_samples、recall、weak 清单。
3. 两组数字完全相同 = 一定是 bug，先查断链再庆祝稳定。
4. 单变量实验 ≠ 独立复现：结论要标注证据等级。
5. 评测脚本禁止写被测仓库；产物一律走 --out。
6. 样本采集窗口与上限来自 args，不是硬编码。

## 逐脚本退出码与参数

### plan-distill.py — 修复计划蒸馏（round-34 新增）

```bash
python skills/eval-harness/scripts/plan-distill.py \
  --patches datasets/swe-out/agent-sample \
  --caliber reports/swebench/code-review-agent.caliber.json \
  --out retro/repair-plans.json
```

- 只蒸馏 caliber 判 resolved=True 的实例（未过实例的补丁形状不进原料）；
  数据全部取自 edits.patch 与 task-manifest.json，不信叙述文本。
- 选版口径与 agent-sample.py 收集器同源：校验过线的最新非空版本。
- 产物按仓库家族聚合（高频文件前缀 / 补丁规模 / 轮数区间）；
  code-task 材料装配命中家族即附带（只读参考，不许当指令）。

退出码：0 = 蒸馏完成；2 = 输入不可读。

### reviewbench-import.py — ReviewBench 语料导入（round-34 新增）

```bash
python skills/eval-harness/scripts/reviewbench-import.py \
  --corpus datasets/reviewbench --out datasets/reviewbench/samples-py.json \
  --lang .py --limit 12
```

- 数据源：github.com/review-bench/ReviewBench（MIT，署名保留）；
  国内可达性实测：raw.githubusercontent.com 不通（WinError 10054），
  github.com 网页/git/pull diff 均通——diff 走 `pull/<n>.diff`。
- golden 命名 `<owner>_<repo>_<pr号>-<head8>.json`；diff 落 diffs/ 目录，
  --offline 只用已落盘 diff 装配（复跑与契约测试用）。

退出码：0 = 正常；1 = manifest 缺失或形状不合格；2 = 参数/环境错误。

### collect-samples.py

- 参数：--repo（必填）、--out（必填）、--limit（可选，默认 eval_initial_sample_size）、--config（可选）。
- 0 = 正常（含 0 样本）；2 = 非 git 仓库或输出不可写。

### extract-window.py

- 参数：--repo、--sha、--file 必填；--pad、--max-window、--rev、--config 可选。
- 0 = 窗口齐全；1 = material_defect；2 = 参数/环境错误。

### forward-bench.py

- prepare 参数：--samples、--repo、--out。
- judge 参数：--findings、--prepared、--repo、--min-tokens（默认 2）。
- 0 = 正常；1 = judge 无有效样本；2 = 参数/环境错误。

### run-regression.py

- 参数：--repo、--baseline 必填；--sample-size、--config 可选。
- 0 = 无回归；1 = 回归或断链；2 = 参数/环境错误。

### fingerprint.py

- 参数：--root 必填。
- 0 = 正常；2 = root 非法。

### reviewbench-bridge.py

- 参数：--input 必填；--out 或 --validate-only 二选一。
- 0 = 正常；1 = 结构不合格；2 = 参数/环境错误。

## 术语表

| 术语 | 含义 |
| --- | --- |
| 前向基准 | 用历史修复构造缺陷场景，验证评审器能否重新发现 |
| 反向 diff | git show -R 的输出：撤回修复 = 引入缺陷 |
| gt 标识符 | fix 改动行中 >=6 字符的符号名，判定命中的锚点 |
| weak 样本 | gt 不足 2 个的样本，不计分母 |
| 断链 | 评测管线某环节失效，输出与输入脱钩 |
| 指纹 | 项目内容哈希聚合，锁定被测对象 |
| 有效样本 | 非 weak 且参与 recall 分母的样本 |
| material_defect | 窗口自检失败的标记，必须可见 |

本 skill 的所有契约改动都要走「先改 BASELINE → 再改代码 → 回归 → 更新指纹」的顺序。

## prompt-optimizer.py — 提示优化循环（round-217 新增，AB-06）

```bash
py skills/eval-harness/scripts/prompt-optimizer.py plan
py skills/eval-harness/scripts/prompt-optimizer.py evaluate --variant v1 \
   --prompt-file materials/prompts/review-v1.md
py skills/eval-harness/scripts/prompt-optimizer.py adopt --variant v1 \
   --metrics runs/prompt-variant-v1-metrics.json \
   --prompt-file materials/prompts/review-v1.md --out materials/prompts/
```

- 评估器驱动（DSPy Optimizer 同型思想，读设计不装库）：plan 机械展开
  变体矩阵（prompt-watch.json 监视面 × detail/order/style 三维度）；
  evaluate 评估协议（无评审臂 → arm_status=blocked_no_judge 不冒充
  已评；有臂 → judge 任务经宿主协议下发）；adopt 采纳闸——precision
  ≥ 护栏地板 0.65 且 **≥ baseline 不许降**，通过以新指纹固化静态 md。
- 指纹纪律沿用 AB-03 prompt-regression；评估器=precision-gate 固定语料。
- live 优化迭代面（变体生成/判卷）由宿主会话执行——协议在 SKILL.md，
  本机无 key 时 blocked 语义如实。

退出码：0=成功；1=评估器不可用 blocked/基线缺失拒采纳；2=输入错误。
