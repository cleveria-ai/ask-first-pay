"""Shared harness for the N7 attacker tests: a gate over the fake provider, and the owner's phone
as a Python key. Attackers get only what the product hands the agent (AgentGate, HoldDesk)."""
import pytest
from ask_first import generate_pair, sign_envelope

from ask_first_pay.fake_provider import FakeProvider
from ask_first_pay.gate import make_engine, split, HoldDesk
from ask_first_pay.agent import AgentState

from tests.demo.conftest import Demo, demo  # noqa: F401  (the `demo` fixture: paired phone + app)


class Rig:
    def __init__(self, tmp_path):
        self.provider = FakeProvider()
        self.priv, self.pub = generate_pair()
        self.engine = make_engine(self.provider, self.pub, str(tmp_path / "ledger.jsonl"))
        self.agent, self.owner = split(self.engine)
        self.desk = HoldDesk(self.provider)

    def held(self, amount=10.0):
        """A held authorization, like the booking flow makes."""
        o = self.provider.create_order(amount, "USD", "ref")
        self.provider.approve(o.order_id)
        return self.provider.authorize(o.order_id).authorization_id

    def sign(self, jti):
        return sign_envelope(self.priv, self.engine.pending[jti])

    def approved_capture(self, amount=10.0):
        auth = self.held()
        m = self.agent.request("capture_deposit", auth, amount)
        self.owner.approve(m["jti"], self.sign(m["jti"]))
        return auth, m["jti"]

    def calls(self, name):
        return [c for c in self.provider.calls if c[0] == name]


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)
