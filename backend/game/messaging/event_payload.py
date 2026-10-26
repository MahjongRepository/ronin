from __future__ import annotations

from typing import TYPE_CHECKING, Any

from game.logic.enums import RoundResultType, WaitKind
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DrawEvent,
    EventType,
    GameEvent,
    MeldEvent,
    RoundEndEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.meld_compact import meld_event_to_compact
from game.wire.compact import encode_discard, encode_draw
from game.wire.enums import WireEventType, WireRoundResultType
from game.wire.events import EVENT_TYPE_INT

if TYPE_CHECKING:
    from game.logic.service import Awaiting
    from game.logic.types import ReconnectionSnapshot, RoundResult
    from game.messaging.types import TimerSettings

WAIT_ID_KEY = "wi"
VIEWER_SEAT_KEY = "s"
TIMER_SETTINGS_KEY = "tm"
ROUND_RESULT_KEY = "re"
CONFIRMATION_OWED_KEY = "oc"
WAIT_ELAPSED_KEY = "el"


def game_event_payload(event: GameEvent) -> dict[str, Any]:
    """
    Return the wire-format dict of a game event.

    Shape: {"t": <int>, **data_fields} with internal-only fields
    ("type" and "target" on the domain model) excluded.

    MeldEvent is serialized as compact {"t": 0, "m": <IMME_int>}.
    DrawEvent/DiscardEvent use packed integer encoding in "d" field.
    All other events use Pydantic serialization aliases via by_alias=True,
    with None fields excluded via exclude_none=True.
    """
    if isinstance(event, MeldEvent):
        return {"t": WireEventType.MELD, "m": meld_event_to_compact(event)}

    if isinstance(event, DrawEvent):
        d = encode_draw(event.seat, event.tile_id)
        payload: dict[str, Any] = {"t": EVENT_TYPE_INT[EventType.DRAW], "d": d}
        if event.available_actions:
            payload["aa"] = [aa.model_dump(by_alias=True, exclude_none=True) for aa in event.available_actions]

        return payload

    if isinstance(event, DiscardEvent):
        return {
            "t": EVENT_TYPE_INT[EventType.DISCARD],
            "d": encode_discard(
                event.seat,
                event.tile_id,
                is_tsumogiri=event.is_tsumogiri,
                is_riichi=event.is_riichi,
            ),
        }

    if isinstance(event, RoundEndEvent):
        return {"t": EVENT_TYPE_INT[event.type], **round_result_payload(event.result)}

    return {
        "t": EVENT_TYPE_INT[event.type],
        **event.model_dump(
            exclude={"type", "target"},
            by_alias=True,
            exclude_none=True,
        ),
    }


_ROUND_RESULT_TYPE_TO_WIRE: dict[str, int] = {
    rt.value: WireRoundResultType[rt.name] for rt in RoundResultType if rt.name in WireRoundResultType.__members__
}


def round_result_payload(result: RoundResult) -> dict[str, Any]:
    """
    Return a round result's wire fields: its type as the integer `rt`, then the result's own fields.

    The round end carries them at its top level, the reconnect snapshot under `re`.
    """
    fields = result.model_dump(by_alias=True, exclude_none=True)
    result_type = fields.pop("type")
    return {"rt": _ROUND_RESULT_TYPE_TO_WIRE[result_type], **fields}


def reconnection_payload(snapshot: ReconnectionSnapshot) -> dict[str, Any]:
    """
    Return the wire-format dict of a reconnect snapshot, its round result (`re`) shaped as a round end's.
    """
    payload = snapshot.model_dump(by_alias=True, exclude_none=True, exclude={"result"})
    if snapshot.result is not None:
        payload[ROUND_RESULT_KEY] = round_result_payload(snapshot.result)

    return payload


def shape_call_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Shape a CallPromptEvent payload for the wire.

    Replace the callers list (clr) with the recipient's seat (cs); a prompt whose seat can meld, a ron prompt included,
    also lists the recipient's meld choices (ac), without the seat.
    """
    callers = payload.pop("clr")
    first_caller = callers[0]
    if isinstance(first_caller, int):
        payload["cs"] = first_caller
        return payload

    payload["cs"] = first_caller["s"]
    available_calls: list[dict[str, Any]] = []
    for caller in callers:
        call: dict[str, Any] = {"clt": caller["clt"]}
        if caller.get("opt") is not None:
            call["opt"] = caller["opt"]

        available_calls.append(call)

    payload["ac"] = available_calls
    return payload


def stamp_viewer_seat(payload: dict[str, Any], seat: int) -> dict[str, Any]:
    """
    Return a copy of a broadcast payload stamped with its recipient's seat (`s`).

    The game start is broadcast, but each client reads its own seat from it to draw the table from that seat. Only the
    socket payloads carry it, never a replay file.
    """
    return {**payload, VIEWER_SEAT_KEY: seat}


def stamp_timer_settings(payload: dict[str, Any], timer: TimerSettings) -> dict[str, Any]:
    """
    Return a copy of a payload stamped with its recipient's timer settings (`tm`).

    The game start and the reconnect snapshot carry them, so the client counts its own turns down without the server
    syncing each one. Only the socket payloads carry them, never a replay file.
    """
    return {**payload, TIMER_SETTINGS_KEY: timer.model_dump(by_alias=True)}


def stamp_wait_id(payload: dict[str, Any], event: GameEvent, awaiting: Awaiting) -> dict[str, Any]:
    """
    Add the wait id (`wi`) to the payload of an event that opens the awaited wait; leave any other payload as it is.

    The opening events: for a turn, the draw or the turn event to the awaited seat; for a call prompt, each prompt to an
    awaited seat; for a round advance, the round end. A game over opens no wait. Only the socket payloads carry it: the
    replay collector shapes its own payloads, so `wi` never reaches a replay file.
    """
    if _opens_wait(event, awaiting):
        payload[WAIT_ID_KEY] = awaiting.wait_id

    return payload


def _opens_wait(event: GameEvent, awaiting: Awaiting) -> bool:
    target = event.target
    to_awaited_seat = isinstance(target, SeatTarget) and target.seat in awaiting.seats
    if awaiting.kind == WaitKind.TURN:
        return isinstance(event, DrawEvent | TurnEvent) and to_awaited_seat

    if awaiting.kind == WaitKind.CALL:
        return isinstance(event, CallPromptEvent) and to_awaited_seat

    return awaiting.kind == WaitKind.ROUND_ADVANCE and isinstance(event, RoundEndEvent)
