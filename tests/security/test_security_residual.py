"""Attacks that are NOT closed. Each test pins the current, known behaviour and what still holds around it,
so the residual risk is measured, not guessed (docs/SECURITY_REVIEW.md, 'Residual risks')."""
from ask_first import MandateRejected

from ask_first_pay.agent import AgentState
from ask_first_pay.agent.tools import Toolbox
from tests.security.test_security_agent import _book_and_hold


def test_approval_fatigue_agent_can_queue_many_identical_requests(rig):
    """OPEN (low): nothing stops a model asking for the same capture again and again. Every one is a
    separate mandate that needs its own owner signature, and each is capped by the held deposit, so
    the harm is owner annoyance, not money."""
    state = _book_and_hold(rig)
    box = Toolbox(state, rig.agent, rig.desk)
    ids = {box.call("request_capture", {"booking_id": "booking-1", "amount": 10})["mandate_id"] for _ in range(50)}
    assert len(ids) == 50 and not rig.calls("capture")
    for jti in ids:
        assert box.call("execute_mandate", {"mandate_id": jti})["rejected"] == "not_approved"


def test_ledger_noise_agent_can_append_rejected_rows(rig):
    """OPEN (low): every rejected try is logged, which is the point, but a looping model can bloat the
    ledger. The chain stays valid and no row can be an 'executed' one without a capture."""
    auth, jti = rig.approved_capture(10.0)
    rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    for _ in range(100):
        try:
            rig.agent.execute(jti, "capture_deposit", auth, 10.0)
        except MandateRejected:
            pass
    rows = rig.engine.ledger.entries()
    assert len(rows) == 101 and sum(r["result"] == "executed" for r in rows) == 1 and rig.engine.ledger.verify()["ok"]


def test_demo_has_no_login_so_anyone_who_reaches_it_can_read_and_press_scenarios(demo):
    """OPEN (accepted, README 'Limits'): single-shop demo, no auth. What reaching it does NOT give:
    approving (needs the owner's private key) or moving money."""
    assert demo.client.get("/owner/api/mandates").status_code == 200
    assert demo.client.post("/scenario/no_show").status_code == 303
    assert demo.pending_ids() and not demo.calls("capture")
    assert demo.client.post("/owner/approve", json={"mandate_id": demo.pending_ids()[0], "signature": "00" * 64}).status_code == 400


def test_chat_body_is_read_whole_before_truncation(demo):
    """OPEN (low): /chat/send reads the entire body before cutting the message to 500 characters, so a
    reverse proxy has to cap request size. The message that reaches the agent is capped."""
    demo.client.post("/chat/send", content="message=" + "a" * 2_000_000, headers={"content-type": "application/x-www-form-urlencoded"})
    assert max(len(m.text) for m in demo.state.front.messages if m.who == "customer") == 500
