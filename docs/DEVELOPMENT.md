# dev-agent 开发文档

> **创建日期**：见下行原始头注 ｜ **当前状态**：维护中
> **所有者**：开发者 ｜ **主导模式**：操作指南
> **权威范围**：见下方原始头注详述
> **不是权威**：逐轮进度（docs/PROGRESS.md）、决策论证（docs/DECISIONS.md）
> **复核期限**：2026-12-07（常用层月检）｜ **上次复核**：2026-11-07

> 文档状态：维护中（D2 架构 + D6 运维权威源）｜创建：2026-10-24 ｜ 权威范围：分层架构、扩展指南、测试与发布、运维要点；文档体系见 `docs/INDEX.md`。

面向本仓库的开发者与维护者。使用方式、能力与安装见根 `README.md`；智能体运行时
主流程见 `AGENTS.md`；全部固定契约见 `BASELINE.md`（**改契约必须同步搜索
README / AGENTS / SKILL.md / tests 的所有引用处**，这是本项目第一纪律）。

## 1. 环境搭建

| 层 | 要求 | 说明 |
|---|---|---|
| 治理壳（skills/*/scripts、llm/、mcp/） | Python ≥ 3.11，纯标准库 | 零依赖可直接跑，任何机器可分发 |
| 引擎层（engines/、agent/） | 项目根 `.venv`（Python 3.12） | 白名单第三方：ruff、libcst、tree-sitter 系、ast-grep-py、hypothesis |
| isolated 层（LGPL） | 按需安装 | semgrep、pynguin 仅 subprocess 隔离调用，禁 import |

```bash
# 创建/重建 .venv（uv 走清华镜像，见 pyproject.toml [tool.uv]）
uv sync
# LGPL 基线对照组件（可选，不进运行时 import 链）
uv sync --extra isolated
```

- 全量测试：**897 项**（895 passed + 2 skipped），预算 60 秒/断言；最近全量 300.23/289.13 秒 full 双跑（`logs/suite-r246-run1/2.log`）。历史时长与逐轮沿革见 `docs/BASELINE-HISTORY.md` 与 `logs/`。
  **解释器必须选对**：`tests/test_agent.py` 会 import 引擎层
  `agent/repo_map.py`（tree-sitter 系），用全局 python 跑会出现 14 例
  `ModuleNotFoundError: tree_sitter_python`——那是环境错，不是代码回归。
- 开局自检：`python skills/self-iteration/scripts/session-probe.py --root .`
  （含 doc-drift 15 问、死代码扫描、视角反向验证；退出码 0=全绿）。
- 引擎与编码循环脚本用 `.venv/Scripts/python`（Windows）或 `.venv/bin/python`
  运行；治理壳用全局 `python`。**全量测试属于「会 import 引擎层」的那一类，跟着 .venv 走。**

## 2. 仓库布局

```
skills/              治理壳主体：13 个技能 × 93 个脚本，每技能 SKILL.md + scripts/
  approval/            审核人（闸 1 范围裁定 / 闸 2 补丁准出）
  code-review/         ZCode 总入口技能
  director/            总监（org-route / case-match / research-brief / org-scorecard / case-archive）
  eval-harness/        评测（synth 基准 / 真实语料 / SWE-bench 桥 / DeepSWE 适配 /
                       精度报告 / 指纹）
  git-change-analysis/ 预检门 / 边界形态 / 代码图缓存
  multi-agent-review/  硬规则 / 污点流 / 派发计划 / 材料校验 / 覆盖度 / 发现校验
  orchestrator/        runner.py（0-10 步编排）/ pr-kit / pr-publish
  production-guardrails/ 审计 / 断点 / 人工门 / 报告与 schema 校验 / 误报库 / args 读取 / 事件账本 / 成本账本
  prompt-enhancement/  意图解析
  repair/              修复团队（fix-plan / fix-patch / fix-apply 唯一落盘口）
  retro/               迭代官（坑台账 / 轮报 / 记忆检索与压缩）
  risk-scoring/        三维风险评分
  self-iteration/      开局探针 / 文档漂移 / 死代码 / 收敛判定 / 端到端
engines/             引擎适配层：ruff_adapter.py（scan/fix-dry/matrix/clean-fp）、
                     libcst_adapter.py（codemod/重构：ref-eq-none、ref-in-keys；
                     库函数自举子进程到 .venv）、astgrep_adapter.py（多语言 AST
                     模式：JS/TS + Python 29 规则）、testgen.py、
                     ruff-matrix.json / libcst-matrix.json / astgrep-matrix.json
agent/               编码循环：repo_map.py（tree-sitter 符号地图；import 图 +
                     个性化 PageRank 排序，默认关）、edit_formats.py
                     （SEARCH/REPLACE 唯一命中）、code-task.py（read/list/edit/done
                     循环；search 定义优先排序 + 测试子集/全量回退 + 语法双网；
                     稳定前缀 + 输出外置 + 历史压缩 + 记忆 few-shot + stderr 进度帧）、
                     trace.py（JSONL 埋点）、swe_run.py（SWE-bench 单实例评测编排
                     prepare/build/eval/report，
                     v1.22.0 恢复脚本形态，转换规则与镜像源改写见 swe-workflow.md）
llm/                 provider.py：openai 兼容后端 + host 宿主文件协议
mcp/review_mcp.py    MCP stdio 服务器（16 工具，JSON-RPC 2.0 / 2025-06-18；D-055/D-176/D-180 异步 submit/status/cancel/purge）
                     异步作业：code_review_submit(repo/range|resume, budget) → job_id；code_review_status(job_id)
                     → state/step/progress/findings_url；code_review_cancel(job_id) 终进程树 + 账本摘要；
                     code_review_purge(job_id, confirm=true) 终态清理 + 中央账本 job.purge 摘要；
                     资源 review://jobs/<id>（envelope: job_state/status/result/cancel/ledger_verify）
                     + 子资源 review://jobs/<id>/ledger（64KB 截断）；作业目录 runs/jobs/<uuid4>/；config 白名单透传（3 键）
commands/            ZCode 命令定义（/code-review）
.zcode-plugin/       ZCode 插件清单（版本唯一事实源）
interop/             DeepSeek Harness 接线示例（cordis.yml.example）
scripts/             评测运维脚本（docker-mirror-probe.py 镜像源判定、
                     docker-image-fetch.py 逐层断点续传下载器、
                     sibling-test-bench.py / sibling-test-realbench.py 邻近测试命中率量具、
                     aci-retrieval-bench.py ACI 阶段二真实语料量具（图排序/搜索排序/
                     测试子集/语法校验，判据先写死）、
                     sweep-test-tmp.py 临时快照报表（缺省只看不删）、
                     verify-closure-commands.py 结案口径抽取与全量实跑（缺省 dry-run））
tests/               契约级断言集（unittest，含临时 git 仓库端到端与反向验证）
reports/ retro/      评测报告 / 复盘台账（含本地档案仓 retro/archive-repo）
datasets/ runs/ logs/ corpus/  评测与运行产物（.gitignore，不入库）
```

## 3. 分层依赖策略（硬约束 1，立宪于 v1.14.0）

- **治理壳**（skills/*/scripts、llm/）：只用 Python 标准库，保持零依赖可分发。
- **引擎层**（engines/、agent/）：按白名单引入第三方——MIT/Apache/BSD 可嵌入
  import（当前：ruff、libcst、tree-sitter 系、ast-grep-py）；MPL（hypothesis）用于测试生成
  模板层；LGPL（semgrep 引擎、rope、pynguin）**仅 subprocess 隔离，禁 import**，
  登记在 `pyproject.toml [project.optional-dependencies].isolated`；GPL 系禁入。
