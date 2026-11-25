---
name: git-change-analysis
description: 预检定档、11 类边界形态机械检测与代码图增量缓存。也用于口语说法：这次改动有多大怎么定档、改动的边界形态在哪、建一下代码图缓存
---

# git-change-analysis — 取数与边界分析

## 目的与边界

主流程步骤 2 的数据入口：预检门、11 类边界形态机械检测、代码图缓存。
原则是「一次取数、全程复用」：diff/numstat/历史统计在此一次采齐，
后续步骤不再各自访问仓库，访问也必须只读且版本锚定。

边界约定：

- 本 skill 对仓库只读（rev-parse/diff/log/ls-tree/show/worktree list/config 读）。
- 版本锚定硬规则：diff 之外的代码必须用 `git show <rev>:<路径>` 取自评审对象那一版。
- 预算与档位是决策输入，不是装饰：预算两档都超必须拒绝开审。

## 何时用 / 何时不用

用：意图解析通过（A/B 级）之后的任何评审。
不用：仓库不可读、rev 不可解析（preflight 拒绝后走 human-gate）。

## 脚本与用法

### preflight.py（预检门）

```bash
python skills/git-change-analysis/scripts/preflight.py --repo /path/repo --range main..feature
python skills/git-change-analysis/scripts/preflight.py --repo . --range HEAD~1..HEAD --config /path/agent.json
```

- 输入：`--repo`、`--range` 必填；`--config` 可选（agent.json 定位顺序：显式 > CWD > 项目根）。
- 输出：`profile`（S/M/L/XL）、`files`、`source_lines`、`commits`、`shallow`、
  `budget{typical,upper,max,upper_exceeded}`、`config`、`config_source`。
- 定档：S(<=50 文件且 <=3000 行) / M(<=300 且 <=30000) / L(<=2000 且 <=200000) / XL。
- 预算两档：typical 与 upper 分钟估计；两档都超 `max_review_minutes` → 退出 1 拒绝。
- 仅 upper 超 → 退出 0 但 `upper_exceeded=true`，编排层考虑降档。

### edge-detect.py（边界形态）

```bash
python skills/git-change-analysis/scripts/edge-detect.py --repo /path/repo --range A..B
python skills/git-change-analysis/scripts/edge-detect.py --repo .   # 缺省 HEAD~1..HEAD
```

- 输出：`edges[]` 共 11 类，每类含 `found`、`evidence`、`probe`（探查方法）。
- 每类必须给 evidence：未检出时 evidence 为空但 probe 仍说明查了什么。
- `oversized_single_file` 阈值读 agent.json args 的 `oversized_diff_lines`。

11 类边界形态：

| type | 探查方法 |
| --- | --- |
| merge_commit | `git log --merges <range>` |
| binary_file | numstat 增删行为 `-` 的文件 |
| lfs_pointer | .gitattributes filter=lfs / diff 内 pointer 文本 |
| empty_commit | `git diff-tree --quiet -r <sha>` 退出码 0 |
| submodule_change | `git diff --raw` 中 mode 160000 |
| worktree | git-dir 含 worktrees / worktree list >1 |
| shallow_clone | `rev-parse --is-shallow-repository` |
| sparse_checkout | core.sparseCheckout / info/sparse-checkout |
| monorepo_multi_package | 按顶层目录归并包清单文件，>=2 组 |
| oversized_single_file | 单文件增删行 > oversized_diff_lines |
| pure_rename | `--name-status -M` 全部为 R 状态 |

### graph-cache.py（代码图缓存）

```bash
python skills/git-change-analysis/scripts/graph-cache.py build --repo /path/repo --out cache.json
python skills/git-change-analysis/scripts/graph-cache.py update --repo /path/repo --cache cache.json
```

- build 全量建缓存；update 按 mtime+size 预筛，未变文件不读内容。
- 上限：单符号定义位置超过 64 个只保留同目录的（多数目录），并记入 truncated_symbols。
- relations 总量上限 200000，超限截断并标 `truncated=true`。
- 单文件超过 512KB 跳过解析（记 skipped），避免超长文件拖垮增量更新。

## 输出消费

| 消费方 | 字段 |
| --- | --- |
| 主流程步骤 2 | profile、budget、config → 决定路数与降档 |
| edge-detect 消费方 | found=true 的边界必须出现在运行信息与报告降级说明里 |
| graph-cache 消费方 | symbols/relations 用于跨文件影响判断与补审窗口 |

