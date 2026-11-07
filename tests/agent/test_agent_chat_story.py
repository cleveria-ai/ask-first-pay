"""N10 on the Claude path, offline: a fake Anthropic client records exactly what reaches the API.

No key and no network: `AnthropicModel(client=FakeClient(...))`, as in test_agent_live_ready.
"""
from anthropic.types import TextBlock, ToolUseBlock

from ask_first_pay.agent import AgentState, AnthropicModel, run_turn

from .test_agent_flows import World, w  # noqa: F401  (the `w` fixture)
from .test_agent_live_ready import FakeClient


def claude_turn(w, message, *turns, state=None):
    client = FakeClient(list(turns))
    state, replies = run_turn(state or w.state, message, gate=w.gate, desk=w.desk,
                              model=AnthropicModel(model="m", client=client))
    w.state = state
    return client.messages.seen, replies


def held_and_captured(w):
    w.book_and_hold()
    w.say("[business] booking-1 did not show up", [
        [{"type": "tool_use", "id": "q", "name": "request_capture", "input": {"booking_id": "booking-1", "amount": 10.0}}],
        [{"type": "text", "text": "Asked."}]])
    (mid,) = w.state.mandates
    w.approve(mid)
    w.say("[owner] approved", [[{"type": "tool_use", "id": "x", "name": "execute_mandate", "input": {"mandate_id": mid}}],
                               [{"type": "text", "text": "Done."}]])
    assert [c[0] for c in w.moves()] == ["capture"]


def test_business_name_from_env_is_what_the_model_is_told(w, monkeypatch):
    monkeypatch.setenv("ASK_FIRST_BUSINESS", "Consultorio Doña Inventada")
    seen, _ = claude_turn(w, "hello", [TextBlock(type="text", text="Hi.")])
    system = seen[0]["system"]
    assert "Consultorio Doña Inventada (fictional)" in system and "Bright Smile" not in system
    monkeypatch.delenv("ASK_FIRST_BUSINESS")
    seen, _ = claude_turn(w, "hello", [TextBlock(type="text", text="Hi.")], state=AgentState())
    assert "Clínica Bahía Imaginaria (fictional)" in seen[0]["system"]


def test_goodwill_message_rule_and_language_rule_reach_the_model(w):
    seen, _ = claude_turn(w, "hola", [TextBlock(type="text", text="Hola.")])
    system = seen[0]["system"]
    assert "Reply in the customer's language" in system
    assert "explains a missed visit and asks for the deposit back" in system and "request_refund" in system
    assert "Never promise the refund" in system
    assert 'Never use a placeholder such as "Customer"' in system


def test_customer_wording_rules_reach_the_model(w):
    seen, _ = claude_turn(w, "hello", [TextBlock(type="text", text="Hi.")])
    system = seen[0]["system"]
    for line in ("It is held, not charged. If you cancel, a person at the clinic releases it.",
                 "I can't move your deposit myself; I've asked the clinic.",
                 "Nothing was charged, so there is nothing to refund."):
        assert line in system


def test_goodwill_message_on_the_claude_path_only_asks_the_owner(w):
    """The customer's words reach the model; its request_refund becomes a pending mandate and
    nothing else: no refund until the owner signs, and the model has no other way to move money."""
    held_and_captured(w)
    msg = "I'm so sorry, my son was in the ER all morning. Can I get my deposit back?"
    seen, replies = claude_turn(
        w, msg,
        [ToolUseBlock(type="tool_use", id="toolu_r", name="request_refund", input={"booking_id": "booking-1", "amount": 10.0})],
        [TextBlock(type="text", text="I'm sorry to hear that. I can't move your deposit myself; I've asked the clinic.")])
    assert seen[0]["messages"][-1] == {"role": "user", "content": msg}        # the customer's own words
    refunds = [m for m in w.state.mandates.values() if m["action"] == "refund_deposit"]
    assert len(refunds) == 1 and refunds[0]["amount"] == 10.0
    assert [c[0] for c in w.moves()] == ["capture"]                            # no refund yet
    # executing it before the owner signs is refused by the gate
    (rid,) = [k for k, m in w.state.mandates.items() if m["action"] == "refund_deposit"]
    claude_turn(w, "[owner] approved", [ToolUseBlock(type="tool_use", id="toolu_x", name="execute_mandate",
                                                     input={"mandate_id": rid})],
                [TextBlock(type="text", text="Not yet.")])
    assert [c[0] for c in w.moves()] == ["capture"]


def test_customer_name_placeholder_from_the_model_is_refused(w):
    _, _ = claude_turn(w, "book Monday 9", [ToolUseBlock(type="tool_use", id="toolu_b", name="book_slot",
                                                         input={"customer": "Customer", "slot": "2026-11-16 09:00"})],
                       [TextBlock(type="text", text="May I have your name?")])
    assert w.state.bookings == {}
    _, _ = claude_turn(w, "I'm Lucía", [ToolUseBlock(type="tool_use", id="toolu_c", name="book_slot",
                                                     input={"customer": "  Lucía  ", "slot": "2026-11-16 09:00"})],
                       [TextBlock(type="text", text="Booked.")])
    assert w.state.bookings["booking-1"]["customer"] == "Lucía"
