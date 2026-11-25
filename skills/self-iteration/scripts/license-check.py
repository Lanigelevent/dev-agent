#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""依赖许可证清单校验：pyproject 直接依赖与入库注册表逐项对账。

用途：
    阶段三 3.4 门禁。读 pyproject.toml 的三类依赖——运行时 dependencies
    （可 import）、optional.isolated（LGPL 引擎，仅 subprocess）、
    optional.dev（测试/构建工具，不随治理壳分发）——与
    skills/self-iteration/licenses.json 注册表逐项对账：每条声明的依赖
    必须有登记、模式一致、许可证落在该模式的策略白名单内；GPL/AGPL 一律
    禁止，LGPL 只允许 subprocess，MPL 只允许 test-only（G12 裁定，D-034）。
    注册表多出未声明的条目、缺 reason、许可证未知，同样判失败。

用法：
    python license-check.py --root .
    python license-check.py --root . --registry skills/self-iteration/licenses.json
    python license-check.py --root pyproject.toml --json-out reports/_work/lic.json

退出码：
    0 = 全部一致且在策略内
    1 = 违规（未登记/模式不符/许可证不被允许/注册表多余）
    2 = 输入或环境错误（文件缺失、TOML/JSON 非法）
"""
import argparse
import importlib.metadata
import json
import re
import sys
import tomllib
from pathlib import Path

SCHEMA = "license-registry/1"
SECTIONS = (("import", ("dependencies",)),
            ("subprocess", ("optional-dependencies", "isolated")),
            ("test-only", ("optional-dependencies", "dev")))
BANNED_PREFIXES = ("GPL-", "AGPL-")
NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _norm(name):
    return name.strip().lower().replace("_", "-")


def _declared_name(spec):
    m = NAME_RE.match(spec or "")
    return _norm(m.group(1)) if m else ""


def _deps(pyproject):
    project = pyproject.get("project") or {}
    out = {"import": [], "subprocess": [], "test-only": []}
    for item in project.get("dependencies") or []:
        out["import"].append(_declared_name(item))
    optional = project.get("optional-dependencies") or {}
    for item in optional.get("isolated") or []:
        out["subprocess"].append(_declared_name(item))
    for item in optional.get("dev") or []:
        out["test-only"].append(_declared_name(item))
    return out


def _license_ok(license_id, mode, policy):
    lic = (license_id or "").strip()
    if not lic:
        return False, "许可证未登记"
    if lic.upper().startswith(BANNED_PREFIXES):
        return False, "GPL/AGPL 系禁止使用"
    if lic.upper().startswith("LGPL") and mode != "subprocess":
        return False, "LGPL 只允许 subprocess 隔离调用"
    if lic.upper().startswith("MPL") and mode != "test-only":
        return False, "MPL 只允许 test-only（G12 裁定）"
    allowed = policy.get(mode) or []
    if lic not in allowed:
        return False, "许可证 %s 不在 %s 白名单内" % (lic, mode)
    return True, "ok"


def check(root, registry_path):
    root = Path(root).resolve()
    pyproject_path = root / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError("pyproject 不可读: %s" % exc)
    try:
        registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("注册表不可读: %s" % exc)
    if registry.get("schema") != SCHEMA:
        raise ValueError("注册表 schema 不符: %s" % registry.get("schema"))
    policy = registry.get("policy") or {}
    packages = {_norm(k): v for k, v in (registry.get("packages") or {}).items()}
    declared = _deps(pyproject)
    problems = []
    checked = []
    declared_all = set()
    for mode, _ in SECTIONS:
        for name in declared[mode]:
            declared_all.add(name)
            entry = packages.get(name)
            if entry is None:
                problems.append({"package": name, "mode": mode,
                                 "problem": "未在注册表登记"})
                continue
            entry_mode = str(entry.get("mode") or "").strip()
            if entry_mode != mode:
                problems.append({"package": name, "mode": mode,
                                 "problem": "注册表模式=%s 与声明位置不符"
                                            % (entry_mode or "?")})
            if not str(entry.get("reason") or "").strip():
                problems.append({"package": name, "mode": mode,
                                 "problem": "缺 reason（用途说明）"})
            ok, why = _license_ok(str(entry.get("license") or ""), mode, policy)
            if not ok:
                problems.append({"package": name, "mode": mode,
                                 "license": entry.get("license"),
                                 "problem": why})
            try:
                version = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                # 未安装是合法状态：版本只作证据，按注册表条目判定
                version = "n/a（未安装，按注册表判定）"
            checked.append({"package": name, "mode": mode,
                            "license": entry.get("license"),
                            "allowed": ok, "installed": version})
    stale = sorted(n for n in packages if n not in declared_all)
    for name in stale:
        problems.append({"package": name, "mode": packages[name].get("mode"),
                         "problem": "注册表条目未被 pyproject 声明（漂移）"})
    ok = not problems
    return {
        "ok": ok,
        "state": "PASS" if ok else "VIOLATION",
        "root": str(root),
        "registry": str(Path(registry_path).resolve()),
        "declared": declared,
        "checked": checked,
        "stale_registry_entries": stale,
        "problems": problems,
        "policy": policy,
    }


def main():
    parser = argparse.ArgumentParser(description="依赖许可证清单校验")
    parser.add_argument("--root", default=".")
    parser.add_argument("--registry",
                        default="skills/self-iteration/licenses.json")
    parser.add_argument("--json-out", default=None,
                        help="另存一份 JSON 证据到该路径（可选）")
    argv = parser.parse_args()
    registry = argv.registry
    if not Path(registry).is_absolute():
        registry = str(Path(argv.root).resolve() / registry)
    try:
        result = check(argv.root, registry)
    except ValueError as exc:
        _emit({"ok": False, "state": "ERROR", "error": str(exc)})
        return 2
    if argv.json_out:
        out = Path(argv.json_out)
        if not out.is_absolute():
            out = Path(argv.root).resolve() / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
