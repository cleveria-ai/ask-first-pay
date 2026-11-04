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
