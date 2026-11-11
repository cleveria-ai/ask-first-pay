"""Put the voice on the video: record once, at your own pace, and one command places every line.

    .venv/bin/python scripts/place_voice.py --take docs/video/out/voice.m4a
    .venv/bin/python scripts/place_voice.py --take docs/video/out/voice.m4a --pick 1,2,4,5,6,7,8,9,10,11,12
    .venv/bin/python scripts/place_voice.py --lines docs/video/out/voice     # 01.* ... 11.*, one line each
    .venv/bin/python scripts/place_voice.py --self-test                      # tone bursts on the real video

`--take` is one recording (or several, their pieces numbered on) with the lines in order and a
pause between lines; it is cut at the pauses. `--lines` is a folder with one file per line. Either
way each line loses the silence at its head and tail, starts 0.3 s after its shot does (the shots
and their seconds are the SHOTS of scripts/record_demo.py, as in check_video_assets.py) and must
end 0.3 s before the shot ends: a line that runs long is sped up, up to --max-tempo, and never
cut. The mix is levelled to -16 LUFS and written beside a copy of the picture, which is not
re-encoded. The output is checked before the script says it is done; a table goes to
voice_report.txt next to it.

Exit codes: 0 written and checked; 1 a file is missing or the output failed its check; 2 the
recording did not give exactly one piece per shot (the table says what was found and what to
do); 3 a line does not fit its shot even at the top speed.

Standard library and ffmpeg/ffprobe only.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video" / "out"
VIDEO = OUT / "ask_first_pay.mp4"
VOICE = OUT / "ask_first_pay_voice.mp4"
SELFTEST = OUT / "voice_selftest.mp4"
REPORT_NAME = "voice_report.txt"
LIMIT_S = 170                 # the upload stays under 2:50 (scripts/make_video.py)
LEAD_S = 0.3                  # a line starts this long into its shot and ends this long before its end
PAD_S = 0.05                  # silence kept at the head and tail of a line
FADE_S = 0.01
MIN_PIECE_S = 0.6             # shorter than this between two pauses is a click or a cough, not a line
MIN_GAP_S = 1.2               # a pause this long splits the take: the guide asks for two seconds between
                              # lines and under one inside a line, and soft word ends make a pause measure longer
MAX_TEMPO = 1.12
KEEP_PAUSE_S = 0.3            # --tighten never leaves a pause inside a line shorter than this
RATE = 48000
FRAME_S = 0.01
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
# What the silence detector listens to: the recording's loudness envelope (speech band, rectified,
# smoothed), so that one loud sample of room noise cannot break a pause.
ENVELOPE_RATE = 16000
ENVELOPE = f"aresample={ENVELOPE_RATE},aformat=sample_fmts=dbl,highpass=f=100,aeval=abs(val(0)),lowpass=f=25"
FLOOR_DB = -120.0
VOICE_PCT, QUIET_PCT = 90, 10  # the recording's voice level and its quiet level: percentiles of the envelope
UNDER_VOICE_DB = 20           # default threshold: this far under the voice ...
OVER_QUIET_DB = 10            # ... and at least this far over the quiet level
EDGE_OVER_NOISE_DB = 6        # a line's edges reach out to where the sound sinks into the room noise
EDGE_REACH_S = 0.6            # ... at most this far,
HEAD_BRIDGE_S = 0.03          # ... stepping over gaps this short before the line
TAIL_BRIDGE_S = 0.15          # ... and this short after it (the closure before a final "k" or "t")
ONSET_TOLERANCE_S = 0.08      # --self-test: each burst must start this close to its second


class Stop(Exception):
    """End the run with an exit code and a message for the person at the keyboard."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Window:
    n: int
    slug: str
    start: float              # where the line starts in the video
    length: float             # the longest the line may be


@dataclass(frozen=True)
class Piece:
    src: Path                 # a mono 48 kHz wav in the work folder
    start: float
    end: float
    name: str = ""            # the recording it came from
    still: tuple = ()         # the stretches of plain room noise in that recording, (start, end)

    @property
    def length(self) -> float:
        return self.end - self.start

    def pauses(self) -> list[tuple[float, float]]:
        """The silences inside the line, clear of its two ends."""
        return [(a, b) for a, b in self.still if a >= self.start + 0.1 and b <= self.end - 0.1]


