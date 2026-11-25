# ACI 工具面审计（AB-07，r195，2026-11-21）

> 准则源：SWE-agent ACI 研究三准则（**短命令 / 反馈及时 / 防呆**；接口设计决定 agent 成功率）。上游补研受阻：SWE-agent 官方文档直连与 CDN 均被网络重置（铁律 8 不傻等）——审计以资料三准则 + 本仓工具面实现为准，接口实例细节留待网络窗口补研。
> 同轮顺路 AB-15：原子 Edit 与终端闸对照（opencode 准则）。

## 一、16 工具 × 三准则审计表

| 工具 | 短命令（参数面最小化/必填清晰） | 反馈及时（JSON/退出码语义/错误即返） | 防呆（危险面拦截/条件必填显式） | 处置 |
|---|---|---|---|---|
| code_review_run | ✓9 参全可选各有其责 | ✓编排 JSON+NEED_HUMAN 语义 | ✓skip_probe 显式 | 描述已含 |
| code_review_scan | ✓2 参 | ✓rc=2 语义 | ⚠️exactly-one-of 仅描述级 | **修订①**：失败语义写入描述（同给/缺省→rc=2） |
| code_review_plan | ✓3 参 | ✓ | ✓ | 描述已含 |
| code_review_feedback | ✓2 参必填 | ✓ | ✓写经验库非被审仓 | 描述已含 |
| code_review_approve | ✓3 必填+mode 条件参数 | ✓REJECTED rc=1 语义 | ✓mode 条件参数说明 | 描述已含 |
| code_review_fix | ✓3 必填 | ✓ | ✓destructiveHint | 描述已含 |
| code_review_retro | ✓mode 条件参数 | ✓round 真仓必填说明 | ✓close_id+note 配对 | 描述已含 |
| code_review_director | ✓ | ✓ | ⚠️prose 漏 scorecard | **修订②**：prose 补 scorecard |
| code_review_testgen | ✓mode 条件参数 | ✓ | ✓ | 描述已含 |
| code_review_coding | ⚠️repo/task 因 resume 模式不进 required——**schema 无法表达条件必填** | ✓WAIT_HOST_LLM 语义 | ⚠️条件必填仅脚本侧 | **修订③**：resume/new 两模式参数要求写入描述+缺失即错语义 |
| code_review_refactor | ✓ | ✓ | ✓需 .venv 说明 | 描述已含 |
| code_review_apply | ✓ | ✓PROPOSED/APPLIED/ROLLED_BACK 语义 | ✓confirm+批准书 sha256+自动回滚（最强防呆面） | 描述已含 |
| code_review_submit | ✓ | ✓queued+资源 URI | ✓写面限于 JOB_ROOT | 描述已含 |
| code_review_status | ✓1 参 | ✓ | ✓ | 描述已含 |
| code_review_cancel | ✓1 参 | ✓ | ✓仅 queued/running 可取消 | 描述已含 |
| code_review_purge | ✓1 参+confirm | ✓ | ✓三重闸+账本摘要前置 | 描述最防呆面 |

## 二、AB-15 对照审计（opencode 准则）

- **edit_formats 原子 Edit**：SEARCH 唯一命中（count==0 → 缺错；count>1 → "需唯一"错误，失败不写入）——**与 opencode「唯一匹配→原子替换→失败不写」同型，已对齐 ✓**（agent/edit_formats.py L129-134）。
- **终端闸**：MCP 层 timeout=600 包裹；材料层 MAX_INLINE_CHARS/MAX_INLINE_LINES 截断；白名单面=五道闸治理下的宿主协议层。**结论：已对齐（参数名与 opencode 不同，机制同型）✓**。
- 差异项：无（预期结论成立）。

## 三、量化收益说明（诚实口径）

本次修订均为**描述面文字**（不改工具行为），deterministic 评审臂不读工具描述——precision 护栏数字**预期不变**；ACI 收益的量化发生在 LLM 评审臂/编码循环等「消费工具描述」的场景（LLM 臂启用时复测）。护栏复测以全量套件回归代替（描述改动零行为变更的实证）。
