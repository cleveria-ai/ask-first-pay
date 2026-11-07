# N8 — Live-ready PayPal path

Branch `n8-live-ready`, from `main` at the commit that adds this file. Read
`docs/encargos/COMMON.md`, `docs/CONTRACT.md` and `docs/JUDGE_PANEL_2026-11.md` (section on bugs
B1-B13) first. Other sessions work in parallel on `n9-owner-story` (owner page, `gate.py`
describe text, templates `owner.html`/`ledger.html`): do not edit those files.

## Goal

The judge panel (2026-11-07) found that nothing in the submission proves the PayPal sandbox path,
and that the live path has bugs that would surface the first time anyone records against the
sandbox. Fix them so the operator can run the whole story live on 8-9 Nov, and leave a script
that produces evidence of a real sandbox run.

1. **B1** `create_order` must send a `PayPal-Request-Id` unique per order (for example a uuid4
   stored on the booking when the order is created), never derived from `booking-N`, which
   repeats across conversations and restarts. Retrying the *same* order creation must reuse its id.
2. **B2** The order body carries `payment_source.paypal.experience_context` with `return_url`,
   `cancel_url`, `shipping_preference: NO_SHIPPING`, `user_action: CONTINUE` (or the value the
   Orders v2 docs require for authorize-later flows; check and cite) and `brand_name` (fictional
   business name). Add a `/chat/return` route that, when PayPal redirects the buyer back with the
   order token, triggers the same confirm/authorize path as the webhook, so a live run works
   without a webhook tunnel. It must be idempotent with the webhook (whichever arrives first wins,
   the other is a no-op).
3. **B3** `refresh_hold` must distinguish "still valid" from "expired / voided / not found":
   only a transient error may fall back to the current hold; a definitive 4xx marks the deposit
   as no longer held and the agent must not request a capture on it.
4. **B4** `FakeProvider.create_order` models `PayPal-Request-Id` idempotency (same id returns the
   same order; different ids give different orders), so offline tests catch B1.
5. **B5** `FakeProvider` allows capture after the 3-day honor period and up to 29 days (as
   PayPal does), refusing only after 29 days; keep the reauthorize path for honor-period refresh.
6. **B6** The Claude loop keeps every content block of assistant turns in history (including
   thinking blocks, unchanged) and uses a `max_tokens` large enough for tool use with adaptive
   thinking (at least 4096; configurable by env). Unit-test the history handling with a fake client.
7. **B13** `request_void` refuses unless the booking's deposit is currently held.
8. `scripts/sandbox_run.py`: with `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` in the environment
   (never printed, never written), (a) creates a 10.00 order with intent AUTHORIZE and prints the
   buyer approval link; (b) `--continue <order_id>` after the buyer approved: authorizes, issues a
   capture through an approved mandate, retries the same capture with the same
   `PayPal-Request-Id` and records whether PayPal returned the same capture id, creates a second
   order to authorize and void, and appends a run record (timestamps, order/authorization/capture
   ids, HTTP statuses, no tokens or headers) to `docs/SANDBOX_RUN.md`. Test it offline against
   `httpx.MockTransport`.

Do not touch the owner page, `gate.py` describe text or templates other than adding the return route.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | earlier ladders still pass | `python3 -c "import json,subprocess,sys; sys.exit(any(json.loads(subprocess.run(['python3','scripts/escalera.py','docs/encargos/'+n+'.md','--json'],capture_output=True,text=True).stdout)['d']!=0 for n in ('N1_paypal_adapter','N2_agent','N3_demo','N4_integration')))"` |
| K3 | B1: two fresh providers send different create-order request ids, and a retry of the same order reuses its id | `.venv/bin/python -m pytest -q -k "request_id and create_order"` |
| K4 | B2: the order body has experience_context with return_url and NO_SHIPPING | `.venv/bin/python -m pytest -q -k experience_context` |
| K5 | B2: the return route confirms the hold and is idempotent with the webhook | `.venv/bin/python -m pytest -q -k "chat_return"` |
| K6 | B3: a definitive error in refresh_hold marks the deposit not held and blocks capture requests | `.venv/bin/python -m pytest -q -k "refresh_hold and definitive"` |
| K7 | B4: the fake provider honours create-order idempotency | `.venv/bin/python -m pytest -q -k "fake and create_order and idempot"` |
| K8 | B5: the fake provider captures between day 4 and day 29 and refuses after day 29 | `.venv/bin/python -m pytest -q -k "honor and day_29"` |
| K9 | B6: the loop keeps non-text blocks and max_tokens is at least 4096 | `.venv/bin/python -m pytest -q -k "loop and (thinking or history_blocks)"` |
| K10 | B13: request_void refuses when the deposit is not held | `.venv/bin/python -m pytest -q -k "request_void and not_held"` |
| K11 | the sandbox run script works offline and never writes secrets | `.venv/bin/python -m pytest -q -k sandbox_run` |
| K12 | no secrets committed | `! git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}\|(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" -- .` |
