# MCP 异步作业模式设计稿（round-154 提案，总监 2026-11-18 裁定批准；round-170 落地）

> **状态**：已批准并实现（round-170，v2.72.0）——见 `mcp/review_mcp.py` 的
> `code_review_submit` / `code_review_status` 与 `review://jobs/{job_id}` 资源；
> 工具数 12→14，+6 契约（769→775），假作业冒烟六项全绿。既有同步工具保持不变。

## 背景与问题

code_review_run 在大 diff 上按 0-10 步并行评审，墙钟达分钟~小时级；当前
MCP 全部 12 工具为同步 stdio 调用——后端 LLM 消费方要么阻塞整个会话等待，
要么自行超时重试（无法感知进度，也无法安全断线重连）。行业参照：GitHub
MCP Server 的 job 提交/轮询模式、Playwright MCP 的进度通知。

## 目标形态（双工具 + 一资源）

| 新增 | 签名草案 | 语义 |
|---|---|---|
| code_review_submit | (repo, range, budget) → {job_id} | 提交异步评审作业，立即返回 job_id |
| code_review_status | (job_id) → {state, step, progress, findings_url} | 轮询作业状态（queued/running/step-N/done/failed） |
| review://jobs/{job_id} | MCP resource | 作业产物只读资源（findings.json/报告），LLM 按需拉取 |

既有同步工具保留不变（向后兼容）；submit 内部复用 runner.py 全流程与
断点/checkpoint 设施——**断线重连 = --resume 已有能力，只差 job 外壳**。

## 实现要点

1. **作业存储**：runs/jobs/{job_id}/（checkpoint.json + status.json + 产物），
   纯文件形态与现有断点设施同构，无新增依赖。
2. **执行器**：MCP 服务器进程内起子进程跑 runner（Windows 无 fork——
   subprocess.Popen + 轮询 status.json；job 超时沿用 D-052 600s 语义放大版）。
3. **状态机**：queued → running（写 status.json 每步一帧，复用 runner 的
   stderr 流式进度帧落盘）→ done/failed（exit 码 + 失败归因字段）。
4. **安全**：job_id 为 uuid4；submit 参数与同步工具同一白名单校验；
   status 只读作业目录，无任意路径面。

## 代价与风险

- 服务器进程生命周期管理（stdio 断开时作业是否续跑——建议：作业独立于
  连接存活，重连后凭 job_id 续查，与 --resume 语义一致）。
- 双工具使 MCP 面从 12→14，LLM 消费方工具卡成本 +2 条描述。
- 涉及 runner 子进程编排，工作量约一轮（含 +6 契约与假 job 冒烟）。

## 建议裁决

批准则排 round-156+（一轮实现 + 一轮真作业冒烟）；不批则维持同步形态，
LLM 消费方以「budget 分档小步跑」规避长阻塞。
