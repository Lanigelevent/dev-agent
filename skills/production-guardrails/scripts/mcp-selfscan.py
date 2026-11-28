#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 自扫描：16 工具清单哈希固化与漂移拒服务（阶段 5 批次一 M1，round-233）。

背景：本仓自身暴露 16 个 MCP 工具（mcp/review_mcp.py TOOLS）+ 工具分级门控
清单（mcp/tools-policy.json，M4）。对标 agent-scan 的「工具描述哈希跨会话
固化防 rug-pull」设计（ROADMAP §3.1 行 4），把工具名/描述/Schema 的 sha256
固化入仓，CI 与服务器启动时比对：任何漂移（描述篡改、清单增删、策略文件
改动而未重 pin）一律判红。

两级比对面：
- check：重算当前哈希与 mcp/tools-pin.json 对账（CI 门禁与启动比对共用）。
- pin：重算并覆写 mcp/tools-pin.json（清单/策略演进时同轮执行，须与 TOOLS
  /policy 改动同 commit）。

退出码：0 = 全绿；1 = 漂移或缺失（可处理：与 TOOLS/policy 改动同轮重跑
pin 并提交）；2 = 输入/环境错误（root 不存在、review_mcp.py 不可解析）。
stdout 只输出一个 JSON 文档，诊断走 stderr。

用法示例：
    py mcp-selfscan.py --root . check
    py mcp-selfscan.py --root . pin
    py mcp-selfscan.py --root . check --pin <路径>   # 检查自检
"""
import argparse
import ast
import hashlib
import json
import sys
import time
from pathlib import Path

PIN_REL = "mcp/tools-pin.json"
POLICY_REL = "mcp/tools-policy.json"
SERVER_REL = "mcp/review_mcp.py"
LEVELS = ("auto", "gated", "deny")


def _load_tools(server_path):
    """从 review_mcp.py 取 TOOLS：importlib 载入（顶层无副作用，main 有 guard）。

    ast 语法校验先行：解析失败 → ValueError（rc=2 面）。
    """
    src = server_path.read_text(encoding="utf-8")
    ast.parse(src)
    import importlib.util
    spec = importlib.util.spec_from_file_location("review_mcp_selfscan", server_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tools = getattr(mod, "TOOLS", None)
    if not isinstance(tools, list) or not tools:
        raise ValueError("review_mcp.py 未找到 TOOLS 列表")
    return tools


def _tool_hash(tool):
    """单工具规范哈希：name + description + 规范 JSON(inputSchema) 的 sha256。"""
    name = str(tool.get("name", ""))
    desc = str(tool.get("description", ""))
    schema = tool.get("inputSchema") or {}
    canonical = json.dumps(schema, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    h = hashlib.sha256()
    h.update(name.encode("utf-8"))
    h.update(b"\x1f")
    h.update(desc.encode("utf-8"))
    h.update(b"\x1f"
             + canonical.encode("utf-8"))
    return h.hexdigest()


def _policy_hash_bytes(policy_path):
    """策略文件规范哈希：解码后按 LF 规范化再哈希（git 换行规范化不产生假漂移；
    内容篡改仍必命中）。
    """
    raw = policy_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    text = text.replace(chr(13) + chr(10), chr(10))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()



    """策略文件原始字节 sha256（篡改任意字节即漂移）。"""
    return hashlib.sha256(policy_path.read_bytes()).hexdigest()


def _compute(root):
    """重算全部哈希。返回 dict（与 pin 文件同形状，不含 generated_at）。"""
    root = Path(root)
    server = root / SERVER_REL
    policy = root / POLICY_REL
    if not server.is_file():
        raise FileNotFoundError("未找到 %s" % SERVER_REL)
    tools = _load_tools(server)
    hashes = {}
    for tool in tools:
        name = str(tool.get("name", ""))
        if not name:
            raise ValueError("TOOLS 含无名工具条目")
        hashes[name] = _tool_hash(tool)
    policy_sha = None
    if policy.is_file():
        policy_sha = _policy_hash_bytes(policy)
    names_sorted = ",".join(sorted(hashes))
    bundle = hashlib.sha256()
    bundle.update(names_sorted.encode("utf-8"))
    bundle.update(b"\x1f")
    for name in sorted(hashes):
        bundle.update(name.encode("utf-8"))
        bundle.update(b"=")
        bundle.update(hashes[name].encode("ascii"))
        bundle.update(b"\x1e")
    bundle.update(b"policy=")
    bundle.update((policy_sha or "none").encode("ascii"))
    return {
        "schema": "tools-pin/v1",
        "tools": hashes,
        "policy_sha256": policy_sha,
        "bundle_sha256": bundle.hexdigest(),
    }


def check(root, pin_path=None):
    """重算哈希与 pin 文件对账；返回 (ok, drifts, computed)。"""
    root = Path(root)
    computed = _compute(root)
    pin_path = Path(pin_path) if pin_path else root / PIN_REL
    if not pin_path.is_file():
        return False, [{"id": "pin_missing", "detail": "pin 文件不存在: %s" % pin_path}], computed
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return False, [{"id": "pin_corrupt", "detail": "pin 非法 JSON: %s" % exc}], computed
    drifts = []
    ct = computed["tools"]
    pt = pin.get("tools") or {}
    for name in sorted(set(ct) | set(pt)):
        c, q = ct.get(name), pt.get(name)
        if q is None:
            drifts.append({"id": "tool_missing_in_pin", "tool": name})
        elif c is None:
            drifts.append({"id": "tool_extra_in_pin", "tool": name})
        elif c != q:
            drifts.append({"id": "tool_hash_mismatch", "tool": name})
    if computed["policy_sha256"] != pin.get("policy_sha256"):
        drifts.append({"id": "policy_drift", "detail": "tools-policy.json 与 pin 不一致"})
    if computed["bundle_sha256"] != pin.get("bundle_sha256"):
        drifts.append({"id": "bundle_drift"})
    return (not drifts), drifts, computed


def pin_verb(root):
    """重算并覆写 mcp/tools-pin.json（与 TOOLS/policy 改动同轮执行）。"""
    root = Path(root)
    computed = _compute(root)
    doc = dict(computed)
    doc["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    doc["note"] = "由 mcp-selfscan.py pin 生成；与 TOOLS/policy 改动同 commit"
    path = root / PIN_REL
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description="MCP 自扫描 pin/check")
    ap.add_argument("--root", default=".")
    ap.add_argument("verb", choices=["pin", "check"])
    ap.add_argument("--pin", default=None, help="覆盖默认 pin 路径（检查自检用）")
    args = ap.parse_args(argv)
    if not Path(args.root).is_dir():
        sys.stderr.write("root 不存在" + chr(10))
        return 2
    try:
        if args.verb == "pin":
            doc = pin_verb(args.root)
            sys.stderr.write("pin written (%d tools)" % len(doc["tools"]) + chr(10))
            return 0
        else:
            ok, values, computed = check(args.root)
            doc = {"ok": ok, "drifts": values, "tool_count": len(computed["tools"]),
                   "schema": computed["schema"]}
            if not ok:
                sys.stderr.write("MCP 自扫描漂移，拒服务面" + chr(10))
        return 0 if ok else 1
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write("输入/环境错误: %s" % exc + chr(10))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
