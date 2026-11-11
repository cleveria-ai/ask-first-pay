"""scripts/place_voice.py cuts one free recording at its pauses, puts each line on its shot, speeds
up a line that runs long, never cuts one, and leaves the picture untouched. Offline and quick: a
12 s synthetic video, three shots, and stand-in recordings made by ffmpeg (tone bursts, pulsed
noise over a noise bed)."""
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("place_voice", ROOT / "scripts" / "place_voice.py")
pv = importlib.util.module_from_spec(spec)
sys.modules["place_voice"] = pv                    # dataclasses look the module up
spec.loader.exec_module(pv)

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg not installed")
SHOTS = [(1, "one", 4), (2, "two", 5), (3, "three", 3)]   # lines start at 0.3, 4.3, 9.3 s; windows 3.4, 4.4, 2.4 s
STARTS = [0.3, 4.3, 9.3]


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    path = tmp_path_factory.mktemp("video") / "video.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x90:r=10:d=12",
                    "-f", "lavfi", "-t", "12", "-i", "anullsrc=r=48000:cl=stereo", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def place(video, tmp_path, *args):
    """Run the command on the synthetic video; returns (exit code, output file)."""
    out = tmp_path / "voice.mp4"
    return pv.main([*map(str, args), "--video", str(video), "--out", str(out)], shot_rows=SHOTS), out


def sounds(out, tmp_path):
    """(start, end) of every sound in the output's audio."""
    wav = pv.to_wav(out, tmp_path / "out.wav")
    total = pv.duration(wav)
    quiet = pv.silences(wav, -40.0, total, 0.2)
    return [(a[1], b[0]) for a, b in zip(quiet, quiet[1:])]


def test_place_voice_windows_are_the_recorders_shots_less_a_breath_at_each_end():
    rows = pv.windows(pv.shots())
    assert [w.n for w in rows] == list(range(1, 12))
    at = 0
    for w, (_, _, seconds) in zip(rows, pv.shots()):
        assert (w.start, w.length) == (pytest.approx(at + 0.3), pytest.approx(seconds - 0.6))
        at += seconds
    assert at == 167 < pv.LIMIT_S


def test_place_voice_split_keeps_the_sound_between_pauses_and_ignores_clicks():
    quiet = [(0.0, 1.5), (4.0, 4.5), (6.0, 8.0), (8.3, 9.4), (12.0, 13.0)]
    pieces, ignored = pv.split(quiet, 13.0, min_gap=1.0)
    assert pieces == [(1.5, 6.0), (9.4, 12.0)]       # the 0.5 s pause stays inside the first piece
    assert ignored == [(8.0, 8.3)]                   # 0.3 s between two pauses: a click, not a line
    assert len(pv.split(quiet, 13.0, min_gap=0.4)[0]) == 3
    assert pv.split([], 5.0, 1.0) == ([(0.0, 5.0)], [])


def test_place_voice_pick_chooses_reorders_and_joins_pieces():
    wav = Path("take.wav")
    pieces = [pv.Piece(wav, 1.0, 3.0), pv.Piece(wav, 5.0, 8.0), pv.Piece(wav, 10.0, 11.0), pv.Piece(Path("b.wav"), 0.5, 2.0)]
    assert pv.parse_pick("1,3", pieces) == [pieces[0], pieces[2]]
    assert pv.parse_pick("4,1", pieces) == [pieces[3], pieces[0]]
    assert [(p.start, p.end) for p in pv.parse_pick("1,2+3", pieces)] == [(1.0, 3.0), (5.0, 11.0)]
    for bad in ("1,9", "one", "1+3", "3+4", "2+1"):  # no such piece; not neighbours; two recordings
        with pytest.raises(pv.Stop) as stop:
            pv.parse_pick(bad, pieces)
        assert stop.value.code == 2


