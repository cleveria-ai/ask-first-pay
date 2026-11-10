"""The fictional business the demo plays: its name and the currency its deposits are held in.

Both come from the environment so a recording can name its own (fictional) clinic:
- ASK_FIRST_BUSINESS: the business name (default: an obviously fictional Latin American clinic);
- ASK_FIRST_CURRENCY: the ISO 4217 code of the deposit (default USD). It is the currency of the
  PayPal order itself, so the label on screen and the money PayPal holds never disagree.

Everything shown on screen or sent to PayPal as `brand_name` uses `display_name()`, which always
says "(fictional)": the demo never speaks for a real clinic.
"""
from __future__ import annotations

import os
import re

DEFAULT_BUSINESS = "Clínica Bahía Imaginaria"
DEFAULT_CURRENCY = "USD"
FICTIONAL = "(fictional)"
_MAX = 80


def business_name() -> str:
    """ASK_FIRST_BUSINESS, whitespace collapsed and capped; the default when unset or blank."""
    name = " ".join((os.environ.get("ASK_FIRST_BUSINESS") or "").split())[:_MAX]
    return name or DEFAULT_BUSINESS


def mark_fictional(name: str, limit: int | None = None) -> str:
    """`name` followed by "(fictional)" (once), cut so the result fits in `limit` characters
    with the marker kept: whatever source a name comes from, it never loses the marker."""
    name = " ".join(str(name).split())
    if FICTIONAL in name.lower():
        name = re.sub(r"\s*\(fictional\)", "", name, flags=re.I).strip()
    if limit is not None:
        name = name[:max(0, limit - len(FICTIONAL) - 1)].rstrip()
    return f"{name} {FICTIONAL}" if name else FICTIONAL


def display_name() -> str:
    """The name as it appears on screen: always marked as fictional."""
    return mark_fictional(business_name())


def currency() -> str:
    """ASK_FIRST_CURRENCY when it is a three-letter code, otherwise USD."""
    code = (os.environ.get("ASK_FIRST_CURRENCY") or "").strip().upper()
    return code if re.fullmatch(r"[A-Z]{3}", code) else DEFAULT_CURRENCY
