from enum import IntEnum


class WireEventType(IntEnum):
    """Integer wire encoding for EventType, plus DRAW_NOTICE, which no
    EventType carries: the session shapes it from a draw for every seat but the
    drawer's (`draw_notice_payload`), naming the drawer and never the tile."""

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
    TURN = 12
    DRAW_NOTICE = 13


class WireRoundResultType(IntEnum):
    """
    Integer wire encoding for RoundResultType.
    """

    TSUMO = 0
    RON = 1
    DOUBLE_RON = 2
    EXHAUSTIVE_DRAW = 3
    ABORTIVE_DRAW = 4
    NAGASHI_MANGAN = 5


class SeatControlReason(IntEnum):
    """
    Describe why an AI player stands in for a participant, in the replay seat control record, the live seat control
    message and the reconnect snapshot.

    LEFT is a disconnect (a kick included) during play, the game start's confirmation included; ABSENT a participant
    without a connection at the game's start, which never joined.
    """

    LEFT = 0
    ABSENT = 1
