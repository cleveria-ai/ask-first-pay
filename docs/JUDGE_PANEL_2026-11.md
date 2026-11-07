# Judge panel synthesis, November 2026

- **Date:** 2026-11-07 (deadline 2026-11-12 12:00 PT; 5 days left, counting today)
- **Commit evaluated:** `57fb354` (N6: design system, AG Grid showcase, Devpost screenshots)
- **Method:** 7 independent judges scored the same commit against the 5 official, equally weighted
  criteria (rules lines 205-214). Five were Claude agents, each given a different role so they
  would disagree: PayPal developer-relations judge, innovation judge, business/impact judge,
  UX/demo judge, and skeptic. Two came from other model families: OpenAI codex and Google gemini.
  Each judge gave a Stage 1 verdict, five scores out of 10, prize odds, reasons it would not win,
  improvements with hours and acceptance checks, and disqualification risks. This document merges
  them. Every code bug below was re-checked by hand on `57fb354` in a clean worktree. The full suite
  passes there: `387 passed, 1 deselected`.
- **Companion:** `docs/STORY_VARIANTS_2026-11.md` (five pitch variants and the chosen story).

> This file is internal. Like `docs/JUDGE_REVIEW*.md`, `docs/PR_N*.md`, `docs/encargos/` and
> `_sesion/`, it lists the entry's weaknesses. Untrack it before the repository goes public
> (see improvement 1).

## 1. Scores

Stage 1 (pass/fail on theme and API use): **all 7 judges say pass**. Four of them say a strict
screener could doubt "reasonably applies PayPal" if the video only shows `Simulated PayPal` and
`offline scripted model` (the PayPal, business, UX and skeptic judges).

| Judge | Family | Tech. Impl. | Design | Impact | Innovation | Presentation | **Total /50** |
|---|---|---:|---:|---:|---:|---:|---:|
| PayPal DevRel | Claude | 6 | 6 | 5 | 6 | 5 | **28** |
| Innovation | Claude | 7 | 6 | 6 | 6 | 6 | **31** |
| Business / impact | Claude | 7 | 6 | 4 | 7 | 5 | **29** |
| UX / demo | Claude | 7 | 5 | 5 | 6 | 5 | **28** |
| Skeptic | Claude | 6 | 6 | 5 | 5 | 4 | **26** |
| codex | OpenAI | 8 | 7 | 7 | 8 | 5 | **35** |
| gemini | Google | 8 | 7 | 7 | 8 | 7 | **37** |
| **Mean (7)** | | **7.00** | **6.14** | **5.57** | **6.57** | **5.29** | **30.57** |
| Std. dev. (sample) | | 0.82 | 0.69 | 1.13 | 1.13 | 0.95 | 4.04 |
| Range | | 6-8 | 5-7 | 4-7 | 5-8 | 4-7 | 26-37 |
| Mean, Claude only (5) | | 6.6 | 5.8 | 5.0 | 6.0 | 5.0 | 28.4 |

Reading:

- The median total is **29/50**. The two other-family judges score 6-9 points higher than the
  Claude judges, mostly on Impact and Innovation. They read the documents generously and gave no
  role-specific scrutiny, so treat 35-37 as the ceiling, not the expected score.
- **Technological Implementation is the strongest criterion** (7.0, low spread): every judge
  credits the AUTHORIZE lifecycle, the jti used as PayPal-Request-Id, and webhook verification.
  The ceiling is "never run live".
- **Presentation (5.3) and Impact (5.6) are the weakest.** Presentation assumes the video gets
  recorded as scripted. With no video it is about 1 (innovation judge).
- **Impact and Innovation split the panel most** (std. dev. 1.13). The business judge gives 4 for
  Impact (no numbers, owner burden). codex and gemini give 7-8 for Innovation; the skeptic gives 5,
  citing AP2, Visa and Mastercard mandates.

## 2. Prize odds by judge

All figures are each judge's own estimates, as they stated them. A value in parentheses is the
judge's estimate after its own improvements.