- **新增依赖流程**：总监批准 → 登记 pyproject.toml（含许可证注释）→ 安装于项目根
  .venv（uv/pip + 国内镜像）。本项目自研脚本不因引擎引入而放松本条。
- 跨层唯一通道是 **subprocess + JSON**（pip 包无 Python API 的实测结论，如 ruff）。
- **依赖刷新纪律（每 10 轮盘点，round-86 立宪；首次锚点 round-90）**：
  每 10 轮（round-90 / 100 / …）除本项外不做其他例行动作，盘点 `pyproject.toml`
  三类依赖（运行时 / 可选 / isolated 子进程档）与许可证白名单对照：
  ① 核对国内镜像中可用的更新版本（清华 PyPI 优先，缺包按「主镜像 → 其他国内镜像 →
     国际直连」降级并记录原因，铁约束 8）；
  ② 升级必须重跑全量套件双跑 + 引擎矩阵重测（ruff-matrix / libcst-matrix /
     astgrep-matrix，自研 973/482/250 + 29/2/2 规则口径回归（ruff 0.17.6 / ast-grep 0.51.3，round-220）），矩阵漂移即回滚；
  ③ 盘点结果入轮报（已更新 / 维持 / 受阻+原因），无自动升级——升级决策仍走
     提案人 ≠ 批准人；
  ④ 任一被审仓库出现依赖兼容阻塞时，本纪律临时提前触发。

