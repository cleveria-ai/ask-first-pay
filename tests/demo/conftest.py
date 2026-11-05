import pytest
from ask_first import generate_pair, public_key_hex, sign_envelope
from fastapi.testclient import TestClient

from ask_first_pay.demo import create_app
from ask_first_pay.fake_provider import FakeProvider


class Demo:
    """A demo app plus a paired 'phone' whose key lives in Python instead of a browser."""

    def __init__(self, tmp_path):
        self.provider = FakeProvider()
        self.app = create_app(self.provider, str(tmp_path / "ledger.jsonl"))
        self.state = self.app.state.demo
        self.client = TestClient(self.app, follow_redirects=False)
        self.priv, self.pub = generate_pair()

    def pair(self):
        code = self.state.new_pairing_code()
        return self.client.post("/owner/pair", json={"code": code, "public_key": public_key_hex(self.pub)})

    def signature(self, jti):
        return sign_envelope(self.priv, self.state.owner.pending[jti])

    def approve(self, jti):
        return self.client.post("/owner/approve", json={"mandate_id": jti, "signature": self.signature(jti)})

    def decline(self, jti):
        return self.client.post("/owner/decline", json={"mandate_id": jti})

    def pending_ids(self):
        return [m["id"] for m in self.client.get("/owner/api/mandates").json()["mandates"] if m["state"] == "pending"]

    def calls(self, name):
        return [c for c in self.provider.calls if c[0] == name]


@pytest.fixture
def demo(tmp_path):
    d = Demo(tmp_path)
    assert d.pair().status_code == 200
    return d
