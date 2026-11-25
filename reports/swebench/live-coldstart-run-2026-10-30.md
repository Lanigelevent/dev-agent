# round-67 D-045 首个冷启动编码数据点：llama_deploy-330（零反馈，f2p-only 判分）

日期：2026-10-30 ｜ 版本：v1.68.0 ｜ 状态：**failed**（D-045 四态如实记录；n=1 不外推）

## 结论

D-045 冷启动协议的**首个零反馈编码数据点**：llama_deploy-330 冷启动
**failed**——宿主文件协议驱动编码循环两次尝试（第 1 次 6 轮预算耗尽 0 编辑；
D-045 允许的 1 次整轮重试用于第 2 次 `--rounds 12`），第 2 次 7 轮 / 1 编辑 /
仓库套件 pass，补丁 1 171 B / 1 文件（`SessionClient.send_event` 最小实现），
判分 live-sample `--mode predictions --f2p-only` 123.468 s：F2P 2 条全败
（`test_run_client` TypeError / `test_run_client_async` AssertionError）。
**与带反馈口径 20/20 并列呈现，校准「带反馈复修 ≠ 冷启动解题」的外推边界**。

## 1. 协议执行（D-045 逐条对账）

| D-045 条款 | 执行情况 |
| --- | --- |
| 任务文本零反馈 | ✅ 仅 problem_statement（108 字符）；F2P/P2P 名称、判分反馈不进任务；循环内搜索确认 base 快照无 hitl/send_event 内容 |
| 预算 ≤45 min/实例 | ❌ **大幅超限**——宿主文件协议每跳含宿主思考与文件落盘，探索轮之间数十秒级往返；如实记录，未刷时间 |
| 预算 ≤20 编辑 | ✅ 只用 1 |
| 预算 ≤1 整轮重试 | ✅ 已用于第 2 次尝试（第 1 次 6 轮 0 编辑） |
| 判分口径 | ✅ f2p-only 部分口径（不计 resolved，D-029/D-045） |
| 四态记录 | ✅ failed（F2P 2/2 败），n=1 标注 |

## 2. 设计与失败分析（零反馈视角）

- 任务：`Add send_event method to SessionClient`。base 快照材料显示：控制面
  session 仅有 tasks 端点、消息层 ActionTypes 无事件类型、`send_event` 全仓
  零命中、human service 走 tasks/handle 流——**事件注入的候选面无法从 base
  材料唯一确定**。
- 宿主实现（零反馈最优努力）：`SessionClient.send_event(ev)` 以当前任务的
  `agent_id` 为目标把事件作为后续任务注入（单文件 +13 行）。
- 判分反馈（判分侧，不回灌编码）：sync 路径 TypeError / async 路径
  AssertionError——F2P 期望的传输语义不同；任务 difficulty 字段为
  **5 文件 / 17 hunks / 128 行**，完整修复面是控制面事件路由改造
  （客户端 + 控制面 + 服务多端协同），单文件最小实现不在同一量级。

## 3. 对 D-045 路线的影响

- 首个数据点说明：**冷启动 n=1 failed 不能与 agent 侧 20/20（带历史判分
  反馈复修）混算或互推**；后续冷启动样本（其余候选）按 D-045 继续如实记
  录，二项区间随 n 增长收敛。
- 执行面改进：宿主协议跑编码循环必须显式 `--rounds`（建议 12）+ 探索止损
  （≤2 轮内进入编辑），已入台账当轮结案。
- 镜像面不变：`resolved` 口径仍阻塞于 Docker Hub 不可达（round-66 判死证
  据可复跑）；f2p_passed 部分口径通路已验证可走通（本轮判分链 123 s）。

## 4. 证据与复跑

```
# 编码跑（宿主协议，两次尝试产物均在）
datasets/swebench/live-runs-r67/coldstart-llama_deploy-330/
datasets/swebench/live-runs-r67/coldstart-llama_deploy-330-attempt1-rounds-exhausted/

# 判分
.venv/Scripts/python.exe skills/eval-harness/scripts/live-sample.py \
  --tasks datasets/swebench/live/gate-r65-llamadeploy.jsonl \
  --mode predictions --f2p-only \
  --predictions datasets/swebench/live-runs-r67/predictions-llama_deploy-330.jsonl \
  --out datasets/swebench/live-runs-r67/live-judge --source-root datasets/swe-repos
```

判分台账 `datasets/swebench/live-runs-r67/live-judge/live-sample-ledger.json`、
失败日志 `datasets/swebench/live-runs-r67/live-judge/work/2fcf73a62b7c/test.log`
（`2 failed, 4 warnings in 11.77s`：sync TypeError / async AssertionError）。

## 5. 边界（不宣称的部分）

- n=1、零反馈、宿主模型既是编排器又是决策核心——**不作任何成功率宣称**；
  失败只证「该实例在该协议该预算下未收敛」，不证「协议不可行」。
- 墙钟超预算如实记录（宿主往返延迟所致），未伪造 45 分钟内完成。
- F2P 测试内容（test patch）未进入编码材料；判分反馈未回灌第二轮之前的
  任何决策（第 2 次尝试先于判分完成，无反馈泄漏）。
