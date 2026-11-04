from enum import IntEnum
from typing import TYPE_CHECKING

from game.wire.enums import WireEventType, WireRoundResultType
from game.wire.keys import WireKey

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet


class ReplayLineType(IntEnum):
    SEAT_CONTROL = 101


_DICE_PAIR_SIZE = 2
_DEALER_ROLL_COUNT = 2

_EVENT_FIELDS = {
    WireEventType.MELD: {WireKey.EVENT_TYPE, WireKey.PACKED_MELD},
    WireEventType.DRAW: {WireKey.EVENT_TYPE, WireKey.PACKED_MOVE, WireKey.TILES_REMAINING},
    WireEventType.DISCARD: {WireKey.EVENT_TYPE, WireKey.PACKED_MOVE},
    WireEventType.ROUND_END: {
        WireKey.EVENT_TYPE,
        WireKey.RESULT_TYPE,
        WireKey.RIICHI_STICKS,
        WireKey.DEALER,
        WireKey.DORA_INDICATORS,
    },
    WireEventType.RIICHI_DECLARED: {WireKey.EVENT_TYPE, WireKey.SEAT, WireKey.SCORE, WireKey.RIICHI_STICKS},
    WireEventType.DORA_REVEALED: {WireKey.EVENT_TYPE, WireKey.TILE_ID},
    WireEventType.GAME_STARTED: {
        WireKey.EVENT_TYPE,
        WireKey.GAME_ID,
        WireKey.GAME_TYPE,
        WireKey.PLAYERS,
        WireKey.DEALER,
        WireKey.DEALER_DICE,
        WireKey.RIICHI_STICK_VALUE,
        WireKey.HAS_AKADORA,
        WireKey.SEED,
        WireKey.RNG_VERSION,
        WireKey.GAME_SETTINGS,
    },
    WireEventType.ROUND_STARTED: {
        WireKey.EVENT_TYPE,
        WireKey.WIND,
        WireKey.ROUND_NUMBER,
        WireKey.ROUND_IN_WIND,
        WireKey.DEALER,
        WireKey.CURRENT_PLAYER,
        WireKey.DORA_INDICATORS,
        WireKey.HONBA,
        WireKey.RIICHI_STICKS,
        WireKey.PLAYERS,
        WireKey.DICE,
        WireKey.TILES_REMAINING,
    },
    WireEventType.GAME_END: {
        WireKey.EVENT_TYPE,
        WireKey.WINNER_SEAT,
        WireKey.STANDINGS,
        WireKey.LEFTOVER_BONUS,
        WireKey.LEFTOVER_RIICHI,
        WireKey.ROUND_COUNT,
        WireKey.END_CAUSE,
    },
    ReplayLineType.SEAT_CONTROL: {WireKey.EVENT_TYPE, WireKey.SEAT, WireKey.AI_PLAYER},
}
_WIN_FIELDS = {
    WireKey.WINNER_SEAT,
    WireKey.HAND_RESULT,
    WireKey.SCORES,
    WireKey.SCORE_CHANGES,
    WireKey.RIICHI_COLLECTED,
    WireKey.CLOSED_TILES,
    WireKey.MELDS,
    WireKey.WINNING_TILE,
    WireKey.HONBA_BONUS,
}
_RESULT_FIELDS = {
    WireRoundResultType.TSUMO: _WIN_FIELDS,
    WireRoundResultType.RON: _WIN_FIELDS | {WireKey.LOSER_SEAT},
    WireRoundResultType.DOUBLE_RON: {
        WireKey.LOSER_SEAT,
        WireKey.WINNING_TILE,
        WireKey.WINNERS,
        WireKey.SCORES,
        WireKey.SCORE_CHANGES,
    },
    WireRoundResultType.EXHAUSTIVE_DRAW: {
        WireKey.TENPAI_SEATS,
        WireKey.NOTEN_SEATS,
        WireKey.TENPAI_HANDS,
        WireKey.SCORES,
        WireKey.SCORE_CHANGES,
    },
    WireRoundResultType.ABORTIVE_DRAW: {WireKey.ABORTIVE_REASON, WireKey.SCORES, WireKey.SCORE_CHANGES},
    WireRoundResultType.NAGASHI_MANGAN: {
        WireKey.QUALIFYING_SEATS,
        WireKey.QUALIFYING_RIVERS,
        WireKey.TENPAI_SEATS,
        WireKey.NOTEN_SEATS,
        WireKey.TENPAI_HANDS,
        WireKey.SCORES,
        WireKey.SCORE_CHANGES,
    },
}
_STRING_FIELDS = frozenset(
    {
        WireKey.GAME_ID,
        WireKey.NAME,
        WireKey.SEED,
        WireKey.RNG_VERSION,
        WireKey.END_CAUSE,
        WireKey.HAND_LIMIT,
        WireKey.KAN_TYPE,
        WireKey.PAO_SHARE,
        WireKey.ABORTIVE_REASON,
    }
)
_BOOLEAN_FIELDS = frozenset({WireKey.HAS_AKADORA, WireKey.RIICHI_DISCARD, WireKey.TSUMOGIRI})
_INTEGER_ARRAY_FIELDS = frozenset(
    {
        WireKey.CLOSED_TILES,
        WireKey.DICE,
        WireKey.DORA_INDICATORS,
        WireKey.HEAD_BUMPED_SEATS,
        WireKey.MELDS,
        WireKey.NOTEN_SEATS,
        WireKey.QUALIFYING_SEATS,
        WireKey.RON_CALLERS,
        WireKey.TILES,
        WireKey.TENPAI_SEATS,
        WireKey.URA_DORA,
    }
)
_OBJECT_ARRAY_FIELDS = frozenset(
    {
        WireKey.DISCARDS,
        WireKey.PLAYERS,
        WireKey.QUALIFYING_RIVERS,
        WireKey.STANDINGS,
        WireKey.TENPAI_HANDS,
        WireKey.WINNERS,
    }
)
_LIST_FIELDS = _INTEGER_ARRAY_FIELDS | _OBJECT_ARRAY_FIELDS | {WireKey.DEALER_DICE, WireKey.YAKU}
_PLAYER_FIELDS = {
    WireEventType.GAME_STARTED: {WireKey.SEAT, WireKey.NAME, WireKey.AI_PLAYER},
    WireEventType.ROUND_STARTED: {WireKey.SEAT, WireKey.SCORE, WireKey.TILES},
}
_MAP_FIELDS = frozenset(
    {WireKey.HAND_RESULT, WireKey.PAO_LIABILITY, WireKey.ROBBED_KAN, WireKey.SCORES, WireKey.SCORE_CHANGES}
)
_NESTED_REQUIRED: dict[int, set[WireKey]] = {
    WireKey.HAND_RESULT: {WireKey.HAN, WireKey.FU, WireKey.YAKU, WireKey.POINTS, WireKey.HAND_LIMIT},
    WireKey.PAO_LIABILITY: {WireKey.YAKU, WireKey.PAO_SHARE, WireKey.PAYS_HONBA},
    WireKey.ROBBED_KAN: {WireKey.SEAT, WireKey.TILE_ID, WireKey.KAN_TYPE},
    WireKey.STANDINGS: {WireKey.SEAT, WireKey.SCORE, WireKey.FINAL_SCORE},
    WireKey.TENPAI_HANDS: {WireKey.SEAT, WireKey.CLOSED_TILES, WireKey.MELDS},
    WireKey.QUALIFYING_RIVERS: {WireKey.SEAT, WireKey.DISCARDS},
    WireKey.DISCARDS: {WireKey.TILE_ID, WireKey.TSUMOGIRI, WireKey.RIICHI_DISCARD},
    WireKey.WINNERS: {
        WireKey.WINNER_SEAT,
        WireKey.HAND_RESULT,
        WireKey.SCORE_CHANGES,
        WireKey.RIICHI_COLLECTED,
        WireKey.CLOSED_TILES,
        WireKey.MELDS,
        WireKey.HONBA_BONUS,
    },
    WireKey.YAKU: {WireKey.YAKU_ID, WireKey.HAN, WireKey.YAKU_YAKUMAN_COUNT},
}


