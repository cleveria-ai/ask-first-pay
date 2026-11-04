# N1 — PayPal sandbox adapter

Branch `n1-paypal-adapter`. Read `docs/encargos/COMMON.md` and `docs/CONTRACT.md` first.

## Goal

`src/ask_first_pay/paypal/` exports `PayPalProvider`, which implements the `PaymentProvider` port
(`src/ask_first_pay/ports.py`) against the PayPal REST API in the **sandbox**. Use `httpx`
(already a dependency). Credentials only from `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`.

## API summary (check it against developer.paypal.com if you can reach it; if not, use this)

Base URL: `https://api-m.sandbox.paypal.com`. Production (`https://api-m.paypal.com`) only with
`PayPalProvider(environment="production", allow_production=True)`; anything else raises.

| Port method | Request | Notes |
|---|---|---|
| token | `POST /v1/oauth2/token`, basic auth client_id:secret, form `grant_type=client_credentials` | cache until `expires_in` minus a margin |
| `create_order` | `POST /v2/checkout/orders` `{"intent":"AUTHORIZE","purchase_units":[{"reference_id":<reference>,"amount":{"currency_code":"USD","value":"10.00"}}]}` | payer link is `links[rel=payer-action]` or `links[rel=approve]`: accept both |
| `authorize` | `POST /v2/checkout/orders/{id}/authorize` | authorization at `purchase_units[0].payments.authorizations[0]`; the order becomes `COMPLETED` |
| `reauthorize` | `POST /v2/payments/authorizations/{id}/reauthorize` | only after the 3-day honor period; returns a new authorization id |
| `capture` | `POST /v2/payments/authorizations/{id}/capture` `{"amount":{...},"final_capture":true}` | partial captures allowed with `final_capture:false` |
| `refund` | `POST /v2/payments/captures/{id}/refund` `{"amount":{...}}` | |
| `void` | `POST /v2/payments/authorizations/{id}/void` | answers **204 with no body**: return the authorization with status `VOIDED` (or GET it) |

- Every write sends `PayPal-Request-Id: <request_id>` (the port passes it; the gate uses the
  mandate id). `create_order` and `authorize` derive one from their inputs.
- Amounts: send a string with exactly two decimals; reject (do not round) an amount with more.
- Errors: PayPal answers `{"name": ..., "message": ..., "details": [...]}`; map to
  `ProviderError(code=name)`. Timeouts and 5xx raise `ProviderError(code="TRANSIENT", transient=True)`.

## Tests

`tests/paypal/test_paypal_*.py`, offline with `httpx.MockTransport` and fixtures in
`tests/paypal/fixtures/` shaped like PayPal's documented responses. One live test,
`tests/paypal/test_paypal_live.py`, marked `@pytest.mark.live`, that creates an order in the
sandbox and prints the payer link (approving needs a browser: write the manual steps in its
docstring). A contract test runs the same story on `FakeProvider` and on `PayPalProvider` with the
mock transport and asserts the same sequence of statuses.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the adapter implements every port method | `.venv/bin/python -c "from ask_first_pay.paypal import PayPalProvider as P; assert all(callable(getattr(P, m, None)) for m in ('create_order','authorize','reauthorize','capture','refund','void'))"` |
| K3 | at least 8 offline adapter tests, all passing | `test $(.venv/bin/python -m pytest tests/paypal --collect-only -q \| grep -c '::') -ge 8 && .venv/bin/python -m pytest -q tests/paypal` |
| K4 | a test inspects the sent request and asserts PayPal-Request-Id equals the request_id on capture, refund and void | `.venv/bin/python -m pytest -q tests/paypal -k request_id` |
| K5 | a test proves production without the explicit flag raises | `.venv/bin/python -m pytest -q tests/paypal -k production` |
| K6 | a test proves amounts go as two-decimal strings and three decimals are rejected | `.venv/bin/python -m pytest -q tests/paypal -k amount` |
| K7 | a test proves a timeout raises a transient error and the retry with the same request_id is sent with the same header | `.venv/bin/python -m pytest -q tests/paypal -k transient` |
| K8 | void with a 204 empty body returns VOIDED | `.venv/bin/python -m pytest -q tests/paypal -k void` |
| K9 | the contract test runs both providers | `.venv/bin/python -m pytest -q tests/paypal -k contract` |
| K10 | no secrets committed | `! git grep -nE "(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,}" -- . ':!docs'` |
