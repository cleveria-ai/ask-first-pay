"""scripts/sandbox_run.py works offline against httpx.MockTransport and never writes secrets."""
import importlib.util
import io
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
CID, SECRET = "cid-MUST-NOT-LEAK-1234", "secret-MUST-NOT-LEAK-5678"
TOKEN = "A21AA-test-access-token-MUST-NOT-LEAK"


def load():
    spec = importlib.util.spec_from_file_location("sandbox_run", ROOT / "scripts" / "sandbox_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Sandbox:
    """A small PayPal: orders need the buyer's approval before authorize; captures are idempotent
    by PayPal-Request-Id unless `idempotent=False` (to prove the script reports what it sees)."""

    def __init__(self, approved=(), idempotent=True):
        self.approved, self.idempotent = set(approved), idempotent
        self.orders, self.captures, self.requests = 0, {}, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        path = req.url.path
        if path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "Bearer", "expires_in": 32400})
        if path == "/v2/checkout/orders":
            self.orders += 1
            oid = f"ORDER{self.orders}"
            return httpx.Response(201, json={"id": oid, "status": "PAYER_ACTION_REQUIRED", "links": [
                {"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]})
        if path.startswith("/v2/checkout/orders/") and path.endswith("/authorize"):
            oid = path.split("/")[4]
            if oid not in self.approved:
                return httpx.Response(422, json={"name": "UNPROCESSABLE_ENTITY", "message": "not approved",
                                                 "details": [{"issue": "ORDER_NOT_APPROVED"}]})
            auth = {"id": f"AUTH-{oid}", "status": "CREATED", "amount": {"currency_code": "USD", "value": "10.00"}}
            return httpx.Response(201, json={"id": oid, "status": "COMPLETED", "purchase_units": [
                {"payments": {"authorizations": [auth]}}]})
        if path.endswith("/capture"):
            key = req.headers["PayPal-Request-Id"] if self.idempotent else str(len(self.requests))
            cid = self.captures.setdefault(key, f"CAP{len(self.captures) + 1}")
            return httpx.Response(201, json={"id": cid, "status": "COMPLETED",
                                             "amount": {"currency_code": "USD", "value": "10.00"}})
        if path.endswith("/void"):
            return httpx.Response(204)
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", CID)
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", SECRET)


def run(argv, sandbox, record):
    out = io.StringIO()
    rc = load().main(argv, transport=httpx.MockTransport(sandbox), record_path=record, out=out)
    return rc, out.getvalue()


def assert_no_secrets(*texts):
    for t in texts:
        for needle in (CID, SECRET, TOKEN, "Bearer", "Authorization", "PayPal-Request-Id"):
            assert needle not in t, needle


def test_sandbox_run_step_a_prints_two_approval_links_and_writes_nothing(creds, tmp_path):
    record = tmp_path / "SANDBOX_RUN.md"
    sb = Sandbox()
    rc, out = run([], sb, record)
    assert rc == 0 and out.count("https://www.sandbox.paypal.com/checkoutnow?token=") == 2
    assert "--continue ORDER1 --void-order ORDER2" in out
    bodies = [json.loads(r.content) for r in sb.requests if r.url.path == "/v2/checkout/orders"]
    assert [b["intent"] for b in bodies] == ["AUTHORIZE", "AUTHORIZE"]
    assert all(b["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "10.00"} for b in bodies)
    ids = [r.headers["PayPal-Request-Id"] for r in sb.requests if r.url.path == "/v2/checkout/orders"]
    assert ids[0] != ids[1]
    assert not record.exists()
    assert_no_secrets(out)


def test_sandbox_run_continue_records_the_capture_retry_replay_and_void_without_secrets(creds, tmp_path):
    record = tmp_path / "SANDBOX_RUN.md"
    sb = Sandbox(approved={"ORDER1", "ORDER2"})
    rc, out = run(["--continue", "ORDER1", "--void-order", "ORDER2"], sb, record)
    assert rc == 0, out
    text = record.read_text()
    assert text.startswith("# PayPal sandbox runs")
    assert "| capture | CAP1 (COMPLETED) |" in text and "| capture_retry | CAP1 (COMPLETED) |" in text
    assert "| same_capture_id_on_retry | yes |" in text
    assert "| gate_replay | refused: replay |" in text
    assert "| void | AUTH-ORDER2 (VOIDED) |" in text
    assert text.count("`POST /v2/payments/authorizations/AUTH-ORDER1/capture` 201") == 2
    assert "`POST /v2/payments/authorizations/AUTH-ORDER2/void` 204" in text
    caps = [r for r in sb.requests if r.url.path.endswith("/capture")]
    assert len(caps) == 2 and caps[0].headers["PayPal-Request-Id"] == caps[1].headers["PayPal-Request-Id"]
    assert_no_secrets(text, out)


def test_sandbox_run_reports_a_different_capture_id_when_paypal_does_not_dedupe(creds, tmp_path):
    record = tmp_path / "SANDBOX_RUN.md"
    rc, _ = run(["--continue", "ORDER1", "--void-order", "ORDER2"],
                Sandbox(approved={"ORDER1", "ORDER2"}, idempotent=False), record)
    assert "| same_capture_id_on_retry | NO |" in record.read_text()


def test_sandbox_run_without_void_order_creates_one_and_records_paypal_refusal(creds, tmp_path):
    record = tmp_path / "SANDBOX_RUN.md"
    sb = Sandbox(approved={"ORDER1"})
    sb.orders = 1                                    # ORDER1 was created by step (a)
    rc, out = run(["--continue", "ORDER1"], sb, record)
    assert rc == 1
    assert "checkoutnow?token=ORDER2" in out and "--void-order ORDER2" in out
    text = record.read_text()
    assert "| void_order_created | ORDER2 (PAYER_ACTION_REQUIRED) |" in text
    assert "| void_story_error | ProviderError: UNPROCESSABLE_ENTITY: not approved |" in text
    assert "`POST /v2/checkout/orders/ORDER2/authorize` 422" in text
    assert "| same_capture_id_on_retry | yes |" in text
    sb2 = Sandbox(approved={"ORDER1"})
    sb2.orders = 1
    run(["--continue", "ORDER1"], sb2, record)                                  # a second run appends
    again = record.read_text()
    assert again.count("## Run ") == 2 and again.count("# PayPal sandbox runs") == 1
    assert_no_secrets(again, out)


def test_sandbox_run_without_credentials_stops_before_any_request(monkeypatch, tmp_path):
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    sb = Sandbox()
    rc, out = run([], sb, tmp_path / "r.md")
    assert rc == 2 and sb.requests == [] and "PAYPAL_CLIENT_ID" in out
