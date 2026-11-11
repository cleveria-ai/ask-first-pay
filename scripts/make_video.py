"""Cut the raw clips of scripts/record_demo.py into the video to upload, with ffmpeg, offline.

    .venv/bin/python scripts/make_video.py             # docs/video/out/ask_first_pay.mp4 + contact_sheet.png
    .venv/bin/python scripts/make_video.py --dry-run   # print the cut and the ffmpeg command; touch nothing

Each raw clip (docs/video/raw/NN-slug.webm) is longer than its slot in docs/video/SHOTLIST.md: the
stage loads at its head and the recorder pads its tail. The recorder writes NN-slug.json with
`head_s` (where the shot starts in the clip), so each shot is cut from there for exactly its
seconds; a clip that ends early holds its last frame. Nothing is sped up or slowed down.

The lower thirds, the yellow caption track naming the PayPal calls, the cards and the English
subtitles for the Spanish lines are already in the clips (record_demo.py draws them). This script
adds one thing: the narration (docs/video/subtitles.srt), burned into the empty band record_demo.py
leaves at the bottom, so the video tells the story without a voice. Output: H.264 (yuv420p, 30 fps, 1920x1080) plus a silent AAC track, which
YouTube accepts; the founder's voice can be mixed in later (docs/video/VOICE_OVER.md). The
contact sheet shows the last second of every shot, labelled, so the cut can be checked without
playing it.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "docs" / "video" / "raw"
OUT = ROOT / "docs" / "video" / "out"
VIDEO_NAME = "ask_first_pay.mp4"
SHEET_NAME = "contact_sheet.png"
WIDTH, HEIGHT, FPS = 1920, 1080, 30
LIMIT_S = 170                 # strictly under 2:50 (was 2:45; raised for the 8 s sandbox still; the rules allow 3:00)
TAIL_S = 0.4                  # without a .json: the recorder's tail (last-frame still) is about this
SRT = ROOT / "docs" / "video" / "subtitles.srt"   # the narration, burned into the bottom band
BAND_PX = 138                 # the band record_demo.py leaves empty at the bottom (92 CSS px x 1.5)
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")   # contact-sheet labels only


@dataclass(frozen=True)
class Cut:
    n: int
    slug: str
    seconds: int              # the slot in SHOTLIST.md
    clip: Path
    start: float              # where the slot starts inside the raw clip
    available: float          # seconds of clip from `start` to its end
    at: int                   # where the slot starts in the final video

    @property
    def hold(self) -> float:
        """Seconds of last frame to repeat because the clip ends before the slot does."""
        return round(max(0.0, self.seconds - self.available), 3)


def shots() -> list[tuple]:
    spec = importlib.util.spec_from_file_location("record_demo", ROOT / "scripts" / "record_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [(n, slug, seconds) for n, slug, seconds, *_ in mod.SHOTS]


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def plan(shot_rows: list[tuple], raw: Path = RAW, duration=probe_duration) -> list[Cut]:
    cuts, at = [], 0
    for n, slug, seconds in shot_rows:
        clip = raw / f"{n:02d}-{slug}.webm"
        if not clip.exists():
            raise SystemExit(f"missing raw clip {clip}: run scripts/record_demo.py --shots {n}")
        total = duration(clip)
        meta = clip.with_suffix(".json")
        if meta.exists():
            start = float(json.loads(meta.read_text(encoding="utf-8"))["head_s"])
        else:                 # no timing: the shot is the last `seconds` before the tail
            start = total - seconds - TAIL_S
        start = round(min(max(0.0, start), max(0.0, total - 0.1)), 3)
        cuts.append(Cut(n, slug, seconds, clip, start, round(total - start, 3), at))
        at += seconds
    if at >= LIMIT_S:
        raise SystemExit(f"the cut runs {at} s; it must stay under {LIMIT_S} s")
    return cuts


def narration_filter(srt: Path, size=(WIDTH, HEIGHT)) -> str:
    """The narration as large white text on a near-black box, centred in the bottom band (at most
    two lines per cue: check_video_assets.py keeps cues to 2 x 42 characters)."""
    w, h = size
    k = h / HEIGHT
    style = ",".join([f"PlayResX={w}", f"PlayResY={h}", "FontName=DejaVu Sans", f"Fontsize={round(44 * k)}",
                      "PrimaryColour=&H00FFFFFF", "OutlineColour=&H14000000", "BackColour=&H14000000",
                      "BorderStyle=3", f"Outline={max(1, round(9 * k))}", "Shadow=0", "Alignment=2",
                      f"MarginV={max(1, round(14 * k))}", "WrapStyle=2"])
    path = str(srt)
    if any(c in path for c in ":'\\,;[]"):          # characters ffmpeg's filter syntax would read
        raise SystemExit(f"move the subtitles to a plain path (no : ' \\ , ; [ ]): {path}")
    return f"subtitles=filename='{path}':force_style='{style}'"


def ffmpeg_command(cuts: list[Cut], out: Path, size=(WIDTH, HEIGHT), fps=FPS,
                   srt: Path | None = SRT) -> list[str]:
    w, h = size
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for c in cuts:            # input-side seek: decode from the shot's start, read no more than it needs
        cmd += ["-ss", f"{c.start:.3f}", "-t", f"{min(c.available, c.seconds):.3f}", "-i", str(c.clip)]
    total = sum(c.seconds for c in cuts)
    cmd += ["-f", "lavfi", "-t", str(total), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    parts = []
    for i, c in enumerate(cuts):
        parts.append(
            f"[{i}:v]setpts=PTS-STARTPTS,fps={fps},"
            f"scale={w}:{h}:flags=lanczos:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0f1720,setsar=1,format=yuv420p,"
            f"tpad=stop_mode=clone:stop_duration={c.seconds},trim=duration={c.seconds},"
            f"setpts=PTS-STARTPTS[v{i}]")
    burn = f",{narration_filter(srt, size)}" if srt is not None else ""
    parts.append("".join(f"[v{i}]" for i in range(len(cuts))) + f"concat=n={len(cuts)}:v=1:a=0{burn}[v]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[v]", "-map", f"{len(cuts)}:a",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "128k", "-t", str(total), "-movflags", "+faststart", str(out)]
    return cmd


def label(c: Cut) -> str:
    end = c.at + c.seconds
    return f"{c.n}  {c.at // 60}:{c.at % 60:02d}-{end // 60}:{end % 60:02d}  {c.slug}"


def sheet_command(cuts: list[Cut], video: Path, out: Path, tile=(960, 540), cols=2) -> list[str]:
    """One frame per shot (a second before its end: the shot's result), in a grid, each labelled
    bottom right so the lower third (top left) and the caption (bottom left) stay visible."""
    tw, th = tile
    cmd = ["ffmpeg", "-v", "error", "-y"]
    for c in cuts:
        cmd += ["-ss", f"{max(0.0, c.at + c.seconds - 1):.3f}", "-i", str(video)]
    parts, cells = [], []
    for i, c in enumerate(cuts):
        text = label(c).replace(":", r"\:")
        draw = (f",drawtext=fontfile={FONT}:text='{text}':x=w-tw-12:y=h-th-12:fontsize={max(14, th // 18)}:"
                f"fontcolor=white:box=1:boxcolor=0x000000@0.75:boxborderw=8") if FONT.exists() else ""
        parts.append(f"[{i}:v]trim=end_frame=1,scale={tw}:{th}:flags=lanczos{draw}[t{i}]")
        cells.append(f"{(i % cols) * tw}_{(i // cols) * th}")
    rows = -(-len(cuts) // cols)
    parts.append("".join(f"[t{i}]" for i in range(len(cuts)))
                 + f"xstack=inputs={len(cuts)}:layout={'|'.join(cells)}:fill=0x0f1720,"
                 + f"pad={cols * tw}:{rows * th}[s]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[s]", "-frames:v", "1", str(out)]
    return cmd


def make(raw: Path = RAW, out_dir: Path = OUT, shot_rows: list[tuple] | None = None,
         size=(WIDTH, HEIGHT), tile=(960, 540), srt: Path | None = SRT) -> tuple[Path, Path, list[Cut]]:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is not installed")
    cuts = plan(shot_rows if shot_rows is not None else shots(), raw)
    out_dir.mkdir(parents=True, exist_ok=True)
    video, sheet = out_dir / VIDEO_NAME, out_dir / SHEET_NAME
    subprocess.run(ffmpeg_command(cuts, video, size, srt=srt), check=True)
    subprocess.run(sheet_command(cuts, video, sheet, tile), check=True)
    return video, sheet, cuts


def report(cuts: list[Cut]) -> str:
    lines = [f"{label(c):<34} raw {c.clip.name} from {c.start:6.2f} s"
             + (f", holds the last frame {c.hold:.2f} s" if c.hold else "") for c in cuts]
    total = sum(c.seconds for c in cuts)
    return "\n".join(lines + [f"total {total} s ({total // 60}:{total % 60:02d})"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="print the cut and the ffmpeg command")
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.dry_run:
        cuts = plan(shots(), a.raw)
        print(report(cuts))
        print(" ".join(ffmpeg_command(cuts, a.out / VIDEO_NAME)))
        return 0
    video, sheet, cuts = make(a.raw, a.out)
    print(report(cuts))
    print(f"wrote {video}\nwrote {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
