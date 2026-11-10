"""PayPalProvider: the PaymentProvider port against the PayPal REST API.

Sandbox by default. Production needs both environment="production" and allow_production=True.
Credentials come only from PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (or explicit arguments).

Where the payer comes back: every order carries `payment_source.paypal.experience_context` with
`return_url` (`<ASK_FIRST_PUBLIC_URL>/chat/return`) and `cancel_url` (`.../chat/cancel`); PayPal
appends `?token=<order id>`. `shipping_preference: NO_SHIPPING` because a deposit ships nothing,
and `user_action: CONTINUE` because nothing is charged when the payer clicks: we authorize after
the redirect and capture (maybe never) later. Orders v2 spec, `paypal_wallet_experience_context`
(https://developer.paypal.com/api/orders/v2/schema.json): CONTINUE is for "when the final amount
is not known when the checkout flow is initiated and you want to redirect the customer to the
merchant page without processing the payment"; PAY_NOW processes "immediately".
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from ..business import business_name, mark_fictional
from ..ports import Authorization, Capture, Order, ProviderError, Refund

BASES = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "production": "https://api-m.paypal.com",
}
TOKEN_MARGIN_S = 60
DEFAULT_PUBLIC_URL = "http://localhost:8000"     # where the demo runs; ASK_FIRST_PUBLIC_URL overrides it


def format_amount(amount: float) -> str:
    """Exactly two decimals as a string; more than two decimals is rejected, never rounded."""
    try:
        d = Decimal(repr(float(amount))) if not isinstance(amount, Decimal) else amount
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ProviderError("INVALID_AMOUNT", f"not a number: {amount!r}") from e
    if not d.is_finite() or d <= 0:
        raise ProviderError("INVALID_AMOUNT", f"amount must be positive: {amount!r}")
    if d != d.quantize(Decimal("0.01")):
        raise ProviderError("INVALID_AMOUNT", f"more than two decimals: {amount!r}")
    return f"{d.quantize(Decimal('0.01'))}"


def _derive_id(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:36]


class PayPalProvider:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, *,
                 environment: str = "sandbox", allow_production: bool = False,
                 transport: httpx.BaseTransport | None = None, timeout: float = 20.0,
                 clock=time.time, public_url: str | None = None, brand_name: str | None = None) -> None:
        if environment not in BASES:
            raise ValueError(f"unknown environment {environment!r}")
        if environment == "production" and not allow_production:
            raise ValueError("production requires allow_production=True")
        self.environment = environment
        self._base = BASES[environment]
        self._client_id = client_id or os.environ.get("PAYPAL_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("PAYPAL_CLIENT_SECRET", "")
        self._http = httpx.Client(transport=transport, timeout=timeout)
        self._clock = clock
        base = (public_url or os.environ.get("ASK_FIRST_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")
        self.return_url, self.cancel_url = f"{base}/chat/return", f"{base}/chat/cancel"
        # The business from ASK_FIRST_BUSINESS (ASK_FIRST_BRAND or the argument override it). The
        # "(fictional)" marker goes on after every source is resolved, inside PayPal's 127 chars.
        self.brand_name = mark_fictional(brand_name or os.environ.get("ASK_FIRST_BRAND") or business_name(), 127)
        self._token: str | None = None
        self._token_until = 0.0
        self._auth_info: dict[str, tuple[str, str, str]] = {}   # auth id -> (order_id, amount, currency)
        self._cap_currency: dict[str, str] = {}

    # -- transport -------------------------------------------------------------------------
    def _send(self, method: str, path: str, *, json: Any = None, request_id: str | None = None,
              auth: tuple[str, str] | None = None, data: dict | None = None) -> httpx.Response:
        headers = {}
        if auth is None:
            headers["Authorization"] = f"Bearer {self._get_token()}"
        if request_id:
            headers["PayPal-Request-Id"] = request_id
        if json is not None:
            headers["Prefer"] = "return=representation"
        try:
            r = self._http.request(method, self._base + path, json=json, data=data,
                                   headers=headers, auth=auth)
        except httpx.HTTPError as e:   # timeouts, connection errors
            raise ProviderError("TRANSIENT", f"{type(e).__name__}: {e}", transient=True) from e
        if r.status_code >= 500:
            raise ProviderError("TRANSIENT", f"HTTP {r.status_code}", transient=True)
        if r.status_code >= 400:
            try:
                body = r.json()
            except ValueError:
                body = {}
            name = body.get("name") or body.get("error") or f"HTTP_{r.status_code}"
            msg = body.get("message") or body.get("error_description") or ""
            raise ProviderError(str(name), str(msg), details={"status": r.status_code,
                                                              "details": body.get("details", [])})
        return r

    def _get_token(self) -> str:
        if self._token and self._clock() < self._token_until:
            return self._token
        if not (self._client_id and self._client_secret):
            raise ProviderError("NO_CREDENTIALS", "set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET")
        r = self._send("POST", "/v1/oauth2/token", auth=(self._client_id, self._client_secret),
                       data={"grant_type": "client_credentials"})
        body = r.json()
        self._token = body["access_token"]
        self._token_until = self._clock() + max(0, int(body.get("expires_in", 300)) - TOKEN_MARGIN_S)
        return self._token

    # -- helpers ---------------------------------------------------------------------------
    @staticmethod
    def _money(m: dict) -> tuple[float, str]:
        return float(m["value"]), m["currency_code"]

    def _remember_auth(self, a: dict, order_id: str) -> Authorization:
        amount, cur = self._money(a["amount"])
        self._auth_info[a["id"]] = (order_id, a["amount"]["value"], cur)
        return Authorization(a["id"], order_id, amount, cur, a["status"])

    def _currency_of_auth(self, authorization_id: str) -> str:
        if authorization_id not in self._auth_info:
            a = self._send("GET", f"/v2/payments/authorizations/{authorization_id}").json()
            self._remember_auth(a, "")
        return self._auth_info[authorization_id][2]

    def _currency_of_capture(self, capture_id: str) -> str:
        if capture_id not in self._cap_currency:
            c = self._send("GET", f"/v2/payments/captures/{capture_id}").json()
            self._cap_currency[capture_id] = c["amount"]["currency_code"]
        return self._cap_currency[capture_id]

    # -- port ------------------------------------------------------------------------------
    def experience_context(self) -> dict:
        return {"brand_name": self.brand_name, "shipping_preference": "NO_SHIPPING",
                "user_action": "CONTINUE", "return_url": self.return_url, "cancel_url": self.cancel_url}

    def create_order(self, amount: float, currency: str, reference: str,
                     request_id: str | None = None) -> Order:
        value = format_amount(amount)
        body = {"intent": "AUTHORIZE", "purchase_units": [
            {"reference_id": reference, "amount": {"currency_code": currency, "value": value}}],
            "payment_source": {"paypal": {"experience_context": self.experience_context()}}}
        # Never derived from `reference`: booking ids restart at booking-1 in every conversation,
        # and PayPal would answer a second customer with the first one's order.
        r = self._send("POST", "/v2/checkout/orders", json=body,
                       request_id=request_id or str(uuid.uuid4())).json()
        links = {link.get("rel"): link.get("href") for link in r.get("links", [])}
        url = links.get("payer-action") or links.get("approve") or ""
        return Order(r["id"], float(value), currency, reference, url, r["status"])

    def authorize(self, order_id: str) -> Authorization:
        r = self._send("POST", f"/v2/checkout/orders/{order_id}/authorize", json={},
                       request_id=_derive_id("authorize", order_id)).json()
        try:
            a = r["purchase_units"][0]["payments"]["authorizations"][0]
        except (KeyError, IndexError) as e:
            raise ProviderError("MALFORMED_RESPONSE", "no authorization in response") from e
        return self._remember_auth(a, r.get("id", order_id))

    def reauthorize(self, authorization_id: str, request_id: str) -> Authorization:
        r = self._send("POST", f"/v2/payments/authorizations/{authorization_id}/reauthorize",
                       json={}, request_id=request_id).json()
        order_id = self._auth_info.get(authorization_id, ("",))[0]
        if "amount" not in r:   # minimal response: the amount is unchanged
            _, value, cur = self._auth_info[authorization_id]
            r["amount"] = {"value": value, "currency_code": cur}
        return self._remember_auth(r, order_id)

    def capture(self, authorization_id: str, amount: float, request_id: str,
                final_capture: bool = True) -> Capture:
        value = format_amount(amount)
        cur = self._currency_of_auth(authorization_id)
        r = self._send("POST", f"/v2/payments/authorizations/{authorization_id}/capture",
                       json={"amount": {"currency_code": cur, "value": value},
                             "final_capture": final_capture}, request_id=request_id).json()
        self._cap_currency[r["id"]] = cur
        return Capture(r["id"], authorization_id, float(value), cur, r["status"])

    def refund(self, capture_id: str, amount: float, request_id: str) -> Refund:
        value = format_amount(amount)
        cur = self._currency_of_capture(capture_id)
        r = self._send("POST", f"/v2/payments/captures/{capture_id}/refund",
                       json={"amount": {"currency_code": cur, "value": value}},
                       request_id=request_id).json()
        return Refund(r["id"], capture_id, float(value), cur, r["status"])

    def void(self, authorization_id: str, request_id: str) -> Authorization:
        r = self._send("POST", f"/v2/payments/authorizations/{authorization_id}/void",
                       request_id=request_id)
        if authorization_id not in self._auth_info:
            self._currency_of_auth(authorization_id)   # one GET to learn amount and currency
        order_id, value, cur = self._auth_info[authorization_id]
        if r.content:   # some responses carry the authorization; the status is VOIDED either way
            try:
                order_id = r.json().get("order_id", order_id)
            except ValueError:
                pass
        self._auth_info[authorization_id] = (order_id, value, cur)
        return Authorization(authorization_id, order_id, float(value), cur, "VOIDED")
