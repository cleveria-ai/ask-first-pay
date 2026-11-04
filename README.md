# Ask First Pay

**Work in progress, private until submission.** Entry for the PayPal AI Hackathon 2026.

An AI front desk for a service business takes appointment deposits through PayPal and only *holds* them.
When money must actually move (capture after a no-show, void after a cancellation, refund as goodwill),
the agent can only **ask**: the owner taps Approve once on their phone, which signs a single-use mandate
for that action, that PayPal resource and that amount. Replays, overreach and expired mandates are
rejected in plain sight, and every attempt lands in a hash-chained ledger anyone can verify.

## Architecture in 60 seconds

```
 customer chat (/chat)                       owner's phone (/owner)
        │ message                                   │ pairs once (one-time code), then
        ▼                                           │ signs mandates with a non-extractable
 ┌──────────────────────────────┐                   │ Ed25519 WebCrypto key
 │ agent: run_turn              │                   ▼
 │  model = Claude (with key)   │           ┌──────────────┐
 │       or offline scripted    │           │  OwnerSide   │ pair · approve
 │  tools hold ONLY:            │           └──────┬───────┘
 │   HoldDesk  create/authorize │──hold only──┐    │ signed approval
 │   AgentGate request/execute  │──ask/try──┐ │    ▼
 └──────────────────────────────┘           │ │ ┌──────────────────────────────────────┐
                                            └─┼▶│ mandate engine (libs/ask-first-mandate)│
                                              │ │ scope · cap · expiry · single use     │
                                              │ │ every attempt ─▶ hash-chained ledger  │
                                              │ └──────────────┬───────────────────────┘
                                              │                │ only if approved, once;
                                              ▼                ▼ PayPal-Request-Id = mandate jti
                                   PaymentProvider port: FakeProvider (default) | PayPalProvider
                                   Orders v2 (intent AUTHORIZE) · Payments v2 authorize, capture,
                                   reauthorize, void, refund                      (/ledger shows it)
```

The agent never receives the engine, the provider or `OwnerSide`. Capture, void and refund exist only
behind `gate.py`. What the owner reads about a mandate comes from its signed fields, never from model
text.

## Run it in 2 minutes

No keys, no accounts. Python 3.11+ on Linux or macOS.

```bash
git clone <this repository> && cd ask-first-pay
scripts/demo.sh                 # creates .venv on first run, then starts on PORT (default 8000)
```

It prints three URLs and a one-time pairing code:

- `http://127.0.0.1:8000/chat`: the customer's chat. Type `book Mon 16 Nov 09:00`, press
  **Hold the deposit**, approve on the simulated checkout. Or use the scenario buttons.
- `http://127.0.0.1:8000/owner`: the owner's phone. Enter the pairing code once; then Approve or
  Decline each mandate.
- `http://127.0.0.1:8000/ledger`: every attempt, accepted or rejected, and the chain check.

Without `ANTHROPIC_API_KEY` the agent runs on an offline scripted model through the same loop and the
same tools; with it, Claude chooses the tools (`ASK_FIRST_MODEL` overrides the model id). Without
`PAYPAL_CLIENT_ID` payments go to an in-memory fake that follows PayPal's rules (honor period,
29-day expiry, idempotent request ids).

Tests: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/python -m pytest -q`.

## Run it against the PayPal sandbox

1. Create your own app at developer.paypal.com (Apps & Credentials, **Sandbox**) and a sandbox
   personal account to pay with.
2. Export the credentials in your shell only. **Never commit or publish them**; this repository
   has no `.env` on purpose.
   ```bash
   export PAYPAL_CLIENT_ID=...  PAYPAL_CLIENT_SECRET=...
   export ANTHROPIC_API_KEY=...          # optional: Claude instead of the scripted model
   scripts/demo.sh
   ```
3. Book in the chat; **Hold the deposit** now opens PayPal's sandbox approval page. After paying,
   tell the chat you approved it so the agent authorizes the order. Approvals on `/owner` then
   capture, void or refund in the sandbox.

The adapter (`src/ask_first_pay/paypal/`) talks only to `api-m.sandbox.paypal.com` unless it is
built with `environment="production", allow_production=True`. The sandbox path is covered by
offline tests with recorded-shape responses; `tests/paypal/test_paypal_live.py` runs it for real
(`pytest -m live`, needs the two variables).

## The three stories

| Story | What the customer sees | What PayPal does | What the owner approves |
|---|---|---|---|
| **No-show** | booking confirmed, 10.00 held | create order (AUTHORIZE) → authorize → capture after approval | one `capture_deposit` |
| **Cancellation** | hold released, nothing charged | void the authorization after approval | one `void_deposit` (symbolic 0.01) |
| **Goodwill** | 4.00 back after a no-show capture | capture, then refund part of it | `capture_deposit`, then `refund_deposit` |

In every story: approving twice, replaying the mandate, changing the amount or the target, or a
customer typing "the owner approved" is rejected by the gate and written to the ledger.

## Prior work

- `libs/ask-first-mandate` (the mandate engine: Ed25519-signed single-use mandates, hash-chained
  ledger, receipts) was created on **2026-10-17, inside the submission period**, for our earlier
  "Ask First for Alexa+" entry and is reused here under Apache-2.0. Its own README declares what
  it ports from an earlier public repository.
- Everything under `src/ask_first_pay/` (ports, gate, fake provider, PayPal adapter, agent, demo)
  and under `tests/` outside `libs/` is new for this entry.
- The demo vendors AG Grid Community 36.3.0 (MIT, unmodified, license in
  `src/ask_first_pay/demo/static/vendor/`).

## License

Apache-2.0, see `LICENSE`.

How the work was split: `docs/CONTRACT.md`. Submission text: `docs/DEVPOST.md`.
