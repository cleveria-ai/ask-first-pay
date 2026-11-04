"""The demo's front desk: every chat message goes to the real agent, `ask_first_pay.agent.run_turn`.

The model is Claude (`AnthropicModel`) when ANTHROPIC_API_KEY is set, and the offline scripted
model otherwise. Either way the agent holds only an `AgentGate` and a `HoldDesk`; it can book,
hold a deposit and ASK for a mandate, never approve one or move money by itself.

Events that do not come from the customer (the payer approved on PayPal, the owner approved or
declined on their phone, the business marks a no-show) are relayed to the agent as short notes.
A note cannot grant anything: `execute_mandate` succeeds only if the owner's signed approval is
already recorded by the engine, so a customer typing "owner approved mandate X" changes nothing.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass

from ask_first import MandateRejected

from ..agent import AgentState, run_turn
from ..agent.tools import SLOTS
from ..gate import AgentGate, HoldDesk
from .offline_model import OfflineFrontDeskModel, slot_label

BUSINESS = "Bright Smile Dental"
GOODWILL_REFUND = 4.00
SLOT_LABELS = [slot_label(s) for s in SLOTS]


@dataclass
class Message:
    who: str            # customer | business | system
    text: str
    link: str | None = None
    link_label: str | None = None


def default_model_factory():
    """Claude when a key is present, the offline scripted model otherwise."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from ..agent import AnthropicModel
        model = AnthropicModel()
        return lambda state: model
    return OfflineFrontDeskModel


