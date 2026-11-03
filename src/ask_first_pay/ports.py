"""Ports: the only seams between the pieces of Ask First Pay.

Every piece (PayPal adapter, agent, demo app) codes against these types, never against another
piece's internals. Change this file only through docs/CONTRACT.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Order:
    order_id: str
    amount: float          # major units, e.g. 10.00
    currency: str          # ISO 4217, e.g. "USD"
    reference: str         # our booking id; PayPal's purchase_units[0].reference_id
    approve_url: str       # where the payer approves the deposit (sandbox checkout)
    status: str            # CREATED | APPROVED | AUTHORIZED | COMPLETED | VOIDED


@dataclass(frozen=True)
class Authorization:
    authorization_id: str
    order_id: str
    amount: float
    currency: str
    status: str            # CREATED | CAPTURED | VOIDED | EXPIRED


@dataclass(frozen=True)
class Capture:
    capture_id: str
    authorization_id: str
    amount: float
    currency: str
    status: str            # COMPLETED | PENDING | DECLINED


@dataclass(frozen=True)
class Refund:
    refund_id: str
    capture_id: str
    amount: float
    currency: str
    status: str            # COMPLETED | PENDING | CANCELLED


@dataclass
class ProviderError(Exception):
    code: str              # provider error name, e.g. "AUTHORIZATION_EXPIRED"
    message: str = ""
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class PaymentProvider(Protocol):
    """A deposit is created and authorized when the customer books; money moves only on
    capture or refund, and those two are reachable only through the mandate gate (gate.py)."""

    def create_order(self, amount: float, currency: str, reference: str) -> Order: ...

    def authorize(self, order_id: str) -> Authorization: ...

    def capture(self, authorization_id: str, amount: float) -> Capture: ...

    def refund(self, capture_id: str, amount: float) -> Refund: ...

    def void(self, authorization_id: str) -> Authorization: ...
