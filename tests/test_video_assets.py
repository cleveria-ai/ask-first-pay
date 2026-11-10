"""The video assets agree with each other and fit the 3-minute rule; record_demo plans offline."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_shotlist_subtitles_and_recorder_agree_and_fit_in_180_s():
    check = load("check_video_assets")
    errs, total = check.problems()
    assert errs == [] and total <= 180


def test_a_shotlist_over_three_minutes_or_out_of_sync_fails(tmp_path, monkeypatch):
    check = load("check_video_assets")
    text = check.SHOTLIST.read_text(encoding="utf-8").replace("| 10 | 9 | 2:30-2:39 |", "| 10 | 30 | 2:30-3:00 |")
    bad = tmp_path / "SHOTLIST.md"
    bad.write_text(text, encoding="utf-8")
    monkeypatch.setattr(check, "SHOTLIST", bad)
    errs, total = check.problems()
    assert total == 180 and any("record_demo.SHOTS" in e for e in errs)
    assert any("Total:" in e for e in errs)


def test_subtitles_are_regenerated_identically():
    check = load("check_video_assets")
    assert check.build_srt(check.shots()) == check.SRT.read_text(encoding="utf-8")


def test_cues_are_short_enough_to_read():
    check = load("check_video_assets")
    for _, _, text in check.parse_srt(check.SRT.read_text(encoding="utf-8")):
        assert len(text) <= check.MAX_CUE_CHARS


def test_record_demo_dry_run_needs_no_browser(capsys):
    rec = load("record_demo")
    assert rec.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count(".webm") == 10 and "total 159 s (2:39)" in out
    assert rec.SIZE == {"width": 1280, "height": 720}


def test_record_demo_records_every_shot_once_and_says_what_runs():
    """Every shot is recorded (in story order), the in-process demo is the video-safe one, and the
    clips carry the honest note that the scripted model runs."""
    rec = load("record_demo")
    assert sorted(rec.RECORD_ORDER) == [n for n, *_ in rec.SHOTS]
    assert rec.RECORD_ORDER.index(4) < rec.RECORD_ORDER.index(1)      # the cold open needs shot 4's booking
    src = (ROOT / "scripts" / "record_demo.py").read_text(encoding="utf-8")
    assert 'os.environ["ASK_FIRST_VIDEO"] = "1"' in src and "ASK_FIRST_TZ" in src
    assert "scripted model" in rec.DISCLOSURE and "scripted model" in rec.closing_card()


def test_no_third_party_marks_in_what_the_recorder_draws():
    rec = load("record_demo")
    drawn = (rec.STAGE + rec.answer_card() + rec.closing_card() + rec.DISCLOSURE).lower()
    for mark in ("claude", "anthropic", "ag grid", "whatsapp", "chrome", "alexa"):
        assert mark not in drawn
