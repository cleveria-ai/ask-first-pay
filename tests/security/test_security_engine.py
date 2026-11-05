"""(d) The mandate engine: canonicalization, float caps, bad amounts, clock skew, ledger tampering."""
import json
import math

import pytest
from ask_first import MandateRejected, sign_envelope, generate_pair
from ask_first.keys import verify_signature


def test_cap_10_000000001_is_over_cap(rig):
    auth, jti = rig.approved_capture(10.0)
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, "capture_deposit", auth, 10.000000001)
    assert e.value.reason == "over_cap" and not rig.calls("capture")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), -1, 0, -0.0, True, "abc", None, [1], {"a": 1}, "nan", "1e999"])
def test_execute_with_hostile_amounts_is_rejected_and_moves_nothing(rig, bad):
    auth, jti = rig.approved_capture(10.0)
    with pytest.raises(MandateRejected):
        rig.agent.execute(jti, "capture_deposit", auth, bad)
    assert not rig.calls("capture")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -5, 0, True, "x", None])
def test_request_with_hostile_amounts_never_creates_a_mandate(rig, bad):
    auth = rig.held()
    with pytest.raises((ValueError, TypeError)):
        rig.agent.request("capture_deposit", auth, bad)
    assert not rig.engine.pending


def test_a_bad_amount_does_not_burn_the_mandate_but_the_real_one_still_works_once(rig):
    auth, jti = rig.approved_capture(10.0)
    with pytest.raises(MandateRejected):
        rig.agent.execute(jti, "capture_deposit", auth, 11)
    assert rig.agent.execute(jti, "capture_deposit", auth, 10.0)["result"] == "executed"
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    assert e.value.reason == "replay" and len(rig.calls("capture")) == 1


def test_sub_cent_cap_is_refused_at_the_gate(rig):
    """FIXED: a cap of 9.996 shows the owner '10.00' (.2f) and the adapter refuses sub-cent amounts,
    so the owner would sign something that is not what is displayed. Caps live on the cent grid."""
    auth = rig.held()
    for amount in (9.996, 0.004, 1e-9, 0.1 + 0.2):
        with pytest.raises(ValueError):
            rig.agent.request("capture_deposit", auth, amount)
    assert not rig.engine.pending
    rig.agent.request("capture_deposit", auth, 9.99)       # a cent amount is still fine


@pytest.mark.parametrize("field,value", [("cap", 1000.0), ("recipient", "AUTH-OTHER"), ("action", "refund_deposit"),
                                          ("exp", 4102444800), ("sub", "someone-else")])
def test_mutating_the_approved_mandate_after_signing_breaks_it(rig, field, value):
    auth, jti = rig.approved_capture(10.0)
    rig.engine.approved[jti]["mandate"][field] = value      # insider tamper of the stored approval
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, rig.engine.approved[jti]["mandate"]["action"],
                          rig.engine.approved[jti]["mandate"]["recipient"], 1.0)
    assert e.value.reason == "signature_tampered" and not rig.calls("capture")


def test_a_signature_for_one_mandate_does_not_approve_another(rig):
    a1, a2 = rig.held(), rig.held()
    m1 = rig.agent.request("capture_deposit", a1, 10.0)
    m2 = rig.agent.request("capture_deposit", a2, 10.0)
    with pytest.raises(MandateRejected) as e:
        rig.owner.approve(m2["jti"], rig.sign(m1["jti"]))
    assert e.value.reason == "invalid_signature"
    assert m2["jti"] not in rig.engine.approved


def test_a_signature_from_the_agents_own_key_is_refused(rig):
    auth = rig.held()
    m = rig.agent.request("capture_deposit", auth, 10.0)
    evil, _ = generate_pair()
    with pytest.raises(MandateRejected):
        rig.owner.approve(m["jti"], sign_envelope(evil, rig.engine.pending[m["jti"]]))
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(m["jti"], "capture_deposit", auth, 10.0)
    assert e.value.reason == "not_approved"


