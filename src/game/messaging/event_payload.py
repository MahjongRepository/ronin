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


def shape_call_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape a CallPromptEvent payload for the wire.

    For ron/chankan: drop callers (recipient is implied by routing target).
    For meld: replace callers with available_calls containing only the
    recipient's call choices (seat is dropped since it's implied).
    """
    call_type = payload.get("call_type")

    if call_type in ("ron", "chankan"):
        callers = payload.pop("callers", [])
        if callers:
            payload["caller_seat"] = callers[0]
        return payload

    if call_type == "meld":
        callers = payload.pop("callers", [])
        if callers:
            payload["caller_seat"] = callers[0]["seat"]
        available_calls: list[dict[str, Any]] = []
        for caller in callers:
            call: dict[str, Any] = {"call_type": caller["call_type"]}
            if caller.get("options") is not None:
                call["options"] = caller["options"]
            available_calls.append(call)
        payload["available_calls"] = available_calls
        return payload

    return payload


def service_event_target(event: ServiceEvent) -> str:
    """Return a string representation of the event's routing target.

    "all" for BroadcastTarget, "seat_{n}" for SeatTarget.
    """
    if isinstance(event.target, BroadcastTarget):
        return "all"
    if isinstance(event.target, SeatTarget):
        return f"seat_{event.target.seat}"
    raise ValueError(f"Unknown target type: {type(event.target)}")
