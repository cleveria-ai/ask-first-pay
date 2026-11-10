"""What the owner's phone shows: the approval cards and the "Today" panel.

Every number here comes from the signed mandates, the bookings and the hash-chained ledger, never
from model text. Times are the shop's local wall clock (`ASK_FIRST_TZ`, an IANA zone; the
server's zone otherwise), written the way people say them: "Mon 9:12 a.m.", "expires in 58 min".
"""
from __future__ import annotations

import ast
import os
import time
import math
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ask_first.keys import public_key_from_hex, verify_signature

from ..gate import minutes_left

RELEASES_ONLY = "void_deposit"     # a void releases a hold: its 0.01 cap is symbolic, it moves nothing
KICKER = {"capture_deposit": "No-show", "void_deposit": "Cancellation", "refund_deposit": "Goodwill"}
PAYPAL_RESULT = {"capture_deposit": ("capture_id", "PayPal capture id"),
                 "refund_deposit": ("refund_id", "PayPal refund id"),
                 "void_deposit": ("authorization_id", "PayPal authorization")}


def zone_status() -> tuple[tzinfo | None, str]:
    """(zone, note). ASK_FIRST_TZ names the shop's IANA zone; unset means the server's own zone.
    An unknown name is never guessed around: times switch to UTC and the note says so on screen."""
    name = os.environ.get("ASK_FIRST_TZ", "").strip()
    if not name:
        return None, ""                                  # datetime.fromtimestamp: the server's zone
    try:
        return ZoneInfo(name), ""
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc, f"Times in UTC: ASK_FIRST_TZ={name!r} is not a known time zone."


def local_zone() -> tzinfo | None:
    return zone_status()[0]


