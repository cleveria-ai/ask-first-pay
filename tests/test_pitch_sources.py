"""The one outside figure in docs/DEVPOST.md keeps its source and says whose number it is.

The pitch may not carry a qnowa number the founder has not given. A published figure is allowed
only with its citation and a plain statement that it is not qnowa's own measurement."""
import re
from pathlib import Path

DEVPOST = Path(__file__).resolve().parents[1] / "docs" / "DEVPOST.md"
DOI = "10.1016/j.healthpol.2018.02.002"


def inspiration() -> str:
    text = DEVPOST.read_text(encoding="utf-8")
    return text.split("## Inspiration", 1)[1].split("\n## ", 1)[0]


def test_pitch_sources_no_show_figure_is_cited():
    section = inspiration()
    assert "23%" in section
    assert DOI in section, "the no-show figure must carry its DOI"
    assert "105 studies" in section


def test_pitch_sources_figure_is_not_presented_as_qnowas():
    assert re.search(r"not from\s+qnowa", inspiration()), "say the figure is not qnowa's own data"


def test_pitch_sources_no_other_percentage_in_the_pitch():
    """Any other percentage in the story section would be an unsourced number."""
    assert re.findall(r"\d+(?:\.\d+)? ?%", inspiration()) == ["23%"]
