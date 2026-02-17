"""Centralized event payload shaping for wire and replay serialization.

Defines helpers that produce the canonical dict shape for ServiceEvent payloads.
Both the session broadcaster and the replay collector reuse these helpers so
serialization logic is defined once.
"""

from __future__ import annotations

from typing import Any

from game.logic.events import DiscardEvent, DrawEvent, RoundEndEvent, ServiceEvent

# Fields on win result models that are omitted when None (not applicable).
_WIN_RESULT_OMIT_WHEN_NONE = ("pao_seat", "ura_dora_indicators")


def _strip_none_win_fields(result: dict[str, Any]) -> None:
    """Strip pao_seat and ura_dora_indicators from a win result dict when None."""
    for key in _WIN_RESULT_OMIT_WHEN_NONE:
        if result.get(key) is None:
            result.pop(key, None)


def service_event_payload(event: ServiceEvent) -> dict[str, Any]:
    """Return the wire-format dict for a ServiceEvent payload.

    Shape: {"type": event.event, **data_fields} with internal-only fields
    ("type" and "target" on the domain model) excluded.

    Omits falsy default fields for wire compactness:
    - DiscardEvent: is_tsumogiri, is_riichi omitted when False
    - DrawEvent: available_actions omitted when empty
    - RoundEndEvent: pao_seat, ura_dora_indicators omitted when None
    """
    payload = {"type": event.event, **event.data.model_dump(exclude={"type", "target"})}
    if isinstance(event.data, DiscardEvent):
        for key in ("is_tsumogiri", "is_riichi"):
            if not payload.get(key):
                payload.pop(key, None)
    elif isinstance(event.data, DrawEvent) and not payload.get("available_actions"):
        payload.pop("available_actions", None)
    elif isinstance(event.data, RoundEndEvent):
        _flatten_round_end(payload)
        _strip_round_end_none_fields(payload)
    return payload


def _flatten_round_end(payload: dict[str, Any]) -> None:
    """Flatten the nested result dict into the top-level round_end payload.

    Convert {"type": "round_end", "result": {"type": "tsumo", ...}}
    into    {"type": "round_end", "result_type": "tsumo", ...}.
    """
    result = payload.pop("result")
    result_type = result.pop("type")
    payload["result_type"] = result_type
    payload.update(result)


def _strip_round_end_none_fields(payload: dict[str, Any]) -> None:
    """Strip None win fields from round_end result payloads."""
    result_type = payload.get("result_type")
    if result_type in ("tsumo", "ron"):
        _strip_none_win_fields(payload)
    elif result_type == "double_ron":
        for winner in payload.get("winners", []):
            _strip_none_win_fields(winner)


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
