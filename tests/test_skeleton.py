"""End-to-end over the fake provider: the contract every piece builds on."""
import pytest
from ask_first import MandateRejected, generate_pair, sign_envelope

from ask_first_pay.fake_provider import DAY, FakeProvider
from ask_first_pay.gate import AgentGate, make_engine, split
from ask_first_pay.ports import ProviderError


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def world(tmp_path):
    clock = Clock()
    provider = FakeProvider(clock=clock)
    priv, pub = generate_pair()
    engine = make_engine(provider, pub, str(tmp_path / "ledger.jsonl"))
    agent, owner = split(engine)
    order = provider.create_order(10.0, "USD", "booking-14")
    provider.approve(order.order_id)
    auth = provider.authorize(order.order_id)
    return provider, priv, agent, owner, auth, clock


def _approve(owner, priv, mandate):
    owner.approve(mandate["jti"], sign_envelope(priv, owner.pending[mandate["jti"]]))


def test_no_show_captures_only_after_the_owner_approves(world):
    provider, priv, agent, owner, auth, _ = world
    m = agent.request("capture_deposit", auth.authorization_id, 10.0)
    with pytest.raises(MandateRejected):
        agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 10.0)
    assert not provider.captures
    _approve(owner, priv, m)
    out = agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 10.0)
    assert len(provider.captures) == 1 and out["receipt"]
    assert provider.calls[-1][3] == m["jti"]          # the mandate id is the idempotency key


def test_replay_and_over_cap_are_rejected(world):
    provider, priv, agent, owner, auth, _ = world
    m = agent.request("capture_deposit", auth.authorization_id, 5.0)
    _approve(owner, priv, m)
    with pytest.raises(MandateRejected) as e:
        agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 6.0)
    assert e.value.reason == "over_cap"
    agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 5.0)
    with pytest.raises(MandateRejected) as e:
        agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 5.0)
    assert e.value.reason == "replay"
    assert len(provider.captures) == 1


def test_cancellation_is_a_void_not_a_refund(world):
    provider, priv, agent, owner, auth, _ = world
    m = agent.request("void_deposit", auth.authorization_id, 0.01)
    _approve(owner, priv, m)
    agent.execute(m["jti"], "void_deposit", auth.authorization_id, 0.01)
    assert provider.auths[auth.authorization_id].status == "VOIDED"
    assert not provider.captures and not provider.refunds
    assert agent.view_ledger()["verification"]["ok"]


def test_goodwill_refund_needs_its_own_mandate(world):
    provider, priv, agent, owner, auth, _ = world
    c = agent.request("capture_deposit", auth.authorization_id, 10.0)
    _approve(owner, priv, c)
    cap = agent.execute(c["jti"], "capture_deposit", auth.authorization_id, 10.0)["outcome"]
    r = agent.request("refund_deposit", cap["capture_id"], 4.0)
    _approve(owner, priv, r)
    agent.execute(r["jti"], "refund_deposit", cap["capture_id"], 4.0)
    assert provider.captures[cap["capture_id"]].status == "PARTIALLY_REFUNDED"


def test_capture_after_the_honor_period_needs_reauthorization(world):
    provider, priv, agent, owner, auth, clock = world
    clock.t += 4 * DAY
    m = agent.request("capture_deposit", auth.authorization_id, 10.0)
    _approve(owner, priv, m)
    with pytest.raises(MandateRejected) as e:
        agent.execute(m["jti"], "capture_deposit", auth.authorization_id, 10.0)
    assert e.value.reason == "executor_failed"
    new = provider.reauthorize(auth.authorization_id, request_id="reauth-1")
    m2 = agent.request("capture_deposit", new.authorization_id, 10.0)
    _approve(owner, priv, m2)
    agent.execute(m2["jti"], "capture_deposit", new.authorization_id, 10.0)
    assert len(provider.captures) == 1


def test_authorization_expires_after_29_days(world):
    provider, _, _, _, auth, clock = world
    clock.t += 30 * DAY
    with pytest.raises(ProviderError) as e:
        provider.capture(auth.authorization_id, 10.0, request_id="x")
    assert e.value.code == "AUTHORIZATION_EXPIRED"


def test_same_request_id_never_moves_money_twice(world):
    provider, _, _, _, auth, _ = world
    a = provider.capture(auth.authorization_id, 10.0, request_id="same")
    b = provider.capture(auth.authorization_id, 10.0, request_id="same")
    assert a == b and len(provider.captures) == 1


def test_the_agent_gate_cannot_approve_pair_or_reach_the_provider(world):
    _, _, agent, _, _, _ = world
    assert isinstance(agent, AgentGate)
    public = {n for n in dir(agent) if not n.startswith("_")}
    assert public == {"request", "execute", "describe", "view_ledger"}
    for forbidden in ("approve", "pair", "new_pairing_code", "pending", "person_pub", "executor", "provider"):
        assert not hasattr(agent, forbidden)
    with pytest.raises(AttributeError):
        agent.approve = lambda *a: None


def test_the_hold_desk_cannot_move_money(world):
    from ask_first_pay.gate import HoldDesk
    provider = world[0]
    desk = HoldDesk(provider)
    assert {n for n in dir(desk) if not n.startswith("_")} == {"create_order", "authorize", "reauthorize"}
    for forbidden in ("capture", "refund", "void"):
        assert not hasattr(desk, forbidden)


def test_describe_comes_from_signed_fields(world):
    _, _, agent, _, auth, _ = world
    m = agent.request("capture_deposit", auth.authorization_id, 7.5)
    text = agent.describe(m["jti"])
    assert auth.authorization_id in text and "7.50" in text and "pending" in text


class _Flaky:
    """Wraps a provider: the first capture times out AFTER the money moved (the worst case)."""

    def __init__(self, inner):
        self.inner, self.request_ids, self.failed = inner, [], False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def capture(self, authorization_id, amount, request_id, final_capture=True):
        self.request_ids.append(request_id)
        c = self.inner.capture(authorization_id, amount, request_id, final_capture)
        if not self.failed:
            self.failed = True
            raise ProviderError("TRANSIENT", "read timeout", transient=True)
        return c


def test_transient_failure_is_retried_with_the_same_request_id_and_moves_money_once(tmp_path):
    from ask_first import generate_pair, sign_envelope
    from ask_first_pay.fake_provider import FakeProvider
    from ask_first_pay.gate import make_engine, split

    fake = FakeProvider()
    flaky = _Flaky(fake)
    priv, pub = generate_pair()
    gate, owner = split(make_engine(flaky, pub, str(tmp_path / "l.jsonl")))
    o = fake.create_order(10.0, "USD", "b-1"); fake.approve(o.order_id)
    a = fake.authorize(o.order_id)
    m = gate.request("capture_deposit", a.authorization_id, 10.0)
    owner.approve(m["jti"], sign_envelope(priv, owner.pending[m["jti"]]))
    out = gate.execute(m["jti"], "capture_deposit", a.authorization_id, 10.0)
    assert out["result"] == "executed" and flaky.request_ids == [m["jti"], m["jti"]]
    assert len(fake.captures) == 1
