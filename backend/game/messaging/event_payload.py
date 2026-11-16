from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from game.engine import (
    AbortiveDrawResult,
    CallOpportunity,
    CallSource,
    DiscardEvent,
    DoraRevealedEvent,
    DoubleRonResult,
    DrawEvent,
    DrawNoticeEvent,
    EventType,
    ExhaustiveDrawResult,
    FuritenEvent,
    GameEndedEvent,
    GameEvent,
    GameStartedEvent,
    KanType,
    MeldEvent,
    NagashiManganResult,
    RiichiDeclaredEvent,
    Ron,
    RonResult,
    RoundEndEvent,
    RoundStartedEvent,
    TsumoResult,
    TurnAfterCall,
    TurnAfterDraw,
)
from game.messaging import serialization
from game.messaging.game_errors import ErrorEvent
from game.messaging.meld_compact import meld_event_to_compact
from game.wire.compact import encode_discard, encode_draw
from game.wire.enums import WireCallType, WireEventType, WireRoundResultType
from game.wire.events import EVENT_TYPE_INT
from game.wire.keys import WireKey

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from game.engine import Decision, RoundResult, SeatView
    from game.messaging.roster import GameRoster
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
        return {
            WireKey.EVENT_TYPE: EVENT_TYPE_INT[EventType.DRAW],
            WireKey.PACKED_MOVE: d,
            WireKey.TILES_REMAINING: event.tiles_remaining,
        }

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
    if isinstance(event, DrawNoticeEvent):
        fields = serialization.serialize_draw_notice_event(event)

    elif isinstance(event, RiichiDeclaredEvent):
        fields = serialization.serialize_riichi_declared_event(event)

    elif isinstance(event, DoraRevealedEvent):
        fields = serialization.serialize_dora_revealed_event(event)

    elif isinstance(event, ErrorEvent):
        fields = serialization.serialize_error_event(event)

    elif isinstance(event, RoundStartedEvent):
        fields = serialization.serialize_round_started_event(event)

    elif isinstance(event, GameEndedEvent):
        fields = serialization.serialize_game_ended_event(event)

    elif isinstance(event, FuritenEvent):
        fields = serialization.serialize_furiten_event(event)

    else:
        raise TypeError(f"unsupported game event: {type(event).__name__}")

    return fields


def game_started_payload(event: GameStartedEvent, *, roster: GameRoster) -> dict[int, Any]:
    """
    Build the game start's protocol message: the engine's table rules and first dealer with the session's game id and
    seats (`WireKey.PLAYERS`), for both the socket and the replay.
    """
    return {
        WireKey.EVENT_TYPE: EVENT_TYPE_INT[event.type],
        **serialization.serialize_game_started_event(event, roster=roster),
    }


def live_game_event_payload(event: GameEvent) -> dict[int, Any]:
    """
    Build a live event, leaving per-draw wall counts in the replay only.
    """
    payload = game_event_payload(event)
    if isinstance(event, DrawEvent):
        del payload[WireKey.TILES_REMAINING]

    return payload


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
    view: SeatView,
    *,
    roster: GameRoster,
    stand_ins: Mapping[int, SeatControlReason],
) -> dict[int, Any]:
    """
    Return the wire-format dict of a reconnect snapshot, built from the seat's view: its round result
    (`WireKey.ROUND_RESULT`) shaped as a round end's and each round history entry's result type (`WireKey.RESULT_TYPE`)
    as its integer.

    The game id and seats come from the roster, and the game type and riichi stick value from the rules preset.
    stand_ins maps seats held by an AI stand-in to their reasons. A stand-in keeps the participant identity and carries
    WireKey.STAND_IN_REASON, while a permanent AI player carries WireKey.AI_PLAYER.
    """
    payload = serialization.serialize_reconnection_snapshot(view, roster=roster, stand_ins=stand_ins)
    if view.result is not None:
        payload[WireKey.ROUND_RESULT] = round_end_fields(
            view.result,
            riichi_sticks=view.riichi_sticks,
            dealer_seat=view.round.dealer_seat,
            dora_indicators=list(view.dora_indicators),
        )

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


_ROBBED_KAN_TYPES: dict[CallSource, KanType] = {
    CallSource.ADDED_KAN: KanType.ADDED,
    CallSource.CLOSED_KAN: KanType.CLOSED,
}


