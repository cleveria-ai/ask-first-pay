# Ask First Pay

**Tagline:** An AI front desk that can take a PayPal deposit on its own, but has to ask before it moves a cent.

## Inspiration

Small service businesses (dentists, salons, physiotherapists) lose real money to no-shows, so they
take deposits. Handing the front desk to an AI agent is tempting, but an agent that can capture,
refund or void on its own is one prompt injection away from refunding everyone. We wanted the
agent to do all the routine work and still leave the decision about money with the owner, in a
way that can be proven afterwards rather than trusted.

It is built for the owner of a small appointment business who runs the front desk from their
phone: they want deposits to stop no-shows, and they want an assistant that handles bookings at
any hour, but they are the only one who decides when a customer's money is actually taken.

## What it does

- A customer books over chat (WhatsApp-style, simulated in the demo). The agent creates a PayPal
  order with intent **AUTHORIZE** and, when PayPal's signed `CHECKOUT.ORDER.APPROVED` webhook
  says the customer approved it, authorizes it: the 10.00 deposit is **held, not charged**.
- When money has to move, the agent can only **ask**:
  - **No-show:** it requests a `capture_deposit` mandate for that authorization and amount. If
    the visit is more than three days after the booking (past PayPal's honor period), it first
    reauthorizes the hold, so the owner signs for the live authorization.
  - **Cancellation:** it requests a `void_deposit` mandate; the hold is released and nothing is
    charged or refunded.
  - **Goodwill:** after a capture, it requests a `refund_deposit` mandate for part of it.
- The owner sees each request on their phone, built from the mandate's signed fields (not from
  what the model wrote), and taps **Approve** once. The phone signs the mandate with a
  non-extractable Ed25519 key that never leaves the browser.
- Only then does the gate call PayPal, once, with the mandate's id as `PayPal-Request-Id`.
  Approving twice, replaying, changing the amount or target, an expired mandate, or a customer
  typing "the owner approved" are all rejected, and every attempt (accepted or rejected) is
  appended to a hash-chained ledger whose chain check is shown on screen.

## How we built it

- **PayPal APIs:** Orders v2 (`POST /v2/checkout/orders` with intent AUTHORIZE, `.../authorize`),
  Payments v2 (`/v2/payments/authorizations/{id}/capture`, `/reauthorize`, `/void`,
  `/v2/payments/captures/{id}/refund`, plus GETs), and OAuth 2.0 client credentials
  (`/v1/oauth2/token`). Written against the **sandbox** with `httpx`; production is refused unless
  explicitly enabled. Every write sends `PayPal-Request-Id`, amounts go as two-decimal strings,
  timeouts and 5xx become transient errors, and the gate retries them with the same request id,
  so a capture that timed out after PayPal took the money is answered, not repeated.
- **AI:** Anthropic **Claude** (Messages API with tool use) drives the agent when an API key is
  set. Ten tools: six free (book, create the deposit order, confirm the hold, refresh an old hold
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
- PayPal's agent toolkit exposes `pay_order` and `create_refund` as plain tools and has no
  authorize/void; we evaluated it and wrote our own narrow adapter instead
  (`docs/agent_toolkit_decision.md`).

## Accomplishments that we're proud of

- The agent cannot move money on its own through any tool it holds: the tests use a spy provider
  and an injected "owner approved" message and assert that nothing moved. A decline is final and
  a second approval is refused.
- Replays and forged approvals are rejected in plain sight on the ledger page, with an intact
  chain check.
- The whole demo runs in two minutes with no keys, and the same code switches to Claude and the
  PayPal sandbox by setting environment variables.
- 387 automated tests, all offline, including the attacks listed under "Try to break it"
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

## Built with

python, fastapi, jinja, httpx, sqlite, paypal-webhooks, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519,
webcrypto, ag-grid