def test_place_voice_fit_speeds_up_to_the_cap_and_only_tightens_pauses_when_asked():
    wav = Path("take.wav")
    assert pv.fit(pv.Piece(wav, 0.0, 3.0), 3.4, 1.12).tempo == 1.0
    long = pv.fit(pv.Piece(wav, 0.0, 3.7), 3.4, 1.12)
    assert 3.7 / 3.4 < long.tempo <= 1.12 and long.drops == ()
    over = pv.fit(pv.Piece(wav, 0.0, 4.0), 3.4, 1.12)
    assert over.tempo is None and over.need == pytest.approx(4.0 / 3.4)
    assert pv.fit(pv.Piece(wav, 0.0, 4.0), 3.4, 1.2).tempo == pytest.approx(1.184, abs=0.002)
    paused = pv.Piece(wav, 0.0, 4.0, still=((1.0, 1.9), (2.5, 2.7), (3.95, 6.0)))   # one inner pause over 0.3 s
    assert pv.fit(paused, 3.4, 1.12).tempo is None                 # not asked: pauses stay
    tight = pv.fit(paused, 3.4, 1.12, tighten=True)
    assert tight.drops == (pytest.approx((1.15, 1.75)),)           # the middle of the pause; 0.3 s of it stays
    assert tight.length == pytest.approx(3.4) and tight.tempo == pytest.approx(1.006, abs=0.002)
    assert pv.fit(pv.Piece(wav, 0.0, 3.0, still=((1.0, 1.9),)), 3.4, 1.12, tighten=True).drops == ()   # fits: untouched


@needs_ffmpeg
def test_place_voice_cuts_a_take_at_its_pauses(tmp_path):
    take = tmp_path / "take.m4a"
    starts = pv.make_test_take(take, [2.0, 3.0, 1.5], gaps=[1.3, 2.6, 1.0])
    found = pv.find(pv.to_wav(take, tmp_path / "take.wav"), take.name, None, 1.0)
    assert len(found.pieces) == 3 and found.auto
    assert found.noise + 6 < found.db < found.voice - 6          # the threshold sits between room and voice
    for piece, start, length in zip(found.pieces, starts, [2.0, 3.0, 1.5]):
        assert piece.start == pytest.approx(start - pv.PAD_S, abs=0.03)       # 50 ms of silence kept at the head
        assert 0 <= piece.end - (start + length + pv.PAD_S) < 0.1             # ... and at the tail, after the decay
    assert len(pv.find(found.pieces[0].src, take.name, None, 1.5).pieces) == 2   # --min-gap 1.5: the 1.3 s pause no longer splits


@needs_ffmpeg
def test_place_voice_puts_each_line_on_its_second_and_leaves_the_picture_alone(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 3.0, 1.5], gaps=[1.3, 2.6, 1.0])
    code, out = place(video, tmp_path, "--take", take)
    assert code == 0
    heard = sounds(out, tmp_path)
    assert len(heard) == 3
    for (a, b), start, length in zip(heard, STARTS, [2.0, 3.0, 1.5]):
        assert 0 <= a - start < pv.ONSET_TOLERANCE_S              # the 50 ms pad, then the burst
        assert b - a == pytest.approx(length, abs=0.06)
    assert pv.picture_md5(out) == pv.picture_md5(video)           # copied, not re-encoded
    assert pv.duration(out) == pytest.approx(pv.duration(video), abs=0.1)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                            "stream=codec_name,sample_rate,channels", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True, check=True)
    assert probe.stdout.strip() == "aac,48000,2"
    mean, lufs = pv.loudness(out)
    assert mean > -40 and lufs == pytest.approx(-16, abs=2.5)     # not silent; levelled
    report = (tmp_path / pv.REPORT_NAME).read_text(encoding="utf-8")
    assert "line  shot            start  length  window  tempo  slack" in report and "picture identical" in report
    assert report.strip() in capsys.readouterr().out
    assert not list(tmp_path.glob("*.part"))


@needs_ffmpeg
def test_place_voice_speeds_up_a_line_that_runs_long_and_says_so(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 4.6, 1.5])                      # line 2: 4.7 s with its pads, window 4.4 s
    code, out = place(video, tmp_path, "--take", take)
    assert code == 0
    assert "line 2 (two) ran long: sped up x1.0" in capsys.readouterr().out
    a, b = sounds(out, tmp_path)[1]
    assert 0 <= a - STARTS[1] < pv.ONSET_TOLERANCE_S
    assert b <= 9.0 - 0.3 and b - a == pytest.approx(4.6 / 1.073, abs=0.08)   # ends before the cut; nothing chopped


@needs_ffmpeg
def test_place_voice_refuses_a_line_that_cannot_fit_with_exit_code_3(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 5.5, 1.5])                      # line 2 would need x1.27
    code, out = place(video, tmp_path, "--take", take)
    said = capsys.readouterr().out
    assert code == 3 and not out.exists() and not (tmp_path / pv.REPORT_NAME).exists()
    assert "line 2 (two) does not fit: it lasts 5.6" in said and "at the top speed x1.12 it is still 0.6" in said
    enough = re.search(r"--max-tempo (1\.\d\d)  would fit every line", said)[1]
    assert 1.26 < float(enough) < 1.31 and f"{enough}!" in said   # the table marks the speed it would need
    code, out = place(video, tmp_path, "--take", take, "--max-tempo", enough)
    assert code == 0 and out.exists()                             # the way out it offers does work


