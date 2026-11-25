# round-53 ACI 阶段二（2.1–2.5）真实语料验收

> 日期：2026-10-29 ｜ 版本：v1.54.0 ｜ 判据在跑数之前写死在
> `scripts/aci-retrieval-bench.py` 头部（`VERDICT_RULES`），本报告只按判据
> 记录结果，不改阈值、不补样本。
> 产物：`reports/aci-round53-bench.json`（完整逐样本行）、
> `reports/aci-round53-bench.stdout.json`（汇总）、
> `reports/aci-round53-bench.log`（运行日志与构图耗时）。

## 0. 结论摘要

| 项 | 实测 | 判据 | 判定 |
|---|---|---|---|
| 2.1 图排序 | 真实任务 Top-8：refs **9/11**；graph@8 / graph@12 / reserved6+2 均 **9/11**；构造样本四策略均 7/9（无退步） | best_graph ≤ refs → 默认关 | **default_off_only**：保留 `--rank graph` 但不改默认材料 |
| 2.2 搜索排序 | 21 个查询，前 5 条含目标定义点：旧 **13/21** → 新 **17/21**（+4，无丢失） | new > old | **keep**（生产已生效） |
| 2.3 list 动作 | 限深 3 / 200 项 / 越界拒绝 / 不跟符号链接，4 类边界均有契约测试；**探索轮数未测** | — | 机制落地；阶段出口指标待宿主实跑 |
| 2.4 测试子集 | 真实任务映射非空 **7/11**（4 条 django 落全量回退）；合成控时 full 1.62s → subset 1.05s（**-35.2%**）；抽检探针能抓隐藏回归并标注未抽检 | coverage>0 且 subset 更快 | **keep**（生产已生效；映射覆盖 64% 如实记录） |
| 2.5 语法校验 | 10 个变异坏样本 **10/10** 拦截；8 个合法样本 **0** 误报；非 .py 不查；宿主协议端到端「坏补丁退回→改对 DONE」 | caught==10 且 FP==0 | **keep**（生产已生效） |

一句话：2.2/2.4/2.5 有可复算的增益并按判据进入生产；2.1 不劣但无增益，
按预注册判据保持默认关；2.3 的机制有边界测试，但「探索轮数下降」需要
编码循环实跑才能回答，本轮不冒充已验收。

## 1. 方法

- **2.1 样本 A（构造，天花板守卫）**：django / sympy / matplotlib 三个真实仓，
  只取可导入包内模块（`__init__.py` 链），每仓 3 个，共 9 个；查询 = 模块
  docstring 首行，目标 = 模块文件。查询文本就在目标文件里，内容扫描天然命中，
  这一组只证明「图补充没有把原命中挤掉」。
- **2.1 样本 B（真实任务，主判据）**：`datasets/swe-out/` 中 11 条已 resolved
  实例的 `problem_statement`；目标文件 = 本项目自产补丁的 `+++ b/` 并集。
  检索在 **base_commit 的 detached worktree** 上做（同 (repo, sha) 建一次），
  避免克隆 HEAD 漂移（sklearn 两实例的目标文件在 HEAD 已改名/删除）；
  11/11 均为 `worktree@base_commit`，无 `clone_head_fallback`。
- **策略**：`refs` = 现默认（地图关键词 + 全文扫描合并，Top-8）；`graph@8` =
  合并图邻居后仍取 8；`graph@12` = 12 槽位上界（只作参照，不代表 token 不增）；
  `reserved6+2` = 前 6 个 refs + 2 个图邻居，凑满 8。
- **2.2**：每条真实任务的目标文件里取 2 个 `def`/`class` 名（去常用名、取较长），
  共 21 个查询；旧口径 = 遍历顺序前 5 条，新口径 = 生产 `_search_repo` 前 5 条；
  命中要求是 `(目标文件, 定义行号)` 精确出现。
