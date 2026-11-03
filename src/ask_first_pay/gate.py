"""The mandate gate: the ONLY way to move money.

An agent may create and authorize deposits freely (no money moves). Capturing a deposit or
refunding it is a consequential action: the agent can only *ask* for a single-use mandate, the
business owner approves it once on their phone, and only then does the gate call the provider.

Actions and what `recipient` means for each:
  capture_deposit   recipient = authorization_id   amount = what to capture (<= authorized)
  refund_deposit    recipient = capture_id         amount = what to refund (<= captured)
  void_deposit      recipient = authorization_id   amount = 0.01 (symbolic; voids move no money
                                                                  but still need the owner's yes)
"""
from __future__ import annotations

from dataclasses import asdict

from ask_first import Ledger, MandateEngine

from .ports import PaymentProvider

ACTIONS = ("capture_deposit", "refund_deposit", "void_deposit")


def make_executor(provider: PaymentProvider):
    def executor(mandate: dict, requested: dict):
        action, target, amount = requested["action"], requested["recipient"], requested["amount"]
        if action == "capture_deposit":
            return asdict(provider.capture(target, amount))
        if action == "refund_deposit":
            return asdict(provider.refund(target, amount))
        if action == "void_deposit":
            return asdict(provider.void(target))
        raise ValueError(f"unknown action {action!r}")
    return executor


def make_engine(provider: PaymentProvider, person_pub, ledger_path: str) -> MandateEngine:
    return MandateEngine(person_pub=person_pub, ledger=Ledger(ledger_path), executor=make_executor(provider))
