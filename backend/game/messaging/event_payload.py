from __future__ import annotations

from typing import TYPE_CHECKING, Any

from game.logic.enums import WaitKind
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    ErrorEvent,
    EventType,
    FuritenEvent,
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
    TurnEvent,
)
from game.logic.meld_compact import meld_event_to_compact
from game.logic.types import (
    AbortiveDrawResult,
    DoubleRonResult,
    ExhaustiveDrawResult,
    NagashiManganResult,
    RonResult,
    TsumoResult,
)
from game.messaging import serialization
from game.wire.compact import encode_discard, encode_draw
from game.wire.enums import WireEventType, WireRoundResultType
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game.logic.service import Awaiting
    from game.logic.types import ReconnectionSnapshot, RoundResult
    from game.messaging.types import TimerSettings
    from game.wire.enums import SeatControlReason


def game_event_payload(event: GameEvent) -> dict[int, Any]:
    """
    Build a numeric-key protocol message from a domain event.
    """
    if isinstance(event, MeldEvent):
        return {WireKey.EVENT_TYPE: WireEventType.MELD, WireKey.PACKED_MELD: meld_event_to_compact(event)}

    if isinstance(event, DrawEvent):
        d = encode_draw(event.seat, event.tile_id)
        payload: dict[int, Any] = {
            WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DRAW],
            WireKey.PACKED_MOVE: d,
            WireKey.TILES_REMAINING: event.tiles_remaining,
        }
        if event.available_actions:
            payload[WireKey.AVAILABLE_ACTIONS] = [
                serialization.serialize_available_action_item(action) for action in event.available_actions
            ]

        return payload

    if isinstance(event, DiscardEvent):
        return {
            WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DISCARD],
            WireKey.PACKED_MOVE: encode_discard(
                event.seat,
                event.tile_id,
                is_tsumogiri=event.is_tsumogiri,
                is_riichi=event.is_riichi,
            ),
        }

    if isinstance(event, RoundEndEvent):
        fields = round_end_fields(
            event.result,
            riichi_sticks=event.riichi_sticks,
            dealer_seat=event.dealer_seat,
            dora_indicators=event.dora_indicators,
        )
        return {WireKey.EVENT_TYPE: EVENT_TYPE_INT[event.type], **fields}

    return {WireKey.EVENT_TYPE: EVENT_TYPE_INT[event.type], **_serialize_event_fields(event)}


def _serialize_event_fields(event: GameEvent) -> dict[int, Any]:
    if isinstance(event, TurnEvent):
        fields = serialization.serialize_turn_event(event)

    elif isinstance(event, CallPromptEvent):
        fields = serialization.serialize_call_prompt_event(event)

    elif isinstance(event, RiichiDeclaredEvent):
        fields = serialization.serialize_riichi_declared_event(event)

    elif isinstance(event, DoraRevealedEvent):
        fields = serialization.serialize_dora_revealed_event(event)

    elif isinstance(event, ErrorEvent):
        fields = serialization.serialize_error_event(event)

    elif isinstance(event, GameStartedEvent):
        fields = serialization.serialize_game_started_event(event)

    elif isinstance(event, RoundStartedEvent):
        fields = serialization.serialize_round_started_event(event)

    elif isinstance(event, GameEndedEvent):
        fields = serialization.serialize_game_ended_event(event)

    elif isinstance(event, FuritenEvent):
        fields = serialization.serialize_furiten_event(event)

    else:
        raise TypeError(f"unsupported game event: {type(event).__name__}")

    return fields


def live_game_event_payload(event: GameEvent) -> dict[int, Any]:
    """
    Build a live event, leaving per-draw wall counts in the replay only.
    """
    payload = game_event_payload(event)
    if isinstance(event, DrawEvent):
        del payload[WireKey.TILES_REMAINING]

    return payload


def draw_notice_payload(event: DrawEvent) -> dict[int, Any]:
    """Return the public notice of a draw that every seat but the drawer's gets
    in its place: the drawer's seat.

    The draw stays private: no tile, offers, bank or wait id, and no `draw` type, so a notice never opens a decision.
    Only the socket sends it; the replay records the draw itself.
    """
    return {
        WireKey.EVENT_TYPE: WireEventType.DRAW_NOTICE,
        WireKey.SEAT: event.seat,
    }


def round_end_fields(
    result: RoundResult,
    *,
    riichi_sticks: int,
    dealer_seat: int,
    dora_indicators: list[int],
) -> dict[int, Any]:
    """
    Return a round end's wire fields: the result's type as the integer `WireKey.RESULT_TYPE`, the riichi sticks the
    result leaves on the table (`WireKey.RIICHI_STICKS`), the round's dealer (`WireKey.DEALER`) and dora indicators
    (`WireKey.DORA_INDICATORS`), then the result's own fields.

    The round end carries them at its top level, the reconnect snapshot under `WireKey.ROUND_RESULT`.
    """
    fields = _serialize_round_result(result)
    return {
        WireKey.RESULT_TYPE: WireRoundResultType[result.type.name],
        WireKey.RIICHI_STICKS: riichi_sticks,
        WireKey.DEALER: dealer_seat,
        WireKey.DORA_INDICATORS: dora_indicators,
        **fields,
    }


