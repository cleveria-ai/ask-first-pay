import json

import httpx
import pytest

from ask_first_pay.paypal import PayPalProvider
from ask_first_pay.ports import ProviderError

from .fakepaypal import MockPayPal

AUTH = "3C679366HH908993F"


def make(mock=None, **kw):
    mock = mock or MockPayPal()
    p = PayPalProvider("cid", "secret", transport=httpx.MockTransport(mock), **kw)
    return p, mock


def body(req):
    return json.loads(req.content)


def test_create_order_payload_and_payer_link():
    p, m = make(public_url="https://shop.example", brand_name="Bright Smile Dental")
    o = p.create_order(10.0, "USD", "booking-42")
    req = m.writes()[0]
    assert req.url.path == "/v2/checkout/orders"
    assert body(req) == {"intent": "AUTHORIZE", "purchase_units": [
        {"reference_id": "booking-42", "amount": {"currency_code": "USD", "value": "10.00"}}],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": "Bright Smile Dental", "shipping_preference": "NO_SHIPPING", "user_action": "CONTINUE",
            "return_url": "https://shop.example/chat/return", "cancel_url": "https://shop.example/chat/cancel"}}}}
    assert req.headers["PayPal-Request-Id"]
    assert o.approve_url.endswith("token=5O190127TN364715T") and o.reference == "booking-42"


def test_create_order_accepts_approve_rel():
    m = MockPayPal()
    orig = m.__call__

    def handler(req):
        r = orig(req)
        if req.url.path == "/v2/checkout/orders":
            d = json.loads(r.content)
            for link in d["links"]:
                if link["rel"] == "payer-action":
                    link["rel"] = "approve"
            return httpx.Response(201, json=d)
        return r
    p = PayPalProvider("cid", "secret", transport=httpx.MockTransport(handler))
    assert "checkoutnow" in p.create_order(10.0, "USD", "b").approve_url


def test_authorize_reads_nested_authorization():
    p, _ = make()
    a = p.authorize("5O190127TN364715T")
    assert (a.authorization_id, a.order_id, a.amount, a.status) == (AUTH, "5O190127TN364715T", 10.0, "CREATED")


