# round-226：剩余历史评测缓存清理（用户裁定执行 item 189①）

- 删除 `datasets/swebench/verified-runs-v99`：0.082 GB / 8666 文件
- 删除 `datasets/swebench/verified-runs-v103`：0.111 GB / 18177 文件
- 删除 `datasets/swebench/verified-runs-v107`：0.425 GB / 58811 文件
- 删除 `datasets/swebench/verified-runs-v108`：0.329 GB / 47129 文件
- 删除 `datasets/swebench/live-runs-extra`：0.117 GB / 8049 文件
- 删除 `datasets/swebench/live-work`：0.054 GB / 3134 文件
- 删除 `datasets/swe-work`：0.642 GB / 63648 文件
- 删除 `datasets/swe-out/harness`：0.107 GB / 891 文件
- 删除 `datasets/swe-out/django__django-14999`：0.053 GB / 7650 文件

**合计 %.3f GB**。

保留：imagecache、swe-repos、swebench/pro-work、live-cache、verified 主体、swrenbench/reviewbench、swe-out 根索引（predictions-*.jsonl 等）、全部受控文件与日志。

均为 gitignored 历史运行产物，数字已入仓；原始产物不可恢复。
