#!/usr/bin/env python3
"""确定性硬规则扫描：38 条规则产出「已证事实」，命中密钥形态自动脱敏。

用途:
    主流程步骤 2。对 diff（新增行）或单个源文件应用 38 条硬规则：
    凭据 8 + 危险函数 15 + 语言 15。所有内容正则不依赖行首锚定（易错点 1），
    剥 diff 前缀时只保留 + 行（易错点 2），snippet 命中密钥形态一律 <redacted>。

    --file 模式对 Python 额外做两层精确化（防"代码 vs 数据"自指误报）：
    1. tokenize 数据区掩码：匹配起点落在字符串字面量/注释内的一律抑制
       （真实凭据赋值的键在代码区，不受影响）；
    2. AST 语义检查：lang-mutable-default / lang-is-literal-misuse /
       lang-closure-late-bind / lang-empty-catch / lang-resource-unclosed
       五条规则在文件模式下改用 ast 判定（同一 rule_id，更准，无缩进启发式）。

用法:
    git -C repo diff A..B > change.diff
    python deterministic-rules.py --diff-file change.diff
    python deterministic-rules.py --file svc/payment.py

退出码:
    0 = 扫描完成（有无发现不改变退出码）
    2 = 参数错误（缺输入或同时给了两种输入）
"""
import argparse
import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

SECRET_PATTERNS = [
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password|passwd|authorization)\s*\"?\s*[:=]\s*)([^\s,;#]{3,})"), r"\1<redacted>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<redacted>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"mysql://[^\s/:]+:[^@\s]+@"), "mysql://<redacted>@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "<redacted>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<redacted>"),
]


def redact(text):
    """密钥形态统一脱敏为 <redacted>。"""
    if not text:
        return text
    t = str(text)
    for pat, rep in SECRET_PATTERNS:
        t = pat.sub(rep, t)
    return t


HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_diff(text):
    """解析 unified diff，返回 [{"path": str, "added": [(new_lineno, line_text)]}]。

    易错点 2：- 行一律丢弃，只保留 + 行参与符号统计，避免计数翻倍。
    """
    files = []
    cur = None
    newln = 0
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].split("\t")[0].strip()
            if path.startswith('"') and path.endswith('"') and len(path) >= 2:
                path = path[1:-1]
            if path.startswith("b/"):
                path = path[2:]
            if path in ("", "/dev/null"):
                cur = None
            else:
                cur = {"path": path, "added": []}
                files.append(cur)
        elif raw.startswith("@@"):
            m = HUNK_RE.match(raw)
            if m and cur is not None:
                newln = int(m.group(2))
        elif raw.startswith("+") and cur is not None:
            cur["added"].append((newln, raw[1:]))
            newln += 1
        elif (raw.startswith(" ") or raw == "") and cur is not None:
            newln += 1
    return files


RULES = []
PY = {".py"}
GO = {".go"}
JS = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
CLANG = {".c", ".cc", ".cpp", ".h", ".hpp"}
JVM = {".java", ".cs"}


def _rule(rule_id, severity, reason, pattern=None, exts=None):
    RULES.append(
        {
            "id": rule_id,
            "severity": severity,
            "reason": reason,
            "pattern": re.compile(pattern, re.I) if pattern else None,
            "exts": sorted(exts) if exts else None,
        }
    )