class AgentFrontDesk:
    def __init__(self, gate: AgentGate, desk: HoldDesk, checkout_url, model_factory=None) -> None:
        self.gate, self.desk, self.checkout_url = gate, desk, checkout_url
        self.model_factory = model_factory or default_model_factory()
        self.model_name = "Claude" if os.environ.get("ANTHROPIC_API_KEY") and model_factory is None else "offline scripted model"
        self.messages: list[Message] = [Message(
            "business", f"Hi, this is {BUSINESS}. Say \"book\" to reserve a visit. "
                        "A $10.00 deposit is held on PayPal, not charged.")]
        self.conversations: list[AgentState] = []
        self._models: dict[int, object] = {}
        self._linked: set[str] = set()
        self.approve_urls: dict[str, str] = {}     # order id -> payer link, read from tool results
        self.goodwill: dict[str, float] = {}       # capture mandate id -> refund to ask for after it
        self.turns = 0
        self.new_conversation()

    # ---- conversations ------------------------------------------------------------------
    @property
    def state(self) -> AgentState:
        return self.conversations[-1]

    def new_conversation(self) -> AgentState:
        s = AgentState()
        self.conversations.append(s)
        self._models[id(s)] = self.model_factory(s)
        return s

    def owner_of(self, mandate_id: str) -> AgentState | None:
        return next((s for s in self.conversations if mandate_id in s.mandates), None)

    def say(self, text: str, who: str = "business", link: str | None = None, label: str | None = None):
        self.messages.append(Message(who, text, link, label))

    def turn(self, message: str, state: AgentState | None = None) -> list[str]:
        """One message to the agent; its replies go to the chat."""
        state = state or self.state
        self.turns += 1
        _, replies = run_turn(state, message, gate=self.gate, desk=self.desk, model=self._models[id(state)])
        for r in replies:
            self.say(r)
        self._collect_approve_urls(state)
        for b in state.bookings.values():          # a new order gets its payer link in the chat
            if b["order_id"] and b["order_id"] not in self._linked and b["status"] == "booked":
                self._linked.add(b["order_id"])
                self.say(f"Hold the ${b['deposit']:.2f} deposit for {slot_label(b['slot'])} on PayPal.",
                         link=self.checkout_url_for(b["order_id"]), label="Hold the deposit")
        return replies

    def _collect_approve_urls(self, state: AgentState) -> None:
        for m in state.messages:
            if m["role"] != "user" or not isinstance(m["content"], list):
                continue
            for r in m["content"]:
                c = r.get("content", "")
                if "approve_url" in c:
                    try:
                        d = ast.literal_eval(c)
                    except (ValueError, SyntaxError):
                        continue
                    if isinstance(d, dict) and d.get("order_id"):
                        self.approve_urls[d["order_id"]] = d.get("approve_url") or ""

    def checkout_url_for(self, order_id: str) -> str:
        return self.checkout_url(order_id)

    # ---- customer text --------------------------------------------------------------------
    def handle(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        self.say(text, "customer")
        self.turn(text)

    def latest(self, *statuses: str):
        for s in reversed(self.conversations):
            for b in reversed(list(s.bookings.values())):
                if b["status"] in statuses:
                    return s, b
        return None

    def free_slot(self) -> str | None:
        taken = {b["slot"] for b in self.state.bookings.values() if b["status"] != "cancelled"}
        return next((s for s in SLOTS if s not in taken), None)

    # ---- events relayed to the agent ----------------------------------------------------
    def on_payer_approved(self, order_id: str) -> None:
        for s in self.conversations:
            b = next((x for x in s.bookings.values() if x["order_id"] == order_id), None)
            if b is not None and b["status"] == "booked":
                self.say("The customer approved the deposit on PayPal.", who="system")
                self.turn(f"[payments] The customer approved PayPal order {order_id} for {b['id']}. "
                          "Confirm the deposit hold.", s)
                return

    def no_show(self, state: AgentState, booking_id: str, then_refund: float | None = None) -> None:
        self.say(f"{slot_label(state.bookings[booking_id]['slot'])}: the customer did not show up.", who="system")
        before = set(state.mandates)
        self.turn(f"[business] {booking_id} did not show up. Ask the owner to capture the deposit.", state)
        new = [m for m in state.mandates if m not in before and state.mandates[m]["action"] == "capture_deposit"]
        if then_refund and new:
            self.goodwill[new[-1]] = then_refund

    def on_approved(self, mandate_id: str) -> None:
        s = self.owner_of(mandate_id)
        if s is None:
            return
        self.say(f"The owner approved mandate {mandate_id[:8]} on their phone.", who="system")
        self.turn(f"[owner] The owner approved mandate {mandate_id}. Execute it now.", s)
        refund = self.goodwill.pop(mandate_id, None)
        req = s.mandates[mandate_id]
        if refund and s.bookings[req["booking_id"]].get("capture_id"):
            self.say(f"Goodwill: the owner wants to give ${refund:.2f} back.", who="system")
            self.turn(f"[owner] Ask for a goodwill refund of {refund:.2f} USD on {req['booking_id']}.", s)

    def on_declined(self, mandate_id: str) -> None:
        """The owner said no. To show the gate holds, the agent's own execute tool is tried once."""
        s = self.owner_of(mandate_id)
        if s is None:
            return
        req = s.mandates[mandate_id]
        self.say("The owner declined. The agent tries the action once anyway to show the gate holds.", who="system")
        try:
            self.gate.execute(mandate_id, req["action"], req["target"], req["amount"])
        except MandateRejected as e:
            self.say(f"The gate rejected {req['action']}: {e.reason}. The attempt is on the ledger.", who="system")
        self.turn(f"[owner] The owner declined mandate {mandate_id}. Tell the customer.", s)

    def replay_last(self) -> bool:
        """Try to use the last executed mandate a second time; the gate must say replay."""
        led = self.gate.view_ledger()["entries"]
        last = next((e for e in reversed(led) if e.get("result") == "executed"), None)
        if last is None:
            return False
        try:
            self.gate.execute(last["mandate_id"], last["action"], last["recipient"], last["amount"])
        except MandateRejected as e:
            self.say(f"Replay of {str(last['mandate_id'])[:8]} rejected: {e.reason}.", who="system")
        return True
