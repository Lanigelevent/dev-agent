---
name: orchestrator
description: 一键编排 0–10 步评审主流程，预算/轮数/断点/双闸全部代码强制。也用于口语说法：完整跑一遍评审主流程、全流程端到端跑一次、预算和轮数怎么控制
---

# orchestrator — 评审编排器

## 目的与边界

把 AGENTS.md 主流程 0–10 步从文档变成代码：预算逐次扣减、轮数强制、
断点真实消费、误报模式库下发与回流、交付双闸（report-check + schema-check）。
评审器可插拔：`deterministic`（默认，零网络）或 `llm`（OpenAI 兼容端点，环境变量配置）。

边界约定：

- 对被审仓库只读；产物只落 `--out` 指定的 run 目录。
- LLM 端点白名单：仅允许公网 https 或本地回环，内网/明文一律拒绝（防 SSRF）。
- 任何一步触发人工门即返回 NEED_HUMAN（退出码 1），不静默降级。

## 脚本与用法

### runner.py

```bash
python skills/orchestrator/scripts/runner.py --repo /path/repo --range A..B --request "评审这次改动"
python skills/orchestrator/scripts/runner.py --repo . --range HEAD~1..HEAD --skip-probe
python skills/orchestrator/scripts/runner.py --resume runs/<run_id>
python skills/orchestrator/scripts/runner.py --repo . --range A..B --reviewer llm --feedback rejects.json
```

- `--reviewer deterministic`：确定性评审器（deterministic-rules 产出按维度分发）。
- `--reviewer llm`：读环境变量 `REVIEW_LLM_BASE_URL / REVIEW_LLM_API_KEY / REVIEW_LLM_MODEL`。
- `--reviewer both`：确定性+LLM 双意见合并（确定性优先、loc 去重、source
  标注；LLM 未配置/不可用/私网端点自动降级不阻塞）。
- 宿主模型模式（桌面端会话内推荐，零 API key）：调用方设
  `CRA_LLM_PROVIDER=host` 并用 `--reviewer both`。runner 需要 LLM 时写
  `<run>/llm-tasks/<id>.prompt.md` 并以退出码 1 返回 `WAIT_HOST_LLM`。
  宿主模型义务：读取 prompt.md（# system / # user 两段），按 user 段要求
  **仅输出 JSON 数组**（可带代码栅栏），UTF-8 写入同目录 `<id>.response.md`，
  然后 `--resume <run_dir>` 续跑（保持 CRA_LLM_PROVIDER=host；不必重复
  --reviewer，从 run_meta 恢复）。每个评审维度各一问，可能多次
  WAIT/续跑循环；响应留档审计，LLM 发现仍须过 findings-check 才采纳。
- `--feedback rejects.json`：用户驳回项（`[{"pattern": "...", "dimension": "..."}]`）回流误报模式库。
- `--resume`：断点续跑；产物缺失（verify 退出 1）直接 NEED_HUMAN，不沿用脏状态。

## 强制执行的护栏

| 护栏 | 执行点 |
| --- | --- |
| max_review_minutes | 每步边界检查，耗尽触发 budget_both_exceeded |
| max_total_rounds | 派发与查证轮数计数器，超限即门 |
| max_verification_rounds | 高风险项查证轮数上限 |
| max_dynamic_dispatches | 反向验证后补审额度 |
| checkpoint | 每步完成即写，产物与步骤对齐（ARTIFACT_MAP） |
| 交付双闸 | report-check 与 schema-check 任一失败即 NEED_HUMAN |

## 反馈闭环

1. 派发前 experience.read 下发误报模式。
2. 发现文本命中模式 → 置信度降「中」+ human_review + note，且查证环节不得升回「高」。
3. `--feedback` 驳回项 → experience.record 入库。
4. 下次 run-regression / runner 复跑即验证效果。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 评审完成，报告与产物落 run 目录 |
| 1 | NEED_HUMAN（含触发原因与 gates 清单） |
| 2 | 参数/环境错误 |

## 检查清单

1. 预算四参数全部被代码消费（评审的盲区已修）。
2. 断点产物与步骤一一对应，resume 校验失败不沿用。
3. 证据比对兼容脱敏文本（redacted snippet 对 redacted diff）。
4. 误报模式命中项不被查证自动升回高置信。
5. LLM 端点白名单内联校验，无用户输入拼接 URL。
