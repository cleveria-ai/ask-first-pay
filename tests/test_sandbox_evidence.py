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
    assert rows(run, "capture_retry") == rows(run, "capture"), "the retry returned another capture"
    assert rows(run, "void")[0].split()[0] == rows(run, "void_authorization")[0].split()[0]
    # the capture, then its retry: PayPal answers 201 to the first and 200 or 201 to the replay
    statuses = re.findall(rf"`POST /v2/payments/authorizations/{auth}/capture` (\d{{3}})", run)
    assert len(statuses) == 2 and statuses[0] == "201" and statuses[1] in ("200", "201"), statuses
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


# ---- the run through the demo's own screens (scripts/sandbox_ui_run.py) ---------------------------
UI_RECORD = ROOT / "docs" / "SANDBOX_UI_RUN.md"
SHOTS = ROOT / "docs" / "screenshots"


def ui_rows() -> list[dict]:
    """The ledger rows of the last sandbox run in docs/SANDBOX_UI_RUN.md."""
    text = UI_RECORD.read_text(encoding="utf-8")
    run = [r for r in re.split(r"^## Run ", text, flags=re.M)[1:] if r.splitlines()[0].endswith("(sandbox)")][-1]
    keys = ("n", "result", "action", "resource", "amount", "answered", "request_id")
    return [dict(zip(keys, (c.strip() for c in line.strip("|").split("|"))))
            for line in run.splitlines() if re.match(r"\| \d+ \|", line)]


def test_the_ui_record_holds_the_three_stories_on_real_paypal_ids():
    got = ui_rows()
    by_action = {a: [r for r in got if r["action"] == a and r["result"] == "executed"]
                 for a in ("capture_deposit", "void_deposit", "refund_deposit")}
    assert len(by_action["capture_deposit"]) == 2 and by_action["void_deposit"] and by_action["refund_deposit"]
    for r in sum(by_action.values(), []):
        assert re.fullmatch(PAYPAL_ID, r["resource"]), r               # not the fake's AUTH-0002
        assert re.search(rf"{PAYPAL_ID} \((COMPLETED|VOIDED)\)", r["answered"]), r
        assert re.fullmatch(r"[0-9a-f]{32}", r["request_id"]), r       # the mandate id sent to PayPal
    replay = [r for r in got if r["result"] == "rejected · replay"]
    assert replay and replay[0]["resource"] == by_action["capture_deposit"][0]["resource"]
    assert not replay[0]["answered"] and not replay[0]["request_id"], "a replay must never reach PayPal"
    # the refund gives back a capture made in this run
    captured = {re.search(PAYPAL_ID, r["answered"]).group() for r in by_action["capture_deposit"]}
    assert by_action["refund_deposit"][0]["resource"] in captured


def test_the_ui_record_carries_no_secret():
    text = UI_RECORD.read_text(encoding="utf-8")
    for needle in ("Bearer", "Authorization:", "access_token", "client_secret", "A21AA"):
        assert needle not in text, needle
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"):
        if os.environ.get(var):
            assert os.environ[var] not in text, var
    for line in re.findall(r"^- `.*$", text, flags=re.M):
        assert re.fullmatch(r"- `(GET|POST) /[A-Za-z0-9/_.-]+` (\d{3}|[A-Za-z]+)", line), line


def test_devpost_cites_the_ui_run_and_its_screenshots_exist():
    devpost = DEVPOST.read_text(encoding="utf-8")
    assert "docs/SANDBOX_UI_RUN.md" in devpost
    for r in ui_rows():
        if r["result"] == "executed":
            pid = re.search(PAYPAL_ID, r["answered"]).group()
            assert pid in devpost, f"docs/DEVPOST.md does not cite {pid} ({r['action']})"
    named = set(re.findall(r"docs/screenshots/(12-sandbox-[a-z-]+\.png)", devpost))
    assert len(named) >= 5
    for name in named:
        png = SHOTS / name
        assert png.exists() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", name
