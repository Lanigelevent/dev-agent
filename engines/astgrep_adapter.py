#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ast-grep 引擎适配器（MIT 引擎；按 AGENTS 硬约束 1 以 subprocess+JSON 调用，
本适配器自身零第三方依赖，运行于全局 Python；ast-grep-py 在 .venv）。

ast-grep-py 是 ast-grep 的 Python 绑定（MIT），通过 SgRoot/SgNode 提供
AST 级模式匹配与重写。与 ruff（lint 规则）不同，ast-grep 的「规则」是
YAML/JSON 模式描述，按语言族组织——这是 dev-agent 引擎矩阵的第一枚
多语言引擎（ruff/libcst 仅 Python）。

五子命令（与 ruff_adapter 同形状）：
- scan：对文件跑规则集，输出本仓 findings 形状
  （rule_id=astgrep:<code>；console.log/debugger→中，empty-block→低）；
- fix-dry：临时副本跑 ast-grep 重写，difflib 产 a/<rel> b/<rel> 的
  LF 补丁（与 fix-patch 产物同格式，五道闸可直接 git apply），不写原文件；
- matrix：枚举内置规则集 → 能力矩阵 astgrep-matrix.json（规则总数/
  可修复数/按语言分布/版本），供总监治理与 fix-plan 分诊；
- clean-fp：规则集在干净语料的命中统计（启用分级依据）。

内置规则（v2，JS/TS + Python，跨语言第一枚）：
- no-console-log: console.log($$) → 删除（JS/TS）
- no-debugger: debugger 语句 → 删除（JS/TS）
- no-empty-block: 空块体 → 标注（JS/TS）
- no-var: var $NAME = $$ → let $NAME = $$（JS/TS）
- no-eval: eval($$) → 标注（JS/TS，高危不自动修复）
- print-debug: print($$) → 标注（Python，与 console.log 对称）

用法示例：
    py engines/astgrep_adapter.py scan --file x.js
    py engines/astgrep_adapter.py fix-dry --repo <仓库> --rel pkg/mod.js --out <dir>
    py engines/astgrep_adapter.py matrix --out engines
    py engines/astgrep_adapter.py clean-fp --corpus <干净语料目录>

退出码：0=成功（含零诊断）；1=引擎不可用；2=输入/引擎错误。
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENGINES_DIR = Path(__file__).resolve().parent
if str(_ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINES_DIR))
from artifact_names import patch_artifact_name  # noqa: E402 - 三引擎共用命名口径

