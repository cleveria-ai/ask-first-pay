"""N8: what the agent does on the live path (B1, B3, B6, B13)."""
import httpx
import pytest
from anthropic.types import RedactedThinkingBlock, TextBlock, ThinkingBlock, ToolUseBlock
from ask_first import generate_pair

from ask_first_pay.agent import AgentState, AnthropicModel, run_turn
from ask_first_pay.agent.loop import MIN_MAX_TOKENS, text, tool
from ask_first_pay.demo.offline_model import OfflineFrontDeskModel
from ask_first_pay.fake_provider import DAY
from ask_first_pay.gate import HoldDesk, make_engine, split
from ask_first_pay.paypal import PayPalProvider

from tests.paypal.fakepaypal import MockPayPal

from .test_agent_flows import World
from .test_agent_holds import clocked_world


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


# ---- B1: the order's PayPal-Request-Id lives on the booking ---------------------------------
def test_agent_create_order_request_id_is_kept_on_the_booking_and_reused(tmp_path):
    w = World(tmp_path)
    w.say("book", [[tool("book_slot", "a", customer="Ana", slot="2026-11-16 09:00")],
                   [tool("create_deposit_order", "b", booking_id="booking-1")],
                   [tool("create_deposit_order", "c", booking_id="booking-1")],     # the model repeats itself
                   [text("ok")]])
    b = w.state.bookings["booking-1"]
    assert b["order_request_id"] and len(w.provider.orders) == 1
    (tmp_path / "other").mkdir()
    w2 = World(tmp_path / "other")
    w2.provider = w.provider                                     # same PayPal, a new conversation
    w2.desk = HoldDesk(w.provider)
    w2.say("book", [[tool("book_slot", "a", customer="Bo", slot="2026-11-16 09:00")],
                    [tool("create_deposit_order", "b", booking_id="booking-1")], [text("ok")]])
    assert w2.state.bookings["booking-1"]["order_id"] != b["order_id"] and len(w.provider.orders) == 2


# ---- B3: refresh_hold tells "still valid" from "gone" ---------------------------------------
class PayPalWorld:
    """The agent over PayPalProvider + a mocked PayPal, with the demo's offline model driving it."""

    def __init__(self, tmp_path):
        self.mock = MockPayPal()
        self.provider = PayPalProvider("cid", "secret", transport=httpx.MockTransport(self.mock))
        self.priv, pub = generate_pair()
        self.gate, self.owner = split(make_engine(self.provider, pub, str(tmp_path / "ledger.jsonl")))
        self.desk = HoldDesk(self.provider)
        self.state = AgentState()
        self.model = OfflineFrontDeskModel(self.state)

    def say(self, message):
        _, replies = run_turn(self.state, message, gate=self.gate, desk=self.desk, model=self.model)
        return replies

    def hold(self):
        self.say("book Mon 16 Nov 09:00")
        self.say("I paid")
        b = self.state.bookings["booking-1"]
        assert b["status"] == "deposit_held"
        return b

    def reauth_posts(self):
        return [r for r in self.mock.writes() if r.url.path.endswith("/reauthorize")]


def unprocessable(issue=None, status=422):
    body = {"name": "UNPROCESSABLE_ENTITY" if status == 422 else "RESOURCE_NOT_FOUND",
            "message": "The requested action could not be performed."}
    if issue:
        body["details"] = [{"issue": issue, "description": "..."}]
    return (status, body)


@pytest.mark.parametrize("error", [unprocessable("AUTHORIZATION_VOIDED"), unprocessable("AUTHORIZATION_EXPIRED"),
                                   unprocessable("PREVIOUSLY_CAPTURED"), unprocessable(None),
                                   unprocessable("INVALID_RESOURCE_ID", status=404)],
                         ids=["voided", "expired", "captured", "bare-422", "not-found"])
