from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from game.logic.exceptions import TileOwnershipError
from game.logic.tiles import NUM_TILES

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState, MahjongPlayer

_ALL_TILE_IDS = frozenset(range(NUM_TILES))


def _unclaimed_discards(players: tuple[MahjongPlayer, ...]) -> list[int]:
    """
    Return the discarded tiles still lying on the table.

    A discard stays in its player's history when a meld claims it, so each meld called from another seat removes one
    matching discard from that seat; a claim without its discard is itself a fault.
    """
    discards = [[d.tile_id for d in p.discards] for p in players]
    for player in players:
        for meld in player.melds:
            if meld.called_tile is None or meld.from_who is None or meld.from_who == player.seat:
                continue

            if meld.called_tile not in meld.tiles:
                raise TileOwnershipError(f"seat {player.seat} meld claims tile {meld.called_tile} it does not contain")

            try:
                discards[meld.from_who].remove(meld.called_tile)
            except ValueError:
                message = f"seat {player.seat} melded tile {meld.called_tile} that seat {meld.from_who} never discarded"
                raise TileOwnershipError(message) from None

    return [t for seat_discards in discards for t in seat_discards]


def verify_tile_ownership(state: MahjongGameState) -> None:
    """
    Check that hands, melds, unclaimed discards, the live wall and the dead wall own every tile id exactly once.

    A ron or a chankan leaves the winning tile where it was called from (the discard or the kan), so a finished round
    satisfies the same partition as a running one.
    """
    round_state = state.round_state
    owned: list[int] = []
    for player in round_state.players:
        owned.extend(player.tiles)
        for meld in player.melds:
            owned.extend(meld.tiles)

    owned.extend(_unclaimed_discards(round_state.players))
    owned.extend(round_state.wall.live_tiles)
    owned.extend(round_state.wall.dead_wall.tiles)

    if len(owned) == NUM_TILES and set(owned) == _ALL_TILE_IDS:
        return

    counts = Counter(owned)
    duplicated = sorted(t for t, n in counts.items() if n > 1)
    missing = sorted(_ALL_TILE_IDS - counts.keys())
    unknown = sorted(t for t in counts if t not in _ALL_TILE_IDS)
    raise TileOwnershipError(f"tile ownership broken: duplicated={duplicated} missing={missing} unknown={unknown}")