@dataclass(frozen=True)
class Opening:
    """
    The message that opens one seat's decision, built from the decision alone (`build_opening`), for the live wait and
    its re-send on a reconnect alike; the session stamps it with the seat's decision id and bank (`stamp_opening`).

    replaces_draw marks a turn after a draw, whose opening is the seat's private draw itself, with its offers.
    """

    seat: int
    payload: dict[int, Any]
    replaces_draw: bool


def build_opening(decision: Decision) -> Opening:
    """
    Build the opening of a seat's decision: its private draw with the draw's offers (`WireKey.AVAILABLE_ACTIONS`, only
    when there are any), the turn after its own pon or chi with the tile types kuikae forbids, or its call prompt.
    """
    context = decision.context
    if isinstance(context, TurnAfterDraw):
        payload: dict[int, Any] = {
            WireKey.EVENT_TYPE: WireEventType.DRAW,
            WireKey.PACKED_MOVE: encode_draw(decision.seat, context.drawn),
        }
        offers = serialization.serialize_draw_offers(decision.legal)
        if offers:
            payload[WireKey.AVAILABLE_ACTIONS] = offers

        return Opening(seat=decision.seat, payload=payload, replaces_draw=True)

    if isinstance(context, TurnAfterCall):
        payload = {WireKey.EVENT_TYPE: WireEventType.TURN, WireKey.KUIKAE_TILES: list(context.kuikae)}
        return Opening(seat=decision.seat, payload=payload, replaces_draw=False)

    return Opening(seat=decision.seat, payload=_call_prompt_payload(decision, context), replaces_draw=False)


def _call_prompt_payload(decision: Decision, context: CallOpportunity) -> dict[int, Any]:
    """
    Shape a call prompt: a chankan prompt for a kan source, naming the kan it robs (`WireKey.KAN_TYPE`), else a ron
    prompt when the seat may ron and a meld prompt otherwise; the recipient's seat (`WireKey.CALLER_SEAT`) and, when it
    may meld, a ron prompt's seat included, its melds (`WireKey.AVAILABLE_CALLS`).
    """
    if context.source != CallSource.DISCARD:
        call_type = WireCallType.CHANKAN
    elif Ron() in decision.legal:
        call_type = WireCallType.RON
    else:
        call_type = WireCallType.MELD

    payload: dict[int, Any] = {
        WireKey.EVENT_TYPE: WireEventType.CALL_PROMPT,
        WireKey.CALL_TYPE: call_type,
        WireKey.TILE_ID: context.tile,
        WireKey.FROM_SEAT: context.from_seat,
    }
    if context.source != CallSource.DISCARD:
        payload[WireKey.KAN_TYPE] = _ROBBED_KAN_TYPES[context.source]

    payload[WireKey.CALLER_SEAT] = decision.seat
    calls = serialization.serialize_available_calls(decision.legal)
    if calls:
        payload[WireKey.AVAILABLE_CALLS] = calls

    return payload


def place_openings(events: list[GameEvent], openings: Sequence[Opening]) -> list[GameEvent | Opening]:
    """
    Return an engine call's events with the openings of the decisions it opened in place, so each seat gets its messages
    in the engine's order.

    A turn after a draw opens on the seat's private draw, which its opening replaces, and on nothing when the events
    hold no draw to that seat; every other opening goes after the step's gameplay facts and ahead of its furiten
    changes, in the order given.
    """
    draws = {opening.seat: opening for opening in openings if opening.replaces_draw}
    inserted = [opening for opening in openings if not opening.replaces_draw]
    placed = [draws.get(event.seat, event) if isinstance(event, DrawEvent) else event for event in events]
    furiten_at = next((i for i, event in enumerate(events) if isinstance(event, FuritenEvent)), len(events))
    return [*placed[:furiten_at], *inserted, *placed[furiten_at:]]


def stamp_opening(
    payload: dict[int, Any],
    *,
    wait_id: int,
    bank_seconds: float,
    elapsed: float | None = None,
) -> dict[int, Any]:
    """
    Copy an opening's payload stamped for its recipient: how long its timer has run when it is re-sent
    (`WireKey.WAIT_ELAPSED`), its decision id (`WireKey.WAIT_ID`) and the bank its timer starts with
    (`WireKey.BANK_SECONDS`), so the client's countdown never carries an earlier decision's delivery delays.

    Only the socket payloads carry them: the replay collector shapes its own payloads, so none reaches a replay file.
    """
    stamped = dict(payload)
    if elapsed is not None:
        stamped[WireKey.WAIT_ELAPSED] = elapsed

    stamped[WireKey.WAIT_ID] = wait_id
    stamped[WireKey.BANK_SECONDS] = bank_seconds
    return stamped
