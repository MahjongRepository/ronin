from dataclasses import dataclass


@dataclass(frozen=True)
class GameRoster:
    """
    Who plays a game, as its messages name them: the game's id, every seat's name by seat, and the seats AI players hold
    from the start, where no participant sits.
    """

    game_id: str
    names: tuple[str, ...]
    ai_seats: frozenset[int]
