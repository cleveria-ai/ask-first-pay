"""The receipt: what the server signs when it executes an action under a mandate, so anyone can
verify it with the server's public key and nothing else. It covers the mandate, the executed
action and the hash of its ledger row, so altering any of the three breaks the signature.
"""
from __future__ import annotations

import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ask_first.keys import public_key_from_hex, public_key_hex, sign_envelope, verify_signature

VERSION = "1"


class Receipt:
    """Namespace for emitting and verifying receipts. A receipt itself is a plain dict."""

    @staticmethod
    def emit(server_priv: Ed25519PrivateKey, mandate: dict, action: str, recipient: str,
             amount: float, ledger_row: dict) -> dict:
        """Signs a receipt over the mandate, the action actually executed and the hash of the
        row that landed in the ledger for that use.
        """
        body = {
            "version": VERSION,
            "mandate_id": mandate["jti"],
            "mandate": dict(mandate),
            "action": action,
            "recipient": recipient,
            "amount": float(amount),
            "ledger_row_hash": ledger_row.get("hash"),
            "issued": int(time.time()),
            "server_pub": public_key_hex(server_priv.public_key()),
        }
        body["signature"] = sign_envelope(server_priv, body)
        return body

    @staticmethod
    def verify(receipt: dict, server_pub_hex: str | None = None) -> tuple[bool, str]:
        """(True, "ok") if `receipt` is signed by the server key. If `server_pub_hex` (a key
        known beforehand, not the one the receipt carries) is given, it must also match, so
        the receipt is not trusted only on what it says about itself.
        """
        signature = receipt.get("signature")
        if not signature:
            return False, "no_signature"
        pub_hex = receipt.get("server_pub")
        if not pub_hex:
            return False, "no_public_key"
        try:
            pub = public_key_from_hex(pub_hex)
        except ValueError:
            return False, "invalid_public_key"
        body = {k: v for k, v in receipt.items() if k != "signature"}
        if not verify_signature(pub, body, signature):
            return False, "invalid_signature"
        if server_pub_hex is not None and pub_hex != server_pub_hex:
            return False, "server_key_mismatch"
        return True, "ok"
