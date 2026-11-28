# round-224：剩余 datasets 二次盘点（零代码 light）

## 1. 现状

r223 删除 120.50 GB 后项目总量 **8.99 GB**，其中 `datasets/` 约 **8.54 GB**：

| 目录 | 大小 | 内容 / 判定 |
|---|---:|---|
| `swebench/pro-work/` | 1.64 GB | Pro 评测 worktree（Pro 重跑需重建，暂留） |
| `imagecache/` | 2.30 GB | `django-11039.tar` + `blobs/` + `plan.json`——Docker 镜像层；**保留**（硬约束 8 镜像铁律，重下代价高；`docker-image-fetch.py` / `pro-sample.py` / `gold-sample.py` 引用） |
| `swe-repos/` | 2.09 GB | 真实仓库克隆（zulip 651 MB / sympy 395 MB / synapse 280 MB / matplotlib 190 MB …）——**保留**（`sibling-test-realbench.py`、`aci-retrieval-bench.py`、`live-sample.py` 直接引用） |
| `swebench/verified-runs-v99/v103/v107/v108/` | 0.97 GB | 历史 verified 运行输出；数字已入仓，**可清候选** |
| `swe-work/` | 0.64 GB | 27 个单题 worktree；主链以 `swe-repos` 为 source-root，**可清候选**（重跑需重建） |
| `swebench/live-cache/` | 0.35 GB | Live 源缓存——**保留**（`live-sample.py` 用） |
| `swebench/live-runs-extra` / `live-work` / `live/` / `verified/` | 0.22 GB | 历史小产物，**可清候选** |
| `swe-out/` | 0.16 GB | 根索引（predictions-*.jsonl 等）+ harness/106 MB + django 单题 53 MB——**保留索引**；harness/单题可清候选 |
| `swrenbench/` | 0.09 GB | `swr-slim.jsonl` + 全量语料——**保留**（0.42% 口径复算依赖） |
| `reviewbench/` | 0.014 GB | golden/diffs/corpus——**保留**（precision-gate 语料） |
| `deepswe-out/` `swe-tasks/` | 0.01 GB | 小样本，保留 |

## 2. 结论

- **无脚本硬编码依赖**任何 `verified-runs-v*` / `pro-work` / `swe-work` / `live-runs-extra` 路径：
  所有评测脚本的 `--out` 都是 required 参数（grep `add_argument("--out")` 覆盖 31 处），旧产物只是历史输出。
- 建议保留：imagecache、swe-repos、live-cache、swrenbench、reviewbench、swe-out 小索引、deepswe-out/swe-tasks。
- 可清候选合计约 **2 GB**（verified-runs 四轮 0.97 + swe-work 0.64 + live-extra/work 0.22 + swe-out harness/单题 0.16）——**未删除**，等用户明确裁定（上一轮裁定只覆盖 swe-out 四目录 + swebench pro-runs/live-runs 系列）。
- `pro-work/` 1.64 GB 不建议删：Pro 口径重跑依赖 worktree 就位，重建代价高于磁盘收益。

## 3. 附带观察

- 依赖刷新锚点：r220 第十六跑后第 4 轮，~10 轮节奏未到，本轮不刷新。
- MCP cancel pid 竞态：本轮双跑若再现 `killed_pids=[]`，再采进程树/文件时间戳定位；未再现则不入坑。
- 对外口径不变（0.42% / 宿主臂 unavailable）；契约 849 / 脚本 90 / 工具 16 不变。
