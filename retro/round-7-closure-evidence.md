# round-7 结案证据档案（3 条；台账 30 条全部结案）

## dcd866f9d912（SWE-bench 编排脚本恢复）

- 阻塞条件复核：v1.20.0 时五种安全写法被静态启发式拦截；本轮以探针实测当前
  Mimosa（normal+deep 双档、独立目录 0 发现），恢复后对全项目 deep 扫描
  **0 发现**（scanId scan-2026-10-24T22-02-08.791Z-ca09a90ae96b，seal
  sha256:e84dfe5e6bf284c4078e9f4cdb764cbef2b3631fa019ba9be19478d906cc06ef）。
- agent/swe_run.py 四阶段（prepare/build/eval/report）：
  - prepare 转换与 v1.21.0 手工产物**字节级等价**（setup1/2.sh diff=0；
    Dockerfile.local 仅注释措辞差异，功能行零差异）；
  - eval 真实端到端：run_id=cra-swerun-1 重跑 django__django-14999，
    官方 harness 判 **resolved 1/1**（F2P 1 pass/0 fail）；
  - report 可解析新跑与历史首评（cra-first2）；
  - tests：TestSweRun 六断言（heredoc 抽取/国内源改写/任务 id 校验/
    docker 门控/predictions 字段校验/dry-run/report 解析）全绿。

## a1ea933d8e26（Docker 探测）——前提勘误结案

- 事实澄清：Docker Desktop v4.96.3 一直在运行（用户出示截图 + docker
  version server=29.9.2 + 任务镜像 4.4GB 在位）。探测误判根因：用户级安装
  （%LOCALAPPDATA%\Programs\DockerDesktop），安装器更新用户 PATH，而探测
  进程的环境快照是旧的。
- 对策落地：探测口径成文（docs/DEVELOPMENT.md §10）+ find_docker 三级
  发现固化进 swe_run.py。

## b86a3400b44f（新增：docker 探测口径坑，即结）

- 见上：三处探测口径写入 DEVELOPMENT.md §10，代码固化 find_docker。

## 本轮新落地工作

1. agent/swe_run.py（v1.22.0）：SWE-bench 四阶段编排，纯标准库，六项契约测试。
2. 版本 1.21.0→1.22.0（plugin.json / pyproject / review_mcp / test_interop）。
3. 文档同步：DEVELOPMENT.md §2/§10、BASELINE 沿革+SWE-bench 契约、
   全部 swe_run 引用处核对（红线 7）。
4. 验证：unittest 177 项全绿；session-probe 15 问全绿；Mimosa deep 0 发现。
