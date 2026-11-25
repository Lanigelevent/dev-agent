# MCP 异步作业扩面设计稿（round-174 提案，待总监裁决）

> **状态（2026-11-18 更新）**：**阶段 B 已批准并落地**（总监授权「按你推荐的步骤推进」，提案人≠批准人红线以用户显式授权满足）；round-176 实现 cancel + 配置白名单透传（+1 工具 14→15、+5 契约 778→783），真作业冒烟通过（running 取消 killed_pids 非空、状态不被覆写、后续 submit 正常 done step=10）。
> **阶段 C（purge 留存）已批准并落地**（总监 2026-11-18 会话裁定；round-180 实现 `code_review_purge`，三重闸 + 中央账本 job.purge 摘要，工具 15→16、+3 契约；真作业冒烟 reports/mcp-purge-smoke-r180.md）。至此 B、C 两阶段均完成；本文件其余内容为原提案正文，不回改。

## 1. 背景与已验证基线

- D-055（r170）已落地 `code_review_submit` / `code_review_status` + `review://jobs/<id>` 资源；
  r171 真作业冒烟发现 step 停在 0，r172 已修（runner stderr `PROGRESS step=N/10` + worker 终局补扫，+3 契约）。
- 真作业两次（r171 job 7d3620da…、r172 job 78b7848a…）均验证：断连重连凭 job_id 可续查、
  `done step=10 exit_code=0`、resource 可读。当前工具数 **14**，契约 **778**，脚本 **86**。
- 作业存储：`runs/jobs/<uuid4>/{job.json,status.json,runner.log,result.json,run/}`；
  `job.json` 记录 cli/runner/created，**不记录 pid**；`status.json` 状态机 queued→running→done/failed。
- LLM 端点/密钥只走环境变量 `REVIEW_LLM_BASE_URL/MODEL/API_KEY`（`llm/provider.py`，SSRF 白名单校验），
  **不得**经 MCP 参数透传（硬约束 5 凭据形态；D-041 端点白名单纪律）。

## 2. 待解决的三个真实缺口

| 缺口 | 现状 | 风险 |
|---|---|---|
| **取消能力** | 作业一旦 submit，D-052 600s 超时只写 `failed`，detached 子进程可能仍在跑；无取消入口 | 宿主想止损只能杀 MCP 进程或等超时；作业仍占 CPU |
| **配置透传受限** | `budget` 与 `config_path` 互斥；budget 生成 job 内 agent.json 仅覆盖 `max_review_minutes` | 轮数/查证轮数等预算字段无法从 submit 端约束；用户只能传任意 config_path（无字段白名单） |
| **作业留存无界** | `runs/jobs/` 无清理；resources/list 只列最近 20 条 | 长期运行磁盘涨；无显式清理/审计入口 |

## 3. 目标形态（按裁决分阶段）

### 阶段 B（建议先落地，+1 工具，工具数 14→15）

1. **`code_review_cancel(job_id)`**：
   - 仅 32 位 hex job_id（与 status 同路径守卫）；只对 `queued|running` 生效，终态作业返回 isError。
   - job.json 增记 `pid`、`process_start`（Unix 用 `os.stat` 启动时间/pid 复用校验；Windows 记 `creationflags` 所需的新进程组 id）。
   - 终止策略：Windows `CTRL_BREAK_EVENT`（submit 时已 `CREATE_NEW_PROCESS_GROUP`），Unix `SIGTERM`；
     超时 5s 未退则 `taskkill /PID … /T /F`（Win）/ `SIGKILL`（Unix）；写 `status.json state=cancelled, exit_code=None, error="cancelled"`。
   - 审计：取消事件写 `event-ledger`（kind=note，replay=opaque，observation 记 job_id/state/actor）。
