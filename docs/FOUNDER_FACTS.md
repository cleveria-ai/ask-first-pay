# Founder facts

Every claim made in the founder's voice in `docs/DEVPOST.md`, `docs/VIDEO_SCRIPT.md` and
`docs/video/SHOTLIST.md`, with its status. A claim is **confirmed by the owner** only when the
founder has said so in writing; until then it is **default wording**: the safest version the
work order allows, chosen so it stays true. Never add a number, a quote or a customer story here
that the founder has not given.

As of 2026-11-10 the founder's answers have not arrived, so every row is default wording.

| # | Claim, exactly as used | Where | Status | Not used (needs the owner's confirmation first) |
|---|---|---|---|---|
| F1 | "I run qnowa: booking with deposits for clinics and salons in Latin America." | Video shot 2 (voice and lower third "Founder, qnowa · Booking with deposits for clinics and salons in Latin America"); DEVPOST *Inspiration* | default wording | — |
| F2 | "The first thing owners ask is: can it touch my money?" | Video shot 2; DEVPOST *Inspiration* | default wording | "Every owner asked …" (a claim about all owners) |
| F3 | "designed for qnowa's clinics" | Video shots 10 (voice and closing card); DEVPOST *Inspiration* and *What's next* | default wording | "We're building this into qnowa" |
| F4 | No numbers about qnowa (no-show rates, deposit sizes, customer counts, revenue) | Nowhere | default wording | Any figure, until the founder gives it with its source |
| F5 | Voice only: the founder records the voice-over, no face on camera; shot 2 is a still of the phone with a lower third | Video shot 2 | default wording | A face-cam shot |
| F6 | The video runs the offline scripted model and the simulated PayPal, and says so on screen ("Demo runs the scripted model; the live model uses the same tools"; "Recorded offline: scripted model, simulated PayPal.") | Video shots 4 and 10 | default wording | Any on-screen claim of a live model or a live sandbox run (only after `docs/SANDBOX_RUN.md` has a capture) |

Also in the founder's voice, but about the product, not about qnowa (each one is what the demo
does on screen, so it needs no confirmation): "Deposits stop no-shows" is offered as the reason
businesses take deposits, not as a qnowa measurement; "Our agent can hold money on its own,
because a hold moves nothing"; "Her money, her decision".

## How to change a row

When the founder confirms or rewrites a claim: replace the wording in this table and in every
place listed under "Where", set the status to `confirmed by the owner` with the date, and re-run
`.venv/bin/python scripts/check_video_assets.py --write-srt` if the video voice changed.

2026-11-10: the owner asked the coordinator to apply the default wording for F1-F6 (relayed by the method's integration session); no line was individually rewritten. This file is internal and leaves `main` before publication (`docs/SUBMISSION_CHECKLIST.md`, *Before making the repository public*).
