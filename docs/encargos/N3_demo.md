# N3 — Demo app: chat booking with a deposit, and the owner's approval page

Branch `n3-demo`. Read `docs/encargos/COMMON.md` and `docs/CONTRACT.md` first.

## Goal

`src/ask_first_pay/demo/` is a small FastAPI app (FastAPI, uvicorn and jinja2 are already
dependencies) that a judge can start with one command and understand in under five minutes:

1. **Customer chat** (`/chat`): a WhatsApp-like page. The customer books a slot; the business
   sends a deposit link. With `FakeProvider`, a fake checkout page approves the order.
2. **Owner phone page** (`/owner`): pending mandates shown with `AgentGate.describe` (the signed
   fields: action, PayPal resource, cap, expiry) and Approve / Decline. It gets `OwnerSide`.
   Approving signs with an Ed25519 key kept in the browser (WebCrypto) after pairing with a
   one-time code (`new_pairing_code`, `pair`, `approve`).
3. **Ledger page** (`/ledger`): every attempt, accepted or rejected, and the chain check.
4. **Scenario buttons** run the no-show (capture), cancellation (void) and goodwill (capture
   then refund) stories end to end, as `docs/CONTRACT.md` tells them.

Until N2 lands, drive the chat with a small stub in `src/ask_first_pay/demo/` that uses only
`AgentGate` and `HoldDesk`; switch to `ask_first_pay.agent.run_turn` when it exists. Provider:
`FakeProvider` by default; `ask_first_pay.paypal.PayPalProvider` when `PAYPAL_CLIENT_ID` is set
and that module exists.

UI in English, mobile-first, accessible (labels, contrast, 44 px targets). No external CDN at
runtime.

## Tests

`tests/demo/test_demo_*.py` with FastAPI's `TestClient`. Tests may sign approvals in Python
(`sign_envelope`) instead of a browser.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the three pages answer 200 and show their key content (chat input, a pending-mandate list, the chain check) | `.venv/bin/python -m pytest -q tests/demo -k pages` |
| K3 | the no-show story captures exactly once and only after approval | `.venv/bin/python -m pytest -q tests/demo -k no_show` |
| K4 | the cancellation story voids and never refunds | `.venv/bin/python -m pytest -q tests/demo -k cancel` |
| K5 | a declined or replayed mandate shows as rejected on the ledger page | `.venv/bin/python -m pytest -q tests/demo -k rejected` |
| K6 | the demo never moves money outside the gate | `test -d src/ask_first_pay/demo && ! grep -rnE "\.(capture\|refund\|void)\(" src/ask_first_pay/demo` |
| K7 | one command starts the demo | `test -x scripts/demo.sh && grep -q uvicorn scripts/demo.sh` |
| K8 | no external CDN at runtime | `test -d src/ask_first_pay/demo && ! grep -rnE "https?://(cdn\|unpkg\|cdnjs\|fonts\.googleapis)" src/ask_first_pay/demo` |
