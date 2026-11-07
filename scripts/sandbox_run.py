#!/usr/bin/env python3
"""Evidence of a real PayPal sandbox run, in two steps (a browser approves in between).

  (a) python scripts/sandbox_run.py
        Creates two USD 10.00 orders with intent AUTHORIZE: one for the no-show (capture) story and
        one for the cancellation (void) story. Prints both buyer approval links and the command
        for step (b). Writes nothing.
  (b) python scripts/sandbox_run.py --continue <capture order id> [--void-order <void order id>]
        After the buyer approved: authorizes the first order, captures it through a mandate the
        "owner" approves (an Ed25519 key made for this run only), retries the same capture with
        the same PayPal-Request-Id and records whether PayPal answered with the same capture id,
        and checks that the gate refuses to replay the mandate. Then the second order: authorize
        and void it through its own approved mandate. Without --void-order it creates the second
        order now and records PayPal's answer to authorizing it before approval (run step (b)
        again with --void-order once the buyer has approved it).
        Appends a run record to docs/SANDBOX_RUN.md: timestamps, order / authorization / capture
        ids, HTTP methods, paths and statuses. Never tokens, headers or credentials.

Credentials come only from PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in the environment; this
script never prints, logs or writes them. Sandbox only: the adapter refuses production unless
told otherwise, and this script never tells it.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "libs" / "ask-first-mandate" / "src"))

from ask_first import MandateRejected, generate_pair, sign_envelope  # noqa: E402

from ask_first_pay.gate import make_engine, split  # noqa: E402
from ask_first_pay.paypal import PayPalProvider  # noqa: E402
from ask_first_pay.ports import ProviderError  # noqa: E402

RECORD = ROOT / "docs" / "SANDBOX_RUN.md"
AMOUNT, CURRENCY = 10.00, "USD"
HEADER = """# PayPal sandbox runs

