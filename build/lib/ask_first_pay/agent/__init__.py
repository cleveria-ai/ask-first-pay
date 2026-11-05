"""The front-desk agent. Public entry point: `run_turn`."""
import sys as _sys
from pathlib import Path as _Path

try:  # the mandate engine lives in libs/ and is not pip-installed by `pip install -e .`
    import ask_first  # noqa: F401
except ModuleNotFoundError:
    _lib = _Path(__file__).resolve().parents[3] / "libs" / "ask-first-mandate" / "src"
    if _lib.is_dir():
        _sys.path.insert(0, str(_lib))

from .loop import AnthropicModel, ScriptedModel, run_turn
from .state import AgentState

__all__ = ["run_turn", "AgentState", "AnthropicModel", "ScriptedModel"]
