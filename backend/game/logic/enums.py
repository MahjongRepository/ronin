from enum import IntEnum, StrEnum


class PlayerAction(StrEnum):
    """
    Actions available to a player during their turn.
    """

    DISCARD = "discard"
    RIICHI = "riichi"
    TSUMO = "tsumo"
    KAN = "kan"
    ADDED_KAN = "added_kan"
    KYUUSHU = "kyuushu"


class GameAction(StrEnum):
    """
    Actions dispatched from client to game service.
    """

    DISCARD = "discard"
    DECLARE_RIICHI = "declare_riichi"
    DECLARE_TSUMO = "declare_tsumo"
    CALL_RON = "call_ron"
    CALL_PON = "call_pon"
    CALL_CHI = "call_chi"
    CALL_KAN = "call_kan"
    CALL_KYUUSHU = "call_kyuushu"
    PASS = "pass"  # noqa: S105
    CONFIRM_ROUND = "confirm_round"


class GameErrorCode(StrEnum):
    """
    Error codes of an ErrorEvent: the action was refused and nothing changed.

    STALE_ACTION comes from the session, not the engine: the action echoed the id of a wait that already ended.
    """

    NOT_YOUR_TURN = "not_your_turn"
    INVALID_DISCARD = "invalid_discard"
    INVALID_RIICHI = "invalid_riichi"
    INVALID_RON = "invalid_ron"
    INVALID_PON = "invalid_pon"
    INVALID_CHI = "invalid_chi"
    INVALID_KAN = "invalid_kan"
    INVALID_PASS = "invalid_pass"  # noqa: S105
    INVALID_ACTION = "invalid_action"
    STALE_ACTION = "stale_action"


class MeldCallType(StrEnum):
    """
    Types of meld calls that can be made on a discarded tile.
    """

    PON = "pon"
    CHI = "chi"
    OPEN_KAN = "open_kan"
    CLOSED_KAN = "closed_kan"
    ADDED_KAN = "added_kan"


class KanType(StrEnum):
    """
    Subtypes of kan declarations.
    """

    OPEN = "open"
    CLOSED = "closed"
    ADDED = "added"

    def to_meld_call_type(self) -> MeldCallType:
        """
        Convert kan type to the corresponding meld call type.
        """
        return _KAN_TO_MELD_CALL[self]


_KAN_TO_MELD_CALL: dict[KanType, MeldCallType] = {
    KanType.OPEN: MeldCallType.OPEN_KAN,
    KanType.CLOSED: MeldCallType.CLOSED_KAN,
    KanType.ADDED: MeldCallType.ADDED_KAN,
}


class PromptKind(StrEnum):
    """
    Kinds of pending call prompts the engine stores.
    """

    DISCARD = "discard"
    CHANKAN = "chankan"


class CallType(StrEnum):
    """
    Kinds of per-seat call prompt events sent to players.
    """

    RON = "ron"
    MELD = "meld"
    CHANKAN = "chankan"


class WireCallType(IntEnum):
    """
    Integer wire encoding for CallType.
    """

    RON = 0
    MELD = 1
    CHANKAN = 2


class WireMeldCallType(IntEnum):
    """
    Integer wire encoding for MeldCallType.
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


class AbortiveDrawType(StrEnum):
    """
    Types of abortive draws in Mahjong.
    """

    NINE_TERMINALS = "nine_terminals"
    FOUR_RIICHI = "four_riichi"
    TRIPLE_RON = "triple_ron"
    FOUR_KANS = "four_kans"
    FOUR_WINDS = "four_winds"


class RoundResultType(StrEnum):
    """
    Types of round end results.
    """

    TSUMO = "tsumo"
    RON = "ron"
    DOUBLE_RON = "double_ron"
    EXHAUSTIVE_DRAW = "exhaustive_draw"
    ABORTIVE_DRAW = "abortive_draw"
    NAGASHI_MANGAN = "nagashi_mangan"
    GAME_END = "game_end"


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


class WindName(StrEnum):
    """
    Wind direction names.
    """

    EAST = "East"
    SOUTH = "South"
    WEST = "West"
    NORTH = "North"
    UNKNOWN = "Unknown"


class AIPlayerType(StrEnum):
    """
    Types of AI players available for matchmaking.
    """

    TSUMOGIRI = "tsumogiri"


class TimeoutType(StrEnum):
    """
    Types of player timeouts.
    """

    TURN = "turn"
    MELD = "meld"
    ROUND_ADVANCE = "round_advance"


class WaitKind(StrEnum):
    """
    What the game waits for: a seat's turn, call prompt responses, round-end confirmations, or nothing (game over).
    """

    TURN = "turn"
    CALL = "call"
    ROUND_ADVANCE = "round_advance"
    NONE = "none"


class MeldViewType(StrEnum):
    """
    Meld type names for client-facing view.
    """

    CHI = "chi"
    PON = "pon"
    OPEN_KAN = "open_kan"
    CLOSED_KAN = "closed_kan"
    ADDED_KAN = "added_kan"


class RoundPhase(StrEnum):
    """
    Phase of a mahjong round.
    """

    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class GamePhase(StrEnum):
    """
    Phase of a mahjong game.
    """

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"
