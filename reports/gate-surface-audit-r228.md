# round-228：对外口径与门禁面季度复核（零代码 light，v2.101.0 不增版本）

## 1. 门禁面交叉复核（全部 PASS）

- `reports/release-gate/2.101.0/release-gate.json`：`ok=true`，七项（version_sync / doc_freshness / doc_drift / secret_scan / license_check / suite_double_run / git_state）全部 PASS；
  `expected_tests=849`、`redline_sec=600`，600s note 生效。
- 日志指纹：gate 记录的两份日志 sha256 前缀 `74b49acbee90d44e` / `cce64696085b52eb` 与 `logs/suite-r226-run1/2.log` 当前实际文件**逐位一致**（259.69 / 250.52 秒）。
- CI nightly（`self-check.yml`）在册：ubuntu `timeout 600 python -m pytest -n 2 -q`；windows `subprocess.run(..., timeout=600)` → `sys.exit(124)`；job `timeout-minutes: 45`；`--require-hashes -r requirements-lock.txt`；doc-structure / secret-scan / license-check / latency-bench check / pip-audit 十项步骤齐备。

## 2. 发现并修正的口径漂移

- README 与 PROGRESS 的「评测口径」行在后续文档重构中**省略了宿主评审臂状态**；按用户早前裁定（硬规则臂 0.42% 为唯一对外数字，宿主臂标 unavailable），已补回：
  `agent 侧 20/20；对外硬规则臂 0.42%；宿主评审臂 unavailable（n=1000 recall=0，D-053 归因）；部分口径与 blocked 单列`。
- 不改任何数字、不改 D-053 因果表述；`doc-freshness` 漂移 0。

## 3. 观察项（未处置）

- MCP cancel pid 竞态：本轮双跑未再现 `killed_pids=[]`，r223 有界等待加固保持有效。
- D-052 触发线：本轮双跑 246.89 秒，远低于 540s 触发线与 600s 挂死护栏；无新触线窗口。
- 依赖刷新锚点：r226 第十七跑后第 2 轮，~10 轮节奏未到，不刷新。

## 4. 证据

- 本文件；`reports/release-gate/2.101.0/release-gate.json`；`.github/workflows/self-check.yml`；
  `logs/suite-r226-run1/2.log`（sha256 对账）；`logs/suite-r228-run1.log`（本轮 light 全绿 246.89 秒，847 passed + 2 skip）。
