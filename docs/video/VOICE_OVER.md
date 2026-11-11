# Voice-over and upload

`docs/video/out/ask_first_pay.mp4` (built by `scripts/make_video.py`, not in git) stands alone
without a voice: the narration below is burned in as large captions in a band at the bottom (from
`docs/video/subtitles.srt`), and so are the lower thirds, the yellow PayPal-call captions, the
cards and the English subtitles for the Spanish lines. Its audio track is silent. It can be
uploaded as it is. To add the founder's voice, record the eleven lines once, at your own pace,
without watching the video, and run one command: `scripts/place_voice.py` cuts the recording at
its pauses and puts each line on its shot. The voice version keeps the burned-in narration (the
mix copies the picture untouched), so a viewer with the sound off still follows it.

## Record once, at your own pace

```bash
.venv/bin/python scripts/place_voice.py --take docs/video/out/voice.m4a
```

Run it from the repository root. It writes `docs/video/out/ask_first_pay_voice.mp4` and, next to
it, `voice_report.txt`: a table with each line, the second it starts at, how long it is, the room
its shot leaves, the speed it was played at and the slack. Before it says `wrote ...` the command
checks its own output: same length as the video, under 170 s, the picture identical to the
original (it is copied, not re-encoded), an audio track that is not silent, levelled to
−16 LUFS (the usual target for speech on YouTube), and, by listening to the mix, that every line
sits within 80 ms of its second and is over before the cut that ends its shot. If any of that
fails, no file is written and the message names the line. Needs only Python and ffmpeg.

To try the tool before recording anything: `.venv/bin/python scripts/place_voice.py --self-test`
places eleven tone bursts on the real video (`docs/video/out/voice_selftest.mp4`) and checks where
each one starts. It never touches `ask_first_pay_voice.mp4`.

### Five minutes with a phone

1. **The room.** Quiet, with soft things in it (a bed, a sofa, curtains). Windows shut, fan and
   air conditioning off, phone on do-not-disturb.
2. **The phone.** Stand it on a table against a pile of books, level with your mouth, a hand's
   width away (15-20 cm) and a little to one side, so your breath does not hit the microphone.
   Do not hold it. Open the voice recorder (Voice Memos on an iPhone, Recorder on Android).
3. **Read** the eleven lines below from this page, in order. Press record, wait two seconds,
   start. **Between two lines, stay silent for two seconds** (count "one thousand one, one
   thousand two" in your head). Inside a line, breathe at the full stops, but never stop for a
   whole second: a pause that long is where the recording gets cut.
4. **A line went wrong?** Keep recording: stay silent two seconds, say the whole line again, and
   go on to the next. You sort it out afterwards with `--pick` (below).
5. After the last line wait two seconds and stop. That is one take of about three minutes.
   Anything else said on it ("ready?", "done") counts as a piece: leave it out with `--pick`.
6. **To the computer.** Send the recording to yourself as a file (AirDrop, email, a cloud drive
   or a USB cable; not as a voice message in a chat, which gets compressed again) and save it as
   `docs/video/out/voice.m4a`. That folder is git-ignored, so recordings never enter the
   repository. Any format ffmpeg reads will do (m4a, mp3, wav, ogg, even a video): use the
   file's real name in the command.

Lines 3 and 1 have the least room (the "Room" column of the table of lines says how much each
one has and marks them tight): read those two briskly and do not linger at their full stops. The
rest fit at a calm pace.

### What the command answers

| It says | What happened | What to do |
|---|---|---|
| `wrote docs/video/out/ask_first_pay_voice.mp4 and ...` | Done and checked. | Play it once, start to finish, with sound. |
| `line 3 (answer) ran long: sped up x1.045` | The line was a little longer than its shot and was sped up to fit (by ×1.12 at most, never more; pitch unchanged). | Nothing. |
| `ignored a 0.31 s sound at 52.4 s (shorter than 0.6 s)` | Something shorter than 0.6 s between two pauses was left out: a click, a cough. | Nothing, unless it was a word: then say that line again (see the last row). |
| `found 12 pieces; the video has 11 lines`, then a table of the pieces (number, start, length); exit code 2 | A line was said twice, a noise lasted over 0.6 s, or a pause was too long or too short. Nothing was written. | A noise (the phone picked up after the last line): the message names the piece and the `--pick` that leaves it out. Said twice: name the pieces to use, in the order of the lines. `--pick 1,2,4,5,6,7,8,9,10,11,12` leaves piece 3 out. A line that broke in two at a long pause: `--pick 1,2+3,4,...` joins pieces 2 and 3. Two lines that ran together: split at shorter pauses with `--min-gap 0.8` (default 1.2; the message names a value when one gives exactly eleven pieces). |
| `line 3 (answer) does not fit: ... still 0.78 s too long`; exit code 3 | That line is longer than its shot even sped up ×1.12, and the voice is never sped up more than that. Nothing was written: a line is never cut. | First `--tighten`: it shortens the pauses inside the lines that run long (never under 0.3 s; no word is touched). If that is not enough, say only those lines again, brisker, into a second recording and pick its pieces: `--take docs/video/out/voice.m4a docs/video/out/fix.m4a --pick 1,2,12,4,5,6,7,8,9,10,11` puts the new recording's first piece (number 12: its pieces are numbered after the first recording's eleven) in the place of line 3. |

