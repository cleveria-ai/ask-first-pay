# N3 — Demo app: chat booking with a deposit, and the owner's approval page

Branch `n3-demo`. Read `docs/encargos/COMMON.md` first.

## Goal

`src/ask_first_pay/demo/` is a small FastAPI app that a judge can run with one command and use in
under five minutes:

1. **Customer chat** (`/chat`): a WhatsApp-like page. The customer books a slot; the business
   sends a PayPal sandbox approval link for the deposit (with `FakeProvider`, a fake checkout page
   that approves the order).
2. **Owner phone page** (`/owner`): shows pending mandates exactly as signed (action, PayPal
   resource, amount cap, expiry) with Approve / Decline. Approve signs with an Ed25519 key kept in
   the browser (WebCrypto) after pairing with a one-time code, as `ask_first` expects
   (`new_pairing_code`, `pair`, `approve`).
3. **Ledger page** (`/ledger`): every attempt, accepted or rejected, with the chain check.
4. A **scenario button** runs the no-show and the cancellation stories end to end.

Until N2 lands, drive the chat with a stub that calls the same gate; switch to N2's public entry
point when it exists (CONTRACT.md). Provider: `FakeProvider` by default; the N1 adapter when
`PAYPAL_CLIENT_ID` is set.

UI in English, mobile-first, accessible (labels, contrast, large targets). No external CDN at
runtime: vendor anything you need.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the three pages answer 200 | `.venv/bin/python -m pytest -q tests/demo -k pages` |
| K3 | the no-show story captures exactly once, only after approval | `.venv/bin/python -m pytest -q tests/demo -k no_show` |
| K4 | a declined or replayed mandate shows as rejected in the ledger page | `.venv/bin/python -m pytest -q tests/demo -k rejected` |
| K5 | one command starts the demo | `test -x scripts/demo.sh && grep -q uvicorn scripts/demo.sh` |
| K6 | no external CDN at runtime | `test -d src/ask_first_pay/demo && ! grep -rnE "https?://(cdn\|unpkg\|cdnjs)" src/ask_first_pay/demo` |
