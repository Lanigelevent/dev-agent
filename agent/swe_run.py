#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SWE-bench 单实例评测编排（Phase 3B 扩样；恢复 v1.20.0 降级的脚本形态）。

把 agent/swe-workflow.md 的已验证命令序列代码化为四个阶段；镜像获取纪律与
CRLF 坑的机器自检内建。纯标准库，路径参数全部显式可指定。

用途:
    prepare  获取任务目录（sparse clone 或复用 --task-dir）并把官方 Dockerfile
             的 BuildKit heredoc 块逐字抽成 setupN.sh + COPY/RUN bash（import
             基镜像不支持 heredoc），按实测规则定向国内源（apt/miniconda→NJU，
             conda 渠道/pip→TUNA，版本 pin 不变），生成 Dockerfile.local。
    build    docker build -f Dockerfile.local -t <image>（镜像 tag 用数据集
             image 列派生名，如 swebench/sweb.eval.x86_64.django_1776_django-14999）。
    eval     门控自检（docker/swebench/CRLF 补丁/predictions 字段）后运行官方
             harness：HF_ENDPOINT=hf-mirror python -m swebench.harness.run_evaluation。
    report   解析 logs/run_evaluation/<run_id>/<model>/report.json 出 resolved 判定。

用法示例:
    py swe_run.py prepare --task django__django-14999 --out datasets/swe-out \
        [--tasks-repo <git url>] [--task-dir <已检出目录>] [--no-rewrite]
    py swe_run.py build --task-dir <dir> --image <tag> [--dry-run]
    py swe_run.py eval --predictions <jsonl> --run-id <id> \
        [--venv-python .venv/Scripts/python.exe] [--cwd .] [--timeout 3600] [--dry-run]
    py swe_run.py report --run-id <id> [--logs-root logs/run_evaluation] [--model <name>]

退出码:
    0 = 成功
    1 = 可处理问题（docker 缺席 / swebench 缺失 / CRLF 补丁缺失 / harness 失败）
    2 = 参数或输入文件错误（任务 id 非法 / 文件不存在 / predictions 缺字段）

docker 发现顺序：--docker 显式 > PATH（shutil.which）> 用户目录安装
%LOCALAPPDATA%/Programs/DockerDesktop/resources/bin/docker.exe（安装器更新
PATH 后旧进程环境取不到，属实测场景）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DATASET = "SWE-bench/SWE-bench_Lite"
# 官方任务仓库（Dockerfile 源）。国内镜像注意：gitee.com/mirrors/ 不收
# SWE-bench-tasks（v1.22.0 实测 401），github 直连/容器/常见代理均时通时断；
# 不可达时改走预构建镜像路线（docker pull 经 docker.1ms.run 代理，见
# agent/swe-workflow.md「镜像获取路径」）。
DEFAULT_TASKS_REPO = "https://github.com/SWE-bench/swe-bench-tasks.git"
TASK_ID_RE = re.compile(r"[A-Za-z0-9_.-]+")
# 国内源改写（agent/swe-workflow.md 实测定型；只换下载源，版本 pin 不变）
MINICONDA_URL = ("https://repo.anaconda.com/miniconda/",
                 "https://mirror.nju.edu.cn/anaconda/miniconda/")
APT_SED = ("RUN sed -i 's|//archive.ubuntu.com|//mirror.nju.edu.cn|g; "
           "s|//security.ubuntu.com|//mirror.nju.edu.cn|g' /etc/apt/sources.list")