def test_agent_refresh_hold_definitive_error_marks_not_held_and_blocks_capture(tmp_path, error):
    w = PayPalWorld(tmp_path)
    b = w.hold()
    w.mock.fail_next.append(error)
    replies = w.say("[business] booking-1 did not show up. Ask the owner to capture the deposit.")
    assert len(w.reauth_posts()) == 1
    assert b["status"] == "hold_ended"
    assert w.state.mandates == {} and w.owner.pending == {}           # nobody is asked to sign
    assert "no longer held" in " ".join(replies)
    out = run_turn(w.state, "capture it", gate=w.gate, desk=w.desk, model=_script(
        [tool("request_capture", "q", booking_id="booking-1", amount=10.0)]))[0]
    assert "no held deposit" in out.messages[-2]["content"][0]["content"]
    assert w.owner.pending == {} and not [r for r in w.mock.writes() if r.url.path.endswith("/capture")]


def test_agent_refresh_hold_too_soon_in_paypal_format_is_not_definitive_and_keeps_the_hold(tmp_path):
    """PayPal answers a reauthorize inside the honor period with 422 UNPROCESSABLE_ENTITY and the
    issue REAUTHORIZATION_TOO_SOON in details: the hold is fine, the capture request goes ahead."""
    w = PayPalWorld(tmp_path)
    b = w.hold()
    w.mock.fail_next.append(unprocessable("REAUTHORIZATION_TOO_SOON"))
    w.say("[business] booking-1 did not show up. Ask the owner to capture the deposit.")
    assert b["status"] == "deposit_held" and b["authorization_id"] == "3C679366HH908993F"
    (mid,) = w.state.mandates
    assert w.owner.get(mid)["recipient"] == "3C679366HH908993F"


def test_agent_refresh_hold_transient_is_not_definitive_and_falls_back_to_the_current_hold(tmp_path):
    w = PayPalWorld(tmp_path)
    b = w.hold()
    w.mock.fail_next.append(httpx.ConnectTimeout("no answer"))
    w.say("[business] booking-1 did not show up. Ask the owner to capture the deposit.")
    assert b["status"] == "deposit_held" and len(w.state.mandates) == 1


def test_agent_refresh_hold_definitive_on_the_fake_after_day_29(tmp_path):
    w = clocked_world(tmp_path)
    w.book_and_hold()
    w.clock.t += 30 * DAY
    w.say("no-show", [[tool("refresh_hold", "h", booking_id="booking-1")],
                      [tool("request_capture", "c", booking_id="booking-1", amount=10.0)], [text("?")]])
    results = w.tool_results()
    assert "AUTHORIZATION_EXPIRED" in results[-2] and "'deposit_held': False" in results[-2]
    assert "no held deposit" in results[-1] and w.state.mandates == {}
    assert w.state.bookings["booking-1"]["status"] == "hold_ended"


# ---- B13: request_void needs a held deposit ------------------------------------------------
def test_agent_request_void_not_held_after_capture_is_refused(w):
    w.book_and_hold()
    w.say("no-show", [[tool("request_capture", "c", booking_id="booking-1", amount=10.0)], [text("ok")]])
    (cap,) = w.state.mandates
    w.approve(cap)
    w.say("go", [[tool("execute_mandate", "e", mandate_id=cap)], [text("ok")]])
    assert w.state.bookings["booking-1"]["status"] == "captured"
    w.say("cancel", [[tool("request_void", "v", booking_id="booking-1")], [text("no")]])
    assert "no held deposit" in w.tool_results()[-1]
    assert list(w.state.mandates) == [cap] and list(w.owner.pending) == [cap]


def test_agent_request_void_not_held_before_the_payer_approved_or_after_the_hold_ended(tmp_path):
    w = clocked_world(tmp_path)
    w.say("book", [[tool("book_slot", "a", customer="Ana", slot="2026-11-16 09:00")],
                   [tool("create_deposit_order", "b", booking_id="booking-1")],
                   [tool("request_void", "v", booking_id="booking-1")], [text("ok")]])
    assert "no held deposit" in w.tool_results()[-1]
    w.provider.approve(w.state.bookings["booking-1"]["order_id"])
    w.say("paid", [[tool("confirm_deposit", "c", booking_id="booking-1")], [text("ok")]])
    w.clock.t += 30 * DAY
    w.say("cancel", [[tool("refresh_hold", "h", booking_id="booking-1")],
                     [tool("request_void", "v", booking_id="booking-1")], [text("ok")]])
    assert "no held deposit" in w.tool_results()[-1] and w.state.mandates == {}