def local_day(ts: float):
    return datetime.fromtimestamp(float(ts), local_zone()).date()


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
        chip = "Needs your signature"
    else:
        headline, chip = action, "Needs your signature"
    who = ""
    if booking:
        name = str(booking.get("customer") or "").strip()
        when = slot_text(booking.get("slot", ""))
        placeholder = name.lower() in ("customer", "guest (no name given)")       # N10 stores this when unnamed
        who = f"{name} · {when}" if name and not placeholder else f"Appointment {when}"
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
def _booking_day(b: dict):
    """The local day a booking was made (`created_at`, UTC ISO, written by book_slot), or None
    for a booking saved before that field existed."""
    raw = b.get("created_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_zone()).date()          # None: the server's zone, as local_day


def _agent_reauthorizations(front, counted: set) -> int:
    """refresh_hold calls that reached PayPal for the bookings in `counted` (conversation index,
    booking id), read from the results our own tool code wrote (never from the model's words).
    Reached PayPal: "refreshed" (an answer or a timeout), a definitive refusal (N8: deposit_held
    False) or any provider_error. Refused before PayPal ("no held deposit") does not count."""
    n = 0
    for i, s in enumerate(front.conversations):
        uses = {}
        for msg in s.messages:
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                if blk.get("type") == "tool_use":
                    uses[blk.get("id")] = blk
                elif blk.get("type") == "tool_result":
                    use = uses.get(blk.get("tool_use_id")) or {}
                    if use.get("name") != "refresh_hold":
                        continue
                    if (i, str((use.get("input") or {}).get("booking_id", ""))) not in counted:
                        continue
                    try:
                        out = ast.literal_eval(str(blk.get("content", "")))
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(out, dict) and ("refreshed" in out or "provider_error" in out
                                                  or out.get("deposit_held") is False):
                        n += 1
    return n


def _amount(row: dict) -> float | None:
    try:
        a = float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return None
    return a if math.isfinite(a) else None


def _signed(row: dict, approved: dict, keys: list) -> bool:
    """Did the owner sign exactly what this executed ledger row did? ALL of: an approval stored
    for the row's mandate id, whose mandate carries that same jti; a valid Ed25519 signature over
    it from a key this shop paired; the same action and PayPal resource; amount within the cap."""
    mid = str(row.get("mandate_id", ""))
    a = approved.get(mid)
    if not mid or not isinstance(a, dict):
        return False
    m, sig = a.get("mandate") or {}, a.get("signature") or ""
    if m.get("jti") != mid:
        return False
    amount = _amount(row)
    try:
        cap = float(m.get("cap"))
    except (TypeError, ValueError):
        return False
    if amount is None or not math.isfinite(cap) or amount > cap + 1e-9:
        return False
    if row.get("action") != m.get("action") or row.get("recipient") != m.get("recipient"):
        return False
    return any(verify_signature(k, m, sig) for k in keys)


def today(demo, now: float | None = None) -> dict:
    """The owner's day of money: ledger rows and bookings of the shop's local calendar day
    (ASK_FIRST_TZ), computed from bookings and the ledger. Money moved without a signature is
    also checked on EVERY earlier row, so it cannot hide in yesterday."""
    day = local_day(time.time() if now is None else now)
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

    kept = given_back = released = unsigned = unsigned_before = 0.0
    unsigned_rows = unsigned_rows_before = refused = failed = undated_rows = 0
    reasons: dict[str, int] = {}
    held_by_auth = {b.get("authorization_id"): float(b.get("deposit") or 0) for b in bookings(demo.front)}
    for e in entries:
        result, action = e.get("result"), e.get("action")
        ts = e.get("ts")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            is_today = local_day(ts) == day
        else:
            is_today, undated_rows = True, undated_rows + 1     # no date: counted, and the panel says so
        if result == "executed":
            amount = _amount(e)
            if not _signed(e, approved, keys):
                # Every unsigned row counts. Only an exact void_deposit is known to move no money;
                # any other action (or an unknown one) counts its whole positive amount.
                moved = 0.0 if action == RELEASES_ONLY else max(amount or 0.0, 0.0)
                if is_today:
                    unsigned_rows += 1
                    unsigned += moved
                else:
                    unsigned_rows_before += 1
                    unsigned_before += moved
            if not is_today or amount is None:
                continue
            if action == "capture_deposit":
                kept += amount
            elif action == "refund_deposit":
                given_back += amount
            elif action == RELEASES_ONLY:
                released += held_by_auth.get(e.get("recipient"), 0.0)
        elif not is_today:
            continue
        elif result == "rejected":
            refused += 1
            reasons[e.get("reason") or "rejected"] = reasons.get(e.get("reason") or "rejected", 0) + 1
        elif result == "failed":
            failed += 1

    counted, undated_bookings, bs = set(), 0, []
    for i, s in enumerate(demo.front.conversations):
        for bid, b in s.bookings.items():
            d = _booking_day(b)
            if d is None:
                undated_bookings += 1           # saved before bookings carried a date: counted
            elif d != day:
                continue
            counted.add((i, str(bid)))
            bs.append(b)
    orders = sum(1 for b in bs if b.get("order_id"))
    holds = sum(1 for b in bs if b.get("authorization_id"))
    reauth = _agent_reauthorizations(demo.front, counted)

    def asked_today(jti: str) -> bool:
        m = demo.owner.get(jti) or {}
        return isinstance(m.get("created"), (int, float)) and local_day(m["created"]) == day
    approvals = sum(1 for jti in approved if asked_today(jti))
    declines = sum(1 for jti in demo.declined if asked_today(jti))   # a decline is only possible while pending
    v = demo.ledger_rows()[1]                                        # includes the remembered head
    chain_ok = (v["ok"] or (v["empty"] and demo.ledger_head is None)) and unreadable == 0
    _, zone_note = zone_status()
    return {
        "day": f"{day:%a} {day.day} {day:%b}", "zone_note": zone_note,
        "bookings": len(bs), "undated_bookings": undated_bookings, "undated_rows": undated_rows,
        "orders": orders, "holds": holds, "reauthorizations": reauth,
        "agent_calls": orders + holds + reauth,
        "approvals": approvals, "declines": declines, "taps": approvals + declines,
        "kept": money(kept), "given_back": money(given_back), "released": money(released),
        "refused": refused, "failed": failed,
        "refused_reasons": ", ".join(f"{k.replace('_', ' ')} {n}" for k, n in sorted(reasons.items())),
        "unsigned": money(unsigned), "unsigned_rows": unsigned_rows,
        "unsigned_before": money(unsigned_before), "unsigned_rows_before": unsigned_rows_before,
        "clean": unsigned_rows == 0 and unsigned_rows_before == 0 and chain_ok, "chain_ok": chain_ok,
        "rows": len(led["entries"]),
    }