The first line of the output says what the command took for silence, for example `under -41.5 dB
(auto) is silence`: by default 20 dB under the voice of that recording, and at least 10 dB over
its quiet parts, so a quiet phone or a room with some noise needs no setting. If the pieces still
come out wrong in a noisy room, raise it by hand: `--silence-db -25`.

## The lines

Exactly the "Say" column of `docs/video/SHOTLIST.md` (and `docs/video/subtitles.srt`). With
`place_voice.py` you do not watch the clock: each line is placed at its "Start" (0.3 s after the
shot starts) and must end by "Ends by". The times matter only if you mix by hand (below).

"Room" is the longest the line may last (its shot less 0.3 s at each end) and the pace that
takes: its words divided by those seconds, pauses included. A calm read is about 2 words a
second, and the command's speed-up (×1.12 at most) stretches that to about 2.2; a line that asks
for more than 2.2 words a second is marked **tight** and needs a brisk read.

| Shot | Start | Ends by | Room | Say |
|---|---|---|---|---|
| 1 | 0:00.3 | 0:09.7 | 9.4 s (2.3 words/s, **tight**) | Nine twelve. The nine o'clock patient isn't coming. Her deposit is held on PayPal, and only the owner's tap can keep it. |
| 2 | 0:10.3 | 0:19.7 | 9.4 s (2.1 words/s) | I run qnowa: deposit booking for clinics in Latin America. The first thing owners ask: can it touch my money? |
| 3 | 0:20.3 | 0:33.7 | 13.4 s (2.7 words/s, **tight**) | Deposits stop no-shows. But every day someone decides whose deposit to keep, release or give back. Our agent can hold money on its own, because a hold moves nothing. To move it, it can only ask. |
| 4 | 0:34.3 | 0:53.7 | 19.4 s (2.1 words/s) | Eleven forty-eight at night. Lucía books Monday at nine. The agent creates a PayPal order that only holds ten dollars. She approves it, a signed notice tells the agent, and it confirms. Held, not charged. The owner's phone stayed quiet. |
| 5 | 0:54.3 | 1:17.7 | 23.4 s (2.0 words/s) | Nine twelve again. The agent can't take the deposit; it asks. The phone shows what gets signed, not what the AI wrote: keep up to ten dollars, this booking, once. One tap signs it, and the approval id becomes PayPal's request id. One tap, one PayPal call. |
| 6 | 1:18.3 | 1:35.7 | 17.4 s (1.9 words/s) | Mid-morning. Lucía writes that her son was in the emergency room. A kind assistant would refund on the spot. Ours can't; it asks. And sometimes the owner says yes. Her money, her decision. |
| 7 | 1:36.3 | 1:51.7 | 15.4 s (1.8 words/s) | Someone pretends to be the owner: nothing reaches her phone, nothing reaches PayPal. The agent reuses an approval: rejected as a replay, and written down like everything else. |
| 8 | 1:52.3 | 2:13.7 | 21.4 s (1.9 words/s) | One thirty. Sofía cancels, in Spanish, and the agent answers in Spanish. We only held her money, so this is a void, not a refund: it moves zero dollars and releases the hold. Still the owner's call, so still one tap. |
| 9 | 2:14.3 | 2:29.7 | 15.4 s (1.9 words/s) | Closing time. Three taps. On its own, the agent made five PayPal calls and moved zero dollars. Every attempt, even the refused one, sits in a ledger anyone can check. |
| 10 | 2:30.3 | 2:37.7 | 7.4 s (1.9 words/s) | Not only a simulation. Capture, void and refund ran against the real PayPal sandbox. |
| 11 | 2:38.3 | 2:46.7 | 8.4 s (2.0 words/s) | Can it touch my money? It can hold it. Only you can move it. Ask First Pay. |

