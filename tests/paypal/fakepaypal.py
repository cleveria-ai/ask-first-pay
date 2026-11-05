"""A tiny in-process PayPal sandbox for tests: httpx.MockTransport handler + request log."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

FIX = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text())


class MockPayPal:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.fail_next: list[object] = []   # items: httpx.Exception instance or (status, body)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        p = req.url.path
        if p == "/v1/oauth2/token":
            self.token_calls += 1
            return httpx.Response(200, json=fixture("token.json"))
        if self.fail_next:
            f = self.fail_next.pop(0)
            if isinstance(f, Exception):
                raise f
            return httpx.Response(f[0], json=f[1])
        if p == "/v2/checkout/orders":
            return httpx.Response(201, json=fixture("order_created.json"))
        if p.endswith("/authorize") and "/checkout/orders/" in p:
            return httpx.Response(201, json=fixture("order_authorized.json"))
        if p.endswith("/reauthorize"):
            return httpx.Response(201, json=fixture("reauthorized.json"))
        if p.endswith("/capture"):
            return httpx.Response(201, json=fixture("capture.json"))
        if p.endswith("/refund"):
            return httpx.Response(201, json=fixture("refund.json"))
        if p.endswith("/void"):
            return httpx.Response(204)
        if "/v2/payments/authorizations/" in p and req.method == "GET":
            return httpx.Response(200, json=fixture("authorization.json"))
        if "/v2/payments/captures/" in p and req.method == "GET":
            return httpx.Response(200, json=fixture("capture.json"))
        return httpx.Response(404, json={"name": "INVALID_RESOURCE_ID", "message": p})

    def writes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST" and r.url.path != "/v1/oauth2/token"]
