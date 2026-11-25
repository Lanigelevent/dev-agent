#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""运维口径：把台账里的「验收口径」逐条抽出来实跑（round-31 检查单第 8 项）。

为什么需要它：round-30 给 `--close` 加了「口径里的 unittest 命令必须可跑」的闸门，
但闸门只挡**新写入**，且判据是形状（含 `discover -s tests`）而不是真跑过。
形状对、实际跑不过（测试改名、脚本被删、夹具路径变了）的口径依旧躺在台账里当「已验证」——
这跟 round-30 那条坑本身是同一个病：**把可验证寄托给一次性的形状检查**。
本脚本把「可验证」变成可重复的动作：抽取 → 静态判定 → （`--run`）逐条实跑 → 非 0 即算违规。

抽取口径（判定规则先写死，再看真实台账的数字，不看数字改规则）：
- 启动器白名单：`.venv/.../python(.exe)`、`./gradlew`、`scripts/*.py`、`skills/**/*.py`、`grep -c`；
- 终止于**引号外**的句读（。；，、）、换行、`→`（结果箭头）或「空格 + 中日韩文字」（命令后面接着讲人话了）；引号内的括号 / 分号 / 中文属于命令正文；
- 含 `-m unittest` 的片段必须同时有 `discover` 与 `-s tests`（沿用 retro-ledger 的同一条口径）；
- 字面里带 `...` / `<` 占位的是**省略写法**，不是命令：只登记 `placeholder`，不实跑。

第二轮（真实台账上首跑后补严的四条——抽取器自己也是检查器，假阳性比漏报更有害）：
- **参数形状**：启动器之后必须出现「旗标 / 引号 / `=` / 带 `/` 的操作数」之一，否则就是叙述里
  顺带提到的脚本名（反例：`…retro-report.py main() 在写 report` 里的「retro-report.py main」）；
- **嵌套去重**：已被接受片段的内部不再二次抽取（反例：`grep -c '\.venv/Scripts/python …'` 的
  引号内部会再命中一次解释器，抽出一条尾巴带着单引号的畸形命令）；
- **`grep -c` 需要操作数**：模式之后必须还有文件参数（`shlex` ≥ 4 段），否则判 `incomplete`——
  少了文件名的 grep 会转去读 stdin，实跑既不报错也不证任何事；
- **执行侧兜底**：实跑时 `stdin=DEVNULL`，缺操作数的命令只会退出，不会挂住整轮。
- **自我递归闸**：口径里写着「再跑一遍本脚本」（含 markdown 反引号包裹的形态）判
  `self_reference`，只登记不执行——`--run` 会把它再抽出来跑，串成无限递归；
  跑过的数字要直接写进口径，不是写一句「你去跑一遍」。

第三轮（round-63 真实台账实踩）：**抽取器引号感知**——旧实现不辨引号内外，
结案口径里的 `python -c "…json.load(open('x'))…"` 在第一个 `(` 处被截断，
平衡引号被劈开、判成 `unrunnable_shape`（形状对了字面却不可跑，属假阳性）。
现在引号内只认换行断句；未闭合的引号仍扫到末尾，由 shlex 判 `unrunnable_shape`，
不会因为「宽松」而放行坏形状。

执行侧（第一次 `--run` 就抓出三条自己的 bug，都已在数字前写死成规则）：
- 前导 `KEY=VALUE` 是**环境前缀**，要拆进 env，整串当 argv[0] 会 WinError 2；
- argv[0] 以 `.py` 结尾时 Windows 不认 shebang，改用本进程解释器执行并显式标
  `interpreter_injected`——口径写得不完整，但语义等价，照样算验过；
- **绝不全局反斜杠换正斜杠**：`grep -c '\.venv/…'` 的 `\.` 是正则转义，换成 `/` 后
  命令仍然「跑成功」但计数全 0——静默假阴性，比报错更坏。

结案口径三分类（round-33 检查单第 8 项）：已结案条目按 closure_note 分为
machine_checkable（抽得出可跑命令）/ human_conclusion（无命令但带复验条件 +
期限两类信号，人工结论型允许无命令）/ weak_closure（无命令且缺任一信号）。
判定规则写在 CONDITION_RE / DEADLINE_RE / CLOSURE_CLASS_RULE 常量里，先于真台账
数字定死；本轮三分类只登记摆比例，不设闸（一刀切会把时间性口径逼成假命令）。

