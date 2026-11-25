#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""档案员：成败双轨案例归档 + 详细摘抄 + 可推送任意 Git 仓库。

与 case-match.py 的轻索引分工：本脚本负责"详细整理"——每个案例渲染成
archive/<id>.md 档案文件（背景/摘抄/根因/对策教训/验收/链接），本地档案仓
（archive-repo/）以 git 提交保存，可推送用户自选的任意 Git 远端
（--push --remote，远端 URL 做 host 校验：拒绝 localhost/环回/私有/保留地址）。

双轨：--kind success（优秀案例：可复用的解法）/ failure（失败案例：试过什么、
为何失败、教训是什么）。失败案例在匹配命中时提示"避免此路径"。

用法示例：
    py case-archive.py --kind failure --title "..." --digest "详细摘抄..." \
        --lessons "..." --local-ref <档案路径> --out retro
    py case-archive.py --from-artifacts --scan runs --out retro   # 自动收失败案例
    py case-archive.py --publish --out retro                       # 渲染档案 + 本地提交
    py case-archive.py --publish --out retro --push --remote https://github.com/me/cases.git

退出码：0=成功（推送失败也算存储成功，回执 pushed=false）；2=输入错误。
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CASE_MATCH = ROOT / "skills" / "director" / "scripts" / "case-match.py"

RESERVED_HOST_PAT = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1$|"
    r"172\.(1[6-9]|2\d|3[01])\.)")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _validate_remote(url):
    """推送远端校验：仅 https/http 或 git@ 形式；拒绝本地/私有/保留地址。"""
    url = str(url).strip()
    if url.startswith("git@"):
        host = url[4:].split(":")[0].split("/")[0]
        scheme = "ssh"
    elif "://" in url:
        scheme, rest = url.split("://", 1)
        if scheme not in ("https", "http"):
            return None, "仅支持 https/http 或 git@ 形式，收到: %s" % scheme
        host = rest.split("/")[0].split(":")[0].split("@")[-1]
    else:
        return None, "远端需 https:// 或 git@ 形式"
    host = host.strip("[]").lower()
    if not host:
        return None, "远端缺 host"
    if RESERVED_HOST_PAT.match(host) or host.endswith((".local", ".internal")):
        return None, "拒绝本地/私有/保留地址: %s" % host
    return {"scheme": scheme, "host": host}, None


def _git(repo_dir, args):
    # GIT_TERMINAL_PROMPT=0：无凭据时立即失败，禁止交互挂死
    env = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
    proc = subprocess.run(["git", "-C", str(repo_dir)] + args, shell=False,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, env=env)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _load_index(out_dir):
    path = Path(out_dir) / "cases.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return path, data.get("cases", [])


def _render_archive(case, digest, lessons):
    lines = ["# 案例 %s：%s" % (case.get("id"), case.get("title", "")), ""]
    lines.append("- 类别：%s | 类型：%s | 状态：%s" % (
        case.get("category", "-"),
        "失败案例" if case.get("kind") == "failure" else "优秀案例",
        case.get("status", "-")))
    lines.append("- 档案链接：%s" % (case.get("url") or case.get("local_ref") or "-"))
    if case.get("sources"):
        lines.append("- 参考：%s" % "、".join(case["sources"]))
    lines.append("")
    lines.append("## 详细摘抄")
    lines.append("")
    lines.append(digest.strip())
    lines.append("")
    if lessons:
        lines.append("## 教训与对策")
        lines.append("")
        lines.append(lessons.strip())
        lines.append("")
    lines.append("## 验收口径")
    lines.append("")
    lines.append(case.get("verification", "-"))
    lines.append("")
    lines.append("_整理时间：%s（档案员）_" % datetime.date.today().isoformat())
    return "\n".join(lines) + "\n"


