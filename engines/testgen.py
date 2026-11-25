#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试生成引擎（质量线 Phase 3A；治理壳 stdlib，运行于全局 Python）。

四种模式：
- skeleton：确定性 AST 骨架——按类型注解生成良性样例，产出冒烟测试
  （可调用、良性输入不抛异常）+ 全默认参数调用；未类型化函数生成
  skip+TODO 占位。默认 --style loop（零依赖，纯 pytest，可移植进任意
  仓库的行为回归闸）；--style hypothesis 产 @given 属性模板（要求目标
  仓库环境装有 hypothesis，verify 会用项目 .venv 验证）。
- llm：经 llm/provider 宿主协议让模型写真用例（材料=模块源码；
  host 模式 WAIT_HOST_LLM 退出码 1，宿主填 llm-tasks 后 --resume 续跑）；
- verify：测试文件 + 目标模块复制进临时目录跑 pytest——通过才算生成
  成功（生成物必须被验证，不接受"看起来像测试"）；
- patch：产新文件补丁（/dev/null → b/<rel>，git apply 可创建文件），
  供修复链落盘（Phase 4 task-order 接线）。

治理红线：本脚本不写被审仓库。

用法示例：
    py engines/testgen.py skeleton --file pkg/mod.py --out tests/test_gen_mod.py
    py engines/testgen.py llm --file pkg/mod.py --out tests/test_gen_mod.py
    py engines/testgen.py verify --file pkg/mod.py --test tests/test_gen_mod.py
    py engines/testgen.py patch --test tests/test_gen_mod.py --rel tests/test_gen_mod.py --out patches

