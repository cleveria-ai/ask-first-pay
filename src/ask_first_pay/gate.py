"""The mandate gate: the ONLY way to move money.

An agent may create and authorize deposits freely (no money moves). Capturing, voiding or
refunding is consequential: the agent can only *ask* for a single-use mandate, the business owner
approves it once on their phone, and only then does the gate call the provider.

Actions and what `recipient` means for each:
  capture_deposit   recipient = authorization_id   amount = what to capture (<= authorized)
  void_deposit      recipient = authorization_id   amount = 0.01 (symbolic: a void moves no money
                                                                  but releases the hold, so the
                                                                  owner still says yes)
  refund_deposit    recipient = capture_id         amount = what to refund (<= captured)

Three objects come out of here and they must never be confused:
  AgentGate   what the agent gets for money: request, execute, describe, view_ledger. Nothing
              that can approve, pair a device, read the person's key or reach the provider.
  HoldDesk    what the agent gets for deposits: create_order, authorize, reauthorize (hold only).
  OwnerSide   what the owner's phone page gets: new_pairing_code, pair, approve, pending.
"""
from __future__ import annotations

from dataclasses import asdict

from ask_first import Ledger, MandateEngine

from .ports import PaymentProvider, ProviderError

ACTIONS = ("capture_deposit", "void_deposit", "refund_deposit")
TRANSIENT_RETRIES = 2      # a timeout or 5xx is retried with the SAME PayPal-Request-Id


def make_executor(provider: PaymentProvider, retries: int = TRANSIENT_RETRIES):
    def call(action, target, amount, request_id):
        if action == "capture_deposit":
            return asdict(provider.capture(target, amount, request_id=request_id))
        if action == "void_deposit":
            return asdict(provider.void(target, request_id=request_id))
        if action == "refund_deposit":
            return asdict(provider.refund(target, amount, request_id=request_id))
        raise ValueError(f"unknown action {action!r}")

    def executor(mandate: dict, requested: dict):
        # After a timeout the money may or may not have moved. Retrying with the mandate's jti as
        # the idempotency key makes PayPal answer the first result instead of moving it twice, so
        # one approval survives a flaky network and still means exactly one capture.
        action, target, amount = requested["action"], requested["recipient"], requested["amount"]
        for attempt in range(retries + 1):
            try:
                return call(action, target, amount, mandate["jti"])
            except ProviderError as e:
                if not e.transient or attempt == retries:
                    raise
    return executor


def make_engine(provider: PaymentProvider, person_pub, ledger_path: str) -> MandateEngine:
    return MandateEngine(person_pub=person_pub, ledger=Ledger(ledger_path), executor=make_executor(provider))


class AgentGate:
    """The agent's only handle on money. It can ask and it can try; it cannot approve."""

    __slots__ = ("_request", "_execute", "_get", "_view_ledger")

    def __init__(self, engine: MandateEngine) -> None:
        object.__setattr__(self, "_request", engine.request)
        object.__setattr__(self, "_execute", engine.execute)
        object.__setattr__(self, "_get", engine.get)
        object.__setattr__(self, "_view_ledger", engine.view_ledger)

    def __setattr__(self, name, value):
        raise AttributeError("AgentGate is read-only")

    def request(self, action: str, target: str, amount: float, ttl_s: int = 900, agent: str = "front-desk-agent") -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        # A cap is money: whole cents only. The owner reads it as .2f and the PayPal adapter refuses
        # sub-cent amounts, so 9.996 would be signed as "10.00" and could never run as signed.
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or round(amount, 2) != amount:
            raise ValueError(f"amount must be a number of whole cents, got {amount!r}")
        return dict(self._request(agent, action, target, amount, ttl_s=ttl_s))

    def execute(self, mandate_id: str, action: str, target: str, amount: float) -> dict:
        return self._execute(mandate_id, action, target, amount)

    def describe(self, mandate_id: str) -> str | None:
        """The owner-facing summary, built ONLY from the signed fields, never from model text."""
        m = self._get(mandate_id)
        if not m:
            return None
        return (f"{m['action']} on {m['recipient']} for at most {m['cap']:.2f}, "
                f"single use, expires at {m['exp']} (unix time), state {m['_state']}")

    def view_ledger(self) -> dict:
        return self._view_ledger()


class HoldDesk:
    """The agent's free tools on the provider: create, authorize and reauthorize hold money but
    never move it. Capture, refund and void are deliberately absent."""

    __slots__ = ("_p",)

    def __init__(self, provider: PaymentProvider) -> None:
        object.__setattr__(self, "_p", provider)

    def __setattr__(self, name, value):
        raise AttributeError("HoldDesk is read-only")

    def create_order(self, amount: float, currency: str, reference: str):
        return self._p.create_order(amount, currency, reference)

    def authorize(self, order_id: str):
        return self._p.authorize(order_id)

    def reauthorize(self, authorization_id: str, request_id: str):
        return self._p.reauthorize(authorization_id, request_id)


class OwnerSide:
    """What only the owner's device page may call."""

    def __init__(self, engine: MandateEngine) -> None:
        self.new_pairing_code = engine.new_pairing_code
        self.pair = engine.pair
        self.approve = engine.approve
        self.get = engine.get
        self.pending = engine.pending


def split(engine: MandateEngine) -> tuple[AgentGate, OwnerSide]:
    return AgentGate(engine), OwnerSide(engine)
