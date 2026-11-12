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
| The video is built: `.venv/bin/python scripts/make_video.py` writes `docs/video/out/ask_first_pay.mp4` (2:47, 1920x1080, narration burned in, silent audio; our cap 2:50, rules cap under 3:00; shot 10 is a still of the sandbox ledger). Optional: record the voice-over and mix it with the one command in `docs/video/VOICE_OVER.md` (`ask_first_pay_voice.mp4`) | `docs/video/out/` | OWNER |
| Upload the video to **YouTube** and set its visibility to **Public** (rules line 175: "uploaded to and made publicly visible on YouTube"). Check the link in a private browser window before submitting. | YouTube URL | OWNER |
| Run every step of *Before making the repository public* below, then make it public | https://github.com/cleveria-ai/ask-first-pay | OWNER |
| The Apache-2.0 license shows in the repository's About section (rules line 171) | `gh repo view cleveria-ai/ask-first-pay --json visibility,licenseInfo` shows `PUBLIC` and `Apache-2.0` | OWNER |

## Form fields

| Field | Value |
|---|---|
| Devpost submission | https://devpost.com/software/ask-first-pay, submitted on 2026-11-12 to the PayPal AI Hackathon (Devpost: "Project submitted! Continue to edit your project until the hackathon deadline"). It holds: project name, tagline, story, built-with tags, repository link, eight gallery images with captions, video link, and "Additional info" (individual entrant, new project with the prior-work disclosure, PayPal and AI tools, AG Grid, repository, testing instructions, AI tools used). The personal answers and the eligibility boxes are the OWNER's own; the terms were accepted and Submit pressed on the OWNER's instruction. |
| Project name | Ask First Pay |
| Elevator pitch / tagline | "Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it. |
| About the project (story) | Paste `docs/DEVPOST.md` from "Inspiration" to "Prior work" (eleven sections, including "How it differs", "Proven on the real PayPal sandbox" and "Built with AG Grid"). Founder claims are default wording (`docs/FOUNDER_FACTS.md`); change them there first if the founder rewrites any. |
| AG Grid sponsor prize | Mention it: the ledger and the owner's mandate list are AG Grid Community grids; paste *Built with AG Grid* from `docs/DEVPOST.md` (features named there). |
| Built with | python, fastapi, jinja, httpx, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519, webcrypto, ag-grid |
| "Try it out" links | Repository URL (public since 2026-11-10): https://github.com/cleveria-ai/ask-first-pay |
| Video demo link | https://youtu.be/1rgegQG87w8 (public on YouTube since 2026-11-12; `ask_first_pay.mp4`, 2:47, narration burned in, no voice) |
| Image gallery / thumbnail | In this order: `docs/screenshots/02-owner-approval.png`, `12-sandbox-ledger.png` (real PayPal sandbox ids), `12-sandbox-chat-held.png` (the chip reads "PayPal sandbox"), `01-chat-booking.png`, `03-ledger-replay.png`, `04-cancellation-voided.png`, `05-owner-mobile.png`, `10-owner-today-mobile.png` (all PNG; desktop 1280x720, phone 375x812; the rest optional). Captions: the table in `docs/DEVPOST.md` → *Screenshots*. Thumbnail (3:2): crop `02-owner-approval.png` (OWNER). Regenerate: `.venv/bin/python scripts/screenshots.py --dark`. |
| PayPal APIs / products used | Orders v2 (create with intent AUTHORIZE, authorize), Payments v2 (capture, reauthorize, void, refund, get), OAuth 2.0 client credentials; sandbox. Run for real on 2026-11-11: `docs/SANDBOX_RUN.md`, `docs/SANDBOX_UI_RUN.md` |
| AI used | Anthropic Claude via the Messages API with tool use (model id from `ASK_FIRST_MODEL`, default `claude-sonnet-5-5`); offline scripted model when no key is set |
| Prior work / existing code disclosure | Paste *Prior work* from `docs/DEVPOST.md`: `libs/ask-first-mandate` created 2026-10-17 (inside the submission period) for our "Ask First for Alexa+" entry, reused under Apache-2.0; its identity signing and ledger were ported from our earlier public repository `soyharso/agent-identity-firma` (August 2026). Everything under `src/ask_first_pay/` is new. AG Grid Community vendored (MIT). |
| Testing instructions for judges | "Run it in 2 minutes" in `README.md`: `scripts/demo.sh`, no keys. |
| License | Apache-2.0 |
| Team members | None added (single entrant). OWNER can invite on Devpost before the deadline |
| Country of residence, eligibility | Answered on 2026-11-12 with the OWNER's answers. Tax / payment details: OWNER, only if a prize is awarded |
| Submitter type (individual, team, organization) | Individual (the OWNER's choice, 2026-11-12) |
| Any hackathon-specific questions not listed here | Answered on 2026-11-12 from `docs/DEVPOST.md` and the OWNER's answers |
| Accept the submission terms and press Submit | Done on 2026-11-12 on the OWNER's instruction; the entry can be edited until the deadline |


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
`docs/PR_*.md`, `docs/JUDGE_*.md`, `docs/STORY_VARIANTS_*.md`, `docs/FOUNDER_FACTS.md` (internal record of which founder lines are default wording). `scripts/escalera.py` reads the work
orders, so it keeps working on `internal`, where `docs/encargos/` still exists.

```bash
git branch internal main                              # internal = main with every internal file
# optional check that the ladder still runs on internal (it needs that worktree's own .venv):
#   git worktree add ../afp-internal internal && cd ../afp-internal && python3 -m venv .venv \
#     && .venv/bin/pip install -q -e ".[dev]" && python3 scripts/escalera.py docs/encargos/N11_pitch_and_compliance.md; cd -
git rm -r -q _sesion docs/encargos
git rm -q docs/PR_*.md docs/JUDGE_*.md docs/STORY_VARIANTS_*.md docs/FOUNDER_FACTS.md docs/PAQUETE_OPERADOR.md
git commit -m "Move internal working files to the internal branch before publication"
git ls-files _sesion docs/encargos 'docs/PR_*' 'docs/JUDGE_*' 'docs/STORY_*' docs/FOUNDER_FACTS.md docs/PAQUETE_OPERADOR.md | wc -l   # must print 0
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