@needs_ffmpeg
def test_place_voice_tighten_shortens_the_pauses_inside_a_long_line(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 2.0, 2.0, 1.5], gaps=[2.0, 0.9, 2.0, 1.0])   # line 2 is two sentences 0.9 s apart
    assert place(video, tmp_path, "--take", take)[0] == 3         # 5.0 s in a 4.4 s window: over the cap
    capsys.readouterr()
    code, out = place(video, tmp_path, "--take", take, "--tighten")
    assert code == 0
    assert "line 2 (two) ran long: pauses shortened by 0." in capsys.readouterr().out
    heard = sounds(out, tmp_path)
    assert len(heard) == 4                                        # both sentences are whole
    assert [b - a == pytest.approx(2.0, abs=0.08) for a, b in heard[1:3]] == [True, True]
    assert pv.KEEP_PAUSE_S <= heard[2][0] - heard[1][1] < 0.5     # the 0.9 s pause, down to 0.3 s of room noise
    assert heard[2][1] <= 9.0 - 0.3                               # and the line ends before its shot does


@needs_ffmpeg
def test_place_voice_wrong_number_of_pieces_is_exit_code_2_and_pick_solves_it(video, tmp_path, capsys):
    """A voice-like take: pulsed noise over a -50 dBFS noise bed, uneven pauses, line 2 said twice."""
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 3.0, 3.4, 1.5], gaps=[1.3, 3.0, 1.7, 1.0], noise=0.016, voice=True)
    code, out = place(video, tmp_path, "--take", take)
    said = capsys.readouterr().out
    assert code == 2 and not out.exists()
    assert "found 4 pieces; the video has 3 lines" in said and "piece   start  length" in said
    assert "    4 " in said and "--pick 1,2,4" in said and "--min-gap" in said
    code, out = place(video, tmp_path, "--take", take, "--pick", "1,3,4")
    assert code == 0
    heard = sounds(out, tmp_path)
    assert [0 <= a - s < pv.ONSET_TOLERANCE_S + 0.03 for (a, _), s in zip(heard, STARTS)] == [True] * 3
    assert heard[1][1] - heard[1][0] == pytest.approx(3.4, abs=0.15)          # the second saying of line 2
    assert place(video, tmp_path, "--take", take, "--pick", "1,2")[0] == 2    # two pieces for three lines


@needs_ffmpeg
def test_place_voice_takes_one_file_per_line_in_any_format(video, tmp_path, capsys):
    folder = tmp_path / "voice"
    folder.mkdir()
    for name, length in (("01.wav", 2.0), ("02.m4a", 3.0), ("03.flac", 1.5)):
        pv.make_test_take(folder / name, [length], gaps=0.8, lead=0.7)        # silence at the head and tail
    code, out = place(video, tmp_path, "--lines", folder)
    assert code == 0
    for (a, b), start, length in zip(sounds(out, tmp_path), STARTS, [2.0, 3.0, 1.5]):
        assert 0 <= a - start < pv.ONSET_TOLERANCE_S and b - a == pytest.approx(length, abs=0.06)
    (folder / "03.flac").unlink()
    capsys.readouterr()
    assert place(video, tmp_path, "--lines", folder)[0] == 2
    assert "03.*: missing" in capsys.readouterr().out


@needs_ffmpeg
def test_place_voice_self_test_runs_the_whole_path_and_checks_the_onsets(video, tmp_path, capsys):
    code, out = place(video, tmp_path, "--self-test")
    said = capsys.readouterr().out
    assert code == 0 and out.exists()
    assert "self-test: 3 bursts heard, each starts within 80 ms of its second" in said
    assert "line 3 (three) ran long: sped up" in said             # the tightest window gets an over-long burst


@needs_ffmpeg
def test_place_voice_never_writes_over_the_video_or_without_a_recording(video, tmp_path, capsys):
    before = video.read_bytes()
    assert pv.main(["--take", str(tmp_path / "nope.m4a"), "--video", str(video), "--out", str(tmp_path / "v.mp4")],
                   shot_rows=SHOTS) == 1
    assert pv.main(["--self-test", "--video", str(video), "--out", str(video)], shot_rows=SHOTS) == 1
    assert video.read_bytes() == before and not (tmp_path / "v.mp4").exists()
    assert "no such recording" in capsys.readouterr().err