# 内置规则集：每条规则含 id/pattern/severity/fix/语言/描述。
# 判定规则先写死在常量（维护红线 6：检查器必有判据）。
BUILTIN_RULES = [
    {
        "id": "no-console-log",
        "pattern": "console.log($$$)",
        "severity": "中",
        "fix": "",  # 空串=删除整个匹配
        "languages": ["JavaScript", "TypeScript", "JavaScriptReact", "TypeScriptReact"],
        "description": "console.log 调试语句不应留在生产代码中",
    },
    {
        "id": "no-debugger",
        "pattern": "debugger",
        "severity": "中",
        "fix": "",
        "languages": ["JavaScript", "TypeScript", "JavaScriptReact", "TypeScriptReact"],
        "description": "debugger 断点语句不应留在生产代码中",
    },
    {
        "id": "no-empty-block",
        "pattern": "{ }",
        "severity": "低",
        "fix": None,  # None=只标注不修复
        "languages": ["JavaScript", "TypeScript"],
        "description": "空块体可能是遗漏的逻辑",
    },
    {
        "id": "no-var",
        "pattern": "var $NAME = $$$",
        "severity": "中",
        "fix": None,  # var→let 有作用域语义差异，不可机械修复
        "languages": ["JavaScript", "TypeScript", "JavaScriptReact", "TypeScriptReact"],
        "description": "var 声明有函数作用域与 hoisting 陷阱，应改用 let/const",
    },
    {
        "id": "no-eval",
        "pattern": "eval($$$)",
        "severity": "高",
        "fix": None,  # eval 替换不可机械决定，只标注
        "languages": ["JavaScript", "TypeScript", "JavaScriptReact", "TypeScriptReact"],
        "description": "eval 执行任意代码，有注入风险",
    },
    {
        "id": "print-debug",
        "pattern": "print($$$)",
        "severity": "低",
        "fix": None,  # Python print 删除需人工判断是否是日志
        "languages": ["Python"],
        "description": "print 调试语句不应留在生产代码中（Python）",
    },
    # ── 安全类（步骤 1.1）──
    {
        "id": "js-innerhtml-assignment",
        "pattern": "$EL.innerHTML = $VAL",
        "severity": "高",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "innerHTML 赋值有 XSS 风险，应使用 textContent 或 sanitize",
    },
    {
        "id": "js-document-write",
        "pattern": "document.write($$$)",
        "severity": "高",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "document.write 可被注入恶意内容，应避免使用",
    },
    {
        "id": "ts-unsafe-any-cast",
        "pattern": "$EXPR as any",
        "severity": "中",
        "fix": None,
        "languages": ["TypeScript", "TypeScriptReact"],
        "description": "as any 绕过类型检查，应使用更精确的类型断言",
    },
    {
        "id": "js-settimeout-string-arg",
        "pattern": 'setTimeout("$$$", $$$)',
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "setTimeout 首参为字符串等价于 eval，应使用箭头函数",
    },
    {
        "id": "js-regex-injection-new",
        "pattern": "new RegExp($$$)",
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "new RegExp 动态构造正则有 ReDoS/注入风险，应使用字面量",
    },
    {
        "id": "js-prototype-pollution",
        "pattern": "JSON.parse($$$)",
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "JSON.parse 结果可被 __proto__ 污染原型链，需校验",
    },
    # ── 代码质量类（步骤 1.2）──
    {
        "id": "js-empty-catch",
        "pattern": "try { $$$ } catch ($E) { }",
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "空 catch 块吞掉异常，应至少记录或重新抛出",
    },
    {
        "id": "js-loose-equality",
        "pattern": '$A == $B',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "宽松相等 == 有隐式类型转换，应使用严格相等 ===",
    },
    {
        "id": "js-throw-string",
        "pattern": 'throw "$$$"',
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "throw 字符串不是 Error 对象，丢失堆栈信息",
    },
    {
        "id": "js-typeof-undefined",
        "pattern": 'typeof $X === "undefined"',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "typeof x === 'undefined' 冗长，可用 x === undefined 代替",
    },
    {
        "id": "js-with-statement",
        "pattern": 'with ($$$) { $$$ }',
        "severity": "高",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "with 语句使作用域不可预测，严格模式禁用",
    },
    {
        "id": "js-void-expr",
        "pattern": 'void $$$',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "void 表达式语义模糊，应使用 undefined 显式标注",
    },
    {
        "id": "js-delete-expr",
        "pattern": 'delete $$$',
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "delete 操作有性能影响且在严格模式下受限",
    },
    {
        "id": "js-double-not",
        "pattern": '!!$$$',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "双重否定 !! 转布尔可用 Boolean() 更清晰",
    },
    {
        "id": "js-new-array",
        "pattern": 'new Array($$$)',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "new Array() 有歧义行为，应使用数组字面量 []",
    },
    # ── 最佳实践类（步骤 1.3）──
    {
        "id": "js-new-object",
        "pattern": 'new Object($$$)',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "new Object() 应使用对象字面量 {} 代替",
    },
    {
        "id": "js-parseint-no-radix",
        "pattern": 'parseInt($X)',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "parseInt 应传基数参数避免进制歧义",
    },
    {
        "id": "js-setinterval-no-clear",
        "pattern": 'setInterval($$$)',
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "setInterval 返回值应保存以便 clearInterval 清理",
    },
    {
        "id": "ts-empty-interface",
        "pattern": 'interface $NAME { }',
        "severity": "低",
        "fix": None,
        "languages": ["TypeScript", "TypeScriptReact"],
        "description": "空 interface 无成员，可用类型别名或 never 代替",
    },
    {
        "id": "ts-no-explicit-any",
        "pattern": 'let $NAME: any',
        "severity": "中",
        "fix": None,
        "languages": ["TypeScript", "TypeScriptReact"],
        "description": "显式 any 绕过类型检查，应使用精确类型",
    },
    {
        "id": "js-default-export-anonymous",
        "pattern": 'export default function() { $$$ }',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "匿名函数默认导出不利调试栈追踪，应具名",
    },
    {
        "id": "js-label-statement",
        "pattern": '$LABEL: $$$',
        "severity": "低",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "标签语句罕见且降低可读性，应重构控制流",
    },
    {
        "id": "js-throw-new-error",
        "pattern": 'throw $ERR',
        "severity": "中",
        "fix": None,
        "languages": ["JavaScript", "TypeScript",
                      "JavaScriptReact", "TypeScriptReact"],
        "description": "throw 应抛出 Error 对象而非裸值，保留堆栈信息",
    }
]

