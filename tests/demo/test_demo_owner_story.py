"""N9: the owner's phone tells the story (story V1, grafts G7, G8, G12, judge bugs B7, B12, B15).

Every number on the owner card and in the Today panel must come from the signed mandates, the
bookings and the ledger. These tests change those sources and check the page follows them."""
import html
import re
import time
from datetime import datetime, timezone

import pytest
from ask_first import generate_pair, public_key_hex, sign_envelope

from ask_first_pay import gate as gate_mod
from ask_first_pay.demo import owner_view

from .conftest import Demo

DAYS = r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
CLOCK = DAYS + r" \d{1,2}:\d{2} (a\.m\.|p\.m\.)"


def text_of(fragment: str) -> str:
    """Visible text of an HTML fragment: tags out, entities decoded, spaces collapsed."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def card_html(page: str, jti: str) -> str:
    start = page.rindex("<li", 0, page.index(f'data-id="{jti}"'))   # attributes (signed JSON) are not text
    return page[start:page.index("</li>", start)]


def today_text(page: str) -> str:
    start = page.index('id="today"')
    return text_of(page[start:page.index("</section>", start)])


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("ASK_FIRST_MANDATE_TTL_MIN", "ASK_FIRST_VIDEO", "ASK_FIRST_TZ"):
        monkeypatch.delenv(k, raising=False)


# ---- K3: human, local times on the owner card ---------------------------------------------------
def test_owner_card_human_time_clock_is_local_and_spoken(monkeypatch):
    monkeypatch.setenv("ASK_FIRST_TZ", "America/Mexico_City")          # UTC-6 in November
    monday = datetime(2026, 11, 16, 15, 12, tzinfo=timezone.utc).timestamp()
    assert owner_view.clock(monday) == "Mon 9:12 a.m."
    assert owner_view.clock(monday + 8 * 3600) == "Mon 5:12 p.m."
    assert owner_view.clock(datetime(2026, 11, 16, 6, 5, tzinfo=timezone.utc).timestamp()) == "Mon 12:05 a.m."
    assert owner_view.slot_text("2026-11-16 09:00") == "Mon 16 Nov, 9:00 a.m."


def test_owner_card_human_time_minutes_left_reads_like_a_person():
    now = 1_000_000
    assert gate_mod.minutes_left(now + 3600, now) == "60 min"
    assert gate_mod.minutes_left(now + 3599, now) == "60 min"
    assert gate_mod.minutes_left(now + 58 * 60, now) == "58 min"
    assert gate_mod.minutes_left(now + 95 * 60, now) == "1 h 35 min"
    assert gate_mod.minutes_left(now + 30, now) == "under a minute"
    assert gate_mod.minutes_left(now, now) == "expired"


def test_owner_card_human_time_on_the_page_has_no_epoch_and_no_utc(demo, monkeypatch):
    monkeypatch.setenv("ASK_FIRST_TZ", "America/Mexico_City")
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    m = demo.state.owner.get(jti)
    page = demo.client.get("/owner").text
    card = card_html(page, jti)
    shown = text_of(card)
    assert str(m["exp"]) not in shown and str(m["created"]) not in shown
    assert not re.search(r"\b1\d{9}\b", shown), shown                 # no epoch seconds anywhere on the card
    assert "UTC" not in shown and "unix" not in shown.lower()
    assert "Expires in 60 min" in shown
    tz = owner_view.local_zone()
    exp_local = datetime.fromtimestamp(m["exp"], tz)
    expected = f"{exp_local:%a} {exp_local.hour % 12 or 12}:{exp_local.minute:02d} {'a.m.' if exp_local.hour < 12 else 'p.m.'}"
    assert expected in shown and re.search(CLOCK, shown)
    assert "Appointment Mon 16 Nov, 9:00 a.m." in shown               # the booking that owns the signed hold
    # the all-mandates table (no-JS fallback and the grid data) speaks the same way
    table = text_of(page[page.index('<table class="plain">'):page.index("</table>")])
    assert "UTC" not in table and str(m["exp"]) not in table and "(in 60 min)" in table
    api = demo.client.get("/owner/api/mandates").json()["mandates"][0]
    assert "UTC" not in api["exp_text"] + api["created_text"] and re.fullmatch(CLOCK, api["created_text"])
    assert "unix" not in demo.state.agent.describe(jti) and "expires in 60 min" in demo.state.agent.describe(jti)


# ---- K4: the approval id is the PayPal-Request-Id ---------------------------------------------
def test_owner_card_request_id_is_the_jti_paypal_receives(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    shown = text_of(card_html(demo.client.get("/owner").text, jti))
    assert f"Approval id {jti[:8]} (sent to PayPal as PayPal-Request-Id)" in shown
    assert demo.approve(jti).status_code == 200
    (cap,) = demo.calls("capture")
    assert cap[3] == jti and cap[3][:8] == jti[:8]                     # what PayPal got is what the owner read
    # the ledger detail says so too, with the capture id PayPal returned
    rows, _ = demo.state.ledger_rows()
    (row,) = [r for r in rows if r["result"] == "executed"]
    capture_id = next(iter(demo.provider.captures))
    assert row["request_id"] == jti and row["paypal_id"] == f"PayPal capture id {capture_id} (COMPLETED)"
    demo.client.post("/replay")
    rows, _ = demo.state.ledger_rows()
    (rejected,) = [r for r in rows if r["result"] == "rejected"]
    assert rejected["request_id"] == "" and rejected["paypal_id"] == ""   # a refused attempt never reached PayPal
    used = [m for m in demo.client.get("/owner/api/mandates").json()["mandates"] if m["id"] == jti][0]
    assert used["paypal"] == f"PayPal capture id {capture_id} (COMPLETED)"


def test_owner_card_request_id_and_paypal_ids_for_void_and_refund(demo):
    demo.client.post("/scenario/goodwill")
    (cap,) = demo.pending_ids()
    demo.approve(cap)
    (ref,) = demo.pending_ids()
    demo.approve(ref)
    demo.client.post("/scenario/cancel")
    (void,) = demo.pending_ids()
    demo.approve(void)
    by_id = {r["mandate_id"]: r for r in demo.state.ledger_rows()[0]}
    (refund_call,) = demo.calls("refund")
    (void_call,) = demo.calls("void")
    assert refund_call[3] == by_id[ref]["request_id"] == ref and by_id[ref]["paypal_id"].startswith("PayPal refund id ")
    assert void_call[2] == by_id[void]["request_id"] == void
    assert by_id[void]["paypal_id"] == f"PayPal authorization {void_call[1]} (VOIDED)"
    grid = (owner_view.__file__.rsplit("/", 1)[0] + "/static/grid.js")
    js = open(grid, encoding="utf-8").read()
    assert "'sent to PayPal as', r.request_id ? 'PayPal-Request-Id: ' + r.request_id" in js and "r.paypal_id" in js


def test_owner_card_request_id_survives_a_restart_with_the_store(tmp_path):
    from ask_first_pay.store import SqliteStore
    from ask_first_pay.demo import create_app
    from ask_first_pay.fake_provider import FakeProvider
    from fastapi.testclient import TestClient

    db = str(tmp_path / "shop.sqlite")
    a = Demo.__new__(Demo)
    a.provider = FakeProvider()
    a.app = create_app(a.provider, store=SqliteStore(db, "s"))
    a.state, a.client = a.app.state.demo, TestClient(a.app, follow_redirects=False)
    a.priv, a.pub = generate_pair()
    a.pair()
    a.client.post("/scenario/no_show")
    (jti,) = a.pending_ids()
    a.approve(jti)
    before = a.state.paypal_results[jti]
    b = create_app(a.provider, store=SqliteStore(db, "s")).state.demo
    assert b.paypal_results[jti] == before
    assert owner_view.today(b)["unsigned"] == "$0.00" and owner_view.today(b)["clean"]


# ---- K5: the void card --------------------------------------------------------------------------
def test_void_card_moves_zero_and_releases_the_held_amount(demo):
    demo.client.post("/scenario/cancel")
    (jti,) = demo.pending_ids()
    page = demo.client.get("/owner").text
    card = card_html(page, jti)
    headline = text_of(re.search(r'<p class="headline">(.*?)</p>', card).group(1))
    assert headline == "Moves $0.00 · releases the $10.00 hold"
    assert "0.01" not in headline and "Irreversible" not in text_of(card)
    details = text_of(card[card.index("<details"):])
    assert "USD 0.01 (symbolic" in details                               # the symbolic cap lives in the details
    # the held amount is read from the booking that owns the signed authorization, not a constant
    (_, booking) = demo.state._booking_with("authorization_id", demo.state.owner.get(jti)["recipient"])
    booking["deposit"] = 25.0
    card = card_html(demo.client.get("/owner").text, jti)
    assert "Moves $0.00 · releases the $25.00 hold" in text_of(card)


def test_void_card_moves_zero_while_capture_and_refund_are_irreversible(demo):
    demo.client.post("/scenario/goodwill")
    (cap,) = demo.pending_ids()
    cap_card = text_of(card_html(demo.client.get("/owner").text, cap))
    assert "Irreversible · needs your signature" in cap_card and "Keep up to $10.00 of the held deposit" in cap_card
    demo.approve(cap)
    (ref,) = demo.pending_ids()
    ref_card = text_of(card_html(demo.client.get("/owner").text, ref))
    assert "Irreversible · needs your signature" in ref_card and "Give back up to $4.00 of the captured deposit" in ref_card
    assert "Moves $0.00" not in ref_card


# ---- K6: mandate lifetime --------------------------------------------------------------------------
def test_mandate_ttl_default_is_60_minutes(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    m = demo.state.owner.get(jti)
    assert m["exp"] - m["created"] == 60 * 60
    assert gate_mod.mandate_ttl_s() == 3600


def test_mandate_ttl_follows_the_environment_and_the_card_shows_it(demo, monkeypatch):
    monkeypatch.setenv("ASK_FIRST_MANDATE_TTL_MIN", "5")
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    m = demo.state.owner.get(jti)
    assert m["exp"] - m["created"] == 5 * 60
    assert "Expires in 5 min" in text_of(card_html(demo.client.get("/owner").text, jti))
    monkeypatch.setenv("ASK_FIRST_MANDATE_TTL_MIN", "180")
    m2 = demo.state.agent.request("capture_deposit", m["recipient"], 10.0)
    assert m2["exp"] - m2["created"] == 180 * 60
    assert "Expires in 3 h 0 min" in text_of(card_html(demo.client.get("/owner").text, m2["jti"]))


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.5", "100000"])
def test_mandate_ttl_rejects_bad_values(monkeypatch, bad):
    monkeypatch.setenv("ASK_FIRST_MANDATE_TTL_MIN", bad)
    with pytest.raises(ValueError):
        gate_mod.mandate_ttl_s()


def test_mandate_ttl_an_expired_request_offers_no_approve(demo):
    demo.client.post("/scenario/no_show")
    (jti,) = demo.pending_ids()
    demo.state.engine.pending[jti]["exp"] = int(time.time()) - 1        # its hour is over
    page = demo.client.get("/owner").text
    assert f'data-id="{jti}"' not in page                               # no card, no Approve button
    (row,) = demo.client.get("/owner/api/mandates").json()["mandates"]
    assert row["state"] == "expired" and "expired" in row["exp_text"]


# ---- K7: the Today panel ---------------------------------------------------------------------------
def play_the_day(demo):
    """No-show approved, a replay refused, goodwill (capture + refund) approved, a cancellation
    approved, and one request declined."""
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    demo.client.post("/replay")
    demo.client.post("/scenario/goodwill")
    (j,) = demo.pending_ids(); demo.approve(j)
    (j,) = demo.pending_ids(); demo.approve(j)
    demo.client.post("/scenario/cancel")
    (j,) = demo.pending_ids(); demo.approve(j)
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.decline(j)


def test_today_panel_is_computed_from_the_ledger_and_bookings(demo):
    play_the_day(demo)
    t = demo.state.today()
    entries = demo.state.agent.view_ledger()["entries"]
    executed = [e for e in entries if e["result"] == "executed"]
    # independent oracles: the provider's own call log and the raw ledger rows
    assert t["kept"] == f"${sum(c[2] for c in demo.calls('capture')):.2f}" == "$20.00"
    assert t["given_back"] == f"${sum(c[2] for c in demo.calls('refund')):.2f}" == "$4.00"
    assert t["released"] == "$10.00" and len(demo.calls("void")) == 1
    assert t["refused"] == sum(1 for e in entries if e["result"] == "rejected") == 2   # the replay + the declined try
    assert "replay 1" in t["refused_reasons"] and "not approved 1" in t["refused_reasons"]
    free = [c for c in demo.provider.calls if c[0] in ("create_order", "authorize", "reauthorize")]
    assert t["agent_calls"] == len(free) and t["orders"] == len(demo.calls("create_order"))
    assert t["holds"] == len(demo.calls("authorize")) and t["reauthorizations"] == len(demo.calls("reauthorize"))
    assert t["approvals"] == len(executed) == 4 and t["declines"] == 1 and t["taps"] == 5
    assert t["unsigned"] == "$0.00" and t["unsigned_rows"] == 0 and t["clean"]
    shown = today_text(demo.client.get("/owner").text)
    assert "$0.00 moved without your signature" in shown
    assert f"{t['agent_calls']} PayPal calls · $0.00 moved" in shown and "5 taps" in shown
    assert "4 approved · 1 declined" in shown and "Kept $20.00" in shown and "Given back $4.00" in shown
    assert "Released $10.00" in shown and "Refused 2" in shown
    assert f"Checked against all {len(entries)} ledger rows; chain intact." in shown


def test_today_panel_shows_an_unsigned_money_movement_injected_into_the_ledger(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    assert "$0.00 moved without your signature" in today_text(demo.client.get("/owner").text)
    auth = demo.state.owner.get(j)["recipient"]
    # money that moved with no owner signature behind it (a bug, a script, someone with file access)
    demo.state.engine.ledger.append({"ts": int(time.time()), "mandate_id": "no-such-approval", "result": "executed",
                                     "reason": None, "action": "refund_deposit", "recipient": auth, "amount": 7.0})
    page = demo.client.get("/owner").text
    shown = today_text(page)
    assert "$7.00 moved without your signature" in shown and "$0.00 moved without" not in shown
    assert "1 executed row has no valid signature of yours" in shown
    assert 'class="unsigned bad"' in page


def test_today_panel_catches_an_approval_whose_signature_no_longer_matches(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    assert demo.state.today()["unsigned"] == "$0.00"
    demo.state.engine.approved[j]["signature"] = sign_envelope(generate_pair()[0], demo.state.engine.approved[j]["mandate"])
    t = demo.state.today()
    assert t["unsigned"] == "$10.00" and t["unsigned_rows"] == 1 and not t["clean"]


def test_today_panel_counts_an_unsigned_void_even_though_it_moves_no_money(demo):
    demo.client.post("/scenario/cancel")
    (j,) = demo.pending_ids()
    auth = demo.state.owner.get(j)["recipient"]
    demo.state.engine.ledger.append({"ts": int(time.time()), "mandate_id": j, "result": "executed", "reason": None,
                                     "action": "void_deposit", "recipient": auth, "amount": 0.01})   # never approved
    t = demo.state.today()
    assert t["unsigned"] == "$0.00" and t["unsigned_rows"] == 1 and not t["clean"]


def test_today_panel_keeps_old_approvals_signed_after_pairing_a_new_phone(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    new_priv, new_pub = generate_pair()
    code = demo.state.new_pairing_code()
    assert demo.client.post("/owner/pair", json={"code": code, "public_key": public_key_hex(new_pub)}).status_code == 200
    t = demo.state.today()
    assert t["unsigned"] == "$0.00" and t["clean"]


def test_today_panel_on_an_empty_day(demo):
    shown = today_text(demo.client.get("/owner").text)
    assert "$0.00 moved without your signature" in shown and "Nothing has moved yet" in shown
    assert "0 PayPal calls" in shown and "0 taps" in shown


def test_today_panel_distrusts_a_broken_chain(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    path = demo.state.engine.ledger.path
    lines = open(path, encoding="utf-8").read().splitlines()
    open(path, "w", encoding="utf-8").write("\n".join(lines[:-1]) + ("\n" if lines[:-1] else ""))   # cut the last row
    page = demo.client.get("/owner").text
    assert "The ledger chain is BROKEN" in today_text(page) and 'class="unsigned bad"' in page


# ---- K8: video-safe labels ------------------------------------------------------------------------
BRANDS = ("AG Grid", "Claude", "Anthropic", "WhatsApp", "Chrome", "Safari", "Firefox", "Booksy", "Square")


def pages(demo):
    demo.client.post("/chat/send", data={"message": "book Tue 15:00"})
    out = {p: demo.client.get(p).text for p in ("/", "/chat", "/owner", "/ledger", "/checkout/ORDER-0001")}
    return {p: text_of(t) for p, t in out.items()}


def test_video_safe_off_changes_nothing(demo):
    demo.state.front.model_name = "Claude"                              # as with an ANTHROPIC_API_KEY
    shown = pages(demo)
    assert "Agent model: Claude" in shown["/chat"]
    assert "AG Grid Community" in shown["/owner"] and "AG Grid Community" in shown["/ledger"]


@pytest.mark.parametrize("model,label", [("Claude", "Agent model: live LLM, tool use"),
                                         ("offline scripted model", "Agent model: offline scripted model")])
def test_video_safe_on_shows_no_third_party_brand_but_paypal(demo, monkeypatch, model, label):
    monkeypatch.setenv("ASK_FIRST_VIDEO", "1")
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    demo.state.front.model_name = model
    shown = pages(demo)
    assert label in shown["/chat"]
    for path, text in shown.items():
        for brand in BRANDS:
            assert brand not in text, (path, brand)
    assert "PayPal" in shown["/chat"] and "PayPal" in shown["/owner"]
    assert "Tap a row for its signed fields" in shown["/owner"]          # the help stays, only the brand goes


# ---- review fixes (codex, after the N8 merge) -----------------------------------------------------
TWO_DAYS = 2 * 24 * 3600


def test_today_panel_counts_only_the_shops_local_day(demo, monkeypatch):
    monkeypatch.setenv("ASK_FIRST_TZ", "America/Mexico_City")
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    m = demo.state.engine.approved[j]["mandate"]
    old = int(time.time()) - TWO_DAYS
    # a signed capture and a refusal from two days ago are on the ledger, but not in Today
    demo.state.engine.ledger.append({"ts": old, "mandate_id": j, "result": "executed", "reason": None,
                                     "action": "capture_deposit", "recipient": m["recipient"], "amount": 10.0})
    demo.state.engine.ledger.append({"ts": old, "mandate_id": j, "result": "rejected", "reason": "replay"})
    t = demo.state.today()
    assert t["kept"] == "$10.00" and t["refused"] == 0 and t["unsigned"] == "$0.00" and t["clean"]
    assert t["bookings"] == 1 and t["orders"] == 1 and t["holds"] == 1
    # a booking made two days ago leaves Today, with the PayPal calls the agent made for it
    (booking,) = [b for s in demo.state.front.conversations for b in s.bookings.values()]
    booking["created_at"] = datetime.fromtimestamp(old, timezone.utc).isoformat()
    t = demo.state.today()
    assert (t["bookings"], t["orders"], t["holds"], t["reauthorizations"], t["agent_calls"]) == (0, 0, 0, 0, 0)
    # tomorrow nothing of this is "today"
    tomorrow = owner_view.today(demo.state, now=time.time() + TWO_DAYS)
    assert (tomorrow["kept"], tomorrow["approvals"], tomorrow["taps"]) == ("$0.00", 0, 0)
    assert "Today " + t["day"] in today_text(demo.client.get("/owner").text)


def test_today_panel_counts_an_undated_booking_and_says_so(demo):
    demo.client.post("/scenario/no_show")
    (booking,) = [b for s in demo.state.front.conversations for b in s.bookings.values()]
    assert booking["created_at"]                                         # book_slot writes it
    del booking["created_at"]                                            # as saved before N9
    t = demo.state.today()
    assert t["bookings"] == 1 and t["undated_bookings"] == 1
    assert "Includes 1 booking with no recorded date." in today_text(demo.client.get("/owner").text)


def test_today_panel_an_unknown_action_counts_its_whole_amount_as_unsigned(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    m = demo.state.engine.approved[j]["mandate"]
    demo.state.engine.ledger.append({"ts": int(time.time()), "mandate_id": j, "result": "executed", "reason": None,
                                     "action": "sweep_deposit", "recipient": m["recipient"], "amount": 5.0})
    t = demo.state.today()
    assert t["unsigned"] == "$5.00" and t["unsigned_rows"] == 1 and not t["clean"]


def test_today_panel_an_approval_filed_under_another_mandate_id_is_unsigned(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    approval = demo.state.engine.approved[j]
    demo.state.engine.approved["someone-elses-id"] = dict(approval)      # a valid signature, wrong jti
    demo.state.engine.ledger.append({"ts": int(time.time()), "mandate_id": "someone-elses-id", "result": "executed",
                                     "reason": None, "action": "capture_deposit",
                                     "recipient": approval["mandate"]["recipient"], "amount": 10.0})
    t = demo.state.today()
    assert t["unsigned"] == "$10.00" and t["unsigned_rows"] == 1


def test_today_panel_unsigned_money_from_an_earlier_day_still_shows(demo):
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids(); demo.approve(j)
    auth = demo.state.owner.get(j)["recipient"]
    demo.state.engine.ledger.append({"ts": int(time.time()) - TWO_DAYS, "mandate_id": "x", "result": "executed",
                                     "reason": None, "action": "refund_deposit", "recipient": auth, "amount": 3.0})
    page = demo.client.get("/owner").text
    shown = today_text(page)
    assert "$0.00 moved without your signature" in shown                 # today itself is clean
    assert "And before today: $3.00 moved without your signature (1 row)." in shown
    assert 'class="unsigned bad"' in page


def test_owner_buzz_poll_endpoint_returns_two_counters_and_no_mandate_bytes(demo):
    assert demo.client.get("/owner/api/pending").json() == {"waiting": 0, "asked": 0}
    demo.client.post("/scenario/no_show")
    (j,) = demo.pending_ids()
    m = demo.state.owner.get(j)
    r = demo.client.get("/owner/api/pending")
    assert r.json() == {"waiting": 1, "asked": 1} and r.headers["cache-control"] == "no-store"
    for secret in (j, j[:8], m["recipient"], "AUTH-", "10.00", "10.0", "capture", "plan_hash", m["plan_hash"]):
        assert secret not in r.text, secret
    demo.approve(j)
    assert demo.client.get("/owner/api/pending").json() == {"waiting": 0, "asked": 1}
    demo.client.post("/scenario/cancel")
    (k,) = demo.pending_ids(); demo.decline(k)
    assert demo.client.get("/owner/api/pending").json() == {"waiting": 0, "asked": 2}
    # the page polls the minimal endpoint, never the full mandate list
    page = demo.client.get("/owner").text
    assert 'data-poll="/owner/api/pending" data-asked="2"' in page
    js = open(owner_view.__file__.rsplit("/", 1)[0] + "/static/owner.js", encoding="utf-8").read()
    assert "/owner/api/mandates" not in js and "j.asked" in js and "j.mandates" not in js


def test_owner_card_human_time_with_an_unknown_zone_says_utc(demo, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("ASK_FIRST_TZ", "Mars/Olympus_Mons")
    tz, note = owner_view.zone_status()
    assert tz is timezone.utc and note == "Times in UTC: ASK_FIRST_TZ='Mars/Olympus_Mons' is not a known time zone."
    monday = datetime(2026, 11, 16, 15, 12, tzinfo=timezone.utc).timestamp()
    assert owner_view.clock(monday) == "Mon 3:12 p.m."                  # UTC, not the server's zone
    demo.client.post("/scenario/no_show")
    page = demo.client.get("/owner").text
    assert note in text_of(page[page.index('id="zone-note"') - 40:page.index("</p>", page.index('id="zone-note"'))])
    (tmp_path / "second").mkdir()
    Demo(tmp_path / "second")                                            # create_app warns at startup
    assert note in capsys.readouterr().out
    monkeypatch.setenv("ASK_FIRST_TZ", "America/Mexico_City")
    assert owner_view.zone_status()[1] == "" and 'id="zone-note"' not in demo.client.get("/owner").text
