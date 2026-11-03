# Contract between the pieces

Three pieces are built in parallel, each in its own branch and session. They meet only at
`src/ask_first_pay/ports.py` (the `PaymentProvider` port and its dataclasses) and
`src/ask_first_pay/gate.py` (the mandate gate). Neither file changes without a note here and the
coordinator's merge.

| Piece | Branch | Owns (only writes here) | Reads |
|---|---|---|---|
| N1 PayPal sandbox adapter | `n1-paypal-adapter` | `src/ask_first_pay/paypal/`, `tests/paypal/` | ports, gate |
| N2 Agent with PayPal tools behind the gate | `n2-agent` | `src/ask_first_pay/agent/`, `tests/agent/` | ports, gate, fake_provider |
| N3 Demo: chat booking with deposit + owner approval page | `n3-demo` | `src/ask_first_pay/demo/`, `tests/demo/` | ports, gate, fake_provider, agent (through its public function only) |

Shared rules for every piece:

- `.venv/bin/python -m pytest -q` stays green on the whole repository, not only on your folder.
- Never commit a credential, token, `.env` or real personal data. Sandbox credentials come only
  from the environment variables `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`; tests that need
  them are skipped when they are absent.
- Money moves only through `gate.py`. No piece calls `capture`, `refund` or `void` on a provider
  directly, except N1's own adapter tests.
- English in code, UI and docs (the judges read English).
- The demo business is fictional. No real customer, phone number or company data.
- If you need a change to `ports.py` or `gate.py`, write it in `docs/CONTRACT_CHANGES.md` in your
  branch and keep going against the current version; the coordinator merges it.
