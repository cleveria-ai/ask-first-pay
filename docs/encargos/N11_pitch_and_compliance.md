# N11 — Pitch, video script and rules compliance

Branch `n11-pitch`, from `main` after N9 and N10 are merged. Read `docs/encargos/COMMON.md`,
`docs/JUDGE_PANEL_2026-11.md`, `docs/STORY_VARIANTS_2026-11.md` (V1 and grafts G1-G15) and the
rules copy `docs/rules/rules_2026-11-03.txt` (git-ignored; present in the main checkout only) first.

## Goal

Presentation (5.3/10) and Impact (5.6/10) were the panel's weakest criteria. Rewrite what judges
read and watch around story V1 ("Can it touch my money?"), using only what the app does on `main`,
and remove every rules risk the panel found.

1. **Founder facts file.** `docs/FOUNDER_FACTS.md` lists each claim in the founder's voice that the
   pitch or video uses, with its status: `confirmed by the owner` or `default wording`. Use the
   default wording unless the file says confirmed: "I run qnowa: booking with deposits for clinics
   and salons in Latin America."; "The first thing owners ask is: can it touch my money?";
   "designed for qnowa's clinics"; no numbers. Never invent a number or a quote.
2. **Devpost text (`docs/DEVPOST.md`).** The first screen (Inspiration and the start of What it
   does) is the business story in plain words, from the founder: who, what problem, what the owner
   gets, before any API name. Then the existing technical depth. Add a short "How it differs" with
   AP2/ACP (user-side mandates for agents that shop) versus Ask First Pay (seller-side, single-use
   owner mandates whose id becomes PayPal's request id; holds vs captures). Cite only public facts
   you can check; if you cannot reach a source, say "as publicly described" without specifics.
   Claim the live sandbox run only if `docs/SANDBOX_RUN.md` has a run with a capture; otherwise say
   it is ready to run and point to `scripts/sandbox_run.py`.
3. **Video (`docs/VIDEO_SCRIPT.md`, `docs/video/SHOTLIST.md`, `docs/video/subtitles.srt`,
   `scripts/record_demo.py`).** Rewrite to V1 with the grafts the three selectors agreed on (cold
   open on the 9:12 card, "PayPal" said in the first 15 s, time-of-day lower thirds, second caption
   track naming the PayPal calls, approval id = PayPal-Request-Id shot, void "moves $0.00", the
   Today panel as end card, one Spanish customer line with English subtitles). Total at most 2:45.
   Record with `ASK_FIRST_VIDEO=1` and `ASK_FIRST_TZ` set; no third-party marks other than PayPal
   (no model brand, no "AG Grid" caption, no "WhatsApp", no browser chrome). Every on-screen number
   must be one the app produces (match the Today panel's real counts). `scripts/check_video_assets.py`
   and `tests/test_video_assets.py` stay green.
4. **Rules compliance.** `docs/SUBMISSION_CHECKLIST.md`: the video is uploaded to YouTube and
   public (rules line 175); remove Vimeo, Youku and "unlisted". Add a "Before making the repository
   public" section with the exact commands to: remove the "Work in progress, private until
   submission." line from `README.md`; move internal files out of the published tree
   (`_sesion/`, `docs/encargos/`, `docs/PR_*.md`, `docs/JUDGE_*.md`, `docs/STORY_VARIANTS_*.md`,
   Spanish-language files) into a private branch `internal` and delete them from `main` in one
   commit, keeping `scripts/escalera.py` working on the internal branch; and the secret scan.
   Do not run those commands: list them.
5. **Built with / sponsor.** Keep the AG Grid section in the Devpost text (sponsor prize) and the
   Claude model id; the video stays brand-free.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the founder facts file exists and marks every claim | `test -s docs/FOUNDER_FACTS.md && grep -qE "confirmed by the owner\|default wording" docs/FOUNDER_FACTS.md` |
| K3 | the Devpost first 25 lines name qnowa and avoid API jargon | `head -25 docs/DEVPOST.md \| grep -q qnowa && ! head -25 docs/DEVPOST.md \| grep -qiE "AUTHORIZE\|Orders v2\|Payments v2\|jti\|idempot\|Ed25519"` |
| K4 | the Devpost text positions it against AP2 | `test $(grep -ciE "AP2\|ACP\|seller-side" docs/DEVPOST.md) -ge 3` |
| K5 | no live-run claim without a recorded capture | `grep -q "| capture |" docs/SANDBOX_RUN.md 2>/dev/null \|\| ! grep -qiE "we ran it (live\|against the sandbox)\|recorded against the live sandbox" docs/DEVPOST.md` |
| K6 | the video script follows V1 and stays under 2:45 | `grep -q "Can it touch my money" docs/VIDEO_SCRIPT.md && grep -qiE "total.*(1:[0-5][0-9]\|2:[0-3][0-9]\|2:4[0-5])" docs/VIDEO_SCRIPT.md` |
| K7 | video assets are consistent | `.venv/bin/python scripts/check_video_assets.py && .venv/bin/python -m pytest -q tests/test_video_assets.py` |
| K8 | no third-party marks in the subtitles | `! grep -niE "claude\|anthropic\|ag grid\|whatsapp\|chrome\|alexa" docs/video/subtitles.srt` |
| K9 | the checklist requires public YouTube only | `grep -q "YouTube" docs/SUBMISSION_CHECKLIST.md && ! grep -niE "vimeo\|youku\|unlisted" docs/SUBMISSION_CHECKLIST.md` |
| K10 | the checklist lists the pre-publication cleanup | `grep -q "Before making the repository public" docs/SUBMISSION_CHECKLIST.md && grep -q "_sesion" docs/SUBMISSION_CHECKLIST.md` |
| K11 | no secrets committed | `! git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}\|(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" -- .` |
