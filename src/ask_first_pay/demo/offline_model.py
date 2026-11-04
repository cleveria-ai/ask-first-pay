"""The scripted model the demo uses when there is no ANTHROPIC_API_KEY.

It speaks the same protocol as `AnthropicModel` (`create(system, messages, tools)` returning
text and tool_use blocks), so it drives the very same `run_turn` loop and the very same tools.
It is a small deterministic policy instead of a language model: it reads the newest message,
picks one tool, and turns the tool's result into a reply. It has no more power than Claude has:
everything it does goes through the agent's `Toolbox`, i.e. `AgentGate` and `HoldDesk` only.
"""
from __future__ import annotations

import ast
import re
from datetime import datetime

from ..agent.loop import ScriptedModel, text, tool
from ..agent.state import AgentState
from ..agent.tools import SLOTS

GOODWILL_RE = re.compile(r"goodwill refund of ([0-9]+(?:\.[0-9]{1,2})?) .*?(booking-\d+)", re.I)
NO_SHOW_RE = re.compile(r"(booking-\d+) did not show up", re.I)
PAID_RE = re.compile(r"approved PayPal order ([A-Za-z0-9_-]+)", re.I)
APPROVED_RE = re.compile(r"owner approved mandate ([A-Za-z0-9_-]+)", re.I)
DECLINED_RE = re.compile(r"owner declined mandate ([A-Za-z0-9_-]+)", re.I)


def slot_label(slot: str) -> str:
    """'2026-11-17 15:00' -> 'Tue 17 Nov 15:00' (what people read in the chat)."""
    try:
        return datetime.strptime(slot, "%Y-%m-%d %H:%M").strftime("%a %d %b %H:%M")
    except ValueError:
        return slot


def match_slot(message: str) -> str | None:
    low = message.lower()
    for s in SLOTS:                                   # exact slot or exact label
        if s in low or slot_label(s).lower() in low:
            return s
    times = re.findall(r"\b(\d{1,2}):(\d{2})\b", low) or [(h, "00") for h in re.findall(r"\b(\d{1,2})\s*(?:am|h)\b", low)]
    days = [d for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun") if re.search(rf"\b{d}", low)]
    for s in SLOTS:
        lab = slot_label(s).lower()
        t_ok = any(lab.endswith(f"{int(h):02d}:{m}") for h, m in times)
        d_ok = any(lab.startswith(d) for d in days)
        if (t_ok and d_ok) or (t_ok and not days) or (d_ok and not times):
            return s
    return None


def _result(content: str):
    try:
        return ast.literal_eval(content)
    except (ValueError, SyntaxError):
        return {"error": content}


class OfflineFrontDeskModel(ScriptedModel):
    """A rule-based stand-in for Claude. Reads `state` (the conversation it belongs to) only to
    find booking ids; it never touches the gate, the provider or the owner's side."""

    def __init__(self, state: AgentState) -> None:
        super().__init__([])
        self.state = state

    def create(self, *, system, messages, tools):
        self.calls += 1
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            return self._after_tools(messages)
        return self._on_message(str(last["content"]))

    # ---- a new message (customer, payments relay or owner relay)
    def _latest(self, *statuses):
        for b in reversed(list(self.state.bookings.values())):
            if b["status"] in statuses:
                return b
        return None

    def _on_message(self, msg: str) -> list:
        low = msg.lower()
        if m := PAID_RE.search(msg):
            b = next((x for x in self.state.bookings.values() if x["order_id"] == m.group(1)), None)
            return [tool("confirm_deposit", "c", booking_id=b["id"])] if b else [text("I can't find that order.")]
        if m := APPROVED_RE.search(msg):
            return [tool("execute_mandate", "x", mandate_id=m.group(1))]
        if DECLINED_RE.search(msg):
            return [text("The owner declined, so the deposit stays held and nothing moved.")]
        if m := NO_SHOW_RE.search(msg):
            b = self.state.bookings.get(m.group(1))
            return [tool("request_capture", "q", booking_id=m.group(1), amount=b["deposit"] if b else 0)]
        if m := GOODWILL_RE.search(msg):
            return [tool("request_refund", "r", booking_id=m.group(2), amount=float(m.group(1)))]
        if "cancel" in low:
            b = self._latest("deposit_held")
            if b is None:
                return [text("I can't find a confirmed booking to cancel.")]
            return [text("Understood. I will release the hold."), tool("request_void", "v", booking_id=b["id"])]
        if any(w in low for w in ("book", "appointment", "slot")):
            slot = match_slot(msg)
            if slot is None:
                return [text("Which slot suits you? " + ", ".join(slot_label(s) for s in SLOTS)
                             + f'. Reply with e.g. "book {slot_label(SLOTS[0])}".')]
            return [tool("book_slot", "b", customer="Customer", slot=slot)]
        if "status" in low or "deposit" in low:
            return [tool("list_bookings", "l")]
        if "refund" in low or "capture" in low or "charge" in low:
            return [text("I can't move money myself. Anything beyond the held deposit waits for the owner.")]
        return [text('I can book a visit ("book ' + slot_label(SLOTS[0]) + '") or cancel one ("cancel"). '
                     "Anything involving money beyond the held deposit waits for the owner.")]

    # ---- the result of the tool the model just called
    def _after_tools(self, messages) -> list:
        uses = [b for b in messages[-2]["content"] if b.get("type") == "tool_use"]
        results = [_result(r["content"]) for r in messages[-1]["content"]]
        name, args, res = uses[-1]["name"], uses[-1].get("input", {}), results[-1]
        if not isinstance(res, dict):
            res = {"error": str(res)}
        if "rejected" in res:
            return [text(f"The gate rejected that: {res['rejected']}. The attempt is on the ledger.")]
        if "error" in res or "provider_error" in res:
            if name == "book_slot" and "available" in res:
                return [text("That slot is taken. Free: " + ", ".join(slot_label(s) for s in res["available"]) + ".")]
            return [text(f"Something went wrong: {res.get('error') or res.get('message')}.")]
        if name == "book_slot":
            return [tool("create_deposit_order", "o", booking_id=res["booking_id"])]
        if name == "create_deposit_order":
            b = self.state.bookings[args["booking_id"]]
            return [text(f"Reserved {slot_label(b['slot'])}. To confirm, hold a ${b['deposit']:.2f} deposit "
                         "(nothing is charged now).")]
        if name == "confirm_deposit":
            b = self.state.bookings[args["booking_id"]]
            return [text(f"Confirmed: {slot_label(b['slot'])}. ${b['deposit']:.2f} is held "
                         f"(authorization {res['authorization_id']}), not charged.")]
        if name == "list_bookings":
            bs = res["bookings"]
            if not bs:
                return [text("No booking yet.")]
            b = bs[-1]
            return [text(f"Booking {b['id']} for {slot_label(b['slot'])}: {b['status'].replace('_', ' ')}.")]
        if name.startswith("request_"):
            return [text("I asked the owner to approve. Nothing moves until they do.")]
        if name == "execute_mandate":
            req = self.state.mandates[args["mandate_id"]]
            if req["action"] == "capture_deposit":
                cid = (res.get("outcome") or {}).get("capture_id")
                return [text(f"Done: ${req['amount']:.2f} captured for the no-show ({cid}).")]
            if req["action"] == "void_deposit":
                return [text("Done: the hold is released. Nothing was charged and nothing needs refunding.")]
            return [text(f"Done: ${req['amount']:.2f} refunded to the customer.")]
        return [text("Done.")]