# 语言→文件后缀映射（用于 clean-fp 扫描）
LANG_EXT = {
    "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
    "TypeScript": [".ts", ".tsx"],
    "JavaScriptReact": [".jsx"],
    "TypeScriptReact": [".tsx"],
    "Python": [".py"],
}

# 文件后缀→语言推断
def _infer_lang(path):
    ext = Path(path).suffix.lower()
    for lang, exts in LANG_EXT.items():
        if ext in exts:
            return lang
    return None


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _venv_python():
    """项目 .venv 解释器路径（ast-grep-py 装在 .venv）。"""
    for cand in (ROOT / ".venv" / "Scripts" / "python.exe",
                 ROOT / ".venv" / "bin" / "python",
                 sys.executable):
        if str(cand) == str(sys.executable) or cand.is_file():
            return str(cand)
    return sys.executable


def _astgrep_available():
    """检查 ast-grep-py 是否在 .venv 中可用。"""
    code = "import ast_grep_py; print(ast_grep_py.__version__ if hasattr(ast_grep_py, '__version__') else 'ok')"
    try:
        p = subprocess.run([_venv_python(), "-c", code], shell=False,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# -- 子进程调用 ast-grep-py 的内联脚本（保持适配器零依赖）--

_SCAN_SCRIPT = r"""
import sys, json
from ast_grep_py import SgRoot

payload = json.load(open(sys.argv[1], encoding="utf-8"))
source = payload["source"]
lang = payload["lang"]
rules = payload["rules"]

findings = []
root = SgRoot(source, lang)
inner = root.root()
for rule in rules:
    if lang not in rule.get("languages", []):
        continue
    config = {"rule": {"pattern": rule["pattern"]}}
    nodes = inner.find_all(config)
    for node in nodes:
        pos = node.range()
        findings.append({
            "rule_id": "astgrep:" + rule["id"],
            "severity": rule.get("severity", "low"),
            "line": pos.start.line + 1,
            "col": pos.start.column,
            "text": node.text()[:160],
            "description": rule.get("description", ""),
        })
print(json.dumps(findings, ensure_ascii=False))
"""

_FIX_SCRIPT = r"""
import sys, json
from ast_grep_py import SgRoot

payload = json.load(open(sys.argv[1], encoding="utf-8"))
source = payload["source"]
lang = payload["lang"]
rules = payload["rules"]

root = SgRoot(source, lang)
inner = root.root()
edits = []
for rule in rules:
    if lang not in rule.get("languages", []):
        continue
    if rule.get("fix") is None:
        continue
    config = {"rule": {"pattern": rule["pattern"]}}
    nodes = inner.find_all(config)
    for node in nodes:
        edits.append(node.replace(rule["fix"]))
if edits:
    fixed = inner.commit_edits(edits)
else:
    fixed = source
if not isinstance(fixed, str):
    fixed = source
print(json.dumps({"fixed": fixed}, ensure_ascii=False))
"""

_VERSION_SCRIPT = "import ast_grep_py; print(getattr(ast_grep_py, '__version__', 'unknown'))"


def _run_astgrep(script, source, lang, rules, timeout=30):
    """以 .venv Python 运行 ast-grep-py 脚本，返回 (rc, data, err)。

    round-151：source 与 rules 经临时 payload 文件传递——此前走 argv，
    大文件 + 29 规则 JSON 超 Windows 32767 字符命令行上限（WinError
    206），7 个大文件扫描必炸；payload 文件传输无长度限制。"""
    import tempfile
    payload = json.dumps({"source": source, "lang": lang,
                          "rules": rules}, ensure_ascii=False)
    fd = tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                     delete=False, encoding="utf-8")
    try:
        fd.write(payload)
        fd.close()
        p = subprocess.run(
            [_venv_python(), "-c", script, fd.name],
            shell=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, None, str(exc)[:300]
    finally:
        import os
        try:
            os.unlink(fd.name)
        except OSError:
            pass
    try:
        data = json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError:
        data = None
    return p.returncode, data, p.stderr


def _finding(item, repo_rel):
    return {
        "rule_id": item["rule_id"],
        "severity": item.get("severity", "低"),
        "file": repo_rel,
        "line": int(item.get("line", 1)),
        "snippet": item.get("text", ""),
        "reason": "%s: %s" % (item["rule_id"], item.get("description", "")[:80]),
        "engine": "astgrep",
    }


def cmd_scan(argv):
    target = Path(argv.file)
    if not target.is_file():
        _emit({"ok": False, "error": "文件不存在: %s" % target})
        return 2
    lang = _infer_lang(target) or argv.lang
    if not lang:
        _emit({"ok": False, "error": "无法推断语言（用 --lang 指定）"})
        return 2
    if not _astgrep_available():
        _emit({"ok": False, "error": "ast-grep-py 不可用（.venv 未装 ast-grep-py）"})
        return 1
    source = target.read_text(encoding="utf-8", errors="replace")
    rules = BUILTIN_RULES
    if argv.select:
        rules = [r for r in rules if r["id"] in argv.select.split(",")]
    rc, items, err = _run_astgrep(_SCAN_SCRIPT, source, lang, rules)
    if rc != 0 or items is None:
        _emit({"ok": False, "error": "ast-grep 扫描失败: %s" % (err or "")[:300]})
        return 2
    repo_rel = argv.rel or str(target)
    findings = [_finding(i, repo_rel) for i in (items or [])]
    _emit({"ok": True, "engine": "astgrep", "lang": lang,
           "findings": findings,
           "codes": sorted({f["rule_id"] for f in findings})})
    return 0


def cmd_fix_dry(argv):
    repo = Path(argv.repo).resolve()
    rel = Path(argv.rel).as_posix()
    src = repo / rel
    if not src.is_file():
        _emit({"ok": False, "error": "源文件不存在: %s" % src})
        return 2
    lang = _infer_lang(src) or argv.lang
    if not lang:
        _emit({"ok": False, "error": "无法推断语言（用 --lang 指定）"})
        return 2
    if not _astgrep_available():
        _emit({"ok": False, "error": "ast-grep-py 不可用"})
        return 1
    original = src.read_text(encoding="utf-8", errors="replace")
    rules = BUILTIN_RULES
    if argv.select:
        rules = [r for r in rules if r["id"] in argv.select.split(",")]
    rc, data, err = _run_astgrep(_FIX_SCRIPT, original, lang, rules)
    if rc != 0 or data is None:
        _emit({"ok": False, "error": "ast-grep 修复失败: %s" % (err or "")[:300]})
        return 2
    fixed = data.get("fixed", original)
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        fixed.splitlines(keepends=True),
        fromfile="a/" + rel, tofile="b/" + rel)
    patch_text = "".join(diff)
    if patch_text and not patch_text.endswith("\n"):
        patch_text += "\n"
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_path = out_dir / patch_artifact_name("astgrep", rel, ".patch")
    if patch_text:
        patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    # 残余诊断：修复后再扫一次
    rc2, residual_items, _ = _run_astgrep(
        _SCAN_SCRIPT, fixed, lang,
        [r for r in rules if r.get("fix") is not None])
    residual_codes = sorted({i["rule_id"] for i in (residual_items or [])})
    _emit({"ok": True, "engine": "astgrep", "rel": rel, "lang": lang,
           "patch_path": str(patch_path) if patch_text else "",
           "patch_bytes": len(patch_text.encode("utf-8")),
           "residual_codes": residual_codes})
    return 0


