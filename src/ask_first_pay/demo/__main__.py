"""`python -m ask_first_pay.demo` -- starts the demo and prints the one-time pairing code."""
import os

import uvicorn

from .app import create_app


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    app = create_app()
    code = app.state.demo.new_pairing_code()
    print("\nAsk First Pay demo")
    print(f"  customer chat   http://{host}:{port}/chat")
    print(f"  owner phone     http://{host}:{port}/owner")
    print(f"  ledger          http://{host}:{port}/ledger")
    print(f"\n  agent model     {app.state.demo.front.model_name}"
          f"{'' if app.state.demo.front.model_name == 'Claude' else ' (set ANTHROPIC_API_KEY for Claude)'}")
    print(f"  payments        {type(app.state.demo.provider).__name__}"
          f"{' (PayPal sandbox)' if not app.state.demo.simulated else ' (offline; set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET for the sandbox)'}")
    print(f"\n  Owner pairing code (single use, shown only here): {code}\n")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
