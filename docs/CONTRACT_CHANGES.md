# Contract changes requested

## N2 (n2-agent): make `ask_first` importable outside pytest
`pip install -e '.[dev]'` installs only `src/`; `libs/ask-first-mandate/src` is on the path only
through pytest's `pythonpath`. Plain `python -c "from ask_first_pay.agent import run_turn"`
(criterion K7) and the demo scripts therefore fail with `No module named 'ask_first'`.
N2 works around it with a path fallback in `agent/__init__.py`. Suggested real fix for the
coordinator: install the library too (`pip install -e libs/ask-first-mandate` in the setup
commands, or a `[tool.setuptools]` package-dir entry in `pyproject.toml`).

## N3 (n3-demo): demo packaging

- `pyproject.toml`: no new dependency needed (the chat form is parsed by hand, so `python-multipart`
  is not required). If the package is ever installed non-editable, add package data for
  `ask_first_pay/demo/templates/*` and `ask_first_pay/demo/static/**`.
- `scripts/demo.sh` sets `PYTHONPATH=libs/ask-first-mandate/src` because `ask_first` is not installed by
  `pip install -e .` (pytest gets it from `pythonpath`). Consider declaring it in `pyproject.toml`.
