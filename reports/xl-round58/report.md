# round-58 · 4.1 子代理分解：XL 多文件任务单例实跑

> 证据等级：单例观测（n=1），夹具自产、同一宿主会话模型。只证明机制可用与
> 轮数受控，不构成「XL 任务 resolved 提升」的因果证据。
> 机器可复算产物：`bench.json`、`fix.patch`、`fixture.py`、`task.txt`。

## 1. 口径

- 任务：`xlib` 金额管线的 5 处口径缺陷（括号负数解析、退款校验与小数位、
  退款汇总、负额渲染、包级传参），修复面跨 **5 个文件**（满足 4.1 的「跨
  ≥5 文件」）；初始 **7 failed / 5 passed**，入口 `tests/test_xlib.py`。
- 两臂对照（同一任务陈述、同一夹具、同一宿主模型 `CRA_LLM_PROVIDER=host`）：
  - **single**：单循环（既有模式），`--rounds 12`；
  - **phases**：`--phases --locate-rounds 2 --rework-max 2`，主循环按
    `agent/phases.py` 裁决 locate（只读）→ fix → verify（只读，机械测试优先）。
- 完成判据：仓库测试转绿（`tests=pass`）；三角色臂额外要求
  `state=DONE, resolved=true` 且 `phases.json` 决策链可查。

## 2. 结果

| 臂 | 状态 | 轮数/预算 | 编辑 | 文件 | +/− | 墙钟 | 独立复验 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| single | DONE | **2/12** | 6 | 5 | +18/−8 | 3.124s | 12 passed |
| phases | DONE·resolved | **4/12** | 6 | 5 | +18/−8 | 3.563s | 12 passed |

- 两臂补丁**字节一致**：`sha256 a2ed125f…76d1da`（`fix.patch`）；独立复验为
  把补丁打到全新检出后 `pytest -q` → 12 passed（两臂各做一次）。
- 三角色臂决策链（`phases.json`）：`locate/accept → fix/accept → verify/accept`
  （accept×3）；locate 轮数 2/2（未降级）、rework 0/2、无升级。
- 差值：三角色多 2 轮（定位轮 + 验证轮），换到「角色动作面门禁 + 机械测试
  优先仲裁 + 可审计裁决台账」；轮数远离预算上限，属受控开销。
- 墙钟只计机器时间（解析/编辑/测试），**不含宿主模型思考时间**；host 文件
  协议不回报 usage，token 如实 N/A。

## 3. 本轮实跑抓到的两个产品缺陷（已修 + 契约测试）

1. **地图静默为空**：`build_map`/`rank_candidates` 用**绝对路径父段**判定
   `SKIP_DIRS`，仓库位于 `reports/`、`runs/` 等同名祖先目录下时整仓 0 文件
   （本次夹具正好在 `reports/_work/` 下）。改为只看仓库内相对路径；
   新增契约 `test_repo_map_not_skipped_by_ancestor_dir_name`。
2. **校验未过不回滚工作树**：补丁即时校验（如新增行非 ASCII）未过时只
   `continue`，被拒改动留在工作区——下一轮按基线文本出的 SEARCH 必然
   「未命中」，且最终补丁仍是被拒内容；系统提示「工作区每轮都从基线重建」
   与实现不符。改为编辑前快照、失败**精确回滚**（并撤销 `edits_applied`
   计数与 blocks_log），提示词同步改为「保留已应用编辑，本轮未过校验的回滚」；
   新增契约 `test_rejected_edit_is_rolled_back_before_retry`。

## 4. 复跑命令

```bash
# 1) 重建夹具（初始 7 failed / 5 passed）
.venv/Scripts/python.exe reports/xl-round58/fixture.py --dest /tmp/xl58/base
git -c core.autocrlf=false clone /tmp/xl58/base /tmp/xl58/run
# 2) 单循环臂（宿主协议：写 <id>.response.md 后 --resume）
CRA_LLM_PROVIDER=host .venv/Scripts/python.exe agent/code-task.py \
  --repo /tmp/xl58/run --task "$(cat reports/xl-round58/task.txt)" \
  --out /tmp/xl58/out --rounds 12
#    三角色臂：加 --phases --locate-rounds 2 --rework-max 2
# 3) 独立复验
git clone /tmp/xl58/base /tmp/xl58/verify
git -C /tmp/xl58/verify apply reports/xl-round58/fix.patch
(cd /tmp/xl58/verify && python -m pytest -q)   # 12 passed
```

## 5. 结论与限制

- 机制面：角色动作面门禁、机械测试优先仲裁、返工预算与升级态在真实多文件
  任务上按设计工作；两臂都以 12 passed 收束，轮数 2/12 与 4/12，不失控。
- **不宣称 uplift**：n=1、夹具自产（出题人与解题人是同一宿主模型）、任务
  陈述显式列出五处症状，难度与 SWE-bench XL 不可比。要谈「resolved 提升」，
  需独立语料 + 独立模型 + 固定端点复跑（接第 21 条 Pro「单发口径」计划）。
- 未测：多文件任务下三角色的轮次收益（路径浪费轮）、返工路径的成本；这些
  需要多实例样本，本轮不做外推。
