# Ask First Pay

**Work in progress, private until submission.** Entry for the PayPal AI Hackathon 2026.

A service business takes appointment deposits through PayPal. An AI agent runs the front desk
over chat (WhatsApp, simulated in the demo): it books, creates the PayPal order and holds the
deposit. When money must actually move (capture the deposit after a no-show, refund it after a
cancellation), the agent can only **ask**. The owner approves once on their phone, which signs a
**single-use mandate** scoped to that action, that PayPal resource and that amount, with a cap and
an expiry. Replays, overreach and expired mandates are rejected in plain sight, and every attempt
lands in a hash-chained ledger anyone can verify.

Prior work, declared: the mandate engine is `libs/ask-first-mandate` (Apache-2.0), extracted from
our earlier "Ask First for Alexa+" entry; everything under `src/ask_first_pay/` is new.

## Run the tests

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

How the work is split: `docs/CONTRACT.md`.
