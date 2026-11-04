# Contract changes requested by N3 (demo)

- `pyproject.toml`: no new dependency needed (the chat form is parsed by hand, so `python-multipart`
  is not required). If the package is ever installed non-editable, add package data for
  `ask_first_pay/demo/templates/*` and `ask_first_pay/demo/static/**`.
- `scripts/demo.sh` sets `PYTHONPATH=libs/ask-first-mandate/src` because `ask_first` is not installed by
  `pip install -e .` (pytest gets it from `pythonpath`). Consider declaring it in `pyproject.toml`.
