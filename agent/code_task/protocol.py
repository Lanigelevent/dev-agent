#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt 装配（动作面/阶段声明）与宿主协议解析、stdout 输出帧。

库模块（被 agent/code-task.py 调用）；无独立退出码。
"""
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

import json
import re


SYSTEM_PROMPT = (
    "你是编码智能体的决策核心，只输出 JSON。可选动作："
    '{"action":"read","files":["相对路径",...]}（先读文件再动手；'
    '深文件用 路径:起-止 行区间或 路径#符号 锚定，如 "src/a.py:195-330"'
    ' 或 "src/a.py#Builder"，逐行带行号，单段上限 400 行，缺省取窗只覆盖'
    '文件头部）；'
    '{"action":"list","path":"目录","depth":2}（看目录结构；限深 3 层、'
    '最多 200 项，越界路径会被拒绝；不知道文件在哪个子目录时先用它）；'
    '{"action":"search","query":"字符串","glob":"*.py"}（按字面子串全仓搜索，'
    '不区分大小写；返回 路径:行号: 行内容，最多 40 处，按「定义 > 引用 > '
    '注释」与候选文件路径距离排序。不知道目标文件在哪、要找某个符号/报错'
    '文本的引用点时先用它；glob 可省）；'
    '{"action":"edit","edits":[{"path":"相对路径","search":"精确原文",'
    '"replace":"替换文本"},...],"summary":"一句话说明"}（SEARCH 必须与'
    '**当前文件的实际内容**逐字一致且全文件唯一——不得拿上一版补丁的代码'
    '当 SEARCH，工作区保留此前已应用的编辑（本轮校验未过的编辑会自动回滚）；'
    '新建文件把 search 留空且目标必须'
    '不存在——这是唯一允许空 SEARCH 的情形；edits 至少有一处实质改动，'
    'replace 中的注释与 docstring 一律用英文；改完的源码文件（Python/TS/'
    'Go）必须语法完整，括号/引号/缩进不闭合会被本地语法校验退回）；'
    '{"action":"done","summary":"结论"}'
    "（确认无需更多改动）。修复任务以仓库测试通过为完成标准。"
)


PROBE_CLAUSE = (
    '{"action":"probe","code":"一段 Python"}（在当前工作区跑行为探针，'
    "打印对象状态如 vars(obj) / 顶点数 / extent——报错行只给症状，状态类"
    "缺陷要把状态打出来才定位得到）；"
)


PHASE_SYSTEM = {
    "locate": ("\n本任务处于 locate（定位）阶段：动作面为只读"
               "（read/list/search/probe），完成必须输出 locate_done；"
               "edit 会被主循环拒绝。"),
    "fix": ("\n本任务处于 fix（修复）阶段：可编辑；仓库测试通过后自动交"
            "verify 子代理裁决，也可用 done 提前交。"),
    "verify": ("\n本任务处于 verify（验证）阶段：动作面为只读"
               "（read/list/search），完成必须输出 verdict；edit 会被拒绝。"),
}


def _system_prompt(allow_probe, phase=""):
    """按权限拼装动作面（探针动作只在显式开启时下发）。

    阶段四 4.1：--phases 模式追加当前角色的动作面声明；单循环模式
    （phase 为空）保持原文，prompt 幂等 id 不变。
    """
    if not allow_probe:
        base = SYSTEM_PROMPT
    else:
        head, tail = SYSTEM_PROMPT.split('{"action":"done"', 1)
        base = head + PROBE_CLAUSE + '{"action":"done"' + tail
    if phase in PHASE_SYSTEM:
        base += PHASE_SYSTEM[phase]
    return base


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _progress_frame(round_num, event, **kwargs):
    """向 stderr 输出单行 JSON 进度帧，不污染 stdout 主输出。"""
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    frame = {"round": round_num, "event": event}
    frame.update(kwargs)
    print(json.dumps(frame, ensure_ascii=False), file=sys.stderr)


def _parse_response(raw):
    """解析 LLM 响应为动作对象（容忍代码栅栏、前后杂讯与多对象输出）。

    round-77：openai 兼容端点（DeepSeek JSON 模式）偶发一次输出多个
    动作对象（先「思考草稿」后「最终决定」各一个），旧实现用贪婪
    re.search 整段抓取必然失配——改为逐对象 raw_decode，取最后一个
    成功解码的 dict（最终决定在后的模型行为占多数）。
    """
    cleaned = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(),
                     flags=re.M).strip()
    try:
        obj = json.loads(cleaned)
    except ValueError:
        obj = None
        dec = json.JSONDecoder()
        idx = 0
        last = None
        while True:
            brace = cleaned.find("{", idx)
            if brace < 0:
                break
            try:
                val, end = dec.raw_decode(cleaned, brace)
                if isinstance(val, dict):
                    last = val
                idx = end
            except ValueError:
                idx = brace + 1
        obj = last
    return obj if isinstance(obj, dict) else None


def _apply_protocol_notes(task, notes_path):
    """把协议提示附录文件内容追加到任务文本尾部（round-78 产品化）。

    round-77 D-046 实跑验证：对探索节奏偏慢的 openai 兼容端点
    （DeepSeek），在任务文本尾部附两臂等额的「预算压力 + 先编辑后
    探索 + 测试即完成标准」提示，可显著降低纯探索耗尽预算的形态。
    附录随任务文本进 state（--resume 天然持久化）；缺文件 code=2。
    """
    path = Path(notes_path)
    if not path.is_file():
        raise ValueError("protocol notes 文件不存在: %s" % notes_path)
    notes = path.read_text(encoding="utf-8").strip()
    if not notes:
        return task
    return task.rstrip() + "\n\n" + notes + "\n"
