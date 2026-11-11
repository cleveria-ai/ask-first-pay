# PayPal sandbox runs through the demo's screens

Appended by `scripts/sandbox_ui_run.py`. Each run played three customers through the real pages
(chat, PayPal's own approval page, the owner's phone, the ledger) against the PayPal sandbox. It
lists the ledger rows with the ids PayPal returned and every HTTP call's method, path and status
(never tokens, headers or credentials). Screenshots: `docs/screenshots/12-sandbox-*.png`.

A `reauthorize` answered 422 is expected: before a no-show capture the agent asks PayPal to refresh
the hold, PayPal declines for a fresh one, and the agent goes on with the hold it has
(`refresh_hold` in `src/ask_first_pay/agent/tools.py`).

## Run 2026-11-11T05:33:08Z (sandbox)

Finished 2026-11-11T05:35:09Z. Agent model: offline scripted. Ledger chain check: intact.

| n | result | action | PayPal resource | amount | PayPal answered | PayPal-Request-Id (mandate id) |
|---|---|---|---|---|---|---|
| 1 | executed | capture_deposit | 20C14088TG252664F | 10.00 | PayPal capture id 7YN16151ST920971N (COMPLETED) | 840f2afca247450783f5ec474ce92ab1 |
| 2 | rejected · replay | capture_deposit | 20C14088TG252664F | 10.00 |  |  |
| 3 | executed | void_deposit | 8K576667JA748733C | 0.00 moved (cap 0.01) | PayPal authorization 8K576667JA748733C (VOIDED) | 45ade87d6db54e35a50005657ce379da |
| 4 | executed | capture_deposit | 46E74363MD0396308 | 10.00 | PayPal capture id 5LP876075J833584E (COMPLETED) | dc54649bf0ce425382a989382350bba5 |
| 5 | executed | refund_deposit | 5LP876075J833584E | 10.00 | PayPal refund id 0CE05358RE990873D (COMPLETED) | fdd6ac056b594e40addfa2f6dad07990 |

HTTP calls (method, path, status):

- `POST /v1/oauth2/token` 200
- `POST /v2/checkout/orders` 200
- `POST /v2/checkout/orders/32A7874178884262T/authorize` 201
- `POST /v2/payments/authorizations/20C14088TG252664F/reauthorize` 422
- `POST /v2/payments/authorizations/20C14088TG252664F/capture` 201
- `POST /v2/checkout/orders` 200
- `POST /v2/checkout/orders/9CF072533V251615C/authorize` 201
- `POST /v2/payments/authorizations/8K576667JA748733C/void` 204
- `POST /v2/checkout/orders` 200
- `POST /v2/checkout/orders/7V686220U65831432/authorize` 201
- `POST /v2/payments/authorizations/46E74363MD0396308/reauthorize` 422
- `POST /v2/payments/authorizations/46E74363MD0396308/capture` 201
- `POST /v2/payments/captures/5LP876075J833584E/refund` 201
