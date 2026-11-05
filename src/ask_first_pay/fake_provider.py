"""In-memory PaymentProvider for tests and offline demos. No network, no credentials.

It models what the demo stories need from PayPal: the 3-day honor period and 29-day expiry of an
authorization (with an injectable clock), partial captures with `final_capture`, void only before
any capture, refunds only on captured money, and idempotency by `request_id`.
"""
from __future__ import annotations

import time
from dataclasses import asdict

from .ports import Authorization, Capture, Order, ProviderError, Refund

DAY = 86400
HONOR_S = 3 * DAY
EXPIRY_S = 29 * DAY


class FakeProvider:
    def __init__(self, clock=time.time) -> None:
        self.clock = clock
        self._next_id = 1
        self.orders: dict[str, Order] = {}
        self.auths: dict[str, Authorization] = {}
        self.auth_born: dict[str, float] = {}       # authorization_id -> when its honor period started
        self.auth_root: dict[str, float] = {}       # authorization_id -> when the original was created
        self.captures: dict[str, Capture] = {}
        self.refunds: dict[str, Refund] = {}
        self.calls: list[tuple] = []
        self._done: dict[str, object] = {}          # request_id -> result (idempotency)

    def _id(self, prefix: str) -> str:
        n, self._next_id = self._next_id, self._next_id + 1
        return f"{prefix}-{n:04d}"

    def _replay(self, request_id: str):
        return self._done.get(request_id)

    def _set_auth(self, a: Authorization, status: str) -> Authorization:
        b = Authorization(a.authorization_id, a.order_id, a.amount, a.currency, status)
        self.auths[a.authorization_id] = b
        return b

    def _captured(self, authorization_id: str) -> float:
        return sum(c.amount for c in self.captures.values() if c.authorization_id == authorization_id)

    def _check_alive(self, a: Authorization) -> None:
        if self.clock() - self.auth_root[a.authorization_id] > EXPIRY_S:
            self._set_auth(a, "EXPIRED")
            raise ProviderError("AUTHORIZATION_EXPIRED", a.authorization_id)

    def create_order(self, amount: float, currency: str, reference: str) -> Order:
        self.calls.append(("create_order", amount, currency, reference))
        oid = self._id("ORDER")
        order = Order(oid, amount, currency, reference, f"https://sandbox.example/approve/{oid}", "CREATED")
        self.orders[oid] = order
        return order

    def approve(self, order_id: str) -> None:
        """What the payer does on the checkout page; only the fake exposes it."""
        o = self.orders[order_id]
        self.orders[order_id] = Order(o.order_id, o.amount, o.currency, o.reference, o.approve_url, "APPROVED")

    def authorize(self, order_id: str) -> Authorization:
        self.calls.append(("authorize", order_id))
        o = self.orders.get(order_id)
        if o is None or o.status != "APPROVED":
            raise ProviderError("ORDER_NOT_APPROVED", order_id)
        a = Authorization(self._id("AUTH"), order_id, o.amount, o.currency, "CREATED")
        self.auths[a.authorization_id] = a
        self.auth_born[a.authorization_id] = self.auth_root[a.authorization_id] = self.clock()
        self.orders[order_id] = Order(o.order_id, o.amount, o.currency, o.reference, o.approve_url, "COMPLETED")
        return a

    def reauthorize(self, authorization_id: str, request_id: str) -> Authorization:
        if (r := self._replay(request_id)) is not None:
            return r
        self.calls.append(("reauthorize", authorization_id, request_id))
        a = self.auths.get(authorization_id)
        if a is None or a.status != "CREATED":
            raise ProviderError("CANNOT_BE_REAUTHORIZED", authorization_id)
        self._check_alive(a)
        if self.clock() - self.auth_born[authorization_id] <= HONOR_S:
            raise ProviderError("REAUTHORIZATION_TOO_SOON", "still inside the 3-day honor period")
        n = Authorization(self._id("AUTH"), a.order_id, a.amount, a.currency, "CREATED")
        self.auths[n.authorization_id] = n
        self.auth_born[n.authorization_id] = self.clock()
        self.auth_root[n.authorization_id] = self.auth_root[authorization_id]
        self._set_auth(a, "VOIDED")
        self._done[request_id] = n
        return n

    def capture(self, authorization_id: str, amount: float, request_id: str,
                final_capture: bool = True) -> Capture:
        if (r := self._replay(request_id)) is not None:
            return r
        self.calls.append(("capture", authorization_id, amount, request_id, final_capture))
        a = self.auths.get(authorization_id)
        if a is None:
            raise ProviderError("INVALID_RESOURCE_ID", authorization_id)
        if a.status not in ("CREATED", "PARTIALLY_CAPTURED"):
            raise ProviderError("AUTHORIZATION_ALREADY_CAPTURED" if "CAPTURED" in a.status else
                                f"AUTHORIZATION_{a.status}", authorization_id)
        self._check_alive(a)
        if self.clock() - self.auth_born[authorization_id] > HONOR_S:
            raise ProviderError("HONOR_PERIOD_EXPIRED", "reauthorize before capturing")
        if self._captured(authorization_id) + amount > a.amount + 1e-9:
            raise ProviderError("AMOUNT_EXCEEDS_AUTHORIZATION", f"{amount} > remaining")
        c = Capture(self._id("CAP"), authorization_id, amount, a.currency, "COMPLETED")
        self.captures[c.capture_id] = c
        self._set_auth(a, "CAPTURED" if final_capture else "PARTIALLY_CAPTURED")
        self._done[request_id] = c
        return c

    def refund(self, capture_id: str, amount: float, request_id: str) -> Refund:
        if (r := self._replay(request_id)) is not None:
            return r
        self.calls.append(("refund", capture_id, amount, request_id))
        c = self.captures.get(capture_id)
        if c is None or c.status not in ("COMPLETED", "PARTIALLY_REFUNDED"):
            raise ProviderError("CAPTURE_NOT_REFUNDABLE" if c else "INVALID_RESOURCE_ID", capture_id)
        done = sum(r.amount for r in self.refunds.values() if r.capture_id == capture_id)
        if done + amount > c.amount + 1e-9:
            raise ProviderError("REFUND_AMOUNT_EXCEEDED", f"{done + amount} > {c.amount}")
        r = Refund(self._id("REF"), capture_id, amount, c.currency, "COMPLETED")
        self.refunds[r.refund_id] = r
        full = abs(done + amount - c.amount) < 1e-9
        self.captures[capture_id] = Capture(c.capture_id, c.authorization_id, c.amount, c.currency,
                                            "REFUNDED" if full else "PARTIALLY_REFUNDED")
        self._done[request_id] = r
        return r

    def void(self, authorization_id: str, request_id: str) -> Authorization:
        if (r := self._replay(request_id)) is not None:
            return r
        self.calls.append(("void", authorization_id, request_id))
        a = self.auths.get(authorization_id)
        if a is None or a.status != "CREATED":
            raise ProviderError("CANNOT_BE_VOIDED", authorization_id)
        v = self._set_auth(a, "VOIDED")
        self._done[request_id] = v
        return v

    # ---- persistence (the demo's optional SQLite store) -----------------------------------
    _KINDS = {"Order": Order, "Authorization": Authorization, "Capture": Capture, "Refund": Refund}

    def to_dict(self) -> dict:
        """Everything a restart needs, as JSON-friendly data (not the `calls` spy list)."""
        box = lambda v: {"kind": type(v).__name__, **asdict(v)}                     # noqa: E731
        return {"next_id": self._next_id,
                "orders": {k: asdict(v) for k, v in self.orders.items()},
                "auths": {k: asdict(v) for k, v in self.auths.items()},
                "auth_born": dict(self.auth_born), "auth_root": dict(self.auth_root),
                "captures": {k: asdict(v) for k, v in self.captures.items()},
                "refunds": {k: asdict(v) for k, v in self.refunds.items()},
                "done": {k: box(v) for k, v in self._done.items()}}

    def load_dict(self, d: dict) -> None:
        self._next_id = int(d["next_id"])
        self.orders = {k: Order(**v) for k, v in d["orders"].items()}
        self.auths = {k: Authorization(**v) for k, v in d["auths"].items()}
        self.auth_born, self.auth_root = dict(d["auth_born"]), dict(d["auth_root"])
        self.captures = {k: Capture(**v) for k, v in d["captures"].items()}
        self.refunds = {k: Refund(**v) for k, v in d["refunds"].items()}
        self._done = {k: self._KINDS[v.pop("kind")](**v) for k, v in
                      ((k, dict(v)) for k, v in d["done"].items())}
