"""Centralized event payload shaping for wire and replay serialization.

Defines helpers that produce the canonical dict shape for ServiceEvent payloads.
Both the session broadcaster and the replay collector reuse these helpers so
serialization logic is defined once.
"""

from __future__ import annotations

from typing import Any

from game.logic.events import DiscardEvent, DrawEvent, EventType, MeldEvent, RoundEndEvent, ServiceEvent
from game.logic.meld_compact import meld_event_to_compact
from shared.lib.melds import EVENT_TYPE_MELD

# Stable integer assignments for wire protocol.
# EVENT_TYPE_MELD (0) is defined by the shared melds lib.
EVENT_TYPE_INT: dict[EventType, int] = {
    EventType.MELD: EVENT_TYPE_MELD,  # 0
    EventType.DRAW: 1,
    EventType.DISCARD: 2,
    EventType.CALL_PROMPT: 3,
    EventType.ROUND_END: 4,
    EventType.RIICHI_DECLARED: 5,
    EventType.DORA_REVEALED: 6,
    EventType.ERROR: 7,
    EventType.GAME_STARTED: 8,
    EventType.ROUND_STARTED: 9,
    EventType.GAME_END: 10,
    EventType.FURITEN: 11,
}

# Fields on win result models that are omitted when None (not applicable).
_WIN_RESULT_OMIT_WHEN_NONE = ("pao_seat", "ura_dora_indicators")


def _strip_none_win_fields(result: dict[str, Any]) -> None:
    """Strip pao_seat and ura_dora_indicators from a win result dict when None."""
    for key in _WIN_RESULT_OMIT_WHEN_NONE:
        if result.get(key) is None:
            result.pop(key, None)


def service_event_payload(event: ServiceEvent) -> dict[str, Any]:
    """Return the wire-format dict for a ServiceEvent payload.

    Shape: {"t": <int>, **data_fields} with internal-only fields
    ("type" and "target" on the domain model) excluded.

    MeldEvent is special-cased to produce a compact {"t": 0, "m": <IMME_int>}.

    Omits falsy default fields for wire compactness:
    - DiscardEvent: is_tsumogiri, is_riichi omitted when False
    - DrawEvent: available_actions omitted when empty
    - RoundEndEvent: pao_seat, ura_dora_indicators omitted when None
    """
    if isinstance(event.data, MeldEvent):
        return {"t": EVENT_TYPE_MELD, "m": meld_event_to_compact(event.data)}

    payload = {"t": EVENT_TYPE_INT[event.event], **event.data.model_dump(exclude={"type", "target"})}
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

    Convert {"t": 4, "result": {"type": "tsumo", ...}}
    into    {"t": 4, "result_type": "tsumo", ...}.
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