def test_token_is_cached_and_basic_auth_used():
    p, m = make()
    p.create_order(1.0, "USD", "a")
    p.create_order(2.0, "USD", "b")
    assert m.token_calls == 1
    tok = m.requests[0]
    assert tok.headers["Authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in tok.content
    assert m.requests[1].headers["Authorization"] == "Bearer A21AAtest"


def test_token_refreshed_after_expiry():
    now = [0.0]
    p, m = make(clock=lambda: now[0])
    p.create_order(1.0, "USD", "a")
    now[0] = 32400  # past expires_in minus margin
    p.create_order(1.0, "USD", "b")
    assert m.token_calls == 2


def test_capture_request_id_and_body():
    p, m = make()
    p.authorize("o")
    c = p.capture(AUTH, 10.0, "jti-1", final_capture=False)
    req = m.writes()[-1]
    assert req.url.path == f"/v2/payments/authorizations/{AUTH}/capture"
    assert body(req) == {"amount": {"currency_code": "USD", "value": "10.00"}, "final_capture": False}
    assert (c.capture_id, c.status, c.authorization_id) == ("2GG279541U471931P", "COMPLETED", AUTH)


def test_request_id_header_on_capture_refund_void():
    p, m = make()
    p.authorize("o")
    p.capture(AUTH, 10.0, "jti-cap")
    p.refund("2GG279541U471931P", 4.0, "jti-ref")
    p.void(AUTH, "jti-void")
    w = m.writes()
    assert w[-3].headers["PayPal-Request-Id"] == "jti-cap" and w[-3].url.path.endswith("/capture")
    assert w[-2].headers["PayPal-Request-Id"] == "jti-ref" and w[-2].url.path.endswith("/refund")
    assert w[-1].headers["PayPal-Request-Id"] == "jti-void" and w[-1].url.path.endswith("/void")


def test_request_id_header_on_reauthorize():
    p, m = make()
    a = p.reauthorize(AUTH, "jti-re")
    assert m.writes()[-1].headers["PayPal-Request-Id"] == "jti-re"
    assert a.authorization_id == "7NR5STUB0000" and a.amount == 10.0


def test_void_204_empty_body_returns_voided():
    p, m = make()
    p.authorize("o")
    a = p.void(AUTH, "jti-void")
    assert a.status == "VOIDED" and a.authorization_id == AUTH and a.amount == 10.0


def test_void_unknown_authorization_fetches_it_then_voided():
    p, m = make()
    a = p.void(AUTH, "jti-void")
    assert a.status == "VOIDED" and a.currency == "USD"
    assert [r.method for r in m.requests if r.url.path != "/v1/oauth2/token"] == ["POST", "GET"]


def test_refund_body():
    p, m = make()
    r = p.refund("2GG279541U471931P", 4.0, "jti-ref")
    assert body(m.writes()[-1]) == {"amount": {"currency_code": "USD", "value": "4.00"}}
    assert r.amount == 4.0 and r.status == "COMPLETED"


def test_production_without_flag_raises():
    with pytest.raises(ValueError):
        PayPalProvider("a", "b", environment="production")
    with pytest.raises(ValueError):
        PayPalProvider("a", "b", environment="production", allow_production=False)
    assert PayPalProvider("a", "b", environment="production", allow_production=True)._base == "https://api-m.paypal.com"
    assert PayPalProvider("a", "b")._base == "https://api-m.sandbox.paypal.com"


def test_amount_sent_as_two_decimal_string():
    p, m = make()
    p.create_order(10, "USD", "a")
    p.create_order(0.5, "USD", "b")
    p.create_order(19.9, "USD", "c")
    vals = [body(r)["purchase_units"][0]["amount"]["value"] for r in m.writes()]
    assert vals == ["10.00", "0.50", "19.90"]


@pytest.mark.parametrize("bad", [10.001, 0.005, 1.234, 0.1 + 0.2, 0, -1.0, float("nan")])
def test_amount_rejected_not_rounded(bad):
    p, m = make()
    p.authorize("o")
    n = len(m.requests)
    for call in (lambda: p.create_order(bad, "USD", "x"),
                 lambda: p.capture(AUTH, bad, "r1"),
                 lambda: p.refund("C1", bad, "r2")):
        with pytest.raises(ProviderError) as e:
            call()
        assert e.value.code == "INVALID_AMOUNT"
    assert len(m.requests) == n   # nothing was sent


def test_transient_timeout_then_retry_same_request_id():
    p, m = make()
    p.authorize("o")
    m.fail_next = [httpx.ReadTimeout("slow")]
    with pytest.raises(ProviderError) as e:
        p.capture(AUTH, 10.0, "jti-1")
    assert e.value.code == "TRANSIENT" and e.value.transient
    c = p.capture(AUTH, 10.0, "jti-1")
    caps = [r for r in m.requests if r.url.path.endswith("/capture")]
    assert len(caps) == 2
    assert caps[0].headers["PayPal-Request-Id"] == caps[1].headers["PayPal-Request-Id"] == "jti-1"
    assert c.status == "COMPLETED"


def test_transient_on_5xx():
    p, m = make()
    m.fail_next = [(503, {"name": "SERVICE_UNAVAILABLE"})]
    with pytest.raises(ProviderError) as e:
        p.create_order(1.0, "USD", "a")
    assert e.value.code == "TRANSIENT" and e.value.transient


def test_paypal_error_maps_to_provider_error():
    p, m = make()
    m.fail_next = [(422, {"name": "UNPROCESSABLE_ENTITY", "message": "x",
                          "details": [{"issue": "AUTHORIZATION_ALREADY_CAPTURED"}]})]
    with pytest.raises(ProviderError) as e:
        p.capture(AUTH, 10.0, "r")
    assert e.value.code == "UNPROCESSABLE_ENTITY" and not e.value.transient
    assert e.value.details["details"][0]["issue"] == "AUTHORIZATION_ALREADY_CAPTURED"


def test_missing_credentials_raises(monkeypatch):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    p = PayPalProvider(transport=httpx.MockTransport(MockPayPal()))
    with pytest.raises(ProviderError) as e:
        p.create_order(1.0, "USD", "a")
    assert e.value.code == "NO_CREDENTIALS"
