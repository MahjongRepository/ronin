"""
String enum definitions for Mahjong game concepts.
"""

from enum import Enum


class PlayerAction(str, Enum):
    """Actions available to a player during their turn."""

    DISCARD = "discard"
    RIICHI = "riichi"
    TSUMO = "tsumo"
    KAN = "kan"
    ADDED_KAN = "added_kan"
    KYUUSHU = "kyuushu"


class GameAction(str, Enum):
    """Actions dispatched from client to game service."""

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


class MeldCallType(str, Enum):
    """Types of meld calls that can be made on a discarded tile."""

    PON = "pon"
    CHI = "chi"
    OPEN_KAN = "open_kan"
    CLOSED_KAN = "closed_kan"
    ADDED_KAN = "added_kan"


# priority order for meld calls: kan > pon > chi
MELD_CALL_PRIORITY: dict[MeldCallType, int] = {
    MeldCallType.OPEN_KAN: 0,
    MeldCallType.PON: 1,
    MeldCallType.CHI: 2,
}


class KanType(str, Enum):
    """Subtypes of kan declarations."""

    OPEN = "open"
    CLOSED = "closed"
    ADDED = "added"

    def to_meld_call_type(self) -> MeldCallType:
        """Convert kan type to the corresponding meld call type."""
        return _KAN_TO_MELD_CALL[self]


_KAN_TO_MELD_CALL: dict[KanType, MeldCallType] = {
    KanType.OPEN: MeldCallType.OPEN_KAN,
    KanType.CLOSED: MeldCallType.CLOSED_KAN,
    KanType.ADDED: MeldCallType.ADDED_KAN,
}


class CallType(str, Enum):
    """Types of call prompts sent to players."""

    RON = "ron"
    MELD = "meld"
    CHANKAN = "chankan"


class AbortiveDrawType(str, Enum):
    """Types of abortive draws in Mahjong."""

    NINE_TERMINALS = "nine_terminals"
    FOUR_RIICHI = "four_riichi"
    TRIPLE_RON = "triple_ron"
    FOUR_KANS = "four_kans"
    FOUR_WINDS = "four_winds"


class RoundResultType(str, Enum):
    """Types of round end results."""

    TSUMO = "tsumo"
    RON = "ron"
    DOUBLE_RON = "double_ron"
    EXHAUSTIVE_DRAW = "exhaustive_draw"
    ABORTIVE_DRAW = "abortive_draw"
    NAGASHI_MANGAN = "nagashi_mangan"
    GAME_END = "game_end"


class WindName(str, Enum):
    """Wind direction names."""

    EAST = "East"
    SOUTH = "South"
    WEST = "West"
    NORTH = "North"
    UNKNOWN = "Unknown"


class BotType(str, Enum):
    """Types of bot players available for matchmaking."""

    TSUMOGIRI = "tsumogiri"


class TimeoutType(str, Enum):
    """Types of player timeouts."""

    TURN = "turn"
    MELD = "meld"
    ROUND_ADVANCE = "round_advance"


class GameMode(str, Enum):
    """Game modes for matchmaking."""

    BOT = "bot"
    PVP = "pvp"


class MeldViewType(str, Enum):
    """Meld type names for client-facing view."""

    CHI = "chi"
    PON = "pon"
    KAN = "kan"
    CHANKAN = "chankan"
    SHOUMINKAN = "shouminkan"
    UNKNOWN = "unknown"