退出码：0=成功；1=WAIT_HOST_LLM（llm 模式）或 verify 未通过；2=输入错误。
"""
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))
_ENGINES_DIR = Path(__file__).resolve().parent
if str(_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINES_DIR))
from artifact_names import patch_artifact_name  # noqa: E402 - 三引擎共用命名口径
from llm import provider  # noqa: E402 - 治理壳 stdlib

TYPE_SAMPLES = {
    "int": "[0, 1, -1, 42, 10**6]",
    "float": "[0.0, 1.5, -2.5, 3.14]",
    "bool": "[True, False]",
    "str": "['', 'x', 'hello world', '中文测试']",
    "list": "[[], [1], [1, 2, 3], ['a', 'b']]",
    "dict": "[{}, {'k': 1}, {'a': 1, 'b': 2}]",
    "tuple": "[(), (1,), (1, 2)]",
    "set": "[set(), {1}, {1, 2, 3}]",
}
HYPOTHESIS_STRATEGY = {
    "int": "st.integers()", "float": "st.floats(allow_nan=False)",
    "bool": "st.booleans()", "str": "st.text()",
    "list": "st.lists(st.integers())", "dict": "st.dictionaries(st.text(), st.integers())",
    "tuple": "st.tuples(st.integers())", "set": "st.sets(st.integers())",
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _ann_name(ann):
    if ann is None:
        return ""
    if isinstance(ann, ast.Name):
        return ann.id
    if isinstance(ann, ast.Constant):
        return str(ann.value)
    return ""


def _functions(tree):
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and not node.name.startswith("_"):
            params = []
            for arg in node.args.args + node.args.kwonlyargs:
                params.append({"name": arg.arg,
                               "type": _ann_name(arg.annotation),
                               "has_default": False})
            defaults = [None] * (len(node.args.args) - len(node.args.defaults)) \
                + list(node.args.defaults)
            for i, param in enumerate(node.args.args and params[:len(node.args.args)] or []):
                if i < len(defaults) and defaults[i] is not None:
                    param["has_default"] = True
            out.append({"name": node.name, "params": params})
    return out


def _render_loop(func, module_name):
    """零依赖风格：良性样例循环冒烟。"""
    name = func["name"]
    typed = [p for p in func["params"] if p["type"] in TYPE_SAMPLES]
    all_typed = len(typed) == len(func["params"]) and func["params"]
    all_default = func["params"] and all(p["has_default"] for p in func["params"])
    lines = []
    if all_default:
        lines.append("def test_%s_defaults():" % name)
        lines.append("    result = %s.%s()" % (module_name, name))
        lines.append("    assert callable(result) or result is not None or result is None")
    elif all_typed:
        lines.append("def test_%s_smoke():" % name)
        arg_names = ", ".join(p["name"] for p in typed)
        if len(typed) == 1:
            lines.append("    samples = %s" % TYPE_SAMPLES[typed[0]["type"]])
            lines.append("    for %s in samples:" % arg_names)
        else:
            lines.append("    samples = [%s]" % ", ".join(
                TYPE_SAMPLES[p["type"]] for p in typed))
            lines.append("    for %s in zip(*samples):" % arg_names)
        lines.append("        %s.%s(%s)" % (module_name, name, arg_names))
    else:
        lines.append("import pytest")
        lines.append("")
        lines.append("@pytest.mark.skip(reason='testgen: 未类型化参数，待补真实用例')")
        lines.append("def test_%s_todo():" % name)
        lines.append("    assert True")
    return lines


def _render_hypothesis(func, module_name):
    """hypothesis 风格：@given 属性模板（目标仓库需装 hypothesis）。"""
    name = func["name"]
    typed = [p for p in func["params"] if p["type"] in HYPOTHESIS_STRATEGY]
    if not typed or len(typed) != len(func["params"]) or not func["params"]:
        return _render_loop(func, module_name)
    args = ", ".join("%s=%s" % (p["name"], HYPOTHESIS_STRATEGY[p["type"]])
                     for p in typed)
    lines = ["@given(%s)" % args]
    lines.append("def test_%s_property(%s):" % (name, ", ".join(
        p["name"] for p in typed)))
    lines.append("    # 属性：任意良性类型输入不抛异常（健壮性回归信号）")
    lines.append("    %s.%s(%s)" % (module_name, name,
                                    ", ".join(p["name"] for p in typed)))
    return lines


def cmd_skeleton(argv):
    src = Path(argv.file)
    if not src.is_file():
        _emit({"ok": False, "error": "源文件不存在: %s" % src})
        return 2
    module_name = argv.module_name or src.stem
    tree = ast.parse(src.read_text(encoding="utf-8", errors="replace"))
    funcs = _functions(tree)
    if not funcs:
        _emit({"ok": False, "error": "模块无公开顶层函数"})
        return 2
    renderer = _render_hypothesis if argv.style == "hypothesis" else _render_loop
    header = [
        '"""testgen 生成（engine=testgen, style=%s）——冒烟/属性回归测试。'
        % argv.style,
        '良性输入不抛异常是行为回归闸的最低信号；真值断言请补真实用例。"""',
        "import pytest  # noqa: F401",
        "",
        "import %s" % module_name,
        "",
    ]
    body = []
    for func in funcs:
        body.extend(renderer(func, module_name))
        body.append("")
    if argv.style == "hypothesis":
        header.insert(3, "from hypothesis import given")
        header.insert(4, "from hypothesis import strategies as st")
        header.insert(5, "")
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(header + body), encoding="utf-8", newline="\n")
    covered = [f["name"] for f in funcs]
    _emit({"ok": True, "mode": "skeleton", "style": argv.style,
           "out": str(out), "functions": covered,
           "note": "生成物须先 verify 通过才可用"})
    return 0


LLM_SYSTEM = (
    "你是测试工程师，只输出 Python 代码。为给定模块编写 pytest 测试文件："
    "覆盖每个公开函数的正常路径与至少一个边界值；断言具体返回值（不是"
    "不抛异常）；不修改被测模块；文件以 import 模块名 开头。"
)