Appended by `scripts/sandbox_run.py --continue`. Each run lists the ids PayPal returned and every
HTTP call's method, path and status (never tokens, headers or credentials).
"""


class Recorder(httpx.BaseTransport):
    """Wraps the real transport and keeps (method, path, status) of each call. Nothing else."""

    def __init__(self, inner: httpx.BaseTransport | None = None) -> None:
        self.inner = inner or httpx.HTTPTransport()
        self.calls: list[tuple[str, str, int | str]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            response = self.inner.handle_request(request)
        except httpx.HTTPError as e:
            self.calls.append((request.method, request.url.path, type(e).__name__))
            raise
        self.calls.append((request.method, request.url.path, response.status_code))
        return response

    def close(self) -> None:
        self.inner.close()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_provider(recorder: Recorder) -> PayPalProvider:
    return PayPalProvider(transport=recorder)          # credentials from the environment only


def create(p: PayPalProvider, reference: str):
    return p.create_order(AMOUNT, CURRENCY, reference)     # a fresh PayPal-Request-Id per order


def step_a(p: PayPalProvider, out) -> int:
    a = create(p, f"sandbox-run-capture-{int(time.time())}")
    b = create(p, f"sandbox-run-void-{int(time.time())}")
    print(f"Capture story order {a.order_id} ({a.status}). Buyer approval link:\n  {a.approve_url}", file=out)
    print(f"Void story order {b.order_id} ({b.status}). Buyer approval link:\n  {b.approve_url}", file=out)
    print("Open both links, log in with a sandbox PERSONAL account and approve, then run:\n"
          f"  python scripts/sandbox_run.py --continue {a.order_id} --void-order {b.order_id}", file=out)
    return 0


def _approved_mandate(gate, owner, priv, action, target, amount):
    m = gate.request(action, target, amount)
    owner.approve(m["jti"], sign_envelope(priv, owner.pending[m["jti"]]))
    return m["jti"]


def step_b(p: PayPalProvider, recorder: Recorder, capture_order: str, void_order: str | None,
           record_path: Path, out) -> int:
    rec: dict = {"started": now(), "capture_order": capture_order}
    priv, pub = generate_pair()                         # this run's owner key; never stored
    ledger = Path(tempfile.mkdtemp(prefix="sandbox-run-")) / "ledger.jsonl"
    gate, owner = split(make_engine(p, pub, str(ledger)))
    ok = True
    try:
        auth = p.authorize(capture_order)
        rec["authorization"] = f"{auth.authorization_id} ({auth.status})"
        jti = _approved_mandate(gate, owner, priv, "capture_deposit", auth.authorization_id, AMOUNT)
        first = gate.execute(jti, "capture_deposit", auth.authorization_id, AMOUNT)["outcome"]
        rec["capture"] = f"{first['capture_id']} ({first['status']})"
        try:                                            # the same PayPal-Request-Id again
            again = p.capture(auth.authorization_id, AMOUNT, request_id=jti)
            rec["capture_retry"] = f"{again.capture_id} ({again.status})"
            rec["same_capture_id_on_retry"] = "yes" if again.capture_id == first["capture_id"] else "NO"
        except ProviderError as e:
            rec["capture_retry"] = f"refused: {e.code}"
            rec["same_capture_id_on_retry"] = "NO (refused)"
        try:
            gate.execute(jti, "capture_deposit", auth.authorization_id, AMOUNT)
            rec["gate_replay"] = "NOT refused"
            ok = False
        except MandateRejected as e:
            rec["gate_replay"] = f"refused: {e.reason}"
    except (ProviderError, MandateRejected) as e:
        rec["capture_story_error"] = f"{type(e).__name__}: {e}"
        ok = False

    if void_order is None:
        second = create(p, f"sandbox-run-void-{int(time.time())}")
        void_order = second.order_id
        rec["void_order_created"] = f"{second.order_id} ({second.status})"
        print(f"Second order {second.order_id} created. Buyer approval link:\n  {second.approve_url}\n"
              f"Approve it, then run again with --void-order {second.order_id}", file=out)
        # The buyer has not approved it yet, so PayPal would refuse to authorize it now: the void
        # story waits for the next run instead of recording a refusal that proves nothing.
        rec["void_story"] = f"pending: approve {second.order_id}, then run again with --void-order {second.order_id}"
    else:
        rec["void_order"] = void_order
        try:
            vauth = p.authorize(void_order)
            rec["void_authorization"] = f"{vauth.authorization_id} ({vauth.status})"
            vjti = _approved_mandate(gate, owner, priv, "void_deposit", vauth.authorization_id, 0.01)
            voided = gate.execute(vjti, "void_deposit", vauth.authorization_id, 0.01)["outcome"]
            rec["void"] = f"{voided['authorization_id']} ({voided['status']})"
        except (ProviderError, MandateRejected) as e:
            rec["void_story_error"] = f"{type(e).__name__}: {e}"
            ok = False

    rec["finished"] = now()
    rec["http"] = list(recorder.calls)
    write_record(record_path, rec)
    for k, v in rec.items():
        if k != "http":
            print(f"{k}: {v}", file=out)
    print(f"Run record appended to {record_path}", file=out)
    return 0 if ok else 1


def write_record(path: Path, rec: dict) -> None:
    lines = [f"\n## Run {rec['started']} (sandbox)\n", "| field | value |", "|---|---|"]
    lines += [f"| {k} | {str(v).replace('|', '/')} |" for k, v in rec.items() if k != "http"]
    lines += ["", "HTTP calls (method, path, status):", ""]
    lines += [f"- `{m} {path}` {status}" for m, path, status in rec["http"]]
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if new:
            f.write(HEADER)
        f.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None,
         record_path: Path = RECORD, out=None) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--continue", dest="cont", metavar="ORDER_ID", help="the approved capture-story order")
    ap.add_argument("--void-order", metavar="ORDER_ID", help="the approved void-story order")
    args = ap.parse_args(argv)
    if not (os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET")):
        print("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (sandbox) in the environment.", file=out)
        return 2
    recorder = Recorder(transport)
    p = make_provider(recorder)
    try:
        if args.cont:
            return step_b(p, recorder, args.cont, args.void_order, record_path, out)
        return step_a(p, out)
    except ProviderError as e:                         # code and PayPal's message only
        print(f"PayPal refused: {e.code}: {e.message}", file=out)
        return 1


if __name__ == "__main__":
    sys.exit(main())
