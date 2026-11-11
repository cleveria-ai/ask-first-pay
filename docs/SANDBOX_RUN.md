# PayPal sandbox runs

Appended by `scripts/sandbox_run.py --continue`. Each run lists the ids PayPal returned and every
HTTP call's method, path and status (never tokens, headers or credentials).

## Run 2026-11-11T05:17:30Z (sandbox)

| field | value |
|---|---|
| started | 2026-11-11T05:17:30Z |
| capture_order | 5WF1406594379682R |
| authorization | 7VV66921XN097561Y (CREATED) |
| capture | 998786236C479363B (COMPLETED) |
| capture_retry | 998786236C479363B (COMPLETED) |
| same_capture_id_on_retry | yes |
| gate_replay | refused: replay |
| void_order | 4BB42998PV419681V |
| void_authorization | 63A502184W936794R (CREATED) |
| void | 63A502184W936794R (VOIDED) |
| finished | 2026-11-11T05:17:41Z |

HTTP calls (method, path, status):

- `POST /v1/oauth2/token` 200
- `POST /v2/checkout/orders/5WF1406594379682R/authorize` 201
- `POST /v2/payments/authorizations/7VV66921XN097561Y/capture` 201
- `POST /v2/payments/authorizations/7VV66921XN097561Y/capture` 200
- `POST /v2/checkout/orders/4BB42998PV419681V/authorize` 201
- `POST /v2/payments/authorizations/63A502184W936794R/void` 204
