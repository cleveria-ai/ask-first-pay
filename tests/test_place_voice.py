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
    found = pv.find(pv.to_wav(take, tmp_path / "take.wav"), take.name, None, pv.MIN_GAP_S)
    assert len(found.pieces) == 3 and found.auto                 # a 1.3 s pause is enough
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
    assert re.search(r" 1\.2\d!", said)                           # the table marks the speed it would need
    assert "--tighten" in said and "second recording" in said and "--max-tempo" not in said   # never past x1.12
    code, out = place(video, tmp_path, "--take", take, "--max-tempo", "1.3")
    assert code == 0 and out.exists()                             # the cap is still a flag, x1.12 unless told


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
def test_place_voice_a_second_recording_replaces_a_line_through_pick(video, tmp_path, capsys):
    first, second = tmp_path / "voice.m4a", tmp_path / "fix.m4a"
    pv.make_test_take(first, [2.0, 5.5, 1.5])                     # line 2 is too long for its shot
    pv.make_test_take(second, [3.0], lead=1.0)                    # the same line said again, brisker
    assert place(video, tmp_path, "--take", first, second)[0] == 2            # four pieces: say which
    assert "    4 " in capsys.readouterr().out and not (tmp_path / "voice.mp4").exists()
    code, out = place(video, tmp_path, "--take", first, second, "--pick", "1,4,3")
    assert code == 0 and "take voice.m4a, fix.m4a, --pick 1,4,3" in capsys.readouterr().out
    a, b = sounds(out, tmp_path)[1]
    assert 0 <= a - STARTS[1] < pv.ONSET_TOLERANCE_S and b - a == pytest.approx(3.0, abs=0.06)


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


@needs_ffmpeg
@pytest.mark.parametrize("bursts, gaps, lead", [
    ([2.0, 3.0, 1.5], [2.0, 2.0, 3.0], 1.5),                      # three seconds of silence after the last line
    ([2.0, 3.0, 1.5, 0.2], [2.0, 2.0, 3.0, 0.05], 1.5),           # ... and then the click of the stop button
    ([2.0, 3.0, 1.5], [2.0, 2.0, 2.0], 4.0),                      # four seconds of silence before the first line
])
def test_place_voice_silence_at_either_end_of_the_take_is_not_a_piece(tmp_path, bursts, gaps, lead):
    take = tmp_path / "take.m4a"
    starts = pv.make_test_take(take, bursts, gaps=gaps, lead=lead)
    found = pv.find(pv.to_wav(take, tmp_path / "take.wav"), take.name, None, pv.MIN_GAP_S)
    assert len(found.pieces) == 3 and len(found.ignored) == len(bursts) - 3
    assert [p.start == pytest.approx(s - pv.PAD_S, abs=0.03) for p, s in zip(found.pieces, starts)] == [True] * 3
    assert found.pieces[-1].end < starts[2] + 1.5 + 0.2          # the last line ends at its sound, not at the file's end


@needs_ffmpeg
def test_place_voice_names_the_pick_that_leaves_a_noise_out(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.4, 3.0, 2.2, 0.8], gaps=[2.0, 2.0, 3.0, 0.3])   # the phone picked up after the last line
    assert place(video, tmp_path, "--take", take)[0] == 2         # that is a sound of 0.8 s: a fourth piece
    said = capsys.readouterr().out
    assert "too short to be a line (a noise, a word said aside): piece 4." in said and "--pick 1,2,3\n" in said
    assert place(video, tmp_path, "--take", take, "--pick", "1,2,3")[0] == 0


def test_place_voice_describe_lists_only_the_short_sounds_that_are_in_no_line():
    wav = Path("take.wav")
    found = pv.Found(wav, "take.m4a", 20.0, -20.0, -60.0, -40.0, True, [], (), [], [(5.0, 5.3), (12.0, 12.4)])
    said = pv.describe(found, 1.2, [pv.Piece(wav, 1.0, 8.0)])     # pieces joined over the first sound: it is in the line
    assert "ignored a 0.40 s sound at 12.0 s (shorter than 0.6 s)" in said and "at 5.0 s" not in said