## 4. 核心治理概念

### 科层制组织 v2（事实源 `skills/director/org.json`）

- 三层管理：总监（只分派与验收）→ 团队首席（runner / fix-apply / approve-patch /
  retro-report / research-brief）→ 成员技能。
- RACI 矩阵固定签字权，A 唯一；提案人 ≠ 批准人（两人规则）。
- SRE 错误预算（org-scorecard.py 每轮结算）：修复回滚率 ≤0.2、审核每轮拒绝 ≤3、
  未结坑 ≤8、无链接案例=0；WARN 整改关注、EXCEEDED 整队整改冻结。
- 值班式升级链：L1 首席（查案例库）→ L2 总监（研究简报/审批）→ L3 人工（NEED_HUMAN）。
- 案例库 v2 是链接型档案（`retro/cases.json`）：无 url 或 local_ref 不得入库；
  成败双轨；本地档案仓 `retro/archive-repo` 由 case-archive.py 提交发布
  （该目录是功能性运行产物，已 .gitignore）。

### 写权限与五道闸

**被审仓库的唯一写入口是 `repair/scripts/fix-apply.py`**。机械补丁、引擎修复产物、
重构 codemod、编码循环编辑全部经它落盘，五道闸依次为：

1. 审核人批准书（approval.json，manifest_sha256 绑定补丁包字节，变动即作废重审）
2. 工作树干净
3. HEAD == base_sha
4. git apply 预检
5. 行为回归（逐文件重扫原规则消失且无新增；发现仓库测试即跑 pytest，失败等同验证失败）

任一失败自动回滚（ROLLED_BACK 也写 apply-log 供迭代官采集）；修复在
`review-fix/<id>` 分支，**永不自动合并**。编码循环不直接写被审仓库（worktree 内
编辑，产出标准补丁后走修复链）。

## 5. 脚本规约（新增任何脚本必须遵守）

1. shebang 开头；模块 docstring 写清「用途 + 用法示例 + 退出码」。
2. stdout 只输出**一个 JSON 文档**，诊断信息走 stderr。带主入口的 Python
   脚本须对 `sys.stdout` 执行 `reconfigure(encoding="utf-8")`；无主入口的库模块除外
   （`doc-structure.py` S10 机械校验，注释/字符串不算真实调用）。
3. 退出码契约：0=成功；1=有可处理的问题（含 NEED_HUMAN / WAIT_HOST_LLM，不是崩溃）；
   2=输入/环境错误；intent-parse 另有 3=需追问。
4. 路径参数显式可指定，禁止硬编码绝对路径。
5. 产物零明文凭据：命中密钥形态 snippet 一律脱敏为 `<redacted>`。
6. 扫描 diff 内容的正则不得行首锚定（`^\s*`）——diff 的 +/- 前缀会让它失配。
7. 每个检查器必须有反向验证（造违规样例确认抓得住），纳入 tests。

### 新增脚本 checklist

- [ ] 满足上述脚本规约
- [ ] `AGENTS.md` 脚本清单加行（51 → N）
- [ ] `tests/` 增契约断言（含反向验证样例）
- [ ] 跑 `session-probe.py --root .`：doc-drift 15 问必须全绿
      （孤儿脚本/主线接入/退出码说明/参数漂移/README 引用等问会逐一核对）
- [ ] 若 docstring/文档行数变化触及行数基线，同步 `BASELINE.md` 行数基线表
- [ ] `fingerprint.py --root .` 指纹必变，属预期