def _require_fields(record: dict[int, object], fields: AbstractSet[int]) -> None:
    missing = fields - record.keys()
    if missing:
        raise ValueError(f"replay event misses fields: {sorted(missing)}")


def _validate_field_type(key: int, value: object) -> None:
    if key in _STRING_FIELDS:
        valid = isinstance(value, str)
    elif key in _BOOLEAN_FIELDS:
        valid = type(value) is bool
    elif key in _LIST_FIELDS:
        valid = isinstance(value, list | tuple)
    elif key in _MAP_FIELDS:
        valid = isinstance(value, dict)
    elif key == WireKey.HONBA_BONUS:
        valid = isinstance(value, int)
    else:
        valid = isinstance(value, int) and not isinstance(value, bool)

    if not valid:
        raise ValueError(f"invalid replay field {key}: {type(value).__name__}")


def _validate_integer_array(key: int, values: list[object] | tuple[object, ...]) -> None:
    if any(type(item) is not int for item in values):
        raise ValueError(f"invalid replay array {key}: expected integers")


def _validate_dice(values: list[object] | tuple[object, ...]) -> None:
    if len(values) != _DEALER_ROLL_COUNT:
        raise ValueError("invalid replay dealer dice: expected two dice pairs")

    for pair in values:
        if not isinstance(pair, list | tuple) or len(pair) != _DICE_PAIR_SIZE:
            raise ValueError("invalid replay dealer dice: expected dice pairs")

        _validate_integer_array(WireKey.DEALER_DICE, pair)