@dataclass(frozen=True)
class Fit:
    drops: tuple              # stretches of pause to take out (--tighten), (start, end) in the recording
    length: float             # the line without them, before any speed-up
    need: float               # the speed that would make it fit its window
    tempo: float | None       # the speed to use; None when `need` is over the cap


def shots() -> list[tuple]:
    spec = importlib.util.spec_from_file_location("record_demo", ROOT / "scripts" / "record_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [(n, slug, seconds) for n, slug, seconds, *_ in mod.SHOTS]


def windows(shot_rows: list[tuple]) -> list[Window]:
    out, at = [], 0
    for n, slug, seconds in shot_rows:
        out.append(Window(n, slug, at + LEAD_S, seconds - 2 * LEAD_S))
        at += seconds
    return out


def ffmpeg(args: list[str], level: str = "error", text: bool = True) -> subprocess.CompletedProcess:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-y", "-v", level, *args]
    r = subprocess.run(cmd, capture_output=True, text=text, errors="replace" if text else None)
    if r.returncode:
        err = r.stderr if text else r.stderr.decode(errors="replace")
        raise Stop(1, f"ffmpeg failed:\n  {' '.join(cmd)}\n{err.strip()[-600:]}")
    return r


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    if r.returncode or not r.stdout.strip():
        raise Stop(1, f"cannot read {path}: {r.stderr.strip()[-300:]}")
    return float(r.stdout.strip())


def to_wav(src: Path, dst: Path) -> Path:
    """Any recording ffmpeg reads (m4a, mp3, wav, ogg, a video ...) as mono 48 kHz PCM."""
    if not src.is_file():
        raise Stop(1, f"no such recording: {src}")
    ffmpeg(["-i", str(src), "-vn", "-map", "0:a:0", "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(dst)])
    return dst


def read_pcm(wav: Path, start: float = 0.0, length: float | None = None) -> array:
    with wave.open(str(wav), "rb") as w:
        first = min(w.getnframes(), round(start * RATE))
        w.setpos(first)
        pcm = array("h")
        pcm.frombytes(w.readframes(w.getnframes() - first if length is None else round(length * RATE)))
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm


def write_pcm(wav: Path, pcm: array) -> None:
    if sys.byteorder == "big":
        pcm = array("h", pcm)
        pcm.byteswap()
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def envelope(wav: Path) -> list[float]:
    """The loudness of the recording, one value in dB for every 10 ms: the peak of ENVELOPE in
    that frame, which is what silencedetect compares with its threshold."""
    raw = ffmpeg(["-i", str(wav), "-vn", "-af", ENVELOPE, "-f", "f32le", "-c:a", "pcm_f32le", "-"], text=False).stdout
    samples = array("f")
    samples.frombytes(raw[:len(raw) - len(raw) % 4])
    if sys.byteorder == "big":
        samples.byteswap()
    step = round(ENVELOPE_RATE * FRAME_S)
    floor = 10 ** (FLOOR_DB / 20)
    return [20 * math.log10(max(floor, max(samples[i:i + step]))) for i in range(0, len(samples), step)]


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct / 100))]


def silences(wav: Path, db: float, total: float, min_s: float = 0.25) -> list[tuple[float, float]]:
    """Every stretch of at least `min_s` where the envelope stays under `db` (ffmpeg silencedetect)."""
    log = ffmpeg(["-i", str(wav), "-vn", "-af", f"{ENVELOPE},silencedetect=noise={db:.1f}dB:d={min_s}",
                  "-f", "null", "-"], level="info").stderr
    out, start = [], None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", log):
        t = min(total, max(0.0, float(m[2])))
        if m[1] == "start":
            start = t
        elif start is not None:
            out.append((start, t))
            start = None
    if start is not None:                               # the recording ends inside a silence
        out.append((start, total))
    return out


def runs(flags: list[bool]) -> list[tuple[int, int]]:
    """(first, one past last) of every run of true values."""
    out, start = [], None
    for i, flag in enumerate([*flags, False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i))
            start = None
    return out