### 新增技能（skill）checklist

- [ ] `skills/<name>/SKILL.md`，头部带 harness frontmatter（name/description）
- [ ] `BASELINE.md` 行数基线表增行（实测行数）
- [ ] `AGENTS.md` 主流程接入点写明（步骤 0-10 / 修复 / 复盘 / 评测）
- [ ] ZCode 暴露需要时登记 `.zcode-plugin/plugin.json`

### 接入新引擎 checklist

- [ ] `engines/<name>_adapter.py`：scan / fix-dry / matrix / clean-fp 四能力 +
      subprocess+JSON 调用（禁 import LGPL）
- [ ] 能力矩阵 JSON 入仓（可自动修复规则集 / safe-unsafe 分级 / 目标语言）
- [ ] 修复链接线：fix-plan 按矩阵分诊 → fix-patch 混合修复（manifest 记 engine 与
      before_codes）→ 闸五按引擎复扫（修复码消失且 after_codes ⊆ before_codes）
- [ ] 引擎修复产物与机械补丁同链落盘，不经任何白名单豁免
- [ ] 引擎在干净样例上的误报（engine_clean_fp）计入错误预算口径

### 新增 MCP 工具

- 工具固定名 + 输入 schema（object）；子进程调用显式参数列表 + `shell=False`，
  脚本目标白名单常量；超时 run 600s、其余 60s。
- **注册点两处缺一不可**：`TOOLS` 目录（tools/list）+ `_TOOL_HANDLERS`
  分发表（tools/call）——漏一处时 tools/list 契约测试抓不到，必须补
  tools/call 真调用用例（v1.24.0 教训）。
- isError 语义：脚本退出码 2 → isError true；退出码 1（NEED_HUMAN）**不是错误**
  （apply/fix 例外：非 0 退出码均算错误）。
- 同步：`tests/test_interop.py` 的 TOOL_NAMES 与 BASELINE「互操作契约」。

## 6. LLM 提供者与宿主协议（llm/provider.py）

- 后端选择：`CRA_LLM_PROVIDER=host|openai|none` 显式优先；未显式且已配置
  `REVIEW_LLM_BASE_URL`+`REVIEW_LLM_MODEL` → openai；否则 none（降级不阻塞）。
- openai 后端：SSRF 白名单（公网 https 或回环）、重试参数读 agent.json args、
  token 计入 totals。
- host 宿主协议（桌面会话内推荐，零 API key）：
  1. `complete()` 计算 id = sha256(system+"\0"+user)[:12]，写
     `<run_dir>/llm-tasks/<id>.prompt.md` + `.meta.json`（status=waiting）后抛
     `HostLLMPending`（退出码 1，回执含 llm_task / llm_response 路径）。
  2. 宿主模型填写 `<id>.response.md`（仅 JSON 数组，可带代码栅栏）。
  3. `--resume` 续跑：同材料 → 同 id → 幂等命中既有 response。
- 响应消费纪律：LLM 输出仍须过 findings-check / 证据锚定才可采纳；响应文件留档
  run 目录供审计。
- **openai 兼容端点适配契约（round-77/78 实跑沉淀）**：
  1. **JSON 模式门控**：`REVIEW_LLM_JSON_MODE=1` 时请求体带
     `response_format={"type":"json_object"}`——部分端点（DeepSeek）的工具
     调用先验会把结构化协议输出劫持成私有标记（DSML），JSON 模式在端点侧
     强制合法 JSON（提示词须含 "JSON" 字样满足端点要求）；缺省关闭、不改
     host 后端行为。契约：`TestOpenAIProviderJSONMode::test_json_mode_env_
     gates_response_format`。
  2. **空内容响应重试**：端点在 JSON 模式下偶发空内容响应；provider 把
     空内容按可重试失败处理（重试循环内 raise）。契约：
     `test_empty_content_retries_then_succeeds`。
  3. **多 JSON 对象解析**：模型偶发一次输出多个动作对象（草稿+终稿）；
     `_parse_response` 逐对象 `raw_decode` 取最后一个成功解码的 dict。
     契约：`TestParseResponseMultiObject` ×2。
  4. **协议提示附录**：对探索节奏偏慢的端点，`code-task.py --protocol-notes
     <file>` 把附录追加到任务文本尾部（随 state 持久化，--resume 安全）；
     样例模板 `agent/protocol-notes-example.md`（预算压力 + 探索上限 +
     先编辑指引 + 失败测试即完成标准）。round-77 实跑：附录使 DeepSeek
     从纯探索耗尽（16 轮 0 编辑）转为有效修复行为。契约：
     `TestProtocolNotes` ×4。

