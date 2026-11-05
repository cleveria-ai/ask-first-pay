# N6 design: one visual system, a "what just happened" line, AG Grid made visible

Goal: make the submission look and read like a finished product (Design, Presentation) and make
the AG Grid use genuine and visible for the AG Grid sponsor prize. Nothing here touches
`gate.py`, `ports.py`, `pyproject.toml` or `libs/`; no paid API was called.

## What changed

**Design system** (`src/ask_first_pay/demo/static/app.css`): type scale (13/14/16/19/24/30 px),
4 px spacing scale, color tokens for light and dark mode, every text/background pair checked at
>= 4.5:1 by a test, 44 px touch targets (buttons, nav, quick replies, filter buttons, grid rows),
mobile-first at 375 px with a two-column layout from 900 px (checked at 1280 px). System fonts
only; no CDN.

**"What just happened"** (`src/ask_first_pay/demo/happened.py`): after every action (chat
message, checkout approval, scenario, owner approve/decline, pairing, replay) every page shows
one status line built by diffing the state before and after: new ledger rows (executed /
rejected with reason), new or declined mandates, booking status changes, a new paired key. Tone
Done / Waiting / Refused / Info. It is built from the ledger, mandates and bookings, never from
model text.

**Empty and error states**: empty ledger and empty mandate list are explained with a next step
instead of an empty table; pairing and approval errors are shown in red on the phone; a replay
with nothing to replay says so.

**AG Grid Community** (`static/grid.js`, vendored 36.3.0, MIT license file present): sorting,
text/number column filters, external filters (Executed/Rejected, Capture/Void/Refund on the
ledger; Pending/Used/Declined on the owner page), quick-filter search, status chips through `valueGetter` + `cellClass`
(no cell renderers; cell values stay text), single-row selection driving a detail panel with
the signed fields and the chain link, CSV export, Theming API fed from the CSS tokens (light and
dark), keyboard Enter to open a row. New `GET /ledger/entry/{n}` returns the row as written
(`hash`, `prev`) so the chain link can be followed. The plain table stays as the no-JS fallback.

**Docs**: "Built with AG Grid" in `README.md` and `docs/DEVPOST.md`; screenshot gallery table in
`docs/DEVPOST.md`; `docs/SUBMISSION_CHECKLIST.md` points at the new images and the AG Grid prize.
`scripts/screenshots.py` regenerates them (headless Chromium, offline demo, real WebCrypto pairing).

## Before / after

| | Before (`main`) | After |
|---|---|---|
| Chat | ![before chat](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/before/chat.png?raw=true) | ![after chat](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/01-chat-booking.png?raw=true) |
| Owner | ![before owner](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/before/owner-pending.png?raw=true) | ![after owner](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/02-owner-approval.png?raw=true) |
| Ledger | ![before ledger](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/before/ledger.png?raw=true) | ![after ledger](https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/03-ledger-replay.png?raw=true) |

New: cancellation voided (https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/04-cancellation-voided.png?raw=true),
phone views at 375x812 (https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/05-owner-mobile.png?raw=true, https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/06-ledger-mobile.png?raw=true,
https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/07-chat-mobile.png?raw=true), dark mode (https://github.com/cleveria-ai/ask-first-pay/blob/n6-design/docs/screenshots/08-ledger-dark.png?raw=true).

## Checks

```
$ .venv/bin/python -m pytest -q          # before: 165 passed, 1 deselected
387 passed, 1 deselected (after merging main with N7)
```
29 new tests in `tests/demo/test_demo_design.py`: token contrast (light and dark), 44 px
targets, no external URL in static files, vendored AG Grid and its license, the AG Grid features
`grid.js` relies on, ledger rows carry the signed fields and `prev == previous hash`, the raw
row endpoint, mandate tones and ledger refs, the "what just happened" line before any action,
after pairing, booking, checkout, scenario, approve, replay, decline, a refused approval, a
refused pairing and a replay with nothing to replay, the empty states, local scripts only, and
no favicon 404.

Ladders (start of session: all d = 0.00):
```
$ python3 scripts/escalera.py docs/encargos/N1_paypal_adapter.md
d = 0/10 = 0.00
$ python3 scripts/escalera.py docs/encargos/N2_agent.md
d = 0/9 = 0.00
$ python3 scripts/escalera.py docs/encargos/N3_demo.md
d = 0/8 = 0.00
$ python3 scripts/escalera.py docs/encargos/N4_integration.md
d = 0/10 = 0.00
```

Browser check (headless Chromium 1280x720, offline demo): ledger 2 rows; "Rejected" filter 1;
"Void" 0; search "replay" 1; CSV downloads `ask-first-pay-ledger.csv`; row click opens the
detail on the ledger and the owner page; no console errors.

## After merging N7 (main)

- `tests/security/test_security_http.py::test_grid_js_never_renders_cell_values_as_html` failed
  with both branches together: `grid.js` had cell renderers (they built DOM nodes with
  `textContent`, but the test forbids renderers outright). Now no renderer, no `innerHTML`, no
  `valueFormatter`: chips come from `cellClass` with the tone looked up in a fixed set, the result
  text from `valueGetter`, the hash link moved to the row detail (built with `textContent`).
- Found in the browser, not by the suite: N7's `Referrer-Policy: no-referrer` makes Chromium send
  `Origin: null` on the pages' own form POSTs, so the CSRF check returned 403 on every scenario,
  chat and replay button. Changed to `same-origin` (no referrer leaves the site; Origin is sent).
  Also `font-src 'self' data:` so AG Grid's built-in icon font loads under the CSP. Test:
  `test_design_same_origin_form_posts_pass_and_referrer_keeps_origin` (`Origin: null` still 403).

## Not done / for the owner

- The video clips in `docs/video/raw/` were not re-recorded with the new look
  (`scripts/record_demo.py` still works against it: same button names and grid cells).
- The Devpost thumbnail (3:2 crop) is the owner's.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01T6xRaPeFydvQfhG4s9zkSe