@needs_ffmpeg
def test_place_voice_lists_the_short_sounds_it_leaves_out_on_screen_and_in_the_report(video, tmp_path, capsys):
    take = tmp_path / "take.m4a"                                  # a cough between lines 1 and 2, a click at the end
    starts = pv.make_test_take(take, [2.0, 0.3, 3.0, 1.5, 0.2], gaps=[1.5, 1.5, 2.0, 3.0, 0.05])
    code, out = place(video, tmp_path, "--take", take)
    assert code == 0 and len(sounds(out, tmp_path)) == 3          # they are left out of the mix ...
    for text in (capsys.readouterr().out, (tmp_path / pv.REPORT_NAME).read_text(encoding="utf-8")):
        left = re.findall(r"ignored a (\d\.\d\d) s sound at (\d+\.\d) s \(shorter than 0\.6 s\)", text)
        assert [float(at) for _, at in left] == [pytest.approx(starts[1], abs=0.1), pytest.approx(starts[4], abs=0.1)]
        assert [float(length) for length, _ in left] == [pytest.approx(0.3, abs=0.1), pytest.approx(0.2, abs=0.1)]


@needs_ffmpeg
def test_place_voice_listens_to_the_mix_and_refuses_a_line_that_is_not_on_its_second(video, tmp_path, capsys, monkeypatch):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 3.0, 1.5], voice=True)
    code, out = place(video, tmp_path, "--take", take)
    assert code == 0
    match = re.search(r"placed: every line within 80 ms of its second in the mix \(largest offset 0 ms, "
                      r"weakest match (\d\.\d\d)\), silence at every cut", (tmp_path / pv.REPORT_NAME).read_text())
    assert float(match[1]) > 0.95 > pv.MIN_MATCH                  # the same curve: far from the refusal
    out.unlink()
    capsys.readouterr()
    track = pv.write_track                                        # a fault: line 2 lands 0.4 s late in the mix
    monkeypatch.setattr(pv, "write_track", lambda lines, total, dst: track(
        [(wav, at + (0.4 if n == 1 else 0)) for n, (wav, at) in enumerate(lines)], total, dst))
    code, out = place(video, tmp_path, "--take", take)
    err = capsys.readouterr().err
    assert code == 1 and "line 2 (two) starts 0.40 s late in the mix (it belongs at 0:04.3)" in err
    assert "line 1 (one)" not in err and "line 3 (three)" not in err
    assert not out.exists() and not list(tmp_path.glob("*.part"))


@needs_ffmpeg
def test_place_voice_refuses_a_mix_where_a_line_sounds_past_the_cut_of_its_shot(video, tmp_path, capsys, monkeypatch):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 4.6, 1.5])                      # line 2 runs to the cut at 9 s if nobody speeds it up
    monkeypatch.setattr(pv, "fit", lambda piece, window, max_tempo, tighten=False: pv.Fit((), piece.length, 1.0, 1.0))
    code, out = place(video, tmp_path, "--take", take)
    err = capsys.readouterr().err
    assert code == 1 and not out.exists() and not list(tmp_path.glob("*.part"))
    assert "line 2 (two) is still sounding at the cut that ends its shot (0:09.0)" in err
    assert "line 2 (two) came out 0.3" in err and "line 3 (three)" not in err


@needs_ffmpeg
def test_place_voice_no_listen_writes_the_mix_without_the_placement_check_and_says_so(video, tmp_path, capsys, monkeypatch):
    take = tmp_path / "take.m4a"
    pv.make_test_take(take, [2.0, 4.6, 1.5])
    monkeypatch.setattr(pv, "misplaced", lambda *a: (["line 2 (two) is not in the mix at 0:04.3 (match 0.31)"], ""))
    code, out = place(video, tmp_path, "--take", take)            # the listening says no, rightly or not
    assert code == 1 and not out.exists() and "--no-listen writes the mix" in capsys.readouterr().err
    code, out = place(video, tmp_path, "--take", take, "--no-listen")
    assert code == 0 and len(sounds(out, tmp_path)) == 3          # the way out: the file, and the fact said twice
    for text in (capsys.readouterr().out, (tmp_path / pv.REPORT_NAME).read_text(encoding="utf-8")):
        assert "placed: placement not checked (--no-listen)" in text and "picture identical" in text
    out.unlink()
    monkeypatch.setattr(pv, "fit", lambda piece, window, max_tempo, tighten=False: pv.Fit((), piece.length, 1.0, 1.0))
    code, out = place(video, tmp_path, "--take", take, "--no-listen")
    assert code == 1 and not out.exists()                         # the other checks still run: line 2 is too long
    assert "line 2 (two) came out 0.3" in capsys.readouterr().err


