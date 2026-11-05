"""Optional SQLite persistence: a restart keeps bookings, mandates, approvals and, above all, the
set of mandates already used. Each test 'restarts' by building a second app on the same file."""
import sqlite3

import pytest
from ask_first import generate_pair, public_key_hex, sign_envelope
from fastapi.testclient import TestClient

from ask_first_pay.demo import create_app
from ask_first_pay.fake_provider import FakeProvider
from ask_first_pay.store import SqliteStore


class Shop:
    def __init__(self, db, shop="bright-smile", key=None):
        self.provider = FakeProvider()
        self.app = create_app(self.provider, store=SqliteStore(db, shop))
        self.state = self.app.state.demo
        self.client = TestClient(self.app, follow_redirects=False)
        self.priv, self.pub = key or generate_pair()

    def pair(self):
        code = self.state.new_pairing_code()
        assert self.client.post("/owner/pair", json={"code": code, "public_key": public_key_hex(self.pub)}).status_code == 200

    def approve(self, jti):
        return self.client.post("/owner/approve", json={
            "mandate_id": jti, "signature": sign_envelope(self.priv, self.state.owner.pending[jti])})

    def pending(self):
        return [m["id"] for m in self.client.get("/owner/api/mandates").json()["mandates"] if m["state"] == "pending"]

    def held_booking(self):
        self.client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
        oid = list(self.provider.orders)[-1]
        self.client.post(f"/checkout/{oid}/approve")
        return self.state.front.latest("deposit_held")


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "shop.sqlite")


def test_without_a_store_nothing_is_written(tmp_path, monkeypatch):
    monkeypatch.delenv("ASK_FIRST_DB", raising=False)
    app = create_app(FakeProvider(), str(tmp_path / "l.jsonl"))
    assert app.state.demo.store is None
    TestClient(app).post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    assert not list(tmp_path.glob("*.sqlite*"))


def test_env_var_turns_the_store_on(db, monkeypatch):
    monkeypatch.setenv("ASK_FIRST_DB", db)
    monkeypatch.setenv("ASK_FIRST_SHOP", "shop-7")
    st = create_app(FakeProvider()).state.demo
    assert st.store.shop_id == "shop-7" and st.engine.ledger.path.name.endswith("shop-7.ledger.jsonl")


def test_a_restart_keeps_the_booking_the_hold_and_the_pending_mandate(db):
    a = Shop(db)
    a.pair()
    s, b = a.held_booking()
    a.state.front.no_show(s, b["id"])
    a.state.persist()
    [jti] = a.pending()

    b2 = Shop(db, key=(a.priv, a.pub))                       # the same phone, a new process
    assert b2.state.paired_key == public_key_hex(a.pub)
    assert b2.pending() == [jti]
    _, booking = b2.state.front.latest("deposit_held")
    assert booking["authorization_id"] == b["authorization_id"]
    assert b2.approve(jti).json() == {"ok": True}            # approval after the restart works
    assert [c[0] for c in b2.provider.calls] == ["capture"]   # on the restored hold, once
    assert "captured" in b2.client.get("/chat").text


def test_a_used_mandate_stays_used_across_a_restart(db):
    a = Shop(db)
    a.pair()
    s, b = a.held_booking()
    a.state.front.no_show(s, b["id"])
    [jti] = a.pending()
    a.approve(jti)
    c = Shop(db, key=(a.priv, a.pub))
    c.client.post("/replay")
    rows = [(r["result"], r["reason"]) for r in c.state.ledger_rows()[0]]
    assert rows[0] == ("rejected", "replay") and ("executed", "") in rows
    assert c.state.ledger_rows()[1]["ok"]                     # the chain survived the restart
    assert c.approve(jti).json()["reason"] == "already_approved"
    assert c.provider.calls == []


def test_the_ledger_marks_used_even_if_the_snapshot_was_not_saved(db):
    a = Shop(db)
    a.pair()
    s, b = a.held_booking()
    a.state.front.no_show(s, b["id"])
    [jti] = a.pending()
    a.state.persist()
    before = SqliteStore(db, "bright-smile").load()          # a snapshot from before the capture
    a.approve(jti)
    SqliteStore(db, "bright-smile").save(before)             # as if the later saves were lost
    c = Shop(db, key=(a.priv, a.pub))
    assert jti in c.state.engine.used                        # the ledger row still marks it used
    c.client.post("/replay")       # the lost snapshot also lacks the approval: refused before PayPal
    assert c.state.ledger_rows()[0][0]["reason"] == "not_approved" and c.provider.calls == []


