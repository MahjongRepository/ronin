from enum import IntEnum


class WireEventType(IntEnum):
    """Integer wire encoding for EventType, plus CALL_PROMPT and TURN, which no
    EventType carries: messaging builds those openings from a seat's decision."""

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


class WireCallType(IntEnum):
    """
    Integer wire encoding of a call prompt's type: a ron prompt (the seat may ron, and meld instead when it can), a
    meld-only prompt, or a chankan prompt.
    """

    RON = 0
    MELD = 1
    CHANKAN = 2


class WireMeldCallType(IntEnum):
    """
    Integer wire encoding of a meld a call prompt offers.
    """

    PON = 0
    CHI = 1
    OPEN_KAN = 2


class WirePlayerAction(IntEnum):
    """
    Integer wire encoding for PlayerAction.
    """

    DISCARD = 0
    RIICHI = 1
    TSUMO = 2
    KAN = 3
    ADDED_KAN = 4
    KYUUSHU = 5


class WireWind(IntEnum):
    """
    Integer wire encoding for WindName.
    """

    EAST = 0
    SOUTH = 1
    WEST = 2
    NORTH = 3


class WireGameType(IntEnum):
    """
    Integer wire encoding for GameType.
    """

    HANCHAN = 0
    TONPUSEN = 1