- **2.4**：真实仓只测「改动文件 → 选中测试路径」的映射覆盖率（不跑这些测试，
  缺环境）；墙钟用合成仓对照（24 个无关测试 + 1 个相关测试）。
- **证据等级**：n=9 构造 / n=11 真实 / n=21 查询，属小样本观测；不外推为能力
  上限，也不把单变量实验当独立复现。所有数字来自上述 JSON，不手抄。

## 2. 2.1 repo map 图排序

### 2.1.1 结果

| 组 | n | refs Top-8 | graph@8 | graph@12 | reserved6+2 | 图补充文件数 |
|---|---|---|---|---|---|---|
| 构造（docstring 查询） | 9 | 7 | 7 | 7 | 7 | 54（每样本 6） |
| 真实任务（11 条） | 11 | **9** | **9** | **9** | **9** | 66（每样本 6） |

- 判定：`default_off_only`（best_graph = refs = 9/11）。构造组无退步
  （四策略均 7/9），故不触发 `degrade`。
- 两个真实未命中：`astropy__astropy-14182`（目标 `astropy/io/ascii/rst.py`）、
  `sympy__sympy-13031`（目标 `sympy/matrices/sparse.py`）。图邻居补充到
  Top-12 仍未命中，说明这两个任务的候选种子与目标之间没有可用的 import 边，
  或传播质量低于 `min_ratio`——不是「槽位不够」。
- 每个样本的 refs 都填满了 8 个槽位，所以 `graph@8`（合并后仍按分数取 8）
  与 refs 完全一致；这正是 `reserved6+2` 被设计为对照的原因，但它在本语料
  也没有增益。
- 构图成本（单次、可缓存）：django 5.9s、sympy 10.0s、matplotlib 3.2s
  （`build_import_graph`）；11 个 base_commit worktree 的构图 1.8–6.2s/个。
  实测没有把它设为默认的理由，除了无增益，还有这笔额外成本。

### 2.1.2 生产决定

- 保留 `repo_map.py --rank graph` 与 `code-task.py --rank graph`（默认 `refs`），
  生产默认材料与旧路径完全一致；图排序作为可显式开启的实验能力，不进入
  默认 8 个候选槽位。
- 未做「reserved6+2 转正」：它在真实语料上与 refs 同为 9/11，没有证据支持
  用两个图邻居替换低分 refs（替换还可能挤掉本可命中的文件）。

## 3. 2.2 搜索排序

| 口径 | 前 5 条含目标定义点 |
|---|---|
| 旧（遍历顺序截断） | **13/21（61.9%）** |
| 新（定义 > 引用 > 注释 → 路径距离 → 路径/行号） | **17/21（81.0%）** |

- 判定：`keep`（17 > 13）；21 个查询里旧命中→新丢失为 **0**，增益全部来自
  「定义点被引用/文档压到截断外」这一类。
- 典型增益（目标定义进入前 5）：
  - `astropy__astropy-14182 / get_fixedwidth_params`：新增
    `astropy/io/ascii/rst.py:22`（旧口径被 `fixedwidth.py` 的 5 条引用占满）；
  - `scikit-learn__scikit-learn-14092 / NeighborhoodComponentsAnalysis`：
    新增 `sklearn/neighbors/nca.py:29`（旧口径前 5 全是 `doc/` 文档）；
  - `scikit-learn__scikit-learn-14092 / _validate_params`：新增
    `sklearn/neighbors/nca.py:262`；
  - `sympy__sympy-13031 / _lower_triangular_solve`：新增
    `sympy/matrices/sparse.py:466`。
- 未变的查询里，排序只调整了同一 kind 内的先后（如目标文件内的两个定义行），
  不改变命中集合；`django-11039 / Command` 旧新都未命中（目标定义行在
  `sqlmigrate.py`，全仓同名 `Command` 太多），如实记录为能力边界。
- 生产口径：`_search_repo` 先收 `max_hits×10` 再排序取前 40；命中行仍逐个
  `_redact_snippet` 脱敏并截断 200 字。

## 4. 2.3 list 动作

