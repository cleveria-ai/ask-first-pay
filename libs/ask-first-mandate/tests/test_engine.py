import threading
import time

import pytest
from conftest import approve

from ask_first import MandateRejected, generate_pair, sign_envelope


def test_request_stays_pending_and_executes_nothing(engine, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 50.0)
    assert mandate["cap"] == 50.0
    assert mandate["jti"] in engine.pending
    assert mandate["jti"] not in engine.approved
    assert engine.view_ledger()["entries"] == []
    assert calls == []


def test_request_rejects_non_positive_amount(engine):
    with pytest.raises(ValueError):
        engine.request("assistant", "pay", "acct-1", 0)


def test_execute_without_approval_is_rejected_and_logged(engine, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 10.0)
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 10.0)
    assert exc.value.reason == "not_approved"
    entries = engine.view_ledger()["entries"]
    assert len(entries) == 1 and entries[0]["result"] == "rejected"
    assert calls == []


def test_approve_with_another_key_is_rejected(engine):
    mandate = engine.request("assistant", "pay", "acct-1", 5.0)
    other_priv, _ = generate_pair()
    bad = sign_envelope(other_priv, engine.pending[mandate["jti"]])
    with pytest.raises(MandateRejected) as exc:
        engine.approve(mandate["jti"], bad)
    assert exc.value.reason == "invalid_signature"


def test_happy_path_runs_executor_once_and_lands_in_ledger(engine, person_pair, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])

    result = engine.execute(mandate["jti"], "pay", "acct-1", 20.0)
    assert result["result"] == "executed"
    assert result["outcome"] == {"done": True, "action": "pay", "recipient": "acct-1",
                                 "amount": 20.0}
    assert len(calls) == 1

    view = engine.view_ledger()
    assert view["verification"]["ok"] is True
    assert [e["result"] for e in view["entries"]] == ["executed"]


def test_replay_is_rejected_and_executor_not_called_again(engine, person_pair, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])
    engine.execute(mandate["jti"], "pay", "acct-1", 20.0)

    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 20.0)
    assert exc.value.reason == "replay"
    assert len(calls) == 1


def test_amount_over_cap_is_rejected(engine, person_pair, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 20.01)
    assert exc.value.reason == "over_cap"
    assert calls == []


def test_tampered_mandate_breaks_the_signature(engine, person_pair, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])
    engine.approved[mandate["jti"]]["mandate"]["cap"] = 9999.0   # altered after signing

    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 5000.0)
    assert exc.value.reason == "signature_tampered"
    assert calls == []


def test_expired_mandate_is_rejected(engine, person_pair, calls):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0, ttl_s=1)
    approve(engine, person_pair, mandate["jti"])
    time.sleep(2.1)
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 20.0)
    assert exc.value.reason == "expired"
    assert calls == []


@pytest.mark.parametrize("action,recipient", [("refund", "acct-1"), ("pay", "acct-2")])
def test_other_action_or_recipient_is_out_of_scope(engine, person_pair, calls, action, recipient):
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], action, recipient, 20.0)
    assert exc.value.reason == "out_of_scope"
    assert calls == []


def test_failing_executor_still_spends_the_mandate(engine, person_pair):
    def boom(mandate, requested):
        raise RuntimeError("downstream down")

    engine.executor = boom
    mandate = engine.request("assistant", "pay", "acct-1", 20.0)
    approve(engine, person_pair, mandate["jti"])
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", 20.0)
    assert exc.value.reason == "executor_failed"
    with pytest.raises(MandateRejected) as exc2:
        engine.execute(mandate["jti"], "pay", "acct-1", 20.0)
    assert exc2.value.reason == "replay"
    assert engine.view_ledger()["entries"][0]["result"] == "failed"


def test_pairing_code_is_single_use(engine):
    _, new_pub = generate_pair()
    from ask_first import public_key_hex

    code = engine.new_pairing_code()
    assert engine.pair(code, public_key_hex(new_pub)) == public_key_hex(new_pub)
    with pytest.raises(MandateRejected) as exc:
        engine.pair(code, public_key_hex(new_pub))
    assert exc.value.reason == "code_used"


def test_concurrent_execute_of_one_mandate_runs_executor_once(engine, person_pair, calls):
    n_threads = 32
    slow_calls = calls

    def slow(mandate, requested):
        time.sleep(0.01)
        slow_calls.append(mandate["jti"])
        return {}

    engine.executor = slow
    mandate = engine.request("assistant", "pay", "acct-1", 10.0)
    approve(engine, person_pair, mandate["jti"])

    barrier = threading.Barrier(n_threads)
    outcomes: list[str | None] = [None] * n_threads

    def worker(i: int) -> None:
        barrier.wait()
        try:
            outcomes[i] = engine.execute(mandate["jti"], "pay", "acct-1", 10.0)["result"]
        except MandateRejected as e:
            outcomes[i] = e.reason

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("executed") == 1
    assert outcomes.count("replay") == n_threads - 1
    assert len(slow_calls) == 1
    view = engine.view_ledger()
    assert view["verification"]["ok"] is True
    assert [e["result"] for e in view["entries"]].count("executed") == 1