CONDARC_BLOCK = (
    "# conda/pip 走 TUNA 镜像（版本 pin 不变，只换源）\n"
    "RUN printf 'channels:\\n  - defaults\\n  - conda-forge\\n"
    "show_channel_urls: true\\ndefault_channels:\\n  - "
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main\\n"
    "custom_channels:\\n  conda-forge: "
    "https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\\n' > /root/.condarc\n"
    "ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _fail(state, error, **extra):
    _emit(dict({"ok": False, "state": state, "error": error}, **extra))
    return 1


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def _run(cmd, **kw):
    p = subprocess.run(cmd, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **kw)
    return p.returncode, p.stdout, p.stderr


def find_docker(explicit=""):
    """docker 可执行文件发现：显式 > PATH > 用户目录安装。返回路径或 None。"""
    if explicit:
        return explicit if Path(explicit).is_file() else None
    found = shutil.which("docker")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidate = Path(local) / "Programs/DockerDesktop/resources/bin/docker.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def extract_heredocs(dockerfile_text):
    """把 BuildKit heredoc RUN 块逐字抽成 (setupN 内容, 替换段) 列表。

    官方形态：RUN <<MARKER ... 直到单独一行 MARKER。块体已含 #!/bin/bash
    则原样保留，否则补 shebang 与 set 行。解析失败返回 (None, 错误)。
    """
    blocks = []
    lines = dockerfile_text.splitlines()
    out, i, n = [], 0, len(lines)
    seq = 0
    while i < n:
        m = re.match(r"^\s*RUN\s+<<(\S+)\s*$", lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        marker, body = m.group(1), []
        i += 1
        while i < n and lines[i].strip() != marker:
            body.append(lines[i])
            i += 1
        if i >= n:
            return None, "heredoc %s 未找到结束标记" % marker
        i += 1  # 跳过结束标记行
        seq += 1
        name = "setup%d.sh" % seq
        text = "\n".join(body).rstrip("\n")
        if not text.startswith("#!"):
            text = "#!/bin/bash\nset -euxo pipefail\n" + text
        blocks.append({"name": name, "body": text + "\n"})
        out.append("COPY %s /tmp/%s" % (name, name))
        out.append('RUN ["/bin/bash", "/tmp/%s"]' % name)
    return blocks, "\n".join(out) + ("\n" if out else "")


def rewrite_local(dockerfile_text):
    """对抽取后的 Dockerfile 文本做国内源改写，返回 (新文本, 改写计数 dict)。"""
    counts = {}
    text, c = re.subn(re.escape(MINICONDA_URL[0]), MINICONDA_URL[1],
                      dockerfile_text)
    counts["miniconda_url_to_nju"] = c
    lines = text.splitlines(keepends=True)
    # apt 源 sed 置顶：插在首个 RUN apt 行前
    for idx, line in enumerate(lines):
        if line.startswith("RUN apt"):
            lines.insert(idx, APT_SED + "\n")
            counts["apt_sources_sed_inserted"] = 1
            break
    text = "".join(lines)
    lines = text.splitlines(keepends=True)
    # .condarc + PIP：插在首个 COPY setupN.sh 段前（若无 COPY 则追加）
    for idx, line in enumerate(lines):
        if line.startswith("COPY setup"):
            lines.insert(idx, CONDARC_BLOCK + "\n")
            counts["condarc_pip_inserted"] = 1
            break
    else:
        lines.append("\n" + CONDARC_BLOCK)
        counts["condarc_pip_inserted"] = 1
    return "".join(lines), counts


def cmd_prepare(argv):
    if not TASK_ID_RE.fullmatch(argv.task or ""):
        return _param_error("任务 id 非法（只允许字母数字._-）: %r" % argv.task)
    out_root = Path(argv.out)
    if argv.task_dir:
        task_dir = Path(argv.task_dir)
        if not task_dir.is_dir():
            return _param_error("--task-dir 不存在: %s" % task_dir)
        cloned = False
    else:
        repo_dir = out_root / "swe-tasks" / "repo"
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        if not (repo_dir / ".git").is_dir():
            rc, _, err = _run(["git", "clone", "--depth", "1",
                               "--filter=blob:none", "--sparse",
                               argv.tasks_repo, str(repo_dir)])
            if rc != 0:
                return _fail("CLONE_FAILED", err.strip()[:400])
        rc, _, err = _run(["git", "-C", str(repo_dir), "sparse-checkout",
                           "set", "tasks/%s" % argv.task])
        if rc != 0:
            return _fail("SPARSE_CHECKOUT_FAILED", err.strip()[:400])
        task_dir = repo_dir / "tasks" / argv.task
        if not task_dir.is_dir():
            return _fail("TASK_NOT_FOUND",
                         "sparse checkout 后任务目录不存在: %s" % task_dir)
    official = task_dir / "Dockerfile"
    if not official.is_file():
        return _param_error("任务目录缺少官方 Dockerfile: %s" % official)
    blocks, transformed = extract_heredocs(
        official.read_text(encoding="utf-8"))
    if blocks is None:
        return _fail("HEREDOC_PARSE_FAILED", transformed)
    if not blocks:
        return _fail("NO_HEREDOC",
                     "官方 Dockerfile 无 heredoc 块，无需本地变体")
    if argv.rewrite:
        local_text, counts = rewrite_local(transformed)
    else:
        local_text, counts = transformed, {}
    header = ("# Local variant of the official task Dockerfile for %s.\n"
              "# 变换：heredoc→setupN.sh + COPY/RUN bash（import 基镜像不支持\n"
              "# heredoc）；国内源改写=%s。\n" % (argv.task, bool(argv.rewrite)))
    (task_dir / "Dockerfile.local").write_text(
        header + local_text, encoding="utf-8", newline="\n")
    for b in blocks:
        (task_dir / b["name"]).write_text(b["body"], encoding="utf-8",
                                          newline="\n")
    _emit({"ok": True, "phase": "prepare", "task": argv.task,
           "task_dir": str(task_dir), "cloned": cloned,
           "setup_scripts": [b["name"] for b in blocks],
           "dockerfile_local": str(task_dir / "Dockerfile.local"),
           "rewrites": counts})
    return 0


def cmd_build(argv):
    task_dir = Path(argv.task_dir)
    if not (task_dir / "Dockerfile.local").is_file():
        return _param_error("--task-dir 缺 Dockerfile.local（先跑 prepare）: %s"
                            % task_dir)
    cmd = ["docker", "build", "-f", "Dockerfile.local",
           "--progress=plain", "-t", argv.image, "."]
    if argv.dry_run:
        _emit({"ok": True, "phase": "build", "dry_run": True, "cmd": cmd,
               "cwd": str(task_dir)})
        return 0
    docker = find_docker(argv.docker_bin)
    if not docker:
        return _fail("DOCKER_UNAVAILABLE",
                     "docker 不可执行（--docker 显式指定或安装 Docker Desktop）")
    cmd[0] = docker
    rc, out, err = _run(cmd, cwd=str(task_dir), timeout=argv.timeout)
    if rc != 0:
        return _fail("BUILD_FAILED", (err or out).strip()[-800:])
    _emit({"ok": True, "phase": "build", "image": argv.image,
           "task_dir": str(task_dir)})
    return 0


def _check_crlf_patch(venv_python):
    """BASELINE 契约：swebench 重装/升级后 newline 补丁必须重打。

    通过返回 (None, None)；否则 (state, error)。
    """
    rc, out, err = _run([str(venv_python), "-c",
                         "import swebench, os; print(os.path.dirname("
                         "swebench.__file__))"])
    if rc != 0:
        return "SWEBENCH_MISSING", err.strip()[:300]
    pkg = Path(out.strip())
    src = pkg / "harness" / "run_evaluation.py"
    if not src.is_file():
        return "SWEBENCH_MISSING", "未找到 %s" % src
    text = src.read_text(encoding="utf-8")
    if text.count('newline="\\n"') < 2:
        return "CRLF_PATCH_MISSING", (
            "%s 缺 newline 补丁（重装/升级后须重打，见 BASELINE「SWE-bench 契约」"
            "与 agent/swe-workflow.md）" % src)
    return None, None


def cmd_eval(argv):
    pred = Path(argv.predictions)
    if not pred.is_file():
        return _param_error("--predictions 不存在: %s" % pred)
    ids = []
    with pred.open(encoding="utf-8") as fh:
        for no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                return _param_error("predictions 第 %d 行非 JSON" % no)
            for key in ("instance_id", "model_name_or_path"):
                if key not in row:
                    return _param_error(
                        "predictions 第 %d 行缺 %s 字段（数据集契约）" % (no, key))
            ids.append(row["instance_id"])
    venv_python = Path(argv.venv_python)
    if not venv_python.is_file():
        return _param_error("--venv-python 不存在: %s" % venv_python)
    cmd = [str(venv_python), "-m", "swebench.harness.run_evaluation",
           "--dataset_name", argv.dataset, "--predictions_path", str(pred),
           "--run_id", argv.run_id, "--max_workers", "1"]
    env = dict(os.environ)
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    if argv.dry_run:
        _emit({"ok": True, "phase": "eval", "dry_run": True, "cmd": cmd,
               "env": {"HF_ENDPOINT": env["HF_ENDPOINT"]},
               "instances": ids})
        return 0
    docker = find_docker(argv.docker_bin)
    if not docker:
        return _fail("DOCKER_UNAVAILABLE", "docker 不可执行")
    gate_state, gate_err = _check_crlf_patch(venv_python)
    if gate_state:
        return _fail(gate_state, gate_err)
    rc, out, err = _run(cmd, cwd=argv.cwd, timeout=argv.timeout, env=env)
    log_path = Path(argv.cwd) / ("harness-run-%s.log" % argv.run_id)
    log_path.write_text((out or "") + (err or ""), encoding="utf-8",
                        newline="\n")
    if rc != 0:
        return _fail("HARNESS_FAILED", (err or out).strip()[-800:],
                     log=str(log_path))
    _emit({"ok": True, "phase": "eval", "run_id": argv.run_id,
           "dataset": argv.dataset, "instances": ids, "log": str(log_path),
           "next": "report --run-id %s" % argv.run_id})
    return 0


def diagnose(inst):
    """给单个实例的评测结果做失败归因（可执行结论，不只是计数）。

    归因口径：
      PATCH_APPLY_FAILED —— 补丁没应用上（格式/路径不合法）
      PATCH_BROKE_MODULE  —— 补丁破坏了被改模块（导入期就炸：ImportError/
                            SyntaxError/模块级异常）
      REGRESSION         —— F2P 未过且 P2P 也有失败（补丁破坏了既有行为）
      F2P_MISSED         —— F2P 未过但 P2P 全过（补丁语义没修对）
      RESOLVED           —— 全过
    """
    if not inst.get("patch_successfully_applied", True):
        return "PATCH_APPLY_FAILED"
    f2p_fail = inst.get("fail_to_pass", {}).get("fail", 0)
    p2p_fail = inst.get("pass_to_pass", {}).get("fail", 0)
    if not f2p_fail and not p2p_fail:
        return "RESOLVED"
    detail = str(inst.get("error") or "")
    if any(marker in detail for marker in
           ("ImportError", "ModuleNotFoundError", "SyntaxError",
            "IndentationError", "AttributeError")):
        return "PATCH_BROKE_MODULE"
    if p2p_fail:
        return "REGRESSION"
    return "F2P_MISSED"


def cmd_report(argv):
    run_root = Path(argv.logs_root) / argv.run_id
    if not run_root.is_dir():
        return _param_error("run 目录不存在: %s" % run_root)
    models = [d.name for d in run_root.iterdir() if d.is_dir()]
    if argv.model:
        model = argv.model
    elif len(models) == 1:
        model = models[0]
    else:
        return _param_error("无法唯一定位 model 目录（%s），用 --model 指定"
                            % (", ".join(models) or "无"))
    model_root = run_root / model
    report_paths = sorted(model_root.glob("*/report.json"))
    if not report_paths:
        return _param_error("未找到实例级 report.json（%s/<id>/report.json）"
                            % model_root)
    instances = []
    for path in report_paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for inst_id, r in sorted(data.items()):
            ts = r.get("tests_status", {})
            f2p = ts.get("FAIL_TO_PASS", {})
            p2p = ts.get("PASS_TO_PASS", {})
            instances.append({
                "instance_id": inst_id,
                "resolved": bool(r.get("resolved")),
                "patch_successfully_applied": bool(
                    r.get("patch_successfully_applied")),
                "infra_failure": bool(r.get("infra_failure")),
                "fail_to_pass": {"pass": len(f2p.get("success", [])),
                                 "fail": len(f2p.get("failure", []))},
                "pass_to_pass": {"pass": len(p2p.get("success", [])),
                                 "fail": len(p2p.get("failure", []))},
                "error": str(r.get("error") or "")[-400:]})
    for inst in instances:
        inst["diagnosis"] = diagnose(inst)
    _emit({"ok": True, "phase": "report", "run_id": argv.run_id,
           "model": model, "resolved_count": sum(
               i["resolved"] for i in instances),
           "total": len(instances), "instances": instances})
    return 0


def main():
    parser = argparse.ArgumentParser(description="SWE-bench 单实例评测编排")
    sub = parser.add_subparsers(dest="phase", required=True)

    p = sub.add_parser("prepare", help="获取任务并生成 Dockerfile.local")
    p.add_argument("--task", help="任务 id，如 django__django-14999")
    p.add_argument("--out", default="datasets/swe-out", help="工作根目录")
    p.add_argument("--tasks-repo", default=DEFAULT_TASKS_REPO,
                   help="swe-bench-tasks 仓库（缺省 Gitee 镜像）")
    p.add_argument("--task-dir", help="复用已检出任务目录（跳过 clone）")
    p.add_argument("--no-rewrite", dest="rewrite", action="store_false",
                   help="关闭国内源改写")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("build", help="构建任务镜像")
    p.add_argument("--task-dir", required=True, help="含 Dockerfile.local 的目录")
    p.add_argument("--image", required=True, help="镜像 tag（数据集 image 列派生）")
    p.add_argument("--docker", dest="docker_bin", default="",
                   help="docker 可执行文件路径（缺省自动发现）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("eval", help="官方 harness 评测")
    p.add_argument("--predictions", required=True, help="predictions.jsonl")
    p.add_argument("--run-id", required=True)
    p.add_argument("--dataset", default=DEFAULT_DATASET,
                   help="必须为 2.0 格式数据集（带 image/eval_script 列）")
    p.add_argument("--venv-python",
                   default=".venv/Scripts/python.exe" if os.name == "nt"
                   else ".venv/bin/python")
    p.add_argument("--cwd", default=".", help="harness 工作目录（logs 落此）")
    p.add_argument("--docker", dest="docker_bin", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("report", help="解析评测报告")
    p.add_argument("--run-id", required=True)
    p.add_argument("--logs-root", default="logs/run_evaluation")
    p.add_argument("--model", help="model 目录名（缺省唯一定位）")
    p.set_defaults(func=cmd_report)

    argv = parser.parse_args()
    return argv.func(argv)


if __name__ == "__main__":
    sys.exit(main())
