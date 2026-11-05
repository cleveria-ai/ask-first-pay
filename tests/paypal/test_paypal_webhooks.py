"""Webhook signature verification in PayPal's format, against the local simulator. No network."""
import base64
import datetime as dt
import json
import zlib

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from ask_first_pay.paypal.webhooks import (
    CertVerifier,
    WebhookReceiver,
    WebhookRejected,
    WebhookSimulator,
    cert_url_allowed,
    signed_message,
)

NOW = 1_794_000_000.0


@pytest.fixture(scope="module")
def sim():
    return WebhookSimulator(clock=lambda: NOW)


def order_approved(sim, order_id="ORDER-0001", event_id=None):
    return sim.event("CHECKOUT.ORDER.APPROVED", {"id": order_id, "status": "APPROVED"}, event_id)


def test_signed_message_is_paypals_format():
    body = b'{"id":"WH-1"}'
    assert signed_message("t-1", "2026-11-04T10:00:00Z", "WH-ID", body) == \
        f"t-1|2026-11-04T10:00:00Z|WH-ID|{zlib.crc32(body)}".encode()


def test_a_genuine_simulated_delivery_verifies(sim):
    headers, body = order_approved(sim)
    sim.verifier().verify(headers, body)          # no exception
    assert json.loads(body)["event_type"] == "CHECKOUT.ORDER.APPROVED"


@pytest.mark.parametrize("change, reason", [
    (lambda h, b: (h, b.replace(b"ORDER-0001", b"ORDER-9999")), "bad_signature"),     # body altered
    (lambda h, b: ({**h, "paypal-transmission-id": "other"}, b), "bad_signature"),      # header altered
    (lambda h, b: ({**h, "paypal-auth-algo": "SHA1withRSA"}, b), "bad_algo"),
    (lambda h, b: ({**h, "paypal-cert-url": "https://evil.example/cert.pem"}, b), "bad_cert_url"),
    (lambda h, b: ({**h, "paypal-cert-url": "http://api.sandbox.paypal.com/c"}, b), "bad_cert_url"),
    (lambda h, b: ({**h, "paypal-transmission-time": "2020-01-01T00:00:00Z"}, b), "stale"),
    (lambda h, b: ({**h, "paypal-transmission-sig": "%%%"}, b), "bad_signature"),
    (lambda h, b: ({k: v for k, v in h.items() if k != "paypal-transmission-sig"}, b), "missing_header"),
])
def test_tampered_or_incomplete_deliveries_are_rejected(sim, change, reason):
    headers, body = change(*order_approved(sim))
    with pytest.raises(WebhookRejected) as e:
        sim.verifier().verify(headers, body)
    assert e.value.reason == reason


def test_a_signature_for_another_webhook_id_is_rejected(sim):
    headers, body = order_approved(sim)
    with pytest.raises(WebhookRejected) as e:
        CertVerifier("WH-SOMEONE-ELSE", sim.fetch_cert, clock=lambda: NOW).verify(headers, body)
    assert e.value.reason == "bad_signature"


def test_a_key_that_is_not_the_certificates_is_rejected(sim):
    forger = WebhookSimulator(webhook_id=sim.webhook_id, clock=lambda: NOW)   # same URL, other key
    headers, body = order_approved(forger)
    with pytest.raises(WebhookRejected) as e:
        sim.verifier().verify(headers, body)
    assert e.value.reason == "bad_signature"


def test_an_expired_certificate_is_rejected(sim):
    later = NOW + 60 * 86400                     # the simulator's cert is valid for 30 days
    v = CertVerifier(sim.webhook_id, sim.fetch_cert, clock=lambda: later, max_age_s=10**9)
    headers, body = order_approved(sim)
    with pytest.raises(WebhookRejected) as e:
        v.verify(headers, body)
    assert e.value.reason == "bad_cert"


def test_cert_url_must_be_https_on_paypal_com():
    assert cert_url_allowed("https://api.paypal.com/v1/notifications/certs/CERT-1")
    assert cert_url_allowed("https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1")
    assert not cert_url_allowed("https://paypal.com.evil.example/c")
    assert not cert_url_allowed("https://evilpaypal.com/c")
    assert not cert_url_allowed("ftp://api.paypal.com/c")


