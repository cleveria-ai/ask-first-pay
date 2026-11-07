# N9 — The owner's phone tells the story

Branch `n9-owner-story`, from `main` at the commit that adds this file. Read
`docs/encargos/COMMON.md`, `docs/CONTRACT.md`, `docs/JUDGE_PANEL_2026-11.md` and the winning
variant V1 with its grafts in `docs/STORY_VARIANTS_2026-11.md` first. Another session works in
parallel on `n8-live-ready` (PayPal provider, agent tools, agent loop, fake provider): do not edit
`src/ask_first_pay/paypal/`, `src/ask_first_pay/agent/`, `fake_provider.py` or `offline_model.py`.

## Goal

The video's opening and closing shots are the owner's phone (story V1, "Can it touch my money?").
Make that page a product a small-clinic owner would recognise, with every number computed from the
signed mandates and the ledger, never from model text.

1. **Owner card (B7, G7, G8, G12).** Times are human and local ("expires in 58 min", "Mon 9:12
   a.m."), never unix time or raw UTC. The card shows "Approval id <first 8 of jti> (sent to
   PayPal as PayPal-Request-Id)". The void card headline reads "Moves $0.00 · releases the
   $10.00 hold"; the symbolic 0.01 cap moves into the details. Chips: "Irreversible · needs your
   signature" on capture and refund cards.
2. **Mobile (B9).** On a 375x812 viewport the Approve button of the first pending card is fully
   visible without scrolling.
3. **Expiry (B12).** Mandate lifetime is configurable (`ASK_FIRST_MANDATE_TTL_MIN`), default 60
   minutes; the card shows the remaining time.
4. **"Today" panel (V1 change 6, G12).** On `/owner`, built only from bookings and the ledger:
   PayPal calls the agent made on its own (create order, authorize, reauthorize) with "$0.00
   moved"; owner taps; amounts kept / given back / released; refused attempts; and the line
   "$0.00 moved without your signature" computed from the ledger (it must show a different value
   if a test injects an unsigned money movement). AG Grid may render it if that stays within the
   N7 security rules (no HTML cell renderers).
5. **The phone buzzes (G6).** `owner.js` polls the pending mandates; on a new one it calls
   `navigator.vibrate` when available and sets a "(1)" badge in the page title. No new
   dependencies, no inline scripts (CSP from N7 stays as is).
6. **Video-safe labels (V1 change 1).** With `ASK_FIRST_VIDEO=1` the pages show no third-party
   brand other than PayPal: the model chip reads "Agent model: live LLM, tool use" (or "offline
   scripted model"), and the "AG Grid Community" captions are hidden. Without the flag nothing
   changes. The ledger detail shows "Sent to PayPal as PayPal-Request-Id: <jti>" and the PayPal id
   returned (capture/refund/void) when present.
7. Refresh `docs/screenshots/` with `scripts/screenshots.py` (both themes if the script supports
   it) and keep the gallery in `docs/DEVPOST.md` consistent with the files.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | earlier ladders still pass | `python3 -c "import json,subprocess,sys; sys.exit(any(json.loads(subprocess.run(['python3','scripts/escalera.py','docs/encargos/'+n+'.md','--json'],capture_output=True,text=True).stdout)['d']!=0 for n in ('N1_paypal_adapter','N2_agent','N3_demo','N4_integration')))"` |
| K3 | no unix time or raw UTC on owner cards | `! grep -rn "unix time" src/ask_first_pay && .venv/bin/python -m pytest -q -k "owner_card and human_time"` |
| K4 | the card shows the approval id as PayPal-Request-Id | `.venv/bin/python -m pytest -q -k "owner_card and request_id"` |
| K5 | the void card says it moves $0.00 | `.venv/bin/python -m pytest -q -k "void_card and moves_zero"` |
| K6 | mandate TTL is configurable with default 60 minutes | `.venv/bin/python -m pytest -q -k "mandate_ttl"` |
| K7 | the Today panel is computed from the ledger, including "$0.00 moved without your signature" | `.venv/bin/python -m pytest -q -k "today_panel"` |
| K8 | video-safe mode hides third-party brands except PayPal | `.venv/bin/python -m pytest -q -k "video_safe"` |
| K9 | Approve is above the fold at 375x812 | `.venv/bin/python -m pytest -q -k "approve_above_fold"` |
| K10 | the owner page polls and buzzes without inline scripts | `grep -q "navigator.vibrate" src/ask_first_pay/demo/static/*.js && ! grep -n "<script>" src/ask_first_pay/demo/templates/owner.html` |
| K11 | the N7 security suite still passes | `.venv/bin/python -m pytest -q tests/security` |
| K12 | no secrets committed | `! git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}\|(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" -- .` |
