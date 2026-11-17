from dataclasses import dataclass
from enum import StrEnum

from game.logic.enums import KanType  # noqa: TC001


@dataclass(frozen=True, slots=True)
class Discard:
    """
    Discard the held tile: legal for any tile in hand, in riichi only the drawn one, and right after the seat's own pon
    or chi none of a type kuikae forbids.
    """

    tile: int


@dataclass(frozen=True, slots=True)
class Riichi:
    """
    Declare riichi with the discard of the held tile, one that keeps the hand in tenpai.
    """

    tile: int


@dataclass(frozen=True, slots=True)
class Tsumo:
    """
    Declare a win on the seat's own draw.
    """


@dataclass(frozen=True, slots=True)
class Ron:
    """
    Declare a win on the tile a call offers: a discard, or the kan a chankan robs.
    """


@dataclass(frozen=True, slots=True)
class Kyuushu:
    """
    Declare the kyuushu kyuuhai abortive draw.
    """


@dataclass(frozen=True, slots=True)
class Pass:
    """
    Decline every call a call offers the seat, a ron included.
    """


@dataclass(frozen=True, slots=True)
class Pon:
    """
    Call pon on the offered discard with two held tiles of its type, which pick whether a held red five joins the meld.

    Without tiles the engine takes the first offered pair.
    """

    tiles: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class Chi:
    """
    Call chi on the offered discard with two held tiles whose types match one of the offered shapes.
    """

    tiles: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Kan:
    """
    Declare a kan of the offered type on the tile's type: any tile id of that type, the engine resolves the copies.

    An open kan calls the offered discard; a closed or added kan is a turn action.
    """

    kan_type: KanType
    tile: int


type Action = Discard | Riichi | Tsumo | Ron | Kyuushu | Pass | Pon | Chi | Kan
type CallAnswer = Ron | Pon | Chi | Kan


class CallSource(StrEnum):
    """
    What a call offers its tile from: a discard, or a kan a chankan may rob.
    """

    DISCARD = "discard"
    ADDED_KAN = "added_kan"
    CLOSED_KAN = "closed_kan"


@dataclass(frozen=True, slots=True)
class TurnAfterDraw:
    """
    A turn opened by the seat's draw: the drawn tile, whether it came from the dead wall and whether it was the live
    wall's last.
    """

    drawn: int
    rinshan: bool
    haitei: bool


@dataclass(frozen=True, slots=True)
class TurnAfterCall:
    """
    A turn opened by the seat's own pon or chi, which drew nothing: the tile types (34-format) kuikae forbids it to
    discard.
    """

    kuikae: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CallOpportunity:
    """
    A call offered to the seat: the tile, the seat it comes from, its source and whether it is the round's last discard.
    """

    tile: int
    from_seat: int
    source: CallSource
    houtei: bool


type DecisionContext = TurnAfterDraw | TurnAfterCall | CallOpportunity


@dataclass(frozen=True, slots=True)
class Decision:
    """
    What one awaited seat may do now: its context, every legal action and the action a timeout takes for it.

    The default is never a win or a call: the default discard on a turn, a pass on a call.
    """

    seat: int
    context: DecisionContext
    legal: tuple[Action, ...]
    default: Action