def _serialize_round_result(result: RoundResult) -> dict[int, Any]:
    if isinstance(result, TsumoResult):
        return serialization.serialize_tsumo_result(result)

    if isinstance(result, RonResult):
        return serialization.serialize_ron_result(result)

    if isinstance(result, DoubleRonResult):
        return serialization.serialize_double_ron_result(result)

    if isinstance(result, ExhaustiveDrawResult):
        return serialization.serialize_exhaustive_draw_result(result)

    if isinstance(result, AbortiveDrawResult):
        return serialization.serialize_abortive_draw_result(result)

    if isinstance(result, NagashiManganResult):
        return serialization.serialize_nagashi_mangan_result(result)

    raise TypeError(f"unsupported round result: {type(result).__name__}")


def reconnection_payload(
    snapshot: ReconnectionSnapshot,
    *,
    stand_ins: Mapping[int, SeatControlReason],
) -> dict[int, Any]:
    """
    Return the wire-format dict of a reconnect snapshot, its round result (`WireKey.ROUND_RESULT`) shaped as a round
    end's and each round history entry's result type (`WireKey.RESULT_TYPE`) as its integer.

    stand_ins maps seats held by an AI stand-in to their reasons. A stand-in keeps the participant identity and carries
    WireKey.STAND_IN_REASON, while a permanent AI player carries WireKey.AI_PLAYER.
    """
    payload = serialization.serialize_reconnection_snapshot(snapshot, stand_ins=stand_ins)
    if snapshot.result is not None:
        payload[WireKey.ROUND_RESULT] = round_end_fields(
            snapshot.result,
            riichi_sticks=snapshot.riichi_sticks,
            dealer_seat=snapshot.dealer_seat,
            dora_indicators=snapshot.dora_indicators,
        )

    return payload


def shape_call_prompt_payload(payload: dict[int, Any]) -> dict[int, Any]:
    """
    Shape a CallPromptEvent payload for the wire.

    Replace the callers list with the recipient's seat; a prompt whose seat can meld, a ron prompt included, also lists
    the recipient's meld choices, without the seat.
    """
    payload = dict(payload)
    callers = payload.pop(WireKey.CALLERS)
    first_caller = callers[0]
    if isinstance(first_caller, int):
        payload[WireKey.CALLER_SEAT] = first_caller
        return payload

    payload[WireKey.CALLER_SEAT] = first_caller[WireKey.SEAT]
    available_calls: list[dict[int, Any]] = []
    for caller in callers:
        call: dict[int, Any] = {WireKey.CALL_TYPE: caller[WireKey.CALL_TYPE]}
        if caller.get(WireKey.CALL_OPTIONS) is not None:
            call[WireKey.CALL_OPTIONS] = caller[WireKey.CALL_OPTIONS]

        available_calls.append(call)

    payload[WireKey.AVAILABLE_CALLS] = available_calls
    return payload


def stamp_viewer_seat(payload: dict[int, Any], seat: int) -> dict[int, Any]:
    """
    Return a copy of a broadcast payload stamped with its recipient's seat (`WireKey.SEAT`).

    The game start is broadcast, but each client reads its own seat from it to draw the table from that seat. Only the
    socket payloads carry it, never a replay file.
    """
    return {**payload, WireKey.SEAT: seat}


def stamp_timer_settings(payload: dict[int, Any], timer: TimerSettings) -> dict[int, Any]:
    """
    Return a copy of a payload stamped with its recipient's timer settings (`WireKey.TIMER_SETTINGS`).

    The game start and the reconnect snapshot carry them, so the client counts its own turns down without the server
    syncing each one. Only the socket payloads carry them, never a replay file.
    """
    return {**payload, WireKey.TIMER_SETTINGS: timer.payload()}


def stamp_wait_id(payload: dict[int, Any], *, event: GameEvent, awaiting: Awaiting, wait_id: int) -> dict[int, Any]:
    """
    Copy an opening event's payload with the recipient's decision id (`WireKey.WAIT_ID`); leave any other payload as it
    is.

    The opening events: for a turn, the draw or the turn event to the awaited seat; for a call prompt, each prompt to an
    awaited seat; for a round advance, the round end, or for the one that confirms the game's start, the first round's
    deal to an awaited seat. A game over opens no wait. Only the socket payloads carry it: the
    replay collector shapes its own payloads, so `WireKey.WAIT_ID` never reaches a replay file.
    """
    if _opens_wait(event, awaiting):
        return {**payload, WireKey.WAIT_ID: wait_id}

    return payload


def _opens_wait(event: GameEvent, awaiting: Awaiting) -> bool:
    target = event.target
    to_awaited_seat = isinstance(target, SeatTarget) and target.seat in awaiting.seats
    if awaiting.kind == WaitKind.TURN:
        return isinstance(event, DrawEvent | TurnEvent) and to_awaited_seat

    if awaiting.kind == WaitKind.CALL:
        return isinstance(event, CallPromptEvent) and to_awaited_seat

    if awaiting.kind != WaitKind.ROUND_ADVANCE:
        return False

    if awaiting.starts_game:
        return isinstance(event, RoundStartedEvent) and to_awaited_seat

    return isinstance(event, RoundEndEvent)
