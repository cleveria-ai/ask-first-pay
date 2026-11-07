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

import os
import time
from dataclasses import asdict

from ask_first import Ledger, MandateEngine

from .ports import PaymentProvider, ProviderError

ACTIONS = ("capture_deposit", "void_deposit", "refund_deposit")
TRANSIENT_RETRIES = 2      # a timeout or 5xx is retried with the SAME PayPal-Request-Id
TTL_ENV = "ASK_FIRST_MANDATE_TTL_MIN"
DEFAULT_TTL_MIN = 60       # an owner with a patient answers within the hour, not within 15 minutes
MAX_TTL_MIN = 24 * 60      # a yes is for this decision, today; never a standing permission


def mandate_ttl_s() -> int:
    """How long an unsigned request waits for the owner: ASK_FIRST_MANDATE_TTL_MIN minutes,
    60 by default. A bad value is refused instead of silently replaced."""
    raw = os.environ.get(TTL_ENV, "").strip()
    if not raw:
        return DEFAULT_TTL_MIN * 60
    try:
        minutes = int(raw)
    except ValueError:
        raise ValueError(f"{TTL_ENV} must be a whole number of minutes, got {raw!r}") from None
    if not 1 <= minutes <= MAX_TTL_MIN:
        raise ValueError(f"{TTL_ENV} must be between 1 and {MAX_TTL_MIN} minutes, got {minutes}")
    return minutes * 60


def minutes_left(exp: int, now: float | None = None) -> str:
    """"58 min", "1 h 35 min", "under a minute" or "expired": what a person reads, not a timestamp."""
    left = int(exp) - int(time.time() if now is None else now)
    if left <= 0:
        return "expired"
    if left < 60:
        return "under a minute"
    m = -(-left // 60)                       # round up: a fresh 60-minute mandate reads "60 min"
    return f"{m} min" if m <= 90 else f"{m // 60} h {m % 60} min"


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

    def request(self, action: str, target: str, amount: float, ttl_s: int | None = None,
                agent: str = "front-desk-agent") -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action!r}")
        # A cap is money: whole cents only. The owner reads it as .2f and the PayPal adapter refuses
        # sub-cent amounts, so 9.996 would be signed as "10.00" and could never run as signed.
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or round(amount, 2) != amount:
            raise ValueError(f"amount must be a number of whole cents, got {amount!r}")
        return dict(self._request(agent, action, target, amount, ttl_s=mandate_ttl_s() if ttl_s is None else ttl_s))

    def execute(self, mandate_id: str, action: str, target: str, amount: float) -> dict:
        return self._execute(mandate_id, action, target, amount)

    def describe(self, mandate_id: str) -> str | None:
        """The owner-facing summary, built ONLY from the signed fields, never from model text."""
        m = self._get(mandate_id)
        if not m:
            return None
        left = minutes_left(m["exp"])
        return (f"{m['action']} on {m['recipient']} for at most {m['cap']:.2f}, single use, "
                f"{'expired' if left == 'expired' else 'expires in ' + left}, state {m['_state']}")

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
