# Contract changes requested

## N2 (n2-agent): make `ask_first` importable outside pytest
`pip install -e '.[dev]'` installs only `src/`; `libs/ask-first-mandate/src` is on the path only
through pytest's `pythonpath`. Plain `python -c "from ask_first_pay.agent import run_turn"`
(criterion K7) and the demo scripts therefore fail with `No module named 'ask_first'`.
N2 works around it with a path fallback in `agent/__init__.py`. Suggested real fix for the
coordinator: install the library too (`pip install -e libs/ask-first-mandate` in the setup
commands, or a `[tool.setuptools]` package-dir entry in `pyproject.toml`).

## N3 (n3-demo): demo packaging

- `pyproject.toml`: no new dependency needed (the chat form is parsed by hand, so `python-multipart`
  is not required). If the package is ever installed non-editable, add package data for
  `ask_first_pay/demo/templates/*` and `ask_first_pay/demo/static/**`.
- `scripts/demo.sh` sets `PYTHONPATH=libs/ask-first-mandate/src` because `ask_first` is not installed by
  `pip install -e .` (pytest gets it from `pythonpath`). Consider declaring it in `pyproject.toml`.

## N5 (n5-judge): changes to the contract files

- `gate.py`: `make_executor` retries a **transient** `ProviderError` (timeout, 5xx) up to
  `TRANSIENT_RETRIES = 2` times with the **same** `request_id` (the mandate's `jti`). Before, a
  timeout after PayPal had already captured left the mandate spent and the ledger saying
  `failed` while the money had moved. Non-transient errors are not retried. Signatures and the
  port are unchanged. Test: `tests/test_skeleton.py -k transient`.
- `pyproject.toml`: `pip install -e .` now installs `ask_first` (from `libs/ask-first-mandate/src`)
  next to `ask_first_pay`, plus the demo's templates and static files as package data, so plain
  `python -c "import ask_first"` works and `scripts/demo.sh` no longer needs `PYTHONPATH`. No new
  dependency.

## N9 (n9-owner-story): changes to the contract files

- `gate.py`: `AgentGate.request(ttl_s=None)` now reads the mandate lifetime from
  `ASK_FIRST_MANDATE_TTL_MIN` (whole minutes, 1-1440, default **60**; a bad value raises
  `ValueError` instead of being replaced silently). Before, every request lived 15 minutes
  (judge bug B12). Passing `ttl_s` explicitly still wins, so callers and the engine are unchanged.
- `gate.py`: `AgentGate.describe` no longer prints the expiry as epoch seconds; it says
  "expires in 58 min" (judge bug B7). New helpers `mandate_ttl_s()` and `minutes_left(exp)`.
  The text still comes only from the signed fields. Tests: `tests/demo/test_demo_owner_story.py
  -k "mandate_ttl or human_time"`.
- `pyproject.toml`: a new optional extra `browser = ["playwright>=1.40"]` for the two browser
  tests (`-k "approve_above_fold or buzzes"`) and `scripts/screenshots.py`. Not part of `dev`:
  without Playwright (or its Chromium) those tests skip, so a judge's plain `pytest` stays green.

## N8 (n8-live-ready): create-order idempotency key in the port

- `ports.py`: `PaymentProvider.create_order(amount, currency, reference, request_id=None)`.
  `request_id` is the order's own `PayPal-Request-Id`: the caller chooses it once per order and
  sends the same one when it retries that creation. `None` means a fresh uuid4. It is never
  derived from `reference` (B1: `booking-N` repeats across conversations and restarts, and PayPal
  would hand the second customer the first one's order). Positional callers are unchanged.
- `gate.py`: only `HoldDesk.create_order` changes, to pass `request_id` through. Nothing in
  `AgentGate.describe` or the mandate path is touched (that text belongs to N9).
- `FakeProvider`: `create_order` honours the same idempotency (B4); a capture after the 3-day
  honor period is accepted until day 29, as on PayPal (B5).
