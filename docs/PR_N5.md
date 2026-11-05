# N5: judge review and fixes

A strict judge pass over `n4-integration`, then fixes for what it found. Full review with
evidence: `docs/JUDGE_REVIEW.md`. **Not merged by me.** Base: `n4-integration`.

## Scores (1–10, five equally weighted criteria)

| Criterion | Before | After |
|---|---|---|
| Technological Implementation | 6 | 7 |
| Design | 6 | 7 |
| Potential Impact | 6 | 7 |
| Innovation | 7 | 7 |
| Presentation | 6 | 7 |
| **Total** | **31/50** | **35/50** |

Best fits: honorable mention **Best Use of Agentic Commerce**, sponsor prize **AG Grid** (it
qualifies, but the grid use is thin).

## What I found by driving the demo over HTTP (fresh clone, no keys) and fixed

| # | Found on `n4-integration` | Fix | Test |
|---|---|---|---|
| 1 | Approving after **Decline** still captured money | declines are final (`400 declined`) | `tests/demo/test_demo_judge_fixes.py` |
| 2 | Every demo slot is >3 days after booking, and the agent had no reauthorize tool, so the no-show capture would hit PayPal's honor period | new free tool `refresh_hold` (reauthorize once, idempotent id); the offline model calls it before `request_capture`; system prompt updated | `tests/agent/test_agent_holds.py`, demo test 5 days later |
| 3 | The agent could put "capture 500.00" on a 10.00 hold in front of the owner | capture bounded by the hold, refund by what is still captured | `tests/agent/test_agent_holds.py`; one N2 test now asserts the refusal plus the provider rule |
| 4 | A timeout after PayPal captured burned the mandate and logged `failed` | the gate executor retries transient errors with the same `PayPal-Request-Id` | `tests/test_skeleton.py -k transient` |
| 5 | A second approval answered `ok` | `400 already_approved` | demo tests |
| 6 | Rejected ledger rows had no action, resource or amount | filled from the mandate's signed fields | demo tests |
| 7 | The No-show button booked a new customer, not the one in the chat (the video's shots 3→4 did not connect) | scenarios act on the customer's newest held booking first | demo tests |
| 8 | Malformed JSON on owner endpoints gave 500 | 400 | demo tests |
| 9 | `pip install -e .` did not install `ask_first`; a non-editable install had no templates | `pyproject.toml` package-dir + package data | `tests/test_packaging.py` |
| 10 | Owner read `capture_deposit` and unix time only; pairing form stayed after pairing | plain headline chosen by the signed action and cap; pairing hidden once paired | demo test |

Docs: README (audience, real clone URL, 60-second path, "Try to break it", "Limits we know
about"), DEVPOST (audience, ten tools, reauthorize, retry, no overclaim, 116 tests), VIDEO_SCRIPT
(audience in shot 1, same customer through the no-show, a 10 s injection shot, total 2:40),
checklist total, new screenshots from a real Chromium run (WebCrypto pairing + Approve).
Contract files touched (`gate.py`, `pyproject.toml`) are noted in `docs/CONTRACT_CHANGES.md`.

## Suite
```
before (n4-integration): 103 passed, 1 deselected in 4.93s
after  (n5-judge):       116 passed, 1 deselected in 5.38s
```

## Ladders at the end (n5-judge)
```
== N1_paypal_adapter
PASS  K1   the whole suite is green  | 116 passed, 1 deselected in 5.55s
PASS  K2   the adapter implements every port method  | 
PASS  K3   at least 8 offline adapter tests, all passing  | 25 passed, 1 deselected in 0.21s
PASS  K4   a test inspects the sent request and asserts PayPal-Request-Id equals the request_id on capture, refund and void  | 4 passed, 22 deselected in 0.05s
PASS  K5   a test proves production without the explicit flag raises  | 1 passed, 25 deselected in 0.14s
PASS  K6   a test proves amounts go as two-decimal strings and three decimals are rejected  | 8 passed, 18 deselected in 0.05s
PASS  K7   a test proves a timeout raises a transient error and the retry with the same request_id is sent with the same header  | 2 passed, 24 deselected in 0.05s
PASS  K8   void with a 204 empty body returns VOIDED  | 3 passed, 23 deselected in 0.05s
PASS  K9   the contract test runs both providers  | 1 passed, 25 deselected in 0.05s
PASS  K10  no secrets committed  | 
d = 0/10 = 0.00
== N2_agent
PASS  K1   the whole suite is green  | 116 passed, 1 deselected in 5.60s
PASS  K2   at least 6 agent tests, all passing offline without any key  | 12 passed in 0.09s
PASS  K3   the agent code has no path to approval or to moving money  | 
PASS  K4   the injection test passes and asserts the spy saw no money movement  | 1 passed, 11 deselected in 0.05s
PASS  K5   the cancellation test passes and uses void  | 1 passed, 11 deselected in 0.06s
PASS  K6   the owner summary test passes  | 1 passed, 11 deselected in 0.05s
PASS  K7   the public entry point exists  | 
PASS  K8   the toolkit decision is written with sources  | 
PASS  K9   no secrets committed  | 
d = 0/9 = 0.00
== N3_demo
PASS  K1   the whole suite is green  | 116 passed, 1 deselected in 5.43s
PASS  K2   the three pages answer 200 and show their key content (chat input, a pending-mandate list, the chain check)  | 9 passed, 22 deselected in 0.33s
PASS  K3   the no-show story captures exactly once and only after approval  | 5 passed, 26 deselected in 0.23s
PASS  K4   the cancellation story voids and never refunds  | 3 passed, 28 deselected in 0.21s
PASS  K5   a declined or replayed mandate shows as rejected on the ledger page  | 8 passed, 23 deselected in 0.27s
PASS  K6   the demo never moves money outside the gate  | 
PASS  K7   one command starts the demo  | 
PASS  K8   no external CDN at runtime  | 
d = 0/8 = 0.00
== N4_integration
PASS  K1   the whole suite is green  | 116 passed, 1 deselected in 5.40s
PASS  K2   the three pieces' ladders give d = 0 on this branch  | 
PASS  K3   the demo chat calls the real agent  | 
PASS  K4   an end-to-end test drives chat, owner approval and ledger through the agent  | 9 passed, 22 deselected in 1.67s
PASS  K5   the demo starts and serves the chat page with no keys  | 
PASS  K6   the README has the judge sections  | 
PASS  K7   the Devpost text has its seven sections  | 
PASS  K8   the video script exists and states a total under 2:45  | 
PASS  K9   the submission checklist exists  | 
PASS  K10  no secrets committed  | 
d = 0/10 = 0.00
```

## Left for the owner (only you can, or it needs keys)

1. **One live run each** with your own keys before recording (never commit them): `pytest -m live`
   with `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`, and the demo with `ANTHROPIC_API_KEY`. No
   session has run Claude or the sandbox end to end. This is the biggest remaining risk to the
   Technological Implementation score and to "Best Use of PayPal + AI".
2. Consider recording with Claude and the sandbox approval page on screen; the no-key demo's agent
   is a rule-based script, which judges will notice.
3. Review/merge this PR into `n4-integration`, then #4 into `main`; record from
   `docs/VIDEO_SCRIPT.md` (2:40); remove the WIP line, check history for secrets, make the repo
   public, submit before **2026-11-12 12:00 Pacific**.
4. Optional for the AG Grid prize: ledger filters by result/reason and a detail row with the signed
   mandate and receipt.

---
_Generated by [Claude Code](https://claude.ai/code)_

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01T6xRaSQreSGsFdcazwjCn5
