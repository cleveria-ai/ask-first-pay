# ask-first-mandate

A small, dependency-light Python library so **any** tool server (MCP or not) can *ask first*
before an agent does something consequential:

- **Mandate**: a scoped (action + recipient), capped, time-limited, **single-use** grant that the
  person signs with Ed25519.
- **Ledger**: a hash-chained, append-only JSON-lines file of every attempt, accepted or rejected,
  that anyone can verify for continuity.
- **Receipt**: a server-signed proof of what was executed, covering the mandate, the action and
  the ledger row hash.

It is the open-source core extracted from "Ask First for Alexa+", our entry to the Amazon
Developer Hackathon 2026 (Alexa+ track). It has no dependency on MCP, on any web framework or on
the demo.

Prior work, declared as the rules require: identity signing and the hash-chained ledger are
ported from the public repository `soyharso/agent-identity-firma` (August 2026) and significantly
extended here; the single-use mandate itself is new in this project.

## Install

Requires Python 3.11+ and a **POSIX** system: the ledger takes its lock with `fcntl.flock`, so it
does not run on Windows. Runtime dependencies: `cryptography` and `rfc8785` only.

From this directory (`libs/ask-first-mandate/`), with its own virtual environment: the demo's
`.venv` at the repository root does not install this package, so running the tests with it fails
with `No module named 'ask_first'`.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Use

```python
from ask_first import Ledger, MandateEngine, MandateRejected, Receipt, generate_pair, sign_envelope

person_priv, person_pub = generate_pair()            # in real life: the person's device

def executor(mandate, requested):                    # YOUR consequential action, injected
    return {"paid": requested["amount"], "to": requested["recipient"]}

engine = MandateEngine(person_pub=person_pub, ledger=Ledger("ledger.jsonl"), executor=executor)

mandate = engine.request("assistant", "pay", "water-company", 40.0, ttl_s=300)   # asks, does nothing
engine.approve(mandate["jti"], sign_envelope(person_priv, engine.pending[mandate["jti"]]))

result = engine.execute(mandate["jti"], "pay", "water-company", 40.0)   # runs the executor once
Receipt.verify(result["receipt"], engine.server_pub_hex())              # (True, "ok")

try:
    engine.execute(mandate["jti"], "pay", "water-company", 40.0)        # second use
except MandateRejected as e:
    print(e.reason)                                                      # "replay"

engine.view_ledger()["verification"]["ok"]                               # True
```

## API

| Name | What it is |
|---|---|
| `MandateEngine(person_pub, ledger, executor)` | `request`, `approve`, `execute`, `get`, `view_ledger`, `new_pairing_code`, `pair`, `server_pub_hex` |
| `Mandate` | `dict` subclass; `Mandate.create(agent, action, recipient, amount, ttl_s)` |
| `Ledger(path)` | `append(row)`, `verify(expected_head=None)`, `entries()`, `raw_rows()` |
| `Receipt` | `Receipt.emit(...)`, `Receipt.verify(receipt, server_pub_hex=None)` |
| `MandateRejected` | `.reason` is one of `not_approved`, `signature_tampered`, `replay`, `expired`, `out_of_scope`, `over_cap`, `executor_failed`, `invalid_signature`, `unknown` (plus pairing: `unknown_code`, `code_used`, `code_expired`, `invalid_key`) |
| `Executor` | `Callable[[mandate: dict, requested: dict], Any]`; `requested` is `{"action", "recipient", "amount"}` |
| `generate_pair`, `sign_envelope`, `verify_signature`, `public_key_hex`, `public_key_from_hex` | Ed25519 helpers over RFC 8785 canonical JSON |

Names differ from the demo's Spanish originals (`Motor` -> `MandateEngine`, `libro` -> `Ledger`,
`recibo` -> `Receipt`, `tope` -> `cap`); the logic is the same.

## Guarantees and limits

- The executor is called **at most once per mandate**: the engine holds one global lock over
  "check, mark used, execute", and marks the mandate used *before* calling the executor, so a
  failing executor still spends the mandate. Covered by a 32-thread race test.
- The approved mandate's signature is re-verified at every `execute`, so a field changed after
  signing (cap, recipient, expiry) is rejected as `signature_tampered`.
- An amount is valid only if it is finite and greater than zero: `Mandate.create` raises
  `ValueError` for NaN, inf, zero or negative amounts, and `execute` rejects them as `over_cap`
  (detail `invalid amount`) before calling the executor and without spending the mandate
  (`tests/test_amounts.py`).
- The ledger proves **continuity** (nothing deleted, reordered or altered), not authenticity;
  authenticity comes from the signatures. A lock not obtained within the budget diverts the row
  to a `.partial.<pid>.jsonl` file rather than writing unlocked.
- Rows removed from the END of the ledger are invisible to the chain alone. Keep the last row's
  `{"n", "hash"}` outside the ledger file and pass it as `Ledger.verify(expected_head=...)`:
  a mismatch is reported as kind `truncated` (`tests/test_truncation.py`). Without it, truncation
  is not detected.
- The engine keeps pending/approved/used state **in memory**: it is single-process and does not
  survive a restart. Persisting it is up to the embedding server.
- A mandate bounds the signed plan, not the agent's intent; a quick signature is not informed
  consent. The short time-to-live and the cap bound the damage, they do not remove it.
- Keys are generated by the caller and never stored by the library.

## License

Apache-2.0, see `LICENSE`.
