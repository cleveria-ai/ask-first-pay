"""The engine: the logic of requesting, approving and executing a single-use mandate, apart from
any transport so a tool server of any kind (MCP or not) can embed it.

Hard limits of the design (not promised here): a mandate bounds the signed PLAN, not the agent's
intent in general; and a quick signature is not, by itself, informed consent -- the short
time-to-live and the cap bound the damage, they do not remove it.
"""
from __future__ import annotations

import math
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ask_first.canonical import digest_hex
from ask_first.keys import (
    generate_pair,
    public_key_from_hex,
    public_key_hex,
    verify_signature,
)
from ask_first.ledger import Ledger
from ask_first.receipt import Receipt

VERSION = "1"
MAX_PAIR_FAILURES = 10     # wrong/used/expired codes tolerated before every outstanding code is revoked


def _valid_amount(amount: Any) -> bool:
    """An amount is valid only if it is a finite number greater than zero (NaN, inf are not)."""
    if isinstance(amount, bool):
        return False
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value > 0

# The action with consequences is the caller's: it receives the mandate and the requested
# action ({"action", "recipient", "amount"}) and returns the result that goes in the response.
Executor = Callable[[dict, dict], Any]


class Mandate(dict):
    """A mandate is a plain JSON-able dict (so it signs and serializes as is) with a builder."""

    @classmethod
    def create(cls, agent: str, action: str, recipient: str, amount: float,
               ttl_s: int = 300) -> "Mandate":
        if not _valid_amount(amount):
            raise ValueError("amount must be positive and finite")
        if ttl_s <= 0:
            raise ValueError("ttl_s must be positive")
        now = int(time.time())
        mandate = cls(
            version=VERSION,
            jti=uuid.uuid4().hex,
            iss="person",
            sub=agent,
            action=action,
            recipient=recipient,
            cap=float(amount),
            created=now,
            exp=now + int(ttl_s),
        )
        mandate["plan_hash"] = digest_hex(
            {"action": action, "recipient": recipient, "cap": float(amount)}
        )
        return mandate


class MandateRejected(Exception):
    """An action under a mandate was rejected. `reason` is one of the five kill-test classes:
    replay, over_cap, expired, out_of_scope, signature_tampered -- plus `not_approved` /
    `unknown` / `invalid_signature` / `executor_failed` for the cases that precede or follow
    those five.
    """

    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


