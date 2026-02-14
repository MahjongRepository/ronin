"""
Immutable meld representation for frozen state.

Wraps the external mahjong.meld.Meld class to provide true immutability.
"""

from __future__ import annotations

from typing import ClassVar

from mahjong.meld import Meld
from pydantic import BaseModel, ConfigDict


class FrozenMeld(BaseModel):
    """
    Immutable representation of a meld.

    Converts to mahjong.meld.Meld at boundaries.
    Provides the same interface as Meld for compatibility.
    """

    model_config = ConfigDict(frozen=True)

    tiles: tuple[int, ...]
    meld_type: str
    opened: bool
    called_tile: int | None = None
    who: int = 0
    from_who: int | None = None

    # Meld type constants (matching mahjong.meld.Meld)
    CHI: ClassVar[str] = "chi"
    PON: ClassVar[str] = "pon"
    KAN: ClassVar[str] = "kan"
    SHOUMINKAN: ClassVar[str] = "shouminkan"
    CHANKAN: ClassVar[str] = "chankan"

    @property
    def type(self) -> str:
        """Alias for meld_type to match Meld interface."""
        return self.meld_type

    def to_meld(self) -> Meld:
        """Convert to mahjong.meld.Meld for library compatibility."""
        return Meld(
            meld_type=self.meld_type,
            tiles=self.tiles,
            opened=self.opened,
            called_tile=self.called_tile,
            who=self.who,
            from_who=self.from_who,
        )


def frozen_melds_to_melds(melds: tuple[FrozenMeld, ...]) -> list[Meld] | None:
    """Convert FrozenMeld tuple to Meld list for external library compatibility."""
    if not melds:
        return None
    return [m.to_meld() for m in melds]
