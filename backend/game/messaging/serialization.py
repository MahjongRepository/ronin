from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import WireCallType, WireGameType, WireMeldCallType, WirePlayerAction, WireWind
from game.logic.settings import WIRE_SCORE_DIVISOR
from game.logic.types import (
    AbortiveDrawResult,
    AvailableActionItem,
    DiscardInfo,
    DoubleRonResult,
    DoubleRonWinner,
    ExhaustiveDrawResult,
    GamePlayerInfo,
    HandResultInfo,
    MeldCaller,
    NagashiManganResult,
    NagashiRiver,
    PaoLiability,
    PlayerReconnectState,
    PlayerStanding,
    PlayerView,
    ReconnectionSnapshot,
    RobbedKan,
    RonResult,
    RoundHistoryEntry,
    TenpaiHand,
    TsumoResult,
    YakuInfo,
)
from game.wire.enums import WireRoundResultType
from game.wire.keys import WireKey

if TYPE_CHECKING:
    from collections.abc import Mapping

    from game.logic.events import (
        CallPromptEvent,
        DoraRevealedEvent,
        ErrorEvent,
        FuritenEvent,
        GameEndedEvent,
        GameStartedEvent,
        RiichiDeclaredEvent,
        RoundStartedEvent,
        TurnEvent,
    )
    from game.wire.enums import SeatControlReason


def serialize_score_map(scores: dict[int, int]) -> dict[str, int]:
    return {str(seat): score // WIRE_SCORE_DIVISOR for seat, score in scores.items()}


def serialize_game_player_info(
    value: GamePlayerInfo, *, stand_in_reason: SeatControlReason | None = None
) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.SEAT: value.seat,
        WireKey.NAME: value.name,
        WireKey.AI_PLAYER: int(value.is_ai_player and stand_in_reason is None),
    }
    if stand_in_reason is not None:
        payload[WireKey.STAND_IN_REASON] = stand_in_reason

    return payload


def serialize_yaku_info(value: YakuInfo) -> dict[int, object]:
    return {
        WireKey.YAKU_ID: value.yaku_id,
        WireKey.HAN: value.han,
        WireKey.YAKU_YAKUMAN_COUNT: value.yakuman_count,
    }


def serialize_hand_result_info(value: HandResultInfo) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.HAN: value.han,
        WireKey.FU: value.fu,
        WireKey.YAKU: [serialize_yaku_info(item) for item in value.yaku],
        WireKey.POINTS: value.points // WIRE_SCORE_DIVISOR,
        WireKey.HAND_LIMIT: value.limit,
        WireKey.YAKUMAN_COUNT: value.yakuman_count,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_pao_liability(value: PaoLiability) -> dict[int, object]:
    return {
        WireKey.YAKU: value.yaku_ids,
        WireKey.PAO_SHARE: value.share,
        WireKey.PAYS_HONBA: value.pays_honba,
    }


def serialize_robbed_kan(value: RobbedKan) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.TILE_ID: value.tile_id,
        WireKey.KAN_TYPE: value.kan_type,
    }


def serialize_double_ron_winner(value: DoubleRonWinner) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.WINNER_SEAT: value.winner_seat,
        WireKey.HAND_RESULT: serialize_hand_result_info(value.hand_result),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
        WireKey.RIICHI_COLLECTED: value.riichi_sticks_collected,
        WireKey.CLOSED_TILES: value.closed_tiles,
        WireKey.MELDS: value.melds,
        WireKey.HONBA_BONUS: value.honba_bonus // WIRE_SCORE_DIVISOR,
        WireKey.PAO_SEAT: value.pao_seat,
        WireKey.PAO_LIABILITY: serialize_pao_liability(value.pao) if value.pao is not None else None,
        WireKey.URA_DORA: value.ura_dora_indicators,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_tenpai_hand(value: TenpaiHand) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.CLOSED_TILES: value.closed_tiles,
        WireKey.MELDS: value.melds,
    }


def serialize_discard_info(value: DiscardInfo) -> dict[int, object]:
    return {
        WireKey.TILE_ID: value.tile_id,
        WireKey.TSUMOGIRI: value.is_tsumogiri,
        WireKey.RIICHI_DISCARD: value.is_riichi_discard,
    }


def serialize_nagashi_river(value: NagashiRiver) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.DISCARDS: [serialize_discard_info(item) for item in value.discards],
    }


def serialize_player_standing(value: PlayerStanding) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.SCORE: value.score // WIRE_SCORE_DIVISOR,
        WireKey.FINAL_SCORE: value.final_score,
    }


def serialize_meld_caller(value: MeldCaller) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.SEAT: value.seat,
        WireKey.CALL_TYPE: WireMeldCallType[value.call_type.name],
        WireKey.CALL_OPTIONS: value.options,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_available_action_item(value: AvailableActionItem) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.ACTION: WirePlayerAction[value.action.name],
        WireKey.TILES: value.tiles,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_player_view(value: PlayerView) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.SCORE: value.score // WIRE_SCORE_DIVISOR,
    }


