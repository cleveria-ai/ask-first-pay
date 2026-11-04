# N1: PayPal sandbox adapter

## What I built
- `src/ask_first_pay/paypal/provider.py`: `PayPalProvider` implementing the `PaymentProvider` port with `httpx`. Cached OAuth token (expires_in minus 60 s), `PayPal-Request-Id` on every write, two-decimal string amounts (more decimals raise `INVALID_AMOUNT`, never rounded), `payer-action`/`approve` link, `void` 204 handled, PayPal errors mapped to `ProviderError(code=name)`, timeouts/5xx to transient `TRANSIENT`. Production needs `environment="production", allow_production=True`.
- `tests/paypal/`: 25 offline tests (httpx.MockTransport, fixtures in `fixtures/`), contract test (same story on `FakeProvider` and `PayPalProvider`), one `live` test (skipped by default; manual steps in its docstring).

## Measured
Full suite: 71 passed, 1 deselected (live). Not run against the real sandbox (no credentials here).

## Ladder at start
```
[notice] A new release of pip is available: 24.0 -> 26.3
[notice] To update, run: python3 -m pip install --upgrade pip
PASS  K1   the whole suite is green  | 46 passed in 2.49s
FAIL  K2   the adapter implements every port method  | ModuleNotFoundError: No module named 'ask_first_pay.paypal'
FAIL  K3   at least 8 offline adapter tests, all passing  | 
FAIL  K4   a test inspects the sent request and asserts PayPal-Request-Id equals the request_id on capture, refund and void  | no tests ran in 0.00s
FAIL  K5   a test proves production without the explicit flag raises  | no tests ran in 0.01s
FAIL  K6   a test proves amounts go as two-decimal strings and three decimals are rejected  | no tests ran in 0.01s
FAIL  K7   a test proves a timeout raises a transient error and the retry with the same request_id is sent with the same header  | no tests ran in 0.01s
FAIL  K8   void with a 204 empty body returns VOIDED  | no tests ran in 0.01s
FAIL  K9   the contract test runs both providers  | no tests ran in 0.01s
PASS  K10  no secrets committed  | 
d = 8/10 = 0.80
```

## Ladder at end
```
PASS  K1   the whole suite is green  | 71 passed, 1 deselected in 2.89s
PASS  K2   the adapter implements every port method  | 
FAIL  K3   at least 8 offline adapter tests, all passing  | 
PASS  K4   a test inspects the sent request and asserts PayPal-Request-Id equals the request_id on capture, refund and void  | 4 passed, 22 deselected in 0.06s
PASS  K5   a test proves production without the explicit flag raises  | 1 passed, 25 deselected in 0.29s
PASS  K6   a test proves amounts go as two-decimal strings and three decimals are rejected  | 8 passed, 18 deselected in 0.12s
PASS  K7   a test proves a timeout raises a transient error and the retry with the same request_id is sent with the same header  | 2 passed, 24 deselected in 0.06s
PASS  K8   void with a 204 empty body returns VOIDED  | 3 passed, 23 deselected in 0.07s
PASS  K9   the contract test runs both providers  | 1 passed, 25 deselected in 0.06s
PASS  K10  no secrets committed  | 
d = 1/10 = 0.10
```

## For the coordinator
1. **K3 cannot pass as written.** Its command uses `--collect-only -q` plus a second `-q` (from `pytest -q`), which makes pytest print per-file counts (`tests/paypal/test_paypal_adapter.py: 24`), so `grep -c '::'` returns 0. Proof: `.venv/bin/python -m pytest -q tests/paypal --collect-only -q | head` prints per-file counts. 25 tests exist and all pass (`pytest -q tests/paypal`). Suggested fix: `grep -c '::'` on `pytest tests/paypal --collect-only -q`, or count the `N tests collected` line. I did not touch the work order (not N1's folder).
2. Decision: `capture`/`refund` need the currency, which the port does not carry. The adapter remembers it from `authorize` and otherwise does one GET. No port change needed.
3. `reauthorize` returns `order_id=""` if the authorization was not created by this provider instance (PayPal's response has no order id).
4. Paths from the API summary are unverified against developer.paypal.com (not checked).