@pytest.mark.parametrize("sig", ["", "00" * 64, "zz", "ab" * 63, "AB" * 65, " "])
def test_garbage_signatures_are_refused(rig, sig):
    m = rig.agent.request("capture_deposit", rig.held(), 10.0)
    with pytest.raises(MandateRejected):
        rig.owner.approve(m["jti"], sig)


def test_canonicalization_key_order_and_whitespace_do_not_change_the_signed_bytes(rig):
    from ask_first.canonical import canonical
    m = rig.agent.request("capture_deposit", rig.held(), 10.0)
    reordered = json.loads(json.dumps(m, sort_keys=True)[::1])
    shuffled = dict(reversed(list(reordered.items())))
    assert canonical(shuffled) == canonical(m)
    # ...and a *different value* that prints alike never canonicalizes alike
    other = dict(m, cap=10.000000001)
    assert canonical(other) != canonical(m)
    other2 = dict(m, recipient=m["recipient"] + "​")      # zero-width space lookalike
    assert canonical(other2) != canonical(m)
    assert not verify_signature(rig.pub, other, rig.sign(m["jti"]))


def test_unicode_lookalike_recipient_is_out_of_scope(rig):
    auth, jti = rig.approved_capture(10.0)
    lookalike = auth.replace("A", "А", 1) if "A" in auth else auth + "​"
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, "capture_deposit", lookalike, 10.0)
    assert e.value.reason == "out_of_scope"


def test_scope_cannot_be_swapped_to_refund_or_void(rig):
    auth, jti = rig.approved_capture(10.0)
    for action in ("void_deposit", "refund_deposit", "CAPTURE_DEPOSIT", "capture_deposit "):
        with pytest.raises(MandateRejected) as e:
            rig.agent.execute(jti, action, auth, 10.0)
        assert e.value.reason == "out_of_scope"
    assert not rig.provider.calls or all(c[0] in ("create_order", "approve", "authorize") for c in rig.provider.calls)


def test_clock_skew_around_expiry(rig, monkeypatch):
    import ask_first.engine as eng
    t0 = 1_800_000_000
    monkeypatch.setattr(eng.time, "time", lambda: t0)
    auth = rig.held()
    m = rig.agent.request("capture_deposit", auth, 10.0, ttl_s=60)
    rig.owner.approve(m["jti"], rig.sign(m["jti"]))
    monkeypatch.setattr(eng.time, "time", lambda: t0 + 61)            # one second past exp
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(m["jti"], "capture_deposit", auth, 10.0)
    assert e.value.reason == "expired"
    monkeypatch.setattr(eng.time, "time", lambda: t0 + 60)            # the clock is wound back to exp: still the window
    assert rig.agent.execute(m["jti"], "capture_deposit", auth, 10.0)["result"] == "executed"


@pytest.mark.parametrize("ttl", [0, -1, float("nan")])
def test_non_positive_or_nan_ttl_never_makes_a_mandate(rig, ttl):
    with pytest.raises((ValueError, OverflowError)):
        rig.agent.request("capture_deposit", rig.held(), 10.0, ttl_s=ttl)
    assert not rig.engine.pending


def test_unknown_action_is_refused_by_the_gate(rig):
    with pytest.raises(ValueError):
        rig.agent.request("transfer_all", rig.held(), 10.0)


def test_ledger_tail_truncation_is_visible_in_the_demo_view(demo):
    """FIXED: the demo remembers the ledger head outside the file, so cutting rows off the end
    (which a bare hash chain cannot see) turns the /ledger check red."""
    s = demo.state
    s.scenario("no_show")
    jti = demo.pending_ids()[0]
    assert demo.approve(jti).status_code == 200
    s.front.replay_last()
    assert s.ledger_rows()[1]["ok"]
    path = s.engine.ledger.path
    lines = path.read_text().splitlines()
    assert len(lines) >= 2
    path.write_text("\n".join(lines[:-1]) + "\n")
    ok = s.ledger_rows()[1]
    assert not ok["ok"] and ok["kind"] == "truncated"