def test_receiver_dispatches_once_and_reports_duplicates(sim):
    got = []
    r = WebhookReceiver(sim.verifier(), {"CHECKOUT.ORDER.APPROVED": lambda res: got.append(res["id"]) or "authorized"})
    headers, body = order_approved(sim, event_id="WH-EVT-1")
    assert r.receive(headers, body)["outcome"] == "authorized"
    assert r.receive(headers, body)["outcome"] == "duplicate"          # PayPal redelivers
    assert got == ["ORDER-0001"]


def test_receiver_ignores_unknown_types_and_rejects_before_dispatch(sim):
    got = []
    r = WebhookReceiver(sim.verifier(), {"CHECKOUT.ORDER.APPROVED": lambda res: got.append(1) or "x"})
    assert r.receive(*sim.event("BILLING.PLAN.CREATED", {"id": "P-1"}))["outcome"] == "ignored"
    headers, body = order_approved(sim)
    with pytest.raises(WebhookRejected):
        r.receive(headers, body + b" ")
    assert got == []


def test_receiver_rejects_a_signed_body_that_is_not_an_event(sim):
    r = WebhookReceiver(sim.verifier(), {})
    for raw in (b"[1,2]", b"not json", json.dumps({"id": "x", "event_type": "A.B", "resource": 3}).encode()):
        tid = "t"
        ttime = dt.datetime.fromtimestamp(NOW, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sig = sim._key.sign(signed_message(tid, ttime, sim.webhook_id, raw), padding.PKCS1v15(), hashes.SHA256())
        headers = {"paypal-transmission-id": tid, "paypal-transmission-time": ttime,
                   "paypal-transmission-sig": base64.b64encode(sig).decode(),
                   "paypal-cert-url": sim.CERT_URL, "paypal-auth-algo": "SHA256withRSA"}
        with pytest.raises(WebhookRejected) as e:
            r.receive(headers, raw)
        assert e.value.reason in ("bad_json", "bad_event")


class AcceptsAnything:
    """Stands in for a forger who found a body with the same CRC32 as a captured delivery: the
    signature check passes, as it would in PayPal's scheme, which signs only the CRC32."""
    def verify(self, headers, body):
        return None


def test_one_transmission_signature_is_accepted_once_whatever_the_body(sim):
    got = []
    r = WebhookReceiver(AcceptsAnything(), {"PAYMENT.AUTHORIZATION.EXPIRED": lambda res: got.append(res) or "x",
                                            "PAYMENT.CAPTURE.COMPLETED": lambda res: "noted"})
    headers, body = sim.event("PAYMENT.CAPTURE.COMPLETED", {"id": "CAP-1"})
    assert r.receive(headers, body)["outcome"] == "noted"
    forged = json.dumps({"id": "WH-EVT-NEW", "event_type": "PAYMENT.AUTHORIZATION.EXPIRED",
                         "resource": {"id": "AUTH-1"}}).encode()
    assert r.receive(headers, forged)["outcome"] == "duplicate"      # new event id, same transmission
    assert got == []
    fresh = {**headers, "paypal-transmission-id": "another"}
    assert r.receive(fresh, forged)["outcome"] == "x" and len(got) == 1

def test_the_certificate_dates_are_checked_on_every_delivery(sim):
    now = [NOW]
    v = CertVerifier(sim.webhook_id, sim.fetch_cert, clock=lambda: now[0], max_age_s=10**9)
    headers, body = order_approved(sim)
    v.verify(headers, body)                                     # cached now
    now[0] = NOW + 60 * 86400
    with pytest.raises(WebhookRejected) as e:
        v.verify(headers, body)
    assert e.value.reason == "bad_cert"


def test_a_transmission_time_without_a_zone_is_refused(sim):
    headers, body = order_approved(sim)
    headers["paypal-transmission-time"] = headers["paypal-transmission-time"].rstrip("Z")
    with pytest.raises(WebhookRejected) as e:
        sim.verifier().verify(headers, body)
    assert e.value.reason == "bad_header"
