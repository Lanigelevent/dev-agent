# pytest-xdist 前置审计报告（round-98，D-051 A 项前置条件）

> **性质**：审计报告（未实施 xdist）｜ **结论**：**有条件可行**——4 项
> 阻塞点需先修，均为小改动；修完方可进 round-100 的 A 落地。

## 阻塞点清单（按风险排序）

| # | 风险 | 位置 | 修法（预估） |
|---|---|---|---|
| 1 | **共享夹具单例**：`_scripts_common.ensure_fixture` 每进程一次——xdist 每 worker 是独立进程 → 夹具在每 worker 各建一份（可接受，目录独立）但 `tmpspace.sweep(once_per_process)` 与 atexit 注册在多进程下的回收正确性需验证 | tests/_scripts_common.py:175,246 | 验证性测试：2 worker 并行跑 smoke 子集 + 检查无残留/无互删 |
| 2 | **RUN_ID 冲突回收风险**：tmpspace 以「标记 + 年龄阈值」回收；并行 worker 同时创建目录，标记 run 不同、年龄相同——`sweep` 的 once_per_process 在 worker 内各自跑一次，**回收判定只看年龄** ✓ 无互删风险；但 atexit 在 worker 异常退出时的兜底需实测 | tests/tmpspace.py:36,110 | 同上验证测试覆盖 |
| 3 | **coverage-gate 并行采集**：coverage 的 `parallel=True` 已配置（子进程模式）✓；但 coverage-gate 的 measure 走 unittest discover（非 pytest）——**coverage-gate 不受 xdist 影响** ✓ | coverage-gate.py:106 | 无需改动 |
| 4 | **CI 矩阵**：xdist 需进 CI 依赖安装行（`pytest-xdist`）+ 命令改 `-n auto`；windows/ubuntu 双平台 × 3 版本矩阵的 worker 数需实测（windows 进程启动开销大） | .github/workflows/self-check.yml | round-100 一并改 |

## 建议落地顺序（round-100 议程内）

1. 依赖安装 pytest-xdist（dev 组）
2. 阻塞点 1/2 的验证性测试先行（tests/test_xdist_audit.py，2 worker 实跑）
3. CI 命令切 `-n auto`（保留 unittest discover 为 nightly 全量口径不变）
4. 全量双跑 + 发布闸七项（新口径首轮）
