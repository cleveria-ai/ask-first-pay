"""PayPal webhooks: verify the signature, drop duplicates, hand the event to a handler.

PayPal signs every webhook delivery. The signed message is

    <paypal-transmission-id>|<paypal-transmission-time>|<webhook id>|<CRC32 of the raw body>

signed with SHA256withRSA by the key in the certificate at `paypal-cert-url`. `CertVerifier`
checks exactly that, locally, so no call to `/v1/notifications/verify-webhook-signature` is
needed. The certificate download is injected (`fetch_cert`): in the demo and the tests it is
`WebhookSimulator.fetch_cert`, a local double that plays PayPal and signs its own events; against
the sandbox it is `fetch_paypal_cert`, which only downloads from `https://*.paypal.com`.

A webhook never moves money. The most an event can do in this app is make the agent *hold* a
deposit the customer already approved (authorize), which PayPal refuses anyway unless the order
really is approved. Capture, void and refund stay behind the owner's signed mandate.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import time
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

HEADERS = ("paypal-transmission-id", "paypal-transmission-time", "paypal-transmission-sig",
           "paypal-cert-url", "paypal-auth-algo")
AUTH_ALGO = "SHA256withRSA"
MAX_AGE_S = 300            # a delivery older (or newer) than this is refused: limits replays
MAX_BODY = 64 * 1024


class WebhookRejected(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason, self.detail = reason, detail
        super().__init__(f"{reason}: {detail}")


def signed_message(transmission_id: str, transmission_time: str, webhook_id: str, body: bytes) -> bytes:
    """What PayPal signs: the CRC32 is of the raw bytes, as an unsigned decimal."""
    return f"{transmission_id}|{transmission_time}|{webhook_id}|{zlib.crc32(body)}".encode()


def cert_url_allowed(url: str) -> bool:
    """Only an https URL on a paypal.com host may name the signing certificate."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host == "paypal.com" or host.endswith(".paypal.com"))


def _parse_time(value: str) -> float:
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise WebhookRejected("bad_header", f"paypal-transmission-time {value!r}") from e
    if t.tzinfo is None:                     # never guess the server's local time zone
        raise WebhookRejected("bad_header", f"paypal-transmission-time {value!r} has no time zone")
    return t.timestamp()


def fetch_paypal_cert(url: str) -> bytes:
    """Live path (sandbox): download the PEM certificate from PayPal. Not used offline."""
    import httpx
    if not cert_url_allowed(url):
        raise WebhookRejected("bad_cert_url", url)
    r = httpx.get(url, timeout=10.0)
    r.raise_for_status()
    return r.content


