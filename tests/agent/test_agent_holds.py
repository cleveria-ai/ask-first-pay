"""The agent never asks the owner for more than is held, and keeps an old hold capturable."""
from ask_first_pay.agent.loop import text, tool
from ask_first_pay.fake_provider import DAY, FakeProvider
from ask_first_pay.gate import HoldDesk, make_engine, split

import pytest

from .test_agent_flows import World


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


def clocked_world(tmp_path):
    w = World(tmp_path)
    w.clock = Clock()
    w.provider = FakeProvider(clock=w.clock)
    w.engine = make_engine(w.provider, w.engine.person_pub, str(tmp_path / "ledger2.jsonl"))
    w.gate, w.owner = split(w.engine)
    w.desk = HoldDesk(w.provider)
    return w


def test_agent_capture_request_over_the_hold_never_reaches_the_owner(w):
    w.book_and_hold()
    w.say("charge 500", [[tool("request_capture", "c", booking_id="booking-1", amount=500.0)], [text("no")]])
    assert "held 10.00" in w.tool_results()[-1]
    assert w.state.mandates == {} and w.owner.pending == {}


def test_agent_second_refund_is_bounded_by_what_is_left(w):
    w.book_and_hold()
    w.say("no-show", [[tool("request_capture", "c", booking_id="booking-1", amount=10.0)], [text("ok")]])
    (cap,) = w.state.mandates
    w.approve(cap)
    w.say("go", [[tool("execute_mandate", "e", mandate_id=cap)], [text("ok")]])
    w.say("refund 6", [[tool("request_refund", "r", booking_id="booking-1", amount=6.0)], [text("ok")]])
    (ref,) = [m for m in w.state.mandates if m != cap]
    w.approve(ref)
    w.say("go", [[tool("execute_mandate", "g", mandate_id=ref)], [text("ok")]])
    w.say("refund 6 more", [[tool("request_refund", "s", booking_id="booking-1", amount=6.0)], [text("no")]])
    assert "4.00 still captured" in w.tool_results()[-1] and len(w.state.mandates) == 2


def test_agent_refresh_hold_inside_honor_period_keeps_the_hold(tmp_path):
    w = clocked_world(tmp_path)
    auth = w.book_and_hold()
    w.say("no-show", [[tool("refresh_hold", "h", booking_id="booking-1")], [text("ok")]])
    assert "'refreshed': False" in w.tool_results()[-1]
    assert w.state.bookings["booking-1"]["authorization_id"] == auth


def test_agent_no_show_after_honor_period_reauthorizes_then_captures_once(tmp_path):
    w = clocked_world(tmp_path)
    old = w.book_and_hold()
    w.clock.t += 5 * DAY                                   # the appointment is 5 days after the booking
    w.say("no-show", [[tool("refresh_hold", "h", booking_id="booking-1")],
                      [tool("request_capture", "c", booking_id="booking-1", amount=10.0)], [text("asked")]])
    new = w.state.bookings["booking-1"]["authorization_id"]
    assert new != old and w.provider.auths[old].status == "VOIDED"
    (mid,) = w.state.mandates
    assert w.owner.get(mid)["recipient"] == new             # the owner signs for the live hold
    w.approve(mid)
    w.say("go", [[tool("execute_mandate", "e", mandate_id=mid)], [text("done")]])
    assert [c[0] for c in w.moves()] == ["capture"] and w.provider.auths[new].status == "CAPTURED"