缺省是 dry-run（只抽取与静态判定，绝不执行任何东西）；`--run` 才实跑。
违规判定：`unrunnable_shape` / `placeholder` / `incomplete` / `self_reference` / 实跑非 0 = 违规；
`closed` 但一条命令都没有的口径只登记 `no_command`（本轮不设闸，如实摆数字）。
命令起不来（`OSError`，例如本机 PATH 里没有 grep）记 `environment`，**不算代码回归也不算违规**。
用法：
    py scripts/verify-closure-commands.py                 # 报表（不执行）
    py scripts/verify-closure-commands.py --run           # 逐条实跑（cwd = 仓库根）
    py scripts/verify-closure-commands.py --ledger <路径> --root <路径> --json

退出码：0=无违规；1=有违规（形状不可跑 / 实跑非 0 / 实跑超时）；2=输入错误。
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# 启动器白名单：只认真正「会被复制执行」的形态，避免把中文叙述里的词当成命令。
LAUNCHER_RE = re.compile(
    r"(?:(?:PYTHONIOENCODING|JAVA_HOME|LANG|LC_ALL)=\S+\s+)*"          # 环境变量前缀
    r"("
    r"\.venv[/\\][A-Za-z0-9_.\-]+[/\\]python(?:\.exe)?"                # 本仓约定的解释器
    r"|\B\.venv/Scripts/python\.exe"
    r"|\./gradlew(?!\w)"
    r"|\bgradlew\b"
    r"|\bscripts/[A-Za-z0-9_.\-]+\.py"
    r"|\bskills/[A-Za-z0-9_./\-]+\.py"
    r"|\bgrep\s+-c"
    r")"
)
# 终止集：句读 + 箭头 + 半/全角括号 + 「空格后跟 CJK」。
STOP_PUNCT = "。；，、：！？「」『』（）()【】\n\r\t"
CJK_RE = re.compile(r"\s(?=[\u3040-\u30ff\u4e00-\u9fff\u3000-\u303f])")
PLACEHOLDER_RE = re.compile(r"\.\.\.|…|<[^>\n]{1,40}>")
UNITTEST_RE = re.compile(r"-m\s+unittest\b")
GREP_RE = re.compile(r"^grep\s+-c\b")
# 结案口径分类（round-33 检查单第 8 项；判定规则先于真台账数字写死，不看比例改规则）：
# 已结案且抽不出可跑命令的口径——同时带「复验条件」与「期限/复查点」信号算
# human_conclusion（人工结论型，允许无命令）；缺任一信号算 weak_closure（薄弱）。
CONDITION_RE = re.compile(r"复验|复查|复跑|复测|观察|若再|再出现|复发|连续|未再|保持一致|退化|回潮"
                          r"|零重现|无重现|未复现|未再出现")  # 「零重现」族：时间性口径的已观测证据
DEADLINE_RE = re.compile(r"(?:\d+\s*|一|二|两|三|四|五|六|七|八|九|十)(?:轮|次|天|周|个月|月)"
                         r"|期限|到期|之前|以内|月底|周末")
CLOSURE_CLASS_RULE = ("machine_checkable=有可跑命令 / human_conclusion=无命令但带复验条件+期限 / "
                      "weak_closure=无命令且缺任一信号（本轮只登记不设闸）")
# 本脚本自己的文件名：出现在口径里就是「递归指令」，只登记不执行。
SELF_SCRIPT_RE = re.compile(r"verify-closure-commands\.py")
# 散文钉法识别（round-34，weak_closure 消化）：`tests/test_x.py::test_y` 形状的
# 引用可以机械合成唯一规范命令——discover + -p + -k（与检查单第 10 条同源：
# 不许写成 `-m unittest tests.test_x`，模块互 import 会 ModuleNotFoundError）。
PROSE_TEST_REF_RE = re.compile(
    r"tests/(test_[A-Za-z0-9_]+\.py)::(test_[A-Za-z0-9_]+)")
