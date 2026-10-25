from enum import IntEnum


class WireClientMessageType(IntEnum):
    """
    Integer wire encoding for client-to-server message types.
    """

    GAME_ACTION = 3
    RECONNECT = 6
    JOIN_GAME = 7


class WireGameAction(IntEnum):
    """
    Integer wire encoding for game actions.
    """

    DISCARD = 0
    DECLARE_RIICHI = 1
    DECLARE_TSUMO = 2
    CALL_RON = 3
    CALL_PON = 4
    CALL_CHI = 5
    CALL_KAN = 6
    CALL_KYUUSHU = 7
    PASS = 8
    CONFIRM_ROUND = 9
