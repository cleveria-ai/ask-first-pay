"""docs/SUBMISSION_CHECKLIST.md names the Devpost submission the form fields were pasted into.

Whoever edits the entry before the deadline must land on the one project that already holds
the text, not start a second one. The row carries the project's own Devpost address, the same
one docs/DEVPOST.md gives, the day it was submitted, and who answered the personal questions."""
import re
from pathlib import Path

CHECKLIST = Path(__file__).resolve().parents[1] / "docs" / "SUBMISSION_CHECKLIST.md"
PROJECT_URL = re.compile(r"https://devpost\.com/software/[a-z0-9][a-z0-9-]*")


def submission_rows() -> list[str]:
    text = CHECKLIST.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith("| Devpost submission")]


def test_checklist_names_the_devpost_submission():
    rows = submission_rows()
    assert len(rows) == 1, "one row 'Devpost submission' in the form-fields table"
    found = PROJECT_URL.search(rows[0])
    assert found, "the row carries the project's devpost.com/software/ address"
    devpost = (CHECKLIST.parent / "DEVPOST.md").read_text(encoding="utf-8")
    assert found.group(0) in devpost, "the same address is the one docs/DEVPOST.md gives"


def test_checklist_submission_row_says_when_and_who():
    rows = submission_rows()
    assert rows and re.search(r"submitted on 20\d\d-\d\d-\d\d", rows[0]), "the row dates the submission"
    assert "OWNER" in rows[0], "the row says the owner gave the personal answers and accepted the terms"
