"""Centralized event payload shaping for wire and replay serialization.

Defines helpers that produce the canonical dict shape for ServiceEvent payloads.
Both the session broadcaster and the replay collector reuse these helpers so
serialization logic is defined once.
"""

from __future__ import annotations

from typing import Any

from game.logic.enums import RoundResultType, WireCallType
from game.logic.events import DiscardEvent, DrawEvent, EventType, MeldEvent, RoundEndEvent, ServiceEvent
from game.logic.meld_compact import meld_event_to_compact
from game.messaging.compact import encode_discard, encode_draw
from game.wire.enums import WireEventType, WireRoundResultType
from shared.lib.melds import EVENT_TYPE_MELD

# Derived from WireEventType IntEnum — stable integer assignments for wire protocol.
EVENT_TYPE_INT: dict[EventType, int] = {EventType[name]: WireEventType[name] for name in WireEventType.__members__}

if WireEventType.MELD != EVENT_TYPE_MELD:
    raise RuntimeError(  # pragma: no cover
        f"WireEventType.MELD ({WireEventType.MELD}) != EVENT_TYPE_MELD ({EVENT_TYPE_MELD})",
    )
if set(EVENT_TYPE_INT.keys()) != set(EventType):
    raise RuntimeError(  # pragma: no cover
        f"EVENT_TYPE_INT keys {set(EVENT_TYPE_INT.keys())} != EventType members {set(EventType)}",
    )


def service_event_payload(event: ServiceEvent) -> dict[str, Any]:
    """Return the wire-format dict for a ServiceEvent payload.

    Shape: {"t": <int>, **data_fields} with internal-only fields
    ("type" and "target" on the domain model) excluded.

    MeldEvent is serialized as compact {"t": 0, "m": <IMME_int>}.
    DrawEvent/DiscardEvent use packed integer encoding in "d" field.
    All other events use Pydantic serialization aliases via by_alias=True,
    with None fields excluded via exclude_none=True.
    """
    if isinstance(event.data, MeldEvent):
        return {"t": WireEventType.MELD, "m": meld_event_to_compact(event.data)}

    if isinstance(event.data, DrawEvent):
        d = encode_draw(event.data.seat, event.data.tile_id)
        payload: dict[str, Any] = {"t": EVENT_TYPE_INT[EventType.DRAW], "d": d}
        if event.data.available_actions:
            payload["aa"] = [aa.model_dump(by_alias=True, exclude_none=True) for aa in event.data.available_actions]
        return payload

    if isinstance(event.data, DiscardEvent):
        return {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(
                event.data.seat,
                event.data.tile_id,
                is_tsumogiri=event.data.is_tsumogiri,
                is_riichi=event.data.is_riichi,
            ),
        }

    payload = {
        "t": EVENT_TYPE_INT[event.event],
        **event.data.model_dump(
            exclude={"type", "target"},
            by_alias=True,
            exclude_none=True,
        ),
    }
    if isinstance(event.data, RoundEndEvent):
        _flatten_round_end(payload)
    return payload


_ROUND_RESULT_TYPE_TO_WIRE: dict[str, int] = {
    rt.value: WireRoundResultType[rt.name] for rt in RoundResultType if rt.name in WireRoundResultType.__members__
}


def _flatten_round_end(payload: dict[str, Any]) -> None:
    """Flatten the nested result dict into the top-level round_end payload.

    Convert {"t": 4, "result": {"type": "tsumo", ...}}
    into    {"t": 4, "rt": 0, ...}.
    """
    result = payload.pop("result")
    result_type = result.pop("type")
    payload["rt"] = _ROUND_RESULT_TYPE_TO_WIRE[result_type]
    payload.update(result)


def shape_call_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Shape a CallPromptEvent payload for the wire.

    For ron/chankan: drop callers (recipient is implied by routing target).
    For meld: replace callers with available_calls containing only the
    recipient's call choices (seat is dropped since it's implied).
    """
    call_type = payload.get("clt")

    if call_type in (WireCallType.RON, WireCallType.CHANKAN):
        callers = payload.pop("clr", [])
        if callers:
            payload["cs"] = callers[0]
        return payload

    if call_type == WireCallType.MELD:
        callers = payload.pop("clr", [])
        if callers:
            payload["cs"] = callers[0]["s"]
        available_calls: list[dict[str, Any]] = []
        for caller in callers:
            call: dict[str, Any] = {"clt": caller["clt"]}
            if caller.get("opt") is not None:
                call["opt"] = caller["opt"]
            available_calls.append(call)
        payload["ac"] = available_calls
        return payload

    return payload
