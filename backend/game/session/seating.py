from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING

from game.engine import NUM_PLAYERS, SEED_BYTES, seat_permutation

if TYPE_CHECKING:
    from collections.abc import Sequence


def generate_seed() -> str:
    """
    Generate a game's seed: SEED_BYTES random bytes from the operating system, as hex (`docs/rng.md`).
    """
    return secrets.token_bytes(SEED_BYTES).hex()


@dataclass(frozen=True)
class Seating:
    """
    Who sits where in a game: every seat's name, by seat, and the seat of each player, in input order.

    The seats no player takes are the AI players'.
    """

    names: tuple[str, ...]
    player_seats: tuple[int, ...]

    @property
    def ai_seats(self) -> frozenset[int]:
        return frozenset(range(NUM_PLAYERS)) - frozenset(self.player_seats)


def seat_players(player_names: Sequence[str], seed: str) -> Seating:
    """
    Seat the players at the first entries of the seed's seat permutation, in input order, and the AI players in the
    remaining seats, named "ai-tsumogiri-N" from 1 up in seat order, skipping the players' names.

    The seating is part of the seed's contract (`docs/rng.md`, Seating): the same seed and names seat the same game.
    """
    player_seats = seat_permutation(seed)[: len(player_names)]
    names_by_seat = dict(zip(player_seats, player_names, strict=True))
    ai_player_names = iter(_ai_player_names(NUM_PLAYERS - len(player_names), taken=player_names))
    names = tuple(
        names_by_seat[seat] if seat in names_by_seat else next(ai_player_names) for seat in range(NUM_PLAYERS)
    )
    return Seating(names=names, player_seats=player_seats)


def _ai_player_names(count: int, *, taken: Sequence[str]) -> list[str]:
    """
    Return count AI player names "ai-tsumogiri-N", numbered up from 1 and skipping the names already taken.
    """
    names: list[str] = []
    number = 1
    while len(names) < count:
        name = f"ai-tsumogiri-{number}"
        if name not in taken:
            names.append(name)

        number += 1

    return names
