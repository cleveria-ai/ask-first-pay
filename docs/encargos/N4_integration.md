# N4 — Integration and submission package

Branch `n4-integration`, created from `main` after N1, N2 and N3 opened their pull requests
(#1, #2, #3). Read `docs/encargos/COMMON.md` and `docs/CONTRACT.md` first.

## Goal

One branch where the three pieces work together end to end, plus everything the submission needs
except the acts only the owner can do (joining, recording, publishing, submitting).

1. Merge `n1-paypal-adapter`, `n2-agent` and `n3-demo` into `n4-integration`. Resolve conflicts
   by keeping each piece's own folder as its owner wrote it; in shared files (`pyproject.toml`,
   `README.md`) combine both sides.
2. Wire the demo chat to the real agent (`ask_first_pay.agent.run_turn`) instead of N3's stub.
   The agent uses Claude when `ANTHROPIC_API_KEY` is set and the scripted model otherwise, so a
   judge without keys still gets a working demo. Provider: `FakeProvider` by default,
   `PayPalProvider` when `PAYPAL_CLIENT_ID` is set.
3. `scripts/demo.sh` starts the app on `PORT` (default 8000) and prints the three URLs.
4. `README.md` for judges: what it is (3 lines), a 60-second architecture diagram in text, **"Run
   it in 2 minutes"** (no keys), "Run it against the PayPal sandbox" (create your own sandbox
   app; never publish credentials), the three stories (no-show, cancellation, goodwill), a
   **"Prior work"** section (the mandate library was created on 2026-10-17, inside the submission
   period, and everything under `src/ask_first_pay/` is new), and the Apache-2.0 license.
5. `docs/DEVPOST.md`: the Devpost text with the standard sections (Inspiration, What it does,
   How we built it, Challenges we ran into, Accomplishments that we're proud of, What we learned,
   What's next), naming the PayPal APIs used and the AI used. No claims the code does not back.
6. `docs/VIDEO_SCRIPT.md`: a shot-by-shot script under 2:45 total (the rules cap the video at
   3:00), with a time column, narration and what is on screen; no music, no third-party
   trademarks other than PayPal's. It must show: the problem in 15 s, a booking with a held
   deposit, a no-show captured only after the owner taps Approve, a replay rejected on screen,
   a cancellation voided, the ledger chain check.
7. `docs/SUBMISSION_CHECKLIST.md`: every field of the Devpost form with its value or "OWNER" when
   only the owner can fill it.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the three pieces' ladders give d = 0 on this branch | `python3 -c "import json,subprocess,sys; sys.exit(any(json.loads(subprocess.run(['python3','scripts/escalera.py','docs/encargos/'+n+'.md','--json'],capture_output=True,text=True).stdout)['d']!=0 for n in ('N1_paypal_adapter','N2_agent','N3_demo')))"` |
| K3 | the demo chat calls the real agent | `grep -rq "run_turn" src/ask_first_pay/demo` |
| K4 | an end-to-end test drives chat, owner approval and ledger through the agent | `.venv/bin/python -m pytest -q tests/demo -k end_to_end` |
| K5 | the demo starts and serves the chat page with no keys | `env -u ANTHROPIC_API_KEY -u PAYPAL_CLIENT_ID PORT=8765 timeout 60 bash -c 'scripts/demo.sh >/tmp/demo.log 2>&1 & for i in $(seq 1 30); do curl -sf localhost:8765/chat >/dev/null && kill %1 && exit 0; sleep 1; done; kill %1; exit 1'` |
| K6 | the README has the judge sections | `grep -q "Run it in 2 minutes" README.md && grep -q "Prior work" README.md && grep -q "sandbox" README.md` |
| K7 | the Devpost text has its seven sections | `test $(grep -cE "^## (Inspiration\|What it does\|How we built it\|Challenges\|Accomplishments\|What we learned\|What's next)" docs/DEVPOST.md) -ge 7` |
| K8 | the video script exists and states a total under 2:45 | `grep -qiE "total.*(1:[0-5][0-9]\|2:[0-3][0-9]\|2:4[0-5])" docs/VIDEO_SCRIPT.md` |
| K9 | the submission checklist exists | `test -s docs/SUBMISSION_CHECKLIST.md` |
| K10 | no secrets committed | `! git grep -nE "(sk-ant-[A-Za-z0-9_-]{10,}\|(client_secret\|PAYPAL_CLIENT_SECRET)\s*=\s*['\"][A-Za-z0-9_-]{12,})" -- .` |
