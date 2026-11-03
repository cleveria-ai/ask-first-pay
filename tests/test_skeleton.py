"""End-to-end over the fake provider: the contract every piece builds on."""
import pytest
from ask_first import MandateRejected, generate_pair, sign_envelope

from ask_first_pay.fake_provider import FakeProvider
from ask_first_pay.gate import make_engine


@pytest.fixture
def world(tmp_path):
    provider = FakeProvider()
    priv, pub = generate_pair()
    engine = make_engine(provider, pub, str(tmp_path / "ledger.jsonl"))
    order = provider.create_order(10.0, "USD", "booking-14")
    provider.approve(order.order_id)
    auth = provider.authorize(order.order_id)
    return provider, priv, engine, auth


def _approve(engine, priv, mandate):
    engine.approve(mandate["jti"], sign_envelope(priv, engine.pending[mandate["jti"]]))


def test_capture_only_with_an_approved_mandate(world):
    provider, priv, engine, auth = world
    m = engine.request("agent", "capture_deposit", auth.authorization_id, 10.0, ttl_s=300)
    with pytest.raises(MandateRejected):
        engine.execute(m["jti"], "capture_deposit", auth.authorization_id, 10.0)
    assert not provider.captures
    _approve(engine, priv, m)
    out = engine.execute(m["jti"], "capture_deposit", auth.authorization_id, 10.0)
    assert len(provider.captures) == 1 and out["receipt"]


def test_replay_and_over_cap_are_rejected(world):
    provider, priv, engine, auth = world
    m = engine.request("agent", "capture_deposit", auth.authorization_id, 5.0, ttl_s=300)
    _approve(engine, priv, m)
    with pytest.raises(MandateRejected) as e:
        engine.execute(m["jti"], "capture_deposit", auth.authorization_id, 6.0)
    assert e.value.reason == "over_cap"
    engine.execute(m["jti"], "capture_deposit", auth.authorization_id, 5.0)
    with pytest.raises(MandateRejected) as e:
        engine.execute(m["jti"], "capture_deposit", auth.authorization_id, 5.0)
    assert e.value.reason == "replay"
    assert len(provider.captures) == 1


def test_ledger_verifies(world):
    _, priv, engine, auth = world
    m = engine.request("agent", "void_deposit", auth.authorization_id, 0.01, ttl_s=300)
    _approve(engine, priv, m)
    engine.execute(m["jti"], "void_deposit", auth.authorization_id, 0.01)
    assert engine.view_ledger()["verification"]["ok"]
