"""Prices and the room's budget.

The plugin never converts currencies, never estimates a price and never stops
anyone spending: it parses what a page printed or the user typed, adds up in
integer minor units, and reports. Standard library only.
"""

from __future__ import annotations

import math
import re
from typing import Any

MAX_AMOUNT = 10_000_000.0
SYMBOLS = {"US$": "USD", "CA$": "CAD", "C$": "CAD", "A$": "AUD", "AU$": "AUD", "NZ$": "NZD", "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
_CODE = re.compile(r"(?<![A-Za-z])([A-Z]{3})(?![A-Za-z])")
_NUMBER = re.compile(r"\d[\d.,   ']*\d|\d")
_KNOWN_CODES = {"USD", "EUR", "GBP", "CAD", "AUD", "NZD", "JPY", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK", "MXN", "BRL", "INR", "SGD", "HKD", "CNY", "KRW", "ZAR", "AED"}


def _to_float(token: str) -> float | None:
    t = re.sub(r"[   ']", "", token)
    if "." in t and "," in t:
        dec = "." if t.rfind(".") > t.rfind(",") else ","
        t = t.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        head, _, tail = t.rpartition(sep)
        # "1,899" / "1.899" / "12,345,678": groups of three are thousands; anything else is a decimal mark
        if t.count(sep) > 1 or (len(tail) == 3 and head and head != "0"):
            t = t.replace(sep, "")
        else:
            t = head + "." + tail
    try:
        return float(t)
    except ValueError:
        return None


def currency_code(value: Any) -> str | None:
    """'usd', 'USD', '$', '€' -> 'USD', 'USD', 'USD', 'EUR'. None when unknown."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v in SYMBOLS:
        return SYMBOLS[v]
    v = v.upper()
    return v if re.fullmatch(r"[A-Z]{3}", v) else None


def parse_price(value: Any, default_currency: str | None = None) -> tuple[float, str | None] | None:
    """(amount, currency or None) from a number or a printed price. None when there is
    no usable amount. A range or 'from …' gives the first amount."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount, currency = float(value), None
    elif isinstance(value, str):
        currency, marks = None, []
        for mm in _CODE.finditer(value.upper()):
            if mm.group(1) in _KNOWN_CODES:
                currency = currency or mm.group(1)
                marks.append(mm.span())
        for sym in sorted(SYMBOLS, key=len, reverse=True):
            at = value.find(sym)
            if at >= 0:
                currency = currency or SYMBOLS[sym]
                marks.append((at, at + len(sym)))
                break
        numbers = list(_NUMBER.finditer(value))
        if not numbers:
            return None
        # "2 seats, $499": the amount is the number that touches the currency mark
        near = [n for n in numbers if any(abs(n.start() - e) <= 2 or abs(s0 - n.end()) <= 2 for s0, e in marks)]
        got = _to_float((near or numbers)[0].group(0))
        if got is None:
            return None
        amount = got
    else:
        return None
    if not math.isfinite(amount) or amount <= 0 or amount > MAX_AMOUNT:
        return None
    return round(amount, 2), currency or currency_code(default_currency)


def format_money(amount: float, currency: str | None) -> str:
    cents = round(float(amount) * 100)
    body = f"{cents / 100:,.2f}"
    if body.endswith(".00"):
        body = body[:-3]
    return f"{currency} {body}" if currency else body


def _cents(v: float) -> int:
    return round(float(v) * 100)


def product_price(product: dict | None, default_currency: str | None = None) -> tuple[float, str | None] | None:
    """The price recorded on a product: the parsed fields if present, else the printed text."""
    if not isinstance(product, dict):
        return None
    amount = product.get("price_amount")
    if isinstance(amount, (int, float)) and not isinstance(amount, bool) and math.isfinite(amount) and amount > 0:
        return round(float(amount), 2), currency_code(product.get("price_currency")) or currency_code(default_currency)
    return parse_price(product.get("price"), default_currency)


def budget_status(scene: dict) -> dict | None:
    """Where the room stands against its budget. None when no budget is set."""
    b = scene.get("budget")
    if not isinstance(b, dict) or not isinstance(b.get("limit"), (int, float)):
        return None
    cur = currency_code(b.get("currency"))
    limit = _cents(b["limit"])
    reserve = max(0, min(_cents(b.get("reserve") or 0), limit))
    items, unpriced, other = [], [], []
    spent = 0
    for obj in scene.get("objects", []):
        product = obj.get("product")
        if not isinstance(product, dict):
            continue
        price = product_price(product)
        if price is None:
            unpriced.append(obj["id"])
            continue
        amount, pcur = price
        if cur and pcur and pcur != cur:
            other.append({"id": obj["id"], "name": obj.get("name"), "amount": amount, "currency": pcur})
            continue
        spent += _cents(amount)
        item = {"id": obj["id"], "name": obj.get("name"), "amount": amount, "currency": pcur or cur, "url": product.get("url")}
        if cur and not pcur:
            item["currency_assumed"] = True
        items.append(item)
    spendable = limit - reserve
    out = {
        "limit": limit / 100,
        "currency": cur,
        "reserve": reserve / 100,
        "spendable": spendable / 100,
        "spent": spent / 100,
        "remaining": (limit - spent) / 100,
        "remaining_spendable": (spendable - spent) / 100,
        "over_limit": spent > limit,
        "uses_reserve": reserve > 0 and spendable < spent <= limit,
        "items": items,
        "unpriced": unpriced,
        "other_currency": other,
    }
    left = limit - spent
    text = f"Budget {format_money(limit / 100, cur)} · spent {format_money(spent / 100, cur)} · "
    text += f"{format_money(left / 100, cur)} left" if left >= 0 else f"{format_money(-left / 100, cur)} over"
    if reserve:
        text += f" ({format_money(reserve / 100, cur)} kept back)"
    if unpriced:
        text += f" · {len(unpriced)} without a price, not counted"
    if other:
        text += f" · {len(other)} in another currency, not counted"
    out["text"] = text
    return out


def budget_note(status: dict | None, price: tuple[float, str | None] | None, has_product: bool = True) -> str | None:
    """One plain sentence for the agent after a product was added, or None."""
    if not status or not has_product:
        return None
    cur = status["currency"]
    if price is None:
        return "No readable price: not counted in the total. Ask the user for the price."
    if cur and price[1] and price[1] != cur:
        return f"Priced in {price[1]}; the budget is in {cur}. Not counted: the plugin does not convert currencies."
    if status["over_limit"]:
        return (
            f"This takes the room to {format_money(status['spent'], cur)}: {format_money(-status['remaining'], cur)} over the "
            f"{format_money(status['limit'], cur)} budget. Tell the user and ask whether to keep it, swap it or raise the budget."
        )
    if status["uses_reserve"]:
        return (
            f"Inside the budget, but this uses {format_money(-status['remaining_spendable'], cur)} of the "
            f"{format_money(status['reserve'], cur)} the user wanted kept back. Tell the user."
        )
    return None