## 7. 测试与评测

### 契约测试（tests/，unittest）

- 覆盖：脚本契约（端到端临时 git 仓库 + 反向验证）、修复/审核链、引擎 e2e、
  编码 e2e（stub 宿主）、MCP 互操作、评测链方向锁定、编码循环产补丁即时校验与
  行为探针开关两侧、临时快照生命周期、结案口径抽取与实跑、落盘历史轮转、stdin UTF-8
  契约（GBK 复现旋钮 + 复现判真 + 四处变异复验）、上下文工程与记忆（稳定前缀 /
  输出外置 / 历史压缩 / Tracer / few-shot 注入 / 记忆压缩）、DeepSWE 驱动器
  退出码、事件账本哈希链与重放对账（篡改/首差异/令牌化）等，共 897 项。
- 运行：`.venv/Scripts/python -m unittest discover -s tests`（必须在项目根跑，discover 以
  tests/ 为 top-level；解释器选择见 §1）。
- **评测双指标契约**：judge 汇总必须同时输出 recall 与 precision，只报一个视为
  不合格；分母只用有效样本（valid_samples），跨编号体系只对齐 sha。
- **映射类能力先量化再交付**：`scripts/sibling-test-bench.py` 用 19 文件 / 7 例合成语料
  给「邻近测试三路映射」做命中率实测，逐例归因到通道（A 具体名 / A 泛化名 / B 路径段 /
  C 内容），输出 `recall_mean`、`precision_mean`、`decoy_hits_total`、
  `noise_unlabeled_total` 与 `by_lane`；口径就是评测双指标契约在这里的落地——
  只报「找到了」不算数，必须报找对率与噪声，且噪声一律要带标注。
  运行：`python scripts/sibling-test-bench.py`（`--verbose` 出逐例明细；退出码 0=跑通、2=环境错）。
  契约被 `tests/test_agent.py::test_sibling_bench_contract` 钉住（含「B 路必须触发」与
  「未标注噪声必须为 0」两条下限）。

### 评测四类

1. **合成语料**：`forward-bench.py synth --out corpus/ --count 120 && fp --corpus`
   —— clean 误报 0 / precision 1.0 / recall 1.0 是回归下限。
2. **真实语料**（CVEfixes，缺陷引入态）：`cve-corpus.py` 适配 + `run-samples.py`
   跑分，方向契约由 TestRealCorpusChain 锁定（扫错方向断言落空）。
3. **SWE-bench**：官方 swebench harness；镜像构建/CRLF 补丁等运维要点见
   `agent/swe-workflow.md` 与 BASELINE「SWE-bench 契约」。
4. **DeepSWE**（v1.44.0 接入 / v1.47.0 首测）：`deepswe-fetch.py` 把 Harbor
   格式语料（113 任务，5 语言）解析成 JSONL 索引（优先 ModelScope 国内源，
   硬约束 8）；`deepswe-sample.py` 串起 clone → checkout → code-task →
   Docker 验证 → 台账，`--registry-mirror` / `--pull-timeout` 显式记录镜像
   降级。首次真实评测 1/20（tomlkit resolved，reward=1），其余待按回归集补跑；
   基线 `reports/deepswe/baseline-v1.44.0.json`。评测链四条硬口径（v1.47.0
   踩坑后固化）：① 判分只认语料 `/logs/verifier/reward.txt`，退出码 0 只是
   「脚本跑完」；② 语料 `test.sh` 挂载前做 CRLF→LF 暂存（Windows 检出的
   CRLF 会让 bash 报 `$'
': command not found`）；③ 宿主须预建
   `<out>/docker-logs/verifier/`，否则 reward 写入失败以 exit=5 中断；
   ④ 子模块（如 tomlkit 的 `tests/toml-test`）未初始化时从镜像内置 `/app`
   克隆补齐并校验钉定 sha，GitHub 不可达也能离线复现。gate 语料按数据集
   许可不入库（`skills/eval-harness/data/`），测试在语料缺失时 skip 并标注
   原因，不装绿。

