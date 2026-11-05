"""N6 design pass: color contrast of the tokens, touch targets, the "what just happened" line,
empty states, the AG Grid features the pages rely on, and the raw ledger row behind each hash."""
import json
import re
from pathlib import Path

import pytest
from ask_first import generate_pair, public_key_hex

from .conftest import Demo

DEMO = Path(__file__).resolve().parents[2] / "src" / "ask_first_pay" / "demo"
CSS = (DEMO / "static" / "app.css").read_text(encoding="utf-8")
GRID = (DEMO / "static" / "grid.js").read_text(encoding="utf-8")


# ---- tokens --------------------------------------------------------------------------------
def tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):(#[0-9a-fA-F]{6})", block))


LIGHT = tokens(CSS.split("@media (prefers-color-scheme:dark)", 1)[0])
DARK = {**LIGHT, **tokens(CSS.split("@media (prefers-color-scheme:dark){:root{", 1)[1].split("}}", 1)[0])}


def luminance(hex_: str) -> float:
    def ch(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(hex_[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (text, background) pairs as the stylesheet uses them
PAIRS = [("fg", "bg"), ("fg", "surface"), ("fg", "surface-2"), ("fg", "neutral-bg"), ("fg", "accent-soft"),
         ("muted", "bg"), ("muted", "surface"), ("muted", "surface-2"),
         ("accent-fg", "accent"), ("accent-ink", "surface"), ("accent-ink", "accent-soft"), ("accent-ink", "bg"),
         ("customer-fg", "customer"),
         ("ok", "ok-bg"), ("bad", "bad-bg"), ("warn", "warn-bg"), ("info", "info-bg"), ("neutral", "neutral-bg"),
         ("ok-bg", "ok"), ("bad-bg", "bad"), ("warn-bg", "warn"), ("info-bg", "info"),   # the inverted tags
         ("bad", "surface"), ("ok", "surface"), ("fg", "ok-bg"), ("fg", "bad-bg"), ("fg", "warn-bg")]


@pytest.mark.parametrize("scheme,t", [("light", LIGHT), ("dark", DARK)])
def test_design_tokens_meet_wcag_aa_contrast(scheme, t):
    pairs = PAIRS + ([("accent", "surface"), ("accent", "bg")] if scheme == "dark" else [])
    low = [(f, b, round(contrast(t[f], t[b]), 2)) for f, b in pairs if contrast(t[f], t[b]) < 4.5]
    assert not low, f"{scheme}: below 4.5:1 {low}"


def test_design_touch_targets_are_44px():
    assert "--tap:44px" in CSS
    for sel in (".btn{", ".top nav a{", ".quick button{", ".toolbar .seg button{", "input[type=text],input[type=search]{"):
        rule = CSS.split(sel, 1)[1].split("}", 1)[0]
        assert "min-height:var(--tap)" in rule, sel
    assert "rowHeight: 44" in GRID and "headerHeight: 44" in GRID


def test_design_no_external_urls_in_static_files():
    for f in (DEMO / "static").glob("*.*"):
        assert not re.search(r"https?://", f.read_text(encoding="utf-8")), f.name


# ---- AG Grid ---------------------------------------------------------------------------------
def test_design_ag_grid_is_vendored_with_license():
    vendor = DEMO / "static" / "vendor"
    assert (vendor / "ag-grid-community.min.js").stat().st_size > 100_000
    lic = (vendor / "AG-GRID-LICENSE.txt").read_text(encoding="utf-8")
    assert "MIT License" in lic and "AG GRID LTD" in lic


@pytest.mark.parametrize("feature", ["themeQuartz.withParams", "isExternalFilterPresent", "doesExternalFilterPass",
                                     "quickFilterText", "exportDataAsCsv", "agTextColumnFilter",
                                     "agNumberColumnFilter", "rowSelection", "onSelectionChanged",
                                     "cellRenderer", "ensureDomOrder", "getRowId"])
def test_design_ag_grid_features_used(feature):
    assert feature in GRID


def test_design_ledger_rows_carry_signed_fields_and_chain_link(demo):
    demo.client.post("/scenario/no_show")
    jti = demo.pending_ids()[0]
    demo.approve(jti)
    demo.client.post("/replay")
    page = demo.client.get("/ledger").text
    rows = json.loads(page.split('<script type="application/json" id="ledger-data">', 1)[1].split("</script>", 1)[0])
    newest, first = rows[0], rows[1]
    assert newest["result"] == "rejected" and newest["reason"] == "replay" and newest["tone"] == "bad"
    assert newest["prev"] == first["hash"] and first["prev"] == ""
    assert newest["mandate_id"] == jti and newest["signed"]["action"] == "capture_deposit"
    assert newest["signed"]["recipient"] == newest["resource"] and newest["signed"]["cap"] == 10.0
    assert 'data-filter="result"' in page and 'data-filter="action"' in page and "data-csv" in page
    assert f'href="/ledger/entry/{first["n"]}"' in page            # the hash links to the raw row


def test_design_ledger_entry_endpoint_returns_the_raw_row(demo):
    demo.client.post("/scenario/no_show")
    demo.approve(demo.pending_ids()[0])
    demo.client.post("/replay")
    one, two = demo.client.get("/ledger/entry/1").json(), demo.client.get("/ledger/entry/2").json()
    assert two["entry"]["prev"] == one["entry"]["hash"] and two["prev_url"] == "/ledger/entry/1"
    assert one["prev_url"] is None and one["entry"]["result"] == "executed"
    assert demo.client.get("/ledger/entry/99").status_code == 404


def test_design_mandate_rows_have_state_tone_and_ledger_refs(demo):
    demo.client.post("/scenario/no_show")
    jti = demo.pending_ids()[0]
    rows = demo.client.get("/owner/api/mandates").json()["mandates"]
    assert rows[0]["tone"] == "warn" and rows[0]["ledger"] == []
    demo.approve(jti)
    rows = demo.client.get("/owner/api/mandates").json()["mandates"]
    assert rows[0]["state"] == "used" and rows[0]["tone"] == "ok" and rows[0]["ledger"] == [1]


# ---- "what just happened" -------------------------------------------------------------------
def happened(html: str) -> str:
    return html.split('id="happened"', 1)[1].split("</div>\n</div>", 1)[0]


def test_design_happened_line_before_any_action_and_after_pairing(tmp_path):
    d = Demo(tmp_path)                                # not paired yet
    for path in ("/chat", "/owner", "/ledger"):
        assert "Nothing has happened yet" in happened(d.client.get(path).text)
    assert d.pair().status_code == 200
    line = happened(d.client.get("/owner").text)
    assert "This phone was paired" in line and "only key that can approve" in line


def test_design_happened_line_after_every_action(demo):
    demo.client.post("/chat/send", content="message=book+Mon+16+Nov+09%3A00",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    line = happened(demo.client.get("/chat").text)
    assert "You sent &#34;book Mon 16 Nov 09:00&#34;" in line or 'You sent "book Mon 16 Nov 09:00"' in line
    assert "booked; waiting for the customer to hold the deposit" in line

    order = next(iter(demo.provider.orders))
    demo.client.post(f"/checkout/{order}/approve")
    line = happened(demo.client.get("/chat").text)
    assert "approved the hold" in line and "deposit held on PayPal (authorized, not charged)" in line

    demo.client.post("/scenario/no_show")
    line = happened(demo.client.get("/owner").text)
    assert "Scenario: no-show" in line and "happened warn" in demo.client.get("/owner").text
    assert "asked the owner for capture_deposit" in line and "Nothing moves until the owner approves" in line

    demo.approve(demo.pending_ids()[0])
    line = happened(demo.client.get("/ledger").text)
    assert "The owner approved mandate" in line and "Gate executed capture_deposit" in line
    assert "deposit captured" in line

    demo.client.post("/replay")
    page = demo.client.get("/ledger").text
    assert "happened bad" in page and "Gate rejected capture_deposit" in happened(page) and "replay" in happened(page)


def test_design_happened_line_on_decline_and_refusals(demo):
    demo.client.post("/scenario/cancel")
    jti = demo.pending_ids()[0]
    demo.decline(jti)
    line = happened(demo.client.get("/owner").text)
    assert "declined" in line and "A decline is final" in line and "not_approved" in line
    assert demo.approve(jti).status_code == 400
    assert "was refused: declined" in happened(demo.client.get("/owner").text)
    demo.client.post("/owner/pair", json={"code": "nope", "public_key": public_key_hex(generate_pair()[1])})
    assert "Pairing refused" in happened(demo.client.get("/owner").text)


def test_design_happened_line_when_nothing_to_replay(demo):
    demo.client.post("/replay")
    line = happened(demo.client.get("/ledger").text)
    assert "nothing to replay" in line and "No money moved" in line


# ---- empty and error states ---------------------------------------------------------------------
def test_design_empty_states(demo):
    owner, ledger = demo.client.get("/owner").text, demo.client.get("/ledger").text
    assert "Nothing is waiting." in owner and "No mandates yet." in owner
    assert "The ledger is empty." in ledger and "no attempts recorded yet" in ledger
    assert 'data-grid="ledger"' not in ledger           # no empty grid, an explained empty state


def test_design_pages_load_their_scripts_locally(demo):
    assert '<script src="/static/chat.js">' in demo.client.get("/chat").text
    for path in ("/owner", "/ledger"):
        text = demo.client.get(path).text
        assert '<script src="/static/vendor/ag-grid-community.min.js">' in text and "/static/grid.js" in text
