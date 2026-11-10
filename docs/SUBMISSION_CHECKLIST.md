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
| Record the voice-over and edit the video from `docs/VIDEO_SCRIPT.md` and the raw clips in `docs/video/raw/` (script totals 2:39; hard cap 2:45, rules cap under 3:00) | — | OWNER |
| Upload the video to **YouTube** and set its visibility to **Public** (rules line 175: "uploaded to and made publicly visible on YouTube"). Check the link in a private browser window before submitting. | YouTube URL | OWNER |
| Run every step of *Before making the repository public* below, then make it public | https://github.com/cleveria-ai/ask-first-pay | OWNER |
| The Apache-2.0 license shows in the repository's About section (rules line 171) | `gh repo view cleveria-ai/ask-first-pay --json visibility,licenseInfo` shows `PUBLIC` and `Apache-2.0` | OWNER |

## Form fields

| Field | Value |
|---|---|
| Project name | Ask First Pay |
| Elevator pitch / tagline | "Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it. |
| About the project (story) | Paste `docs/DEVPOST.md` from "Inspiration" to "What's next" (nine sections, including "How it differs" and "Built with AG Grid"). Founder claims are default wording (`docs/FOUNDER_FACTS.md`); change them there first if the founder rewrites any. |
| AG Grid sponsor prize | Mention it: the ledger and the owner's mandate list are AG Grid Community grids; paste *Built with AG Grid* from `docs/DEVPOST.md` (features named there). |
| Built with | python, fastapi, jinja, httpx, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519, webcrypto, ag-grid |
| "Try it out" links | Repository URL (once public): https://github.com/cleveria-ai/ask-first-pay — OWNER confirms |
| Video demo link | OWNER: the public YouTube URL |
| Image gallery / thumbnail | In this order: `docs/screenshots/01-chat-booking.png`, `02-owner-approval.png`, `03-ledger-replay.png`, `04-cancellation-voided.png`, `05-owner-mobile.png` (all PNG; desktop 1280x720, phone 375x812; `06`-`08` optional). Captions: the table in `docs/DEVPOST.md` → *Screenshots*. Thumbnail (3:2): crop `02-owner-approval.png` (OWNER). Regenerate: `.venv/bin/python scripts/screenshots.py --dark`. |
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


## Before making the repository public

Not run by anyone yet: these are the exact commands, for the owner, in a clean checkout of `main`
after the last merge. The repository must contain everything needed to run the project (rules
line 170), so only internal working files move; code, tests, `docs/DEVPOST.md`, `docs/VIDEO_SCRIPT.md`,
`docs/video/`, `docs/screenshots/` and the license stay.

**1. Remove the private notice from `README.md`.**

```bash
git switch main && git pull --ff-only
sed -i 's/^\*\*Work in progress, private until submission\.\*\* //' README.md
grep -c 'private until submission' README.md          # must print 0
git commit -am "README: the repository is public"
```

**2. Keep the internal files on a branch `internal`, and delete them from `main` in one commit.**
Internal files: `_sesion/` (Spanish-language session notes), `docs/encargos/` (work orders),
`docs/PR_*.md`, `docs/JUDGE_*.md`, `docs/STORY_VARIANTS_*.md`. `scripts/escalera.py` reads the work
orders, so it keeps working on `internal`, where `docs/encargos/` still exists.

```bash
git branch internal main                              # internal = main with every internal file
# optional check that the ladder still runs on internal (it needs that worktree's own .venv):
#   git worktree add ../afp-internal internal && cd ../afp-internal && python3 -m venv .venv \
#     && .venv/bin/pip install -q -e ".[dev]" && python3 scripts/escalera.py docs/encargos/N11_pitch_and_compliance.md; cd -
git rm -r -q _sesion docs/encargos
git rm -q docs/PR_*.md docs/JUDGE_*.md docs/STORY_VARIANTS_*.md
git commit -m "Move internal working files to the internal branch before publication"
git ls-files _sesion docs/encargos 'docs/PR_*' 'docs/JUDGE_*' 'docs/STORY_*' | wc -l   # must print 0
git grep -nE '[áéíóúñ¿¡]' -- '*.md' ':(exclude)docs/video/*' ':(exclude)docs/VIDEO_SCRIPT.md' ':(exclude)README.md' ':(exclude)docs/DEVPOST.md' ':(exclude)docs/SUBMISSION_CHECKLIST.md'   # no Spanish-language file left (names and quoted Spanish lines with English translation are fine)
.venv/bin/python -m pytest -q                         # still green on main
```

A branch of a public repository is public too. Keep `internal` private: push it only to a
separate private repository (for example `git remote add private <private repo URL> && git push
private internal`), never `git push origin internal`.

**3. Secret scan, over the whole history of every branch that will be public.**

```bash
git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}|(client_secret|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" $(git rev-list main) | grep -v 'FAKEFAKE'
git grep -nE "A21AA[A-Za-z0-9_-]{20,}" $(git rev-list main) | grep -v MUST-NOT-LEAK   # PayPal access tokens start A21AA; the test fake says MUST-NOT-LEAK
git log main --name-only --format= | sort -u | grep -E '(^|/)\.env|\.sqlite|\.pem$|\.key$|\.p12$'
```

Each command must print nothing. (The first one, without the `grep -v`, also prints one old test
line, `tests/security/test_security_secrets.py` at commit `f0ab477`, whose key is the literal
fake made of the word FAKE repeated; that is expected.) If anything else prints, stop: do not
publish, and rotate the credential first.

**4. Then:** push `main`, make the repository public, and check the About section shows Apache-2.0.

Note: deleting files in a commit keeps them in `main`'s history. If the internal files must not be
readable in the public history either, the history has to be republished (for example a fresh
single-commit branch); that rewrites history and is the owner's decision.