def test_agent_request_void_still_works_on_a_held_deposit(w):
    w.book_and_hold()
    w.say("cancel", [[tool("request_void", "v", booking_id="booking-1")], [text("asked")]])
    (mid,) = w.state.mandates
    w.approve(mid)
    w.say("go", [[tool("execute_mandate", "e", mandate_id=mid)], [text("ok")]])
    assert [c[0] for c in w.moves()] == ["void"] and w.state.bookings["booking-1"]["status"] == "cancelled"


# ---- B6: the Claude loop keeps the whole assistant turn ------------------------------------
class FakeMessages:
    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def create(self, **kw):
        # Snapshot what was sent: the history list is mutated after the call returns.
        self.seen.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        return type("Message", (), {"content": self.turns.pop(0)})()


class FakeClient:
    def __init__(self, turns):
        self.messages = FakeMessages(turns)


THINK = ThinkingBlock(type="thinking", thinking="The customer wants Monday 09:00.", signature="c2lnbmF0dXJlLTE=")
REDACTED = RedactedThinkingBlock(type="redacted_thinking", data="ZW5jcnlwdGVk")


def test_agent_loop_keeps_thinking_blocks_unchanged_in_history(w):
    client = FakeClient([
        [THINK, REDACTED, TextBlock(type="text", text="Booking it."),
         ToolUseBlock(type="tool_use", id="toolu_1", name="book_slot",
                      input={"customer": "Ana", "slot": "2026-11-16 09:00"})],
        [ThinkingBlock(type="thinking", thinking="", signature="c2lnLTI="), TextBlock(type="text", text="Booked.")],
    ])
    state, replies = run_turn(AgentState(), "book Monday 9", gate=w.gate, desk=w.desk,
                              model=AnthropicModel(model="test-model", client=client))
    assert replies == ["Booking it.", "Booked."]
    first_turn = state.messages[1]["content"]
    assert [b["type"] for b in first_turn] == ["thinking", "redacted_thinking", "text", "tool_use"]
    assert first_turn[0] == {"type": "thinking", "thinking": THINK.thinking, "signature": THINK.signature}
    assert first_turn[1] == {"type": "redacted_thinking", "data": REDACTED.data}
    # The second request carries that turn back exactly, before the tool result.
    sent = client.messages.seen[1]["messages"]
    assert sent[1] == {"role": "assistant", "content": first_turn}
    assert sent[2]["content"][0]["tool_use_id"] == "toolu_1"
    assert state.messages[-1]["content"][0]["type"] == "thinking"            # the last turn too


def test_agent_loop_history_blocks_with_max_tokens_and_adaptive_thinking(w, monkeypatch):
    monkeypatch.delenv("ASK_FIRST_MAX_TOKENS", raising=False)
    client = FakeClient([[TextBlock(type="text", text="hi")]])
    run_turn(AgentState(), "hello", gate=w.gate, desk=w.desk, model=AnthropicModel(model="m", client=client))
    kw = client.messages.seen[0]
    assert kw["max_tokens"] >= 4096 and kw["thinking"] == {"type": "adaptive"}


@pytest.mark.parametrize("env,expected", [("20000", 20000), ("2048", MIN_MAX_TOKENS), ("lots", 16000)])
def test_agent_loop_thinking_room_max_tokens_from_env(w, monkeypatch, env, expected):
    monkeypatch.setenv("ASK_FIRST_MAX_TOKENS", env)
    client = FakeClient([[TextBlock(type="text", text="hi")]])
    run_turn(AgentState(), "hello", gate=w.gate, desk=w.desk, model=AnthropicModel(model="m", client=client))
    assert client.messages.seen[0]["max_tokens"] == expected       # what reaches the API, not an attribute
    assert MIN_MAX_TOKENS >= 4096


def _script(*turns):
    from ask_first_pay.agent.loop import ScriptedModel
    return ScriptedModel([*turns, [text("ok")]])