Never read the approval id, a PayPal id or a date aloud (the screen shows "Mon 16 Nov" and the
recording day; shot 10 shows the sandbox run's ids and date as text).

## Other ways

### One file per line

Record eleven short files, one line each, named `01.*` to `11.*` in any format ffmpeg reads (a
synthetic voice saved line by line works the same way), put them in `docs/video/out/voice/` and
run:

```bash
.venv/bin/python scripts/place_voice.py --lines docs/video/out/voice
```

Each file is trimmed to its first and last sound, placed on its shot, and fitted, checked and
reported exactly as above.

### By hand, with ffmpeg alone

Quiet room, soft furnishings around you, phone or laptop microphone a hand's width from your
mouth, slightly to the side. Notifications off. Copy the files into `docs/video/out/` and run the
commands from the repository root. The video stream is copied untouched; the voice is levelled to
−16 LUFS and padded with silence to the video's length (no music, nothing ducked).

**Option A: one take in step with the video.** Play `ask_first_pay.mp4` muted on one screen (the
video is the prompter: each shot's visuals tell you where you are) and read from this page. Start
the recorder and the video at the same moment, and read each line when its shot appears. Save as
`voice.m4a` (iPhone Voice Memos and Android
recorders save m4a; on a laptop, QuickTime "New Audio Recording" or Audacity export to m4a/wav).
If the recorder started before the video, set `TRIM` in the command below to the seconds to cut
from the head of the recording; if it started after the video, set `DELAY_MS` to the
milliseconds of silence to put before it. (Tip: say "mark" as you press play; the time of "mark"
in the recording is your `TRIM`.)

```bash
TRIM=0       # seconds cut from the head of voice.m4a (recorder started before the video)
DELAY_MS=0   # milliseconds of silence before it (recorder started after the video)
ffmpeg -y -i docs/video/out/ask_first_pay.mp4 -i docs/video/out/voice.m4a \
  -filter_complex "[1:a]atrim=start=$TRIM,asetpts=PTS-STARTPTS,adelay=$DELAY_MS:all=1,aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  docs/video/out/ask_first_pay_voice.mp4
```

**Option B: per shot.** Record eleven short files `voice/01.m4a` … `voice/11.m4a`, one line each,
starting to speak right away (no more than a breath of silence at the head). Each is placed at
its start time above (its shot's start + 0.3 s). A line that runs long only overlaps the next
shot's first 0.3 s of silence; keep it within "Ends by".

```bash
cd docs/video/out && ffmpeg -y -i ask_first_pay.mp4 \
  -i voice/01.m4a -i voice/02.m4a -i voice/03.m4a -i voice/04.m4a -i voice/05.m4a \
  -i voice/06.m4a -i voice/07.m4a -i voice/08.m4a -i voice/09.m4a -i voice/10.m4a \
  -i voice/11.m4a \
  -filter_complex "\
[1:a]adelay=300:all=1[a1];[2:a]adelay=10300:all=1[a2];[3:a]adelay=20300:all=1[a3];\
[4:a]adelay=34300:all=1[a4];[5:a]adelay=54300:all=1[a5];[6:a]adelay=78300:all=1[a6];\
[7:a]adelay=96300:all=1[a7];[8:a]adelay=112300:all=1[a8];[9:a]adelay=134300:all=1[a9];\
[10:a]adelay=150300:all=1[a10];[11:a]adelay=158300:all=1[a11];\
[a1][a2][a3][a4][a5][a6][a7][a8][a9][a10][a11]amix=inputs=11:normalize=0:duration=longest,\
aresample=48000,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11,apad[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  ask_first_pay_voice.mp4 && cd ../../..
```

Check a hand-made mix: `ffprobe -v error -show_entries format=duration -of csv=p=0 docs/video/out/ask_first_pay_voice.mp4`
must print about 167 (under 170), and play it once start to finish with sound.

## YouTube upload

Upload `ask_first_pay_voice.mp4` if you recorded the voice, otherwise `ask_first_pay.mp4`.

| Setting | Value |
|---|---|
| Title | `Ask First Pay: an AI front desk that can hold a PayPal deposit, never move it` |
| Description | the block below |
| Thumbnail | auto-generated is fine; the frame at 2:40 (closing card) reads best |
| Audience | **No, it's not made for kids** |
| Subtitles | None needed: the narration is burned in. Do not upload `subtitles.srt` as captions (they would repeat the burned-in text) |
| Music | none (no third-party music; nothing to claim) |
| Visibility | **Public** (the rules require a publicly visible YouTube video; Unlisted or Private does not count) |

Description:

```text
"Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it.

I run qnowa: booking with deposits for clinics and salons in Latin America. When we talk about letting an AI answer the front desk, the first thing owners ask is: can it touch my money? Ask First Pay, designed for qnowa's clinics, is the answer built into the product: it can hold it; only you can move it.

- The customer books in the chat (English or Spanish) and leaves a deposit on PayPal: an order with intent AUTHORIZE, held, not charged.
- To keep (capture), release (void) or give back (refund) a deposit, the AI can only ask. The owner's phone shows what she would sign, never the AI's own words. One tap, one PayPal call, once: the approval id is sent to PayPal as the PayPal-Request-Id.
- Replays, a customer pretending to be the owner, changed amounts and expired approvals are refused, and every attempt is written to a hash-chained ledger anyone can check.

The demo is recorded offline: scripted model, simulated PayPal. The live model uses the same tools.
At 2:30, a still screenshot of the ledger after a run against the real PayPal sandbox (2026-11-11); the record, with PayPal's ids, is docs/SANDBOX_UI_RUN.md in the repository.
The clinic and the customers are fictional.

Code: https://github.com/cleveria-ai/ask-first-pay
Built for the PayPal AI Hackathon 2026.
```

After publishing, open the link in a private browser window to confirm it plays without signing
in, then put it in `docs/DEVPOST.md` and the submission form (`docs/SUBMISSION_CHECKLIST.md`).
