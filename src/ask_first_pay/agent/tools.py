"""Tool schemas and handlers. The handlers hold only an AgentGate and a HoldDesk.

Money never moves here: the gated tools ask for a mandate, `execute_mandate` hands the stored,
unchanged request back to the gate, and the gate runs it only if the owner approved.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ask_first import MandateRejected

from ..business import currency
from ..gate import AgentGate, HoldDesk
from ..ports import ProviderError
from .state import AgentState

SLOTS = ["2026-11-16 09:00", "2026-11-16 11:30", "2026-11-17 15:00", "2026-11-18 10:00"]
DEPOSIT = 10.00
CURRENCY = currency()          # ASK_FIRST_CURRENCY, default USD (business.py)
# Not names: a booking is made under the customer's own name, which the owner decides from.
PLACEHOLDER_NAMES = frozenset({"", "customer", "the customer", "client", "cliente", "unknown", "name", "you"})
# What PayPal answers a reauthorize with when the CURRENT hold is untouched (Payments v2 spec,
# https://developer.paypal.com/api/payments/v2/schema.json): too soon (inside the 3-day honor
# period), or this authorization cannot be reauthorized (it already is a reauthorization, or the
# payment source does not support it). Any other definitive 4xx (voided, expired, captured, not
# found, declined, ...) means the deposit is no longer held.
HOLD_STILL_VALID = frozenset({"REAUTHORIZATION_TOO_SOON", "REAUTHORIZATION_NOT_SUPPORTED",
                              "REAUTHORIZATION_NOT_SUPPORTED_FOR_PAYMENT_SOURCE"})
HOLD_ENDED = "hold_ended"     # booking status after a definitive "this hold is gone"


def _issues(e: ProviderError) -> set[str]:
    """PayPal puts the real reason in details[].issue under a generic name such as
    UNPROCESSABLE_ENTITY; the fake provider puts it in the code itself. Read both."""
    found = {e.code}
    for d in (e.details or {}).get("details") or []:
        if isinstance(d, dict) and d.get("issue"):
            found.add(str(d["issue"]))
    return found


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
    _schema("refresh_hold", "Before asking to capture an old hold: PayPal guarantees an authorization for 3 days (honor period). After that, reauthorize it once to get a fresh hold on the same deposit. Holds money, never moves it.",
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
        if not isinstance(name, str) or name not in _NAMES:
            return {"error": f"unknown tool {name!r}"}
        if not isinstance(args, dict):
            return {"error": "bad call: arguments must be an object"}
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
        customer = " ".join(str(customer).split())[:60]
        if customer.lower() in PLACEHOLDER_NAMES:
            return {"error": "book under the customer's own name: ask for it if you do not know it"}
        if slot not in SLOTS:
            return {"error": "slot not available", "available": SLOTS}
        if any(b["slot"] == slot and b["status"] != "cancelled" for b in self.s.bookings.values()):
            return {"error": "slot already taken", "available": [x for x in SLOTS if x != slot]}
        bid = f"booking-{len(self.s.bookings) + 1}"
        self.s.bookings[bid] = {"id": bid, "customer": customer, "slot": slot, "status": "booked",
                                "deposit": DEPOSIT, "order_id": None, "authorization_id": None,
                                "capture_id": None, "captured": 0.0, "refunded": 0.0,
                                # when it was booked (UTC): the owner's Today panel counts by day
                                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        return {"booking_id": bid, "slot": slot, "deposit": DEPOSIT}

    def t_create_deposit_order(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        # One PayPal-Request-Id per order, chosen once and kept on the booking: a retry of this
        # same creation (after a timeout, or the model calling the tool twice) gets the same order
        # back, and no other booking, conversation or restart can ever share it.
        if not b.get("order_request_id"):
            b["order_request_id"] = str(uuid.uuid4())
        o = self.desk.create_order(b["deposit"], CURRENCY, booking_id, request_id=b["order_request_id"])
        b["order_id"] = o.order_id
        return {"order_id": o.order_id, "approve_url": o.approve_url, "status": o.status}

    def t_confirm_deposit(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        if not b["order_id"]:
            return {"error": "no order yet: create_deposit_order first"}
        a = self.desk.authorize(b["order_id"])
        b["authorization_id"], b["status"] = a.authorization_id, "deposit_held"
        return {"authorization_id": a.authorization_id, "status": a.status}

    def t_refresh_hold(self, booking_id: str) -> dict:
        """Reauthorize after the honor period. Three outcomes, kept apart:
        - PayPal says too soon / not reauthorizable: the current hold is untouched ("not needed");
        - PayPal did not answer (timeout, 5xx): nothing is known, keep the current hold;
        - any other definitive refusal (voided, expired, captured, not found): the deposit is no
          longer held. The booking leaves `deposit_held`, so no capture can be requested on it."""
        b = self.s.bookings[booking_id]
        if not b["authorization_id"] or b["status"] != "deposit_held":
            return {"error": "no held deposit for this booking"}
        old = b["authorization_id"]
        try:
            a = self.desk.reauthorize(old, f"reauth-{old}")       # idempotent: one reauthorization per hold
        except ProviderError as e:
            if e.transient:
                return {"refreshed": False, "authorization_id": old, "deposit_held": True,
                        "reason": f"{e.code}: PayPal did not answer; the current hold stays as it is"}
            issues = _issues(e)
            if issues & HOLD_STILL_VALID:
                return {"refreshed": False, "authorization_id": old, "deposit_held": True,
                        "reason": f"{'/'.join(sorted(issues & HOLD_STILL_VALID))}: the current hold is still valid, capture it as is"}
            b["status"] = HOLD_ENDED
            return {"error": f"the deposit is no longer held ({'/'.join(sorted(issues))}); "
                             "do not ask the owner to capture it", "deposit_held": False,
                    "authorization_id": old}
        b["authorization_id"] = a.authorization_id
        return {"refreshed": True, "authorization_id": a.authorization_id, "replaces": old, "status": a.status}

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
        if not b["authorization_id"] or b["status"] != "deposit_held":
            return {"error": "no held deposit for this booking"}
        if not 0 < float(amount) <= b["deposit"]:
            # Never put a bigger number in front of the owner than the hold itself.
            return {"error": f"can only ask to capture between 0.01 and the held {b['deposit']:.2f}"}
        return self._ask("capture_deposit", b["authorization_id"], float(amount), booking_id)

    def t_request_void(self, booking_id: str) -> dict:
        b = self.s.bookings[booking_id]
        # Only a hold can be released: after a capture PayPal refuses the void (PREVIOUSLY_CAPTURED),
        # so the owner must never be asked to sign one.
        if not b["authorization_id"] or b["status"] != "deposit_held":
            return {"error": "no held deposit for this booking"}
        return self._ask("void_deposit", b["authorization_id"], 0.01, booking_id)

    def t_request_refund(self, booking_id: str, amount: float) -> dict:
        b = self.s.bookings[booking_id]
        if not b["capture_id"]:
            return {"error": "nothing captured for this booking yet"}
        left = round(b["captured"] - b.get("refunded", 0.0), 2)
        if not 0 < float(amount) <= left:
            return {"error": f"can only ask to refund between 0.01 and the {left:.2f} still captured"}
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
            b["refunded"] = round(b.get("refunded", 0.0) + req["amount"], 2)
            b["status"] = "refunded" if b["refunded"] >= b["captured"] else "partly_refunded"
        return {"result": out["result"], "outcome": outcome}
