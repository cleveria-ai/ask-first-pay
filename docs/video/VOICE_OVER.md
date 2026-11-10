# Voice-over and upload

`docs/video/out/ask_first_pay.mp4` (built by `scripts/make_video.py`, not in git) is complete
without a voice: lower thirds, the yellow PayPal-call captions, the cards and the English
subtitles for the Spanish lines are burned in, and its audio track is silent. It can be uploaded
as it is. To add the founder's voice, record the lines below and run one ffmpeg command.

## The lines

Exactly the "Say" column of `docs/video/SHOTLIST.md` (and `docs/video/subtitles.srt`). Start
each line at its time (0.3 s after the shot starts); every line fits its shot at a calm pace.

| Shot | Start | Ends by | Say |
|---|---|---|---|
| 1 | 0:00.3 | 0:09.7 | Nine twelve. The nine o'clock patient isn't coming. Her deposit is held on PayPal, and only the owner's tap can keep it. |
| 2 | 0:10.3 | 0:19.7 | I run qnowa: booking with deposits for clinics and salons in Latin America. The first thing owners ask is: can it touch my money? |
| 3 | 0:20.3 | 0:33.7 | Deposits stop no-shows. But every day someone decides whose deposit to keep, release or give back. Our agent can hold money on its own, because a hold moves nothing. To move it, it can only ask. |
| 4 | 0:34.3 | 0:53.7 | Eleven forty-eight at night. Lucía books Monday at nine. The agent creates a PayPal order that only holds ten dollars. She approves it, a signed notice tells the agent, and it confirms. Held, not charged. The owner's phone stayed quiet. |
| 5 | 0:54.3 | 1:17.7 | Nine twelve again. The agent can't take the deposit; it asks. The phone shows what gets signed, not what the AI wrote: keep up to ten dollars, this booking, once. One tap signs it, and the approval id becomes PayPal's request id. One tap, one PayPal call. |
| 6 | 1:18.3 | 1:35.7 | Mid-morning. Lucía writes that her son was in the emergency room. A kind assistant would refund on the spot. Ours can't; it asks. And sometimes the owner says yes. Her money, her decision. |
| 7 | 1:36.3 | 1:51.7 | Someone pretends to be the owner: nothing reaches her phone, nothing reaches PayPal. The agent reuses an approval: rejected as a replay, and written down like everything else. |
| 8 | 1:52.3 | 2:13.7 | One thirty. Sofía cancels, in Spanish, and the agent answers in Spanish. We only held her money, so this is a void, not a refund: it moves zero dollars and releases the hold. Still the owner's call, so still one tap. |
| 9 | 2:14.3 | 2:29.7 | Closing time. Three taps. On its own, the agent made five PayPal calls and moved zero dollars. Every attempt, even the refused one, sits in a ledger anyone can check. |
| 10 | 2:30.3 | 2:38.7 | Can it touch my money? It can hold it. Only you can move it. Ask First Pay, designed for qnowa's clinics. |

Never read the approval id or a date aloud (the screen shows "Mon 16 Nov" and the recording day).

## How to record

Quiet room, soft furnishings around you, phone or laptop microphone a hand's width from your
mouth, slightly to the side. Notifications off.

