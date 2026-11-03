"""Tail truncation is only visible against a head kept outside the ledger file."""
from ask_first import Ledger


def _ledger(tmp_path, rows=5):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for i in range(rows):
        last = ledger.append({"who": f"m{i}"})
    return ledger, {"n": last["n"], "hash": last["hash"]}


def _cut(ledger, keep):
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    ledger.path.write_text("".join(f"{x}\n" for x in lines[:keep]), encoding="utf-8")


def test_trunc_intact_ledger_matches_expected_head(tmp_path):
    ledger, head = _ledger(tmp_path)
    assert ledger.verify(expected_head=head)["ok"] is True


def test_trunc_without_the_last_row(tmp_path):
    ledger, head = _ledger(tmp_path)
    _cut(ledger, 4)
    result = ledger.verify(expected_head=head)
    assert result["ok"] is False and result["kind"] == "truncated"


def test_trunc_without_the_last_three_rows(tmp_path):
    ledger, head = _ledger(tmp_path)
    _cut(ledger, 2)
    assert ledger.verify(expected_head=head)["kind"] == "truncated"


def test_trunc_empty_file(tmp_path):
    ledger, head = _ledger(tmp_path)
    ledger.path.write_text("", encoding="utf-8")
    assert ledger.verify(expected_head=head)["kind"] == "truncated"


def test_trunc_then_append_then_verify(tmp_path):
    ledger, head = _ledger(tmp_path)
    _cut(ledger, 3)
    ledger.append({"who": "after"})
    result = ledger.verify(expected_head=head)
    assert result["ok"] is False and result["kind"] == "truncated"


def test_trunc_without_expected_head_behaviour_is_unchanged(tmp_path):
    ledger, _ = _ledger(tmp_path)
    _cut(ledger, 3)
    result = ledger.verify()
    assert result["ok"] is True and result["chained"] == 3
