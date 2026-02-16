"""
Immutable meld representation for frozen state.

Wraps the external mahjong.meld.Meld class to provide true immutability.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from mahjong.meld import Meld
from pydantic import BaseModel, ConfigDict, field_validator

_MIN_MELD_TILES = 3
_MAX_MELD_TILES = 4
_MIN_SEAT = 0
_MAX_SEAT = 3

MeldType = Literal["chi", "pon", "kan", "shouminkan", "chankan"]


class FrozenMeld(BaseModel):
    """
    Immutable representation of a meld.

    Converts to mahjong.meld.Meld at boundaries.
    Provides the same interface as Meld for compatibility.
    """

    model_config = ConfigDict(frozen=True)

    tiles: tuple[int, ...]
    meld_type: MeldType
    opened: bool
    called_tile: int | None = None
    who: int = 0
    from_who: int | None = None

    # Meld type constants (matching mahjong.meld.Meld)
    CHI: ClassVar[MeldType] = "chi"
    PON: ClassVar[MeldType] = "pon"
    KAN: ClassVar[MeldType] = "kan"
    SHOUMINKAN: ClassVar[MeldType] = "shouminkan"
    CHANKAN: ClassVar[MeldType] = "chankan"

    @field_validator("tiles")
    @classmethod
    def _validate_tiles(cls, v: tuple[int, ...]) -> tuple[int, ...]:
        if not (_MIN_MELD_TILES <= len(v) <= _MAX_MELD_TILES):
            raise ValueError(f"meld must have {_MIN_MELD_TILES}-{_MAX_MELD_TILES} tiles, got {len(v)}")
        return v

    @field_validator("who")
    @classmethod
    def _validate_who(cls, v: int) -> int:
        if not (_MIN_SEAT <= v <= _MAX_SEAT):
            raise ValueError(f"who must be in [{_MIN_SEAT}, {_MAX_SEAT}], got {v}")
        return v

    @field_validator("from_who")
    @classmethod
    def _validate_from_who(cls, v: int | None) -> int | None:
        if v is not None and not (_MIN_SEAT <= v <= _MAX_SEAT):
            raise ValueError(f"from_who must be in [{_MIN_SEAT}, {_MAX_SEAT}], got {v}")
        return v

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