def split(quiet: list[tuple[float, float]], total: float, min_gap: float,
          min_piece: float = MIN_PIECE_S) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """The sound between pauses: a silence splits the recording when it lasts `min_gap` or touches
    either end. Returns (pieces, ignored): anything shorter than `min_piece` is ignored."""
    ends = [(0.0 if a <= 0.02 else a, total if b >= total - 0.02 else b) for a, b in quiet]
    cuts = [(a, b) for a, b in ends if b - a >= min_gap or a == 0.0 or b == total]
    marks = [0.0] + [t for ab in cuts for t in ab] + [total]
    spans = [(marks[i], marks[i + 1]) for i in range(0, len(marks), 2) if marks[i + 1] - marks[i] > 0.001]
    return ([s for s in spans if s[1] - s[0] >= min_piece], [s for s in spans if s[1] - s[0] < min_piece])


def edges(env: list[float], a: float, b: float, high: float, low: float, lo: float, hi: float) -> tuple[float, float]:
    """Where the sound in (a, b) really starts and ends. First inwards to the first and last frame
    over `high`; then outwards while the frames are still over `low` (the quiet start of an "s",
    the "k" after its closure), never past (lo, hi), EDGE_REACH_S, or a gap over the bridge."""
    i, j = max(0, round(a / FRAME_S)), min(len(env), round(b / FRAME_S))
    while i < j and env[i] <= high:
        i += 1
    while j > i and env[j - 1] <= high:
        j -= 1
    reach = round(EDGE_REACH_S / FRAME_S)
    start, k, gap = i, i - 1, 0
    while k >= max(0, math.ceil(lo / FRAME_S)) and i - k <= reach and gap <= round(HEAD_BRIDGE_S / FRAME_S):
        start, gap = (k, 0) if env[k] > low else (start, gap + 1)
        k -= 1
    end, k, gap = j, j, 0
    while k < min(len(env), int(hi / FRAME_S)) and k - j < reach and gap <= round(TAIL_BRIDGE_S / FRAME_S):
        end, gap = (k + 1, 0) if env[k] > low else (end, gap + 1)
        k += 1
    return start * FRAME_S, end * FRAME_S


@dataclass
class Found:
    """What the silence detector made of one recording."""
    name: str
    total: float
    voice: float              # envelope levels, dB
    noise: float
    db: float                 # the threshold used
    auto: bool
    quiet: list               # every silence of 0.25 s or more (under `db`): where the take can split
    still: tuple              # every 0.25 s or more at room-noise level: what --tighten may shorten
    pieces: list              # Piece, with PAD_S at each end
    ignored: list             # (start, end) of sounds too short to be a line


def find(wav: Path, name: str, silence_db: float | None, min_gap: float) -> Found:
    """Cut one recording at its pauses."""
    env = envelope(wav)
    if not env:
        raise Stop(1, f"{name}: the recording is empty")
    total = len(env) * FRAME_S
    voice, guess = percentile(env, VOICE_PCT), percentile(env, QUIET_PCT)
    db = silence_db if silence_db is not None else max(voice - UNDER_VOICE_DB, guess + OVER_QUIET_DB)
    quiet = silences(wav, db, total, min(0.25, min_gap))
    # the room noise, measured inside the silences just found (their edges left out)
    calm = [x for a, b in quiet for x in env[round((a + 0.15) / FRAME_S):round((b - 0.15) / FRAME_S)]]
    noise = percentile(calm, 50) if calm else guess
    low = min(db, max((percentile(calm, 95) if calm else guess) + EDGE_OVER_NOISE_DB, db - 30))
    still = tuple((a * FRAME_S, b * FRAME_S) for a, b in runs([x <= low for x in env]) if (b - a) * FRAME_S >= 0.25)
    spans, ignored = split(quiet, total, min_gap)
    pieces = []
    for n, (a, b) in enumerate(spans):
        lo = (spans[n - 1][1] + a) / 2 if n else 0.0
        hi = (b + spans[n + 1][0]) / 2 if n + 1 < len(spans) else total
        s, e = edges(env, a, b, db, low, lo, hi)
        pieces.append(Piece(wav, max(lo, s - PAD_S), min(hi, e + PAD_S), name, still))
    return Found(name, total, voice, noise, db, silence_db is None, quiet, still, pieces, ignored)