def test_the_used_mark_is_saved_before_paypal_is_called(db):
    a = Shop(db)
    a.pair()
    s, b = a.held_booking()
    a.state.front.no_show(s, b["id"])
    [jti] = a.pending()
    seen = {}
    real = a.provider.capture

    def capture(*args, **kw):                                # the process "dies" during the call
        seen["used_on_disk"] = jti in SqliteStore(db, "bright-smile").load()["engine"]["used"]
        return real(*args, **kw)
    a.provider.capture = capture
    a.approve(jti)
    assert seen == {"used_on_disk": True}


def test_a_decline_stays_final_across_a_restart(db):
    a = Shop(db)
    a.pair()
    s, b = a.held_booking()
    a.state.front.no_show(s, b["id"])
    [jti] = a.pending()
    a.client.post("/owner/decline", json={"mandate_id": jti})
    c = Shop(db, key=(a.priv, a.pub))
    assert c.approve(jti).json()["reason"] == "declined" and c.provider.calls == []


def test_a_webhook_redelivered_after_a_restart_is_a_duplicate(db):
    a = Shop(db)
    a.client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    oid = list(a.provider.orders)[-1]
    a.provider.approve(oid)
    headers, body = a.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": oid}, "WH-EVT-R")
    assert a.client.post("/webhooks/paypal", content=body, headers=headers).json()["outcome"] == "deposit_held"
    c = Shop(db)
    c.state.webhooks.verifier = a.state.webhook_sim.verifier()     # same simulated PayPal
    assert c.client.post("/webhooks/paypal", content=body, headers=headers).json()["outcome"] == "duplicate"


def test_two_shops_share_a_file_but_not_their_state(db):
    a = Shop(db, "shop-a")
    a.client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    b = Shop(db, "shop-b")
    b.client.post("/chat/send", data={"message": "hello"})
    assert not any(s.bookings for s in b.state.front.conversations)
    assert any(s.bookings for s in Shop(db, "shop-a").state.front.conversations)
    with sqlite3.connect(db) as c:
        assert {r[0] for r in c.execute("SELECT shop_id FROM snapshots")} == {"shop-a", "shop-b"}


def test_a_database_from_the_other_provider_is_refused(db):
    Shop(db).client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})

    class NotSimulated:
        pass
    with pytest.raises(ValueError, match="different payment provider"):
        create_app(NotSimulated(), store=SqliteStore(db, "bright-smile"))


@pytest.mark.parametrize("bad", ["", "../etc", "a b", "x" * 65])
def test_shop_id_is_a_plain_name(db, bad):
    with pytest.raises(ValueError):
        SqliteStore(db, bad)


def test_fake_provider_round_trips_through_its_dict():
    p = FakeProvider()
    o = p.create_order(10.0, "USD", "booking-1")
    p.approve(o.order_id)
    a = p.authorize(o.order_id)
    p.capture(a.authorization_id, 10.0, "jti-1")
    q = FakeProvider()
    q.load_dict(p.to_dict())
    assert q.to_dict() == p.to_dict()
    assert q.capture(a.authorization_id, 10.0, "jti-1").capture_id == "CAP-0003"   # idempotent replay
    assert q.create_order(10.0, "USD", "booking-2").order_id == "ORDER-0004"      # ids continue


def test_a_webhook_effect_is_saved_before_its_id_is_marked_seen(db):
    a = Shop(db)
    a.client.post("/chat/send", data={"message": "book Mon 16 Nov 09:00"})
    oid = list(a.provider.orders)[-1]
    a.provider.approve(oid)
    status_when_marked = []
    real = a.state.store.remember_event

    def remember(event_id, event_type, outcome):
        snap = SqliteStore(db, "bright-smile").load()
        status_when_marked.append(snap["front"]["conversations"][-1]["bookings"]["booking-1"]["status"])
        return real(event_id, event_type, outcome)
    a.state.store.remember_event = remember
    headers, body = a.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": oid})
    a.client.post("/webhooks/paypal", content=body, headers=headers)
    assert status_when_marked and set(status_when_marked) == {"deposit_held"}
