#!/usr/bin/env bash
# One command: starts the Ask First Pay demo (uvicorn on $PORT, default 8000) and prints the
# three URLs (chat, owner phone, ledger) and the owner pairing code. No keys needed: without
# ANTHROPIC_API_KEY the agent uses the offline scripted model; without PAYPAL_CLIENT_ID the fake provider.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi
export PYTHONPATH="libs/ask-first-mandate/src${PYTHONPATH:+:$PYTHONPATH}"   # the mandate engine lives in libs/
exec .venv/bin/python -m ask_first_pay.demo   # runs uvicorn on $HOST:$PORT (default 127.0.0.1:8000)