def cmd_matrix(argv):
    if not _astgrep_available():
        _emit({"ok": False, "error": "ast-grep-py 不可用"})
        return 1
    # 版本
    try:
        p = subprocess.run([_venv_python(), "-c", _VERSION_SCRIPT],
                           shell=False, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        version = p.stdout.strip() if p.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        version = "unknown"
    fixable = [r["id"] for r in BUILTIN_RULES if r.get("fix") is not None]
    by_lang = {}
    for r in BUILTIN_RULES:
        for lang in r.get("languages", []):
            by_lang[lang] = by_lang.get(lang, 0) + 1
    matrix = {
        "engine": "astgrep",
        "version": version,
        "total_rules": len(BUILTIN_RULES),
        "fixable_rules": len(fixable),
        "safe_fixable_rules": len(fixable),  # ast-grep 重写是结构性的，全部 safe
        "fixable_codes": sorted(fixable),
        "safe_fixable_codes": sorted(fixable),
        "by_language": dict(sorted(by_lang.items(), key=lambda kv: -kv[1])),
        "builtin_rules": [{"id": r["id"], "pattern": r["pattern"],
                           "severity": r.get("severity", "低"),
                           "fixable": r.get("fix") is not None,
                           "languages": r.get("languages", []),
                           "description": r.get("description", "")}
                          for r in BUILTIN_RULES],
        "risk_policy": "fix-dry 仅在内置规则白名单上执行；产物过五道闸",
    }
    out_dir = Path(argv.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "astgrep-matrix.json"
    path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2),
                    encoding="utf-8", newline="\n")
    _emit({"ok": True, "matrix_path": str(path),
           "total_rules": matrix["total_rules"],
           "fixable_rules": matrix["fixable_rules"],
           "safe_fixable_rules": matrix["safe_fixable_rules"]})
    return 0


