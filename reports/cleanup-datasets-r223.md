# round-223：历史评测缓存清理（用户 2026-11-26 确认删除约 118GB）

- 删除 `datasets/swe-out/gold-expand30`：54.43 GB / 199 文件
- 删除 `datasets/swe-out/expand`：28.03 GB / 77 文件
- 删除 `datasets/swe-out/gold-sample`：9.45 GB / 48 文件
- 删除 `datasets/swe-out/expand-cache-private`：6.14 GB / 14 文件
- 删除 `datasets/swebench/pro-runs`：15.01 GB / 336 文件
- 删除 `datasets/swebench/live-runs`：0.83 GB / 24563 文件
- 删除 `datasets/swebench/live-runs-r65`：0.46 GB / 29775 文件
- 删除 `datasets/swebench/live-runs-r67`：0.26 GB / 12448 文件
- 删除 `datasets/swebench/live-runs-r68`：1.03 GB / 51250 文件
- 删除 `datasets/swebench/live-runs-r70`：0.26 GB / 16083 文件
- 删除 `datasets/swebench/live-runs-r71`：3.57 GB / 54067 文件
- 删除 `datasets/swebench/live-runs-r72`：1.02 GB / 40242 文件

**合计释放 %.2f GB**。

**保留**：`datasets/swe-out` 根目录小索引（predictions-*.jsonl 等）、`swebench/pro-work`、`live-cache`、`verified-runs-v107/v108`、`swe-repos`、`imagecache`、`swe-work`、`swrenbench`、`reviewbench`、全部受控文件与 suite 日志。

删除项全部为 gitignored 评测运行产物（数字已固化于入仓报告），不可恢复；如需复核须按脚本重新下载/重跑。