def _validate_array(
    key: int,
    values: list[object] | tuple[object, ...],
    context: int | None,
) -> None:
    if key == WireKey.DEALER_DICE:
        _validate_dice(values)
        return

    if key in _INTEGER_ARRAY_FIELDS or (key == WireKey.YAKU and context == WireKey.PAO_LIABILITY):
        _validate_integer_array(key, values)
        return

    required = _PLAYER_FIELDS.get(context, set()) if key == WireKey.PLAYERS else _NESTED_REQUIRED[key]
    for item in values:
        if not isinstance(item, dict):
            raise TypeError(f"invalid replay array {key}: expected objects")

        _require_fields(item, required)
        _validate_fields(item, key)


def _validate_fields(record: dict[int, object], context: int | None = None) -> None:
    for key, value in record.items():
        if key == WireKey.GAME_SETTINGS:
            continue

        _validate_field_type(key, value)
        if isinstance(value, dict) and key not in {WireKey.SCORES, WireKey.SCORE_CHANGES}:
            _require_fields(value, _NESTED_REQUIRED[key])
            _validate_fields(value, key)

        if isinstance(value, list | tuple):
            _validate_array(key, value, context)


def validate_replay_event(record: dict[int, object]) -> None:
    event_type = record.get(WireKey.EVENT_TYPE)
    if not isinstance(event_type, int) or isinstance(event_type, bool) or event_type not in _EVENT_FIELDS:
        raise ValueError(f"unsupported replay event type: {event_type!r}")

    _require_fields(record, _EVENT_FIELDS[event_type])
    _validate_fields(record, event_type)
    if event_type == WireEventType.ROUND_END:
        result_type = record[WireKey.RESULT_TYPE]
        if not isinstance(result_type, int) or isinstance(result_type, bool) or result_type not in _RESULT_FIELDS:
            raise ValueError(f"unsupported replay result type: {result_type!r}")

        _require_fields(record, _RESULT_FIELDS[result_type])

    if event_type == ReplayLineType.SEAT_CONTROL and record[WireKey.AI_PLAYER] == 1:
        _require_fields(record, {WireKey.SEAT_CONTROL_REASON})