def describe(f: Found, min_gap: float) -> str:
    text = (f"{f.name}: {f.total:.1f} s; voice {f.voice:.1f} dB, room noise {f.noise:.1f} dB; "
            f"under {f.db:.1f} dB{' (auto)' if f.auto else ''} is silence, {min_gap:g} s of it is a pause")
    if f.voice - f.noise < 20:
        text += "\n  the room noise is close to the voice: if the pieces look wrong, record nearer the phone"
    for a, b in f.ignored:
        text += f"\n  ignored a {b - a:.2f} s sound at {a:.1f} s (shorter than {MIN_PIECE_S} s)"
    return text


def pieces_table(pieces: list[Piece]) -> str:
    rows = ["piece   start  length  pause after  recording"]
    for i, p in enumerate(pieces):
        nxt = pieces[i + 1] if i + 1 < len(pieces) and pieces[i + 1].src == p.src else None
        gap = f"{nxt.start - p.end:11.2f}" if nxt else " " * 11
        rows.append(f"{i + 1:5d} {p.start:7.2f} {p.length:7.2f}  {gap}  {p.name}")
    return "\n".join(rows)


def gap_hint(found: list[Found], want: int, min_gap: float) -> float | None:
    """A --min-gap that would give exactly `want` pieces, the nearest one to the gap in use."""
    grid = [round(0.3 + 0.1 * k, 1) for k in range(38)]                    # 0.3 .. 4.0 s
    good = [g for g in grid if sum(len(split(f.quiet, f.total, g)[0]) for f in found) == want]
    return min(good, key=lambda g: abs(g - min_gap)) if good else None


def parse_pick(text: str, pieces: list[Piece]) -> list[Piece]:
    """`1,2,4` keeps those pieces, in that order, as lines 1, 2, 3; `2+3` joins neighbours into one line."""
    out = []
    for item in text.split(","):
        try:
            nums = [int(x) for x in item.split("+")]
        except ValueError:
            raise Stop(2, f"--pick: {item!r} is not a piece number") from None
        if any(not 1 <= n <= len(pieces) for n in nums):
            raise Stop(2, f"--pick: there is no piece {item} (the recording has {len(pieces)})")
        first, last = pieces[nums[0] - 1], pieces[nums[-1] - 1]
        if nums != list(range(nums[0], nums[0] + len(nums))) or first.src != last.src:
            raise Stop(2, f"--pick: {item} must join neighbouring pieces of one recording, like 2+3")
        out.append(Piece(first.src, first.start, last.end, first.name, first.still))
    return out


def from_takes(takes: list[Path], work: Path, want: int, silence_db: float | None, min_gap: float,
               pick: str | None, log: list[str]) -> list[Piece]:
    found = [find(to_wav(t, work / f"take{i}.wav"), t.name, silence_db, min_gap) for i, t in enumerate(takes)]
    log += [describe(f, min_gap) for f in found]
    pieces = [p for f in found for p in f.pieces]
    chosen = parse_pick(pick, pieces) if pick else pieces
    if len(chosen) == want:
        return chosen
    hint = gap_hint(found, want, min_gap)
    gives = f"--min-gap {hint:g} (gives exactly {want} pieces; now {min_gap:g})" if hint else \
        f"--min-gap S (a pause of S seconds splits the take; now {min_gap:g})"
    lines = log + [f"found {len(pieces)} pieces" + (f", --pick keeps {len(chosen)}" if pick else "")
                   + f"; the video has {want} lines", pieces_table(pieces), "what to do:"]
    if len(pieces) > want:
        lines += ["  a line was said twice (two pieces of about the same length in a row): keep one,",
                  "      --pick 1,2,4,...     the pieces to use, in the order of the lines",
                  "  a line broke in two at a long pause (two short pieces in a row): join them,",
                  f"      --pick 1,2+3,4,...   or split only at longer pauses: {gives}"]
    else:
        lines += ["  two lines ran together (a piece about as long as two): split at shorter pauses,",
                  f"      {gives}",
                  "  or say the missing lines in a second recording and choose the pieces,",
                  "      --take first.m4a second.m4a --pick ...   (its pieces are numbered after the first's)"]
    lines.append(f"  in a noisy room the pauses can hide: --silence-db {max(f.db for f in found) + 6:.0f} "
                 f"raises what counts as silence (now {max(f.db for f in found):.1f} dB)")
    raise Stop(2, "\n".join(lines))


