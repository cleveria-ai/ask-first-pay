import json

from ask_first import Ledger


def test_missing_ledger_is_not_an_intact_chain(tmp_path):
    result = Ledger(tmp_path / "ledger.jsonl").verify()
    assert result["ok"] is False
    assert result["kind"] == "missing"


def _three(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for who, what in (("a", 1), ("b", 2), ("c", 3)):
        last = ledger.append({"who": who, "what": what})
    return ledger, last


def test_append_chains_and_verifies(tmp_path):
    ledger, last = _three(tmp_path)
    assert last["n"] == 3 and last["prev"] != ""
    result = ledger.verify()
    assert result["ok"] is True and result["chained"] == 3


def test_verify_detects_altered_row(tmp_path):
    ledger, _ = _three(tmp_path)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["what"] = 999                       # content altered, hash left as is
    lines[1] = json.dumps(row)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = ledger.verify()
    assert result["ok"] is False and result["kind"] == "altered" and result["broken_at"] == 2


def test_verify_detects_deleted_and_reordered_rows(tmp_path):
    ledger, _ = _three(tmp_path)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()

    ledger.path.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert ledger.verify()["kind"] == "altered"

    ledger.path.write_text("\n".join([lines[1], lines[0], lines[2]]) + "\n", encoding="utf-8")
    assert ledger.verify()["kind"] == "altered"


def test_entries_hide_internal_annotations(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append({"who": "a"})
    entries = ledger.entries()
    assert len(entries) == 1 and "_line" not in entries[0] and entries[0]["n"] == 1
