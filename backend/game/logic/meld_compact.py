"""Bridge between game meld objects and the shared IMME compact encoding.

The shared lib (shared.lib.melds) is dependency-free and uses MeldData TypedDict.
This module converts game-specific objects to/from MeldData at the boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.meld_wrapper import FrozenMeld
from shared.lib.melds import MeldData, MeldType, encode_meld_compact

if TYPE_CHECKING:
    from game.logic.events import MeldEvent

# FrozenMeld meld_type -> MeldData meld_type (wire vocabulary).
# FrozenMeld.KAN is handled separately because it needs the `opened` flag
# to distinguish open_kan vs closed_kan.
_FROZEN_TO_WIRE_TYPE: dict[str, MeldType] = {
    FrozenMeld.CHI: "chi",
    FrozenMeld.PON: "pon",
    FrozenMeld.SHOUMINKAN: "added_kan",
    FrozenMeld.CHANKAN: "added_kan",
}


def _frozen_meld_wire_type(meld: FrozenMeld) -> MeldType:
    """Resolve the wire-format meld type for a FrozenMeld."""
    if meld.meld_type == FrozenMeld.KAN:
        return "open_kan" if meld.opened else "closed_kan"
    wire_type = _FROZEN_TO_WIRE_TYPE.get(meld.meld_type)
    if wire_type is None:
        raise ValueError(f"Unknown FrozenMeld type: {meld.meld_type!r}")
    return wire_type


def frozen_meld_to_meld_data(meld: FrozenMeld) -> MeldData:
    """Convert a FrozenMeld to a MeldData dict for IMME encoding."""
    return MeldData(
        type="meld",
        meld_type=_frozen_meld_wire_type(meld),
        caller_seat=meld.who,
        from_seat=meld.from_who,
        tile_ids=list(meld.tiles),
        called_tile_id=meld.called_tile,
    )


def frozen_meld_to_compact(meld: FrozenMeld) -> int:
    """Encode a FrozenMeld as a single IMME integer."""
    return encode_meld_compact(frozen_meld_to_meld_data(meld))


def meld_event_to_meld_data(event: MeldEvent) -> MeldData:
    """Convert a MeldEvent domain object to a MeldData dict."""
    return MeldData(
        type="meld",
        meld_type=event.meld_type.value,
        caller_seat=event.caller_seat,
        from_seat=event.from_seat,
        tile_ids=list(event.tile_ids),
        called_tile_id=event.called_tile_id,
    )


def meld_event_to_compact(event: MeldEvent) -> int:
    """Encode a MeldEvent as a single IMME integer."""
    return encode_meld_compact(meld_event_to_meld_data(event))
