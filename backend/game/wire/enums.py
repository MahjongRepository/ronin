"""Wire encoding enums shared across messaging and replay layers.

These IntEnum classes define stable integer assignments for the wire protocol.
They are used by both game.messaging and game.replay, so they live in a shared
module to avoid cross-layer imports.
"""

from enum import IntEnum


class WireEventType(IntEnum):
    """Integer wire encoding for EventType."""

    MELD = 0
    DRAW = 1
    DISCARD = 2
    CALL_PROMPT = 3
    ROUND_END = 4
    RIICHI_DECLARED = 5
    DORA_REVEALED = 6
    ERROR = 7
    GAME_STARTED = 8
    ROUND_STARTED = 9
    GAME_END = 10
    FURITEN = 11


class WireRoundResultType(IntEnum):
    """Integer wire encoding for RoundResultType."""

    TSUMO = 0
    RON = 1
    DOUBLE_RON = 2
    EXHAUSTIVE_DRAW = 3
    ABORTIVE_DRAW = 4
    NAGASHI_MANGAN = 5