def from_lines(folder: Path, work: Path, rows: list[Window], silence_db: float | None, min_gap: float,
               log: list[str]) -> list[Piece]:
    """One file per line, NN.*: each is trimmed to its first and last sound (inner pauses stay)."""
    if not folder.is_dir():
        raise Stop(1, f"no such folder: {folder}")
    files, missing = [], []
    for w in rows:
        hits = sorted(p for p in folder.glob(f"{w.n:02d}.*") if p.is_file())
        if len(hits) == 1:
            files.append(hits[0])
        else:
            missing.append(f"  {w.n:02d}.*: " + (", ".join(h.name for h in hits) or "missing"))
    if missing:
        raise Stop(2, f"{folder} needs exactly one file per line, {rows[0].n:02d}.* to {rows[-1].n:02d}.*:\n"
                   + "\n".join(missing))
    out = []
    for path in files:
        f = find(to_wav(path, work / f"line{path.stem}.wav"), path.name, silence_db, min_gap)
        log.append(describe(f, min_gap))
        if not f.pieces:
            raise Stop(2, f"{path.name}: no voice found (nothing over {f.db:.1f} dB for {MIN_PIECE_S} s)")
        out.append(Piece(f.pieces[0].src, f.pieces[0].start, f.pieces[-1].end, path.name, f.still))
    return out


def fit(piece: Piece, window: float, max_tempo: float, tighten: bool = False) -> Fit:
    """How the line gets into its window: as it is; with --tighten, by taking the middle out of
    its pauses (no more than needed, each keeps KEEP_PAUSE_S); then by speeding it up, up to
    `max_tempo`. Never by cutting sound."""
    drops, length = (), piece.length
    room = [(a, b, b - a - KEEP_PAUSE_S) for a, b in piece.pauses() if b - a > KEEP_PAUSE_S] if tighten else []
    have = sum(r for *_, r in room)
    if length > window and have > 0:
        share = min(1.0, (length - window + 0.02) / have)
        drops = tuple(((a + b - r * share) / 2, (a + b + r * share) / 2) for a, b, r in room)
        length -= have * share
    need = length / window
    if need <= 1:
        return Fit(drops, length, need, 1.0)
    if need > max_tempo + 1e-9:
        return Fit(drops, length, need, None)
    return Fit(drops, length, need, min(max_tempo, math.ceil(length / (window - 0.02) * 1000) / 1000))


