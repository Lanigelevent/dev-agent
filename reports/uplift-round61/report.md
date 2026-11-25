# round-61 4.1 uplift 对照基准（独立语料 × 三角色两臂）

## 结论先行

- **4/4 resolved**：两题两臂全部通过机械判分（F2P 全绿 + P2P 全绿），补丁**字节级一致**
  （click 5,856 B sha256 `f7f9db30…`；tomlkit 6,866 B sha256 `feb2afc4…`）。
- **未观测到 uplift**：本基准下三角色臂与单循环臂 resolved 相同（2/2 vs 2/2），
  代价是固定 4 轮（locate 2 + fix 1 + verify 1）对 2 轮。**4.1 的「XL resolved 提升」
  仍不成立为已证主张**，状态维持 ◐。
- 两臂**同一宿主模型**（本会话），不构成跨模型结论；n=2，只证机制与判定口径，不外推。

## 口径

- **语料独立性**：任务取自公开上游真实提交，题目只给诉求、不给实现；测试补丁在开跑前
  种入基线并提交，两臂看到同一批失败测试。
  - click `831c8f09`（父 `19fd4d6e`）：`NoSuchCommand` + `Did you mean` 建议，
    跨 `src/click/{__init__,core,exceptions,parser}.py` 4 个源文件 + 2 个测试文件。
  - tomlkit `0561e5de`（父 `b5da6c94`）：`key([...])` 多段与 `Container` 展开，
    跨 `tomlkit/{api,container,items,parser}.py` 4 个源文件 + `tests/test_api.py`。
  - **XL 操作化**：源文件 ≥4 且含测试文件共 ≥5 个文件改动；两题均满足（6 文件）。
- **判分机械化**：judge 在独立 worktree 上 apply agent 补丁，先跑 F2P node ids
  （click 7 项 / tomlkit 1 项），再跑 P2P（click `tests/test_commands.py` +
  `tests/test_options.py`；tomlkit 全 `tests/`）；`resolved = f2p.rc==0 and p2p.rc==0`，
  不由模型自评。
- **基线自检**：种入测试后基线 click 7 failed / 635 passed；tomlkit 1 failed / 743 passed
  （子模块用提交锚定的 toml-test 27837d3）。
- **模型轴**：两臂均为宿主会话模型（同一模型、同一宿主协议）；**不是**跨模型对照。

## 结果

| 任务 | 臂 | resolved | F2P | P2P | 补丁 B | sha256 | 轮数 | 耗时 s |
|---|---|---|---|---|---|---|---|---|
| click-nosuchcommand | single | ✅ | 7/7 | 642 passed | 5856 | f7f9db30… | 2 | 5.438 |
| click-nosuchcommand | phases | ✅ | 7/7 | 642 passed | 5856 | f7f9db30… | 4 | 6.360 |
| tomlkit-dotted-key | single | ✅ | 1/1 | 744 passed | 6866 | feb2afc4… | 2 | 9.140 |
| tomlkit-dotted-key | phases | ✅ | 1/1 | 744 passed | 6866 | feb2afc4… | 4 | 7.749 |

聚合：single 2/2、phases 2/2；补丁字节数组完全相同。三角色臂的决策台账
（`phases.json`）：locate accept ×1、fix accept ×1、verify accept ×1，rework 0/2、
locate 2/2；无 ESCALATED。

## 解读与限制

1. **resolved 无差异**（2/2 = 2/2）——本样本不支持「三角色提升 XL 成功率」。
   与 round-58 单例（两臂均 resolved）方向一致；两轮独立证据都指向「机制可用、
   提升未证」。样本仍小（n=2 + 单例），不外推。
2. **轮数**：三角色固定 4 轮（locate 2 + fix 1 + verify 1），单循环 2 轮；
   「轮数不失控」成立，但代价可量化。
3. **记忆污染风险**：click/tomlkit 是知名库，宿主模型可能记得上游实现；题目虽未含实现，
   不能排除先验知识帮助。两臂同受影响；该风险对「uplift 无差异」结论是保守方向
   （若两臂都会做，差异更难显形），但不能据此反推机制无效。
4. **环境插曲（如实记录）**：tomlkit 首轮实跑因 worktree 未初始化 `tests/toml-test`
   子模块而全量 error；修复时先误用主仓当前（新版）子模块，导致 32 个与本任务无关的
   `invalid_decode`/数据用例失败；改用**提交锚定的子模块内容**后基线恢复
   （1 failed / 743 passed）。首版 phases 臂因此耗尽 4 轮预算 ESCALATED，
   属环境故障而非机制结论，已按同一协议重跑并留档。

## 复跑

```
py reports/uplift-round61/run-uplift-bench.py prepare --work <dir>
# 每臂按宿主协议跑 code-task（--rounds 4 [--phases]），补丁落 out/edits.patch
py reports/uplift-round61/run-uplift-bench.py judge --task <id> --arm <single|phases> --work <dir>
py reports/uplift-round61/run-uplift-bench.py report --work <dir> --out bench.json
```

本文件数字与 `bench.json` 同源；判分明细见各臂 `judge.json`。
