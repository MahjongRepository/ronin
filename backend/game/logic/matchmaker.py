"""
Matchmaker for seat assignment and AI player filling.

Assigns players to random seats and fills remaining slots with AI players.
"""

from game.logic.enums import AIPlayerType
from game.logic.rng import create_seat_rng
from game.logic.settings import NUM_PLAYERS
from game.logic.types import SeatConfig


def _ai_player_names(num_ai: int) -> set[str]:
    """Return the set of AI player names that will be generated."""
    return {f"Tsumogiri {i}" for i in range(1, num_ai + 1)}


def fill_seats(player_names: list[str], seed: str | None = None) -> list[SeatConfig]:
    """
    Create seat configurations for a game.

    Assigns players to random seats and fills remaining with tsumogiri AI players.
    The sample ordering determines which seats get players AND the order of name assignment,
    so seat randomization works correctly even with all-player games.
    """
    if not player_names or len(player_names) > NUM_PLAYERS:
        raise ValueError(f"Expected 1 to {NUM_PLAYERS} player names, got {len(player_names)}")
    player_names = [name.strip() for name in player_names]
    if any(not name for name in player_names):
        raise ValueError("Player names must not be empty or whitespace")
    if len(player_names) != len(set(player_names)):
        raise ValueError("Player names must be unique")
    num_ai = NUM_PLAYERS - len(player_names)
    collisions = _ai_player_names(num_ai) & set(player_names)
    if collisions:
        raise ValueError(f"Player names must not match AI player names: {sorted(collisions)}")

    rng = create_seat_rng(seed)

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
                ),
            )
            ai_player_number += 1

    return configs
