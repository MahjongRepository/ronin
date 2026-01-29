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
    """
    rng = random.Random(seed)  # noqa: S311

    all_seats = list(range(NUM_PLAYERS))
    human_seats = set(rng.sample(all_seats, len(human_names)))

    configs: list[SeatConfig] = []
    human_index = 0
    bot_number = 1

    for seat in range(NUM_PLAYERS):
        if seat in human_seats:
            configs.append(
                SeatConfig(
                    name=human_names[human_index],
                    is_bot=False,
                )
            )
            human_index += 1
        else:
            configs.append(
                SeatConfig(
                    name=f"Tsumogiri {bot_number}",
                    is_bot=True,
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
