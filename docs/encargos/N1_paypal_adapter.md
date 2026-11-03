# N1 — PayPal sandbox adapter

Branch `n1-paypal-adapter`. Read `docs/encargos/COMMON.md` first.

## Goal

`src/ask_first_pay/paypal/` implements the `PaymentProvider` port (`src/ask_first_pay/ports.py`)
against the **PayPal REST API v2 in the sandbox** (`https://api-m.sandbox.paypal.com`):

- OAuth2 client-credentials token, cached until expiry;
- `create_order` = `POST /v2/checkout/orders` with `intent: AUTHORIZE`, one purchase unit whose
  `reference_id` is our booking id, returning the payer `approve` link;
- `authorize` = `POST /v2/checkout/orders/{id}/authorize`;
- `capture` = `POST /v2/payments/authorizations/{id}/capture` (partial amounts allowed);
- `refund` = `POST /v2/payments/captures/{id}/refund` (partial amounts allowed);
- `void` = `POST /v2/payments/authorizations/{id}/void`;
- every write sends a `PayPal-Request-Id` idempotency header derived from our inputs, so a retry
  never moves money twice;
- PayPal errors become `ProviderError(code=<PayPal error name>)`.

Use `httpx`. Credentials only from `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`. Read PayPal's
official docs for request and response shapes; do not guess field names.

## Tests

- `tests/paypal/` runs **offline** by default with `httpx.MockTransport` and response bodies that
  follow PayPal's documented examples (keep them in `tests/paypal/fixtures/`).
- One live test, `tests/paypal/test_live_sandbox.py`, marked `live`, skipped unless both env vars
  exist: create order, then stop (approval needs a browser; document the manual step).
- A contract test runs the same scenario on `FakeProvider` and on the adapter with the mock
  transport and asserts the same sequence of statuses.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the adapter exists and implements every port method | `.venv/bin/python -c "from ask_first_pay.paypal import PayPalProvider as P; import inspect; assert all(hasattr(P, m) for m in ('create_order','authorize','capture','refund','void'))"` |
| K3 | offline adapter tests exist and pass | `.venv/bin/python -m pytest -q tests/paypal -m "not live" && test $(ls tests/paypal/test_*.py \| wc -l) -ge 2` |
| K4 | idempotency header on every write | `grep -rq "PayPal-Request-Id" src/ask_first_pay/paypal` |
| K5 | the sandbox host is the default and production needs an explicit flag | `grep -rq "api-m.sandbox.paypal.com" src/ask_first_pay/paypal` |
| K6 | no secrets committed | `! git grep -nE "(client_secret|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,}" -- . ':!docs'` |
