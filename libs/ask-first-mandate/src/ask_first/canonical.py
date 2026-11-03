# Adapted from src/canonico.py of the public repository soyharso/agent-identity-firma:
# RFC 8785 in one place so signing and verification always hash the same bytes.
"""The exact form that is signed and that enters the ledger: canonical JSON, RFC 8785."""
import hashlib

import rfc8785


def canonical(envelope: dict) -> bytes:
    """The exact bytes that are signed or hashed, per RFC 8785."""
    return rfc8785.dumps(envelope)


def digest(envelope: dict) -> bytes:
    return hashlib.sha256(canonical(envelope)).digest()


def digest_hex(envelope: dict) -> str:
    return "sha256:" + digest(envelope).hex()