| Judge | Any general (1st-3rd) | Agentic Commerce | PayPal + AI | Most Creative | Most Impactful | Best Demo | AG Grid any place | AG Grid 1st | Render |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PayPal DevRel | 4% | 7% (12% vs AP2) | 5% (15% live + toolkit) | 3% | 2% (5% with qnowa) | 3% | 20% | 5% | 0% |
| Innovation | 4% | 7% (12% reframed) | 3% | 2% | 2% | 1% (4% live) | 15% | 3% | 0% |
| Business | 3% | 8% | 4% (10% live) | 3% | 1-2% | 2% | 15% | 3% | 0% |
| UX / demo | 3% | 8% (15% after fixes) | 3% | 2% | 2% | 1-2% | 15-20% | 4% | 0% |
| Skeptic | 3% | 5% | 3% | 1% | 2% | 1% | 15% | 3% | 0% |
| codex | 1% | 7% | 3% | 3% | 2% | 2% | 3% | n/a | n/a |
| gemini | 20% | 60% | 35% | 30% | 25% | 20% | 65% | 25% | n/a |
| **Median** | **3%** | **7%** | **3%** | **3%** | **2%** | **2%** | **15%** | **3%** | **0%** |

Other totals the judges gave: any cash prize about 20% (innovation); any general or honorable
mention about 12% (UX) and about 10% (skeptic). The skeptic expects all odds to rise about 1.5x
with a public live-sandbox video that opens on the business.

Consensus: the best fit is **Best Use of Agentic Commerce** (all 7 judges), followed by the
**AG Grid sponsor prize**, which stacks with a general or honorable-mention prize (rules
lines 297-300). gemini is an outlier by an order of magnitude on every line; the other six agree
within a few points. Render is 0% because nothing is hosted on Render.

## 3. Why it would not win (consolidated)

Duplicates are merged. Judges: **P** PayPal DevRel, **I** innovation, **B** business, **U** UX,
**S** skeptic, **C** codex, **G** gemini.

