"""The "what just happened" line shown on every page after every action.

It is built by comparing two cheap marks of the demo's state (before and after the action):
new ledger rows, new or declined mandates, and booking status changes. So the line states facts
the gate and the ledger recorded, never model text.
"""
from __future__ import annotations

from .offline_model import slot_label

STATUS_TEXT = {
    "booked": "booked; waiting for the customer to hold the deposit on PayPal",
    "deposit_held": "deposit held on PayPal (authorized, not charged)",
    "captured": "deposit captured",
    "cancelled": "hold released (voided); nothing charged",
    "refunded": "captured deposit refunded",
    "partly_refunded": "part of the captured deposit refunded",
}


def mark(demo) -> dict:
    """What the line compares: ledger length, mandate states, booking statuses."""
    mandates = {}
    for jti in list(demo.owner.pending):
        m = demo.owner.get(jti)
        if m is not None:
            mandates[jti] = "declined" if jti in demo.declined and m["_state"] == "pending" else m["_state"]
    bookings = {}
    for i, s in enumerate(demo.front.conversations):
        for bid, b in s.bookings.items():
            bookings[(i, bid)] = (b["slot"], b["status"])
    return {"ledger": len(demo.agent.view_ledger()["entries"]), "mandates": mandates, "bookings": bookings,
            "paired": demo.paired_key}


def _money(x) -> str:
    return f"{float(x):.2f} USD"


def describe(demo, label: str, before: dict) -> dict:
    """{label, tone, items}: tone is ok (money moved as approved), bad (something was refused),
    warn (waiting for the owner) or info (nothing moved)."""
    after = mark(demo)
    items: list[str] = []
    tones: set[str] = set()
    entries = demo.agent.view_ledger()["entries"][before["ledger"]:]
    for e in entries:
        if "_unreadable" in e:
            continue
        m = demo.owner.get(str(e.get("mandate_id", ""))) or {}
        action = e.get("action") or m.get("action", "?")
        target = e.get("recipient") or m.get("recipient", "?")
        if e.get("result") == "executed":
            items.append(f"Gate executed {action} on {target} for {_money(e.get('amount', m.get('cap', 0)))}, "
                         f"once (ledger #{e.get('n')}).")
            tones.add("ok")
        else:
            items.append(f"Gate rejected {action} on {target}: {e.get('reason') or e.get('result')}. "
                         f"Nothing moved (ledger #{e.get('n')}).")
            tones.add("bad")
    for jti, st in after["mandates"].items():
        was = before["mandates"].get(jti)
        if was is None:
            m = demo.owner.get(jti) or {}
            if m.get("action") == "void_deposit":      # its 0.01 cap is symbolic: say what it does
                items.append(f"The agent asked the owner to release (void) the hold {m.get('recipient')}; "
                             f"a void moves no money. Nothing happens until the owner approves.")
            else:
                items.append(f"The agent asked the owner for {m.get('action')} on {m.get('recipient')}, at most "
                             f"{_money(m.get('cap', 0))}. Nothing moves until the owner approves.")
            if st == "pending":
                tones.add("warn")
        elif st == "declined" and was != "declined":
            items.append(f"The owner declined mandate {jti[:8]}. A decline is final.")
            tones.add("bad")
    for key, (slot, status) in after["bookings"].items():
        old = before["bookings"].get(key)
        if old is None or old[1] != status:
            items.append(f"{slot_label(slot)}: {STATUS_TEXT.get(status, status)}.")
            if status == "deposit_held":
                tones.add("ok")
    if after["paired"] != before["paired"] and after["paired"]:
        items.append(f"Phone key {after['paired'][:12]}… is now the only key that can approve a mandate.")
        tones.add("ok")
    if not items:
        items.append("No booking, mandate or ledger row changed. No money moved.")
    tone = "bad" if "bad" in tones else "warn" if "warn" in tones else "ok" if "ok" in tones else "info"
    return {"label": label, "tone": tone, "items": items}
