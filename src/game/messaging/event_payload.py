"""Centralized event payload shaping for wire and replay serialization.

Defines helpers that produce the canonical dict shape for ServiceEvent payloads.
Both the session broadcaster and the replay collector reuse these helpers so
serialization logic is defined once.
"""

from __future__ import annotations

from typing import Any

from game.logic.events import BroadcastTarget, SeatTarget, ServiceEvent


def service_event_payload(event: ServiceEvent) -> dict[str, Any]:
    """Return the wire-format dict for a ServiceEvent payload.

    Shape: {"type": event.event, **data_fields} with internal-only fields
    ("type" and "target" on the domain model) excluded.
    """
    return {"type": event.event, **event.data.model_dump(exclude={"type", "target"})}


def service_event_target(event: ServiceEvent) -> str:
    """Return a string representation of the event's routing target.

    "all" for BroadcastTarget, "seat_{n}" for SeatTarget.
    """
    if isinstance(event.target, BroadcastTarget):
        return "all"
    if isinstance(event.target, SeatTarget):
        return f"seat_{event.target.seat}"
    raise ValueError(f"Unknown target type: {type(event.target)}")
