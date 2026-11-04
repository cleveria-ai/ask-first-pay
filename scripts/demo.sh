#!/usr/bin/env bash
# One command: starts the Ask First Pay demo (uvicorn) and prints the owner pairing code.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi
exec .venv/bin/python -m ask_first_pay.demo   # runs uvicorn on $HOST:$PORT (default 127.0.0.1:8000)
