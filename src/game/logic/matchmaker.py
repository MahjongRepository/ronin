"""
Matchmaker for seat assignment and AI player filling.

Assigns players to random seats and fills remaining slots with AI players.
"""

import random

from game.logic.enums import AIPlayerType
from game.logic.types import SeatConfig

NUM_PLAYERS = 4


def fill_seats(player_names: list[str], seed: float | None = None) -> list[SeatConfig]:
    """
    Create seat configurations for a game.

    Assigns players to random seats and fills remaining with tsumogiri AI players.
    The sample ordering determines which seats get players AND the order of name assignment,
    so seat randomization works correctly even with all-player games.
    """
    rng = random.Random(seed)  # noqa: S311

    # sample determines which seats get players AND the order of name assignment
    player_seat_order = rng.sample(range(NUM_PLAYERS), len(player_names))

    # map seat -> player name
    seat_to_player: dict[int, str] = dict(zip(player_seat_order, player_names, strict=True))

    configs: list[SeatConfig] = []
    ai_player_number = 1

    for seat in range(NUM_PLAYERS):
        if seat in seat_to_player:
            configs.append(SeatConfig(name=seat_to_player[seat]))
        else:
            configs.append(
                SeatConfig(
                    name=f"Tsumogiri {ai_player_number}",
                    ai_player_type=AIPlayerType.TSUMOGIRI,
                )
            )
            ai_player_number += 1

    return configs