| # | Reason | Judges |
|---|---|---|
| W1 | **Nothing real is on screen.** Every screenshot and raw clip shows `Simulated PayPal`, FakeProvider ids (AUTH-0002) and `offline scripted model`. There is no sandbox.paypal.com page, no dashboard capture, no real webhook and no live Claude. This caps Tech, Presentation and "Best Use of PayPal + AI". | P I B U S C G |
| W2 | **There is no video yet and the repository is private** (README.md:3 "Work in progress, private until submission"). Presentation is judged on the video, so it cannot be scored until the video exists. | P I U S C G |
| W3 | **It pattern-matches to "agent asks, human approves, capped, audit log".** Nothing positions it against Google AP2 (Intent/Cart Mandates), OpenAI/Stripe ACP, Visa Intelligent Commerce, Mastercard Agent Pay, MCP elicitation or LangGraph interrupt(). The genuinely new parts (seller-side mandates over the post-authorization lifecycle, the hold as the agent's free zone, one tap = one PayPal-Request-Id) sit in "Challenges" instead of the headline. | P I B U S C |
| W4 | **The impact case has no numbers and hides the real business.** No no-show rate, deposit size or recovered money appears anywhere. qnowa, a real company selling deposit booking to Latin American clinics and salons, is never mentioned (grep finds 0 hits). The demo is a fictional US clinic in USD, in English. | P I B U S C |
| W5 | **The owner card cannot support the owner's decision.** It shows no customer and no appointment, only `capture_deposit on AUTH-0002`, a unix timestamp and UTC times. On a 375 px phone, Approve is below the fold. The scenario buttons on the customer chat make it read as a test harness, not a product. | P I B U S |
| W6 | **The AI looks thin.** The default model is regex slot-matching. The No-show button sends the literal instruction "Ask the owner to capture the deposit", so the agent makes no judgment of its own. | P I S |
| W7 | **The pitch is written for security engineers.** Narration uses intent AUTHORIZE, idempotency key, hash chain and Ed25519. The video spends 10 s on an ASCII diagram that is unreadable at 720p, and 15 s re-shows the ledger. The owner's pain has no number. | B U S C |
| W8 | **It adds work compared with incumbents.** Booksy, Fresha, Vagaro and Square already charge no-show fees automatically by policy. Here the owner taps for every no-show and every cancellation (even a 0.01 void) within a 15-minute mandate window (gate.py:74). Standing policies appear only under "What's next". | I B S |
| W9 | **It explicitly rejects PayPal's Agent Toolkit/MCP** (docs/agent_toolkit_decision.md). The reasons are sound, but a PayPal or checklist-driven judge reads it as "didn't use our AI tools". | P S G |
| W10 | **There is no hosted demo URL.** Judges reviewing 200+ entries will not clone a Python repository. | P S G |
| W11 | **The raw clips predate the N6 redesign** (docs/PR_N6_design.md:95-96), so the video and the Devpost screenshots tell different visual stories. | U S |
| W12 | **The core engine is reused.** `libs/ask-first-mandate` comes from the team's "Ask First for Alexa+" entry, so only the PayPal mapping is new idea-wise. | I S G |
| W13 | **Latent live-path bugs** (see section 5: B1-B3) would surface on the first sandbox recording. | P |
| W14 | **Latin American adoption blockers are not addressed.** Patients there often pay with Pix, OXXO, SPEI or Mercado Pago rather than PayPal. PayPal's fixed fee is a large share of a $10 capture. WhatsApp is only simulated. | B |
| W15 | **Holds expire after 29 days.** An authorization cannot secure a booking further out, and there is no Vault or card-on-file path. | P |
| W16 | **It lacks consumer "wow".** It reads as back-office governance next to flashy shopping assistants. | G |
| W17 | **Repository hygiene.** Internal Spanish work orders (`docs/encargos/*`, `_sesion/entendido.md`) and self-critical reviews (`JUDGE_REVIEW*.md`) are tracked and will be public. | S |

## 4. Improvements, ranked by score gain per hour

These merge 30+ proposals from the 7 judges. Hours and deltas are a consensus: where judges
differed, the value is the midpoint, rounded conservatively. "Delta" is the expected change in
the summed /50 score from an average judge. Deltas overlap, so do not add them all up. Ratio is
delta divided by hours. Item 1 comes first whatever its ratio, because it removes disqualification
risk.

| Rank | Improvement | Hours | Criterion | Delta (/50) | Ratio | Proposed by |
|---:|---|---:|---|---:|---:|---|
| 1 | Submission compliance and hygiene | 0.5 | Eligibility, Presentation | DQ risk removed, +0.5 | gate | P I B U S C G |
| 2 | Business-first pitch with qnowa's real numbers | 1.5 | Impact, Presentation | +2.0 | 1.33 | P I B U S C |
| 3 | Owner card a real owner can decide from | 1.5 | Design (+ Impact) | +1.25 | 0.83 | P I B U S |
| 4 | Position against AP2/ACP: "seller-side mandates", toolkit as complement | 1.25 | Innovation (+ Tech) | +1.0 | 0.80 | P I B U S G |
| 5 | Re-cut the video script for a cold viewer | 2 | Presentation | +1.5 | 0.75 | B U S |
| 6 | "Today" panel plus AG Grid totals row | 3 | Impact, Design (+ AG Grid odds) | +2.0 | 0.67 | B G (+ story selectors) |
| 7 | Localize: Spanish booking line, MXN deposit | 2.5 | Impact, Design | +1.5 | 0.60 | B (+ all 3 story selectors for the Spanish line) |
| 8 | Live-path fixes, then live sandbox and Claude run, then record and upload | 2 + 5 = 7 | Tech, Presentation | +3.5 | 0.50 (mandatory) | P I B U S C G |
| 9 | Make AG Grid visible: seeded week, filter, detail, CSV shot | 1 | Design (+ AG Grid odds 15% to 25%) | +0.5 | 0.50 | S C G |
| 10 | Separate the personas: demo drawer, no AUTH ids for customers, chat styled as a phone thread | 2 | Design | +1.0 | 0.50 | U G |
| 11 | The agent applies a written policy; buttons report only facts | 5 | Innovation, Tech, Design | +2.0 | 0.40 | I |
| 12 | Hosted demo on Render with a per-visitor shop | 3 | Design, Presentation (+ Render prize) | +1.0 | 0.33 | P S G |
| 13 | Standing mandates (owner signs a policy once) | 6.5 | Innovation, Impact, Design | +2.0 | 0.31 | I B |
| 14 | Read-only PayPal Agent Toolkit/MCP tools, money tools only behind the gate | 5 | Tech, Innovation (+ PayPal + AI odds) | +1.5 | 0.30 | P |

Item 8 has a lower ratio than items 2-7, but **it is required**: without a YouTube video the entry
is not eligible, and without live runs W1 caps three criteria. Do the 2 h of fixes on day 1 and
the live run on day 2, so the recording uses the final UI. Items 1-8 add up to about 19 h.

### Acceptance checks

Run every command from the repository root.

1. **Submission compliance and hygiene (0.5 h).** In SUBMISSION_CHECKLIST.md:17, require "YouTube,
   publicly visible" only. Delete README.md:3. Untrack `_sesion/`, `docs/encargos/`, `docs/PR_N*.md`,
   `docs/JUDGE_REVIEW*.md`, `docs/JUDGE_PANEL_*.md`, `docs/STORY_VARIANTS_*.md` and
   `docs/CONTRACT*.md`. Make the repository public with Apache-2.0 detected.
   - `grep -nE 'Vimeo|Youku|unlisted' docs/SUBMISSION_CHECKLIST.md` prints nothing.
   - `grep -c 'private until submission' README.md` prints `0`.
   - `git ls-files _sesion docs/encargos 'docs/PR_N*' 'docs/JUDGE_*' 'docs/STORY_*' | wc -l` prints `0`.
   - `gh repo view cleveria-ai/ask-first-pay --json visibility,licenseInfo` shows `PUBLIC` and `Apache-2.0`.
2. **Business-first pitch (1.5 h).** Rewrite the first screen of DEVPOST.md and shot 1 around qnowa:
   name the company, its Latin American clinic and salon customers, and the measured no-show rate
   and typical deposit, each with its source. Push mandate, authorize, void, idempotency, Ed25519
   and hash chain below the fold. Use only real figures.
   - `sed -n 1,25p docs/DEVPOST.md | grep -ciE 'mandate|authoriz|idempoten|Ed25519|hash-chain|CHECKOUT\.ORDER'` prints `0`.
   - `sed -n 1,25p docs/DEVPOST.md | grep -cE 'qnowa|[0-9]+ ?%'` prints `2` or more.
   - Shot 1 in `docs/VIDEO_SCRIPT.md` names Latin American clinics or salons.
3. **Owner card (1.5 h).** Show the customer name and the slot, looked up on the server from the
   booking that owns the signed resource (never taken from model text). Show the expiry as
   relative local time. Move `capture_deposit on AUTH-…`, the unix time and the key fingerprint
   into a details element. Make Approve/Decline sticky under 900 px. Read the customer name from
   the message instead of `customer="Customer"`.
   - `grep -n 'unix time' src/ask_first_pay/gate.py` prints nothing.
   - Run `.venv/bin/python scripts/screenshots.py`. In `docs/screenshots/05-owner-mobile.png`,
     Approve is fully visible within 375x812, and the card shows a name and `Mon 16 Nov 09:00`.
   - `.venv/bin/python -m pytest -q` stays green.
4. **Positioning (1.25 h).** Add a five-row table to DEVPOST.md comparing AP2 Intent/Cart Mandate,
   the ACP Shared Payment Token, PayPal/Stripe agent toolkits, MCP elicitation/LangGraph
   interrupt, and Ask First Pay. Lead with "AP2 and ACP govern what a buyer's agent may spend;
   Ask First Pay governs what a seller's agent may take after the sale." Rewrite the toolkit
   decision as "complements PayPal's agent toolkit".
   - `grep -nE 'AP2|Agentic Commerce Protocol|seller-side' docs/DEVPOST.md | wc -l` prints `3` or more.
   - At least one of those lines falls within the first 15 lines.
5. **Video script re-cut (2 h).** Cut shot 2 (the ASCII diagram) and shot 8 (the duplicate
   ledger). Give the approval tap 8-10 s. Define "mandate" once. Remove the jargon from the
   narration. Label the second customer. Follow the founder story in
   `docs/STORY_VARIANTS_2026-11.md`.
   - `.venv/bin/python scripts/check_video_assets.py` prints OK, with a total of 170 s or less.
   - `grep -ciE 'AUTHORIZE|idempotency|webhook' docs/video/subtitles.srt` prints `0` (PayPal terms go in the caption track only).
   - No shot shows the README diagram.
6. **"Today" panel and grid totals (3 h).** Build it on /owner from bookings and the ledger, never
   from model text: holds, $ kept, $ released, $ given back, owner taps, refused attempts, and
   "$0.00 moved without your signature". Add an AG Grid pinned bottom totals row on /ledger that
   follows the filters.
   - After the README 60-second path, `curl -s localhost:8000/owner` contains `Recovered` with
     `10.00` and an approvals count of `2`.
   - A new test in `tests/demo/` asserts these values come from the ledger.
   - Clicking the Rejected filter changes the pinned totals.
7. **Localization (2.5 h; the Spanish line alone is 0.25 h).** Add "Reply in the customer's
   language" to SYSTEM. Add `ASK_FIRST_CURRENCY` and `ASK_FIRST_DEPOSIT`, used only if the sandbox
   confirms MXN authorize, capture and void.
   - `ASK_FIRST_CURRENCY=MXN ASK_FIRST_DEPOSIT=200 scripts/demo.sh`, then the chat shows `MXN 200.00` held.
   - `pytest -m live` with MXN passes create, authorize, capture and void against api-m.sandbox.paypal.com.
8. **Live path, run and record (7 h).** First fix B1-B3 and B5-B6 from section 5. Then run with
   `PAYPAL_CLIENT_ID/SECRET`, `PAYPAL_WEBHOOK_ID` (through a tunnel) and `ANTHROPIC_API_KEY`.
   Record on the current UI. Upload to YouTube, public.
   - New offline test: two `PayPalProvider` instances calling `create_order(10.0, 'USD', 'booking-1')`
     send different `PayPal-Request-Id` headers. The body contains
     `payment_source.paypal.experience_context.return_url` and `shipping_preference == 'NO_SHIPPING'`.
   - A mocked 422 on reauthorize makes `refresh_hold` return an error, and no mandate is requested.
   - `.venv/bin/python -m pytest -m live -q` passes.
   - `curl -s localhost:8000/webhooks/paypal/events` lists a real event with `simulated: false`.
   - `yt-dlp --print duration --print availability <url>` prints less than 180 and `public`.
   - Frames show sandbox.paypal.com and the "PayPal sandbox" chip. No frame shows "offline scripted model", "FakeProvider", "Claude" or "AG Grid" (see D5).
9. **AG Grid visible (1 h).** Seed about 30 rows for one clinic week. Add a 6-8 s ledger shot
   (filter Rejected, open a row's detail, Download CSV). Name AG Grid in the Devpost text only.
   - `grep -ci 'AG Grid' docs/DEVPOST.md` prints `1` or more.
   - The video shows 20 or more ledger rows with an active filter, and no "AG Grid" caption.
10. **Personas (2 h).**
    - `grep -c 'Act as the business' src/ask_first_pay/demo/templates/chat.html` prints `0`.
    - After the booking flow, `curl -s localhost:8000/chat | grep -c 'AUTH-'` prints `0`.
11. **Policy judgment (5 h).**
    - `grep -rn 'Ask the owner to capture' src/` prints nothing.
    - A test sends a fact-only late cancellation and gets a `request_capture` for 5.00 whose plan
      hash is the sha256 of the policy clause.
    - The /owner HTML shows the clause.
12. **Render (3 h).**
    - `curl -s https://<app>.onrender.com/healthz` returns `{"ok":true}`.
    - Two browsers each complete book, hold, no-show and approve without seeing each other's mandates.
    - The README's first 10 lines contain the URL.
13. **Standing mandates (6.5 h; only after items 1-8).** A test runs two $10 no-shows under one
    signed standing mandate with zero /owner approvals, then a $15 one.
    - The $15 capture stays pending.
    - The executed rows carry the standing jti.
    - Replays are rejected.
    - The chain check stays intact.
14. **Toolkit read-only (5 h).**
    - `grep -rnE 'paypal-agent-toolkit|@paypal/mcp|paypal_agent_toolkit' pyproject.toml src` prints something.
    - A test asserts the model's TOOLS have no ungated `pay_order` or `create_refund`.
    - The video or a GIF shows a sandbox `list_transactions` answer.

## 5. Bugs found in the code (re-checked on `57fb354`)

The judges' line numbers came from a review copy and some do not match `57fb354` (for example
"tools.py:292" in a 165-line file). The lines below are the current ones. Status: **verified**
means confirmed by reading the code, and by an offline reproduction where noted. **Not
reproduced** means the code is as described, but the claimed effect needs a live key to show.

| # | Bug | Where | Status | From |
|---|---|---|---|---|
| B1 | **The create_order PayPal-Request-Id collides across conversations and restarts.** The id is `sha256("create_order"\|reference\|value\|currency)` with `reference = booking-N`. Booking ids restart at `booking-1` in every `AgentState`, and the demo opens new conversations (`front.new_conversation`, used by app.py:262). Live, PayPal would replay the first conversation's order to the second one. | `src/ask_first_pay/paypal/provider.py:129-130`, `src/ask_first_pay/agent/tools.py:72`, `src/ask_first_pay/demo/front.py:68-72` | **verified**. With MockTransport, two fresh providers both sent `a03d465aec719310dc4c0d96839032d2078b`. | P |
| B2 | **The order body has no `payment_source.paypal.experience_context`**: no return_url, no cancel_url, no `shipping_preference: NO_SHIPPING`, no user_action. The payer may be asked for a shipping address for a deposit, and nothing brings them back to the app (hence README "tell the chat you approved it"). | `src/ask_first_pay/paypal/provider.py:127-128` | **verified** that it is missing (grep finds none in `src/`). The payer-side effect is **not reproduced** live. | P |
| B3 | **`refresh_hold` reports every non-transient PayPal error as "the current hold is still valid"**, including a voided, expired or already-reauthorized authorization. The offline model then asks the owner to sign a capture that cannot run. | `src/ask_first_pay/agent/tools.py:99-105`, `src/ask_first_pay/demo/offline_model.py:139-141` | **verified**. A mocked 422 returned `{'refreshed': False, ..., 'reason': 'UNPROCESSABLE_ENTITY: the current hold is still valid, capture it as is'}`. | P |
| B4 | **FakeProvider.create_order takes no request id and has no idempotency**, so the offline suite cannot catch B1. | `src/ask_first_pay/fake_provider.py:52-57` | **verified** | P |
| B5 | **FakeProvider refuses a capture after the 3-day honor period** (`HONOR_PERIOD_EXPIRED`). Real PayPal still allows a capture within 29 days; it only stops guaranteeing funds. Narration copied from the fake would overclaim. | `src/ask_first_pay/fake_provider.py:105-106` | **verified** (code). The PayPal behaviour comes from PayPal's docs, **not reproduced** live. | story selectors (PayPal, skeptic), V4 risks |
| B6 | **The Claude loop is set up in ways never tested live.** It uses `max_tokens=1024` and keeps only `text`/`tool_use` blocks in history (thinking blocks would be dropped if the model returns them). The default model id `claude-sonnet-5-5` has never been called. | `src/ask_first_pay/agent/loop.py:38`, `:45`, `:47-48` | Code **verified**; the impact is **not reproduced** (no live key) | P S |
| B7 | **The owner card prints raw unix time**: "expires at 1793855593 (unix time)". The other times are UTC only. | `src/ask_first_pay/gate.py:91-92`, rendered at `src/ask_first_pay/demo/templates/owner.html:42`; `src/ask_first_pay/demo/app.py:308,312` | **verified** (also visible in `docs/screenshots/02-owner-approval.png`) | P I B U S |
| B8 | **The owner card never names the customer or the appointment.** The offline model books everyone as `customer="Customer"`, and `mandate_rows` never looks up the booking. | `src/ask_first_pay/demo/offline_model.py:108`, `src/ask_first_pay/demo/app.py:42-44,305-314` | **verified** | U |
| B9 | **On a 375 px phone, Approve is below the fold.** A banner, the Ed25519 "Paired" card and the details box come first. | `src/ask_first_pay/demo/templates/owner.html:10,44`; `docs/screenshots/05-owner-mobile.png` | **verified** (screenshot) | U |
| B10 | **The Cancellation scenario posts "I need to cancel, sorry." as the customer ("You") in the current thread**, even when the scenario created a booking for a different visit. | `src/ask_first_pay/demo/app.py:279-283` → `src/ask_first_pay/demo/front.py:117-122` | **verified** (UX). The suspicion that the wrong booking gets voided is **not reproduced**: the offline model voids the latest held booking of the same conversation (`offline_model.py:98-102`), which is the scenario's booking. | U |
| B11 | **The No-show button tells the agent what to do** ("… did not show up. Ask the owner to capture the deposit."), so the agent makes no judgment. | `src/ask_first_pay/demo/front.py:149` | **verified** (design limitation) | I S |
| B12 | **Mandates expire after 15 minutes**, too short for an owner who is with a patient. | `src/ask_first_pay/gate.py:74` (`ttl_s=900`) | **verified** (product issue) | B |
| B13 | **`request_void` does not require `status == deposit_held`.** After a capture, the agent can still ask the owner to void the captured authorization, and PayPal would refuse it. | `src/ask_first_pay/agent/tools.py:136-140` (compare `request_capture` at :129) | **verified** by reading; found during this re-check, **not reproduced** against PayPal | panel synthesis |
| B14 | **Deposit and currency are hard-coded** (10.00 USD for every shop and service); the business name is hard-coded too. | `src/ask_first_pay/agent/tools.py:15-16`, `src/ask_first_pay/agent/loop.py:11-12`, `src/ask_first_pay/demo/front.py:25` | **verified** | B |
| B15 | **The live UI puts third-party marks on screen**: `Agent model: Claude` and "Table: AG Grid Community". | `src/ask_first_pay/demo/templates/chat.html:32`, `owner.html:80`, `ledger.html:50` | **verified** (see D5) | U S, all 5 story variants |
| B16 | **The submission docs are wrong**: the checklist allows Vimeo, Youku or unlisted, and the README still says private/WIP. | `docs/SUBMISSION_CHECKLIST.md:17`, `README.md:3` | **verified** | all |
| B17 | **The raw clips were recorded on the pre-N6 UI.** | `docs/PR_N6_design.md:95-96`, `docs/video/raw/*` | **verified** (the doc says so) | U S |

Claims checked and found **correct**: `DEVPOST.md:117` "387 automated tests" (387 passed,
1 deselected on `57fb354`); same-id retries in `gate.py:42-53`; webhook verification as
described in `README.md:151-156`.

## 6. Disqualification risks

Rule line numbers refer to `docs/rules/rules_2026-11-03.txt`. That file is ignored by git, so read
it in the main checkout.

| # | Risk | Rule | Status on `57fb354` | Fix |
|---|---|---|---|---|
| D1 | **The video must be "uploaded to and made publicly visible on YouTube".** SUBMISSION_CHECKLIST.md:17 says "YouTube, Vimeo or Youku, public or unlisted". Vimeo, Youku or an unlisted upload could be ruled non-compliant. | line 175 | **verified mismatch** | Improvement 1. YouTube public only. |
| D2 | **The video must be under 3 minutes** ("Judges are not required to watch beyond three minutes"). The script runs 2:40; live latency can push it past. | line 173 | Not recorded yet | Hard cap of 2:50 in the edit. Cut silences; never speed up the voice. |
| D3 | **Public repository with an open-source license visible in About.** The repository is private, and README.md:3 says "private until submission". | lines 169-171 | **Not met yet** (owner task) | Improvement 1 |
| D4 | **The entry "must function as depicted in the video and/or text".** It also needs a functional demo (a non-functional demo "does not meet this requirement"). The text claims sandbox and Claude paths that have never run, and B1-B2 would break a judge's sandbox run. | lines 154, 165-168 | Risk | Improvement 8. Or keep the `Simulated PayPal` / `offline scripted model` labels visible if recording offline. |
| D5 | **No third-party trademarks in the video.** The live chat chip says `Agent model: Claude`; owner and ledger pages say "AG Grid Community". DEVPOST says "WhatsApp-style" and mentions "Alexa+". Browser and OS chrome also count. | line 176 | Risk when recording live | Env flag for a video-safe label ("live LLM, tool use"), hide the AG Grid caption, no browser chrome. Name Claude and AG Grid only in the text. |
| D6 | **Prior work / significant update.** `libs/ask-first-mandate` was written on 2026-10-17 for "Ask First for Alexa+" and ports code from `soyharso/agent-identity-firma`. It is disclosed at README.md:184-192. If both entries were in this hackathon, they would have to be "substantially different". The Devpost text must explain the new work. | lines 157-158, 178, 190 | Disclosed; low risk | Paste the disclosure into the Devpost form. Confirm the Alexa+ entry belongs to a different hackathon and that no rights went to Amazon. |
| D7 | **Eligibility by residence.** Residents and organizations domiciled in Brazil or Quebec are excluded. qnowa works in Latin America. | line 115 | Owner to confirm | Confirm that the Representative and the entering organization are not in Brazil or Quebec. |
| D8 | **All submission materials in English.** Spanish files are tracked (`_sesion/entendido.md`, `docs/encargos/*`). A Spanish line in the video needs burned-in English subtitles. | line 186 | Low risk | Improvement 1, plus subtitles |
| D9 | **Form completion.** Owner tasks are still open: join, accept the rules, upload, submit, invite team members (SUBMISSION_CHECKLIST.md:11-19, 38-42). | n/a | Open | Submit by 2026-11-11, one day early. |

## 7. Per-judge notes worth keeping

- **PayPal DevRel (28):** "A PayPal judge never sees PayPal." Wants a live sandbox, the
  experience_context fix, AP2 positioning and some use of PayPal's agent stack (read-only toolkit
  or MCP tools, money tools only behind the gate).