- 机制：只读目录树；`depth` 容错并钳到 1–3；条目上限 200（默认 80）；剪
  `SEARCH_SKIP_DIRS`；不跟随符号链接；`Path.resolve()` 后必须仍在工作区内，
  `../` 与绝对路径越界一律拒绝；目标是文件时返回行数。
- 契约测试（`tests/test_agent.py::TestAciStageTwo::test_list_tree_bounded_and_jailed`）：
  - 限深：depth=1 不出现二级目录内容；
  - 越界：`../outside` 与工作区外绝对路径均返回 `False`；
  - 正常目录列出文件；符号链接权限不足时跳过该断言（Windows 非管理员
    `WinError 1314` 环境差异，不影响越界判据）。
- **未测项（如实）**：路线图阶段出口要求「大仓探索轮数下降」，需要在编码
  循环里让模型实际使用 list 动作并统计轮数；本轮没有宿主实跑预算，故不报
  轮数下降，只报能力与边界已就位。该验收留待阶段出口的实跑轮。

## 5. 2.4 测试子集

### 5.1 真实仓映射（不跑测试）

| 实例 | 目标文件 | 选中测试 | 全量测试文件 |
|---|---|---|---|
| astropy-12907 | `astropy/modeling/separable.py` | 1 | 306 |
| astropy-14182 | `astropy/io/ascii/rst.py` | 1 | 311 |
| django-10914 | `django/conf/global_settings.py` | **0** | 520 |
| django-11039 | `django/core/management/commands/sqlmigrate.py` | **0** | 522 |
| django-11049 | `django/db/models/fields/__init__.py` | **0** | 522 |
| django-12284 | `django/db/models/base.py` | **0** | 540 |
| django-14999 | `django/db/migrations/operations/models.py` | 2 | 561 |
| sklearn-13241 | `sklearn/decomposition/kernel_pca.py` | 1 | 166 |
| sklearn-14092 | `sklearn/neighbors/nca.py` | 1 | 175 |
| sympy-13031 | `sympy/matrices/sparse.py` | 2 | 353 |
| sympy-13043 | `sympy/integrals/intpoly.py` | 1 | 357 |

- 映射非空 **7/11（63.6%）**；4 条 django 全部落全量回退——A 路同名测试在
  多个测试目录出现、B 路目录段映射找不到 `tests/<app>/`，按「无证据不猜」
  返回空，由 `_run_tests` 回退全量。回退不是失败，但意味着这 4 条任务没有
  享受到子集加速；报告不把它写成 100% 覆盖。
- 判据只要求 coverage>0 且子集更快；`covered=7` 满足。**映射准确率不是本轮
  验收项**（路线图的「漏测率 0」以全量抽检为金标准，见 5.3）。

### 5.2 合成控时

- 同一套 pytest 语料（24 个无关测试 + 1 个相关测试）：
  全量 **1.62s**，子集 **1.05s**，加速比 **1.54×**，耗时下降 **35.2%**
  （≥ 路线图的 30%）。两者均 pass。
- 口径说明：这是小语料的墙钟，pytest 启动与收集占大头；真实大仓的降幅
  取决于映射到的测试规模，本轮没有在真实仓跑 pytest（缺环境），不把 35.2%
  外推成「任何仓都能省 35%」。
- 标注口径：`_run_tests` 首行写「子集 N 项（原范围 M 项）」——N/M 是传给
  pytest 的**路径条目数**（目录按 1 项计），不是用例数；真实仓常见
  「1 项 vs 1 项」，缩减体现在 pytest 收集到的用例与墙钟，不在这两个数字。
  该说明同时写进报告与决策，避免把「1 项 vs 1 项」误读成没有缩减。

### 5.3 漏测抽检

- 生产口径：`audit_seed = 轮次|改动文件`，sha1 首字节 % 3 == 0 时子集通过后
  再跑全量；全量失败按 `fail` 返回并注明「隐藏回归」，未抽检的通过注明
  「未抽检」，下游不得当全量通过。