PROSE_REF_RULE = ("tests/test_x.py::test_y 散文引用 → 合成 "
                  ".venv/Scripts/python -m unittest discover -s tests -p test_x.py -k test_y"
                  "（derived_from=prose_test_ref；--run 时真跑）")
# 参数形状：旗标（` -x`/`--x`）、引号、`=`、或带 `/` 的操作数——至少得有一个，
# 否则「启动器 + 一个散文词」不算口径（见 docstring 第二轮第 1 条）。
ARG_HINT_RE = re.compile(r"(?:^|\s)-\S|['\"]|=|/")

DEFAULT_LEDGER = "retro/pitfalls.json"
RUN_TIMEOUT_SECONDS = 180


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _is_cjk(ch):
    code = ord(ch)
    return (0x3000 <= code <= 0x303F or 0x3040 <= code <= 0x30FF
            or 0x4E00 <= code <= 0x9FFF or 0xFF00 <= code <= 0xFFEF)


def _cut_command(tail):
    """截出命令本体：引号外的句读 / 箭头 / CJK 即断句，引号内只认换行。

    round-63 修：旧实现不辨引号内外，`python -c "…open('x')…"` 在第一个
    `(` 处被截断，判成 unrunnable_shape（真实台账结案口径实踩）。引号内的
    括号、分号、CJK 都是命令正文；反斜杠按转义跳字。未闭合的引号一路扫到
    末尾，仍由 classify 的 shlex 判 unrunnable_shape，不会被误放行。
    """
    quote = None
    i = 0
    n = len(tail)
    while i < n:
        ch = tail[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            elif ch in "\n\r":
                return i
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch in STOP_PUNCT or ch == "→" or _is_cjk(ch):
            return i
        i += 1
    return n


def extract_commands(note):
    """从一条 closure_note 里抽出所有「会被复制执行」的命令片段。

    返回去重后的列表（保持出现顺序）。同一句话里重复抽到的同形命令只算一条——
    实跑两遍不会多证一件事，只会让报表难读。
    落在已接受片段内部的命中直接丢（引号里再嵌一条会抽出畸形尾巴）。
    """
    found = []
    accepted = []
    for m in LAUNCHER_RE.finditer(note):
        if any(s <= m.start() < e for s, e in accepted):
            continue
        tail = note[m.start():]
        end = _cut_command(tail)
        cmd = tail[:end].strip().rstrip("「」『』，。；、：").strip("`").strip()
        args = cmd[m.end() - m.start():].strip()
        if len(cmd) < len(m.group(0)) + 4 or " " not in cmd.strip():
            continue  # 只有启动器没有参数，不是可执行口径
        if not ARG_HINT_RE.search(args):
            continue  # 参数只是个散文词（`retro-report.py main`），是叙述不是命令
        accepted.append((m.start(), m.start() + end))
        if cmd not in found:
            found.append(cmd)
    return found


def classify(cmd):
    """静态判定：ok / unrunnable_shape / placeholder / incomplete / self_reference。"""
    if SELF_SCRIPT_RE.search(cmd):
        # 口径不能写成「再跑一遍本检查器」：--run 会把它又抽出来再跑一次，自我递归；
        # 真跑过的数字应当直接落在口径里（本脚本输出的 totals/violations 就是可抄的数）
        return "self_reference"
    if PLACEHOLDER_RE.search(cmd):
        return "placeholder"
    if _token_count(cmd) == 0:
        return "unrunnable_shape"  # 引号不闭合，shlex 都拆不开，谈不上执行
    if UNITTEST_RE.search(cmd) and not (re.search(r"\bdiscover\b", cmd) and re.search(r"-s\s+tests", cmd)):
        # 与 retro-ledger 的写入口闸门同一条口径（形状两侧不能各说各话）
        return "unrunnable_shape"
    if GREP_RE.match(cmd) and _token_count(cmd) < 4:
        return "incomplete"  # grep -c 缺文件操作数：会读 stdin，跑了也不证任何事
    return "ok"


def synthesize_from_prose(note):
    """散文里的 tests/...::test_ 引用 → 可跑命令列表（去重保序）。"""
    out = []
    for m in PROSE_TEST_REF_RE.finditer(note or ""):
        cmd = (".venv/Scripts/python -m unittest discover -s tests "
               "-p %s -k %s" % (m.group(1), m.group(2)))
        if cmd not in out:
            out.append(cmd)
    return out


def classify_closure(status, note, commands):
    """结案口径三分类（规则见 CLOSURE_CLASS_RULE；open 条目不参与分类）。"""
    if status != "closed":
        return None
    if commands:
        return "machine_checkable"
    text = note or ""
    if CONDITION_RE.search(text) and DEADLINE_RE.search(text):
        return "human_conclusion"
    return "weak_closure"


def _token_count(cmd):
    try:
        return len(shlex.split(cmd, posix=True))
    except ValueError:
        return 0


def _ledger_entries(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    pitfalls = data.get("pitfalls") if isinstance(data, dict) else data
    if not isinstance(pitfalls, list):
        raise ValueError("台账形状不对：既不是 {pitfalls:[...]} 也不是 [...]")
    return [p for p in pitfalls if isinstance(p, dict)]


ENV_PREFIX_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _argv_of(cmd):
    r"""拆成 (env 覆盖, argv, 标记)。

    - 前导 `KEY=VALUE` 是环境前缀，不是可执行文件名（整串塞给 CreateProcess 会 WinError 2）；
    - argv[0] 以 `.py` 结尾时，Windows 不会按 shebang 执行，改用本进程的解释器跑，
      并显式记 `interpreter_injected`——口径本身写得不完整，但语义等价，照样能验。
    反斜杠不做全局替换：`grep -c '\.venv/...'` 里的 `\.` 是正则转义，替换成正斜杠会静默失配。
    """
    tokens = shlex.split(cmd, posix=True)
    env = {}
    while tokens and ENV_PREFIX_RE.match(tokens[0]):
        key, _, value = tokens[0].partition("=")
        env[key] = value
        tokens = tokens[1:]
    injected = bool(tokens and tokens[0].lower().endswith(".py"))
    if injected:
        tokens = [sys.executable] + tokens
    return env, tokens, injected


def _run_command(cmd, root, timeout):
    env_over, argv, injected = _argv_of(cmd)
    if not argv:
        return {"rc": 2, "stdout_tail": "", "stderr_tail": "空命令", "injected": injected}
    env = None
    if env_over:
        env = dict(os.environ)
        env.update(env_over)
    try:
        p = subprocess.run(argv, cwd=str(root), shell=False, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, stdin=subprocess.DEVNULL, env=env)
        rc = p.returncode
        err = (p.stderr or p.stdout or "")
    except subprocess.TimeoutExpired:
        rc, err = 124, "实跑超时（%ss）" % timeout
    except OSError as exc:
        # 环境缺二进制（本机 PATH 没 grep 之类）——是环境问题，不是口径写错，也不是代码回归
        rc, err = 127, "命令起不来（环境）：%s" % exc
        return {"rc": rc, "stdout_tail": err[-200:], "stderr_tail": "",
                "env_missing": True, "injected": injected}
    return {"rc": rc, "stdout_tail": err[-200:], "stderr_tail": "", "injected": injected}


def main(argv=None):
    parser = argparse.ArgumentParser(description="逐条实跑台账里的验收口径")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="台账 JSON 路径（默认 %s）" % DEFAULT_LEDGER)
    parser.add_argument("--root", default=".", help="实跑时的工作目录（默认当前仓库根）")
    parser.add_argument("--run", action="store_true", help="真执行（缺省只做抽取与静态判定）")
    parser.add_argument("--timeout", type=int, default=RUN_TIMEOUT_SECONDS, help="单条命令超时秒数")
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON 输出（缺省即 JSON）")
    argv = parser.parse_args(argv)

    ledger = Path(argv.ledger)
    if not ledger.is_absolute():
        ledger = Path(argv.root).resolve() / ledger
    if not ledger.is_file():
        _emit({"ok": False, "error": "台账不存在：%s" % ledger})
        return 2
    root = Path(argv.root).resolve()
    if not root.is_dir():
        _emit({"ok": False, "error": "工作目录不存在：%s" % root})
        return 2

    try:
        entries = _ledger_entries(ledger)
    except (ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "error": "台账读不起来：%s" % exc})
        return 2

    records = []
    counters = {"closed": 0, "with_closure_note": 0, "with_command": 0,
                "no_command": 0, "commands": 0, "shape_ok": 0,
                "placeholder": 0, "unrunnable_shape": 0, "incomplete": 0,
                "self_reference": 0,
                "executed": 0, "passed": 0, "failed": 0,
                "env_missing": 0, "interpreter_injected": 0,
                "machine_checkable": 0, "human_conclusion": 0, "weak_closure": 0,
                "prose_derived": 0}
    violations = []
    environment = []
    unverifiable = []
    human_ids = []
    weak_ids = []
    for pitfall in entries:
        note = (pitfall.get("closure_note") or "").strip()
        status = pitfall.get("status") or "open"
        if status == "closed":
            counters["closed"] += 1
        if not note:
            records.append({"id": pitfall.get("id"), "status": status, "commands": []})
            continue
        counters["with_closure_note"] += 1
        commands = extract_commands(note)
        derived = []
        if not commands:
            derived = synthesize_from_prose(note)
            commands = derived
        if not commands:
            counters["no_command"] += 1
            cls = classify_closure(status, note, commands)
            if cls:
                counters[cls] += 1
            if status == "closed":
                unverifiable.append(pitfall.get("id"))
                (human_ids if cls == "human_conclusion" else weak_ids).append(
                    pitfall.get("id"))
            records.append({"id": pitfall.get("id"), "status": status,
                            "closure_class": cls, "commands": []})
            continue
        counters["with_command"] += 1
        cls = classify_closure(status, note, commands)
        if cls:
            counters[cls] += 1
        row = {"id": pitfall.get("id"), "status": status,
               "closure_class": cls, "commands": []}
        for cmd in commands:
            kind = classify(cmd)
            counters["commands"] += 1
            counters["shape_ok" if kind == "ok" else kind] += 1
            if derived:
                counters["prose_derived"] += 1
            item = {"command": cmd, "shape": kind}
            if derived:
                item["derived_from"] = "prose_test_ref"
            if kind == "ok" and argv.run:
                result = _run_command(cmd, root, argv.timeout)
                item["rc"] = result["rc"]
                item["output_tail"] = result["stdout_tail"]
                if result.get("injected"):
                    counters["interpreter_injected"] += 1
                    item["interpreter_injected"] = True
                if result.get("env_missing"):
                    counters["env_missing"] += 1
                    environment.append({"id": pitfall.get("id"), "command": cmd,
                                        "note": result["stdout_tail"]})
                else:
                    counters["executed"] += 1
                    if result["rc"] == 0:
                        counters["passed"] += 1
                    else:
                        counters["failed"] += 1
                        violations.append({"id": pitfall.get("id"), "command": cmd,
                                           "reason": "实跑退出码 %s" % result["rc"],
                                           "output_tail": result["stdout_tail"]})
            elif kind == "ok":
                pass  # dry-run：形状对，等 --run
            else:
                violations.append({"id": pitfall.get("id"), "command": cmd, "reason": kind})
            row["commands"].append(item)
        records.append(row)

    ok = not violations
    _emit({
        "ok": ok,
        "ledger": str(ledger),
        "root": str(root),
        "mode": "run" if argv.run else "dry-run",
        "totals": counters,
        "records": records,
        "violations": violations,
        "environment": environment,
        "no_command_closed_ids": unverifiable,
        "closure_class_rule": CLOSURE_CLASS_RULE,
        "prose_ref_rule": PROSE_REF_RULE,
        "human_conclusion_ids": human_ids,
        "weak_closure_ids": weak_ids,
        "hint": _hint(counters, violations, argv.run, len(unverifiable)),
    })
    return 0 if ok else 1


def _hint(counters, violations, did_run, no_command_closed):
    if violations:
        return ("以下口径复现不了，要么改回真跑过的形态、要么重开这条坑：%d 条"
                "（缺省 dry-run 不执行；加 --run 才实跑）" % len(violations))
    if not did_run:
        return "静态判定全过；实跑请加 --run"
    return ("实跑 %d 条全部退出码 0" % counters["executed"]) + (
        "；另有 %d 条已结案口径里没有可复制的命令（本轮只登记不判违规；"
        "其中 human_conclusion / weak_closure 见对应名单）" % no_command_closed
        if no_command_closed else "")


if __name__ == "__main__":
    sys.exit(main())
