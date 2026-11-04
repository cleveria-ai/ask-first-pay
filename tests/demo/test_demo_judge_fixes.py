"""Holes a judge found by driving the demo over HTTP (docs/JUDGE_REVIEW.md), each pinned by a test."""
import json
import re
import html


def ledger_rows(demo):
    text = demo.client.get("/ledger").text
    return json.loads(html.unescape(re.search(r'id="ledger-data">(.*?)</script>', text, re.S).group(1)))


def test_rejected_approve_after_decline_moves_no_money(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    assert demo.decline(jti).status_code == 200
    r = demo.approve(jti)                      # a valid signature arriving after the decline
    assert r.status_code == 400 and r.json()["reason"] == "declined"
    assert demo.calls("capture") == []
    assert jti not in demo.state.engine.approved


def test_rejected_second_approval_is_refused_not_ok(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    assert demo.approve(jti).status_code == 200
    r = demo.approve(jti)
    assert r.status_code == 400 and r.json()["reason"] == "already_approved"
    assert len(demo.calls("capture")) == 1


def test_rejected_replay_row_names_what_was_refused(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    demo.approve(jti)
    demo.client.post("/replay")
    top = ledger_rows(demo)[0]
    assert top["result"] == "rejected" and top["reason"] == "replay"
    assert top["action"] == "capture_deposit" and top["resource"].startswith("AUTH-") and top["amount"] == "10.00"


def test_rejected_malformed_owner_requests_are_400_not_500(demo):
    for path in ("/owner/pair", "/owner/approve", "/owner/decline"):
        r = demo.client.post(path, content=b"not json", headers={"content-type": "application/json"})
        assert r.status_code == 400, path


def test_no_show_scenario_acts_on_the_booking_the_customer_just_made(demo):
    demo.client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    demo.client.post("/checkout/ORDER-0001/approve")
    auth = demo.state.front.latest("deposit_held")[1]["authorization_id"]
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    assert demo.state.owner.get(jti)["recipient"] == auth          # the same customer, not a new one
    assert len(demo.state.front.state.bookings) == 1
    demo.approve(jti)
    demo.client.post("/scenario/cancel")                           # that booking is used: a new one
    assert len(demo.state.front.state.bookings) == 2


def test_no_show_end_to_end_five_days_later_reauthorizes_and_captures(tmp_path):
    """The demo's slots are days ahead; past PayPal's 3-day honor period the agent refreshes the hold."""
    from ask_first import generate_pair, public_key_hex, sign_envelope
    from fastapi.testclient import TestClient

    from ask_first_pay.demo import create_app
    from ask_first_pay.fake_provider import DAY, FakeProvider

    now = [1_800_000_000.0]
    provider = FakeProvider(clock=lambda: now[0])
    app = create_app(provider, str(tmp_path / "ledger.jsonl"))
    st, client = app.state.demo, TestClient(app)
    priv, pub = generate_pair()
    client.post("/owner/pair", json={"code": st.new_pairing_code(), "public_key": public_key_hex(pub)})
    client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    client.post("/checkout/ORDER-0001/approve")
    old = st.front.latest("deposit_held")[1]["authorization_id"]
    now[0] += 5 * DAY
    client.post("/scenario/no_show")
    (m,) = [r for r in client.get("/owner/api/mandates").json()["mandates"] if r["state"] == "pending"]
    assert m["resource"] != old and provider.auths[old].status == "VOIDED"
    r = client.post("/owner/approve", json={"mandate_id": m["id"], "signature": sign_envelope(priv, st.owner.pending[m["id"]])})
    assert r.status_code == 200
    assert [c[0] for c in provider.calls if c[0] in ("capture", "void", "refund")] == ["capture"]
    assert "captured for the no-show" in client.get("/chat").text
