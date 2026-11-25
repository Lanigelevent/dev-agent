"""tests/tmpspace.py — 临时快照的自建自删生命周期（round-30 检查单第 12 项）。

本机 `%TEMP%` 下留了上千个 `cra-tests-*`（最大单个 14 万+ 文件），全是被中断的
评测/测试跑次留下的仓库快照。形状是：**创建方在跑次开始时建目录，只有跑次
正常收尾时才删**——Ctrl-C、崩溃、超时、机器重启，任何一种中断都把目录永久留下，
而没有任何一条路径会回头认领它。

本模块把「建」和「删」绑成一件事：

1. `create(prefix)` 建目录时在目录内落一个归属标记 `.cra-tmp-owner.json`
   （pid / created / run / cwd），并登记 `atexit` 删除；
2. `release(path)` 删除，带 Windows 只读文件处理（git 对象是只读的，
   普通 rmtree 会静默失败——这正是 `ignore_errors=True` 长期掩盖的东西）；
3. `sweep(...)` 回收**带我们自己标记**的陈旧目录：只认标记、只认超过年龄阈值的。

为什么用年龄而不是查活进程：Windows 上 `os.kill(pid, 0)` 不是「探活」——CPython
在没有信号语义的平台上会走 `TerminateProcess`，拿它探活等于把并发跑次杀掉。
年龄阈值（默认 2 小时）对一次全量约 4 分钟的套件足够安全：还在跑的跑次不可能
创建两小时前的目录，因而不会被误删。

标记之外的目录**一律不碰**：本机那上千个历史遗留目录没有标记，删不删是运维决定，
不由这里替用户做主（`scripts/sweep-test-tmp.py` 提供先列后删的口径）。
"""

import atexit
import json
import os
import shutil
import stat
import sys
import time
import uuid
from pathlib import Path

MARKER = ".cra-tmp-owner.json"
RUN_ID = "%s-%s" % (int(time.time()), uuid.uuid4().hex[:8])
DEFAULT_STALE_SECONDS = 2 * 60 * 60

# 测试夹具自己用的前缀。回收缺省只在这份清单里找，不是「有标记就够了」：
# 临时根上有 2.6 万个目录，全根扫归属标记要 stat 两六万次，套件一启动就付这个钱；
# 前缀清单可能漏（新夹具忘了登记），漏的后果只是「这一类暂时不自动回收」，
# 报表里仍然看得见（scripts/sweep-test-tmp.py 的 unmarked.by_prefix）。
KNOWN_PREFIXES = ("cra-tests-", "repo-map-", "edit-fmt-", "code-task-",
                  "patch-gate-", "probe-", "repair-", "ruff-", "libcst-",
                  "artifact-naming-", "cve-corpus-", "dump-scan-", "gold-",
                  "mcp-", "taint-", "real-corpus-", "testgen-", "pynguin-",
                  "tmpspace-case-")

_created = set()
_swept_roots = set()


def _marker_payload():
    return {"pid": os.getpid(), "run": RUN_ID,
            "created": time.time(), "cwd": os.getcwd()}


def _rmtree(path):
    """删目录树，带只读位清理与重试（Windows 上 git 对象是只读的）。

    返回 True=确实删掉了；False=仍在。静默失败是这个模块要根治的东西，
    所以这里不吞错误，而是把结果如实报出来。
    """
    path = Path(path)
    if not path.exists():
        return True

    def _clear(func, target, exc):
        """只读位挡路时清掉再试一次；仍然失败就如实留下（不吞成「已删除」）。

        写进 stderr 而不是 raise：onerror 里抛会把整个 rmtree 打断，
        而「删不掉」要由返回值告诉调用方，由调用方决定报警。
        """
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError as retry_exc:
            sys.stderr.write("tmpspace: 删不掉 %s (%s)\n" % (target, retry_exc))

    for attempt in range(3):
        try:
            shutil.rmtree(path, onerror=_clear)
        except OSError:
            time.sleep(0.2)
            continue
        if not path.exists():
            return True
    return not path.exists()


def release(path):
    """删除 create() 出来的目录；幂等，返回 (removed: bool, path: str)。"""
    path = Path(path)
    _created.discard(str(path))
    ok = _rmtree(path)
    return ok, str(path)


