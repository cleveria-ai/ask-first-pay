"""In-memory PaymentProvider for tests and offline demos. No network, no credentials."""
from __future__ import annotations

import itertools

from .ports import Authorization, Capture, Order, ProviderError, Refund


class FakeProvider:
    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.orders: dict[str, Order] = {}
        self.auths: dict[str, Authorization] = {}
        self.captures: dict[str, Capture] = {}
        self.refunds: dict[str, Refund] = {}
        self.calls: list[tuple] = []

    def _id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids):04d}"

    def create_order(self, amount: float, currency: str, reference: str) -> Order:
        self.calls.append(("create_order", amount, currency, reference))
        oid = self._id("ORDER")
        order = Order(oid, amount, currency, reference, f"https://sandbox.example/approve/{oid}", "CREATED")
        self.orders[oid] = order
        return order

    def approve(self, order_id: str) -> None:
        """What the payer does in the checkout page; only the fake exposes it."""
        o = self.orders[order_id]
        self.orders[order_id] = Order(o.order_id, o.amount, o.currency, o.reference, o.approve_url, "APPROVED")

    def authorize(self, order_id: str) -> Authorization:
        self.calls.append(("authorize", order_id))
        o = self.orders.get(order_id)
        if o is None or o.status != "APPROVED":
            raise ProviderError("ORDER_NOT_APPROVED", order_id)
        a = Authorization(self._id("AUTH"), order_id, o.amount, o.currency, "CREATED")
        self.auths[a.authorization_id] = a
        return a

    def capture(self, authorization_id: str, amount: float) -> Capture:
        self.calls.append(("capture", authorization_id, amount))
        a = self.auths.get(authorization_id)
        if a is None or a.status != "CREATED":
            raise ProviderError("AUTHORIZATION_ALREADY_CAPTURED" if a else "INVALID_RESOURCE_ID", authorization_id)
        if amount > a.amount:
            raise ProviderError("AMOUNT_EXCEEDS_AUTHORIZATION", f"{amount} > {a.amount}")
        self.auths[authorization_id] = Authorization(a.authorization_id, a.order_id, a.amount, a.currency, "CAPTURED")
        c = Capture(self._id("CAP"), authorization_id, amount, a.currency, "COMPLETED")
        self.captures[c.capture_id] = c
        return c

    def refund(self, capture_id: str, amount: float) -> Refund:
        self.calls.append(("refund", capture_id, amount))
        c = self.captures.get(capture_id)
        if c is None:
            raise ProviderError("INVALID_RESOURCE_ID", capture_id)
        done = sum(r.amount for r in self.refunds.values() if r.capture_id == capture_id)
        if done + amount > c.amount:
            raise ProviderError("REFUND_AMOUNT_EXCEEDED", f"{done + amount} > {c.amount}")
        r = Refund(self._id("REF"), capture_id, amount, c.currency, "COMPLETED")
        self.refunds[r.refund_id] = r
        return r

    def void(self, authorization_id: str) -> Authorization:
        self.calls.append(("void", authorization_id))
        a = self.auths.get(authorization_id)
        if a is None or a.status != "CREATED":
            raise ProviderError("CANNOT_BE_VOIDED", authorization_id)
        v = Authorization(a.authorization_id, a.order_id, a.amount, a.currency, "VOIDED")
        self.auths[authorization_id] = v
        return v
