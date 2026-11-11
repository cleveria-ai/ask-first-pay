"""docs/SANDBOX_RUN.md holds a real sandbox run (capture, retry with the same PayPal-Request-Id,
void), carries no secret, and docs/DEVPOST.md cites the same PayPal ids."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "docs" / "SANDBOX_RUN.md"
DEVPOST = ROOT / "docs" / "DEVPOST.md"
PAYPAL_ID = r"[0-9A-Z]{17}"


def rows(text: str, field: str) -> list[str]:
    return re.findall(rf"^\| {re.escape(field)} \| (.+) \|$", text, flags=re.M)


def complete_runs(text: str) -> list[str]:
    """Runs where the capture completed, the retry returned the same capture and the hold was voided."""
    runs = re.split(r"^## Run ", text, flags=re.M)[1:]
    return [r for r in runs
            if re.search(rf"^\| capture \| {PAYPAL_ID} \(COMPLETED\) \|$", r, flags=re.M)
            and "| same_capture_id_on_retry | yes |" in r
            and re.search(r"^\| gate_replay \| refused: ", r, flags=re.M)
            and re.search(rf"^\| void \| {PAYPAL_ID} \(VOIDED\) \|$", r, flags=re.M)]


def test_the_record_holds_a_complete_real_run():
    text = RECORD.read_text(encoding="utf-8")
    runs = complete_runs(text)
    assert runs, "no run with capture COMPLETED, same capture id on retry, gate replay refused and void VOIDED"
    run = runs[-1]
    auth = rows(run, "authorization")[0].split()[0]
    assert run.count(f"`POST /v2/payments/authorizations/{auth}/capture` 201") == 2, "capture and its retry"
    assert re.search(r"`POST /v2/payments/authorizations/[0-9A-Z]{17}/void` 204", run)


def test_the_record_carries_no_secret():
    text = RECORD.read_text(encoding="utf-8")
    for needle in ("Bearer", "Authorization:", "access_token", "client_secret", "A21AA"):
        assert needle not in text, needle
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        value = os.environ.get(var)
        if value:
            assert value not in text, var
    # every HTTP line is method, path and status: no query string, no header, no body
    for line in re.findall(r"^- `.*$", text, flags=re.M):
        assert re.fullmatch(r"- `(GET|POST) /[A-Za-z0-9/_.-]+` (\d{3}|[A-Za-z]+)", line), line


def test_devpost_cites_the_ids_of_the_recorded_run():
    run = complete_runs(RECORD.read_text(encoding="utf-8"))[-1]
    devpost = DEVPOST.read_text(encoding="utf-8")
    assert "docs/SANDBOX_RUN.md" in devpost
    for field in ("capture_order", "capture", "void_order", "void"):
        pid = rows(run, field)[0].split()[0]
        assert re.fullmatch(PAYPAL_ID, pid), (field, pid)
        assert pid in devpost, f"docs/DEVPOST.md does not cite the {field} id {pid}"