@dataclass
class MandateEngine:
    person_pub: Ed25519PublicKey
    ledger: Ledger
    executor: Executor
    pending: dict[str, dict] = field(default_factory=dict)
    approved: dict[str, dict] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    pairing_codes: dict[str, dict] = field(default_factory=dict)
    # The SERVER's key to sign receipts -- distinct from `person_pub` (the approver's).
    # Ephemeral in memory if nobody sets it.
    server_priv: Ed25519PrivateKey = field(default_factory=lambda: generate_pair()[0])
    # GLOBAL engine lock: covers "check -> mark used" in `execute` and `pair`, and the executor
    # call. A per-mandate lock is not enough when the executor touches state shared across ALL
    # mandates (measured in the demo: 32 distinct mandates at once lost or corrupted payments
    # without it).
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _pair_failures: int = field(default=0, repr=False, compare=False)

    def request(self, agent: str, action: str, recipient: str, amount: float,
                ttl_s: int = 300) -> dict:
        """The agent ASKS for a mandate. It authorizes nothing: it only records the request,
        pending the person's signature.
        """
        mandate = Mandate.create(agent, action, recipient, amount, ttl_s)
        self.pending[mandate["jti"]] = mandate
        return dict(mandate)

    def server_pub_hex(self) -> str:
        return public_key_hex(self.server_priv.public_key())

    def new_pairing_code(self, ttl_s: int = 600) -> str:
        """A short, single-use, short-lived code so the person's device can register its public
        key. Show it on the server console -- never send it over the network.
        """
        code = secrets.token_hex(4)
        with self._lock:
            self._pair_failures = 0                      # a fresh code gets a fresh allowance of guesses
            self.pairing_codes[code] = {"exp": int(time.time()) + int(ttl_s), "used": False}
        return code

    def pair(self, code: str, device_pub_hex: str) -> str:
        """Registers the public key the device generated as the person's key, using a
        single-use code. A second attempt with the same code is rejected.
        """
        with self._lock:
            entry = self.pairing_codes.get(code) if isinstance(code, str) else None
            failure = None
            if entry is None:
                failure = MandateRejected("unknown_code", f"the code {code!r} does not exist")
            elif entry["used"]:
                failure = MandateRejected("code_used", f"the code {code!r} was already used: "
                                                       f"it is single-use")
            elif int(time.time()) > entry["exp"]:
                failure = MandateRejected("code_expired", f"the code {code!r} has expired")
            if failure is not None:
                # The code is 32 bits and the endpoint is open: bound the guessing. After
                # MAX_PAIR_FAILURES misses every outstanding code is revoked; the owner asks the
                # console for a new one.
                self._pair_failures += 1
                if self._pair_failures >= MAX_PAIR_FAILURES:
                    self.pairing_codes.clear()
                raise failure
            try:
                pub = public_key_from_hex(device_pub_hex)
            except ValueError as e:
                raise MandateRejected("invalid_key", str(e)) from e
            entry["used"] = True
            self.person_pub = pub
            return public_key_hex(pub)

    def get(self, mandate_id: str) -> dict | None:
        """The mandate, to show it on the approval screen, with its current state."""
        if mandate_id in self.approved:
            mandate = dict(self.approved[mandate_id]["mandate"])
            mandate["_state"] = "used" if mandate_id in self.used else "approved"
            return mandate
        mandate = self.pending.get(mandate_id)
        if mandate is None:
            return None
        mandate = dict(mandate)
        mandate["_state"] = "pending"
        return mandate

    def approve(self, mandate_id: str, signature_hex: str) -> dict:
        """The person approves ONCE, signing the pending mandate exactly as it was requested."""
        mandate = self.pending.get(mandate_id)
        if mandate is None:
            raise MandateRejected("unknown", f"no pending mandate {mandate_id}")
        if not verify_signature(self.person_pub, mandate, signature_hex):
            raise MandateRejected(
                "invalid_signature",
                "the signature does not match the person's key over this exact mandate",
            )
        self.approved[mandate_id] = {"mandate": dict(mandate), "signature": signature_hex}
        return dict(mandate)

    def _log(self, mandate_id: str, result: str, reason: str | None,
             extra: dict[str, Any]) -> dict:
        row = {"ts": int(time.time()), "mandate_id": mandate_id, "result": result,
               "reason": reason}
        row.update(extra)
        return self.ledger.append(row)

    def execute(self, mandate_id: str, action: str, recipient: str, amount: float) -> dict:
        """Runs the executor ONLY if the mandate is approved, still matches its signature, has
        not expired, was not used before, and the requested action/recipient/amount fit what
        was authorized. Every attempt -- accepted or rejected -- lands in the ledger.
        """
        with self._lock:
            approval = self.approved.get(mandate_id)
            if approval is None:
                self._log(mandate_id, "rejected", "not_approved", {})
                raise MandateRejected("not_approved",
                                      f"{mandate_id} has no recorded approval")

            mandate = approval["mandate"]
            signature = approval["signature"]

            # The signature is re-verified over the CURRENT content of the approved mandate,
            # not over a flag cached at approval: if anything altered a field afterwards (cap,
            # recipient, exp...) those bytes are no longer what the person signed.
            if not verify_signature(self.person_pub, mandate, signature):
                self._log(mandate_id, "rejected", "signature_tampered",
                          {"plan_hash": mandate.get("plan_hash")})
                raise MandateRejected("signature_tampered",
                                      "the approved mandate no longer matches its signature")

            if mandate_id in self.used:
                self._log(mandate_id, "rejected", "replay", {"plan_hash": mandate["plan_hash"]})
                raise MandateRejected("replay", f"{mandate_id} was already used: single-use")

            if int(time.time()) > int(mandate["exp"]):
                self._log(mandate_id, "rejected", "expired", {"plan_hash": mandate["plan_hash"]})
                raise MandateRejected("expired", f"{mandate_id} expired at {mandate['exp']}")

            if action != mandate["action"] or recipient != mandate["recipient"]:
                self._log(mandate_id, "rejected", "out_of_scope",
                          {"plan_hash": mandate["plan_hash"]})
                raise MandateRejected("out_of_scope",
                                      "the requested action or recipient are not the "
                                      "authorized ones")

            if not _valid_amount(amount):
                self._log(mandate_id, "rejected", "over_cap",
                          {"plan_hash": mandate["plan_hash"], "detail": "invalid amount"})
                raise MandateRejected("over_cap", f"invalid amount: {amount!r} (must be finite "
                                                  f"and greater than zero)")

            if float(amount) > float(mandate["cap"]):
                self._log(mandate_id, "rejected", "over_cap", {"plan_hash": mandate["plan_hash"]})
                raise MandateRejected("over_cap", f"{amount} exceeds the cap {mandate['cap']}")

            # Marked used BEFORE executing: if the executor fails, the mandate stays spent (it
            # is not silently "un-used" to allow a second try) and the ledger row says
            # "failed", not "executed".
            self.used.add(mandate_id)
            requested = {"action": action, "recipient": recipient, "amount": float(amount)}
            try:
                outcome = self.executor(dict(mandate), requested)
            except Exception as e:                                # noqa: BLE001
                self._log(mandate_id, "failed", "executor_failed",
                          {"plan_hash": mandate["plan_hash"]})
                raise MandateRejected("executor_failed", str(e)) from e
            row = self._log(mandate_id, "executed", None,
                            {**requested, "plan_hash": mandate["plan_hash"]})
            receipt = Receipt.emit(self.server_priv, mandate, action, recipient, amount, row)
            return {"result": "executed", "row": row, "outcome": outcome, "receipt": receipt}

    def view_ledger(self) -> dict:
        return {"entries": self.ledger.entries(), "verification": self.ledger.verify()}
