# jobs 资源扩面提案：cancel 摘要 + event-ledger 重放对账（round-178 提案，待总监裁决）

> **状态（2026-11-18 更新）**：**A+B 已批准并落地**（总监会话裁定「批 A+B」；round-179 实现，契约 786→791，工具数 15 不变）——`resources/read` 增 cancel 摘要 + ledger_verify envelope（旧字段向后兼容），新增 `review://jobs/<id>/ledger` 子资源（64KB 截断标记）；+5 契约全绿，真作业冒烟通过（reports/mcp-resource-smoke-r179.md：killed_pids 非空、ledger_verify.ok=true、子资源含 job.cancel）。
> **C（code_review_replay 工具）仍不在范围**；阶段 C（purge 留存）已另次批准，待后续轮实现。

## 1. 背景与已验证基线

- r170 D-055 落地 submit/status + `review://jobs/<id>`；r172 修 step 帧；r176 落地 cancel + 配置白名单透传；
  r177 补 Unix 信号/回退契约与 `runs/jobs/` 只读审计（6 目录 / 0.2MB）。当前工具 15、契约 786、脚本 86。
- cancel 已把摘要写入**作业目录下的** `ledger.jsonl`（event-ledger `job.cancel` note，`killed_pids` + `state`），
  且 r176 真作业冒烟 `ledger_ok=true`。但 MCP 消费方**无法经现有资源读到该账本**：
  `resources/read` 只返回 `result.json`（done）或 `status.json`（其它态），cancelled 作业的账本摘要不可见。
- event-ledger 自带 `verify` 子命令（哈希链/schema 校验），目前只能在宿主机跑 CLI，MCP 消费方无只读入口。

## 2. 缺口

| 缺口 | 现状 | 影响 |
|---|---|---|
| cancel 摘要不可读 | `review://jobs/<id>` 对 cancelled 作业只回 status，账本里的 killed_pids/observer 不可见 | 宿主无法确认「取消是否真的杀了进程树」，只能信 cancel 工具返回值 |
| 账本完整性不可查 | `verify` 只能 CLI | 断连重连后无法从 MCP 侧确认作业证据链未被篡改 |
| 资源形态不一致 | done 回 result、其它回 status，无统一 envelope | 消费方需按 state 分支解析，易漏字段 |

## 3. 候选方案

- **A（建议先批，最小面）**：**只扩展现有 `resources/read` 的 payload**，不改工具数：
  ```json
  {"job_id": "...", "state": "cancelled|done|...", "status": {...},
   "result": {...} | null,
   "cancel": {"killed_pids": [...], "ledger_ok": true} | null,
   "ledger_verify": {"ok": true, "records": 1, "first_bad": null} | null}
  ```
  - 为向后兼容，保留原顶层字段（现有 `result.json` 内容仍平铺在顶层），新增字段只增不改；
  - `ledger_verify` 通过调用 `event-ledger.py verify --ledger <job_dir>/ledger.jsonl` 得到（有账本才调用，无则 null）；
  - +3 契约：cancelled 资源含 cancel 块、账本被篡改时 `ledger_verify.ok=false`、无账本作业 `ledger_verify=null`。
- **B（可选后续）**：新增子资源 `review://jobs/<id>/ledger`，只读返回账本原文（限 64KB），+2 契约；
  适合需要原文审计的消费方，不改工具数（资源不是工具）。
- **C（超出范围）**：新增 `code_review_replay` 工具重放判定——另案提案，不在本次裁决内。

**提案人建议**：批 **A**；B 视消费方实际需求再议；C 不动。A 落地后工具数仍 15、口径不变、doc-freshness 无新增计数面。

## 4. 安全与边界

- 路径守卫沿用 32 位 hex job_id；账本文件只在 `JOB_ROOT/<32hex>/ledger.jsonl`，无任意路径面。
- 账本 observation 只含 job_id/state/killed_pids，不含凭据；MCP 输出仍受硬约束 5 脱敏纪律。
- 账本读取限 64KB，超出返回截断标记（不静默丢）；`verify` 子进程超时 30s，失败回 `ok=false` 而非崩溃。
- 不改 0.42% / 宿主臂 unavailable 对外口径；不改 cancel 现有语义（已验 killed_pids 非空）。

## 5. 验收判据（若批准 A）

1. +3 契约、总契约 786→789；`resources/read` 对 done/cancelled/running 三态 JSON shape 均有 status + 新字段。
2. 篡改测试：改 ledger.jsonl 一行 → `ledger_verify.ok=false` 且 `first_bad` 非空；正常作业 `ok=true`。
3. 真作业：submit→cancel→`resources/read` 同时见到 `state=cancelled`、`cancel.killed_pids`、`ledger_verify.ok=true`；断连重连后同样可读。
4. MCP 自扫零命中；工具数 15 不变；doc-freshness 漂移 0；双跑/gate/tag 按 D-035。

## 6. 附带观测（非本提案任务）

- 阶段 C（purge 留存）：仍未批准，不实现；`runs/jobs/` 审计维持 r177 快照（6 目录 / 0.2MB），无迫切性。
- 依赖刷新锚点：r173 第十一跑后第 5 轮，~10 轮节奏未到，本轮不刷新。
- D-052 粒度勘误已于 r176 落地（双跑中位 >540s），无新触线窗口。

## 7. 证据

- `reports/mcp-cancel-smoke-r176.md`（cancel 真作业 + ledger_ok=true）；
- `reports/mcp-async-regression-r177.md`（Unix 信号 mock + 目录审计）；
- `mcp/review_mcp.py` 的 `_resource_read` / `_cancel_tool` / `SCRIPT_EVENT_LEDGER` 现状；
- `skills/production-guardrails/scripts/event-ledger.py`（verify 子命令）。