@needs_ffmpeg
def test_place_voice_never_shows_an_absolute_path(video, tmp_path, capsys):
    """The recording and --out may live anywhere and the report gets pasted: messages and report
    name files, or paths inside the repository, never the folders above them."""
    take, long, broken = tmp_path / "take.m4a", tmp_path / "long.m4a", tmp_path / "broken.m4a"
    pv.make_test_take(take, [2.0, 3.0, 1.5])
    pv.make_test_take(long, [2.0, 5.5, 1.5])
    broken.write_text("not a recording")
    for args, code in ((["--take", take], 0), (["--take", take, "--pick", "1,2"], 2), (["--take", long], 3),
                       (["--take", tmp_path / "nope.m4a"], 1), (["--take", broken], 1),
                       (["--lines", tmp_path / "nowhere"], 1), (["--lines", tmp_path], 2)):
        assert place(video, tmp_path, *args)[0] == code
    deep = tmp_path / ("a" * 120) / ("b" * 120)                   # ffprobe's complaint is longer than what is shown of it
    deep.mkdir(parents=True)
    (deep / "broken_video.mp4").write_text("not a video")
    assert pv.main(["--take", str(take), "--video", str(deep / "broken_video.mp4"), "--out", str(tmp_path / "v.mp4")],
                   shot_rows=SHOTS) == 1
    shown = capsys.readouterr()
    text = shown.out + shown.err + (tmp_path / pv.REPORT_NAME).read_text(encoding="utf-8")
    assert "voice.mp4: take take.m4a on video.mp4" in text and "no such recording: nope.m4a" in text
    assert "ffmpeg failed" in text and "-i broken.m4a" in text and "no such folder: nowhere" in text
    assert "cannot read broken_video.mp4: " in text and "broken_video.mp4: Invalid data" in text   # ffprobe's words
    assert "aaaa" not in text and "bbbb" not in text              # ... without the folders, even cut short
    assert str(tmp_path.parent) not in text and not re.search(r"(?<![\w.~-])/[\w.-]+/", text)
    assert pv.rel(ROOT / "docs" / "video" / "out" / "x.mp4") == "docs/video/out/x.mp4"   # inside the repository: from its root


def test_place_voice_guide_leads_with_the_one_command_and_says_how_much_room_each_line_has():
    spec2 = importlib.util.spec_from_file_location("check_video_assets", ROOT / "scripts" / "check_video_assets.py")
    check = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(check)
    guide = (ROOT / "docs" / "video" / "VOICE_OVER.md").read_text(encoding="utf-8")
    assert (guide.index("## Record once, at your own pace") < guide.index("scripts/place_voice.py --take")
            < guide.index("## The lines") < guide.index("## Other ways"))
    room = dict(re.findall(r"^\| (\d+) \| \d:\d\d\.\d \| [^|]+ \| ([^|]+) \|", guide, re.M))
    for w, shot in zip(pv.windows(pv.shots()), check.shots()):
        pace = len(shot["say"].split()) / w.length                # the words a second the line asks for
        assert room[str(w.n)].strip() == f"{w.length:.1f} s ({pace:.1f} words/s" + (", **tight**)" if pace > 2.2 else ")")
    assert "more than 2.2 words a second is marked **tight**" in guide
    script = (ROOT / "docs" / "VIDEO_SCRIPT.md").read_text(encoding="utf-8")
    assert "`scripts/place_voice.py`" in script and "×1.12 at most" in script and "never speed up the voice" not in script
