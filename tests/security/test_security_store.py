"""(e) The SQLite store: restart then replay, a second process on the same file, concurrent writers,
tampered rows, hostile shop ids."""
import sqlite3
import threading

import pytest
from ask_first import MandateRejected

from ask_first_pay.store import SqliteStore
from tests.demo.test_demo_store import Shop, db  # noqa: F401  (a 'restartable' demo on one file)


def spent_mandate(db):
    a = Shop(db)
    a.pair()
    a.held_booking()
    a.state.scenario("no_show")
    jti = a.pending()[-1]
    assert a.approve(jti).status_code == 200
    assert len(a.provider.calls_of("capture") if hasattr(a.provider, "calls_of") else [c for c in a.provider.calls if c[0] == "capture"]) == 1
    return a, jti


def test_restart_then_replay_is_still_a_replay(db):
    a, jti = spent_mandate(db)
    b = Shop(db, key=(a.priv, a.pub))
    req = next(iter(b.state.front.conversations[-1].mandates.values()))
    with pytest.raises(MandateRejected) as e:
        b.state.agent.execute(jti, req["action"], req["target"], req["amount"])
    assert e.value.reason == "replay"
    assert not [c for c in b.provider.calls if c[0] == "capture"]


def test_restart_replay_survives_a_snapshot_that_forgot_the_mandate_was_used(db):
    """The ledger is the second witness: wipe 'used' from the snapshot and the executed row still blocks it."""
    a, jti = spent_mandate(db)
    with sqlite3.connect(db) as c:
        import json
        (data,) = c.execute("SELECT data FROM snapshots").fetchone()
        snap = json.loads(data)
        snap["engine"]["used"] = []
        c.execute("UPDATE snapshots SET data=?", (json.dumps(snap),))
    b = Shop(db, key=(a.priv, a.pub))
    req = next(iter(b.state.front.conversations[-1].mandates.values()))
    with pytest.raises(MandateRejected) as e:
        b.state.agent.execute(jti, req["action"], req["target"], req["amount"])
    assert e.value.reason == "replay"


def test_two_processes_on_one_database_cannot_both_spend_a_mandate(db):
    """FIXED: 'used' lived in each process's memory and in a last-writer-wins snapshot, so a second
    process started from a snapshot taken after approval could execute the same mandate again (only
    PayPal's idempotency key would then have stopped the double capture). Spending is now claimed in
    the database, atomically, before the provider is called."""
    a = Shop(db)
    a.pair()
    a.held_booking()
    a.state.scenario("no_show")
    jti = a.pending()[-1]
    a.state.owner.approve(jti, __import__("ask_first").sign_envelope(a.priv, a.state.owner.pending[jti]))   # approved, not yet executed
    a.state.persist()
    b = Shop(db, key=(a.priv, a.pub))                     # the second process (rolling restart, two workers)
    req = a.state.front.conversations[-1].mandates[jti]
    args = (jti, req["action"], req["target"], req["amount"])
    assert a.state.agent.execute(*args)["result"] == "executed"
    with pytest.raises(MandateRejected):
        b.state.agent.execute(*args)
    assert len([c for c in b.provider.calls if c[0] == "capture"]) == 0
    assert len([c for c in a.provider.calls if c[0] == "capture"]) == 1


def test_concurrent_writers_never_corrupt_the_snapshot(db):
    s = SqliteStore(db, "shop")
    errors = []
    def w(i):
        try:
            for j in range(30):
                s.save({"version": 1, "n": i * 100 + j})
                s.remember_event(f"E-{i}-{j}", "T", "ok")
                assert s.load()["version"] == 1
        except Exception as e:     # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors
    assert all(s.seen_event(f"E-{i}-{j}") for i in range(8) for j in range(30))


@pytest.mark.parametrize("shop", ["../evil", "a/b", "x;DROP TABLE snapshots", "", "a" * 65, "sp ace", "nul\x00", "é", "a\nb"])
def test_hostile_shop_ids_are_refused(db, shop):
    with pytest.raises(ValueError):
        SqliteStore(db, shop)


def test_sql_injection_through_event_ids_is_inert(db):
    s = SqliteStore(db, "shop")
    evil = "x'); DROP TABLE webhook_events; --"
    s.remember_event(evil, "T'; --", "o'; --")
    assert s.seen_event(evil) and not s.seen_event("x")
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT count(*) FROM webhook_events").fetchone()[0] == 1


def test_shops_in_one_file_do_not_see_each_other(db):
    a, b = SqliteStore(db, "a"), SqliteStore(db, "b")
    a.save({"version": 1, "who": "a"}); a.remember_event("EV", "T", "o")
    assert b.load() is None and not b.seen_event("EV")
    assert a.ledger_path != b.ledger_path


def test_a_snapshot_from_the_wrong_provider_or_version_is_refused(db):
    s = SqliteStore(db, "bright")
    s.save({"version": 99})
    from ask_first_pay.demo import create_app
    from ask_first_pay.fake_provider import FakeProvider
    with pytest.raises(ValueError):
        create_app(FakeProvider(), store=SqliteStore(db, "bright"))


def test_write_access_to_the_database_is_total_trust_a_documented_residual(db):
    """OPEN / accepted: the snapshot holds the paired public key AND the signed approvals, so whoever can
    WRITE the database file can pair their own key and forge approvals. The DB file is as sensitive as
    the server's disk; this pins that fact (docs/SECURITY_REVIEW.md, residual R2)."""
    a = Shop(db)
    a.pair()
    a.held_booking()
    a.state.scenario("no_show")
    jti = a.pending()[-1]
    a.state.persist()
    import json
    from ask_first import generate_pair, public_key_hex, sign_envelope
    evil_priv, evil_pub = generate_pair()
    with sqlite3.connect(db) as c:
        (data,) = c.execute("SELECT data FROM snapshots").fetchone()
        snap = json.loads(data)
        snap["paired_key"] = public_key_hex(evil_pub)
        snap["engine"]["approved"][jti] = {"mandate": snap["engine"]["pending"][jti],
                                           "signature": sign_envelope(evil_priv, snap["engine"]["pending"][jti])}
        c.execute("UPDATE snapshots SET data=?", (json.dumps(snap),))
    b = Shop(db)
    req = next(iter(b.state.front.conversations[-1].mandates.values()))
    assert b.state.agent.execute(jti, req["action"], req["target"], req["amount"])["result"] == "executed"
