"""N8 (B2): PayPal sends the buyer back to /chat/return?token=<order id>. That confirms the hold
through the same path as the CHECKOUT.ORDER.APPROVED webhook; whichever arrives first wins and
the other is a no-op. With the real adapter it works with no webhook configured at all."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ask_first_pay.demo import create_app
from ask_first_pay.paypal import PayPalProvider

from tests.paypal.fakepaypal import MockPayPal


def book(demo, slot="Mon 16 Nov 09:00"):
    demo.client.post("/chat/send", data={"message": f"book {slot}"})
    return list(demo.provider.orders)[-1]


def held(state):
    return [b for s in state.front.conversations for b in s.bookings.values() if b["status"] == "deposit_held"]


def webhook(demo, oid, event_id):
    headers, body = demo.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": oid}, event_id)
    r = demo.client.post("/webhooks/paypal", content=body, headers=headers)
    assert r.status_code == 200
    return r.json()["outcome"]


def test_demo_chat_return_confirms_the_hold_and_the_later_webhook_is_a_no_op(demo):
    oid = book(demo)
    demo.provider.approve(oid)                                   # the payer approved on PayPal
    r = demo.client.get(f"/chat/return?token={oid}&PayerID=PAYER123")
    assert r.status_code == 303 and r.headers["location"] == "/chat#end"
    assert len(held(demo.state)) == 1 and len(demo.calls("authorize")) == 1
    assert any(m.text.startswith("Back from PayPal: the customer approved") for m in demo.state.front.messages)
    assert webhook(demo, oid, "WH-RET-1") == "no booking waiting for this order"
    assert len(demo.calls("authorize")) == 1 and len(held(demo.state)) == 1
    assert not demo.calls("capture") and demo.pending_ids() == []          # holding moves no money


def test_demo_chat_return_after_the_webhook_is_a_no_op(demo):
    oid = book(demo)
    demo.provider.approve(oid)
    assert webhook(demo, oid, "WH-RET-2") == "deposit_held"
    messages = len(demo.state.front.messages)
    demo.client.get(f"/chat/return?token={oid}")
    demo.client.get(f"/chat/return?token={oid}")                # a reload of the return page too
    assert len(demo.calls("authorize")) == 1 and len(held(demo.state)) == 1
    assert len(demo.state.front.messages) == messages            # the agent was not woken again


def test_demo_chat_return_ignores_unknown_or_malformed_tokens(demo):
    oid = book(demo)
    demo.provider.approve(oid)
    for token in ("ORDER-9999", "<script>", "a" * 65, ""):
        r = demo.client.get("/chat/return", params={"token": token})
        assert r.status_code == 303
    assert demo.calls("authorize") == [] and held(demo.state) == []


def test_demo_chat_return_before_approval_holds_nothing(demo):
    """A hand-typed return URL is not an approval: PayPal (here the fake) refuses to authorize."""
    oid = book(demo)
    demo.client.get(f"/chat/return?token={oid}")
    assert held(demo.state) == [] and demo.state.provider.orders[oid].status == "CREATED"


def test_demo_chat_cancel_says_so_and_holds_nothing(demo):
    oid = book(demo)
    r = demo.client.get(f"/chat/cancel?token={oid}")
    assert r.status_code == 303
    assert demo.state.front.messages[-1].text == "The customer left PayPal without approving. Nothing is held."
    assert demo.calls("authorize") == [] and held(demo.state) == []


@pytest.fixture
def live_like(tmp_path, monkeypatch):
    """The demo on the real adapter (mocked PayPal), with no webhook configured: the live setup."""
    for var in ("PAYPAL_WEBHOOK_ID", "ANTHROPIC_API_KEY", "ASK_FIRST_DB"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ASK_FIRST_PUBLIC_URL", "https://demo.example")
    mock = MockPayPal()
    app = create_app(PayPalProvider("cid", "secret", transport=httpx.MockTransport(mock)),
                     str(tmp_path / "ledger.jsonl"))
    return app.state.demo, TestClient(app, follow_redirects=False), mock


def test_demo_chat_return_live_adapter_without_webhook_holds_the_deposit_once(live_like):
    state, client, mock = live_like
    assert not state.simulated and state.webhooks is None
    client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    (create,) = [r for r in mock.writes() if r.url.path == "/v2/checkout/orders"]
    ctx = json.loads(create.content)["payment_source"]["paypal"]["experience_context"]
    assert ctx["return_url"] == "https://demo.example/chat/return" and ctx["shipping_preference"] == "NO_SHIPPING"
    assert "checkoutnow?token=5O190127TN364715T" in client.get("/chat").text      # PayPal's own payer page
    client.get("/chat/return?token=5O190127TN364715T&PayerID=X")
    client.get("/chat/return?token=5O190127TN364715T&PayerID=X")
    authorizes = [r for r in mock.writes() if r.url.path.endswith("/authorize")]
    assert len(authorizes) == 1 and [b["authorization_id"] for b in held(state)] == ["3C679366HH908993F"]
    assert client.post("/webhooks/paypal", content=b"{}").status_code == 503       # no tunnel needed
