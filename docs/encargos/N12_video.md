# N12 — The demo video, ready to upload

Branch `n12-video`, from `main` after N11 is merged. Read `docs/encargos/COMMON.md`,
`docs/VIDEO_SCRIPT.md`, `docs/video/SHOTLIST.md`, `docs/video/subtitles.srt` and
`docs/FOUNDER_FACTS.md` first.

## Goal

The owner records nothing complicated on submission eve. Produce the final video from the app
itself so the only remaining act is uploading it to YouTube, with an optional voice track the
owner can add with one command.

1. Record every shot of `docs/VIDEO_SCRIPT.md` with `scripts/record_demo.py` (offline, no keys,
   `ASK_FIRST_VIDEO=1`, `ASK_FIRST_TZ=America/Mexico_City`), at 1920x1080, with the phone shots
   in a 390x844 frame as the script says.
2. `scripts/make_video.py` assembles `docs/video/out/ask_first_pay.mp4` (git-ignored) with ffmpeg:
   the title/text cards the script asks for (rendered from the design tokens, no third-party
   fonts that need a licence beyond what the repo already ships), lower thirds, the English
   subtitles burned in (readable on a phone: large, high contrast), and the second caption track
   naming the PayPal calls if the script has one. H.264 + AAC, a silent audio track (YouTube
   accepts it), no music.
3. Total duration strictly under 2:45 and every shot within ±1 s of the script's timing; if the
   app is faster or slower, adjust holds, never speed up text.
4. `docs/video/VOICE_OVER.md`: the narration lines with their start times, how to record them on
   a phone or laptop in one take (or per shot), and the exact ffmpeg command that mixes a
   recorded `voice.m4a` (or per-shot files) into `ask_first_pay_voice.mp4`, ducking nothing (no
   music). Also the YouTube upload settings: title, description (from `docs/DEVPOST.md`, with the
   repository link), visibility **Public**, "No, it's not made for kids", no third-party music.
5. A contact sheet `docs/video/out/contact_sheet.png` (one frame per shot) so the coordinator can
   check the cut without playing it.

## Acceptance criteria

| id | says | command |
|---|---|---|
| K1 | the whole suite is green | `.venv/bin/python -m pytest -q` |
| K2 | the video exists, is 1920x1080 and under 2:45 | `ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 docs/video/out/ask_first_pay.mp4 \| grep -q "^1920,1080$" && test $(ffprobe -v error -show_entries format=duration -of csv=p=0 docs/video/out/ask_first_pay.mp4 \| cut -d. -f1) -lt 165` |
| K3 | it has an audio track (silent is fine) and H.264 video | `ffprobe -v error -show_entries stream=codec_name -of csv=p=0 docs/video/out/ask_first_pay.mp4 \| tr '\n' ' ' \| grep -q "h264.*aac\|aac.*h264"` |
| K4 | the assembly script is tested offline | `.venv/bin/python -m pytest -q -k make_video` |
| K5 | the contact sheet exists | `test -s docs/video/out/contact_sheet.png` |
| K6 | the voice-over guide has the mix command and public YouTube settings | `grep -q "ffmpeg" docs/video/VOICE_OVER.md && grep -q "Public" docs/video/VOICE_OVER.md` |
| K7 | video assets stay consistent | `.venv/bin/python scripts/check_video_assets.py` |
| K8 | no third-party marks in subtitles | `! grep -niE "claude\|anthropic\|ag grid\|whatsapp\|chrome\|alexa" docs/video/subtitles.srt` |