def cmd_clean_fp(argv):
    corpus = Path(argv.corpus)
    if not corpus.is_dir():
        _emit({"ok": False, "error": "语料目录不存在: %s" % corpus})
        return 2
    if not _astgrep_available():
        _emit({"ok": False, "error": "ast-grep-py 不可用"})
        return 1
    total, by_code, files = 0, {}, 0
    exts = set()
    for exts_list in LANG_EXT.values():
        exts.update(exts_list)
    for p in sorted(corpus.rglob("*")):
        if p.suffix.lower() not in exts:
            continue
        files += 1
        lang = _infer_lang(p)
        if not lang:
            continue
        source = p.read_text(encoding="utf-8", errors="replace")
        rc, items, _ = _run_astgrep(_SCAN_SCRIPT, source, lang, BUILTIN_RULES)
        if rc != 0 or items is None:
            continue
        total += len(items)
        for i in items:
            code = i["rule_id"]
            by_code[code] = by_code.get(code, 0) + 1
    _emit({"ok": True, "engine": "astgrep",
           "files": files, "findings": total,
           "by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
           "note": "内置规则在干净语料的命中=引擎启用分级依据；"
                   "命中>0 的码不进评审管线，只进修复链（经五道闸）"})
    return 0


# -- 库函数（供修复链 import，与 ruff_fix_text/ruff_scan_codes 同形状）--

def astgrep_fix_text(text, select, lang=None):
    """库函数：在临时副本上跑 ast-grep 重写，返回修复后文本；失败返回 None。

    与 ruff_fix_text 同形状：text + select(逗号分隔规则ID) → fixed text。
    lang 缺省时从 select 对应规则的语言推断（取第一个匹配规则的第一个语言）。
    """
    rules = BUILTIN_RULES
    if select:
        ids = select.split(",")
        rules = [r for r in BUILTIN_RULES if r["id"] in ids]
    if not lang:
        for r in rules:
            if r.get("fix") is not None and r.get("languages"):
                lang = r["languages"][0]
                break
    if not lang:
        return None
    rc, data, _ = _run_astgrep(_FIX_SCRIPT, text, lang, rules)
    if rc != 0 or data is None:
        return None
    fixed = data.get("fixed", text)
    if not isinstance(fixed, str):
        return None
    return fixed


def astgrep_scan_codes(path, select=""):
    """库函数：返回 {"codes": 去重码列表, "count": 诊断条数}；失败返回 None。

    以 .venv 子进程调用 ast-grep-py，全局 Python import 安全。
    与 ruff_scan_codes 同形状。
    """
    rules = BUILTIN_RULES
    if select:
        rules = [r for r in rules if r["id"] in select.split(",")]
    lang = _infer_lang(path)
    if not lang:
        return None
    source = Path(path).read_text(encoding="utf-8", errors="replace")
    rc, items, _ = _run_astgrep(_SCAN_SCRIPT, source, lang, rules)
    if rc != 0 or items is None:
        return None
    return {"codes": sorted({i["rule_id"] for i in items}),
            "count": len(items)}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="ast-grep 引擎适配器")
    sub = parser.add_subparsers(dest="mode", required=True)
    p_scan = sub.add_parser("scan")
    p_scan.add_argument("--file", required=True)
    p_scan.add_argument("--rel", default="", help="仓库相对路径（findings.file）")
    p_scan.add_argument("--select", default="", help="规则集（逗号分隔 ID）")
    p_scan.add_argument("--lang", default="", help="覆盖语言推断")
    p_fix = sub.add_parser("fix-dry")
    p_fix.add_argument("--repo", required=True)
    p_fix.add_argument("--rel", required=True)
    p_fix.add_argument("--out", required=True)
    p_fix.add_argument("--select", default="")
    p_fix.add_argument("--lang", default="")
    p_mat = sub.add_parser("matrix")
    p_mat.add_argument("--out", required=True)
    p_cf = sub.add_parser("clean-fp")
    p_cf.add_argument("--corpus", required=True)
    argv = parser.parse_args()
    if argv.mode == "scan":
        return cmd_scan(argv)
    if argv.mode == "fix-dry":
        return cmd_fix_dry(argv)
    if argv.mode == "matrix":
        return cmd_matrix(argv)
    return cmd_clean_fp(argv)


if __name__ == "__main__":
    sys.exit(main())
