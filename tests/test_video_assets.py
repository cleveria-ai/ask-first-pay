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
    text = check.SHOTLIST.read_text(encoding="utf-8").replace("| 11 | 9 | 2:38-2:47 |", "| 11 | 22 | 2:38-3:00 |")
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
    assert out.count(".webm") == 11 and "total 167 s (2:47)" in out
    assert rec.SIZE == {"width": 1280, "height": 720}
    assert rec.VIDEO == {k: int(v * rec.SCALE) for k, v in rec.SIZE.items()} == {"width": 1920, "height": 1080}
    assert f"html{{zoom:{rec.SCALE}}}" in rec.STAGE


def test_record_demo_records_every_shot_once_and_says_what_runs():
    """Every shot is recorded (in story order), the in-process demo is the video-safe one, and the
    clips carry the honest note that the scripted model runs."""
    rec = load("record_demo")
    assert sorted(rec.RECORD_ORDER) == [n for n, *_ in rec.SHOTS]
    assert rec.RECORD_ORDER.index(4) < rec.RECORD_ORDER.index(1)      # the cold open needs shot 4's booking
    src = (ROOT / "scripts" / "record_demo.py").read_text(encoding="utf-8")
    assert 'os.environ["ASK_FIRST_VIDEO"] = "1"' in src and "ASK_FIRST_TZ" in src
    assert "scripted model" in rec.DISCLOSURE and "scripted model" in rec.closing_card()


def test_the_sandbox_still_says_what_it_is_and_shows_only_ids_from_the_record():
    """Shot 10 is the one shot that is not the offline demo: a committed screenshot, labelled as a
    screenshot, with PayPal ids that are all in docs/SANDBOX_UI_RUN.md (as capture, void, refund)."""
    import re
    rec = load("record_demo")
    record = (ROOT / rec.SANDBOX_RECORD).read_text(encoding="utf-8")
    ids = dict(re.findall(r"(Capture|Void|Refund) ([0-9A-Z]{17})", rec.SANDBOX_IDS))
    assert set(ids) == {"Capture", "Void", "Refund"}
    assert f"PayPal capture id {ids['Capture']} (COMPLETED)" in record
    assert f"PayPal authorization {ids['Void']} (VOIDED)" in record
    assert f"PayPal refund id {ids['Refund']} (COMPLETED)" in record
    date = re.search(r"\d{4}-\d\d-\d\d", rec.SANDBOX_TITLE).group(0)
    assert f"## Run {date}T" in record and "sandbox" in rec.SANDBOX_TITLE
    assert "screenshot" in rec.SANDBOX_NOTE.lower() and rec.SANDBOX_RECORD in rec.SANDBOX_NOTE
    assert rec.SANDBOX_STILL.is_file() and rec.SANDBOX_STILL.name == "12-sandbox-ledger.png"
    assert rec.SANDBOX_STILL_URL in rec.sandbox_card()
    assert "offline" in rec.closing_card() and rec.SANDBOX_RECORD in rec.closing_card()


def test_the_answer_diagram_runs_on_a_fixed_timeline_ends_still_and_stays_readable():
    """Shot 3 explains the mechanism as a diagram that builds itself: every change is a CSS
    animation with a fixed delay that keeps its end state, at most three things change at once,
    the last change ends two seconds before the shot does, and nothing is written under 24 px."""
    import re
    rec = load("record_demo")
    seconds = next(s for n, _, s, _ in rec.SHOTS if n == 3)
    beats, card = rec.ANSWER_BEATS, rec.answer_card()
    starts = [at for at, _, _ in beats]
    assert starts == sorted(starts) and starts[0] >= 0
    assert max(at + lasts for at, lasts, _ in beats) <= seconds - rec.ANSWER_STILL_S
    assert max(sum(a <= at < a + d for a, d, _ in beats) for at, _, _ in beats) <= 3
    classes = {c for quoted, bare in re.findall(r'class=(?:"([^"]*)"|([\w-]+))', rec.ANSWER_HTML)
               for c in (quoted or bare).split()}
    for at, lasts, what in beats:
        for cls, keyframes in (piece.split(":") for piece in what.split()):
            assert f".flow .{cls}{{animation:{keyframes} {lasts}s ease {at}s forwards}}" in card
            assert f"@keyframes {keyframes}{{" in rec.ANSWER_CSS and cls in classes, (cls, keyframes)
    for chance in ("<script", "infinite", "url(", "http", "random"):     # nothing but the delays
        assert chance not in card
    assert min(int(px) for px in re.findall(r"font-size:(\d+)px", rec.ANSWER_CSS)) >= 24
    assert "font:" not in rec.ANSWER_CSS and "body.card-only #wrap{visibility:hidden}" in rec.STAGE
    for text in ("Customer", "AI front desk", "PayPal", "keep", "release", "give back", "HOLD $10.00",
                 "on its own:", "books · creates the order", "holds the deposit", "$0.00 moved", "ask",
                 "Owner's phone", "Keep up to", "Approve", "single-use", "used",
                 "It can hold it. Only you can move it."):
        assert text in rec.ANSWER_HTML, text


def test_no_third_party_marks_in_what_the_recorder_draws():
    rec = load("record_demo")
    drawn = (rec.STAGE + rec.answer_card() + rec.closing_card() + rec.DISCLOSURE + rec.sandbox_card()
             + rec.SANDBOX_TITLE + rec.SANDBOX_NOTE + rec.SANDBOX_IDS).lower()
    for mark in ("claude", "anthropic", "ag grid", "whatsapp", "chrome", "alexa"):
        assert mark not in drawn
