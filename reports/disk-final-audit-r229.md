# round-229：项目体积与缓存终盘（零代码 light，v2.101.0 不增版本）

## 1. 实测分布

- **总量 7.07 GB / 约 12 万文件**（r222 前 129.49 GB → r222/r223/r226 三轮清理共释放约 122.4 GB）。

| 目录 | 大小 | 判定 |
|---|---:|---|
| `datasets/` | 6.60 GB | 见下细分 |
| `.mimosa/` | 282 MB | 宿主审计账本（finding-ledger / hook-state），保留 |
| `.venv/` | 104 MB | Python 3.12 运行环境，保留 |
| `logs/` | 47.5 MB | suite 日志与评测输出，保留 |
| `skills/` | 15 MB | 含 `eval-harness/data/` 13 MB 语料，保留 |
| `.git/` | 11.7 MB | 全部版本与 tag 历史 |
| 其余（tests/reports/retro/docs/agent/zcode…） | < 10 MB | 受控源码与轮报 |

`datasets/` 细分：`imagecache/` 2.30 GB（Docker 镜像层，硬约束 8 + `docker-image-fetch.py` / `pro-sample.py` / `gold-sample.py` 引用）、`swe-repos/` 2.09 GB（`sibling-test-realbench.py` / `aci-retrieval-bench.py` / `live-sample.py` 直接引用）、`swebench/pro-work/` 1.64 GB（Pro 重跑就位）、`live-cache/` 350 MB（Live 源缓存）、其余 < 100 MB（`live/`、`verified/`、小样本、根索引）。

## 2. 结论

- **无可安全删除项**：剩余内容全部有脚本引用、镜像下载铁律约束或审计证据价值；不再继续清理。
- 三轮清理日志：`reports/cleanup-r222.md`（4.6 GB）、`reports/cleanup-datasets-r223.md`（120.5 GB）、`reports/cleanup-datasets-r226.md`（1.92 GB），均为 gitignored 运行产物，受控文件零删除。
- 观察项：依赖刷新锚点 r226 后第 3 轮未到；MCP cancel 竞态与 D-052 触发线本轮双跑未再现（259.00 秒，线内）。
- 版本/契约/脚本/工具与对外口径不变（2.101.0 / 849 / 90 / 16 / 0.42% + host unavailable）；台账 266 / open 0。

## 3. 证据

- 只读盘点脚本实测（项目各顶层目录 + datasets 子目录）；`git ls-files` 确认受控文件未删；
- `logs/suite-r229-run1.log`（本轮 light 全绿 847 passed + 2 skip）；三轮清理报告。
