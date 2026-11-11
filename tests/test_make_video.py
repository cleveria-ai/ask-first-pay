"""scripts/make_video.py cuts each raw clip to its slot, never changes speed, and builds an H.264 +
AAC file and a contact sheet with ffmpeg, offline (synthetic clips, no browser, no network)."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_video", ROOT / "scripts" / "make_video.py")
mv = importlib.util.module_from_spec(spec)
sys.modules["make_video"] = mv                     # dataclasses look the module up
spec.loader.exec_module(mv)

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg not installed")


def fake_raw(tmp_path, rows, lengths, heads):
    for (n, slug, _), length, head in zip(rows, lengths, heads):
        (tmp_path / f"{n:02d}-{slug}.webm").write_bytes(b"")
        if head is not None:
            (tmp_path / f"{n:02d}-{slug}.json").write_text(json.dumps({"head_s": head}))
    by_name = {f"{n:02d}-{slug}.webm": length for (n, slug, _), length in zip(rows, lengths)}
    return lambda p: by_name[p.name]


def test_make_video_plan_cuts_each_shot_from_its_recorded_start(tmp_path):
    rows = [(1, "a", 10), (2, "b", 14), (3, "c", 9)]
    dur = fake_raw(tmp_path, rows, lengths=[13.0, 15.5, 7.0], heads=[2.5, 1.2, 0.8])
    cuts = mv.plan(rows, tmp_path, duration=dur)
    assert [(c.start, c.at, c.seconds) for c in cuts] == [(2.5, 0, 10), (1.2, 10, 14), (0.8, 24, 9)]
    assert [c.hold for c in cuts] == [0, 0, 2.8]          # clip 3 ends early: its last frame is held


def test_make_video_without_timing_takes_the_seconds_before_the_tail(tmp_path):
    rows = [(1, "a", 10)]
    cuts = mv.plan(rows, tmp_path, duration=fake_raw(tmp_path, rows, [14.0], [None]))
    assert cuts[0].start == pytest.approx(14.0 - 10 - mv.TAIL_S)


def test_make_video_refuses_a_missing_clip_or_a_cut_over_the_limit(tmp_path):
    with pytest.raises(SystemExit, match="missing raw clip"):
        mv.plan([(1, "a", 10)], tmp_path, duration=lambda p: 12.0)
    rows = [(1, "a", 100), (2, "b", 70)]
    with pytest.raises(SystemExit, match="under 170"):
        mv.plan(rows, tmp_path, duration=fake_raw(tmp_path, rows, [101, 71], [0.5, 0.5]))


def test_make_video_real_shots_fit_the_script():
    rows = mv.shots()
    assert [r[0] for r in rows] == list(range(1, 12))
    assert sum(r[2] for r in rows) == 167 < mv.LIMIT_S <= 170 < 180      # the rules: under 3:00


def test_make_video_command_is_h264_aac_1080p_and_never_changes_speed(tmp_path):
    rows = [(1, "a", 10), (2, "b", 6)]
    cuts = mv.plan(rows, tmp_path, duration=fake_raw(tmp_path, rows, [12.0, 9.0], [1.5, 2.0]))
    cmd = mv.ffmpeg_command(cuts, tmp_path / "x.mp4")
    joined = " ".join(cmd)
    assert cmd[cmd.index("-c:v") + 1] == "libx264" and cmd[cmd.index("-c:a") + 1] == "aac"
    assert "anullsrc" in joined and "scale=1920:1080" in joined and "-pix_fmt yuv420p" in joined
    assert "-ss 1.500 -t 10.000" in joined and "-ss 2.000 -t 6.000" in joined
    assert "trim=duration=10" in joined and "trim=duration=6" in joined
    for speed in ("atempo", "setpts=0.", "setpts=2", "*PTS", "PTS/"):
        assert speed not in joined
    # the narration is burned in, large, bottom centre, in a box, from the shot list's subtitles
    assert f"subtitles=filename='{mv.SRT}'" in joined
    for style in ("PlayResY=1080", "Fontsize=44", "BorderStyle=3", "Alignment=2", "WrapStyle=2"):
        assert style in joined
    assert "subtitles=" not in " ".join(mv.ffmpeg_command(cuts, tmp_path / "x.mp4", srt=None))
    with pytest.raises(SystemExit, match="plain path"):
        mv.narration_filter(Path("/tmp/a:b.srt"))


def gray_max(video, t, crop):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                          "-vf", f"crop={crop},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=True).stdout
    return max(raw)


@needs_ffmpeg
def test_make_video_builds_a_real_file_and_contact_sheet(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    rows = [(1, "red", 2), (2, "blue", 1)]
    for (n, slug, _), length in zip(rows, [3, 0.5]):     # the second clip is shorter than its slot
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        f"color=c={slug}:s=320x180:r=25:d={length}", "-c:v", "libvpx", "-b:v", "200k",
                        str(raw / f"{n:02d}-{slug}.webm")], check=True)
        (raw / f"{n:02d}-{slug}.json").write_text(json.dumps({"head_s": 0.5 if n == 1 else 0}))
    srt = tmp_path / "n.srt"
    srt.write_text("1\n00:00:00,100 --> 00:00:01,500\nNine twelve.\n", encoding="utf-8")
    video, sheet, cuts = mv.make(raw, out, rows, size=(320, 180), tile=(160, 90), srt=srt)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height",
                            "-show_entries", "format=duration", "-of", "json", str(video)],
                           capture_output=True, text=True, check=True)
    info = json.loads(probe.stdout)
    codecs = {s["codec_name"] for s in info["streams"]}
    assert codecs == {"h264", "aac"}
    v = next(s for s in info["streams"] if s["codec_name"] == "h264")
    assert (v["width"], v["height"]) == (320, 180)
    assert float(info["format"]["duration"]) == pytest.approx(3.0, abs=0.15)
    assert cuts[1].hold == pytest.approx(0.5, abs=0.05)
    # white narration text at the bottom while the cue runs, none after it (the clips are flat colour)
    assert gray_max(video, 0.8, "200:40:60:140") > 200
    assert gray_max(video, 2.5, "200:40:60:140") < 120
    assert sheet.exists() and sheet.stat().st_size > 0
    sp = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                         str(sheet)], capture_output=True, text=True, check=True)
    assert sp.stdout.strip() == "320,90"                  # two tiles side by side


def test_make_video_voice_over_guide_matches_the_shot_list():
    """VOICE_OVER.md: each line is the shot list's "Say", starts 0.3 s into its shot, and the
    per-shot mix places each file there; the upload is public and not made for kids."""
    import re
    spec2 = importlib.util.spec_from_file_location("check_video_assets", ROOT / "scripts" / "check_video_assets.py")
    check = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(check)
    guide = (ROOT / "docs" / "video" / "VOICE_OVER.md").read_text(encoding="utf-8")
    rows = {int(m[1]): (m[2], m[3]) for m in re.finditer(r"^\| (\d+) \| (\d:\d\d\.\d) \| [^|]+ \| ([^|]+) \|$",
                                                        guide, re.M)}
    at = 0
    for shot in check.shots():
        start, say = rows[shot["n"]]
        m, s = start.split(":")
        assert int(m) * 60 + float(s) == pytest.approx(at + 0.3), shot["n"]
        assert say.strip() == shot["say"], shot["n"]
        assert f"[{shot['n']}:a]adelay={at * 1000 + 300}:all=1" in guide
        at += shot["seconds"]
    assert "ask_first_pay_voice.mp4" in guide and "-c:v copy" in guide
    assert "**Public**" in guide and "not made for kids" in guide