- 探针（合成「子集通过、全量有隐藏失败」）：种子
  `0|mod/core.py|6` 触发抽检 → `fail` + 「全量抽检未过」；同一仓不带种子
  → `pass` + 「未抽检」。`detects_hidden_regression=true`、
  `labels_unaudited=true`。
- 局限：1/3 抽检不是全覆盖，未被抽中的子集通过仍可能藏着全量失败；这是
  成本与漏测的显式折中，报告不宣称「漏测率 0」。路线图的「漏测率 0（以
  全量为金标准抽检）」在统计意义上只能靠全量复核，生产只做确定性抽检。

## 6. 2.5 语法树级校验

- 变异语料：10 个坏片段（缺括号/引号、缩进错、缺冒号、坏字典、截断 def、
  垃圾 token 等）**10/10 全部拦截**；8 个合法片段（含 match、f-string、
  装饰器、类型注解、async）**0 误报**；`notes.txt` 不被检查。
- 双网口径：先 tree-sitter 根节点 `has_error`（报精确行号），再 `ast.parse`
  兜底。首测只有 8/10——tree-sitter 的 ERROR 恢复放过了「多个空格缩进」与
  「缩进不齐的截断 def」，`bad_indent.py` / `truncated_def.py` 由 ast 第二道
  网抓住；单元测试用 `bad_indent.py` 锁定该路径。
- 接线：编辑分支（`_validate_patch` 之后）与收束前各查一次；非末轮退回重做，
  末轮进 `patch_validation.issues` 并置 `ok=false`；只查本次编辑过的 `.py`，
  避免把基线老语法算到模型头上。宿主协议端到端测试证明坏补丁不进入
  `edits.patch`，下一轮材料出现「补丁即时校验未过[syntax_error]」。

## 7. 阶段出口核对（如实）

| 阶段出口指标 | 状态 | 说明 |
|---|---|---|
| 因路径/文件不存在浪费的轮次占比下降一半 | **未测** | 需要编码循环实跑对照；本轮只交付 list 动作与边界，不报下降 |
| 同一任务中位轮数下降 | **未测** | 同上；2.2 只证检索排序质量，不证轮数 |
| 无新增回归 | **已双跑** | 460 项两次全绿 **306.471 / 416.967 秒**（`logs/suite-r53-run1/2.log`，1 skip）；run1 为终稿代码首跑，run2 与邻居项目全量 E2E 并发（时长受负载影响，仅作绿/红证据）；两次均超 300s 红线，连续第三轮越线，升级处置、红线未改 |

## 8. 边界与未测项

- 小样本：构造 9 / 真实 11 / 查询 21；单仓单任务形状，不外推。
- 真实任务目标是**本项目自产补丁**触达的文件（已 resolved），不是 gold
  patch；目标里可能含顺带修改的文件。
- 2.1 的 `graph@12` 是 12 槽位上界，不代表材料 token 不增；生产未采用。
- 2.3 没有模型实跑，探索轮数未验证。
- 2.4 真实仓未跑 pytest（缺环境），只测映射；控时用合成仓。
- 2.4 的「子集 N 项」是 pytest 路径条目数，不是用例数。
- 基准脚本运行期间两次因被测代码变更作废并重跑（图种子泛词修正、抽检功能
  加入）；最终数字对应本报告所列的最终实现。
- 全量套件第一跑红在文档门禁（README「9 项测试」被 F5 当总数，346.990s /
  failures=1），修复表述后重跑；失败跑日志保留在 `logs/suite-r53-run1-fail.log`。

## 9. 复现

```bash
.venv/Scripts/python.exe scripts/aci-retrieval-bench.py \
  --out reports/aci-round53-bench.json
```

退出码 0 = 实测跑通（数字难看也是 0）；2 = 依赖仓库/数据缺失。构造样本与
真实样本的取样、base_commit worktree、四策略与判据全部在脚本内可读。
