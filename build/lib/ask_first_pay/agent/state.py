"""Conversation and booking state. Plain data, JSON-friendly, owned by the caller."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentState:
    messages: list = field(default_factory=list)      # Anthropic-format conversation
    bookings: dict = field(default_factory=dict)      # booking_id -> booking dict
    mandates: dict = field(default_factory=dict)      # mandate_id -> {action,target,amount,booking_id,summary}
    owner_notes: list = field(default_factory=list)   # gate.describe text, for the owner page