@dataclass
class CertVerifier:
    webhook_id: str                                  # the id PayPal gave the webhook subscription
    fetch_cert: Callable[[str], bytes]
    max_age_s: int = MAX_AGE_S
    clock: Callable[[], float] = time.time
    _certs: dict = field(default_factory=dict, repr=False)

    def _public_key(self, url: str):
        if url not in self._certs:
            try:
                self._certs[url] = x509.load_pem_x509_certificate(self.fetch_cert(url))
            except WebhookRejected:
                raise
            except Exception as e:                        # noqa: BLE001
                raise WebhookRejected("bad_cert", f"{type(e).__name__}: {e}") from e
        cert = self._certs[url]
        now = dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc)
        if not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc:   # on every delivery
            raise WebhookRejected("bad_cert", "certificate outside its validity period")
        return cert.public_key()

    def verify(self, headers: dict, body: bytes) -> None:
        h = {k.lower(): v for k, v in headers.items()}
        missing = [k for k in HEADERS if not h.get(k)]
        if missing:
            raise WebhookRejected("missing_header", ", ".join(missing))
        if h["paypal-auth-algo"] != AUTH_ALGO:
            raise WebhookRejected("bad_algo", h["paypal-auth-algo"])
        if not cert_url_allowed(h["paypal-cert-url"]):
            raise WebhookRejected("bad_cert_url", h["paypal-cert-url"])
        if abs(self.clock() - _parse_time(h["paypal-transmission-time"])) > self.max_age_s:
            raise WebhookRejected("stale", h["paypal-transmission-time"])
        try:
            sig = base64.b64decode(h["paypal-transmission-sig"], validate=True)
        except ValueError as e:
            raise WebhookRejected("bad_signature", "not base64") from e
        msg = signed_message(h["paypal-transmission-id"], h["paypal-transmission-time"], self.webhook_id, body)
        try:
            self._public_key(h["paypal-cert-url"]).verify(sig, msg, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature as e:
            raise WebhookRejected("bad_signature", "does not match the certificate") from e


class WebhookSimulator:
    """A local stand-in for PayPal's webhook sender: its own RSA key and self-signed certificate,
    events signed exactly the way PayPal signs them. `fetch_cert` is the double of the
    certificate download, so `CertVerifier` runs its real checks with no network."""

    CERT_URL = "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-local-simulator"

    def __init__(self, webhook_id: str = "WH-LOCAL-SIMULATOR", clock: Callable[[], float] = time.time) -> None:
        self.webhook_id, self.clock = webhook_id, clock
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local webhook simulator")])
        now = dt.datetime.fromtimestamp(clock(), dt.timezone.utc)
        self.cert_pem = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                         .public_key(self._key.public_key()).serial_number(x509.random_serial_number())
                         .not_valid_before(now - dt.timedelta(days=1))
                         .not_valid_after(now + dt.timedelta(days=30))
                         .sign(self._key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM))

    def fetch_cert(self, url: str) -> bytes:
        if url != self.CERT_URL:
            raise WebhookRejected("bad_cert", f"unknown certificate {url}")
        return self.cert_pem

    def verifier(self) -> CertVerifier:
        return CertVerifier(self.webhook_id, self.fetch_cert, clock=self.clock)

    def event(self, event_type: str, resource: dict, event_id: str | None = None) -> tuple[dict, bytes]:
        """(headers, raw body) of one signed delivery, as PayPal would POST it."""
        ev = {"id": event_id or f"WH-EVT-{uuid.uuid4().hex[:16].upper()}", "event_version": "1.0",
              "create_time": dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "resource_type": event_type.split(".")[1].lower(), "event_type": event_type,
              "summary": f"{event_type} (local simulator)", "resource": resource}
        body = json.dumps(ev, separators=(",", ":")).encode()
        tid = str(uuid.uuid4())
        ttime = dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sig = self._key.sign(signed_message(tid, ttime, self.webhook_id, body), padding.PKCS1v15(), hashes.SHA256())
        return ({"paypal-transmission-id": tid, "paypal-transmission-time": ttime,
                 "paypal-transmission-sig": base64.b64encode(sig).decode(),
                 "paypal-cert-url": self.CERT_URL, "paypal-auth-algo": AUTH_ALGO,
                 "content-type": "application/json"}, body)


class WebhookReceiver:
    """verify -> parse -> drop duplicates (PayPal redelivers) -> dispatch by event_type.

    `seen(event_id)` and `remember(event_id, event_type, outcome)` default to memory; the demo
    passes the SQLite store's so a restart does not replay old deliveries."""

    def __init__(self, verifier: CertVerifier, handlers: dict[str, Callable[[dict], str]],
                 seen: Callable[[str], bool] | None = None,
                 remember: Callable[[str, str, str], None] | None = None) -> None:
        self.verifier, self.handlers = verifier, handlers
        self._mem: dict[str, str] = {}
        self.seen = seen or (lambda i: i in self._mem)
        self.remember = remember or (lambda i, t, o: self._mem.__setitem__(i, o))
        self.log: list[dict] = []

    def receive(self, headers: dict, body: bytes) -> dict:
        if len(body) > MAX_BODY:
            raise WebhookRejected("too_large", f"{len(body)} bytes")
        self.verifier.verify(headers, body)
        try:
            ev = json.loads(body)
        except ValueError as e:
            raise WebhookRejected("bad_json", str(e)) from e
        if not isinstance(ev, dict) or not isinstance(ev.get("id"), str) or not isinstance(ev.get("event_type"), str):
            raise WebhookRejected("bad_event", "id and event_type are required")
        if not isinstance(ev.get("resource"), dict):
            raise WebhookRejected("bad_event", "resource must be an object")
        # PayPal's signature covers only the CRC32 of the body, so one signature could be replayed
        # on another body with the same CRC32. Each transmission is accepted once, whatever its body.
        tx = "tx:" + {k.lower(): v for k, v in headers.items()}["paypal-transmission-id"]
        if self.seen(ev["id"]) or self.seen(tx):
            return {"event_id": ev["id"], "event_type": ev["event_type"], "outcome": "duplicate"}
        handler = self.handlers.get(ev["event_type"])
        outcome = handler(ev["resource"]) if handler else "ignored"
        self.remember(tx, ev["event_type"], outcome)
        self.remember(ev["id"], ev["event_type"], outcome)
        row = {"event_id": ev["id"], "event_type": ev["event_type"], "outcome": outcome}
        self.log.append(row)
        return row
