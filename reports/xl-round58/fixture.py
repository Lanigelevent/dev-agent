#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""round-58 XL 基准夹具生成器（工作区辅助，不入库）。

在 <dest> 下建一个 6 模块的小包 xlib 与 12 条 pytest 用例：初始
7 failed / 5 passed，修复面跨 5 个文件（parsers/validators/service/
report/__init__），core.py 为只读上下文。

用法：.venv/Scripts/python.exe reports/_work/xl58-fixture.py --dest <dir>
退出码：0=建成并 git 提交；2=目标已存在或 git 失败。
"""
import argparse
import subprocess
import sys
from pathlib import Path

FILES = {
    "xlib/__init__.py": '''"""xlib 公共入口。"""
from xlib.parsers import parse_amount
from xlib.report import render
from xlib.service import total
from xlib.validators import validate_amount


def parse_and_validate(text):
    """解析并校验一笔金额。"""
    value = parse_amount(text)
    return validate_amount(text)


__all__ = ["parse_amount", "validate_amount", "total", "render",
           "parse_and_validate"]
''',
    "xlib/core.py": '''"""金额基础设施：量化精度与四舍五入规则。"""
from decimal import Decimal, ROUND_HALF_UP

AMOUNT_QUANTUM = Decimal("0.01")


def as_money(value):
    """把 Decimal 量化为两位小数（四舍五入）。"""
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
''',
    "xlib/parsers.py": '''"""金额解析：支持千分位与首尾空白。"""
from decimal import Decimal, InvalidOperation


def parse_amount(text):
    """'1,234.50' → Decimal('1234.50')；非法输入抛 ValueError。"""
    cleaned = text.strip().replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError("无法解析金额: %r" % text)
''',
    "xlib/validators.py": '''"""发票金额校验。"""
from decimal import Decimal


def validate_amount(value):
    """拒绝负金额。"""
    if value < 0:
        raise ValueError("金额不能为负")
    return value
''',
    "xlib/service.py": '''"""发票汇总。"""
from decimal import Decimal


def total(invoices):
    """汇总发票金额。"""
    result = Decimal("0")
    for inv in invoices:
        result += inv["amount"]
    return result
''',
    "xlib/report.py": '''"""金额渲染：千分位两位小数。"""
from xlib.core import as_money


def render(value):
    """Decimal('1234.5') → '1,234.50'。"""
    return "{:,.2f}".format(as_money(value))
''',
    "tests/test_xlib.py": '''"""发票金额管线的业务口径（初始 7 失败 / 5 通过）。"""
from decimal import Decimal

import pytest

import xlib
from xlib.parsers import parse_amount
from xlib.report import render
from xlib.service import total
from xlib.validators import validate_amount


def test_parse_plain_amount():
    assert parse_amount(" 42 ") == Decimal("42")


def test_parse_thousands_separator():
    assert parse_amount("1,234.50") == Decimal("1234.50")


def test_parse_accounting_negative():
    assert parse_amount("(1,234.50)") == Decimal("-1234.50")


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_amount("not-money")


def test_validate_accepts_refund_amount():
    assert validate_amount(Decimal("-30.00")) == Decimal("-30.00")


def test_validate_rejects_three_decimals():
    with pytest.raises(ValueError):
        validate_amount(Decimal("10.005"))


def test_total_subtracts_refunds():
    invoices = [{"kind": "charge", "amount": Decimal("100.00")},
                {"kind": "refund", "amount": Decimal("30.00")}]
    assert total(invoices) == Decimal("70.00")


def test_total_sums_charges():
    invoices = [{"kind": "charge", "amount": Decimal("10.10")},
                {"kind": "charge", "amount": Decimal("0.90")}]
    assert total(invoices) == Decimal("11.00")


def test_render_negative_accounting_style():
    assert render(Decimal("-1234.5")) == "(1,234.50)"


def test_render_positive():
    assert render(Decimal("1234.5")) == "1,234.50"


def test_package_parse_and_validate():
    assert xlib.parse_and_validate("1,234.5") == Decimal("1234.5")


def test_package_rejects_three_decimals():
    with pytest.raises(ValueError):
        xlib.parse_and_validate("1.234")
''',
    "README.md": "# xlib\n\n发票金额解析、校验、汇总与渲染的小型金额管线。\n",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    args = ap.parse_args()
    dest = Path(args.dest)
    if dest.exists() and any(dest.iterdir()):
        print("目标非空：%s" % dest)
        return 2
    for rel, text in FILES.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    for argv in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=xl", "-c", "user.email=xl@x",
                  "commit", "-q", "-m", "xlib 初始导入"]):
        p = subprocess.run(["git", "-C", str(dest)] + argv, shell=False,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        if p.returncode != 0:
            print("git 失败：%s\n%s" % (argv, p.stdout + p.stderr))
            return 2
    print(str(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
