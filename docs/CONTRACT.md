# Contract between the pieces

Three pieces are built in parallel, each in its own branch and session. They meet only at
`src/ask_first_pay/ports.py` (the `PaymentProvider` port and its dataclasses) and
`src/ask_first_pay/gate.py` (the mandate gate). Neither file, nor `pyproject.toml`, changes
without a note in `docs/CONTRACT_CHANGES.md` and the coordinator's merge.

| Piece | Branch | Owns (only writes here) | Reads |
|---|---|---|---|
| N1 PayPal sandbox adapter | `n1-paypal-adapter` | `src/ask_first_pay/paypal/`, `tests/paypal/` | ports, gate |
| N2 Agent with PayPal tools behind the gate | `n2-agent` | `src/ask_first_pay/agent/`, `tests/agent/` | ports, gate (`AgentGate` only), fake_provider |
| N3 Demo: chat booking with deposit + owner approval page | `n3-demo` | `src/ask_first_pay/demo/`, `scripts/demo.sh`, `tests/demo/` | ports, gate, fake_provider, agent (through `ask_first_pay.agent.run_turn` once it exists) |

## The stories (all pieces tell them the same way)

| Story | PayPal calls | Mandates the owner approves |
|---|---|---|
| Booking | create order (intent AUTHORIZE), payer approves, authorize | none: money is only held |
| No-show | capture (inside the 3-day honor period; after it, reauthorize first; the hold expires at 29 days) | one `capture_deposit` |
| Cancellation | void the authorization | one `void_deposit` (symbolic 0.01) |
| Goodwill after a no-show | capture, then refund part of it | `capture_deposit`, then `refund_deposit` |

## Rules for every piece

- `.venv/bin/python -m pytest -q` stays green on the whole repository, not only your folder.
- Test files are named with your prefix (`test_paypal_*.py`, `test_agent_*.py`, `test_demo_*.py`)
  inside your test package, so the merged suite has no name clashes.
- Money moves only through `gate.py`. The agent receives an `AgentGate` (request, execute,
  describe, view_ledger) and never the engine, the provider or `OwnerSide`. The owner page
  receives `OwnerSide`. Only N1's own adapter tests call capture, refund or void directly.
- Every capture, refund and void carries `request_id`; the gate passes the mandate's `jti`.
- What the owner reads about a mandate comes from `AgentGate.describe` (signed fields), never
  from model text.
- Never commit a credential, token, `.env` or real personal data. Sandbox credentials come only
  from `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`; tests that need them are marked `live` and
  are skipped by default.
- English in code, UI and docs (the judges read English). The demo business is fictional.
- If you need a change to `ports.py`, `gate.py` or `pyproject.toml`, write it in
  `docs/CONTRACT_CHANGES.md` in your branch and keep going against the current version.
