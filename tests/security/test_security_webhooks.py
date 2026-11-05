"""(c) Webhooks: forged signature, replay, cert-URL tricks, stale timestamps, events that claim a capture."""
import base64
import json
import zlib

import httpx
import pytest

from ask_first_pay.paypal.webhooks import (CertVerifier, WebhookReceiver, WebhookRejected, WebhookSimulator,
                                           cert_url_allowed, fetch_paypal_cert)


def post(demo, headers, body):
    return demo.client.post("/webhooks/paypal", content=body, headers=headers)


def booked(demo):
    demo.client.post("/chat/send", content="message=book+Mon+16+Nov+09%3A00", headers={"content-type": "application/x-www-form-urlencoded"})
    return demo.state.front.latest("booked")[1]


def test_forged_and_altered_webhooks_hold_nothing(demo):
    b = booked(demo)
    sim = WebhookSimulator()                                   # an attacker's own "PayPal": own key, same cert URL
    h, body = sim.event("CHECKOUT.ORDER.APPROVED", {"id": b["order_id"], "status": "APPROVED"})
    r = post(demo, h, body)
    assert r.status_code == 400 and r.json()["reason"] == "bad_signature"
    h, body = demo.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": b["order_id"]})
    r = post(demo, h, body.replace(b"CHECKOUT", b"CHECKOUX"))
    assert r.status_code == 400
    assert b["status"] == "booked" and not demo.calls("authorize")


def test_unsigned_and_garbage_webhooks_are_rejected_not_crashing(demo):
    for h, body in (({}, b"{}"), ({"content-type": "application/json"}, b"\xff"), ({}, b"x" * 70_000)):
        assert post(demo, h, body).status_code in (400, 413)


def test_a_valid_event_replayed_is_accepted_once(demo):
    b = booked(demo)
    sim = demo.state.webhook_sim
    sim.clock = lambda: __import__("time").time()
    h, body = sim.event("CHECKOUT.ORDER.APPROVED", {"id": b["order_id"], "status": "APPROVED"})
    demo.provider.approve(b["order_id"])
    assert post(demo, h, body).json()["outcome"] == "deposit_held"
    assert post(demo, h, body).json()["outcome"] == "duplicate"
    h2, body2 = sim.event("CHECKOUT.ORDER.APPROVED", {"id": b["order_id"]}, event_id=json.loads(body)["id"])
    assert post(demo, h2, body2).json()["outcome"] == "duplicate"          # same event id, fresh signature
    assert len(demo.calls("authorize")) == 1


@pytest.mark.parametrize("url", [
    "https://evil.example/cert.pem", "http://api.paypal.com/c", "https://paypal.com.evil.example/c",
    "https://evilpaypal.com/c", "https://api.paypal.com.evil.example/c", "https://evil.example/@api.paypal.com/c",
    "https://api.paypal.com@evil.example/c", "https://evil.example\\@api.paypal.com/c", "https://evil.example#@api.paypal.com/c",
    "https://evil.example?.paypal.com/c", "ftp://api.paypal.com/c", "//api.paypal.com/c", "https:///api.paypal.com/c",
    "https://api.paypal.com\t.evil.example/c", "https://api.paypal.com%2eevil.example/c", "file:///etc/passwd", "",
    "https://xn--pypal-4ve.com/c", "https://api.paypal.com:444@evil.example/c", "https://127.0.0.1/c", "https://[::1]/c",
])
def test_cert_url_tricks_are_refused(url):
    assert not cert_url_allowed(url), url


@pytest.mark.parametrize("url", ["https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1", "https://api.paypal.com/v1/notifications/certs/CERT-1"])
def test_genuine_cert_urls_still_pass(url):
    assert cert_url_allowed(url)


def test_cert_urls_that_urllib_and_httpx_read_differently_are_refused():
    """FIXED where it applied: whatever host urlparse extracts must be the host httpx will CONNECT to."""
    from urllib.parse import urlparse
    for url in ("https://evil.example\\@api.paypal.com/c", "https://evil.example\t@api.paypal.com/c", "https://a.b\\.paypal.com/c"):
        try:
            connect = httpx.URL(url).host
        except Exception:
            connect = None
        if cert_url_allowed(url):
            assert connect and (connect == "paypal.com" or connect.endswith(".paypal.com")), (url, connect)


