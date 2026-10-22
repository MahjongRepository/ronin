from game.logic.enums import AIPlayerType
from game.logic.rng import create_seat_rng
from game.logic.settings import NUM_PLAYERS
from game.logic.types import SeatConfig


def _generate_ai_player_names(count: int, taken_names: list[str]) -> list[str]:
    """
    Return `count` AI player names "Tsumogiri N", numbered up from 1 and skipping the names already taken.
    """
    names: list[str] = []
    number = 1
    while len(names) < count:
        name = f"Tsumogiri {number}"
        if name not in taken_names:
            names.append(name)

        number += 1

    return names


def fill_seats(player_names: list[str], seed: str | None = None) -> tuple[list[SeatConfig], tuple[int, ...]]:
    """
    Create seat configurations for a game; return them by seat, with the seat of each input player in input order.

    Assigns players to random seats and fills the remaining ones with tsumogiri AI players, whose names skip the
    players' names. The sample ordering determines which seats get players AND which player sits where, so seat
    randomization works correctly even with all-player games; the replay loader inverts this exact sample.
    """
    if not player_names or len(player_names) > NUM_PLAYERS:
        raise ValueError(f"Expected 1 to {NUM_PLAYERS} player names, got {len(player_names)}")

    rng = create_seat_rng(seed)
    player_seats = tuple(rng.sample(range(NUM_PLAYERS), len(player_names)))
    seat_to_player = dict(zip(player_seats, player_names, strict=True))
    ai_player_names = iter(_generate_ai_player_names(NUM_PLAYERS - len(player_names), player_names))

    configs: list[SeatConfig] = []
    for seat in range(NUM_PLAYERS):
        if seat in seat_to_player:
            configs.append(SeatConfig(name=seat_to_player[seat]))
        else:
            configs.append(SeatConfig(name=next(ai_player_names), ai_player_type=AIPlayerType.TSUMOGIRI))

    return configs, player_seats
