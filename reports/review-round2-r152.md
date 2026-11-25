# 第二轮多视角审查（round-152 前置审查，2026-11-14）

> 首轮审查（r136 前置）产出的九轮路线已全部落地收官（r141-r151，v2.43.0→v2.53.0）。
> 本轮审查聚焦「落地之后」的新状态：工作自身浮现的缺口 + 对标基准的复测。

## 一、兑现对账（首轮审查 P0/P1/P2 → 实绩）

| 首轮建议 | 实绩 |
|---|---|
| P0-1 r132 归因修正 | ✅ r137/D-053（README/PROGRESS 四处 + DECISIONS 登记） |
| P0-2 评审质量门禁 | ✅ r138（review-quality-gate.py + judge 前置硬校验 rc=1） |
| P1-3 供应链锁定 | ✅ r139（uv.lock + hash 锁 + dependabot）+ r146（SHA 钉定/权限收敛/SBOM）+ r148（CVE 7→0+nightly 固化） |
| P1-4 口径事实源 | ✅ r141（eval-config.toml） |
| P1-5 第三方 judge | ⏸ blocked（ollama 未装，r140 如实记录；第 113 条候选） |
| P1-6 分级收官 | ✅ r142（light 模式，实战 3 轮省半程） |
| P2-7 变异测试 | ✅ r144（mutmut Windows 不可用 → stdlib 自研，kill_rate 0.8） |
| P2-8 host 跨平台 | ✅ r145（host 流契约 +5 + POSIX 断言） |
| P2-9 沿革瘦身 | ✅ r143（3267→313 字符） |
| 超出路线 | r149 override 锁对齐（pytest 9.2.0 分歧关闭）、r151 astgrep WinError 206 真 bug 修复、r142 light 首战 |

## 二、本轮新发现（按严重度）

### F1【测试债·红线 6 违例】release-gate 解析器无契约
r141 收官时我为 release-gate._parse_suite 打了 pytest 双格式补丁——**补丁本身没有契约测试**。
「每个检查器都要有反向验证」红线在自己手里被绕过；且该解析器是全仓发布判定的事实源。
→ round-152 必修（本报告发布即修）。

### F2【CI 现实缺口】GitHub workflows 在 Gitea 上不运行
仓库托管于内网 Gitea（ssh://git.example.invalid:22）；self-check.yml 双平台矩阵 + nightly
**只是死配置**——Gitea 侧 .gitea/workflows/smoke.yml 仅 3 条 grep 断言。
首轮审查 Scorecard 自评「CI-Tests PASS」**引用错了平台证据**（修正：CI-Tests 实为
「本地发布闸每轮实跑 + Gitea smoke 最小断言」，双平台矩阵属「配置就绪未运行」）。
→ 候选：Gitea runner 注册后移植 self-check 矩阵（操作员动作）；如实降级自评。

### F3【PR 保护面缺口】smoke manifest 200 条测试、新机制 0 覆盖
round-gate light / review-quality-gate / mutation-sampler / provider host 流 /
eval-config 的契约全部不在 smoke manifest——PR 级检查对这些机制零保护。
→ round-152 补录（本报告发布即修）。

### F4【账本断链】event-ledger 哈希链未接轮流程
手册步骤 0 的设施（event-ledger.py，Action/Observation JSONL + sha256 哈希链）
在 r141-r151 十一轮中一次未跑——复盘走的是 retro events JSON（无哈希链）。
→ 候选：轮流程接入 event-ledger（结构改造候选，非一轮能收）。

### F5【文档缺口】06-operations 未覆盖新机制
light 收官 / quality gate / mutation sampler 的运维用法未进操作文档。
→ round-152 补（本报告发布即修）。

### F6【覆盖基线滞后】76.1% 为 r138 时点，r142-151 新代码未重测
→ 候选：下轮 coverage-gate measure。

## 三、对标复测

- OpenSSF Scorecard：整改后 8 项 PASS；**F2 修正后 CI-Tests 应降级为「部分」**
- 评测诚实度纪律维持（对外口径 0.42% 单列、host 臂 unavailable 不冒充）
- 收官效率：xdist 提速 + light 轮使轮固定成本显著下降（401-517s 双跑 vs 693-983s 顺序）

## 四、round-152 即修清单

1. release-gate._parse_suite 契约测试（unittest/pytest 双格式 + 红线反向验证）
2. smoke manifest +12 条（五组新机制契约进 PR 保护面）
3. 06-operations 补三段用法