2. **配置透传（无新工具）**：
   - 放开 `budget` + `config_path` 互斥：budget 优先，读 config_path 的 `args` 后仅覆盖白名单键
     `max_review_minutes`（上限 120）、`max_total_rounds`（上限 64）、`max_verification_rounds`（上限 5），
     写 job 内**沙箱副本** agent.json，原文件不改。
   - 非白名单键一律丢弃并在 submit 结果里回 `ignored_keys` 列表（不静默）；凭据/端点类字段永不允许。

### 阶段 C（B 后再议，+1 工具，工具数 15→16）

3. **`code_review_purge(job_id, confirm=true)`**：
   - 仅终态（done/failed/cancelled）作业可清理；`confirm=true` 显式确认；路径仍限 `JOB_ROOT/<32hex>`。
   - 删除前把 `status.json` 摘要写入 `event-ledger`（kind=note，observation 记 job_id/终态/产物摘要），
     再 `shutil.rmtree`；`isError=true` 用于非法 id / 非终态 / 未 confirm。
   - 留存策略：默认保留最近 20 条终态作业（与 resources/list 上限一致），超出才允许 purge；
     不允许批量 purge（无 glob/通配），降低误删面。

## 4. 候选方案（供裁定）

- **A. 不扩面**：维持 14 工具；取消靠 600s 超时、清理靠人工；零成本但缺口留存。
- **B. 仅取消 + 配置透传**（建议先批）：+1 工具、+5 契约；解决止损与预算约束，风险集中在子进程终止。
- **C. B + 清理留存**（建议后续批）：再 +1 工具、+3 契约；补磁盘与审计闭环，风险集中在误删（confirm + 单 id + 终态三重闸）。
- **提案人建议**：**分阶段 B → C**，不一次性扩到 16 工具；每阶段独立双跑/gate/tag，按 D-035 执行。

## 5. 验收判据（若批准）

1. 契约增量 **+8**（B 5 + C 3），总量 778→786；假作业覆盖：取消 running（终态 cancelled / 进程确退）、
   取消终态作业被拒、pid 复用守卫、白名单 config 覆盖与 ignored_keys 回显、凭据字段被丢弃、
   purge 非法 id/未 confirm/非终态被拒、purge 成功且 event-ledger 有摘要、purge 后 resource 读取失败。
2. MCP 自扫零命中（无空 catch、无路径穿越、无明文凭据，`lang-empty-catch` 等规则不触发）。
3. 真作业冒烟一次：submit → cancel running（阶段 B）→ 新 submit → done step=10 → resource 可读。
4. 工具数随阶段 14→15→16 同步 README/AGENTS/DEVELOPMENT/架构页/MEMORY；doc-freshness 漂移 0。
5. 协议版本、SSH/stdio 传输、既有 14 工具行为均不变（向后兼容）；不改对外评测口径（0.42% / 宿主臂 unavailable）。

## 6. 代价与风险

- 子进程树终止在 Windows 上需 `taskkill /T /F` 兜底，可能误杀同进程组的其他子任务——用独立 job 进程组隔离，禁止复用。
- purge 删除不可恢复（虽有 event-ledger 摘要），必须 confirm + 单 id + 终态三重闸；不支持批量。
- 白名单 config 改变 runner 预算语义，需保留 `ignored_keys` 明示，避免「以为生效其实被丢」。
- 工作量：每阶段约一轮（实现 + 契约 + 双跑 + gate + tag），两阶段共约两轮；工具描述 +2 条增加消费方工具卡成本。

## 7. 证据与引用

- `reports/proposal-mcp-async-r154.md`（D-055 原提案，已批准/落地）；
- `reports/mcp-async-smoke-r171.md`、`reports/mcp-async-smoke-r172.md`（真作业与 step 帧验证）；
- `mcp/review_mcp.py`（submit/status/job worker/resources 现状）；
- `llm/provider.py`（端点/密钥走环境变量，不经 MCP 参数）；
- `docs/DECISIONS.md` D-035（tag/发布边界）、D-052（600s 挂死护栏语义）。