def serialize_player_reconnect_state(value: PlayerReconnectState) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.SCORE: value.score // WIRE_SCORE_DIVISOR,
        WireKey.DISCARDS: [serialize_discard_info(item) for item in value.discards],
        WireKey.MELDS: value.melds,
        WireKey.IS_RIICHI: value.is_riichi,
        WireKey.TILE_COUNT: value.tile_count,
    }


def serialize_round_history_entry(value: RoundHistoryEntry) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.WIND: WireWind[value.round_wind.name],
        WireKey.DEALER: value.dealer_seat,
        WireKey.HONBA: value.honba_sticks,
        WireKey.RESULT_TYPE: WireRoundResultType[value.result_type.name],
        WireKey.ABORTIVE_REASON: value.abortive_reason,
        WireKey.RIICHI_SEATS: value.riichi_seats,
        WireKey.WINNER_SEAT: value.winner_seats,
        WireKey.LOSER_SEAT: value.loser_seat,
        WireKey.PAO_SEAT: value.pao_seats,
        WireKey.TENPAI_SEATS: value.tenpai_seats,
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_reconnection_snapshot(
    value: ReconnectionSnapshot, *, stand_ins: Mapping[int, SeatControlReason]
) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.GAME_ID: value.game_id,
        WireKey.GAME_TYPE: WireGameType[value.game_type.name],
        WireKey.PLAYERS: [
            serialize_game_player_info(item, stand_in_reason=stand_ins.get(item.seat)) for item in value.players
        ],
        WireKey.DEALER: value.dealer_seat,
        WireKey.FIRST_DEALER: value.first_dealer_seat,
        WireKey.DEALER_DICE: value.dealer_dice,
        WireKey.RIICHI_STICK_VALUE: value.riichi_stick_value // WIRE_SCORE_DIVISOR,
        WireKey.SEAT: value.seat,
        WireKey.WIND: WireWind[value.round_wind.name],
        WireKey.ROUND_NUMBER: value.round_number,
        WireKey.ROUND_IN_WIND: value.round_in_wind,
        WireKey.CURRENT_PLAYER: value.current_player_seat,
        WireKey.LATEST_DISCARD_SEAT: value.latest_discard_seat,
        WireKey.DORA_INDICATORS: value.dora_indicators,
        WireKey.HONBA: value.honba_sticks,
        WireKey.RIICHI_STICKS: value.riichi_sticks,
        WireKey.MY_TILES: value.my_tiles,
        WireKey.DICE: value.dice,
        WireKey.TILES_REMAINING: value.tiles_remaining,
        WireKey.PLAYER_STATES: [serialize_player_reconnect_state(item) for item in value.player_states],
        WireKey.FURITEN: value.is_furiten,
        WireKey.ROUND_HISTORY: [serialize_round_history_entry(item) for item in value.round_history],
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_tsumo_result(value: TsumoResult) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.WINNER_SEAT: value.winner_seat,
        WireKey.HAND_RESULT: serialize_hand_result_info(value.hand_result),
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
        WireKey.RIICHI_COLLECTED: value.riichi_sticks_collected,
        WireKey.CLOSED_TILES: value.closed_tiles,
        WireKey.MELDS: value.melds,
        WireKey.WINNING_TILE: value.win_tile,
        WireKey.HONBA_BONUS: value.honba_bonus // WIRE_SCORE_DIVISOR,
        WireKey.PAO_SEAT: value.pao_seat,
        WireKey.PAO_LIABILITY: serialize_pao_liability(value.pao) if value.pao is not None else None,
        WireKey.URA_DORA: value.ura_dora_indicators,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_ron_result(value: RonResult) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.WINNER_SEAT: value.winner_seat,
        WireKey.LOSER_SEAT: value.loser_seat,
        WireKey.WINNING_TILE: value.winning_tile,
        WireKey.HAND_RESULT: serialize_hand_result_info(value.hand_result),
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
        WireKey.RIICHI_COLLECTED: value.riichi_sticks_collected,
        WireKey.CLOSED_TILES: value.closed_tiles,
        WireKey.MELDS: value.melds,
        WireKey.HONBA_BONUS: value.honba_bonus // WIRE_SCORE_DIVISOR,
        WireKey.PAO_SEAT: value.pao_seat,
        WireKey.PAO_LIABILITY: serialize_pao_liability(value.pao) if value.pao is not None else None,
        WireKey.URA_DORA: value.ura_dora_indicators,
        WireKey.ROBBED_KAN: serialize_robbed_kan(value.robbed_kan) if value.robbed_kan is not None else None,
        WireKey.HEAD_BUMPED_SEATS: value.head_bumped_seats,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_double_ron_result(value: DoubleRonResult) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.LOSER_SEAT: value.loser_seat,
        WireKey.WINNING_TILE: value.winning_tile,
        WireKey.WINNERS: [serialize_double_ron_winner(item) for item in value.winners],
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
        WireKey.ROBBED_KAN: serialize_robbed_kan(value.robbed_kan) if value.robbed_kan is not None else None,
        WireKey.HEAD_BUMPED_SEATS: value.head_bumped_seats,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_exhaustive_draw_result(value: ExhaustiveDrawResult) -> dict[int, object]:
    return {
        WireKey.TENPAI_SEATS: value.tempai_seats,
        WireKey.NOTEN_SEATS: value.noten_seats,
        WireKey.TENPAI_HANDS: [serialize_tenpai_hand(item) for item in value.tenpai_hands],
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
    }


