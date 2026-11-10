"""Keep the video assets in step: docs/video/SHOTLIST.md, docs/video/subtitles.srt and
scripts/record_demo.py must name the same shots with the same seconds, the total must be at most
165 s (2:45), and each shot's subtitles must say exactly its "Say" text inside its time window.

    .venv/bin/python scripts/check_video_assets.py              # check; exit 1 on any problem
    .venv/bin/python scripts/check_video_assets.py --write-srt  # regenerate subtitles.srt
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOTLIST = ROOT / "docs" / "video" / "SHOTLIST.md"
SRT = ROOT / "docs" / "video" / "subtitles.srt"
LIMIT_S = 165          # the work order caps this cut at 2:45 (the rules allow 3:00)
MAX_WPS = 3.2            # faster than this is not narration, it is a race
MAX_CUE_CHARS = 84       # two lines of 42


def shots(path: Path | None = None) -> list[dict]:
    rows = []
    for line in (path or SHOTLIST).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append({"n": int(cells[0]), "seconds": int(cells[1]), "window": cells[2],
                     "show": cells[3], "say": cells[4], "clip": cells[5].strip("`")})
    return rows


def record_demo_shots() -> list[tuple]:
    spec = importlib.util.spec_from_file_location("record_demo", ROOT / "scripts" / "record_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SHOTS


def ts(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def parse_ts(s: str) -> float:
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def chunks(text: str) -> list[str]:
    """Sentences, and sentences longer than a cue split at commas/semicolons, then by words."""
    out = []
    for sent in re.split(r"(?<=[.?!])\s+", text.strip()):
        parts = [sent]
        if len(sent) > MAX_CUE_CHARS:
            parts = [p for p in re.split(r"(?<=[,;:])\s+", sent)]
        buf = ""
        for p in parts:
            if buf and len(buf) + 1 + len(p) > MAX_CUE_CHARS:
                out.append(buf)
                buf = p
            else:
                buf = f"{buf} {p}".strip()
        while len(buf) > MAX_CUE_CHARS:
            cut = buf.rfind(" ", 0, MAX_CUE_CHARS)
            out.append(buf[:cut])
            buf = buf[cut + 1:]
        if buf:
            out.append(buf)
    return out


def wrap(cue: str) -> str:
    if len(cue) <= 42:
        return cue
    mid = len(cue) // 2
    cut = min((i for i, c in enumerate(cue) if c == " "), key=lambda i: abs(i - mid))
    return cue[:cut] + "\n" + cue[cut + 1:]


def build_srt(rows: list[dict]) -> str:
    cues, start = [], 0.0
    for r in rows:
        parts = chunks(r["say"])
        lead, usable = 0.3, r["seconds"] - 0.6          # a breath at each cut
        total = sum(len(p) for p in parts)
        t = start + lead
        for p in parts:
            d = usable * len(p) / total
            cues.append((t, t + d - 0.05, p))
            t += d
        start += r["seconds"]
    return "\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{wrap(text)}\n" for i, (a, b, text) in enumerate(cues, 1))


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        a, b = (parse_ts(x.strip()) for x in lines[1].split("-->"))
        cues.append((a, b, " ".join(lines[2:])))
    return cues


def norm(s: str) -> str:
    return " ".join(s.split())


def problems() -> tuple[list[str], int]:
    rows, errs = shots(), []
    total = sum(r["seconds"] for r in rows)
    if [r["n"] for r in rows] != list(range(1, len(rows) + 1)) or not rows:
        errs.append(f"shots must be numbered 1..N, got {[r['n'] for r in rows]}")
    if total > LIMIT_S:
        errs.append(f"total {total} s > {LIMIT_S} s")
    claimed = re.search(r"\*\*Total: (\d+) s", SHOTLIST.read_text(encoding="utf-8"))
    if not claimed or int(claimed.group(1)) != total:
        errs.append(f"the 'Total:' line does not say {total} s")
    rec = record_demo_shots()
    if [(n, s) for n, _, s, _ in rec] != [(r["n"], r["seconds"]) for r in rows]:
        errs.append("record_demo.SHOTS and SHOTLIST.md disagree on shots or seconds")
    for (n, slug, _, _), r in zip(rec, rows):
        if r["clip"] != f"{n:02d}-{slug}.webm":
            errs.append(f"shot {n}: clip {r['clip']!r} is not {n:02d}-{slug}.webm")
    start = 0
    for r in rows:
        a, b = (x.strip() for x in r["window"].split("-"))
        mm = lambda s: int(s.split(":")[0]) * 60 + int(s.split(":")[1])         # noqa: E731
        if (mm(a), mm(b)) != (start, start + r["seconds"]):
            errs.append(f"shot {r['n']}: window {r['window']} is not {start}-{start + r['seconds']} s")
        wps = len(r["say"].split()) / r["seconds"]
        if wps > MAX_WPS:
            errs.append(f"shot {r['n']}: {wps:.1f} words/s is too fast to say")
        start += r["seconds"]
    if not SRT.exists():
        errs.append(f"missing {SRT.relative_to(ROOT)}")
        return errs, total
    cues = parse_srt(SRT.read_text(encoding="utf-8"))
    prev = 0.0
    for a, b, _ in cues:
        if not prev <= a < b:
            errs.append(f"cue at {ts(a)} overlaps or runs backwards")
        prev = b
    if cues and cues[-1][1] > total:
        errs.append(f"subtitles run past {total} s")
    start = 0
    for r in rows:
        said = norm(" ".join(t for a, b, t in cues if start <= a and b <= start + r["seconds"]))
        if said != norm(r["say"]):
            errs.append(f"shot {r['n']}: subtitles do not match its Say text")
        start += r["seconds"]
    return errs, total


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="check the video assets")
    ap.add_argument("--write-srt", action="store_true")
    a = ap.parse_args(argv)
    if a.write_srt:
        SRT.write_text(build_srt(shots()), encoding="utf-8")
        print(f"wrote {SRT.relative_to(ROOT)}")
    errs, total = problems()
    for e in errs:
        print("FAIL", e)
    if errs:
        return 1
    print(f"OK total {total} s <= {LIMIT_S} s; {len(shots())} shots; shot list, subtitles and record_demo agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
