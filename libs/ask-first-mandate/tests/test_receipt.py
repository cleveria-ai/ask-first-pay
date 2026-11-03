import json

import pytest
from conftest import approve

from ask_first import Receipt


def _executed(engine, person_pair):
    mandate = engine.request("assistant", "pay", "acct-1", 10.0)
    approve(engine, person_pair, mandate["jti"])
    return mandate, engine.execute(mandate["jti"], "pay", "acct-1", 10.0)


def test_valid_receipt_verifies_alone_and_against_the_known_key(engine, person_pair):
    mandate, result = _executed(engine, person_pair)
    receipt = json.loads(json.dumps(result["receipt"]))     # survives a file round trip

    assert receipt["mandate_id"] == mandate["jti"]
    assert receipt["ledger_row_hash"] == result["row"]["hash"]
    assert Receipt.verify(receipt) == (True, "ok")
    assert Receipt.verify(receipt, engine.server_pub_hex()) == (True, "ok")
    assert Receipt.verify(receipt, "00" * 32) == (False, "server_key_mismatch")


@pytest.mark.parametrize("field,value", [
    ("amount", 999999.0),
    ("recipient", "other-account"),
    ("ledger_row_hash", "not-this-row"),
])
def test_altered_receipt_does_not_verify(engine, person_pair, field, value):
    _, result = _executed(engine, person_pair)
    receipt = dict(result["receipt"])
    receipt[field] = value
    assert Receipt.verify(receipt) == (False, "invalid_signature")
