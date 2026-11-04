# Submission checklist (Devpost)

Deadline: **2026-11-12 12:00 Pacific**. "OWNER" means only the repository owner can do or fill it.
Field names follow the standard Devpost project form; check the live form for any extra
hackathon-specific questions and answer them from `docs/DEVPOST.md`.

## Before the form

| Step | Value | Who |
|---|---|---|
| Join the hackathon on Devpost (and accept the rules) | — | OWNER |
| Merge the integration pull request into `main` | after review | OWNER |
| Full suite green on `main` | `.venv/bin/python -m pytest -q` | OWNER (re-run after merge) |
| Optional: one run against the PayPal sandbox with your own sandbox app | `pytest -m live` and the demo with `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET` exported (never committed) | OWNER |
| Optional: one run with Claude | export `ANTHROPIC_API_KEY`, `scripts/demo.sh` | OWNER |
| Record the video from `docs/VIDEO_SCRIPT.md` (under 3:00; script totals 2:30) | — | OWNER |
| Upload the video (YouTube, Vimeo or Youku, public or unlisted as the rules allow) | URL | OWNER |
| Make the repository public (after checking `git log` has no secrets: `git grep -nE "sk-ant-\|PAYPAL_CLIENT_SECRET\s*="`) | https://github.com/cleveria-ai/ask-first-pay | OWNER |
| Remove "Work in progress, private until submission." from `README.md` | — | OWNER |

## Form fields

| Field | Value |
|---|---|
| Project name | Ask First Pay |
| Elevator pitch / tagline | An AI front desk that can take a PayPal deposit on its own, but has to ask before it moves a cent. |
| About the project (story) | Paste `docs/DEVPOST.md` from "Inspiration" to "What's next" (the seven sections). |
| Built with | python, fastapi, jinja, httpx, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519, webcrypto, ag-grid |
| "Try it out" links | Repository URL (once public): https://github.com/cleveria-ai/ask-first-pay — OWNER confirms |
| Video demo link | OWNER (URL after upload) |
| Image gallery / thumbnail | `docs/screenshots/chat.png`, `docs/screenshots/owner-pending.png`, `docs/screenshots/ledger.png` (3:2 thumbnail: OWNER crops) |
| PayPal APIs / products used | Orders v2 (create with intent AUTHORIZE, authorize), Payments v2 (capture, reauthorize, void, refund, get), OAuth 2.0 client credentials; sandbox |
| AI used | Anthropic Claude via the Messages API with tool use (model id from `ASK_FIRST_MODEL`, default `claude-sonnet-5-5`); offline scripted model when no key is set |
| Prior work / existing code disclosure | `libs/ask-first-mandate` created 2026-10-17 (inside the submission period) for our "Ask First for Alexa+" entry, reused under Apache-2.0; its README declares what it ports from an earlier public repository. Everything under `src/ask_first_pay/` is new. AG Grid Community vendored (MIT). |
| Testing instructions for judges | "Run it in 2 minutes" in `README.md`: `scripts/demo.sh`, no keys. |
| License | Apache-2.0 |
| Team members | OWNER (invite on Devpost) |
| Country of residence, eligibility, tax / payment details | OWNER |
| Submitter type (individual, team, organization) | OWNER |
| Any hackathon-specific questions not listed here | OWNER (answer from `docs/DEVPOST.md`) |
| Accept the submission terms and press Submit | OWNER |
