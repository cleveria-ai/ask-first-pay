"""docs/SUBMISSION_CHECKLIST.md names the Devpost draft the form fields were pasted into.

Whoever presses Submit must land on the one draft that already holds the text, not start a
second project. The row carries the project's own Devpost address and still says who submits."""
import re
from pathlib import Path

CHECKLIST = Path(__file__).resolve().parents[1] / "docs" / "SUBMISSION_CHECKLIST.md"
DRAFT_URL = re.compile(r"https://devpost\.com/software/[a-z0-9][a-z0-9-]*")


def draft_rows() -> list[str]:
    text = CHECKLIST.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith("| Devpost draft")]


def test_checklist_names_the_devpost_draft():
    rows = draft_rows()
    assert len(rows) == 1, "one row 'Devpost draft' in the form-fields table"
    found = DRAFT_URL.search(rows[0])
    assert found, "the row carries the draft's devpost.com/software/ address"
    devpost = (CHECKLIST.parent / "DEVPOST.md").read_text(encoding="utf-8")
    assert found.group(0) in devpost, "the same address is the one docs/DEVPOST.md gives"


def test_checklist_draft_row_leaves_submit_to_the_owner():
    rows = draft_rows()
    assert rows and "OWNER" in rows[0], "the draft row says the owner submits"
    assert "not submitted" in rows[0]