def test_fetch_paypal_cert_refuses_off_paypal_hosts_without_any_request(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(WebhookRejected):
        fetch_paypal_cert("https://evil.example/c")


def test_cert_download_does_not_follow_redirects(monkeypatch):
    """A paypal.com URL that 302s to elsewhere must not be followed (httpx default; pinned here)."""
    seen = {}
    def fake_get(url, **kw):
        seen.update(kw)
        return httpx.Response(200, content=b"pem", request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", fake_get)
    fetch_paypal_cert("https://api.paypal.com/v1/notifications/certs/C")
    assert not seen.get("follow_redirects")


def test_old_and_future_timestamps_are_refused():
    now = [1_800_000_000.0]
    sim = WebhookSimulator(clock=lambda: now[0])
    v = sim.verifier()
    h, body = sim.event("CHECKOUT.ORDER.APPROVED", {"id": "O"})
    now[0] += 301
    with pytest.raises(WebhookRejected) as e:
        v.verify(h, body)
    assert e.value.reason == "stale"
    now[0] -= 602                                              # the sender's clock is in the future by 301s
    with pytest.raises(WebhookRejected) as e:
        v.verify(h, body)
    assert e.value.reason == "stale"
    h2 = {**h, "paypal-transmission-time": "2026-11-05T10:00:00"}      # no time zone: never guessed
    with pytest.raises(WebhookRejected):
        v.verify(h2, body)


def test_an_expired_certificate_is_refused():
    now = [1_800_000_000.0]
    sim = WebhookSimulator(clock=lambda: now[0])
    v = sim.verifier()
    now[0] += 40 * 86400
    sim.clock = lambda: now[0]
    h, body = sim.event("CHECKOUT.ORDER.APPROVED", {"id": "O"})
    with pytest.raises(WebhookRejected) as e:
        v.verify(h, body)
    assert e.value.reason == "bad_cert"


def test_a_genuine_event_claiming_a_capture_or_refund_moves_nothing(demo):
    b = booked(demo)
    sim = demo.state.webhook_sim
    for typ in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.DENIED", "PAYMENT.AUTHORIZATION.VOIDED"):
        h, body = sim.event(typ, {"id": "CAP-FAKE", "status": "COMPLETED", "amount": {"value": "10.00"}, "invoice_id": b["id"]})
        assert post(demo, h, body).status_code == 200
    assert not demo.calls("capture") and not demo.calls("refund") and not demo.calls("void")
    assert demo.state.front.latest("booked")[1]["status"] == "booked"
    assert not demo.state.owner.pending and not demo.state.engine.ledger.entries()


def test_webhook_text_in_the_chat_is_escaped_and_never_fed_to_the_agent(demo):
    sim = demo.state.webhook_sim
    h, body = sim.event("PAYMENT.CAPTURE.COMPLETED", {"id": "<script>alert(1)</script>"})
    post(demo, h, body)
    assert "<script>alert" not in demo.client.get("/chat").text
    assert all("alert(1)" not in str(m) for s in demo.state.front.conversations for m in s.messages)


def test_order_approved_for_an_unknown_order_does_nothing(demo):
    h, body = demo.state.webhook_sim.event("CHECKOUT.ORDER.APPROVED", {"id": "ORDER-NOT-OURS"})
    assert post(demo, h, body).json()["outcome"] == "no booking waiting for this order"
    assert not demo.calls("authorize")


def test_crc32_only_signature_is_a_documented_protocol_residual():
    """OPEN (low, inherent to PayPal's scheme): the signature covers crc32(body), so a different body
    with the same CRC32 verifies under the same headers. The receiver therefore accepts each
    TRANSMISSION once and handlers never move money; this test pins both halves."""
    sim = WebhookSimulator()
    h, body = sim.event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-1"})
    target = zlib.crc32(body)
    prefix, suffix = body[:-1] + b',"x":"', b'"}'
    forged = prefix + _solve_crc(prefix, suffix, target) + suffix
    assert forged != body and zlib.crc32(forged) == target
    sim.verifier().verify(h, forged)                      # verifies: the limit of the scheme
    got = []
    r = WebhookReceiver(sim.verifier(), {"PAYMENT.CAPTURE.COMPLETED": lambda res: got.append(res) or "noted"})
    assert r.receive(h, forged)["outcome"] == "noted"
    assert r.receive(h, body)["outcome"] == "duplicate"   # the genuine one cannot ride the same transmission again
    assert len(got) == 1


def _solve_crc(prefix: bytes, suffix: bytes, target: int, n: int = 8) -> bytes:
    """n ASCII bytes (0x40-0x7f, no backslash) X with crc32(prefix + X + suffix) == target.
    CRC32 is affine over GF(2): solve the 32 equations by Gaussian elimination over 6n free bits."""
    f = lambda x: zlib.crc32(prefix + bytes(x) + suffix)
    for fill in range(0x40, 0x60):
        x0 = [fill] * n
        base = f(x0)
        cols = []
        for i in range(n):
            for bit in range(6):
                x = list(x0); x[i] ^= 1 << bit
                cols.append(((f(x) ^ base), i, bit))
        want, basis = target ^ base, []
        for v, i, bit in cols:                        # reduce into an echelon basis, remembering which bits make it
            mask = {(i, bit)}
            for bv, bmask in basis:
                if v ^ bv < v:
                    v, mask = v ^ bv, mask ^ bmask
            if v:
                basis.append((v, mask)); basis.sort(key=lambda t: -t[0])
        pick, w = set(), want
        for bv, bmask in basis:
            if w ^ bv < w:
                w, pick = w ^ bv, pick ^ bmask
        if w:
            continue
        x = list(x0)
        for i, bit in pick:
            x[i] ^= 1 << bit
        if f(x) == target and 0x5c not in x:
            return bytes(x)
    raise AssertionError("no solution")
