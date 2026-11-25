#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skill 触发词覆盖度静态体检（离线、无副作用；移植自 workbuddy-skills
skill-trigger-coverage/scripts/trigger_audit.py，适配本项目脚本规约）。

为什么需要它
------------
agent 选 skill 时**只读 frontmatter.description**；SKILL.md 正文里的
「典型触发」不参与匹配。所以「正文写了触发词但选路召不回」是真实且常见的
缺陷。本脚本离线量化：给定一组真实用户口语话术，逐条测能否命中该 skill
的 description。

判别力自检（--self-check，推荐每次体检前跑）
--------------------------------------------
静态匹配器可能「恒中」或「恒不中」，此时报告无效：
  1) MUST 组：description 里逐字抄写的触发词必须全命中——报盲区=规则过严
     （假红），结论不可信，先调规则不要照盲区改 description；
  2) SOFT 组：同义改写看真实召回，召回低才说明确有口语盲区。

跨 skill 误命中：子串型=真抢词（需收窄触发词）；字符覆盖型=匹配器假象。

用法示例:
    python trigger-audit.py --skills-root skills --probes skills/self-iteration/probes.json
    python trigger-audit.py --skills-root skills --probes <probes.json> --self-check --cross

probes.json 格式:
    {"skill 目录名": ["口语话术1", ...], ...}
    可选 "_must": {skill: ["必须命中的原触发词"]}、"_soft": {skill: ["同义改写"]}

退出码: 0 = 体检通过；1 = 存在盲区/自检未过/真抢词；2 = 参数或输入错误。
stdout 输出单个 JSON 文档（--format text 时输出人读报告）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

STOP_EN = {
    "skill", "use", "when", "user", "the", "and", "with", "for", "not", "are",
    "was", "were", "this", "that", "from", "into", "then", "than", "its", "it",
    "in", "on", "of", "to", "a", "an", "is", "be", "as", "at", "by", "can",
    "will",
}


def _emit(obj):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _param_error(error):
    _emit({"ok": False, "error": error})
    return 2


def frontmatter(path):
    """解析 frontmatter（CRLF 容错——^---\\n 在 CRLF 文件上失配是常见假红源）。"""
    with open(path, "rb") as f:
        txt = f.read().decode("utf-8", "replace")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", txt, re.S)
    if not m:
        return None
    fm = m.group(1)
    d = re.search(r"(?ms)^description\s*:\s*(.+?)(?=^\w+\s*:|\Z)", fm)
    v = re.search(r"(?m)^version\s*:\s*(\S+)", fm)
    nm = re.search(r"(?m)^name\s*:\s*(\S+)", fm)
    return {
        "description": d.group(1).strip().strip('"') if d else None,
        "version": v.group(1) if v else None,
        "name": nm.group(1).strip().strip('"') if nm else None,
    }


def extract_pool(description):
    """从 description 抽可匹配触发短语：引号/顿号内短句、逗号短句、英文术语。

    长分段再按括号/箭头/斜杠子切（MUST 自检教训：单字关键词嵌在超长分段里
    会被长度截断排除，造成匹配器假红）。
    """
    if not description:
        return []
    qs = re.findall(r"[\"“「『]([^\"”」』]{2,24})[\"”」』]", description)
    parts = re.split(r"[，,、；;。:：]", description)
    shorts = []
    for p in parts:
        for sub in re.split(r"[（()）→\-—/]", p):
            sub = sub.strip().strip("\"“”「」『』")
            if 2 <= len(sub) <= 24:
                shorts.append(sub)
    en = [w for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]{2,}\b", description)
          if w.lower() not in STOP_EN]
    seen, out = set(), []
    for x in qs + shorts + en:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def match(pool, probe, cover_thr=0.5):
    """返回 (命中词, 方式)。方式=子串(真召回) / 字符覆盖(可能假象)。"""
    for c in pool:
        if len(c) >= 2 and (c in probe or probe in c):
            return c, "子串"
    best, bs = None, 0.0
    for c in pool:
        if len(c) < 2:
            continue
        ov = len(set(c) & set(probe)) / len(set(c))
        if ov > bs:
            best, bs = c, ov
    return (best, "字符覆盖") if bs >= cover_thr else (None, "")


