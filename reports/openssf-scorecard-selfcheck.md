# OpenSSF Scorecard 自评（round-146，2026-11-13）

对 OpenSSF Scorecard 关键检查项的自评（人工对账，非官方 runner）；
本轮落地两项整改，其余如实记录缺口。

| 检查项 | 状态 | 证据 |
|---|---|---|
| Pinned-Dependencies | **PASS（r146 整改）** | 4 处 GitHub Actions 全部 SHA 钉定（checkout@11bd7190 / setup-python@a26af69，ls-remote 权威 SHA）+ requirements-lock.txt 全量 sha256 |
| Token-Permissions | **PASS（r146 整改）** | self-check.yml 顶层 permissions: contents: read；review.yml 保持最小（pull-requests: write 为行内评论所需） |
| Dependency-Update-Tool | PASS | .github/dependabot.yml（pip + github-actions 双生态 weekly，r139） |
| Vulnerability-Scan | 部分 | license-check.py 管许可证面；CVE 扫描未接（gap，候选：pip-audit 进 nightly） |
| SAST | 部分 | secret-scan.py（凭据形态）+ doc-drift（一致性）；语义 SAST 未接（gap） |
| Binary-Artifacts | PASS | 仓库无提交的二进制产物（datasets/reports/_work 不入库） |
| Maintained | PASS | 257+ commits / 20 天，逐轮收官留痕 |
| CI-Tests | PASS | self-check.yml 双平台 × 3 Python 矩阵 + nightly full + smoke manifest |
| CII-Best-Practices | 未评 | 需注册 bestpractices.badge（候选） |
| SBOM | **PASS（r146 整改）** | reports/sbom/sbom-2.43.0.json（sbom-inventory/1，20 组件，来源 hash 锁定导出） |

## 缺口与候选（如实）

- **CVE 扫描**：pip-audit 进 nightly（需联网，镜像纪律走清华源）——候选 r148+。
- **语义 SAST**：**已自查（round-146 补）**——astgrep 安全族对自身仓 103
  文件全扫：107 条命中全部为 print-debug（CLI 契约下的设计性输出，非缺陷），
  安全族（eval/innerHTML/原型污染等）零命中；报告 reports/sast-selfscan-r146.md。
- **CII badge 注册**：操作员动作。