### 自迭代探针（CI 同款）

```bash
python skills/self-iteration/scripts/session-probe.py --root .   # 15 问全绿
python skills/self-iteration/scripts/dead-code-scan.py --root .  # 零死代码
python skills/eval-harness/scripts/fingerprint.py --root .       # 项目指纹
python skills/self-iteration/scripts/round-gate.py --root . open   # 开局门全 PASS
python skills/self-iteration/scripts/doc-structure.py --root .  # 文档九判据 + 脚本编码契约
python skills/orchestrator/scripts/report-adapter.py --findings <findings.json> --style executive  # 报告适配
python skills/orchestrator/scripts/runner.py --repo <仓库> --range A..B --report-style executive  # 评审交付自动生成风格变体
python skills/eval-harness/scripts/f2p-quality.py --tasks <pool.jsonl> --select --select-out <candidates.jsonl>  # 扩样前选批
python skills/orchestrator/scripts/github-poster.py --repo owner/name --pr 42 --comments pr-kit-out/review-comments.json --dry-run  # 行内评论发布（P0-3）
```

## 8. 版本与发布流程

1. 版本唯一事实源是 `.zcode-plugin/plugin.json` 的 `version`（当前 2.108.0）；
   **同步六处版本 + 计数真值一律跑 `skills/self-iteration/scripts/bump-version.py --root . --set X.Y.Z [--apply] [--sync-counts]`**
   （`pyproject.toml` / `mcp/review_mcp.py SERVER_INFO` / README 头条 / 本文发布口径 /
   PROGRESS 版本行；缺省干跑出计划，`--apply` 落盘、校验失败零写入）；
   `tests/test_interop.py` 断言版本号（动态读取，无需手改）。
2. 在 `docs/BASELINE-HISTORY.md` 末尾追加版本沿革条目（做了什么、清单数 64→N、MCP 工具数；v1.87.0 起沿革分卷）。
3. 版本/计数改完跑 `python skills/self-iteration/scripts/doc-freshness.py --root .`，
   `drift_count=0` 才算传播完成（F1-F10 数字对账，历史值按「数值前 12 字内标记」豁免）。
4. 改 AGENTS.md / skills/ / agent.json args 后**指纹必变**——属预期，无需登记
   指纹值，但依赖指纹的评测要在新指纹下重跑基线。
5. 提交信息用中文描述能力变化；推送前会过 Mimosa 安全闸（见 §10）。
6. 发布：`python skills/self-iteration/scripts/release-gate.py --root . --tag v<version> --run-suite` 七项全绿才可人工打附注 tag（`v<version>`，不自动 push）；复用同轮双跑日志时用两份 `--suite-log`（记录 sha256 / 计数 / 耗时，mode=reuse）；证据落 `reports/release-gate/<version>/`（D-035）。

## 9. Git 工作流与 CI

- 主干 `main`，远端 `origin = https://github.com/Lanigelevent/dev-agent.git`
  （公开 GitHub 仓；内部版本库历史与发布证据不随公开仓同步）。
- CI（`.github/workflows/self-check.yml`，ubuntu+windows × py3.11/3.12/3.13）：
  unittest（CI/PR=smoke 清单 `tests/smoke-manifest.json`，nightly=全量，D-049 A）→ session-probe → dead-code-scan → doc-freshness →
  trigger-audit → forward-bench 合成语料 → fingerprint → **覆盖率对账
  （coverage-gate check，仅 windows-latest × 3.12 单格——基线平台对齐）
  → 凭据形态扫描（secret-scan）→ 依赖许可证校验（license-check）**。
  **推送/PR 前先在本地把这些步骤跑绿**；覆盖率基线更新用
  `coverage-gate.py measure --root . --out skills/self-iteration/coverage-baseline.json`
  （固定五项测试子集：test_scripts_*.py / test_agent.py / test_dual_reviewer.py / test_provider_ssrf.py / test_report_adapter.py——r120 起含 SSRF 安全契约、r123 起含报告适配器契约；全量套件不测覆盖率，实测 2.6× 成本，D-034）。
