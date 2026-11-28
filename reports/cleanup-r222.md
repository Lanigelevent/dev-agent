# round-222：冗余备份与无用文件清理（用户授权全权删除）

- 删除 `reports/_work`：858.9 MB（方式：git-clean-ffdX）
- 删除 `logs/r94-dbg`：6.4 MB（方式：rmtree）
- 删除 `logs/r96-goldref`：33.3 MB（方式：rmtree）
- 删除 `logs/v99-dbg`：6.9 MB（方式：rmtree）
- 删除 `.pytest_cache`：1.1 MB（方式：rmtree）
- 删除 `.ruff_cache`：0.4 MB（方式：rmtree）
- 删除 `.hypothesis`：0.3 MB（方式：rmtree）
- 删除 `corpus`：0.0 MB（方式：rmtree）
- 删除源码 `__pycache__` 目录 25 处

**合计释放约 %.2f GB**（首次 4.57 GB 统计中含已被前一轮 rmtree 部分清理的文件）。

**保留**：所有受控文件（`git ls-files` 无备份形态文件）、`logs/suite-*.log` 与双跑证据、`runs/jobs` 哈希链账本（审计证据）、`datasets/` 缓存语料（重下载代价高）、`.venv/`、`.mimosa/` 审计账本、`retro/archive-repo/` 档案、`skills/eval-harness/data/` 语料。

删除项均经 `git check-ignore` 或 `git ls-files` 预检确认为非受控临时产物；历史报告中引用 `reports/_work/` 的原始临时产物不再可读，结论数字以入仓报告为准。