def _ingest(args, out_dir):
    if not args.title or not args.digest:
        _emit({"ok": False, "error": "入库需要 --title 与 --digest（详细摘抄）"})
        return 2
    if not args.url and not args.local_ref:
        _emit({"ok": False, "error": "需要 --url 或 --local-ref（档案链接）"})
        return 2
    index_path, cases = _load_index(out_dir)
    proc = subprocess.run(
        [sys.executable, str(CASE_MATCH), "--ingest",
         "--category", args.category, "--title", args.title,
         "--takeaway", (args.lessons or args.digest)[:400],
         "--verification", args.verification,
         "--url", args.url, "--local-ref", args.local_ref,
         "--out", str(out_dir)],
        shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60)
    if proc.returncode != 0:
        _emit({"ok": False, "error": "索引入库失败: %s" % proc.stderr[:200]})
        return 2
    index_path, cases = _load_index(out_dir)
    cid = json.loads(proc.stdout).get("id")
    for case in cases:
        if case.get("id") == cid:
            case["kind"] = args.kind
            case["detail_ref"] = "archive/%s.md" % cid
    index_path.write_text(
        json.dumps({"cases": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8", newline="\n")
    archive_dir = out_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    digest_path = archive_dir / ("%s.md" % cid)
    digest_path.write_text(_render_archive(
        next(c for c in cases if c.get("id") == cid),
        args.digest, args.lessons), encoding="utf-8", newline="\n")
    _emit({"ok": True, "mode": "ingest", "id": cid, "kind": args.kind,
           "archive_md": str(digest_path),
           "note": "详细摘抄已归档；发布推送用 --publish --push"})
    return 0


def _from_artifacts(args, out_dir, errors):
    """自动收失败案例：ROLLED_BACK 落盘台账与 REJECTED 批准书。"""
    created = 0
    for root in args.scan or []:
        root = Path(root)
        if not root.exists():
            errors.append("扫描路径不存在: %s" % root)
            continue
        for path in root.rglob("apply-log.json"):
            try:
                log = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                errors.append("apply-log 解析失败(%s): %s" % (path, exc))
                continue
            if log.get("status") != "ROLLED_BACK":
                continue
            rc, ingested = _run_case_match_ingest(
                out_dir, category="失败案例",
                kind="failure",
                title="落盘回滚: %s" % str(log.get("error", ""))[:120],
                digest="回滚现场：%s；修复文件：%s" % (
                    log.get("error", "-"),
                    [f.get("path") for f in log.get("files", [])]),
                lessons="；".join(h.get("takeaway", "")
                                  for h in log.get("reuse_hints", [])) or
                        "按 reuse_hints 复用案例对策",
                verification="复跑五道闸全绿",
                local_ref=str(path))
            if rc == 0:
                created += 1
    _emit({"ok": True, "mode": "from-artifacts", "created": created,
           "errors": errors})
    return 0


def _run_case_match_ingest(out_dir, category, title, digest, lessons,
                           verification, local_ref, kind="success"):
    proc = subprocess.run(
        [sys.executable, str(CASE_MATCH), "--ingest", "--category", category,
         "--title", title, "--takeaway", (lessons or digest)[:400],
         "--verification", verification, "--local-ref", local_ref,
         "--out", str(out_dir)],
        shell=False, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60)
    if proc.returncode != 0:
        return proc.returncode, {}
    ingested = json.loads(proc.stdout)
    # 双轨标记：批量路径同样回写 kind 与档案位
    index_path = Path(out_dir) / "cases.json"
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        for case in data.get("cases", []):
            if case.get("id") == ingested.get("id"):
                case["kind"] = kind
                case["detail_ref"] = "archive/%s.md" % case["id"]
        index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        sys.stderr.write("双轨标记回写失败（索引仍可用）: %s\n" % exc)
    return 0, ingested


def _publish(args, out_dir, errors):
    """渲染全部案例档案 + 本地档案仓提交 + 可选推送。"""
    index_path, cases = _load_index(out_dir)
    archive_dir = out_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    rendered = 0
    for case in cases:
        digest_ref = case.get("detail_ref")
        digest = "（摘抄见 %s；本页为索引渲染）" % digest_ref if digest_ref else \
            case.get("takeaway", "-")
        if digest_ref:
            ref_path = out_dir / digest_ref
            if ref_path.is_file():
                digest = ref_path.read_text(encoding="utf-8", errors="replace")
        (archive_dir / ("%s.md" % case.get("id"))).write_text(
            _render_archive(case, digest, case.get("takeaway", "")),
            encoding="utf-8", newline="\n")
        rendered += 1
    readme = out_dir / "archive" / "README.md"
    readme.write_text("# 案例档案（成败双轨）\n\n共 %d 条；"
                      "本档案仓由档案员维护，可推送任意 Git 远端。\n"
                      % len(cases), encoding="utf-8", newline="\n")

    repo_dir = out_dir / "archive-repo"
    repo_dir.mkdir(exist_ok=True)
    if not (repo_dir / ".git").is_dir():
        rc, out_init = _git(repo_dir, ["init", "-q"])
        if rc != 0:
            errors.append("git init 失败: %s" % out_init[:200])
    # 档案文件同步进仓库工作区再提交
    repo_archive = repo_dir / "archive"
    repo_archive.mkdir(exist_ok=True)
    for src in archive_dir.glob("*.md"):
        (repo_archive / src.name).write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    _git(repo_dir, ["-c", "user.name=archivist",
                    "-c", "user.email=archivist@local", "add", "-A"])
    rc, out_commit = _git(repo_dir, ["-c", "user.name=archivist",
                                     "-c", "user.email=archivist@local",
                                     "commit", "-q", "-m",
                                     "cases archive: %d entries" % len(cases)])
    committed = rc == 0 or "nothing to commit" in out_commit
    pushed = False
    push_note = "未请求推送"
    if args.push:
        target, err = _validate_remote(args.remote)
        if err:
            _emit({"ok": False, "error": "远端校验失败: %s" % err})
            return 2
        _git(repo_dir, ["remote", "remove", "origin"])
        rc, out_remote = _git(repo_dir, ["remote", "add", "origin", args.remote])
        if rc != 0:
            errors.append("remote add 失败: %s" % out_remote[:200])
        rc, out_push = _git(repo_dir, ["push", "-u", "origin", "HEAD"])
        pushed = rc == 0
        push_note = ("已推送 %s" % target["host"]) if pushed else \
            "推送失败（凭据/网络）：档案已在本地提交，%s" % out_push[:200]
    _emit({"ok": True, "mode": "publish", "rendered": rendered,
           "committed": committed, "pushed": pushed,
           "archive_repo": str(repo_dir), "push_note": push_note,
           "errors": errors})
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="档案员：成败双轨案例归档与发布")
    parser.add_argument("--out", required=True, help="案例库目录（retro）")
    parser.add_argument("--kind", default="success", choices=["success", "failure"],
                        help="案例类型：success 优秀案例 / failure 失败案例")
    parser.add_argument("--title", default="", help="案例标题")
    parser.add_argument("--digest", default="", help="详细摘抄（多行，归档正文）")
    parser.add_argument("--lessons", default="", help="教训与对策")
    parser.add_argument("--verification", default="", help="验收口径")
    parser.add_argument("--category", default="手工", help="案例类别")
    parser.add_argument("--url", default="", help="公开档案/仓库链接")
    parser.add_argument("--local-ref", dest="local_ref", default="",
                        help="本仓库档案路径")
    parser.add_argument("--from-artifacts", action="store_true",
                        help="从产物痕迹自动收失败案例")
    parser.add_argument("--scan", action="append", default=[],
                        help="产物扫描目录，可多次")
    parser.add_argument("--publish", action="store_true",
                        help="渲染档案 + 本地档案仓提交")
    parser.add_argument("--push", action="store_true", help="推送到远端")
    parser.add_argument("--remote", default="", help="Git 远端 URL（--push 时必填）")
    argv = parser.parse_args()
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if argv.publish:
        return _publish(argv, out_dir, [])
    if argv.from_artifacts:
        return _from_artifacts(argv, out_dir, [])
    return _ingest(argv, out_dir)


if __name__ == "__main__":
    sys.exit(main())