def cmd_audit(argv):
    probes_path = Path(argv.probes)
    if not probes_path.is_file():
        return _param_error("probes 文件不存在: %s" % probes_path)
    skills_root = Path(argv.skills_root)
    if not skills_root.is_dir():
        return _param_error("skills 根目录不存在: %s" % skills_root)
    raw = json.loads(probes_path.read_text(encoding="utf-8"))
    probes = {k: v for k, v in raw.items() if not k.startswith("_")}
    must = raw.get("_must", {})
    soft = raw.get("_soft", {})
    allow_cross = {(a.get("probe_skill"), a.get("hit_skill"))
                   for a in raw.get("_allow_cross", [])}
    pools, missing = {}, []
    for n in probes:
        p = skills_root / n / "SKILL.md"
        if not p.is_file():
            missing.append(n)
            continue
        fm = frontmatter(p)
        if not fm or not fm["description"]:
            missing.append(n + "(description 缺失)")
            continue
        pools[n] = extract_pool(fm["description"])
    if missing:
        return _param_error("以下 skill 无法读取: %s" % ", ".join(missing))

    # 自检
    trust = True
    must_result = {"hit": 0, "total": 0, "misses": []}
    if argv.self_check and must:
        for n, ps in must.items():
            if n not in pools:
                continue
            for p in ps:
                must_result["total"] += 1
                w, _ = match(pools[n], p)
                if w:
                    must_result["hit"] += 1
                else:
                    must_result["misses"].append({"skill": n, "probe": p})
        if must_result["total"] and must_result["hit"] != must_result["total"]:
            trust = False
    soft_result = {"hit": 0, "total": 0}
    if argv.self_check and soft:
        for n, ps in soft.items():
            if n not in pools:
                continue
            for p in ps:
                soft_result["total"] += 1
                if match(pools[n], p)[0]:
                    soft_result["hit"] += 1

    # 盲区
    blind = []
    for n, ps in probes.items():
        for p in ps:
            w, _how = match(pools[n], p)
            if not w:
                blind.append({"skill": n, "probe": p})

    # 跨 skill 误命中（子串型=真抢词；_allow_cross 豁免共词对并留理由）
    real_cross = []
    if argv.cross:
        for n, ps in probes.items():
            for p in ps:
                for o in pools:
                    if o == n or (n, o) in allow_cross:
                        continue
                    w, how = match(pools[o], p)
                    if w and how == "子串":
                        real_cross.append({"probe_skill": n, "probe": p,
                                           "hit_skill": o, "word": w})

    ok = (not blind) and trust and (not real_cross if argv.cross else True)
    result = {
        "ok": ok,
        "trust": trust,
        "pools": {n: len(pool) for n, pool in pools.items()},
        "self_check": {"must": must_result, "soft": soft_result},
        "blind_spots": blind,
        "blind_count": len(blind),
        "real_cross_hits": real_cross,
        "cross_count": len(real_cross),
        "note": "盲区数=0 且 MUST 全过" + ("且真抢词=0" if argv.cross else "")
                + " 才算通过；MUST 未过=匹配器假红，先调规则别改 description",
    }
    if argv.format == "text":
        lines = ["触发短语数: %s" % json.dumps(result["pools"], ensure_ascii=False),
                 "MUST: %d/%d" % (must_result["hit"], must_result["total"]),
                 "SOFT: %d/%d" % (soft_result["hit"], soft_result["total"]),
                 "盲区 %d: %s" % (len(blind), json.dumps(blind, ensure_ascii=False)),
                 "真抢词 %d: %s" % (len(real_cross),
                                    json.dumps(real_cross, ensure_ascii=False)),
                 "结论: %s" % ("通过" if ok else "需处理(信任=%s)" % trust)]
        print("\n".join(lines))
    else:
        _emit(result)
    return 0 if ok else 1


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Skill 触发词覆盖度静态体检")
    parser.add_argument("--skills-root", required=True, help="skills 根目录")
    parser.add_argument("--probes", required=True, help="probes.json 路径")
    parser.add_argument("--self-check", action="store_true",
                        help="跑判别力自检（MUST/SOFT 对照组）")
    parser.add_argument("--cross", action="store_true",
                        help="跨 skill 误命中诊断（子串型=真抢词）")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    argv = parser.parse_args()
    return cmd_audit(argv)


if __name__ == "__main__":
    sys.exit(main())
