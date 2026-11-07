"""N8: the create-order request id (B1) and the payer's way back (B2), against a mocked PayPal."""
import json

import httpx
from ask_first import generate_pair

from ask_first_pay.agent.state import AgentState
from ask_first_pay.agent.tools import Toolbox
from ask_first_pay.gate import HoldDesk, make_engine, split
from ask_first_pay.paypal import PayPalProvider

from .fakepaypal import MockPayPal


def provider(**kw):
    mock = MockPayPal()
    return PayPalProvider("cid", "secret", transport=httpx.MockTransport(mock), **kw), mock


def toolbox(p, tmp_path, name):
    engine = make_engine(p, generate_pair()[1], str(tmp_path / f"{name}.jsonl"))
    gate, _ = split(engine)
    return Toolbox(AgentState(), gate, HoldDesk(p))


def order_posts(mock):
    return [r for r in mock.writes() if r.url.path == "/v2/checkout/orders"]


def test_paypal_create_order_request_id_differs_across_fresh_providers_for_the_same_booking_id(tmp_path):
    """Two conversations (or two restarts) each have a booking-1: PayPal must see two orders."""
    ids = []
    for n in (1, 2):
        p, mock = provider()
        box = toolbox(p, tmp_path, f"l{n}")
        assert box.call("book_slot", {"customer": "Ana", "slot": "2026-11-16 09:00"})["booking_id"] == "booking-1"
        assert "order_id" in box.call("create_deposit_order", {"booking_id": "booking-1"})
        (req,) = order_posts(mock)
        assert json.loads(req.content)["purchase_units"][0]["reference_id"] == "booking-1"
        ids.append(req.headers["PayPal-Request-Id"])
    assert ids[0] != ids[1]


def test_paypal_create_order_request_id_is_reused_when_the_same_order_is_retried(tmp_path):
    p, mock = provider()
    box = toolbox(p, tmp_path, "l")
    box.call("book_slot", {"customer": "Ana", "slot": "2026-11-16 09:00"})
    mock.fail_next.append(httpx.ReadTimeout("timed out"))            # PayPal may or may not have it
    first = box.call("create_deposit_order", {"booking_id": "booking-1"})
    assert first["provider_error"] == "TRANSIENT" and first["transient"]
    second = box.call("create_deposit_order", {"booking_id": "booking-1"})
    assert second["order_id"] == "5O190127TN364715T"
    sent = [r.headers["PayPal-Request-Id"] for r in mock.requests if r.url.path == "/v2/checkout/orders"]
    assert len(sent) == 2 and sent[0] == sent[1]
    # ...and a second booking in the same conversation gets its own key.
    box.call("book_slot", {"customer": "Bo", "slot": "2026-11-16 11:30"})
    box.call("create_deposit_order", {"booking_id": "booking-2"})
    assert order_posts(mock)[-1].headers["PayPal-Request-Id"] != sent[0]


def test_paypal_create_order_request_id_without_caller_key_is_random_never_derived():
    p, mock = provider()
    p.create_order(10.0, "USD", "booking-1")
    p.create_order(10.0, "USD", "booking-1")
    a, b = (r.headers["PayPal-Request-Id"] for r in order_posts(mock))
    assert a != b
    p.create_order(10.0, "USD", "booking-1", request_id="caller-key-1")
    assert order_posts(mock)[-1].headers["PayPal-Request-Id"] == "caller-key-1"


def test_paypal_experience_context_has_return_url_and_no_shipping(monkeypatch):
    monkeypatch.setenv("ASK_FIRST_PUBLIC_URL", "https://demo.example/")
    monkeypatch.delenv("ASK_FIRST_BRAND", raising=False)
    monkeypatch.delenv("ASK_FIRST_BUSINESS", raising=False)
    p, mock = provider()
    o = p.create_order(10.0, "USD", "booking-1")
    ctx = json.loads(order_posts(mock)[0].content)["payment_source"]["paypal"]["experience_context"]
    assert ctx["return_url"] == "https://demo.example/chat/return"
    assert ctx["cancel_url"] == "https://demo.example/chat/cancel"
    assert ctx["shipping_preference"] == "NO_SHIPPING"
    assert ctx["user_action"] == "CONTINUE"                 # nothing is charged on PayPal's button
    assert ctx["brand_name"] == "Clínica Bahía Imaginaria (fictional)"    # the default fictional business
    assert o.approve_url.startswith("https://www.sandbox.paypal.com/checkoutnow?token=")


def test_paypal_experience_context_brand_and_url_are_configurable(monkeypatch):
    monkeypatch.delenv("ASK_FIRST_PUBLIC_URL", raising=False)
    p, mock = provider(brand_name="Clinica Sonrisa", public_url="http://127.0.0.1:9000")
    p.create_order(10.0, "USD", "b")
    ctx = json.loads(order_posts(mock)[0].content)["payment_source"]["paypal"]["experience_context"]
    assert ctx["brand_name"] == "Clinica Sonrisa" and ctx["return_url"] == "http://127.0.0.1:9000/chat/return"
    q, mock2 = provider()
    q.create_order(10.0, "USD", "b")
    ctx2 = json.loads(order_posts(mock2)[0].content)["payment_source"]["paypal"]["experience_context"]
    assert ctx2["return_url"] == "http://localhost:8000/chat/return"