# 凭据 8 条
_rule("cred-password", "高", "源码出现 password 赋值形态", r"(\bpassword\s*\"?\s*[:=]\s*)([^\s,;#]{3,})")
_rule("cred-api-key", "高", "源码出现 api_key 赋值形态", r"(\bapi[_-]?key\s*\"?\s*[:=]\s*)([^\s,;#]{3,})")
_rule("cred-secret", "高", "源码出现 secret 赋值形态", r"(\bsecret\s*\"?\s*[:=]\s*)([^\s,;#]{3,})")
_rule("cred-token", "高", "源码出现 token 赋值形态", r"(\btoken\s*\"?\s*[:=]\s*)([^\s,;#]{3,})")
_rule("cred-aws-akia", "高", "AWS AccessKey 形态", r"\bAKIA[0-9A-Z]{16}\b")
_rule("cred-private-key", "高", "私钥块形态", r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_rule("cred-db-uri", "高", "数据库连接串带明文口令", r"mysql://[^\s/:]+:[^@\s]+@")
_rule("cred-jwt", "高", "硬编码 JWT 形态", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")
# 危险函数 15 条
_rule("dang-eval", "高", "eval 动态求值", r"(?<![.\w])eval\s*\(")
_rule("dang-exec", "高", "exec 动态执行", r"(?<![.\w])exec\s*\(")
_rule("dang-shell-true", "高", "subprocess shell=True", r"shell\s*=\s*True\b")
_rule("dang-pickle-loads", "高", "pickle.loads 反序列化不可信数据", r"\bpickle\.loads\s*\(")
_rule("dang-yaml-load", "高", "yaml.load 未指定安全 Loader", r"\byaml\.load\s*\((?![^)]*Loader)")
_rule("dang-innerhtml", "高", "innerHTML 直赋存在 XSS 面", r"\binnerHTML\s*=[^=]")
_rule("dang-dangerously-set", "高", "React dangerouslySetInnerHTML", r"dangerouslySetInnerHTML")
_rule("dang-document-write", "高", "document.write 直写 DOM", r"\bdocument\.write\s*\(")
_rule("dang-os-system", "高", "os.system 执行 shell", r"\bos\.system\s*\(")
_rule("dang-runtime-exec", "高", "Java Runtime.exec 执行外部命令", r"\bRuntime\s*\.\s*(exec|getRuntime)", JVM)
_rule("dang-unserialize", "高", "PHP unserialize 反序列化", r"\bunserialize\s*\(", {".php"})
_rule("dang-system-call", "高", "C/PHP system() 执行 shell", r"(?<![.\w])system\s*\(", CLANG | {".php"})
_rule("dang-strcpy-family", "高", "strcpy/strcat/sprintf 无边界拷贝", r"\b(strcpy|strcat|sprintf)\s*\(", CLANG)
_rule("dang-gets", "高", "gets 无界读取", r"\bgets\s*\(", CLANG)
_rule("dang-weak-hash-password", "高", "口令使用 md5/sha1 弱散列", r"(?:\b(?:md5|sha1)\s*\([^)]{0,60}(?:password|passwd|pwd)|(?:password|passwd|pwd)[^\n]{0,60}\b(?:md5|sha1)\s*\()")
# 语言硬规则 15 条
_rule("lang-mutable-default", "中", "Python 可变默认参数", r"def\s+\w+\s*\([^)]*=\s*(\[\]|\{\}|set\(\))", PY)
_rule("lang-is-literal-misuse", "中", "is 用于字面量比较或 ==None", r"\bis\s+(?:\"[^\"]*\"|'[^']*'|\d+)|(?:==|!=)\s*None\b", PY)
_rule("lang-closure-late-bind", "中", "循环体内定义 lambda 存在闭包延迟绑定", None, PY)
_rule("lang-nil-map-write", "中", "向 nil map 写入", None, GO)
_rule("lang-unhandled-err", "中", "err 返回值未检查", None, GO)
_rule("lang-defer-in-loop", "中", "defer 出现在循环体内", None, GO)
_rule("lang-goroutine-leak", "中", "启动 goroutine 但全文件无取消/超时机制", None, GO)
_rule("lang-type-assert-no-ok", "中", "Go 类型断言未用 ok 形式", r"\.\(\s*[A-Za-z_][\w.*\[\]]*\s*\)(?!\s*,\s*ok)", GO)
_rule("lang-buffer-overflow", "中", "malloc 未配合 sizeof，存在越界/溢出风险", r"\bmalloc\s*\((?![^;]*sizeof)", CLANG)
_rule("lang-empty-catch", "中", "空 catch/except 吞异常", r"catch\s*\([^)]*\)\s*\{\s*\}|except[^:]*:\s*pass\b", PY | JS | JVM | {".php"})
_rule("lang-resource-unclosed", "中", "open() 打开但全文件无 with/close", None, PY)
_rule("lang-int-overflow-cast", "中", "乘法结果强转 int 存在溢出", r"\(\s*int\s*\)\s*[\w.]+\s*\*", JVM | CLANG)
_rule("lang-symlink-toctou", "中", "exists 检查后 open 同一路径存在 TOCTOU", None, PY)
_rule("lang-uninit-pointer", "中", "指针声明未初始化", r"\b(?:int|char|void|float|double|long)\s+\*\s*\w+\s*;", CLANG)
_rule("lang-lock-free-read", "中", "声明了锁但全文件无加锁调用", None, GO)

VALUE_WORDS = {"str", "int", "bool", "bytes", "object", "none", "null", "true", "false",
               "float", "list", "dict", "string", "optional", "user", "name", "id"}
SAFE_VALUE_RE = re.compile(
    r"os\.environ|getenv|get\w*\(|input\(|config|settings|request\.|params|fields|headers|"
    r"keyring|secret_manager|<redacted>|chr\(", re.I
)
VALUE_RULES = {"cred-password", "cred-api-key", "cred-secret", "cred-token"}
PLACEHOLDER_VALUES = {"x", "***", "<redacted>", "", "your_key_here", "changeme", "none",
                      "null", "xxx", "placeholder", "example", "dummy", "test", "redacted",
                      "your_api_key", "todo", "t", "f"}
VALUE_SHAPE_PATTERNS = [
    ("cred-api-key", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("cred-token", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
]
LONG_RANDOM_RE = re.compile(r"[\"']([A-Za-z0-9_\-]{16,})[\"']")
COMMENT_PREFIXES = ("#", "//", "*", "/*", "<!--")
AST_MANAGED = {"lang-mutable-default", "lang-is-literal-misuse", "lang-closure-late-bind",
               "lang-empty-catch", "lang-resource-unclosed"}


def _comment_positions(text):
    """py 文件模式：注释 token 覆盖的 (行号, 列) 集合；解析失败返回 None。"""
    positions = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type != tokenize.COMMENT:
                continue
            row0, col0 = tok.start
            row1, col1 = tok.end
            if row0 == row1:
                for col in range(col0, col1):
                    positions.add((row0, col))
            else:
                for row in range(row0, row1 + 1):
                    positions.add((row, 0))
    except (tokenize.TokenError, SyntaxError, ValueError, IndentationError):
        return None
    return positions


def _value_shape_scan(path, lines, comment_positions=None):
    """凭据「值形态」信号：不依赖键名（sk-/ghp_/长随机串）。

    注释区（py 文件模式经 tokenize 定位；diff 模式用行首前缀启发）不报；
    与键名命中同行时去重（键规则已覆盖该行）。
    """
    out = []
    rule_map = {r["id"]: r for r in RULES}
    emitted = set()
    for lineno, text in lines:
        stripped = text.strip()
        is_comment_line = stripped.startswith(COMMENT_PREFIXES)
        for rule_id, pat in VALUE_SHAPE_PATTERNS:
            m = pat.search(text)
            if not m:
                continue
            if is_comment_line or (comment_positions and (lineno, m.start()) in comment_positions):
                continue
            if lineno not in emitted:
                out.append(_finding(rule_map[rule_id], path, lineno, text))
                emitted.add(lineno)
        for m in LONG_RANDOM_RE.finditer(text):
            inner = m.group(1)
            if len(inner) < 16 or inner.lower() in PLACEHOLDER_VALUES:
                continue
            if not (re.search(r"[a-z]", inner) and re.search(r"[A-Z]", inner)
                    and re.search(r"\d", inner)):
                continue
            if is_comment_line or (comment_positions and (lineno, m.start()) in comment_positions):
                continue
            if lineno not in emitted:
                out.append(_finding(rule_map["cred-secret"], path, lineno, text))
                emitted.add(lineno)
            break
    return out


def _data_positions(text):
    """字符串字面量与注释覆盖的 (行号, 列) 集合；解析失败返回 None（退化为不抑制）。"""
    types = {tokenize.STRING, tokenize.COMMENT}
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
        t = getattr(tokenize, name, None)
        if t:
            types.add(t)
    positions = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in types:
                continue
            row0, col0 = tok.start
            row1, col1 = tok.end
            if row0 == row1:
                for col in range(col0, col1):
                    positions.add((row0, col))
            else:
                for row in range(row0, row1 + 1):
                    positions.add((row, 0))
    except (tokenize.TokenError, SyntaxError, ValueError, IndentationError):
        return None
    return positions


def _finding(rule, path, lineno, text):
    snippet = redact(text.strip()[:200])
    return {
        "rule_id": rule["id"],
        "severity": rule["severity"],
        "file": path,
        "line": lineno,
        "snippet": snippet,
        "reason": rule["reason"],
    }


def _line_scan(path, lines, ext, skip_ids=(), data_positions=None):
    out = []
    for rule in RULES:
        if rule["pattern"] is None or rule["id"] in skip_ids:
            continue
        if rule["exts"] and ext not in rule["exts"]:
            continue
        for lineno, text in lines:
            m = rule["pattern"].search(text)
            if not m:
                continue
            if data_positions is not None and (lineno, m.start()) in data_positions:
                continue
            if rule["id"] in VALUE_RULES:
                value = (m.group(2) or "").strip("\"'")
                if value.lower() in VALUE_WORDS or value.lower() in PLACEHOLDER_VALUES \
                        or set(value) <= {"*"} or SAFE_VALUE_RE.search(text):
                    continue
                if text[m.end():].lstrip().startswith("+"):
                    continue  # 拼接组装的值不是字面量泄露
            out.append(_finding(rule, path, lineno, text))
    return out


def _lambda_default_bound(text, loop_names):
    """行扫描近似：lambda 默认值引用循环变量且函数体不再用该变量 → 已绑定。"""
    m = re.search(r"\blambda\b(.*?):(.*)$", text)
    if not m:
        return False
    head, body = m.group(1), m.group(2)
    if "=" not in head:
        return False
    defaults = head.split("=", 1)[1]
    captured = set(re.findall(r"[A-Za-z_]\w*", defaults)) & set(loop_names)
    if not captured:
        return False
    body_names = set(re.findall(r"[A-Za-z_]\w*", body))
    return not (captured & body_names)


def _context_scan(path, lines, ext, skip_ids=()):
    out = []
    open_loops = []
    pending_exists = None
    all_text = "\n".join(t for _, t in lines)
    rule_map = {r["id"]: r for r in RULES}

    def emit(rule_id, lineno, text):
        if rule_id in skip_ids:
            return
        out.append(_finding(rule_map[rule_id], path, lineno, text))

    for lineno, text in lines:
        if not text.strip() or text.strip().startswith(("#", "//", "*", "/*")):
            continue
        indent = len(text) - len(text.lstrip())
        while open_loops and indent <= open_loops[-1][0]:
            open_loops.pop()
        m_loop = re.search(r"\b(?:for|while)\b([^:]*):", text)
        if m_loop:
            open_loops.append((indent, set(re.findall(r"[A-Za-z_]\w*",
                                                     m_loop.group(1)))))
            continue
        if ext == ".py":
            loop_names = set().union(*(names for _, names in open_loops)) \
                if open_loops else set()
            if re.search(r"\blambda\b", text) and open_loops \
                    and indent > open_loops[-1][0] \
                    and not _lambda_default_bound(text, loop_names):
                emit("lang-closure-late-bind", lineno, text)
            m = re.search(r"os\.path\.(?:exists|isfile|islink)\(\s*([\w.\"']+)\s*\)", text)
            if m:
                pending_exists = (m.group(1), lineno)
            elif pending_exists and re.search(r"\bopen\s*\(", text) and pending_exists[0] in text \
                    and lineno - pending_exists[1] <= 5:
                emit("lang-symlink-toctou", lineno, text)
                pending_exists = None
        if ext == ".go":
            if re.search(r"\bdefer\b", text) and open_loops and indent > open_loops[-1]:
                emit("lang-defer-in-loop", lineno, text)
            if re.search(r",\s*err\s*:?=", text):
                idx = [i for i, (ln, _) in enumerate(lines) if ln == lineno][0]
                lookahead = [t for _, t in lines[idx + 1: idx + 4] if t.strip()]
                if not any(re.search(r"\bif\s+err", t) for t in lookahead):
                    emit("lang-unhandled-err", lineno, text)
    if ext == ".go":
        if re.search(r"\bvar\s+\w+\s+map\[", all_text):
            count = 0
            for lineno, text in lines:
                if count >= 5:
                    break
                if re.search(r"\w+\[[^\]]+\]\s*=\s*[^=]", text):
                    emit("lang-nil-map-write", lineno, text)
                    count += 1
        if re.search(r"\bgo\s+(?:func\b|\w+\()", all_text) \
                and not re.search(r"context\.|\.Done\(\)|time\.(?:After|NewTicker|NewTimer)", all_text):
            for lineno, text in lines:
                if re.search(r"\bgo\s+(?:func\b|\w+\()", text):
                    emit("lang-goroutine-leak", lineno, text)
                    break
        if re.search(r"sync\.(?:R?WMutex|Mutex)", all_text) \
                and not re.search(r"\.(?:R?Lock|Unlock|RUnlock)\(", all_text):
            for lineno, text in lines:
                if re.search(r"sync\.(?:R?WMutex|Mutex)", text):
                    emit("lang-lock-free-read", lineno, text)
                    break
    if ext == ".py" and "lang-resource-unclosed" not in skip_ids \
            and re.search(r"=\s*open\s*\(", all_text) \
            and not re.search(r"with\s+open\s*\(", all_text) \
            and not re.search(r"\.close\s*\(", all_text):
        for lineno, text in lines:
            if re.search(r"=\s*open\s*\(", text):
                emit("lang-resource-unclosed", lineno, text)
                break
    return out


# ---- 污点流引擎（stdlib 数据流 lite：同文件内 source -> sink，无清洗点建模）----
# sources/sinks 经总监治理的 taint-config.json 配置化（缺省内置，坏配置回退内置）；
# 汇点条目数即输出 taint_rules 字段。本文件内置缺省：
TAINT_DEFAULT_SOURCES = ["environ", "argv", "stdin", "request", "input"]
TAINT_DEFAULT_SINKS = {
    "eval": "taint-eval",
    "exec": "taint-exec",
    "os.system": "taint-os-shell",
    "os.popen": "taint-os-shell",
}
_TAINT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "taint-config.json"


def _load_taint_config():
    sources, sinks = list(TAINT_DEFAULT_SOURCES), dict(TAINT_DEFAULT_SINKS)
    try:
        data = json.loads(_TAINT_CONFIG_PATH.read_text(encoding="utf-8"))
        if (isinstance(data.get("sources"), list)
                and all(isinstance(s, str) and s for s in data["sources"])
                and isinstance(data.get("sinks"), dict)
                and all(isinstance(k, str) and isinstance(v, str)
                        for k, v in data["sinks"].items())):
            sources, sinks = data["sources"], data["sinks"]
        else:
            sys.stderr.write("污点配置形态非法，回退内置缺省\n")
    except (OSError, ValueError) as exc:
        sys.stderr.write("污点配置不可读（%s），回退内置缺省\n" % exc)
    return set(sources), sinks


_TAINT_SOURCE_NAMES, TAINT_SINK_FUNCS = _load_taint_config()


def _call_fullname(call):
    """返回调用目标的可读点路径（如 os.system / eval）。"""
    parts = []
    node = call.func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_taint_source(node):
    """表达式是否触及不可信输入：input() 调用或 environ/argv/stdin/request 链。"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name) and sub.func.id in _TAINT_SOURCE_NAMES:
                return True
        if isinstance(sub, ast.Attribute) and sub.attr in _TAINT_SOURCE_NAMES:
            return True
        if isinstance(sub, ast.Name) and sub.id in _TAINT_SOURCE_NAMES:
            return True
    return False


def _is_taint_sink(call):
    """调用是否为污点汇点：动态求值 / 系统命令（os.system）。"""
    full = _call_fullname(call)
    return TAINT_SINK_FUNCS.get(full)


def _contains_name(node, names):
    return any(isinstance(sub, ast.Name) and sub.id in names for sub in ast.walk(node))


def _taint_findings(path, text, lines_by_no):
    """同文件直线传播：source 赋值 -> 变量 -> sink 实参（含 f-string/拼接）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    tainted = set()
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            targets = [node.target]
        for target in targets:
            if _is_taint_source(node.value):
                tainted.add(target.id)
            elif _contains_name(node.value, tainted):
                tainted.add(target.id)
    out = []
    seen = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        rule_id = _is_taint_sink(node)
        if rule_id is None:
            continue
        touched = any(_contains_name(a, tainted) for a in node.args)
        touched = touched or any(_contains_name(kw.value, tainted)
                                 for kw in node.keywords)
        if not touched or node.lineno in seen:
            continue
        seen.add(node.lineno)
        raw = lines_by_no.get(node.lineno, "")
        out.append({
            "rule_id": rule_id,
            "severity": "高",
            "file": path,
            "line": node.lineno,
            "snippet": redact(raw.strip())[:160],
            "reason": "污点流：不可信输入未经清洗抵达 %s" % _call_fullname(node),
        })
    return out


def _ast_findings(path, text):
    """Python 文件模式的五条 AST 语义检查（与正则版本同 rule_id，判定更准）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines()
    rule_map = {r["id"]: r for r in RULES}
    hits = {}
    opens = {}
    with_names = set()
    close_names = set()

    def add(rule_id, lineno):
        if lineno < 1 or lineno > len(lines):
            return
        key = (rule_id, lineno)
        if key in hits:
            return
        hits[key] = _finding(rule_map[rule_id], path, lineno, lines[lineno - 1])

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults) + \
                [d for d in node.args.kw_defaults if d is not None]
            if any(isinstance(d, (ast.List, ast.Dict, ast.Set))
                   or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                       and d.func.id == "set") for d in defaults):
                add("lang-mutable-default", node.lineno)
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                bad = (isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant)
                       and comp.value is not None) \
                    or (isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant)
                        and comp.value is None)
                if bad:
                    add("lang-is-literal-misuse", node.lineno)
                    break
        if isinstance(node, ast.ExceptHandler):
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                add("lang-empty-catch", node.body[0].lineno)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "open" \
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            opens.setdefault(node.targets[0].id, node.lineno)
        if isinstance(node, ast.With):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    with_names.add(item.optional_vars.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "close" and isinstance(node.func.value, ast.Name):
            close_names.add(node.func.value.id)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            loop_vars = set()
            if isinstance(node, (ast.For, ast.AsyncFor)):
                for t in ast.walk(node.target):
                    if isinstance(t, ast.Name):
                        loop_vars.add(t.id)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Lambda) and sub is not node:
                    params = {a.arg for a in list(sub.args.posonlyargs) + list(sub.args.args)
                              + list(sub.args.kwonlyargs)}
                    if sub.args.vararg:
                        params.add(sub.args.vararg.arg)
                    if sub.args.kwarg:
                        params.add(sub.args.kwarg.arg)
                    used = {n.id for n in ast.walk(sub) if isinstance(n, ast.Name)}
                    # 默认参数在定义时求值：lambda 默认值引用循环变量即为显式
                    # 绑定（如 lambda _m, p=str(path): p），不算延迟绑定
                    captured = set()
                    for d in list(sub.args.defaults) + \
                            [d for d in sub.args.kw_defaults if d is not None]:
                        captured |= {n.id for n in ast.walk(d)
                                     if isinstance(n, ast.Name)}
                    if (used & loop_vars) - params - captured:
                        add("lang-closure-late-bind", sub.body.lineno)
    for name, lineno in opens.items():
        if name not in with_names and name not in close_names:
            add("lang-resource-unclosed", lineno)
    return list(hits.values())


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _scan_one_file(p):
    """单文件扫描（单文件模式与批扫共用；D-049 C，round-92）。"""
    text = p.read_text(encoding="utf-8", errors="replace")
    lines = [(i, l) for i, l in enumerate(text.splitlines(), 1)]
    ext = p.suffix.lower()
    findings = []
    if ext == ".py":
        data_positions = _data_positions(text)
        findings.extend(_line_scan(str(p), lines, ext, AST_MANAGED, data_positions))
        findings.extend(_context_scan(str(p), lines, ext, AST_MANAGED))
        findings.extend(_ast_findings(str(p), text))
        findings.extend(_taint_findings(str(p), text, dict(lines)))
        entry = (str(p), lines, _comment_positions(text))
    else:
        findings.extend(_line_scan(str(p), lines, ext))
        findings.extend(_context_scan(str(p), lines, ext))
        entry = (str(p), lines, None)
    return findings, len(lines), entry


def main():
    parser = argparse.ArgumentParser(description="38 条确定性硬规则扫描")
    parser.add_argument("--diff-file", help="unified diff 文件")
    parser.add_argument("--file", help="源文件（可重复；多次即批扫，D-049 C）",
                        action="append")
    argv = parser.parse_args()
    if bool(argv.diff_file) == bool(argv.file):
        _emit({"ok": False, "error": "必须且只能给 --diff-file 或 --file 之一"})
        return 2
    findings = []
    scanned_lines = 0
    scanned = []
    if argv.diff_file:
        p = Path(argv.diff_file)
        if not p.is_file():
            _emit({"ok": False, "error": "diff 文件不存在: %s" % p})
            return 2
        targets = [(f["path"], f["added"])
                   for f in parse_diff(p.read_text(encoding="utf-8", errors="replace"))]
        for path, lines in targets:
            ext = Path(path).suffix.lower()
            scanned_lines += len(lines)
            findings.extend(_line_scan(path, lines, ext))
            findings.extend(_context_scan(path, lines, ext))
            scanned.append((path, lines, None))
    else:
        files = [Path(f) for f in argv.file]
        if len(files) == 1:
            p = files[0]
            if not p.is_file():
                _emit({"ok": False, "error": "源文件不存在: %s" % p})
                return 2
            f_findings, scanned_lines, entry = _scan_one_file(p)
            findings.extend(f_findings)
            scanned.append(entry)
        else:
            # 批扫（D-049 C，round-92）：逐文件走同一扫描路径，每文件一段。
            # 单文件模式输出保持字节级不变；批扫按文件归段，各自 rc/findings。
            results = []
            total_lines = 0
            for p in files:
                if not p.is_file():
                    results.append({"file": str(p), "rc": 2,
                                    "error": "源文件不存在: %s" % p})
                    continue
                f_findings, n_lines, entry = _scan_one_file(p)
                cred_spans = {(f["file"], f["line"]) for f in f_findings
                              if f["rule_id"].startswith("cred-")}
                for vf in _value_shape_scan(entry[0], entry[1], entry[2]):
                    if (vf["file"], vf["line"]) not in cred_spans:
                        f_findings.append(vf)
                order = {"高": 0, "中": 1, "低": 2}
                f_findings.sort(key=lambda f: (order.get(f["severity"], 3),
                                               f["file"], f["line"]))
                total_lines += n_lines
                results.append({"file": str(p), "rc": 0,
                                "findings": f_findings,
                                "scanned": {"files": 1, "lines": n_lines}})
            _emit({"ok": True, "batch": True, "results": results,
                   "scanned": {"files": len(files), "lines": total_lines}})
            return 0
    cred_spans = {(f["file"], f["line"]) for f in findings if f["rule_id"].startswith("cred-")}
    for path, lines, cpos in scanned:
        for vf in _value_shape_scan(path, lines, cpos):
            if (vf["file"], vf["line"]) not in cred_spans:
                findings.append(vf)
    order = {"高": 0, "中": 1, "低": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 3), f["file"], f["line"]))
    _emit(
        {
            "ok": True,
            "rule_count": len(RULES),
            "taint_rules": len(TAINT_SINK_FUNCS),
            "findings": findings,
            "scanned": {"files": 1 if argv.file else len(targets), "lines": scanned_lines},
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
