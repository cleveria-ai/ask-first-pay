"""The demo's PayPal webhook receiver: the checkout approval arrives as a signed webhook, not as
the customer saying "I paid". A webhook can hold a deposit; it can never move money."""
import pytest

from ask_first_pay.demo import create_app
from ask_first_pay.paypal.webhooks import WebhookSimulator


def book(demo, slot="Mon 16 Nov 09:00"):
    demo.client.post("/chat/send", data={"message": f"book {slot}"})
    return list(demo.provider.orders)[-1]


def held(demo):
    return [b for s in demo.state.front.conversations for b in s.bookings.values() if b["status"] == "deposit_held"]


def test_checkout_approval_reaches_the_agent_as_a_verified_webhook(demo):
    oid = book(demo)
    demo.client.post(f"/checkout/{oid}/approve")
    events = demo.client.get("/webhooks/paypal/events").json()
    assert events["simulated"] and [e["event_type"] for e in events["events"]] == ["CHECKOUT.ORDER.APPROVED"]
    assert events["events"][0]["outcome"] == "deposit_held"
    assert any("PayPal webhook: the customer approved" in m.text for m in demo.state.front.messages)
    assert demo.calls("authorize") and not demo.calls("capture")


def test_a_signed_order_approved_posted_over_http_holds_the_deposit_once(demo):
    oid = book(demo)
    demo.provider.approve(oid)                  # the payer approved on PayPal's page
    headers, body = demo.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": oid}, "WH-EVT-A")
    r = demo.client.post("/webhooks/paypal", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["outcome"] == "deposit_held"
    again = demo.client.post("/webhooks/paypal", content=body, headers=headers)
    assert again.json()["outcome"] == "duplicate"
    assert len(demo.calls("authorize")) == 1 and len(held(demo)) == 1


def test_a_forged_webhook_is_refused_and_changes_nothing(demo):
    oid = book(demo)
    demo.provider.approve(oid)
    forger = WebhookSimulator(webhook_id=demo.state.webhook_sim.webhook_id)   # right URL, wrong key
    headers, body = forger.event("CHECKOUT.ORDER.APPROVED", {"id": oid})
    r = demo.client.post("/webhooks/paypal", content=body, headers=headers)
    assert r.status_code == 400 and r.json()["reason"] == "bad_signature"
    unsigned = demo.client.post("/webhooks/paypal", content=body, headers={"content-type": "application/json"})
    assert unsigned.status_code == 400 and unsigned.json()["reason"] == "missing_header"
    assert not demo.calls("authorize") and not held(demo)


def test_no_webhook_event_moves_money_even_when_genuine(demo):
    oid = book(demo)
    demo.client.post(f"/checkout/{oid}/approve")
    auth = held(demo)[0]["authorization_id"]
    sim = demo.state.webhook_sim
    for kind in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.AUTHORIZATION.VOIDED"):
        headers, body = sim.event(kind, {"id": auth})
        assert demo.client.post("/webhooks/paypal", content=body, headers=headers).status_code == 200
    assert not demo.calls("capture") and not demo.calls("void") and not demo.calls("refund")
    assert demo.pending_ids() == []                       # and nothing was asked of the owner


def test_an_expired_authorization_webhook_stops_a_capture_request(demo):
    oid = book(demo)
    demo.client.post(f"/checkout/{oid}/approve")
    s, b = demo.state.front.latest("deposit_held")
    headers, body = demo.state.webhook_sim.event("PAYMENT.AUTHORIZATION.EXPIRED", {"id": b["authorization_id"]})
    assert demo.client.post("/webhooks/paypal", content=body, headers=headers).json()["outcome"] == "hold_expired"
    demo.state.front.no_show(s, b["id"])
    assert demo.pending_ids() == [] and not demo.calls("capture")


def test_order_approved_for_an_unknown_order_is_accepted_but_does_nothing(demo):
    headers, body = demo.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": "ORDER-NOPE"})
    r = demo.client.post("/webhooks/paypal", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["outcome"] == "no booking waiting for this order"
    assert not demo.calls("authorize")


def test_without_a_webhook_id_the_sandbox_receiver_is_off(tmp_path, monkeypatch):
    class Sandboxish:                     # any provider without the fake's approve(): not simulated
        def create_order(self, *a): raise AssertionError
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID", raising=False)
    from fastapi.testclient import TestClient
    app = create_app(Sandboxish(), str(tmp_path / "l.jsonl"))
    r = TestClient(app).post("/webhooks/paypal", content=b"{}")
    assert r.status_code == 503 and r.json()["reason"] == "not_configured"
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-SANDBOX")
    app = create_app(Sandboxish(), str(tmp_path / "l2.jsonl"))
    r = TestClient(app).post("/webhooks/paypal", content=b"{}")
    assert r.status_code == 400 and r.json()["reason"] == "missing_header"
