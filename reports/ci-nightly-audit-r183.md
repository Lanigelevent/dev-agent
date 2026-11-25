# round-183：CI nightly 全量口径复核（零代码，v2.79.0 不增版本）

## 结论先行

- **600s 挂死护栏在 CI 与发布闸双侧仍生效**：
  - ubuntu nightly：`timeout 600 python -m pytest tests -n 2 -q`（self-check.yml:51）；
  - windows nightly：Python `subprocess.run([...], timeout=600)`，超时 `sys.exit(124)` 判红（:57–62）——**比旧文档记录的「仅 job-level timeout-minutes: 45 兜底」更强**，r139 已补 subprocess 包装；45 分钟作业级上限仍在（:19），作为二次兜底；
  - release-gate：`REDLINE_SEC = 600`（release-gate.py:78）+ `redline_note` 600s（:351），>600s 的复用日志同样判红。
- **nightly 触发与依赖安装**：cron `0 19 * * *` 每日（:12）；CI/PR 走 smoke 清单、nightly 走全量（:45–51）；安装用 `--require-hashes -r requirements-lock.txt`（:44，锁文件在仓 38KB）。
- **nightly 门禁面（逐项在册）**：session-probe、dead-code-scan、doc-freshness、doc-structure（r165 接线）、release-gate `--only version_sync`、trigger-audit、coverage-gate（仅 win×3.12）、secret-scan、license-check、forward-bench synth/fp、fingerprint、pip-audit CVE（nightly 每次，钉 2.10.1）、latency-bench run+check（p95 逐档断言，r155）。
- **无漂移、无需改动**：旧轮次文档里「Windows 仅 job-level 兜底」的描述属历史口径（r135），当前 CI 已升级，不回改历史卷。契约 794 / 脚本 86 / 工具 16 / 对外口径（0.42% / 宿主臂 unavailable）均不变。

## 证据

- `.github/workflows/self-check.yml`（nightly 双 OS 全量 + 全部门禁步骤）；
- `skills/self-iteration/scripts/release-gate.py:78,351`（600s 判红）；
- `requirements-lock.txt`（hash 锁，38,350 字节）；
- 本文件。
