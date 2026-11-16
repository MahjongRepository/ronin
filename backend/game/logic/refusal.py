from dataclasses import dataclass
from enum import StrEnum


class RefusalKind(StrEnum):
    """
    Which kind of mistake a refusal reports.

    RULE: a held tile or an offered action that a rule forbids now. NOT_OFFERED: structurally impossible input, a tile
    not held or an action the seat was not offered. NOT_AWAITED: a call in the wrong phase, an action from a seat the
    engine is not waiting on, or an action for another decision than the seat's (a pass on its own turn, a discard
    during a call).
    """

    RULE = "rule"
    NOT_OFFERED = "not_offered"
    NOT_AWAITED = "not_awaited"


class RefusalCode(StrEnum):
    """
    What exactly a refusal refused: a reason, never a wire code.
    """

    TILE_NOT_HELD = "tile_not_held"
    NOT_OFFERED = "not_offered"
    WRONG_PHASE = "wrong_phase"
    SEAT_NOT_AWAITED = "seat_not_awaited"
    ALREADY_ANSWERED = "already_answered"
    RIICHI_DRAWN_TILE_ONLY = "riichi_drawn_tile_only"
    RIICHI_BREAKS_TENPAI = "riichi_breaks_tenpai"
    KUIKAE = "kuikae"


@dataclass(frozen=True, slots=True)
class Refusal:
    """
    A refused engine call: its kind and its reason.

    A refused call leaves the game unchanged.
    """

    kind: RefusalKind
    code: RefusalCode
