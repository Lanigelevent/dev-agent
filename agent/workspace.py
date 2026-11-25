#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一工作区抽象（阶段四 4.3：本地 / 容器 / 远程三档同一接口）。

三档后端（同一套 prepare / run / read / write / diff / close 接口）：
  local              git worktree + 本机 subprocess（缺省，行为与旧版一致）
  container:<image>  git worktree 挂进持久容器的 /wt，命令走 docker exec
                     （编辑与测试共享同一份文件；差别只在执行环境）
  remote:<target>    远端 git worktree，命令与文件 IO 走 ssh（BatchMode）

设计约束：
- 工作区路径固定为 <out>/wt（与编码循环的历史布局一致），三档可互相替换；
- 所有命令都显式给超时；容器名由 <out> 哈希决定，--resume 能复用同一容器；
- 文件路径一律拒绝绝对路径与 `..` 越界（容器/远端写文件前最后一道网）；
- 远程档不假设远端有 python，解释器在 prepare 时探测并记录（python/python3）。

用法示例：
    py agent/workspace.py --backend local --repo <仓库> --out <目录> --run "python -V"
    py agent/workspace.py --backend container:cra-pytest:3.12 --repo <仓库> \
        --out <目录> --run "python -m pytest -q" --diff
    py agent/workspace.py --backend remote:user@host --repo /srv/repo \
        --out /tmp/task --describe

退出码：0=成功；1=动作失败（命令非零 / 补丁生成失败）；2=输入或环境错误。
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
from agent.edit_formats import apply_edits_io  # noqa: E402

WORKSPACE_DIRNAME = "wt"


class WorkspaceError(Exception):
    """工作区动作失败；code=1 动作失败，code=2 输入/环境错误。"""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def _safe_rel(rel):
    """相对路径校验：绝对路径 / 盘符 / `..` 一律拒绝（三档共用）。"""
    text = str(rel or "").replace("\\", "/").strip()
    if (not text or text.startswith("/") or text == ".."
            or ".." in text.split("/") or re.match(r"^[A-Za-z]:", text)):
        raise WorkspaceError("路径非法（须为工作区内相对路径）: %r" % rel, code=2)
    return text


