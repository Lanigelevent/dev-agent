#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PII 出站脱敏闸（阶段 5 批次二 M7，round-234；隐私三层之第①层）。

定位：文本出站前置闸——发往 LLM 端点/外部前的个人信息扫描。凭据形态归
secret-scan.py（7 规则），个人信息归本脚本（对标 privacy-filter 的
预过滤+上下文正则+校验兜底三层；presidio 引擎层引入与否见 D-054 待批）。

规则面（全部带校验位/结构校验降误报）：
- cn_id       中国居民身份证 18 位（GB 11643-1999 校验位验证，非法跳过）
- cn_phone    中国手机号 1[3-9] 位段（前后边界断言，不吃长数字段）
- email       标准邮箱形态
- bank_card   13-19 位银行卡（Luhn 校验验证，非法跳过）
- entropy     高熵可疑段（≥32 位混合大小写+数字的 base64 形态）标记为 suspicious

命中即脱敏：snippet 中命中段替换为 <pii:rule>（硬约束 5 同款占位形态）。

用法示例：
    py pii-scan.py scan --file <文本路径>                # 扫文件
    py pii-scan.py selftest                                # 内置反向样例自检（CI 用）
库函数 scan_text(text) 供调用方 import（出站前最后一道）。

退出码：0 = 干净（或 selftest 全过）；1 = 有 PII 命中（可处理：出站前脱敏）
        2 = 输入/环境错误（文件缺失、参数非法）。
stdout 只输出一个 JSON 文档，诊断走 stderr。
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

CN_ID = re.compile(r"(?<![0-9Xx])[1-9]\d{5}(?:19|20)\d{2}"
                   r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx](?![0-9Xx])")
CN_PHONE = re.compile(r"(?<![0-9])1[3-9]\d{9}(?![0-9])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BANK_CARD = re.compile(r"(?<![0-9])[3-6]\d{12,18}(?![0-9])")
ENTROPY = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{32,}={0,2}(?![A-Za-z0-9+/=])")

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"


def _cn_id_valid(num):
    if len(num) != 18 or not num[:17].isdigit():
        return False
    s = sum(int(b) * w for b, w in zip(num[:17], _ID_WEIGHTS))
    return _ID_CHECK[s % 11] == num[17].upper()


def _luhn_valid(digits):
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _shannon(text):
    if not text:
        return 0.0
    freq = {}
    for ch in text:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _entropy_suspect(seg):
    """熵兜底：≥32 位混合段且香农熵 ≥3.0 判可疑（降纯注释/长常量误报）。"""
    if not seg or len(seg) < 32:
        return False
    if not (re.search(r"[A-Z]", seg) and re.search(r"[a-z]", seg)
            and re.search(r"[0-9]", seg)):
        return False
    return _shannon(seg) >= 3.0


RULES = (
    ("cn_id", CN_ID, _cn_id_valid),
    ("cn_phone", CN_PHONE, None),
    ("email", EMAIL, None),
    ("bank_card", BANK_CARD, _luhn_valid),
)


def scan_text(text):
    """文本 → {hits: [...], scanned_chars}；命中段在 snippet 内脱敏为 <pii:rule>。"""
    hits = []
    text = str(text or "")
    for lineno, line in enumerate(text.splitlines(), 1):
        for rule, pat, checker in RULES:
            for m in pat.finditer(line):
                seg = m.group(0)
                if checker is not None and not checker(seg):
                    continue
                hits.append({"rule": rule, "line": lineno,
                             "snippet": line.replace(seg, "<pii:%s>" % rule)[:160],
                             "count": 1})
        for m in ENTROPY.finditer(line):
            if _entropy_suspect(m.group(0)):
                hits.append({"rule": "entropy", "line": lineno,
                             "snippet": line.replace(m.group(0), "<pii:entropy>")[:160],
                             "count": 1})
    return {"hits": hits, "scanned_chars": len(text)}


def _selftest():
    """内置反向样例自检（CI 门禁用）：合法样例必命中、非法校验位必不命中。"""
    cases = [
        ("11010519491231002X", "cn_id", True),
        ("110105194912310021", "cn_id", False),
        ("13812345678", "cn_phone", True),
        ("reviewer@example.com", "email", True),
        ("4111111111111111", "bank_card", True),
        ("4111111111111112", "bank_card", False),
    ]
    for raw, rule, expect in cases:
        r = scan_text(raw)
        got = any(h["rule"] == rule for h in r["hits"])
        if got != expect:
            sys.stderr.write("selftest FAIL: %s expect=%s got=%s\n" % (rule, expect, got))
            return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="PII 出站脱敏闸 scan/selftest")
    ap.add_argument("verb", choices=["scan", "selftest"])
    ap.add_argument("--file", default=None)
    args = ap.parse_args(argv)
    if args.verb == "selftest":
        rc = _selftest()
        sys.stdout.write(json.dumps(
            {"ok": rc == 0, "verb": "selftest"}, ensure_ascii=False) + "\n")
        return rc
    if not args.file:
        sys.stderr.write("scan 需 --file" + chr(10))
        return 2
    path = Path(args.file)
    if not path.is_file():
        sys.stderr.write("文件不存在: %s\n" % args.file)
        return 2
    text = path.read_text(encoding="utf-8", errors="replace")
    result = scan_text(text)
    ok = not result["hits"]
    sys.stdout.write(json.dumps(
        {"ok": ok, "verb": "scan", "file": str(path),
         "hit_count": len(result["hits"]), "hits": result["hits"][:50],
         "scanned_chars": result["scanned_chars"]},
        ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
