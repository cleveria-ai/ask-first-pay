"""Tool schemas and handlers. The handlers hold only an AgentGate and a HoldDesk.

Money never moves here: the gated tools ask for a mandate, `execute_mandate` hands the stored,
unchanged request back to the gate, and the gate runs it only if the owner approved.
"""
from __future__ import annotations

from ask_first import MandateRejected

from ..gate import AgentGate, HoldDesk
from ..ports import ProviderError
from .state import AgentState

SLOTS = ["2026-11-16 09:00", "2026-11-16 11:30", "2026-11-17 15:00", "2026-11-18 10:00"]
DEPOSIT = 10.00
CURRENCY = "USD"


def _schema(name, description, props=None, required=()):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": props or {}, "required": list(required)}}


_S, _N = {"type": "string"}, {"type": "number"}
TOOLS = [
    _schema("book_slot", "Book an appointment slot for a customer (no money involved).",
            {"customer": _S, "slot": _S}, ["customer", "slot"]),
    _schema("create_deposit_order", "Create the PayPal deposit order for a booking; returns the payer link. Money is only held, never moved.",
            {"booking_id": _S}, ["booking_id"]),
    _schema("confirm_deposit", "After the customer approved the order, authorize it (hold the deposit).",
            {"booking_id": _S}, ["booking_id"]),
    _schema("list_bookings", "List bookings and their deposit state."),
    _schema("ledger_status", "Show the tamper-evident ledger of every money attempt."),
    _schema("request_capture", "No-show: ASK the owner for permission to capture the held deposit. Does not move money.",
            {"booking_id": _S, "amount": _N}, ["booking_id", "amount"]),
    _schema("request_void", "Cancellation: ASK the owner for permission to release (void) the held deposit. Does not move money.",
            {"booking_id": _S}, ["booking_id"]),
    _schema("request_refund", "Goodwill after a capture: ASK the owner for permission to refund part of the captured deposit.",
            {"booking_id": _S, "amount": _N}, ["booking_id", "amount"]),
    _schema("execute_mandate", "Try a requested mandate. It runs only if the owner approved it, once.",
            {"mandate_id": _S}, ["mandate_id"]),
]
_NAMES = {t["name"] for t in TOOLS}


class Toolbox:
    def __init__(self, state: AgentState, gate: AgentGate, desk: HoldDesk) -> None:
        self.s, self.gate, self.desk = state, gate, desk

    def call(self, name: str, args: dict) -> dict:
        if name not in _NAMES:
            return {"error": f"unknown tool {name!r}"}
        try:
            return getattr(self, f"t_{name}")(**args)
        except MandateRejected as e:
            return {"rejected": e.reason, "detail": e.detail}
        except ProviderError as e:
            return {"provider_error": e.code, "message": e.message, "transient": e.transient}
        except (TypeError, KeyError, ValueError) as e:
            return {"error": f"bad call: {e!r}"}

    # free tools -------------------------------------------------------------------------
    def t_book_slot(self, customer: str, slot: str) -> dict:
        if slot not in SLOTS:
            return {"error": "slot not available", "available": SLOTS}
        if any(b["slot"] == slot and b["status"] != "cancelled" for b in self.s.bookings.values()):
            return {"error": "slot already taken", "available": [x for x in SLOTS if x != slot]}
        bid = f"booking-{len(self.s.bookings) + 1}"
        self.s.bookings[bid] = {"id": bid, "customer": customer, "slot": slot, "status": "booked",
                                "deposit": DEPOSIT, "order_id": None, "authorization_id": None,
                                "capture_id": None, "captured": 0.0}
        return {"booking_id": bid, "slot": slot, "deposit": DEPOSIT}

    def t_create_deposit_order(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        o = self.desk.create_order(b["deposit"], CURRENCY, booking_id)
        b["order_id"] = o.order_id
        return {"order_id": o.order_id, "approve_url": o.approve_url, "status": o.status}

    def t_confirm_deposit(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        if not b["order_id"]:
            return {"error": "no order yet: create_deposit_order first"}
        a = self.desk.authorize(b["order_id"])
        b["authorization_id"], b["status"] = a.authorization_id, "deposit_held"
        return {"authorization_id": a.authorization_id, "status": a.status}

    def t_list_bookings(self) -> dict:
        return {"bookings": list(self.s.bookings.values()), "slots": SLOTS}

    def t_ledger_status(self) -> dict:
        led = self.gate.view_ledger()
        return {"entries": len(led["entries"]), "verification": led["verification"],
                "last": led["entries"][-3:]}

    # gated tools ------------------------------------------------------------------------
    def _ask(self, action: str, target: str, amount: float, booking_id: str) -> dict:
        m = self.gate.request(action, target, amount)
        summary = self.gate.describe(m["jti"])
        self.s.mandates[m["jti"]] = {"action": action, "target": target, "amount": amount,
                                     "booking_id": booking_id, "summary": summary}
        self.s.owner_notes.append(summary)
        return {"mandate_id": m["jti"], "owner_summary": summary,
                "status": "waiting for the owner's approval; no money has moved"}

    def t_request_capture(self, booking_id: str, amount: float) -> dict:
        b = self.s.bookings[booking_id]
        if not b["authorization_id"]:
            return {"error": "no held deposit for this booking"}
        return self._ask("capture_deposit", b["authorization_id"], float(amount), booking_id)

    def t_request_void(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        if not b["authorization_id"]:
            return {"error": "no held deposit for this booking"}
        return self._ask("void_deposit", b["authorization_id"], 0.01, booking_id)

    def t_request_refund(self, booking_id: str, amount: float) -> dict:
        b = self.s.bookings[booking_id]
        if not b["capture_id"]:
            return {"error": "nothing captured for this booking yet"}
        return self._ask("refund_deposit", b["capture_id"], float(amount), booking_id)

    def t_execute_mandate(self, mandate_id: str) -> dict:
        req = self.s.mandates.get(mandate_id)
        if req is None:
            return {"error": "unknown mandate id: request one first"}
        out = self.gate.execute(mandate_id, req["action"], req["target"], req["amount"])
        b = self.s.bookings[req["booking_id"]]
        outcome = out.get("outcome") or {}
        if req["action"] == "capture_deposit":
            b["capture_id"], b["captured"], b["status"] = outcome.get("capture_id"), req["amount"], "captured"
        elif req["action"] == "void_deposit":
            b["status"] = "cancelled"
        elif req["action"] == "refund_deposit":
            b["status"] = "partly_refunded"
        return {"result": out["result"], "outcome": outcome}