## 降级规则

- 命中 shallow_clone：历史稳定性统计会低估，报告必须注明。
- 命中 oversized_single_file：材料按 hunk 截窗，禁整文件入材料。
- profile=XL 或 upper_exceeded：降 quick 档并在报告注明降级。
- 降级跨两级以上 → human-gate.py --situation downgrade_two_levels。

## 与主流程的接入点

| 主流程 | 用法 |
| --- | --- |
| 步骤 2 | preflight 通过后，diff/numstat 一次取齐 |
| 步骤 2 | edge-detect 结果写运行信息；empty/merge/submodule 影响派发 |
| 步骤 2 | deterministic-rules 的 diff 输入来自本次取数产物 |
| 步骤 8 | graph-cache 辅助补审定位引用方 |

## 反向验证要求

1. preflight：伪造不可解析 rev → 退出 1；非 git 目录 → 退出 2。
2. edge-detect：含二进制文件的提交必须命中 binary_file 且有 evidence。
3. graph-cache：改一个文件后 update，files_reread 必须只含该文件。
4. 定档阈值钉死在测试（S/M/L 边界值各一条）。

## 退出码汇总

| 脚本 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| preflight.py | 通过 | rev 不可解析 / 预算两档都超 | 参数/环境错误 |
| edge-detect.py | 检测完成 | rev 不可解析 | 参数/环境错误 |
| graph-cache.py | 正常 | - | 参数/环境错误 |

## 检查清单

1. 定档阈值与 BASELINE.md 一致。
2. 预算两档都超退出 1，仅 upper 超只标记不拒绝。
3. 全部 git 调用只读。
4. 版本锚定：show <rev>:<路径>，不读工作区。
5. 11 类边界每类都有 probe 说明。
6. 缓存增量只重读 mtime+size 变化的文件。
7. 超限截断必须标 truncated，不得静默丢弃。
8. 浅克隆低估历史稳定性时必须上报信号。

## 输出字段明细

### preflight.py

| 字段 | 说明 |
| --- | --- |
| profile | S/M/L/XL 定档结果 |
| files / source_lines | 变更文件数与源码增删行合计（二进制不计行） |
| commits | 范围内提交数 |
| shallow | 是否浅克隆 |
| budget.typical / upper | 分钟级预算两档估计 |
| config | 来自 agent.json args 的超时/预算/轮数 |
| config_source | 配置来源：显式路径 / CWD / 项目根 / builtin |

### edge-detect.py

| 字段 | 说明 |
| --- | --- |
| edges[].type | 11 类之一 |
| edges[].found | 是否检出 |
| edges[].evidence | 证据（sha/路径/配置值） |
| edges[].probe | 探查方法说明 |
| any_found | 任一边界检出即 true |

### graph-cache.py

| 字段 | 说明 |
| --- | --- |
| files_scanned / files_reread | 当前文件数 / 实际重读数 |
| symbols | 符号总数 |
| relations_total | import 关系总数 |
| truncated / truncated_symbols | 超限截断标记 |

## 取数产物清单

预检通过后，一次取数应固定产出以下中间产物，后续步骤只读产物不重复访问仓库：

1. diff.patch —— 完整 unified diff（deterministic-rules / dispatch-plan 输入）。
2. numstat 明细 —— 文件级增删行与二进制标记。
3. 提交清单 —— sha + subject（用于意图一致性与历史统计）。
4. 历史稳定性 —— 每文件近 3 个月/12 个月改动次数与修复次数。
5. 边界形态清单 —— edge-detect 输出原文。

## 反向验证样例

- 构造含二进制文件的提交 → binary_file 检出且 evidence 为文件路径。
- 构造 `git commit --allow-empty` → empty_commit 检出且 evidence 为 sha。
- 浅克隆仓库 → shallow_clone 检出，且 preflight.shallow 同步为 true。
- update 前后只改一个文件 → files_reread == 1。
- 超大文件（>512KB）→ skipped 记录 file_too_large。

## 性能与上限

- ls-tree/rev-list 均有行数上限（20000/500），防止 monorepo 拖垮探针。
- graph-cache 单文件 512KB、总量 20000 文件软上限，超限记录不中断。

## 维护注意

- graph-cache 是加速手段，不作为正确性依据；缓存损坏一律重建。
