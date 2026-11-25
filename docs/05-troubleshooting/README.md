# 排障（05）

> **创建日期**：2026-11-06 ｜ **当前状态**：维护中 ｜ **所有者**：迭代官
> **权威范围**：本类管「出问题怎么查」——坑台账（权威源 retro/pitfalls.json）+ 常见问题速查（自 README §十收敛）
> **不是权威**：任务排期（07）、设计论证（03）
> **复核期限**：2026-12-06 ｜ **上次复核**：2026-11-06
> **主导模式**：参考（入口） + 参考（常见问题）

## 本类管什么

坑台账导航与常见问题速查。台账真值与逐条根因/对策/验证口径在 [retro/pitfalls.json](../../retro/pitfalls.json)（机械维护：retro-ledger.py 入册 / --close 结案 / --archive 归档；真值计数现取命令见 [08 记忆](../08-memory/INDEX.md)）。

## 台账读法

| 字段 | 含义 |
|---|---|
| status=open | 未结坑（SRE 预算「未结坑 ≤8」口径） |
| status=closed | 已结案（带可验证验收口径） |
| status=archived | 非坑归档（入册错误的完成事件，保留原文） |

无根因不结案；只缓解不治本的条目显式标注留观。当前 open 数为 0；历史留观项均已在台账结案或归档，未结状态以 `retro/pitfalls.json` 当场读取为准。

## 常见问题速查（自 README §十收敛，逐条给根因层）

- **Windows CRLF**：补丁文件必须 LF（CRLF 使 git apply 失配）；swebench harness 在 .venv 内两处 `newline="\n"` 补丁，重装/升级后必须重打——`swe_run.py eval` 自带该补丁的机器自检闸。
- **Mimosa 提交闸**：本机 push/commit 前静态安全扫描会误拦第三方克隆（评测数据）——评测数据保持移出工作区或接受扫描后再推；钩子在命令**执行前**拦截，「移出 → 提交 → 移回」必须分三次独立调用（坑 022913d6c6a4）。
- **宿主 PYTHONUTF8 注入**：ZCode 会话向子进程注入 PYTHONUTF8=1/PYTHONIOENCODING，改变解码行为致 cp936 报错——套件与 locale 敏感子进程链以 `PYTHONUTF8= PYTHONIOENCODING=` 置空前缀运行（坑 8cfbcaf7d227，round-gate 探针已内建净化）。
- **docker 找不到**：Docker Desktop 用户级安装的 PATH 不在旧进程环境快照里——按 `swe_run.py find_docker` 三级顺序探测：显式 > PATH > `%LOCALAPPDATA%\Programs\DockerDesktop`。
- **uv trampoline**：整目录移动项目后 .venv 内脚本启动器失效——`uv pip install --reinstall <包>` 修复。
- **gitee mirrors 不是万能镜像**：并非所有上游仓库都有官方 Gitee 镜像（SWE-bench-tasks 即无，401）——逐仓验证，失败走预构建镜像或记录降级。
- **宿主 Edit/Write 工具大段中文替换静默失效**：大段中文改动走「脚本补丁 + 锚点 count==1 + 读回验证」三件套（坑 daf1a5fc2f9f；严禁 git checkout 当复位）。

## 相关文档

| 文档 | 关系 |
|---|---|
| [retro/next-round.md](../../retro/next-round.md) | 未结坑的轮内留观指针（D7 待办唯一事实源） |
| [docs/06-operations/README.md](../06-operations/README.md) | 命令与运维（故障入口指向本类） |