def create(prefix="cra-tests-", root=None):
    """建一个带归属标记的临时目录，跑次结束时（含异常与 Ctrl-C）自动删除。

    root 用于把测试夹具固定在同一父目录下；缺省走系统临时目录。
    """
    tmp = Path(root) if root else Path(temp_dir())
    path = tmp / ("%s%s" % (prefix, uuid.uuid4().hex[:8]))
    path.mkdir(parents=True, exist_ok=True)
    (path / MARKER).write_text(json.dumps(_marker_payload(), ensure_ascii=False),
                               encoding="utf-8", newline="\n")
    _created.add(str(path))
    atexit.register(release, path)
    return path


def temp_dir():
    """跑测试用的临时根：只认**真的存在**的目录。

    Git Bash 会把 TMP/TMPDIR 指成 `/tmp`（msys 视角），而这里的解释器是 Windows
    python——`/tmp` 对它不是那个目录。所以候选逐个验存在性，第一个真实可用的才算。
    """
    candidates = []
    for key in ("TEMP", "TMP", "TMPDIR"):
        value = os.environ.get(key)
        if value:
            candidates.append(Path(value))
    candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Temp")
    candidates.append(Path("/tmp"))
    for cand in candidates:
        try:
            if str(cand) and cand.is_dir():
                return cand
        except OSError:
            continue
    return Path(os.getcwd())


def owner_of(path):
    """读归属标记；没有标记（不是本模块建的）返回 None。"""
    marker = Path(path) / MARKER
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "created" in data else None


def sweep(root=None, prefixes=None, older_than_seconds=DEFAULT_STALE_SECONDS,
          apply=True, now=None, report_limit=200, once_per_process=False):
    """回收**带本模块标记**且已超过年龄阈值的临时目录。

    三条硬规矩（都是反向验证钉住的）：
    - 只碰 `prefixes` 前缀匹配的目录（缺省 = KNOWN_PREFIXES，见上面注释）；
    - 只认归属标记——没标记的一律计入 `skipped_unmarked_total`，交人工决定；
    - 只认年龄超过阈值的——还在跑的并发跑次不能被杀掉。

    `once_per_process=True` 时同一个根只扫一次：套件里 14 个模块都调
    test_scripts.setUpModule，每次扫一边临时根就是 14 次白扫。
    清单各桶只留前 `report_limit` 条名字，总数走 `*_total`——
    全量名字会把一次回收报表变成几十 MB 的 JSON。
    """
    base = Path(root) if root else temp_dir()
    if prefixes is None:
        prefixes = KNOWN_PREFIXES
    if once_per_process:
        key = (str(base), older_than_seconds, bool(apply))
        if key in _swept_roots:
            return {"root": str(base), "removed": [], "skipped_young": [],
                    "skipped_unmarked": [], "failed": [],
                    "skipped_young_total": 0, "skipped_unmarked_total": 0,
                    "dry_run": not apply, "already_swept": True}
        _swept_roots.add(key)
    now = now if now is not None else time.time()
    removed, skipped_young, skipped_unmarked, failed = [], [], [], []
    totals = {"skipped_young": 0, "skipped_unmarked": 0}
    if not base.is_dir():
        return {"root": str(base), "removed": removed,
                "skipped_young": skipped_young,
                "skipped_unmarked": skipped_unmarked, "failed": failed,
                "skipped_young_total": 0, "skipped_unmarked_total": 0,
                "dry_run": not apply}
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        if prefixes and not any(entry.name.startswith(p) for p in prefixes):
            continue
        owner = owner_of(entry)
        if owner is None:
            totals["skipped_unmarked"] += 1
            if len(skipped_unmarked) < report_limit:
                skipped_unmarked.append(entry.name)
            continue
        if now - float(owner["created"]) < older_than_seconds:
            totals["skipped_young"] += 1
            if len(skipped_young) < report_limit:
                skipped_young.append(entry.name)
            continue
        if not apply:
            removed.append(entry.name)
            continue
        ok, _ = release(entry)
        if ok:
            removed.append(entry.name)
        else:
            failed.append(entry.name)
    return {"root": str(base), "removed": removed,
            "skipped_young": skipped_young, "skipped_unmarked": skipped_unmarked,
            "skipped_young_total": totals["skipped_young"],
            "skipped_unmarked_total": totals["skipped_unmarked"],
            "failed": failed, "dry_run": not apply}
