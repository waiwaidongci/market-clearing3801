"""调账单口径：按结算日、校区和档口组，对最新复核应结额与财务已确认累计轧差开单。"""

from collections import defaultdict
from datetime import date
from src.constants.enums import Receipt


def valid_day(value):
    try:
        day = date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("结算日须为 YYYY-MM-DD") from None
    if day != value:
        raise ValueError("结算日须为 YYYY-MM-DD")
    return day


def payable_groups(result):
    """最新复核结果中各校区 × 档口组的应结额（分），取食堂核销账净额。"""
    for table in (result or {}).get("tables", []):
        keys = {column["key"] for column in table.get("columns", [])}
        if {"zone", "merchant_group", "canteen_cents"} <= keys:
            return {(row["zone"], row["merchant_group"]): row["canteen_cents"] for row in table["rows"]}
    raise ValueError("复核结果缺少校区 × 档口组勾稽表，无法开单")


def plan_lines(payable, existing):
    """把相关组拆成新调账行、暂缓组和已结平组。

    同组存在等回执的调账行时暂缓；复核缺组应结额按零计；调账额等于
    应结额减去财务已确认累计，负差照常开单，零差视为已结平。
    """
    pending = {(line.zone, line.merchant_group) for line in existing if line.state == Receipt.PENDING}
    confirmed = defaultdict(int)
    for line in existing:
        if line.state == Receipt.CONFIRMED:
            confirmed[(line.zone, line.merchant_group)] += line.delta_cents
    new_lines, held, settled = [], [], []
    for key in sorted(payable.keys() | confirmed.keys() | pending):
        zone, group = key
        if key in pending:
            held.append({"zone": zone, "merchant_group": group, "reason": "存在等回执的调账行"})
            continue
        expected = payable.get(key, 0)
        before = confirmed.get(key, 0)
        delta = expected - before
        if delta == 0:
            settled.append({"zone": zone, "merchant_group": group, "expected_cents": expected})
        else:
            new_lines.append({"zone": zone, "merchant_group": group, "expected_cents": expected,
                              "confirmed_before_cents": before, "delta_cents": delta})
    return new_lines, held, settled
