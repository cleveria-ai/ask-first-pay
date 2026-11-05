# Judge review (N6)

Same rubric as `docs/JUDGE_REVIEW.md` (five official criteria, equally weighted, 1-10 each).
"Before" is `n5-judge` (feaaa6c), as scored there; "after" is
`claude/ask-first-pay-webhooks-video-xjlz0e`. Nothing here was run against live Claude or the
live PayPal sandbox: no keys in this session. Those runs are the operator's
(`docs/video/SHOTLIST.md`, checklist).

## Scores

| Criterion | Before (N5) | After (N6) | Main evidence |
|---|---|---|---|
| Technological Implementation | 7 | 8 | Before: no webhooks, the customer had to say "I paid"; state lost on restart. After: `/webhooks/paypal` verifies PayPal's signed format locally (SHA256withRSA over `transmission_id\|transmission_time\|webhook_id\|crc32(body)`, certificate only from `https://*.paypal.com`, 5-minute window, dedupe by event id), `src/ask_first_pay/paypal/webhooks.py`; the simulated checkout now goes through that path; optional SQLite per shop, `src/ask_first_pay/store.py`, which also rebuilds "used" from the ledger so a restart cannot reopen a replay. Still not run live (weakness 4 of N5 stays open). |
| Design | 7 | 7 | Same three pages. The chat now shows "PayPal webhook: the customer approved the deposit", which makes the hold step legible. No new UI for the webhook log beyond `GET /webhooks/paypal/events`. |
| Potential Impact | 7 | 7 | Persistence and a `shop_id` key remove "a restart forgets everything", the main blocker to a pilot. Still one shop per process, no owner login, no real WhatsApp channel: not enough to move the score. |
| Innovation | 7 | 7 | Unchanged idea. Webhook verification is standard practice; the one new twist (a webhook may hold, never move money) is a consequence of the existing design. |
| Presentation | 7 | 7 (8 once recorded) | Added: `docs/video/SHOTLIST.md` (160 s, per-shot say/show, checklist), `docs/video/subtitles.srt` generated from it, nine raw 1280x720 clips recorded headless by `scripts/record_demo.py`, and `scripts/check_video_assets.py` keeping the three in step. A judge scores the published video, which does not exist yet; the score moves only when it does. |
| **Total (of 50)** | **35** | **36** | 37 projected after a recorded video with live Claude and the sandbox. |

## Commands behind the scores

```
$ .venv/bin/python -m pytest -q            # before (n5-judge, this session, start of work)
116 passed, 1 deselected in 5.50s
$ .venv/bin/python -m pytest -q            # after
TESTS_AFTER
$ .venv/bin/python scripts/check_video_assets.py
OK total 160 s <= 180 s; 9 shots; shot list, subtitles and record_demo agree
$ .venv/bin/python scripts/record_demo.py  # headless Chromium 153, offline demo
... saved docs/video/raw/01-title.webm ... 09-closing.webm   (9 clips, 9.4 MB, 1280x720 vp8)
$ git diff --stat feaaa6c -- libs/ src/ask_first_pay/gate.py src/ask_first_pay/ports.py | wc -l
0                                          # the signed mandate's contract is unchanged
```

Against a real server process (`scripts/demo.sh`, no keys, port 8011):
```
GET  /healthz                                  {"ok":true}
POST /webhooks/paypal  (unsigned JSON body)    {"ok":false,"reason":"missing_header",...}
GET  /webhooks/paypal/events                   {"enabled":true,"simulated":true,"events":[]}
```
Restart with `ASK_FIRST_DB` (two processes on the same file, port 8012):
```
POST /chat/send  message=book Mon 16 Nov 09:00      303
(process stopped, a new one started on the same file)
GET  /chat  ->  "Reserved Mon 16 Nov 09:00. To confirm, hold a $10.00 deposit (nothing is charged now)."
```
What the new tests pin down (`tests/paypal/test_paypal_webhooks.py`,
`tests/demo/test_demo_webhooks.py`, `tests/demo/test_demo_store.py`, `tests/test_video_assets.py`):
altered body, altered header, wrong algorithm, non-PayPal or non-https cert URL, stale
timestamp, missing header, another webhook id, a key that is not the certificate's, and an
expired certificate are all refused; a redelivered event is a duplicate (also after a restart);
genuine capture/refund/void events move no money and ask the owner nothing; an EXPIRED event
stops a later capture request; after a restart a pending mandate can still be approved once, a
used one is still `rejected · replay`, a decline is still final, and a capture whose snapshot
was never saved is still marked used from the ledger.

## Weaknesses from N5, where they stand

| N5 weakness | Now |
|---|---|
| 1-3, 6-9 (decline not final, honor period, inflated asks, timeout after capture, video incoherence, ledger readability, packaging) | fixed in N5; unchanged |
| 4. No live run of Claude or the PayPal sandbox | **open, operator**: checklist items 1-2 in `docs/video/SHOTLIST.md`; webhook verification against PayPal's real certificate is part of item 2 |
| 5. Without a key the AI is a script | **open, operator**: record shots 3, 4, 6 and 7 with Claude, or keep the "Agent model: offline scripted model" line visible |
| 10. Overclaims; "no webhooks, in-memory single-shop state" | **webhooks: fixed** (verified, deduplicated, cannot move money). **In-memory: fixed** (optional SQLite). **Single shop: partly** (the store is keyed by shop; one process still serves one) |

## Prize fit

Unchanged from N5: Honorable mention *Best Use of Agentic Commerce* first; *Best Use of PayPal +
AI* needs the live runs on video. AG Grid use is still thin.
