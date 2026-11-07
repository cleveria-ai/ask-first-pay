"""FakeProvider models what PayPal does on the points the live path depends on (N8: B4, B5)."""
import pytest

from ask_first_pay.fake_provider import DAY, FakeProvider
from ask_first_pay.ports import ProviderError


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def held(clock=None):
    p = FakeProvider(clock=clock or Clock())
    o = p.create_order(10.0, "USD", "booking-1", request_id="order-key-1")
    p.approve(o.order_id)
    return p, p.authorize(o.order_id)


def test_fake_create_order_idempotency_same_request_id_same_order_different_ids_new_orders():
    p = FakeProvider()
    a = p.create_order(10.0, "USD", "booking-1", request_id="key-A")
    again = p.create_order(10.0, "USD", "booking-1", request_id="key-A")
    other = p.create_order(10.0, "USD", "booking-1", request_id="key-B")    # same reference, new key
    assert again.order_id == a.order_id
    assert other.order_id != a.order_id
    assert len(p.orders) == 2 and [c[0] for c in p.calls] == ["create_order", "create_order"]
    # A retry after the payer approved returns that order as it is now, not a fresh one.
    p.approve(a.order_id)
    assert p.create_order(10.0, "USD", "booking-1", request_id="key-A").status == "APPROVED"


def test_fake_create_order_idempotency_without_request_id_always_creates():
    p = FakeProvider()
    assert p.create_order(10.0, "USD", "r").order_id != p.create_order(10.0, "USD", "r").order_id


def test_fake_create_order_idempotency_survives_a_restart():
    p = FakeProvider()
    a = p.create_order(10.0, "USD", "booking-1", request_id="key-A")
    q = FakeProvider()
    q.load_dict(p.to_dict())
    assert q.create_order(10.0, "USD", "booking-1", request_id="key-A").order_id == a.order_id
    assert len(q.orders) == 1


@pytest.mark.parametrize("days", [4, 10, 28, 29])
def test_fake_honor_period_over_capture_still_allowed_up_to_day_29(days):
    clock = Clock()
    p, auth = held(clock)
    clock.t += days * DAY
    c = p.capture(auth.authorization_id, 10.0, request_id=f"cap-{days}")
    assert c.status == "COMPLETED" and p.auths[auth.authorization_id].status == "CAPTURED"


def test_fake_honor_period_capture_refused_after_day_29():
    clock = Clock()
    p, auth = held(clock)
    clock.t += 29 * DAY + 1
    with pytest.raises(ProviderError) as e:
        p.capture(auth.authorization_id, 10.0, request_id="late")
    assert e.value.code == "AUTHORIZATION_EXPIRED" and not p.captures


def test_fake_honor_period_reauthorize_path_kept_until_day_29():
    """Inside the honor period PayPal refuses a reauthorization; after it, a reauthorization gives a
    new authorization with a fresh honor period, which can be captured; after day 29, nothing."""
    clock = Clock()
    p, auth = held(clock)
    with pytest.raises(ProviderError) as e:
        p.reauthorize(auth.authorization_id, request_id="too-soon")
    assert e.value.code == "REAUTHORIZATION_TOO_SOON"
    clock.t += 5 * DAY
    new = p.reauthorize(auth.authorization_id, request_id="r1")
    assert new.authorization_id != auth.authorization_id and p.auths[auth.authorization_id].status == "VOIDED"
    assert p.capture(new.authorization_id, 10.0, request_id="c1").status == "COMPLETED"
    clock2 = Clock()
    p2, auth2 = held(clock2)
    clock2.t += 30 * DAY
    with pytest.raises(ProviderError) as e:
        p2.reauthorize(auth2.authorization_id, request_id="r2")
    assert e.value.code == "AUTHORIZATION_EXPIRED"