- 仓库内不入库：`.venv/ datasets/ runs/ logs/ corpus/ reports/_work/
  retro/archive-repo/ .workbuddy/（项目记忆，本地资产）/ 缓存/`
  （见 `.gitignore`）；`retro/archive-repo` 是功能性本地档案仓，留在磁盘。

## 10. 已知坑与运维要点

- **Windows CRLF**：补丁文件必须 LF（CRLF 会使 git apply 失配）；swebench harness
  在 .venv 内两处 `newline="\n"` 补丁，**swebench 重装/升级后必须重打**（见
  BASELINE「SWE-bench 契约」）。
- **下载策略（硬约束 8 铁律）**：所有外部下载先找国内镜像（Gitee 镜像 /
  hf-mirror / 清华 PyPI / NJU / TUNA），国际直连仅作回退并记录降级原因；大文件
  `curl -C -` 断点续传挂后台。**镜像（docker/模型权重）另有铁律：下载前必须
  联网实测国内可达性并优先国内源，判定一律跑 `scripts/docker-mirror-probe.py`
  （blob 段实测才算数，manifest 可达 ≠ 可拉）。**
- **Mimosa 安全闸**：本机 push 前有静态安全扫描，第三方克隆（评测数据）放工作区会
  被误拦——评测数据保持移出工作区或接受扫描后再推；钩子在命令**执行前**拦截，
  「移出 → 提交 → 移回」必须分三次独立调用；写源码必须走编辑工具不走
  shell 重定向。
- **uv trampoline**：整目录移动项目后 `.venv` 内脚本启动器会失效
  （canonicalize 报错），`uv pip install --reinstall <包>` 可修。
- **SWE-bench 编排脚本**：`agent/swe_run.py`（v1.22.0 恢复）代码化
  swe-workflow.md 四阶段；swebench harness 仍按 `agent/swe-workflow.md` 理解。
- **SWE-bench 口径分两档**：`skills/eval-harness/scripts/gold-sample.py` 评
  **gold 补丁**（只验管线）；`skills/eval-harness/scripts/agent-sample.py` 评
  **agent 产出补丁**（收集 `<iid>[-vN]/edits.patch` → 装配预测 → 委托
  gold-sample 评测 → 台账）。agent 侧口径必须**分档记录**：严格首跑（模型
  只见 issue 文本）与按 harness 反馈迭代后的成绩是两件事（v1.25.0 实测
  6/7 → 7/7），严禁混谈。
- **被审仓库的 Python 版本约束**：本机只有 3.12/3.14，老仓库（如 sympy 1.1
  需 ≤3.9，`from collections import Mapping`）直接导入失败——用垫片本地迭代
  （不改被审仓库、不改全局解释器），**最终判定一律以 harness 容器为准**：
  `python agent/legacy_compat.py --repo <被审仓库> -- <命令...>`（垫片是
  `agent/legacy_compat/sitecustomize.py`，经 PYTHONPATH 注入；契约测试
  `tests/test_agent.py::TestLegacyCompat` 带反向验证：无垫片时老式 import
  必失败、有垫片时必通过）。
- **国内镜像缺包时降级**：清华 PyPI 镜像对 mpmath 无匹配版本（`from
  versions: none`）——降级阿里云源（mirrors.aliyun.com/pypi/simple）并记录
  降级原因（铁律 8）。
- **docker 探测三处都查**：PATH（shutil.which）、Program Files、用户目录
  `%LOCALAPPDATA%\Programs\DockerDesktop`——Docker Desktop 支持用户级安装且
  安装器改的是用户 PATH，旧进程环境快照取不到（v1.22.0 实测踩坑，探测口径
  见 swe_run.py find_docker）。
- **Windows 下脚本输出取 ID**：`py print` 打印 CRLF 行尾，bash 反引号取出的 ID
  带 `\r` 会查无此项——脚本提取 ID 后必须 `strip()`，或改用文件传递（台账
  8bad50975bae）。
- **编辑工具做纯空行微调**：old_string 含尾换行的小编辑可能误删 `def` 行尾换行
  使函数体并行成语法错误——无实质变更不提交编辑；插入方法用带上下文的完整块
  （台账 d086f638b262）。
