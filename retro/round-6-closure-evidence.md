# round-6 结案证据档案（25 条）

结案原则：对策必须已在仓库内可验证（测试名 / 代码位置 / 文档锚点 / 归档案例），
不许"标完成即完成"（retro SKILL.md 硬约束）。本轮新落地的工作在文末。

| ID | 类别 | 验收口径（仓库内锚点） | 证据状态 |
|---|---|---|---|
| 5fc9903b1f38 | 误报 | runner.py:459 material 过 redact()；新增反向验证 tests/test_scripts.py::test_runner_material_redacted_in_prompts（host 逐问填答 + 全量扫描 prompt 文件） | 本轮补测试后通过 |
| 7ec6fce89ac0 | 误报 | 方向契约 tests/test_taint.py::TestRealCorpusChain；失败案例 8b26199b0a71 已归档 retro/cases.json | 已验证 |
| 8073fbd3b145 | 误报 | 引擎只进修复链：engines/ruff_adapter.py 仅被 skills/repair/scripts/fix-apply.py、fix-patch.py（+tests）引用，评审管线无引擎调用 | 已验证（import 图） |
| 062f26343730 | 手工 | agent/swe-workflow.md：SWE-bench/SWE-bench_Lite 命名空间、model_name_or_path 字段、本地 docker build 全部书面化 | 已验证 |
| 07cf8ce1f8cc | 手工 | 写作规约生效：session-probe doc-drift 15 问全绿（本轮 EXIT=0） | 已验证 |
| 2ae5d49858cb | 手工 | 下载策略入宪：AGENTS.md「下载策略」节 + docs/DEVELOPMENT.md §10 | 已验证 |
| 2ffdd403d017 | 手工 | tests/test_agent.py:25 venv_run() 直调 .venv 解释器，agent 层测试独立 | 已验证 |
| 4e9f24db4b21 | 手工 | engines/ruff_adapter.py:158 `rules = [r for r in rules if r.get("code")]` 过滤未编号规则 | 已验证 |
| 538612b42731 | 手工 | skills/eval-harness/scripts/cve-dump-scan.py 流式扫描入 51 脚本清单 | 已验证 |
| 6016972afe29 | 手工 | resume 形状保真（v1.15.0）+ 中途续跑测试 tests/test_scripts.py:478,924 | 已验证 |
| 8bad50975bae | 手工 | 运维规约成文：docs/DEVELOPMENT.md §10「Windows 下脚本输出取 ID」 | 本轮成文 |
| 906e6e6d01d9 | 手工 | skills/orchestrator/SKILL.md:41-42 写明每维度一问、多次 WAIT/续跑循环 | 已验证 |
| 9d3895093194 | 手工 | agent/repo_map.py:27-31 tree-sitter 0.26 API（_walk + grammar_name），测试全绿 | 已验证 |
| 9d93e1705cb6 | 手工 | subprocess+JSON 跨层通道：engines/ruff_adapter.py 全 subprocess；docs/DEVELOPMENT.md §3 立宪 | 已验证 |
| a37377345434 | 手工 | agent/edit_formats.py:28 END=">>>>>>>" REPLACE；tests/test_agent.py:71,79 块格式与解析器互测 | 已验证 |
| a8c51e998c03 | 手工 | 两人规则入 AGENTS.md 组织架构；窗口变更三件套留痕 retro/events-round-realcorpus.json | 已验证 |
| aceff6563e08 | 手工 | 哨兵语义成文：collect-samples.py 模块 docstring 写明 --limit 0 行为 | 本轮成文 |
| b67f26397fe9 | 手工 | 失败案例双轨归档：retro/cases.json 647dda69645c（jinja2 镜像缺失）、ebee9570de23（策展方法） | 已验证 |
| d086f638b262 | 手工 | 运维规约成文：docs/DEVELOPMENT.md §10「编辑工具纯空行微调」 | 本轮成文 |
| d2c22ec68c70 | 手工 | 运维规约成文：docs/DEVELOPMENT.md §10「五道闸链路的测试夹具先提交」 | 本轮成文 |
| d8c4b419a461 | 手工 | 折衷接受并声明：reports/precision-report-2026-10-24.md 含局限声明 | 已验证 |
| ebf2a3e2a457 | 手工 | scripts/docker-mirror-probe.py 实测口径入仓（token 流+逐跳重定向+首 blob 测速） | 已验证 |
| ef3ebe02120a | 手工 | agent/code-task.py:301-304 仅 manifest 落盘后清 worktree；tests/test_agent.py:119 WAIT 状态断言；django-14999 真跑 | 已验证 |
| a1f04c9d3e77 | 手工 | agent/swe-workflow.md:18-22 heredoc→setup1/2.sh + NJU/TUNA 定向，django-14999 构建通过 | 已验证 |
| b2e15a0e4f88 | 手工 | agent/swe-workflow.md:36-37 harness 两处 newline 补丁书面化（重装后重打） | 已验证 |

## 保留未结（2 条，真待办）

- a1ea933d8e26：Docker 二进制缺失（Windows/WSL 均无），SWE-bench Phase 3B 镜像构建被环境阻塞——等环境而非等代码。
- dcd866f9d912：swe_run.py 脚本形态待静态启发式规则更新后恢复——真实功能待办（整改冻结期不扩功能，仅保留候选）。

## 本轮新落地工作

1. tests/test_scripts.py 新增 `test_runner_material_redacted_in_prompts`：
   runner host 协议逐问填答反向验证，prompt 文件明文凭据零容忍（红线 6 补齐）。
2. collect-samples.py docstring 写清 `--limit` 哨兵语义。
3. docs/DEVELOPMENT.md §10 增三条宿主运维规约（CRLF/strip、编辑工具微调、夹具先提交）。
