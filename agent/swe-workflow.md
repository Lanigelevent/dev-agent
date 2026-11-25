# SWE-bench 评测工作流（Phase 3B；全链路已打通，首评 1/1 resolved）

Docker 就绪（29.9.2，32C/30GiB）。**2026-10-25 全链路验证**：
`django__django-14999` 从 worktree 检出到官方 harness 判定
**resolved**（FAIL_TO_PASS `test_rename_model_with_db_table_noop` 转绿，
PASS_TO_PASS 全保），run_id=cra-first2，单实例评测 25 秒。

## 镜像获取路径（实测定型，勿再走弯路）

1. 公开加速器对 `swebench/sweb.eval.*` **全部不可用**（scripts/
   docker-mirror-probe.py 八源并行实测判死；docker CLI 的
   "Pulling from" 是假启动）。纪律：2 分钟内慢即判死，不傻等。
2. 基础镜像 `ubuntu:jammy`：docker hub 及加速器均不可拉——用
   mirror.nju.edu.cn/ubuntu-cdimage 的 ubuntu-base rootfs（30MB，
   实测 57MB/s）`docker import` 获得（已就位）。
3. **任务镜像本地构建**：sparse clone `SWE-bench/swe-bench-tasks`
   （--depth 1 --filter=blob:none --sparse + sparse-checkout set
   tasks/<id>）后，**官方 Dockerfile 的 BuildKit heredoc（RUN <<EOF_x）
   与 import 基镜像不兼容**（exit 127 /dev/pipes/EOF_x not found）——
   已修：heredoc 块逐字抽成 setup1.sh/setup2.sh + Dockerfile.local 用
   COPY + `RUN ["/bin/bash", "/tmp/setupN.sh"]` 替代，并把网络步骤定向
   国内源（apt/miniconda→mirror.nju.edu.cn，conda 渠道/pip→TUNA；
   版本 pin 不变）。django-14999 构建全程 ~6 分钟一次通过。
4. swebench 5.0.2 的 --task_repo 自动构建导入 Unix-only `resource`
   模块，Windows 原生不可用——上述手动 build 等价替代。
5. **预构建镜像直拉（v1.22.0 实测：docker 客户端不可用，用逐层下载器）**：
   上游为大量实例发布过预构建 eval 镜像，实例→镜像映射来自 harness 缓存的
   2.0 数据集 image 列（本机已导出 datasets/swebench/lite-test-image-map.csv）。
   **docker pull 在慢 CDN 下假启动**（manifest 秒回、blob 307→CDN 挂死，
   round-8/10/11 三轮实测），镜像源判定一律跑
   `scripts/docker-mirror-probe.py`（blob 段实测 + phase 分段死因）。
   **可用路径 = `scripts/docker-image-fetch.py` 四阶段**：
   plan（token+manifest 选 amd64）→ fetch（逐 blob **并行 Range 分段**
   （`--segments 16 --workers 8`；**连接数上限 16**——aria2 社区硬约定
   （官方手册 -x 上限 16），实测 24/32/48 无吞吐增益且 TLS 握手超时
   开始出现；本机到该 CDN 总带宽天花板 ~100KB/s，16 连接已饱和）；
   边界只依赖 total 跨运行稳定；工作文件改进程唯一名
   （`<hex>.part.p<pid>` / `<hex>.seg<i>.p<pid>`，round-28 纪律 8：并发会话
   不共享半成品，WinError 32 的正式修法），旧版遗留的 `<hex>.part` 与
   「此刻无人持有」的他人半成品按**改名认领**回收，段 0 基线照样继承）+
   sha256 强制验证，curl 语义跨主机剥离 Authorization）→
   assemble（OCI image layout tar，blob 原样入档不重压缩）→ load
   （docker load）。中断后重跑 fetch 即续传（同进程直接接着自己的中间名；
   跨进程走认领，边界只依赖 total 故 seg 前缀同样可继承）。tasks 仓
   （Dockerfile 源）同窗口不可达：github 直连/
   容器/常见代理全断，gitee mirrors 不收 SWE-bench-tasks（401）——
   判定存在性以浅克隆试探为准（ls-remote 空响应是假象）。

## Windows 宿主跑 harness 的 CRLF 大坑（已修，重装须重打）

harness 在宿主写 eval.sh / model patch 用 `Path.write_text` 文本模式，
Windows 上被翻译成 CRLF 再 docker cp 进容器：`set: pipefail\r` 报错、
`cd /testbed\r` 找不到目录、内嵌 test patch 的 git apply 全线失败，
表象是 **ambiguous failure**（无 infra failure）。

