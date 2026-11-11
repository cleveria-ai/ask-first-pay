# Ask First Pay

**Tagline:** "Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it.

## Inspiration

I run qnowa: booking with deposits for clinics and salons in Latin America. Deposits are how a
small clinic protects itself from empty chairs. When we talk about letting an AI answer the front
desk, the first thing owners ask is: can it touch my money?

It is a fair question. Deposits create a daily job: someone decides whose deposit to keep after a
no-show, whose to release after a cancellation, and who gets something back as a kindness. In a
small clinic that someone is the owner, on her phone, between patients. An AI could take the
routine work off her hands, but the danger is not a hacker. It is an assistant too kind to say no.

So we built the answer into the product, designed for qnowa's clinics: **it can hold it; only you
can move it.**

## What it does

- **For the customer:** she books a visit in the chat (English or Spanish) and leaves a deposit
  on PayPal. It is held, not charged. The AI does this on its own, because a hold moves nothing.
- **For the owner:** to keep, release or give back a deposit, the AI can only ask. Her phone shows
  what she would sign ("Keep up to $10.00 of the held deposit", the customer's name and visit),
  never the AI's own words. One tap approves it: one tap, one PayPal call, once.
- **At closing:** the phone's Today panel shows what the AI did on its own, the owner's taps, the
  money kept, released and given back, and "$0.00 moved without your signature", counted from a
  tamper-evident record anyone can check.
- **Under the hood** (the rest of this page): the AI creates PayPal orders with intent
  **AUTHORIZE** and, when PayPal's signed `CHECKOUT.ORDER.APPROVED` webhook says the customer
  approved, authorizes them: the 10.00 deposit is **held, not charged**. When money has to move:
  - **No-show:** it requests a `capture_deposit` mandate for that authorization and amount. If
    the visit is more than three days after the booking (past PayPal's honor period), it first
    reauthorizes the hold, so the owner signs for the live authorization.
  - **Cancellation:** it requests a `void_deposit` mandate; the hold is released and nothing is
    charged or refunded. The owner's card says "Moves $0.00 · releases the $10.00 hold".
  - **Goodwill:** after a capture, when the customer explains a missed visit and asks for the
    deposit back, it requests a `refund_deposit` mandate and promises nothing.
- The owner's card is built from the mandate's signed fields, and the phone signs the mandate with
  a non-extractable Ed25519 key that never leaves the browser.
- Only then does the gate call PayPal, once, with the mandate's id as `PayPal-Request-Id` (shown
  on the owner's card as "Approval id … (sent to PayPal as PayPal-Request-Id)" and next to the
  capture id PayPal returned in the ledger). Approving twice, replaying, changing the amount or
  target, an expired mandate, or a customer typing "the owner approved" are all rejected, and
  every attempt (accepted or rejected) is appended to a hash-chained ledger whose chain check is
  shown on screen.

## How it differs

**AP2 and ACP govern what a buyer's agent may spend. Ask First Pay governs what a seller's agent
may do with the money after the sale.** It is seller-side: the mandate is signed by the business
owner, not the shopper, and it covers the post-authorization lifecycle (capture, void, refund)
that buyer-side protocols leave to the merchant.

| | Who signs | Whose agent | What it governs |
|---|---|---|---|
| **AP2**, Agent Payments Protocol (Google, announced 2025-09-16) | The user: an Intent Mandate up front ("Buy concert tickets the moment they go on sale"), a Cart Mandate when approving a cart | The shopper's agent | Buying: what the agent may purchase for the user |
| **ACP**, Agentic Commerce Protocol (developed by Stripe and OpenAI, Apache-2.0) | Payment tokens passed between buyer and business through the agent; the business stays merchant of record | The shopper's agent, which starts a checkout | Checkout: how an agent pays a business |
| **PayPal's agent toolkit** (`@paypal/agent-toolkit`, `paypal-agent-toolkit`) | Nobody: tools such as `create_order`, `pay_order`, `create_refund` are called by the model | Any agent | Calling PayPal APIs from a model. Ask First Pay complements it: the same PayPal APIs, with the money-moving calls placed behind an owner's signature (`docs/agent_toolkit_decision.md`) |
| **Ask First Pay** | The business owner, on her phone: one **single-use, seller-side mandate** per action, scoped to one PayPal resource, capped, expiring | The seller's agent (the front desk) | After the sale: **holds are free** (create order, authorize, reauthorize); **captures, voids and refunds need a mandate**, and the mandate's id becomes PayPal's `PayPal-Request-Id`, so one approval is one PayPal call |

Sources: AP2, https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol
(read 2026-11-10); ACP, https://www.agenticcommerce.dev/ (read 2026-11-10); the toolkit's tool
list, its npm and PyPI pages as recorded in `docs/agent_toolkit_decision.md` (2026-11-04).

The two sides fit together: a shopper's agent can pay with an AP2 or ACP mandate, and the
clinic's agent still cannot keep, release or refund that money without the owner's own mandate.

## Proven on the real PayPal sandbox

On 2026-11-11 the same gate and the same adapter ran against the real PayPal sandbox.
`scripts/sandbox_run.py` created two USD 10.00 orders with intent AUTHORIZE, a sandbox buyer
approved them in the browser, and then:

| Step | What PayPal answered |
|---|---|
| No-show: authorize order `5WF1406594379682R`, then capture through an owner-approved mandate | capture `998786236C479363B`, `COMPLETED` (HTTP 201) |
| The same capture sent again with the same `PayPal-Request-Id` (the mandate's id) | the **same** capture `998786236C479363B` (HTTP 200): PayPal did not charge twice |
| The agent replays the spent mandate at our gate | refused (`replay`) before any PayPal call |
| Cancellation: authorize order `4BB42998PV419681V`, then void through its own mandate | authorization `63A502184W936794R`, `VOIDED` (HTTP 204): nothing charged |

Then the product itself ran there: three fictional customers booked in the demo's chat, a sandbox
buyer approved each deposit on PayPal's own sandbox page, and each request was approved on the
owner's page with the real WebCrypto signature. The run is scripted (`scripts/sandbox_ui_run.py`
drives the pages in headless Chromium; the phone pictures are that same page at 375 px):

| Story | On the owner's page | What PayPal answered |
|---|---|---|
| No-show (Lucía) | one Approve on "Keep up to $10.00 of the held deposit" | capture `7YN16151ST920971N`, `COMPLETED`; the agent's replay of that mandate was refused at the gate |
| Cancellation (Mateo) | one Approve on the void card | authorization `8K576667JA748733C`, `VOIDED`: $0.00 moved |
| Goodwill (Sofía) | one Approve to keep the deposit, a second to give it back | capture `5LP876075J833584E`, then refund `0CE05358RE990873D`, `COMPLETED` |

Before each no-show capture the agent asked PayPal to refresh the hold. PayPal answered 422, and
the agent went on with the hold it had, which PayPal then captured.

The full records, with every HTTP call's method, path and status (never tokens or headers), are
`docs/SANDBOX_RUN.md` and `docs/SANDBOX_UI_RUN.md`; the screens are `docs/screenshots/12-sandbox-*.png`
(the chip reads "PayPal sandbox", the ledger shows PayPal's ids); `tests/test_sandbox_evidence.py`
keeps these tables and those records in step. In these runs the agent was the offline scripted
model, and PayPal's webhook was not used (the buyer's return to the site confirmed the hold). The
demo and the video run offline by default (scripted model, simulated PayPal) and say so on screen,
so anyone can run them without keys; the video adds one still of the sandbox ledger
(`docs/screenshots/12-sandbox-ledger.png`), labelled as a screenshot.

## How we built it

- **PayPal APIs:** Orders v2 (`POST /v2/checkout/orders` with intent AUTHORIZE, `.../authorize`),
  Payments v2 (`/v2/payments/authorizations/{id}/capture`, `/reauthorize`, `/void`,
  `/v2/payments/captures/{id}/refund`, plus GETs), and OAuth 2.0 client credentials
  (`/v1/oauth2/token`). Written against the **sandbox** with `httpx`; production is refused unless
  explicitly enabled. Every write sends `PayPal-Request-Id`, amounts go as two-decimal strings,
  timeouts and 5xx become transient errors, and the gate retries them with the same request id,
  so a capture that timed out after PayPal took the money is answered, not repeated.
- **AI:** Anthropic **Claude** (Messages API with tool use; model id `claude-sonnet-5-5` by
  default, `ASK_FIRST_MODEL` overrides it) drives the agent when an API key is set. Ten tools: six free (book, create the deposit order, confirm the hold, refresh an old hold
  by reauthorizing it, list bookings, read the ledger) and four gated (request capture, request void, request refund, execute an
  approved mandate). Without a key, an offline scripted model drives the same loop and tools, so
  anyone can run the demo.
- **Mandate engine:** our Apache-2.0 library `ask-first-mandate` (single-use, scoped, capped,
  expiring mandates signed with Ed25519; RFC 8785 canonical JSON; hash-chained JSON-lines ledger).
- **The gate:** the agent receives two narrow handles: `AgentGate` (request, execute, describe,
  view ledger) and `HoldDesk` (create order, authorize, reauthorize). It never receives the
  engine, the PayPal client or the owner's side, so none of the model's tools reaches capture,
  void or refund except through an approved mandate. The gated tools also refuse to ask for more
  than is held (capture) or still captured (refund), so the owner is never shown an inflated
  number to approve.
- **Webhooks:** `/webhooks/paypal` verifies each delivery locally the way PayPal signs it
  (SHA256withRSA over transmission id, time, webhook id and the body's CRC32, certificate only
  from `*.paypal.com`, 5-minute window, each event and each transmission accepted once). A webhook can make the agent hold a
  deposit; it can never capture, void or refund. Offline, a local simulator plays PayPal.
- **Persistence:** optional SQLite (`ASK_FIRST_DB`), one row per shop, so a restart keeps
  bookings, signed approvals and the set of used mandates (a restart cannot reopen a replay).
- **Demo:** FastAPI + Jinja pages (chat, owner phone, ledger), WebCrypto for the owner's key,
  AG Grid Community for the ledger and the owner's mandate list (see *Built with AG Grid*), one
  set of design tokens checked for 4.5:1 contrast in light and dark mode, 44 px touch targets,
  and a "what just happened" line after every action. No CDN.
- A fake PayPal provider follows the same rules (3-day honor period, 29-day expiry, idempotent
  request ids) and a contract test runs the same story against it and the real adapter.

## Built with AG Grid

The owner's mandate list (`/owner`) and the ledger (`/ledger`) are AG Grid Community 36.3.0
grids, vendored and served locally (`src/ask_first_pay/demo/static/vendor/`, MIT license file
alongside, no CDN). Setup in `src/ask_first_pay/demo/static/grid.js`; every feature used is in
the free Community edition:

- **Sorting** on every column (the ledger opens newest first; shift-click for multi-column).
- **Filtering**: text and number column filters, **external filters** wired to the
  *Executed / Rejected* and *Capture / Void / Refund* buttons (and *Pending / Used / Declined*
  on the owner page), and the **quick filter** behind the search box.
- **Status cells** via `valueGetter` and `cellClass`: result and state read as colored chips
  (`rejected · replay` in red, `executed` in green, `pending` in amber) while every cell value stays
  plain text: no cell renderers, no HTML from data (`tests/security` checks it).
- **Row selection driving a detail panel**: tap or press Enter on a row to see the signed fields
  (jti, action, recipient, cap, expiry, issuer, plan hash) and the chain link (`hash`, `prev`,
  links to the raw row `/ledger/entry/<n>` and the previous one). On the owner page it shows the exact canonical bytes the phone signs.
- **CSV export** of the ledger (`exportDataAsCsv`), the **Theming API** (`themeQuartz.withParams`)
  fed from the page's own color tokens in light and dark mode, 44 px rows, `ensureDomOrder` and
  keyboard navigation. On a phone the grid keeps four columns and the rest moves to the detail.
- The server-rendered table stays underneath as the no-JS fallback.

## Challenges we ran into

- Choosing the PayPal lifecycle. A deposit that is captured up front means every cancellation is
  a refund; AUTHORIZE-then-capture lets a cancellation be a void, which moves no money. A void is
  still consequential (it releases the hold), so it also needs the owner, with a symbolic 0.01 cap.
- Making "approve" mean exactly one thing. The mandate binds action, PayPal resource, amount cap
  and expiry, and its id is reused as PayPal's idempotency key, so even a network retry cannot
  turn one approval into two captures.
- Keeping the model's words out of the owner's decision: the approval screen is rendered only
  from signed fields.
- Fitting PayPal's agent toolkit. Its tool list (as of 2026-11-04) has `pay_order` and
  `create_refund` as plain model tools and no authorize, capture or void, so we wrote a narrow
  adapter for the hold lifecycle and kept money-moving calls behind the owner's mandate. It
  complements the toolkit rather than replacing it (`docs/agent_toolkit_decision.md`).

## Accomplishments that we're proud of

- It works against PayPal for real: one owner approval became exactly one sandbox capture
  (`998786236C479363B`), the retry with the same `PayPal-Request-Id` returned that same capture,
  and a cancellation became a void (`63A502184W936794R`). The three stories also ran end to end
  through the product's own screens, refund included. See *Proven on the real PayPal sandbox*.
- The agent cannot move money on its own through any tool it holds: the tests use a spy provider
  and an injected "owner approved" message and assert that nothing moved. A decline is final and
  a second approval is refused.
- Replays and forged approvals are rejected in plain sight on the ledger page, with an intact
  chain check.
- The whole demo runs in two minutes with no keys, and the same code switches to Claude and the
  PayPal sandbox by setting environment variables. The video is recorded from that offline demo
  (scripted model, simulated PayPal) and says so on screen, plus one still screenshot of the
  ledger after the sandbox run; the business and customers are
  fictional, and the video shows no brand but PayPal's.
- 545 automated tests (2026-11-11), all offline, including the attacks listed under "Try to break it"
  in the README.

## What we learned

- Authorization holds (honor period, reauthorization, expiry) are a natural fit for agents: the
  agent can safely do everything up to the hold and the human only decides at the moment money
  moves.
- Idempotency keys are a security feature, not just a reliability one, when they are tied to a
  single-use approval.
- Capability design beats prompt design: the system prompt asks the model to behave, but the
  guarantee comes from what objects the model can reach.

## What's next

- A real WhatsApp Business channel instead of the simulated chat.
- Run the webhook path against the live sandbox certificate (it is verified offline today).
- Several shops behind one deployment, with a login per owner (the SQLite store already keys
  everything by shop).
- A daily sweep that reauthorizes holds before the 29-day expiry, and reminders to the owner.
- Per-owner policies (for example "approve no-show captures under 20.00 automatically") expressed
  as standing mandates with their own cap and expiry.

## Prior work

- New for this hackathon: everything under `src/ask_first_pay/` (the PayPal adapter for Orders v2
  and Payments v2, the gate that puts capture, void and refund behind a mandate, the agent and
  its ten tools, webhook verification, the demo pages) and its tests.
- Reused: our own Apache-2.0 library `libs/ask-first-mandate` (single-use signed mandates,
  hash-chained ledger, receipts). We created it on 2026-10-17, inside this submission period, for
  our "Ask First for Alexa+" entry. Its identity signing and ledger were ported from our earlier
  public repository `soyharso/agent-identity-firma` (August 2026) and extended; the single-use
  mandate is new in that library. Nothing in it knows about PayPal.
- Third party: AG Grid Community 36.3.0 (MIT), vendored unmodified.

## Screenshots (image gallery)

All from the offline demo in headless Chromium (`scripts/screenshots.py`), PNG.

| File | Size | Shows |
|---|---|---|
| `docs/screenshots/01-chat-booking.png` | 1280x720 | the customer books; the deposit is held on PayPal, not charged |
| `docs/screenshots/02-owner-approval.png` | 1280x720 | the owner's approval card ("Keep up to $10.00 of the held deposit", expires in 60 min, approval id = PayPal-Request-Id); the mandate grid beside it |
| `docs/screenshots/03-ledger-replay.png` | 1280x720 | the replay is rejected; ledger grid with status chips and the row's signed fields |
| `docs/screenshots/04-cancellation-voided.png` | 1280x720 | a cancellation approved: the hold is voided, nothing charged |
| `docs/screenshots/05-owner-mobile.png` | 375x812 | the owner's phone: the no-show card with Approve above the fold |
| `docs/screenshots/06-ledger-mobile.png` | 375x812 | the ledger grid and row detail on a phone |
| `docs/screenshots/07-chat-mobile.png` | 375x812 | the chat on a phone |
| `docs/screenshots/08-ledger-dark.png` | 1280x720 | the ledger in dark mode |
| `docs/screenshots/09-owner-void-mobile.png` | 375x812 | a cancellation card: "Moves $0.00 · releases the $10.00 hold" |
| `docs/screenshots/10-owner-today-mobile.png` | 375x812 | the Today panel at the end of the day: "$0.00 moved without your signature", computed from the ledger |
| `docs/screenshots/11-owner-today-dark.png` | 375x812 | the Today panel in dark mode |

From the run against the real PayPal sandbox (`scripts/sandbox_ui_run.py`), PNG:

| File | Size | Shows |
|---|---|---|
| `docs/screenshots/12-sandbox-chat-held.png` | 1280x720 | back from PayPal's sandbox page: the deposit is held, the chip reads "PayPal sandbox" |
| `docs/screenshots/12-sandbox-owner-approval.png` | 1280x720 | the owner's card for a real PayPal authorization |
| `docs/screenshots/12-sandbox-owner-mobile.png` | 375x812 | the same card on the phone |
| `docs/screenshots/12-sandbox-ledger-replay.png` | 1280x720 | the real capture executed once; the replay rejected |
| `docs/screenshots/12-sandbox-cancellation-voided.png` | 1280x720 | the cancellation: the real hold voided, nothing charged |
| `docs/screenshots/12-sandbox-ledger.png` | 1280x720 | the ledger after the three stories, with the PayPal refund id in the row detail |
| `docs/screenshots/12-sandbox-today-mobile.png` | 375x812 | the Today panel after the sandbox run |

## Built with

python, fastapi, jinja, httpx, sqlite, paypal-webhooks, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519,
webcrypto, ag-grid
