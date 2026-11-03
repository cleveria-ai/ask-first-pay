"""An amount is valid only if it is finite and greater than zero."""
import math

import pytest
from conftest import approve

from ask_first import MandateRejected


def _rejects_and_stays_usable(engine, person_pair, calls, amount):
    mandate = engine.request("assistant", "pay", "acct-1", 30.0)
    approve(engine, person_pair, mandate["jti"])
    with pytest.raises(MandateRejected) as exc:
        engine.execute(mandate["jti"], "pay", "acct-1", amount)
    assert exc.value.reason == "over_cap"
    assert "invalid amount" in exc.value.detail

    assert calls == []                                    # the executor was never reached
    assert mandate["jti"] not in engine.used
    row = engine.view_ledger()["entries"][-1]
    assert row["result"] == "rejected" and row["reason"] == "over_cap"
    assert row["detail"] == "invalid amount"

    result = engine.execute(mandate["jti"], "pay", "acct-1", 10.0)
    assert result["result"] == "executed" and len(calls) == 1


def test_negative_amount_is_rejected(engine, person_pair, calls):
    _rejects_and_stays_usable(engine, person_pair, calls, -500)


def test_zero_amount_is_rejected(engine, person_pair, calls):
    _rejects_and_stays_usable(engine, person_pair, calls, 0)


def test_nan_amount_is_rejected(engine, person_pair, calls):
    _rejects_and_stays_usable(engine, person_pair, calls, math.nan)


def test_non_finite_inf_amount_is_rejected(engine, person_pair, calls):
    _rejects_and_stays_usable(engine, person_pair, calls, math.inf)


def test_non_finite_negative_inf_amount_is_rejected(engine, person_pair, calls):
    _rejects_and_stays_usable(engine, person_pair, calls, -math.inf)


def test_request_with_nan_raises_value_error(engine):
    with pytest.raises(ValueError):
        engine.request("assistant", "pay", "acct-1", math.nan)


def test_request_with_non_finite_inf_raises_value_error(engine):
    with pytest.raises(ValueError):
        engine.request("assistant", "pay", "acct-1", math.inf)