def serialize_abortive_draw_result(value: AbortiveDrawResult) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.ABORTIVE_REASON: value.reason,
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
        WireKey.SEAT: value.seat,
        WireKey.RON_CALLERS: value.ron_seats,
        WireKey.ROBBED_KAN: serialize_robbed_kan(value.robbed_kan) if value.robbed_kan is not None else None,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_nagashi_mangan_result(value: NagashiManganResult) -> dict[int, object]:
    return {
        WireKey.QUALIFYING_SEATS: value.qualifying_seats,
        WireKey.QUALIFYING_RIVERS: [serialize_nagashi_river(item) for item in value.rivers],
        WireKey.TENPAI_SEATS: value.tempai_seats,
        WireKey.NOTEN_SEATS: value.noten_seats,
        WireKey.TENPAI_HANDS: [serialize_tenpai_hand(item) for item in value.tenpai_hands],
        WireKey.SCORES: serialize_score_map(value.scores),
        WireKey.SCORE_CHANGES: serialize_score_map(value.score_changes),
    }


def serialize_turn_event(value: TurnEvent) -> dict[int, object]:
    return {
        WireKey.KUIKAE_TILES: value.kuikae_tiles,
    }


def serialize_call_prompt_event(value: CallPromptEvent) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.CALL_TYPE: WireCallType[value.call_type.name],
        WireKey.TILE_ID: value.tile_id,
        WireKey.FROM_SEAT: value.from_seat,
        WireKey.CALLERS: [
            serialize_meld_caller(item) if isinstance(item, MeldCaller) else item for item in value.callers
        ],
        WireKey.KAN_TYPE: value.kan_type,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_riichi_declared_event(value: RiichiDeclaredEvent) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.SCORE: value.score // WIRE_SCORE_DIVISOR,
        WireKey.RIICHI_STICKS: value.riichi_sticks,
    }


def serialize_dora_revealed_event(value: DoraRevealedEvent) -> dict[int, object]:
    return {
        WireKey.TILE_ID: value.tile_id,
    }


def serialize_error_event(value: ErrorEvent) -> dict[int, object]:
    payload: dict[int, object] = {
        WireKey.GAME_ERROR_CODE: value.code,
        WireKey.GAME_ERROR_MESSAGE: value.message,
        WireKey.WAIT_ID: value.wait_id,
    }
    return {key: item for key, item in payload.items() if item is not None}


def serialize_game_started_event(value: GameStartedEvent) -> dict[int, object]:
    return {
        WireKey.GAME_ID: value.game_id,
        WireKey.GAME_TYPE: WireGameType[value.game_type.name],
        WireKey.PLAYERS: [serialize_game_player_info(item) for item in value.players],
        WireKey.DEALER: value.dealer_seat,
        WireKey.DEALER_DICE: value.dealer_dice,
        WireKey.RIICHI_STICK_VALUE: value.riichi_stick_value // WIRE_SCORE_DIVISOR,
    }


def serialize_round_started_event(value: RoundStartedEvent) -> dict[int, object]:
    return {
        WireKey.SEAT: value.seat,
        WireKey.WIND: WireWind[value.round_wind.name],
        WireKey.ROUND_NUMBER: value.round_number,
        WireKey.ROUND_IN_WIND: value.round_in_wind,
        WireKey.DEALER: value.dealer_seat,
        WireKey.CURRENT_PLAYER: value.current_player_seat,
        WireKey.DORA_INDICATORS: value.dora_indicators,
        WireKey.HONBA: value.honba_sticks,
        WireKey.RIICHI_STICKS: value.riichi_sticks,
        WireKey.MY_TILES: value.my_tiles,
        WireKey.PLAYERS: [serialize_player_view(item) for item in value.players],
        WireKey.DICE: value.dice,
        WireKey.TILES_REMAINING: value.tiles_remaining,
    }


def serialize_game_ended_event(value: GameEndedEvent) -> dict[int, object]:
    return {
        WireKey.WINNER_SEAT: value.winner_seat,
        WireKey.STANDINGS: [serialize_player_standing(item) for item in value.standings],
        WireKey.LEFTOVER_BONUS: value.leftover_riichi_bonus // WIRE_SCORE_DIVISOR,
        WireKey.LEFTOVER_RIICHI: value.leftover_riichi_sticks,
        WireKey.ROUND_COUNT: value.num_rounds,
        WireKey.END_CAUSE: value.end_cause,
    }


def serialize_furiten_event(value: FuritenEvent) -> dict[int, object]:
    return {
        WireKey.FURITEN: value.is_furiten,
    }