def _base_env():
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class Workspace:
    """三档后端的共同骨架；子类只实现「在哪执行」与「怎么读写」。"""

    backend = "local"
    _IS_CONTAINER = False
    _IS_REMOTE = False

    def __init__(self, repo, out_dir, image="", target="", ssh_cmd=None):
        self.repo = Path(str(repo)).resolve()
        self.out_dir = Path(str(out_dir)).resolve()
        self.wt = self.out_dir / WORKSPACE_DIRNAME
        self.image = image
        self.target = target
        self.ssh_cmd = list(ssh_cmd or [])
        self.python = "python"
        self._prepared = False

    # ------------------------------------------------------------- 生命周期
    def prepare(self):
        """建立（或复用）工作区；幂等——--resume 时容器与 worktree 都还活着。"""
        if not self.repo.is_dir():
            raise WorkspaceError("仓库不存在: %s" % self.repo, code=2)
        if not self.wt.is_dir():
            rc, _out, err = self._git(["worktree", "add", "--detach",
                                       str(self.wt), "HEAD"], at_repo=True)
            if rc != 0:
                raise WorkspaceError("worktree 建立失败: %s" % err.strip()[:300])
        self._prepare_backend()
        self.python = self._detect_python()
        self._prepared = True
        return self.wt

    def _prepare_backend(self):
        """后端专属准备（容器启动 / 远端目录）。"""

    def _detect_python(self):
        return "python"

    def _require(self):
        if not self._prepared:
            raise WorkspaceError("工作区尚未 prepare()", code=2)

    def close(self):
        """清理后端资源与 worktree；重复调用安全。"""
        try:
            self._close_backend()
        finally:
            if self.wt.is_dir():
                self._git(["worktree", "remove", "--force", str(self.wt)],
                          at_repo=True)
            self._prepared = False

    def _close_backend(self):
        """后端专属清理（容器删除 / 远端 worktree 移除）。"""

    # ------------------------------------------------------------- 执行接口
    def run(self, cmd, timeout=600, input_text=None, cwd=""):
        """在工作区里执行命令 → (rc, stdout, stderr)；超时/环境错误转 WorkspaceError。"""
        self._require()
        raise NotImplementedError

    def run_in(self, base, cmd, timeout=600, input_text=None):
        """在指定后端绝对目录执行（工作区之外的基线目录用，如补丁前后对比）。"""
        self._require()
        raise NotImplementedError

    # 后端命名空间里的两个关键目录（补丁自检的「前后对比」依赖它们）
    @property
    def workspace_dir(self):
        return str(self.wt)

    @property
    def baseline_dir(self):
        return str(self.repo)

    def read_text(self, rel):
        self._require()
        raise NotImplementedError

    def write_text(self, rel, text):
        self._require()
        raise NotImplementedError

    def exists(self, rel):
        self._require()
        raise NotImplementedError

    def apply_blocks(self, blocks):
        """用 SEARCH/REPLACE 语义写工作区（远端档也走同一套唯一命中校验）。"""
        self._require()
        return apply_edits_io(blocks, self.read_text, self.exists,
                              self.write_text)

    def diff(self):
        """工作区相对 HEAD 的补丁 → (rc, patch, stderr)。

        先 `git add -A -N` 把未跟踪文件标记为 intent-to-add，否则新建文件
        不进补丁（round-46 实踩：新建文件缺失导致即时校验误报 file_missing）。
        """
        self._require()
        rc, _out, err = self._git(["add", "-A", "-N"], at_wt=True)
        if rc != 0:
            return rc, "", err
        rc, out, err = self._git(["diff", "HEAD"], at_wt=True)
        return rc, out, err

    def describe(self, probe=False):
        info = {"backend": self.backend, "workspace": str(self.wt),
                "repo": str(self.repo)}
        if self._IS_CONTAINER:
            info["image"] = self.image
        if self._IS_REMOTE:
            info["target"] = self.target
        if probe and self._prepared:
            info["python"] = self.python
            rc, out, err = self.run(
                [self.python, "-c",
                 "import sys,platform;print(sys.version.split()[0]);"
                 "print(platform.system())"], timeout=60)
            if rc == 0:
                lines = [l for l in out.strip().splitlines() if l]
                if lines:
                    info["python_version"] = lines[0]
                if len(lines) > 1:
                    info["platform"] = lines[1]
            else:
                info["probe_error"] = err.strip()[:200]
        return info

    # ------------------------------------------------------------- 子类钩子
    def _git(self, args, at_repo=False, at_wt=False):
        """git 命令；local/container 走宿主 git（容器共享挂载，不必装 git）。"""
        base = self.repo if at_repo else self.wt
        proc = subprocess.run(["git", "-C", str(base)] + list(args),
                              shell=False, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
        return proc.returncode, proc.stdout or "", proc.stderr or ""

    def _subprocess(self, argv, timeout, input_text=None, cwd=None):
        try:
            proc = subprocess.run(
                argv, shell=False, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
                cwd=cwd, env=_base_env(), input=input_text)
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError("命令超时（%ss）: %s" % (timeout, exc))
        except OSError as exc:
            raise WorkspaceError("命令无法执行: %s" % exc, code=2)
        return proc.returncode, proc.stdout or "", proc.stderr or ""


class LocalWorkspace(Workspace):
    """本机 worktree：与 round-59 及以前的编码循环行为逐字一致。"""

    backend = "local"

    def _detect_python(self):
        # 本地档必须用启动本进程的解释器（.venv），不能靠 PATH 上的 python
        # ——Windows 上裸 python 可能是别的基础解释器，没有 pytest。
        return sys.executable or "python"

    def run(self, cmd, timeout=600, input_text=None, cwd=""):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        base = str(self.wt / cwd) if cwd else str(self.wt)
        return self._subprocess(argv, timeout, input_text=input_text, cwd=base)

    def run_in(self, base, cmd, timeout=600, input_text=None):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        return self._subprocess(argv, timeout, input_text=input_text,
                                cwd=str(base))

    def read_text(self, rel):
        self._require()
        return (self.wt / _safe_rel(rel)).read_text(encoding="utf-8",
                                                    errors="replace")

    def write_text(self, rel, text):
        self._require()
        target = self.wt / _safe_rel(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def exists(self, rel):
        self._require()
        return (self.wt / _safe_rel(rel)).is_file()


class ContainerWorkspace(Workspace):
    """容器档：同一 worktree 挂到 /wt，命令走 docker exec。

    容器只提供执行环境（测试/探针/自检），文件仍是同一份挂载——于是
    「同一任务两档跑出的补丁一致」是验收判据：不一致只可能来自后端 bug。
    """

    backend = "container"
    _IS_CONTAINER = True

    def __init__(self, repo, out_dir, image, ssh_cmd=None):
        super().__init__(repo, out_dir, image=image, ssh_cmd=ssh_cmd)
        if not image:
            raise WorkspaceError("container 档必须给镜像名", code=2)
        digest = hashlib.sha1(str(self.out_dir).encode("utf-8")).hexdigest()[:12]
        self.name = "cra-ws-%s" % digest

    def _docker(self, args, timeout=120, input_text=None):
        return self._subprocess(["docker"] + list(args), timeout,
                                input_text=input_text)

    def _container_running(self):
        rc, out, _err = self._docker(
            ["inspect", "-f", "{{.State.Running}}", self.name], timeout=30)
        return rc == 0 and out.strip() == "true"

    def _prepare_backend(self):
        if self._container_running():
            return
        # 先清理同名残留（上次异常退出留下的），再起持久容器；
        # tail -f /dev/null 在 slim/busybox/ubuntu 上都可用。
        self._docker(["rm", "-f", self.name], timeout=60)
        rc, _out, err = self._docker(
            ["run", "-d", "--rm", "--name", self.name,
             "-v", "%s:/wt" % self.wt,
             "-v", "%s:/repo:ro" % self.repo, "-w", "/wt",
             "-e", "PYTHONDONTWRITEBYTECODE=1",
             self.image, "tail", "-f", "/dev/null"], timeout=180)
        if rc != 0:
            raise WorkspaceError("容器启动失败: %s" % err.strip()[:300], code=2)
        rc, _out, err = self._docker(["exec", self.name, "true"], timeout=60)
        if rc != 0:
            self._close_backend()
            raise WorkspaceError("容器不可执行: %s" % err.strip()[:300], code=2)

    def _detect_python(self):
        for cand in ("python", "python3"):
            rc, _out, _err = self._docker(
                ["exec", self.name, "sh", "-c", "command -v %s" % cand],
                timeout=30)
            if rc == 0:
                return cand
        return "python"

    def _close_backend(self):
        name = getattr(self, "name", "")
        if name:
            self._docker(["rm", "-f", name], timeout=60)

    def run(self, cmd, timeout=600, input_text=None, cwd=""):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        workdir = "/wt" + ("/" + cwd.strip("/") if cwd else "")
        args = ["exec", "-i"]
        if workdir != "/wt":
            args += ["-w", workdir]
        args += [self.name, "sh", "-c", shlex.join(argv)]
        return self._docker(args, timeout, input_text=input_text)

    def run_in(self, base, cmd, timeout=600, input_text=None):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        args = ["exec", "-i", "-w", str(base), self.name, "sh", "-c",
                shlex.join(argv)]
        return self._docker(args, timeout, input_text=input_text)

    @property
    def workspace_dir(self):
        return "/wt"

    @property
    def baseline_dir(self):
        return "/repo"

    def _path(self, rel):
        return "/wt/" + _safe_rel(rel)

    def read_text(self, rel):
        self._require()
        rc, out, err = self._docker(["exec", self.name, "cat", self._path(rel)],
                                    timeout=120)
        if rc != 0:
            raise WorkspaceError("读取失败 %s: %s" % (rel, err.strip()[:200]))
        return out

    def write_text(self, rel, text):
        self._require()
        target = self._path(rel)
        parent = target.rsplit("/", 1)[0]
        script = "mkdir -p %s && cat > %s" % (shlex.quote(parent),
                                              shlex.quote(target))
        rc, _out, err = self._docker(
            ["exec", "-i", self.name, "sh", "-c", script], timeout=120,
            input_text=text)
        if rc != 0:
            raise WorkspaceError("写入失败 %s: %s" % (rel, err.strip()[:200]))

    def exists(self, rel):
        self._require()
        rc, _out, _err = self._docker(
            ["exec", self.name, "test", "-f", self._path(rel)], timeout=60)
        return rc == 0


class RemoteWorkspace(Workspace):
    """远程档：远端 git worktree，命令与文件 IO 走 ssh（BatchMode，无交互）。

    本档没有真实远端环境时由契约测试用「本地 ssh 假壳」验证接线；报告里
    不得把它冒充成真机实跑。
    """

    backend = "remote"
    _IS_REMOTE = True

    def __init__(self, repo, out_dir, target, ssh_cmd=None):
        if not target:
            raise WorkspaceError("remote 档必须给 ssh 目标", code=2)
        host = target.split(":", 1)[0]
        super().__init__(repo, out_dir, image="", target=target,
                         ssh_cmd=ssh_cmd or [
                             "ssh", "-o", "BatchMode=yes", "-o",
                             "ConnectTimeout=15", host])
        self.remote_repo = str(repo).replace("\\", "/")
        self.remote_out = str(out_dir).replace("\\", "/")
        self.remote_wt = self.remote_out + "/" + WORKSPACE_DIRNAME

    def _ssh(self, script, timeout=600, input_text=None):
        argv = self.ssh_cmd + [script]
        return self._subprocess(argv, timeout, input_text=input_text)

    def _prepare_backend(self):
        # 幂等：--resume 时远端 worktree 已存在，不能再 add 一次
        script = ("if [ ! -d %s ]; then mkdir -p %s && "
                  "git -C %s worktree add --detach %s HEAD; fi"
                  % (shlex.quote(self.remote_wt),
                     shlex.quote(self.remote_out),
                     shlex.quote(self.remote_repo),
                     shlex.quote(self.remote_wt)))
        rc, _out, err = self._ssh(script, timeout=180)
        if rc != 0:
            raise WorkspaceError("远端 worktree 建立失败: %s"
                                 % err.strip()[:300], code=2)

    def _detect_python(self):
        rc, out, _err = self._ssh(
            "command -v python || command -v python3 || true", timeout=60)
        return (out.strip().splitlines() or ["python"])[0] if rc == 0 \
            else "python"

    def _close_backend(self):
        script = "git -C %s worktree remove --force %s" % (
            shlex.quote(self.remote_repo), shlex.quote(self.remote_wt))
        self._ssh(script, timeout=120)

    def run(self, cmd, timeout=600, input_text=None, cwd=""):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        workdir = self.remote_wt + ("/" + cwd.strip("/") if cwd else "")
        script = "cd %s && %s" % (shlex.quote(workdir), shlex.join(argv))
        return self._ssh(script, timeout, input_text=input_text)

    def run_in(self, base, cmd, timeout=600, input_text=None):
        self._require()
        argv = list(cmd) if isinstance(cmd, (list, tuple)) \
            else shlex.split(str(cmd), posix=True)
        script = "cd %s && %s" % (shlex.quote(str(base)), shlex.join(argv))
        return self._ssh(script, timeout, input_text=input_text)

    @property
    def workspace_dir(self):
        return self.remote_wt

    @property
    def baseline_dir(self):
        return self.remote_repo

    def _path(self, rel):
        return self.remote_wt + "/" + _safe_rel(rel)

    def read_text(self, rel):
        self._require()
        rc, out, err = self._ssh("cat %s" % shlex.quote(self._path(rel)),
                                 timeout=120)
        if rc != 0:
            raise WorkspaceError("读取失败 %s: %s" % (rel, err.strip()[:200]))
        return out

    def write_text(self, rel, text):
        self._require()
        target = self._path(rel)
        parent = target.rsplit("/", 1)[0]
        script = "mkdir -p %s && cat > %s" % (shlex.quote(parent),
                                              shlex.quote(target))
        rc, _out, err = self._ssh(script, timeout=120, input_text=text)
        if rc != 0:
            raise WorkspaceError("写入失败 %s: %s" % (rel, err.strip()[:200]))

    def exists(self, rel):
        self._require()
        rc, _out, _err = self._ssh(
            "test -f %s" % shlex.quote(self._path(rel)), timeout=60)
        return rc == 0

    def _git(self, args, at_repo=False, at_wt=False):
        base = self.remote_repo if at_repo else self.remote_wt
        script = "git -C %s %s" % (shlex.quote(base), shlex.join(args))
        rc, out, err = self._ssh(script, timeout=120)
        return rc, out, err


def open_workspace(spec, repo, out_dir, ssh_cmd=None):
    """后端规格 → Workspace 实例。

    规格："" / "local" → 本地；"container:<image>" → 容器；
    "remote:<target>" → 远端（target 里的冒号留给 ssh，例如 host:port）。
    未知规格抛 WorkspaceError(code=2)，不静默退回 local。
    """
    text = str(spec or "").strip()
    if not text or text == "local":
        return LocalWorkspace(repo, out_dir)
    if text.startswith("container:"):
        image = text.split(":", 1)[1].strip()
        return ContainerWorkspace(repo, out_dir, image, ssh_cmd=ssh_cmd)
    if text.startswith("remote:"):
        target = text.split(":", 1)[1].strip()
        return RemoteWorkspace(repo, out_dir, target, ssh_cmd=ssh_cmd)
    raise WorkspaceError("未知工作区规格: %r（local / container:<image> / "
                         "remote:<target>）" % spec, code=2)


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="统一工作区抽象（三档）")
    parser.add_argument("--backend", default="local")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run", default="", help="在工作区里执行的命令")
    parser.add_argument("--read", default="", help="读工作区内相对路径")
    parser.add_argument("--write", default="", help="写工作区内相对路径")
    parser.add_argument("--content", default="")
    parser.add_argument("--content-file", default="",
                        help="写入内容从文件读（避免 shell 转义与换行问题）")
    parser.add_argument("--diff", action="store_true")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--keep", action="store_true", help="不自动 close")
    parser.add_argument("--ssh-cmd", default="",
                        help="remote 档的 ssh 命令前缀（测试用假壳）")
    argv = parser.parse_args()
    ssh_cmd = shlex.split(argv.ssh_cmd, posix=True) if argv.ssh_cmd else None
    try:
        ws = open_workspace(argv.backend, argv.repo, argv.out, ssh_cmd=ssh_cmd)
        ws.prepare()
    except WorkspaceError as exc:
        _emit({"ok": False, "error": str(exc), "backend": argv.backend})
        return exc.code
    result = {"ok": True, "workspace": ws.describe(probe=True)}
    try:
        if argv.run:
            rc, out, err = ws.run(argv.run, timeout=600)
            result["run"] = {"rc": rc, "stdout": out[-8000:],
                             "stderr": err[-8000:]}
            if rc != 0:
                result["ok"] = False
        if argv.read:
            result["read"] = ws.read_text(argv.read)
        if argv.write:
            if argv.content_file:
                content = Path(argv.content_file).read_text(encoding="utf-8")
            else:
                content = argv.content
            ws.write_text(argv.write, content)
            result["written"] = argv.write
        if argv.diff:
            rc, patch, err = ws.diff()
            result["diff"] = {"rc": rc, "patch": patch, "stderr": err}
            if rc != 0:
                result["ok"] = False
    except WorkspaceError as exc:
        result["ok"] = False
        result["error"] = str(exc)
    finally:
        if argv.close or not argv.keep:
            try:
                ws.close()
            except WorkspaceError as exc:
                result["close_error"] = str(exc)
    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
