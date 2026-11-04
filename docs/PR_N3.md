# N3: demo app (chat booking with deposit, owner approval page, ledger)

## Ladder at the start
```
PASS  K1   the whole suite is green  | 46 passed in 2.41s
FAIL  K2   the three pages answer 200 and show their key content (chat input, a pending-mandate list, the chain check)  | no tests ran in 0.00s
FAIL  K3   the no-show story captures exactly once and only after approval  | no tests ran in 0.00s
FAIL  K4   the cancellation story voids and never refunds  | no tests ran in 0.00s
FAIL  K5   a declined or replayed mandate shows as rejected on the ledger page  | no tests ran in 0.00s
FAIL  K6   the demo never moves money outside the gate  | 
FAIL  K7   one command starts the demo  | 
FAIL  K8   no external CDN at runtime  | 
d = 7/8 = 0.88
```
## Ladder at the end
```
PASS  K1   the whole suite is green  | 62 passed in 3.27s
PASS  K2   the three pages answer 200 and show their key content (chat input, a pending-mandate list, the chain check)  | 8 passed, 8 deselected in 0.39s
PASS  K3   the no-show story captures exactly once and only after approval  | 2 passed, 14 deselected in 0.13s
PASS  K4   the cancellation story voids and never refunds  | 2 passed, 14 deselected in 0.14s
PASS  K5   a declined or replayed mandate shows as rejected on the ledger page  | 3 passed, 13 deselected in 0.15s
PASS  K6   the demo never moves money outside the gate  | 
PASS  K7   one command starts the demo  | 
PASS  K8   no external CDN at runtime  | 
d = 0/8 = 0.00
```

## What I built (`src/ask_first_pay/demo/`, `scripts/demo.sh`, `tests/demo/`)
- `/chat`: WhatsApp-like page; a rule-based stub (`stub.py`) holding only `AgentGate` + `HoldDesk`. Fake checkout at `/checkout/{order}`.
- `/owner`: pending mandates from `AgentGate.describe` + signed fields; Approve/Decline. Gets `OwnerSide`. Pairing with the one-time code printed in the terminal, then an Ed25519 non-extractable WebCrypto key in IndexedDB signs the canonical (RFC 8785) bytes the server serves; the page checks the signed bytes match what is shown.
- `/ledger`: every attempt, plus the chain check.
- Scenario buttons: no-show (capture), cancellation (void), goodwill (capture then refund, two approvals). Decline makes the agent try once anyway, so the gate's rejection lands on the ledger; "replay" button does the same for a spent mandate.
- Start: `scripts/demo.sh` (prints the pairing code; env `HOST`, `PORT`, `ASK_FIRST_DEMO_LEDGER`). `PayPalProvider` is used when `PAYPAL_CLIENT_ID` is set and the module exists, else `FakeProvider`.

## AG Grid (approved by coordinator)
AG Grid Community 36.3.0, MIT (`static/vendor/AG-GRID-LICENSE.txt` copied from the npm tarball), vendored unmodified at `static/vendor/ag-grid-community.min.js` (1.9 MB), no CDN. It upgrades the `/ledger` table and the owner's mandate list; a plain accessible table is rendered server-side as the no-JS fallback and is what the tests read.

## Measured
- `pytest -q`: 62 passed (16 in tests/demo). Headless Chromium (390x844): paired with the real code, approved a no-show capture via WebCrypto, mandate left the queue, ledger showed `executed`, AG Grid rendered. Screenshots: `docs/screenshots/`.

## For the coordinator to decide
- `run_turn` (N2) is not wired: it needs a model (paid API) and did not exist on main. The stub is used; swapping is one object in `stub.py`.
- `ask_first` is not installed by `pip install -e .`; `demo.sh` sets PYTHONPATH (see `docs/CONTRACT_CHANGES.md`).
- Only one phone can pair per code and codes are only printed in the terminal (by design); restart to get a new one.
- PayPalProvider path and the PayPal return URL are untested (no adapter, no credentials).