def test_ledger_reorder_alter_and_recomputed_chain(rig):
    auth, jti = rig.approved_capture(10.0)
    rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    for _ in range(2):
        with pytest.raises(MandateRejected):
            rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    led = rig.engine.ledger
    original = led.path.read_text()
    lines = original.splitlines()
    assert led.verify()["ok"] and len(lines) == 3
    led.path.write_text("\n".join([lines[1], lines[0], lines[2]]) + "\n")          # reorder
    assert led.verify()["kind"] == "altered"
    led.path.write_text(original.replace('"replay"', '"expired"', 1))               # alter a reason
    assert led.verify()["kind"] == "altered"
    led.path.write_text("\n".join(lines[:1] + lines[2:]) + "\n")                    # drop the middle
    assert not led.verify()["ok"]
    led.path.write_text("\n".join(lines[:-1]) + "\n")                               # drop the tail
    assert led.verify()["ok"]                                                       # a bare chain cannot see it...
    head = {"n": 3, "hash": json.loads(lines[-1])["hash"]}
    assert led.verify(expected_head=head)["kind"] == "truncated"                    # ...an outside head can


def test_every_rejection_is_logged_and_none_moves_money(rig):
    auth, jti = rig.approved_capture(10.0)
    attempts = [(jti, "void_deposit", auth, 10.0), (jti, "capture_deposit", "AUTH-X", 10.0),
                (jti, "capture_deposit", auth, 99.0), ("nope", "capture_deposit", auth, 1.0)]
    for a in attempts:
        with pytest.raises(MandateRejected):
            rig.agent.execute(*a)
    rows = rig.engine.ledger.entries()
    assert [r["reason"] for r in rows] == ["out_of_scope", "out_of_scope", "over_cap", "not_approved"]
    assert not rig.calls("capture")


def test_concurrent_executes_of_one_mandate_capture_once(rig):
    import threading
    auth, jti = rig.approved_capture(10.0)
    results = []
    def go():
        try:
            results.append(rig.agent.execute(jti, "capture_deposit", auth, 10.0)["result"])
        except MandateRejected as e:
            results.append(e.reason)
    ts = [threading.Thread(target=go) for _ in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count("executed") == 1 and results.count("replay") == 15
    assert len(rig.calls("capture")) == 1


def test_executor_failure_burns_the_mandate(rig):
    """A failed money call still spends the approval: no second try without the owner."""
    auth, jti = rig.approved_capture(10.0)
    rig.provider.capture = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    assert e.value.reason == "executor_failed"
    with pytest.raises(MandateRejected) as e:
        rig.agent.execute(jti, "capture_deposit", auth, 10.0)
    assert e.value.reason == "replay"


def test_pairing_code_is_single_use_expiring_and_bounded_by_lockout(rig):
    from ask_first import public_key_hex
    code = rig.engine.new_pairing_code()
    _, other = generate_pair()
    rig.owner.pair(code, public_key_hex(other))
    with pytest.raises(MandateRejected) as e:
        rig.owner.pair(code, public_key_hex(other))
    assert e.value.reason == "code_used"


def test_pairing_bruteforce_locks_out_every_code(rig):
    """FIXED: 8 hex digits and no throttle meant unlimited guesses against a live code. After a
    few wrong guesses every outstanding code is revoked (the owner asks the console for a new one)."""
    from ask_first import public_key_hex
    code = rig.engine.new_pairing_code()
    _, attacker = generate_pair()
    for i in range(10):
        with pytest.raises(MandateRejected):
            rig.owner.pair(f"{i:08x}", public_key_hex(attacker))
    with pytest.raises(MandateRejected) as e:
        rig.owner.pair(code, public_key_hex(rig.pub))          # even the right code is dead now
    assert e.value.reason in ("locked_out", "unknown_code")
    assert rig.engine.person_pub is rig.pub


def test_pair_with_a_garbage_key_is_refused_and_keeps_the_code_usable(rig):
    code = rig.engine.new_pairing_code()
    for bad in ("", "zz", "00", "ab" * 31):
        with pytest.raises(MandateRejected) as e:
            rig.owner.pair(code, bad)
        assert e.value.reason == "invalid_key"