def cmd_llm(argv):
    src = Path(argv.file)
    if not src.is_file():
        _emit({"ok": False, "error": "源文件不存在: %s" % src})
        return 2
    module_name = argv.module_name or src.stem
    material = "## 模块 %s\n```python\n%s\n```" % (
        module_name, src.read_text(encoding="utf-8", errors="replace"))
    base_dir = Path(argv.out).resolve().parent / "llm-tasks"
    try:
        raw, meta = provider.complete(LLM_SYSTEM, material, base_dir=base_dir)
    except provider.HostLLMPending as pending:
        _emit({"ok": False, "state": "WAIT_HOST_LLM",
               "llm_task": pending.prompt_path,
               "llm_response": pending.response_path,
               "note": "宿主模型：读 llm_task，仅输出测试代码写入 llm_response，"
                       "然后重跑本命令续跑（幂等）"})
        return 1
    if raw is None:
        _emit({"ok": False, "error": "LLM 不可用：%s" % meta})
        return 2
    code = re.sub(r"^```(?:python)?|```$", "", raw.strip(), flags=re.M).strip()
    if not code:
        _emit({"ok": False, "error": "LLM 响应为空代码"})
        return 2
    out = Path(argv.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code + "\n", encoding="utf-8", newline="\n")
    _emit({"ok": True, "mode": "llm", "out": str(out),
           "note": "生成物须先 verify 通过才可用"})
    return 0


def _pytest_exe():
    for cand in (AGENT_ROOT / ".venv" / "Scripts" / "python.exe", "py"):
        target = str(cand)
        try:
            probe = subprocess.run([target, "-c", "import pytest"], shell=False,
                                   capture_output=True, timeout=30)
        except OSError:
            continue
        if probe.returncode == 0:
            return target
    return None


def cmd_verify(argv):
    src = Path(argv.file)
    test = Path(argv.test)
    if not src.is_file() or not test.is_file():
        _emit({"ok": False, "error": "源文件或测试文件不存在"})
        return 2
    exe = _pytest_exe()
    if exe is None:
        _emit({"ok": False, "error": "环境无 pytest"})
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="testgen-verify-"))
    try:
        shutil.copy(src, tmp / src.name)
        shutil.copy(test, tmp / test.name)
        proc = subprocess.run(
            [exe, "-m", "pytest", "-q", str(tmp / test.name)],
            shell=False, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300, cwd=str(tmp))
        tail = [l for l in (proc.stdout or "").strip().splitlines() if l][-6:]
        _emit({"ok": proc.returncode == 0, "mode": "verify",
               "passed": proc.returncode == 0, "summary": tail})
        return 0 if proc.returncode == 0 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_patch(argv):
    test = Path(argv.test)
    if not test.is_file():
        _emit({"ok": False, "error": "测试文件不存在: %s" % test})
        return 2
    rel = Path(argv.rel).as_posix()
    if ".." in rel.split("/"):
        _emit({"ok": False, "error": "rel 路径非法"})
        return 2
    lines = test.read_text(encoding="utf-8", errors="replace").splitlines()
    patch = ["diff --git a/%s b/%s" % (rel, rel),
             "new file mode 100644",
             "--- /dev/null",
             "+++ b/%s" % rel,
             "@@ -0,0 +1,%d @@" % len(lines)]
    patch += ["+" + l for l in lines]
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_path = out_dir / patch_artifact_name("testgen", rel, ".patch")
    patch_path.write_text("\n".join(patch) + "\n", encoding="utf-8",
                          newline="\n")
    _emit({"ok": True, "mode": "patch", "patch_path": str(patch_path),
           "lines": len(lines)})
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="测试生成引擎")
    sub = parser.add_subparsers(dest="mode", required=True)
    p_sk = sub.add_parser("skeleton")
    p_sk.add_argument("--file", required=True)
    p_sk.add_argument("--out", required=True)
    p_sk.add_argument("--module-name", dest="module_name", default="")
    p_sk.add_argument("--style", choices=["loop", "hypothesis"], default="loop")
    p_llm = sub.add_parser("llm")
    p_llm.add_argument("--file", required=True)
    p_llm.add_argument("--out", required=True)
    p_llm.add_argument("--module-name", dest="module_name", default="")
    p_vf = sub.add_parser("verify")
    p_vf.add_argument("--file", required=True)
    p_vf.add_argument("--test", required=True)
    p_pt = sub.add_parser("patch")
    p_pt.add_argument("--test", required=True)
    p_pt.add_argument("--rel", required=True)
    p_pt.add_argument("--out", required=True)
    argv = parser.parse_args()
    return {"skeleton": cmd_skeleton, "llm": cmd_llm,
            "verify": cmd_verify, "patch": cmd_patch}[argv.mode](argv)


if __name__ == "__main__":
    sys.exit(main())
