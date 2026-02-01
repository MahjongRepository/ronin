"""
Matchmaker for seat assignment and bot filling.

Assigns human players to random seats and fills remaining slots with bots.
"""

import random

from game.logic.enums import BotType
from game.logic.types import SeatConfig

NUM_PLAYERS = 4


def fill_seats(human_names: list[str], seed: float | None = None) -> list[SeatConfig]:
    """
    Create seat configurations for a game.

    Assigns human players to random seats and fills remaining with tsumogiri bots.
    The sample ordering determines which seats get humans AND the order of name assignment,
    so seat randomization works correctly even with all-human games.
    """
    rng = random.Random(seed)  # noqa: S311

    # sample determines which seats get humans AND the order of name assignment
    human_seat_order = rng.sample(range(NUM_PLAYERS), len(human_names))

    # map seat -> human name
    seat_to_human: dict[int, str] = dict(zip(human_seat_order, human_names, strict=True))

    configs: list[SeatConfig] = []
    bot_number = 1

    for seat in range(NUM_PLAYERS):
        if seat in seat_to_human:
            configs.append(SeatConfig(name=seat_to_human[seat]))
        else:
            configs.append(
                SeatConfig(
                    name=f"Tsumogiri {bot_number}",
                    bot_type=BotType.TSUMOGIRI,
                )
            )
            bot_number += 1

    return configs


class Matchmaker:
    """
    Stateless seat assignment wrapper.

    Delegates to fill_seats module function.
    """

    def fill_seats(self, human_names: list[str], seed: float | None = None) -> list[SeatConfig]:
        """
        Create seat configurations for a game.
        """
        return fill_seats(human_names, seed)