def render(piece: Piece, how: Fit, dst: Path) -> float:
    """Copy the line out of its recording (without `how.drops`), fade every cut end, speed it up
    if asked. Returns its length in seconds."""
    pcm = read_pcm(piece.src, piece.start, piece.length)
    line, at, ramp = array("h"), 0, round(FADE_S * RATE)
    for a, b in [*how.drops, (piece.end, piece.end)]:
        part = pcm[at:round((a - piece.start) * RATE)]
        at = round((b - piece.start) * RATE)
        for k in range(min(ramp, len(part) // 2)):
            part[k] = int(part[k] * k / ramp)
            part[-1 - k] = int(part[-1 - k] * k / ramp)
        line.extend(part)
    if how.tempo == 1:
        write_pcm(dst, line)
    else:
        raw = dst.with_name(dst.stem + "_raw.wav")
        write_pcm(raw, line)
        ffmpeg(["-i", str(raw), "-af", f"atempo={how.tempo:.3f}", "-ar", str(RATE), "-ac", "1",
                "-c:a", "pcm_s16le", str(dst)])
    return len(read_pcm(dst)) / RATE


def write_track(lines: list[tuple[Path, float]], total: float, dst: Path) -> None:
    """One mono track as long as the video: silence, with each line copied in at its second."""
    track = array("h", bytes(2 * round(total * RATE)))
    for wav, start in lines:
        pcm, at = read_pcm(wav), round(start * RATE)
        pcm = pcm[:max(0, len(track) - at)]
        track[at:at + len(pcm)] = pcm
    write_pcm(dst, track)


def mux(video: Path, track: Path, out: Path, total: float) -> None:
    """The picture copied as it is, the voice levelled and encoded beside it."""
    ffmpeg(["-i", str(video), "-i", str(track), "-filter_complex",
            f"[1:a]aformat=channel_layouts=stereo,{LOUDNORM},aresample={RATE},apad,atrim=end={total:.3f}[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE),
            "-ac", "2", "-movflags", "+faststart", "-f", "mp4", str(out)])


def picture_md5(path: Path) -> str:
    return ffmpeg(["-i", str(path), "-map", "0:v", "-c", "copy", "-f", "md5", "-"]).stdout.strip()


def loudness(path: Path) -> tuple[float, float]:
    """(mean volume in dB, integrated loudness in LUFS) of the file's audio."""
    log = ffmpeg(["-i", str(path), "-vn", "-af", "volumedetect,ebur128=framelog=verbose", "-f", "null", "-"],
                 level="info").stderr
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    lufs = re.findall(r"\bI:\s+(-?[\d.]+) LUFS", log)
    return (float(mean[1]) if mean else FLOOR_DB, float(lufs[-1]) if lufs else FLOOR_DB)


def check(video: Path, out: Path) -> tuple[list[str], str]:
    """What is wrong with the file just written (nothing, one hopes), and one line of facts."""
    src, got = duration(video), duration(out)
    md5, (mean, lufs) = picture_md5(out), loudness(out)
    errs = []
    if abs(got - src) > 0.1:
        errs.append(f"it lasts {got:.2f} s, the video {src:.2f} s")
    if got >= LIMIT_S:
        errs.append(f"it lasts {got:.2f} s, the limit is under {LIMIT_S} s")
    if md5 != picture_md5(video):
        errs.append("its picture is not the video's picture, packet for packet")
    if mean < -60:
        errs.append(f"its audio is silent (mean volume {mean:.1f} dB)")
    facts = (f"{got:.2f} s (video {src:.2f} s, limit under {LIMIT_S} s); picture identical ({md5}); "
             f"audio {lufs:.1f} LUFS, mean volume {mean:.1f} dB")
    return errs, facts


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def table(rows: list[Window], lengths: list[float], tempos: list[float], cap: float) -> str:
    """line, where it starts, how long it is, its window, its speed (! = over the cap), what is left."""
    out = ["line  shot            start  length  window  tempo  slack"]
    for w, length, tempo in zip(rows, lengths, tempos):
        out.append(f"{w.n:4d}  {w.slug:<13} {clock(w.start):>7} {length:7.2f} {w.length:7.2f}  {tempo:5.2f}"
                   f"{'!' if tempo > cap + 1e-9 else ' '}{w.length - length:6.2f}")
    return "\n".join(out)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return path.name


def place(lines: list[Piece], rows: list[Window], video: Path, out: Path, work: Path, max_tempo: float,
          tighten: bool, log: list[str]) -> None:
    """Fit every line to its window, mix, write `out` and check it; the table goes to `log`."""
    total = duration(video)
    if rows[-1].start + rows[-1].length > total + 0.05:
        raise Stop(1, f"{video.name} lasts {total:.1f} s, shorter than the shot list")
    fits = [fit(p, w.length, max_tempo, tighten) for p, w in zip(lines, rows)]
    late = [(w, f) for w, f in zip(rows, fits) if f.tempo is None]
    if late:
        ways = [] if tighten else ["  --tighten         first shortens the pauses inside a line that runs long "
                                   "(no word is touched)"]
        ways.append(f"  --max-tempo {math.ceil(max(f.need for f in fits) * 100) / 100:.2f}  would fit every line "
                    f"as it is (now {max_tempo:g}; a voice stays clear up to about 1.25)")
        ways.append("  or say those lines again, brisker, in a second recording, and choose its pieces with --pick\n"
                    "  (--take first.m4a second.m4a: the second recording's pieces are numbered after the first's)")
        raise Stop(3, "\n".join(
            log + [table(rows, [f.length for f in fits], [max(1.0, f.need) for f in fits], max_tempo)]
            + [f"line {w.n} ({w.slug}) does not fit: it lasts {f.length:.2f} s and its shot leaves {w.length:.2f} s; "
               f"at the top speed x{max_tempo:g} it is still {f.length / max_tempo - w.length:.2f} s too long"
               for w, f in late]
            + ["nothing was written: a line is never cut. Ways out:"] + ways))
    wavs = [work / f"placed{w.n:02d}.wav" for w in rows]
    lengths = [render(p, f, wav) for p, f, wav in zip(lines, fits, wavs)]
    track = work / "track.wav"
    write_track([(wav, w.start) for wav, w in zip(wavs, rows)], total, track)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")          # `out` appears only once it has passed the check
    try:
        mux(video, track, part, total)
        errs, facts = check(video, part)
        if errs:
            raise Stop(1, "\n".join(log + ["the mix failed its check, nothing was written:"] + [f"  {e}" for e in errs]))
        part.replace(out)
    finally:
        part.unlink(missing_ok=True)
    log.append(table(rows, lengths, [f.tempo for f in fits], max_tempo))
    for p, w, f in zip(lines, rows, fits):
        did = ([f"pauses shortened by {p.length - f.length:.2f} s"] if f.drops else []) \
            + ([f"sped up x{f.tempo:.3f}"] if f.tempo > 1 else [])
        if did:
            log.append(f"line {w.n} ({w.slug}) ran long: " + ", ".join(did))
    log.append(f"checked: {facts}")


def make_test_take(path: Path, bursts: list[float], gaps: float | list[float] = 2.0, lead: float = 1.5,
                   noise: float = 0.004, voice: bool = False) -> list[float]:
    """A stand-in for a recording, made with ffmpeg: one burst per entry (a tone, a different
    pitch each; with `voice`, pink noise pulsing like syllables), its gap of silence after it,
    and steady pink noise underneath (0.004 is about -62 dBFS, 0.016 about -50). Returns where
    each burst starts."""
    gaps = gaps if isinstance(gaps, list) else [gaps] * len(bursts)
    cmd, parts, starts, at = [], [], [], lead
    for i, (d, gap) in enumerate(zip(bursts, gaps)):
        sound = (f"anoisesrc=color=pink:amplitude=0.5:sample_rate={RATE}:duration={d}:seed={i + 1},tremolo=f=4.5:d=0.95"
                 if voice else f"sine=frequency={300 + 50 * i}:sample_rate={RATE}:duration={d}")
        cmd += ["-f", "lavfi", "-i", sound]
        head = f"adelay={round(lead * 1000)}," if i == 0 else ""
        parts.append(f"[{i}:a]{head}apad=pad_dur={gap}[b{i}]")
        starts.append(at)
        at += d + gap
    cmd += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude={noise}:sample_rate={RATE}:duration={at}:seed=99"]
    parts.append("".join(f"[b{i}]" for i in range(len(bursts))) + f"concat=n={len(bursts)}:v=0:a=1[tones]")
    parts.append(f"[tones][{len(bursts)}:a]amerge=inputs=2,pan=mono|c0=c0+c1[a]")
    ffmpeg(cmd + ["-filter_complex", ";".join(parts), "-map", "[a]", str(path)])
    return starts


def onsets(media: Path, work: Path, db: float = -40.0) -> list[float]:
    """Where sound starts in the file's audio, after at least 0.2 s of silence."""
    wav = to_wav(media, work / "heard.wav")
    total = duration(wav)
    return [b for _, b in silences(wav, db, total, 0.2) if b < total - 0.02]


def self_test(rows: list[Window], video: Path, out: Path, work: Path, max_tempo: float, log: list[str]) -> None:
    """Tone bursts of different lengths through the whole path, then listen to the result: every
    burst must start within ONSET_TOLERANCE_S of its line's second (one burst is too long for its
    window on purpose, so the speed-up runs too)."""
    bursts = [round(w.length * (0.62 + 0.03 * (i % 7)), 2) for i, w in enumerate(rows)]
    tight = min(range(len(rows)), key=lambda i: rows[i].length)
    bursts[tight] = round(rows[tight].length * 1.06, 2)
    take = work / "selftest_take.m4a"
    make_test_take(take, bursts)
    lines = from_takes([take], work, len(rows), None, MIN_GAP_S, None, log)
    place(lines, rows, video, out, work, max_tempo, False, log)
    heard = onsets(out, work)
    offsets = [min((abs(t - w.start) for t in heard), default=math.inf) for w in rows]
    errs = [f"line {w.n}: no burst starts within {ONSET_TOLERANCE_S * 1000:.0f} ms of {clock(w.start)}"
            for w, off in zip(rows, offsets) if off >= ONSET_TOLERANCE_S]
    if len(heard) != len(rows):
        errs.append(f"{len(heard)} bursts heard in the output, {len(rows)} placed")
    if errs:
        raise Stop(1, "\n".join(log + ["self-test FAILED:"] + [f"  {e}" for e in errs]))
    log.append(f"self-test: {len(rows)} bursts heard, each starts within {ONSET_TOLERANCE_S * 1000:.0f} ms "
               f"of its second (largest offset {max(offsets) * 1000:.0f} ms)")


def run(a: argparse.Namespace, shot_rows: list[tuple]) -> int:
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise Stop(1, f"{tool} is not installed")
    out = a.out or (SELFTEST if a.self_test else VOICE)
    if not a.video.is_file():
        raise Stop(1, f"no video at {a.video}: build it with scripts/make_video.py")
    if out.resolve() == a.video.resolve():
        raise Stop(1, "--out is the video itself; choose another name")
    rows = windows(shot_rows)
    print("cutting, fitting, mixing and checking: about half a minute ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="place_voice_") as tmp:
        work = Path(tmp)
        if a.self_test:
            log = [f"{rel(out)}: self-test, tone bursts on {rel(a.video)}"]
            self_test(rows, a.video, out, work, a.max_tempo, log)
        elif a.take:
            log = [f"{rel(out)}: take {', '.join(t.name for t in a.take)}" + (f", --pick {a.pick}" if a.pick else "")
                   + f" on {rel(a.video)}"]
            lines = from_takes(a.take, work, len(rows), a.silence_db, a.min_gap, a.pick, log)
            place(lines, rows, a.video, out, work, a.max_tempo, a.tighten, log)
        else:
            log = [f"{rel(out)}: lines in {a.lines.name}/ on {rel(a.video)}"]
            lines = from_lines(a.lines, work, rows, a.silence_db, a.min_gap, log)
            place(lines, rows, a.video, out, work, a.max_tempo, a.tighten, log)
    report = "\n".join(log)
    print(report)
    (out.parent / REPORT_NAME).write_text(report + "\n", encoding="utf-8")
    print(f"wrote {rel(out)} and {rel(out.parent / REPORT_NAME)}: play it once, start to finish, with sound")
    return 0


def main(argv=None, shot_rows: list[tuple] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--take", type=Path, nargs="+", metavar="FILE",
                     help="one recording with every line in order and a pause between lines")
    src.add_argument("--lines", type=Path, metavar="FOLDER", help="a folder with one file per line: 01.* 02.* ...")
    src.add_argument("--self-test", action="store_true", help="place tone bursts on the video and check them")
    ap.add_argument("--pick", metavar="1,2,4,...", help="with --take: the pieces to use, in line order; 2+3 joins two")
    ap.add_argument("--silence-db", type=float, metavar="DB",
                    help=f"what counts as silence (default: {UNDER_VOICE_DB} dB under the recording's voice, "
                         f"at least {OVER_QUIET_DB} dB over its quiet parts)")
    ap.add_argument("--min-gap", type=float, default=MIN_GAP_S, metavar="S",
                    help=f"a pause this long splits the take (default {MIN_GAP_S})")
    ap.add_argument("--max-tempo", type=float, default=MAX_TEMPO, metavar="X",
                    help=f"how much a line that runs long may be sped up (default {MAX_TEMPO})")
    ap.add_argument("--tighten", action="store_true",
                    help=f"shorten the pauses inside a line that runs long (down to {KEEP_PAUSE_S} s) before speeding it up")
    ap.add_argument("--video", type=Path, default=VIDEO, help="the video to put the voice on")
    ap.add_argument("--out", type=Path, help=f"default {VOICE.name} (self-test: {SELFTEST.name}), next to the video")
    a = ap.parse_args(argv)
    if a.pick and not a.take:
        ap.error("--pick needs --take")
    try:
        return run(a, shot_rows if shot_rows is not None else shots())
    except Stop as stop:
        print(stop.message, file=sys.stdout if stop.code in (2, 3) else sys.stderr)
        return stop.code


if __name__ == "__main__":
    sys.exit(main())
