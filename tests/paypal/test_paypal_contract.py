"""The same story on FakeProvider and on PayPalProvider (mock transport): same statuses."""
import httpx

from ask_first_pay.fake_provider import FakeProvider
from ask_first_pay.paypal import PayPalProvider

from .fakepaypal import MockPayPal


def story(p, approve=lambda oid: None):
    out = []
    o = p.create_order(10.0, "USD", "booking-42")
    out.append(("order", o.status in ("CREATED", "PAYER_ACTION_REQUIRED"), bool(o.approve_url)))
    approve(o.order_id)
    a = p.authorize(o.order_id)
    out.append(("authorize", a.status, a.amount))
    c = p.capture(a.authorization_id, 10.0, "jti-cap")
    out.append(("capture", c.status, c.amount))
    r = p.refund(c.capture_id, 4.0, "jti-ref")
    out.append(("refund", r.status, r.amount))
    # cancellation path on a second booking
    o2 = p.create_order(10.0, "USD", "booking-43")
    approve(o2.order_id)
    a2 = p.authorize(o2.order_id)
    v = p.void(a2.authorization_id, "jti-void")
    out.append(("void", v.status, v.amount))
    return out


def test_contract_same_statuses_on_fake_and_paypal():
    fake = FakeProvider()
    paypal = PayPalProvider("cid", "secret", transport=httpx.MockTransport(MockPayPal()))
    a = story(fake, approve=fake.approve)
    b = story(paypal)
    assert a == b
    assert [s[0] for s in a] == ["order", "authorize", "capture", "refund", "void"]
    assert [s[1] for s in a[1:]] == ["CREATED", "COMPLETED", "COMPLETED", "VOIDED"]
