"""What the owner's phone shows: the approval cards and the "Today" panel.

Every number here comes from the signed mandates, the bookings and the hash-chained ledger, never
from model text. Times are the shop's local wall clock (`ASK_FIRST_TZ`, an IANA zone; the
server's zone otherwise), written the way people say them: "Mon 9:12 a.m.", "expires in 58 min".
"""
from __future__ import annotations

import ast
import os
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ask_first.keys import public_key_from_hex, verify_signature

from ..gate import minutes_left

MOVES_MONEY = ("capture_deposit", "refund_deposit")      # a void releases a hold: it moves nothing
KICKER = {"capture_deposit": "No-show", "void_deposit": "Cancellation", "refund_deposit": "Goodwill"}
PAYPAL_RESULT = {"capture_deposit": ("capture_id", "PayPal capture id"),
                 "refund_deposit": ("refund_id", "PayPal refund id"),
                 "void_deposit": ("authorization_id", "PayPal authorization")}


def local_zone() -> tzinfo | None:
    name = os.environ.get("ASK_FIRST_TZ", "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return None                                          # datetime.fromtimestamp: the server's zone


def _ampm(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d} {'a.m.' if dt.hour < 12 else 'p.m.'}"


def clock(ts: float) -> str:
    """A moment as a person says it: 'Mon 9:12 a.m.'."""
    dt = datetime.fromtimestamp(float(ts), local_zone())
    return f"{dt:%a} {_ampm(dt)}"


def slot_text(slot: str) -> str:
    """'2026-11-16 09:00' (the clinic's own wall clock) -> 'Mon 16 Nov, 9:00 a.m.'."""
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(slot or "")
    return f"{dt:%a} {dt.day} {dt:%b}, {_ampm(dt)}"


def money(x: float) -> str:
    return f"${float(x):,.2f}"


# ---- bookings ----------------------------------------------------------------------------------
def bookings(front) -> list[dict]:
    return [b for s in front.conversations for b in s.bookings.values()]


def booking_for(front, resource: str) -> dict | None:
    """The booking that owns a signed PayPal resource (authorization id for capture and void,
    capture id for refund). Looked up on the server: the card never repeats what the model said."""
    if not resource:
        return None
    return next((b for b in bookings(front) if resource in (b.get("authorization_id"), b.get("capture_id"))), None)


# ---- one approval card ---------------------------------------------------------------------------
def card(m: dict, booking: dict | None) -> dict:
    """The owner-facing words of one mandate, chosen by its SIGNED action and filled with its
    SIGNED cap; only the hold amount and the appointment come from the booking that owns it."""
    action, cap = m["action"], float(m["cap"])
    held = booking.get("deposit") if booking else None
    if action == "capture_deposit":
        headline, chip = f"Keep up to {money(cap)} of the held deposit", "Irreversible · needs your signature"
    elif action == "refund_deposit":
        headline, chip = f"Give back up to {money(cap)} of the captured deposit", "Irreversible · needs your signature"
    elif action == "void_deposit":
        # The cap a void carries (0.01) is symbolic: the engine needs a positive amount. It goes in
        # the details; the headline says what really happens to the money.
        headline = f"Moves $0.00 · releases the {money(held)} hold" if held else "Moves $0.00 · releases the hold"
        chip = "Releases the hold · needs your signature"
    else:
        headline, chip = action, "Needs your signature"
    who = ""
    if booking:
        name = str(booking.get("customer") or "").strip()
        when = slot_text(booking.get("slot", ""))
        who = f"{name} · {when}" if name and name.lower() != "customer" else f"Appointment {when}"
    cap_text = (f"USD {cap:.2f} (symbolic: a void moves no money, the engine needs an amount)"
                if action == "void_deposit" else f"USD {cap:.2f}")
    return {"kicker": KICKER.get(action, "Request"), "headline": headline, "chip": chip, "who": who,
            "cap_text": cap_text, "exp_left": minutes_left(m["exp"]), "exp_clock": clock(m["exp"]),
            "created_clock": clock(m["created"])}


def paypal_result(action: str, outcome: dict | None) -> dict | None:
    """The id PayPal returned for an executed mandate, read from the provider's answer."""
    if not isinstance(outcome, dict) or action not in PAYPAL_RESULT:
        return None
    key, label = PAYPAL_RESULT[action]
    if not outcome.get(key):
        return None
    return {"label": label, "id": str(outcome[key]), "status": str(outcome.get("status") or "")}


def paypal_text(found: dict | None) -> str:
    if not found:
        return ""
    return f"{found['label']} {found['id']}" + (f" ({found['status']})" if found.get("status") else "")


# ---- the Today panel -------------------------------------------------------------------------------
def _agent_reauthorizations(front) -> int:
    """refresh_hold calls that reached PayPal, counted from the results our own tool code wrote
    (never from the model's words). A call refused before PayPal ("error") does not count."""
    n = 0
    for s in front.conversations:
        names = {}
        for msg in s.messages:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "tool_use":
                    names[blk.get("id")] = blk.get("name")
                elif blk.get("type") == "tool_result" and names.get(blk.get("tool_use_id")) == "refresh_hold":
                    try:
                        out = ast.literal_eval(str(blk.get("content", "")))
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(out, dict) and ("refreshed" in out or "provider_error" in out):
                        n += 1
    return n


def _signed(row: dict, approved: dict, keys: list) -> bool:
    """Did the owner sign what this executed ledger row did? The approval must exist, its
    signature must verify over the stored mandate with a key this shop paired, and the row must
    stay inside it (same action, same PayPal resource, amount within the cap)."""
    a = approved.get(str(row.get("mandate_id", "")))
    if not a:
        return False
    m, sig = a.get("mandate") or {}, a.get("signature") or ""
    if not any(verify_signature(k, m, sig) for k in keys):
        return False
    try:
        within = float(row.get("amount", 0)) <= float(m.get("cap", 0)) + 1e-9
    except (TypeError, ValueError):
        return False
    return row.get("action") == m.get("action") and row.get("recipient") == m.get("recipient") and within


def today(demo) -> dict:
    """The owner's day of money, computed from bookings and the ledger."""
    led = demo.agent.view_ledger()
    entries = [e for e in led["entries"] if "_unreadable" not in e]
    unreadable = len(led["entries"]) - len(entries)
    keys = [demo.engine.person_pub]
    for hexkey in getattr(demo, "owner_keys", []):
        try:
            keys.append(public_key_from_hex(hexkey))
        except ValueError:
            continue
    approved = demo.engine.approved

    kept = given_back = released = unsigned = 0.0
    unsigned_rows = refused = failed = 0
    reasons: dict[str, int] = {}
    held_by_auth = {b.get("authorization_id"): float(b.get("deposit") or 0) for b in bookings(demo.front)}
    for e in entries:
        result, action = e.get("result"), e.get("action")
        if result == "executed":
            amount = float(e.get("amount") or 0)
            if not _signed(e, approved, keys):
                unsigned_rows += 1
                if action in MOVES_MONEY:
                    unsigned += amount
            if action == "capture_deposit":
                kept += amount
            elif action == "refund_deposit":
                given_back += amount
            elif action == "void_deposit":
                released += held_by_auth.get(e.get("recipient"), 0.0)
        elif result == "rejected":
            refused += 1
            reasons[e.get("reason") or "rejected"] = reasons.get(e.get("reason") or "rejected", 0) + 1
        elif result == "failed":
            failed += 1

    bs = bookings(demo.front)
    orders = sum(1 for b in bs if b.get("order_id"))
    holds = sum(1 for b in bs if b.get("authorization_id"))
    reauth = _agent_reauthorizations(demo.front)
    approvals, declines = len(approved), len(demo.declined)   # a decline is only possible while pending
    v = demo.ledger_rows()[1]                                        # includes the remembered head
    chain_ok = (v["ok"] or (v["empty"] and demo.ledger_head is None)) and unreadable == 0
    return {
        "bookings": len(bs),
        "orders": orders, "holds": holds, "reauthorizations": reauth,
        "agent_calls": orders + holds + reauth,
        "approvals": approvals, "declines": declines, "taps": approvals + declines,
        "kept": money(kept), "given_back": money(given_back), "released": money(released),
        "refused": refused, "failed": failed,
        "refused_reasons": ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in sorted(reasons.items())),
        "unsigned": money(unsigned), "unsigned_rows": unsigned_rows,
        "clean": unsigned_rows == 0 and chain_ok, "chain_ok": chain_ok, "rows": len(led["entries"]),
    }
