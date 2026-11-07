"""Ports: the only seams between the pieces of Ask First Pay.

Every piece (PayPal adapter, agent, demo app) codes against these types, never against another
piece's internals. Change this file only through docs/CONTRACT.md.

Money model (PayPal Orders v2 with intent AUTHORIZE):
  book      -> create_order, payer approves, authorize      (money held, nothing moved)
  no-show   -> capture (within the 3-day honor period, or reauthorize first; the authorization
               expires after 29 days)
  cancel    -> void (nothing was captured, so there is nothing to refund)
  goodwill  -> refund, only on a COMPLETED / PARTIALLY_REFUNDED capture

Amounts are major units as float at this boundary because the mandate engine caps with floats;
adapters must send PayPal a string with exactly two decimals (USD) and must reject amounts with
more than two decimals instead of rounding them.

`request_id` is the idempotency key. The gate passes the mandate's `jti`, so a retry of the same
mandate can never move money twice, and two different mandates for equal amounts are never
confused. Adapters send it as the `PayPal-Request-Id` header.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Order:
    order_id: str
    amount: float
    currency: str          # ISO 4217, e.g. "USD"
    reference: str         # our booking id; PayPal's purchase_units[0].reference_id
    approve_url: str       # the payer link: rel "payer-action" or "approve" in PayPal's links
    status: str            # CREATED | SAVED | APPROVED | PAYER_ACTION_REQUIRED | COMPLETED | VOIDED


@dataclass(frozen=True)
class Authorization:
    authorization_id: str
    order_id: str
    amount: float
    currency: str
    status: str            # CREATED | CAPTURED | PARTIALLY_CAPTURED | VOIDED | EXPIRED | DENIED | PENDING


@dataclass(frozen=True)
class Capture:
    capture_id: str
    authorization_id: str
    amount: float
    currency: str
    status: str            # COMPLETED | PENDING | DECLINED | FAILED | REFUNDED | PARTIALLY_REFUNDED


@dataclass(frozen=True)
class Refund:
    refund_id: str
    capture_id: str
    amount: float
    currency: str
    status: str            # COMPLETED | PENDING | FAILED | CANCELLED


@dataclass
class ProviderError(Exception):
    code: str              # PayPal error name, e.g. "AUTHORIZATION_EXPIRED"
    message: str = ""
    transient: bool = False   # True for timeouts and 5xx: the money may or may not have moved
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class PaymentProvider(Protocol):
    """Money moves only on capture, refund and void, and those are reachable only through the
    mandate gate (gate.py). Everything else holds or describes money."""

    def create_order(self, amount: float, currency: str, reference: str,
                     request_id: str | None = None) -> Order:
        """`request_id` is the order's own idempotency key (PayPal-Request-Id): unique per order,
        stored by the caller so a retry of the SAME order creation sends it again. None means a
        fresh random id (never one derived from `reference`, which repeats across conversations)."""
        ...

    def authorize(self, order_id: str) -> Authorization: ...

    def reauthorize(self, authorization_id: str, request_id: str) -> Authorization: ...

    def capture(self, authorization_id: str, amount: float, request_id: str,
                final_capture: bool = True) -> Capture: ...

    def refund(self, capture_id: str, amount: float, request_id: str) -> Refund: ...

    def void(self, authorization_id: str, request_id: str) -> Authorization: ...