修复（已打在 .venv，**swebench 重装/升级后必须重打**）：
`.venv/Lib/site-packages/swebench/harness/run_evaluation.py`
- ~L291 `patch_file.write_text(pred["model_patch"] or "", newline="\n")`
- ~L360 `eval_file.write_text(..., newline="\n")`

## 已验证的评测命令序列（ django__django-14999 实录）

    # 1) agent 侧（已完成，产物在 datasets/swe-out/）
    #    worktree 检出 base_commit → code-task.py 宿主协议（CRA_LLM_PROVIDER=host，
    #    WAIT_HOST_LLM → 宿主填 llm-tasks 响应 → --resume）→ edits.patch
    #    → predictions.jsonl（必须含 model_name_or_path 字段）
    # 2) 镜像构建（一次性；task 目录在 datasets/swe-tasks/repo/tasks/<id>）
    docker build -f Dockerfile.local --progress=plain \
      -t swebench/sweb.eval.x86_64.django_1776_django-14999:latest .
    # 3) 官方评测（镜像名后缀 django_1776 来自数据集 image 列）
    HF_ENDPOINT=https://hf-mirror.com .venv/Scripts/python.exe \
      -m swebench.harness.run_evaluation \
      --dataset_name SWE-bench/SWE-bench_Lite \
      --predictions_path datasets/swe-out/predictions.jsonl \
      --run_id <run_id> --max_workers 1
    # 报告：reports/swebench/code-review-agent.<run_id>.json（历史产物归档）+
    #       logs/run_evaluation/<run_id>/<model>/<id>/report.json（测试级明细）

数据集名必须是 `SWE-bench/SWE-bench_Lite`（5.0.2 的 2.0 格式，带
image/eval_script 列；`princeton-nlp/...` 旧格式 KeyError: image）。

## agent 侧管道要点

- code-task 真 bug 已修：WAIT_HOST_LLM 暂停退出不再误删含已应用编辑的
  worktree（仅收束后清理，django-14999 真跑验证）。
- **补丁产物必须纯净**：`git diff` 的 stdout 与 stderr 必须分离——autocrlf 的
  CRLF 警告走 stderr，混进补丁会让产物不再是合法 unified diff（round-18 修，
  契约测试 `tests/test_agent.py::TestCodeTaskPatchHygiene`）。
- **`--resume` 幂等**：已收束（`task-manifest.json` 存在）再续跑只回放结果，
  不重建 worktree、不改写补丁（round-18 修）。
- **测试探测要覆盖包内布局**：sympy/astropy/scikit-learn 的测试在
  `pkg/**/tests/`，只查仓库根会误判「无测试」而跳过验收闸（round-18 修，
  `_discover_test_paths` 递归发现有界）。
- 克隆根 datasets/swe-repos/（Gitee 镜像 `gitee.com/mirrors/<name>`；
  django/sympy/zulip/aiohttp 等实测有镜像）。容器内 git clone
  github.com 本次实测可达（未需 gitee 备胎），备胎：
  `gitee.com/mirrors/django` 已验证分支全。

### agent 侧口径（编码循环产补丁 → 官方 harness 判定）

严格按 SWE-bench 协议：**只把 problem_statement 喂给模型**（不含 gold
patch / test_patch），补丁由 `code-task.py` 宿主协议产出：

    # 1) 每实例：工作区（base_commit 检出）+ 任务文本 → 编码循环 → edits.patch
    #    宿主协议：CRA_LLM_PROVIDER=host → WAIT_HOST_LLM → 宿主填
    #    llm-tasks/*.response.md → --resume（收束后 --resume 幂等）
    # 2) 汇总补丁 → 官方 harness 评测（复用 gold-sample 驱动器）
    py skills/eval-harness/scripts/agent-sample.py \
      --patches datasets/swe-out/agent-sample --out datasets/swe-out/agent-sample/eval

- 同实例多版本用 `<iid>-vN` 目录保留历史补丁，驱动器按 mtime 取最新。
- **口径必须分档记录**：严格首跑（agent 只看 issue 文本）与按 harness 失败
  反馈迭代后的成绩是两件事，不得混为一谈（round-18：sympy-13437 的 bell
  limit 连返工三版才补齐非法入参语义——`bell(oo)`/负整数/非整数数值/无穷处
  多项式各自的语义都不在 issue 文本里）。
- 被审仓库若要求更老的 Python（如 sympy 1.1 需 ≤3.9），本机可用兼容垫片
  本地迭代，但**最终判定一律以 harness 容器为准**。

## 约定与纪律

- 首跑基线已建立（n=1，非代表性分数）；治理与工作流是差异化，
  分数用于校准。扩样按实例逐个：sparse checkout → Dockerfile.local
  → build → 评测。
- 每仓镜像数 GB，磁盘预算 ≥60GB。
- 新坑一律入 retro/pitfalls.json。
