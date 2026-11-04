"""The chat stub: a small rule-based front desk for the fictional "Bright Smile Dental".

It is deliberately dumb and deterministic so the demo runs offline with no API key. It holds the
two handles the contract allows an agent: an `AgentGate` (ask, try, describe, read the ledger)
and a `HoldDesk` (create, authorize and reauthorize: money is only held). It never sees the
engine, the provider or `OwnerSide`, so it cannot approve a mandate or move money by itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ask_first import MandateRejected

from ..gate import AgentGate, HoldDesk

BUSINESS = "Bright Smile Dental"
DEPOSIT = 10.00
CURRENCY = "USD"
GOODWILL_REFUND = 4.00
VOID_SYMBOLIC = 0.01
SLOTS = ["Tue 10:00", "Tue 14:30", "Wed 09:00", "Thu 16:00"]


@dataclass
class Message:
    who: str            # customer | business | system
    text: str
    link: str | None = None
    link_label: str | None = None


@dataclass
class Booking:
    id: str
    slot: str
    amount: float
    order_id: str
    approve_url: str
    status: str = "awaiting_payment"   # awaiting_payment | confirmed | captured | voided
    authorization_id: str | None = None
    capture_id: str | None = None
    mandates: list[str] = field(default_factory=list)


@dataclass
class Pending:
    """What the agent will do the moment the owner's approval for `mandate_id` is recorded."""
    mandate_id: str
    booking_id: str
    action: str
    target: str
    amount: float
    then_refund: float | None = None


class FrontDesk:
    def __init__(self, gate: AgentGate, desk: HoldDesk, checkout_url) -> None:
        self.gate = gate
        self.desk = desk
        self.checkout_url = checkout_url      # order -> URL the customer opens to pay
        self.messages: list[Message] = [Message(
            "business", f"Hi, this is {BUSINESS}. Say \"book\" to reserve a visit. "
                        f"A ${DEPOSIT:.2f} deposit is held on PayPal, not charged.")]
        self.bookings: dict[str, Booking] = {}
        self.pending: dict[str, Pending] = {}
        self.last_executed: tuple[str, str, str, float] | None = None
        self._n = 0

    # ---- helpers
    def say(self, text: str, who: str = "business", link: str | None = None, label: str | None = None):
        self.messages.append(Message(who, text, link, label))

    def latest(self, *statuses: str) -> Booking | None:
        for b in reversed(list(self.bookings.values())):
            if b.status in statuses:
                return b
        return None

    # ---- customer text
    def handle(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.say(text, "customer")
        low = text.lower()
        if "cancel" in low:
            b = self.latest("confirmed")
            if b is None:
                self.say("I can't find a confirmed booking to cancel.")
            else:
                self.cancel(b)
        elif "book" in low or "appointment" in low or "slot" in low:
            slot = next((s for s in SLOTS if s.lower() in low), None)
            if slot is None:
                m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\b", low)
                if m:
                    slot = next((s for s in SLOTS if s.endswith(f"{int(m.group(1)):02d}:{m.group(2) or '00'}")), None)
            if slot is None:
                self.say("Which slot suits you? " + ", ".join(SLOTS) + ". Reply with e.g. \"book " + SLOTS[0] + "\".")
            else:
                self.book(slot)
        elif "status" in low or "deposit" in low:
            b = self.latest("awaiting_payment", "confirmed", "captured", "voided")
            self.say("No booking yet." if b is None else
                     f"Booking {b.id} for {b.slot}: {b.status.replace('_', ' ')}.")
        else:
            self.say("I can book a visit (\"book Tue 10:00\") or cancel one (\"cancel\"). "
                     "Anything involving money beyond the held deposit waits for the owner.")

    # ---- free tools: money is only held
    def book(self, slot: str) -> Booking:
        self._n += 1
        bid = f"booking-{self._n}"
        order = self.desk.create_order(DEPOSIT, CURRENCY, bid)
        b = Booking(bid, slot, DEPOSIT, order.order_id, order.approve_url)
        self.bookings[bid] = b
        self.say(f"Reserved {slot}. To confirm, hold a ${DEPOSIT:.2f} deposit (nothing is charged now).",
                 link=self.checkout_url(order), label="Hold the deposit")
        return b

    def on_payer_approved(self, order_id: str) -> None:
        b = next((x for x in self.bookings.values() if x.order_id == order_id), None)
        if b is None or b.status != "awaiting_payment":
            return
        auth = self.desk.authorize(order_id)
        b.authorization_id = auth.authorization_id
        b.status = "confirmed"
        self.say(f"Confirmed: {b.slot}. ${b.amount:.2f} is held (authorization {auth.authorization_id}), not charged.")

    # ---- consequential tools: the agent can only ask
    def _ask(self, b: Booking, action: str, target: str, amount: float, why: str,
             then_refund: float | None = None) -> str:
        m = self.gate.request(action, target, amount)
        jti = m["jti"]
        b.mandates.append(jti)
        self.pending[jti] = Pending(jti, b.id, action, target, amount, then_refund)
        self.say(f"{why} I asked the owner to approve. Nothing moves until they do.", who="system")
        return jti

    def no_show(self, b: Booking, then_refund: float | None = None) -> str:
        return self._ask(b, "capture_deposit", b.authorization_id, b.amount,
                         f"{b.slot}: the customer did not show up.", then_refund)

    def cancel(self, b: Booking) -> str:
        self.say("Understood. I will release the hold.")
        return self._ask(b, "void_deposit", b.authorization_id, VOID_SYMBOLIC,
                         f"{b.slot}: the customer cancelled.")

    # ---- what happens after the owner answers
    def _try(self, p: Pending) -> dict | None:
        try:
            out = self.gate.execute(p.mandate_id, p.action, p.target, p.amount)
        except MandateRejected as e:
            self.say(f"The gate rejected {p.action}: {e.reason}. The attempt is on the ledger.", who="system")
            return None
        self.last_executed = (p.mandate_id, p.action, p.target, p.amount)
        return out

    def on_approved(self, mandate_id: str) -> None:
        p = self.pending.pop(mandate_id, None)
        if p is None:
            return
        b = self.bookings[p.booking_id]
        out = self._try(p)
        if out is None:
            return
        if p.action == "capture_deposit":
            b.status, b.capture_id = "captured", out["outcome"]["capture_id"]
            self.say(f"Done: ${p.amount:.2f} captured for the no-show ({b.capture_id}).")
            if p.then_refund:
                self._ask(b, "refund_deposit", b.capture_id, p.then_refund,
                          f"Goodwill: refunding ${p.then_refund:.2f} of the captured deposit.")
        elif p.action == "void_deposit":
            b.status = "voided"
            self.say("Done: the hold is released. Nothing was charged and nothing needs refunding.")
        elif p.action == "refund_deposit":
            self.say(f"Done: ${p.amount:.2f} refunded to the customer.")

    def on_declined(self, mandate_id: str) -> None:
        """The owner said no. To show the gate holds, the agent tries once anyway."""
        p = self.pending.pop(mandate_id, None)
        if p is None:
            return
        self.say("The owner declined. I will try the action once anyway to show the gate holds.", who="system")
        self._try(p)
        self.say("The owner declined, so the deposit stays held and nothing moved.")

    def replay_last(self) -> bool:
        """Try to use the last mandate a second time; the gate must say replay."""
        if self.last_executed is None:
            return False
        jti, action, target, amount = self.last_executed
        try:
            self.gate.execute(jti, action, target, amount)
        except MandateRejected as e:
            self.say(f"Replay of {jti[:8]} rejected: {e.reason}.", who="system")
        return True
