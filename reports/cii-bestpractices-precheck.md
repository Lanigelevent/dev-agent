# CII Best Practices 预填自查（round-150，2026-11-13）

CII Best Practices badge（https://bestpractices.coreinfrastructure.org）注册前自查清单；
仓内证据已按判据映射，操作员照单勾选即可（注册需人工登录）。

## 基础项（应全部可勾）

| 判据 | 仓内证据 |
|---|---|
| 公开版本库 | Gitea http://gitea.example.invalid:3000/zcx/dev-agent.git（README 从哪拿节） |
| 变更历史公开 | git log 逐轮留痕（257+ commits / 20 天） |
| 版本号 X.Y.Z | 六处真值同步（release-gate version_sync） |
| 发布说明 | docs/BASELINE-HISTORY.md 逐轮条目（含双跑时长/台账/证据指针） |
| 变更追踪 issue/PR | 逐轮台账 + D-001..D-053 ADR |
| 构建可复现 | uv.lock + requirements-lock.txt（hash 锁定，r139） |
| 测试套件 | 739 契约（unittest discover，双跑纪律） |
| CI 集成 | self-check.yml 双平台 × 3 Python + nightly full + smoke manifest |
| 测试覆盖率 | coverage-baseline.json + coverage-gate（0.5pp 容差） |
| 静态分析 | ruff + astgrep 安全族自查（reports/sast-selfscan-r146.md）+ secret-scan |
| 依赖安全扫描 | pip-audit nightly（r148，CVE 7→0 闭环） |
| SBOM | reports/sbom/sbom-2.43.0.json（r146） |
| 加密通道 | Gitea 内网 http——**gap（候选：外网发布时上 https）** |
| 其他硬件资源 | 不适用 |

## 建议操作顺序（操作员动作）

1. 用 GitHub 账号登录 bestpractices.coreinfrastructure.org，项目路径填
   Gitea 仓库地址（若要求 GitHub 公开仓则需镜像或迁移——如实评估）。
2. 按「基础项」表逐条勾选（每条都有现成证据链接）。
3. 达标等级目标：**Passing**（银级需要 ASVF/Golf 类附加项，暂不冲）。
4. 注册后把徽章 markdown 加进 README 头部，并回填本文件的状态列。