- **五道闸链路的测试夹具先提交**：夹具文件未提交会使工作树脏，闸 2 直接把行为
  回归测试用例本身拦下——凡进五道闸链路的夹具先提交再送审（台账 d2c22ec68c70）。
- **setup_cmds 信任边界**（eval-harness：live-sample / pro-sample / gate-run）：
  任务实例自带 `setup_cmds` 以 `shell=True` 在**被评测 worktree 内**（cwd=repo_dir）
  执行，替代默认 `pip install -e .` 流程。边界条款：
  ① 命令载体是 **SWE-bench 公开语料**（lite/verified 等）实例自带的构建命令，
     非 LLM 生成、非操作者随手输入，信任级别与执行 `pip install -e .` 相同；
  ② 只在被评测仓库 worktree 内执行，不改 dev-agent 仓库、不落被评测仓库之外的
     用户可写路径；
  ③ 来源仅限公开 SWE-bench 语料与总监批准的任务源；接入其他任务源前必须先过
     注入审查（含人工核对 setup_cmds 文本），不得静默信任新来源；
  ④ setup_cmds 失败/超时只记环境失败（blocked / env_failed / setup_failed），
     不冒充任务 F2P 失败、不计入 resolved；
  ⑤ 评测容器化（docker 工作区档）时应默认在容器内执行 setup_cmds；
  ⑥ 本边界**不构成对任意命令的放行**——它只解释为什么公开语料的 setup_cmds
     可以执行，不解释也不授权其他来源的命令。
- **宿主环境注入**：ZCode 宿主向子进程注入 `PYTHONUTF8=1` / `PYTHONIOENCODING=utf-8`，
  会改变 cp936 机器上 subprocess reader 的解码假设（套件 ERROR 的已知诱因）；
  套件启动链一律 `PYTHONUTF8= PYTHONIOENCODING=` 置空后再跑（`logs/suite-r65-*.log`
  实测）；Mimosa 宿主 L3 会误拦 gitignored 评测夹具——commit 前把 `reports/_work/`
  等 gitignored 数据目录移出工作树（round-66 观测，留观不动）。
- **受阻轮补录操作规程（D-052 口径，r141 与 r166/167 两批先例）**：宿主重负载
  判红（EXIT=124，qemu×2 同型取证）按纪律不绕闸、等待负载窗口；恢复后补录三步——
  ①**重跑套件重写日志**：`logs/suite-rN-run1/2.log`，用 `.venv` 解释器（全局 python
  无 pytest-xdist，`-n` 直接 EXIT=4）+ 置空两环境变量 + `timeout 600` + `RUNx_EXIT`
  尾行；重试期间读日志必须先确认文件属主与写入完成（无 `RUNx_EXIT` 尾行即读到
  半截/残留——r166 曾据此误记「三连判红」，勘误 d4e5ec5）。
  ②**换位过闸**：收官门要求 top 收官行==被收官轮（round-gate `_check_next_round_topline`），
  连续受阻轮按时间正序逐轮 close：把被收官轮的收官行换到顶部 → `close --round N
  --round-type light` → 复原 → 下一轮（换位是工作树编辑，随补录 commit 留痕）。
  ③**尾随 commit**（7b60c21 先例）：收官行受阻叙述改补录完成 + PROGRESS §1 快照
  同步 + 缺失版本的发布闸证据补齐（r166/167 补录后版本证据面自 2.43.0 起连续）。
  并行会话抢承接时让位监控、勿双跑勿抢闸。

## 11. 维护红线（八条易错点，全文见 AGENTS.md）

1. 扫描 diff 的正则不得行首锚定。
2. 剥 diff 前缀只保留 + 行，否则符号计数翻倍。
3. 跨编号体系对齐只用不可变标识（sha），不用序号。
4. 汇总层必须输出有效样本数；分母错了不会报错只会算错。
5. 两组数字完全相同 = 一定是 bug。
6. 每个检查器都要有反向验证。
7. 改结论时搜索所有引用处（README / SKILL.md / BASELINE 可能各有一份）。
8. 结论标证据等级：观测 ≠ 因果；单变量实验 ≠ 独立复现。