**Option A: one take (simplest).** Play `ask_first_pay.mp4` muted on one screen (the video is
the prompter: each shot's visuals tell you where you are) and read from this page. Start the
recorder and the video at the same moment, and read each line when its shot appears. Save as
`voice.m4a` (iPhone Voice Memos and Android
recorders save m4a; on a laptop, QuickTime "New Audio Recording" or Audacity export to m4a/wav).
If your take starts late or early, set `OFFSET` in the command below (seconds; positive delays
the voice, negative trims its head).

**Option B: per shot.** Record ten short files `voice/01.m4a` … `voice/10.m4a`, one line each,
starting to speak right away (no more than a breath of silence at the head). Each is placed at
its start time above. A line that runs long only overlaps the next shot's first 0.3 s of silence;
keep it within "Ends by".

Copy the files into `docs/video/out/` (git-ignored, so the recordings never enter the repository)
and run the commands from the repository root.

## Mix (no music, nothing ducked)

The video stream is copied untouched; the voice is levelled to −16 LUFS (the usual target for
speech on YouTube) and padded with silence to the video's length.

**Option A, one take:**

```bash
OFFSET=0   # seconds; e.g. 0.8 if you started speaking 0.8 s late, -0.5 if 0.5 s early
ffmpeg -y -i docs/video/out/ask_first_pay.mp4 -itsoffset "$OFFSET" -i docs/video/out/voice.m4a \
  -filter_complex "[1:a]aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  docs/video/out/ask_first_pay_voice.mp4
```

**Option B, per shot** (each file starts at its shot's start + 0.3 s):

```bash
cd docs/video/out && ffmpeg -y -i ask_first_pay.mp4 \
  -i voice/01.m4a -i voice/02.m4a -i voice/03.m4a -i voice/04.m4a -i voice/05.m4a \
  -i voice/06.m4a -i voice/07.m4a -i voice/08.m4a -i voice/09.m4a -i voice/10.m4a \
  -filter_complex "\
[1:a]adelay=300:all=1[a1];[2:a]adelay=10300:all=1[a2];[3:a]adelay=20300:all=1[a3];\
[4:a]adelay=34300:all=1[a4];[5:a]adelay=54300:all=1[a5];[6:a]adelay=78300:all=1[a6];\
[7:a]adelay=96300:all=1[a7];[8:a]adelay=112300:all=1[a8];[9:a]adelay=134300:all=1[a9];\
[10:a]adelay=150300:all=1[a10];\
[a1][a2][a3][a4][a5][a6][a7][a8][a9][a10]amix=inputs=10:normalize=0:duration=longest,\
aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  ask_first_pay_voice.mp4 && cd ../../..
```

Check it: `ffprobe -v error -show_entries format=duration -of csv=p=0 docs/video/out/ask_first_pay_voice.mp4`
must print about 159 (under 165), and play it once start to finish with sound.

## YouTube upload

Upload `ask_first_pay_voice.mp4` if you recorded the voice, otherwise `ask_first_pay.mp4`.

| Setting | Value |
|---|---|
| Title | `Ask First Pay: an AI front desk that can hold a PayPal deposit, never move it` |
| Description | the block below |
| Thumbnail | auto-generated is fine; the frame at 2:30 (closing card) reads best |
| Audience | **No, it's not made for kids** |
| Subtitles | Upload `docs/video/subtitles.srt` as English captions (Subtitles → Add language → English → Upload file → "With timing") |
| Music | none (no third-party music; nothing to claim) |
| Visibility | **Public** (the rules require a publicly visible YouTube video; Unlisted or Private does not count) |

Description:

```text
"Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it.

I run qnowa: booking with deposits for clinics and salons in Latin America. When we talk about letting an AI answer the front desk, the first thing owners ask is: can it touch my money? Ask First Pay, designed for qnowa's clinics, is the answer built into the product: it can hold it; only you can move it.

- The customer books in the chat (English or Spanish) and leaves a deposit on PayPal: an order with intent AUTHORIZE, held, not charged.
- To keep (capture), release (void) or give back (refund) a deposit, the AI can only ask. The owner's phone shows what she would sign, never the AI's own words. One tap, one PayPal call, once: the approval id is sent to PayPal as the PayPal-Request-Id.
- Replays, a customer pretending to be the owner, changed amounts and expired approvals are refused, and every attempt is written to a hash-chained ledger anyone can check.

Recorded offline: scripted model, simulated PayPal. The live model uses the same tools.
The clinic and the customers are fictional.

Code: https://github.com/cleveria-ai/ask-first-pay
Built for the PayPal AI Hackathon 2026.
```

After publishing, open the link in a private browser window to confirm it plays without signing
in, then put it in `docs/DEVPOST.md` and the submission form (`docs/SUBMISSION_CHECKLIST.md`).