- **Innovation (31):** the real novelty is **seller-side** mandates over the post-authorization
  lifecycle (AP2 and ACP cover the buyer side). Make the agent apply a written policy so there is
  something for it to judge.
- **Business (29):** Impact 4/10. Wants qnowa's numbers, a "this month: X recovered" outcome,
  standing mandates to remove the owner bottleneck, and MXN/Spanish. Points out that PayPal is a
  niche way to pay a clinic deposit in Latin America.
- **UX / demo (28):** the money shot is buried. The approval card is on screen for about 3 s in
  `raw/04-no-show.webm`, with Approve clipped. Recommends 8-10 s on the tap and separate personas.
- **Skeptic (26):** the first 60 s read as a mockup (title card, ASCII diagram, regex bot). Clean
  the repository before it goes public. Check the Brazil exclusion.
- **codex (35):** a conservative ranking: record the video first (4-6 h), then the live run, then
  the public repository, then the evidence-based impact paragraph, then AG Grid visibility. Its
  checks allow "public or unlisted", which conflicts with rule line 175: follow the rule.
  References, translated from its review copy to repository paths: `docs/DEVPOST.md:39`,
  `docs/video/SHOTLIST.md:29`, `gate.py:42-52`, `docs/JUDGE_REVIEW_N6.md:63`,
  `docs/DEVPOST.md:65-70`, `docs/DEVPOST.md:7-15`, `gate.py:14-18`, `docs/VIDEO_SCRIPT.md:17-25`,
  `docs/video/SHOTLIST.md:7`, `docs/SUBMISSION_CHECKLIST.md:16-18`,
  `docs/rules/rules_2026-11-03.txt:213,297`, `README.md:61-66,175-182,184-192`,
  `docs/SUBMISSION_CHECKLIST.md:11-19,38-42`.
- **gemini (37):** the most optimistic judge (Agentic Commerce 60%, AG Grid 65% for any place).
  Its useful ideas: present the toolkit decision as thought leadership ("Hold vs Move"), a
  WhatsApp-like chat skin (but do not name WhatsApp on screen; see D5), Render, and AG Grid pinned
  totals with a KPI bar. Its "uploaded to YouTube/Vimeo" check conflicts with rule line 175.
  Evidence it cited: `src/ask_first_pay/gate.py:12,44`,
  `src/ask_first_pay/agent/tools.py:90` (refresh_hold is now at :92),
  `src/ask_first_pay/demo/app.py:180`, `src/ask_first_pay/demo/static/grid.js:40`,
  `docs/DEVPOST.md:12`, `docs/video/SHOTLIST.md:12`.
