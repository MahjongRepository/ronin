from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol

MAX_BOTS = 3


@dataclass
class Player:
    """Represent a connected player in the session layer.

    Lifecycle:
    - Created on connection registration (game_id=None, seat=None)
    - On join_game: game_id is set
    - On game start (_start_mahjong_game): seat is assigned
    - On leave_game: game_id and seat are cleared to None
    - On unregister: Player is removed from the registry entirely
    """

    connection: ConnectionProtocol
    name: str
    game_id: str | None = None
    seat: int | None = None

    @property
    def connection_id(self) -> str:
        return self.connection.connection_id


@dataclass
class Game:
    game_id: str
    num_bots: int = 3
    started: bool = False
    players: dict[str, Player] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate num_bots is within the allowed range."""
        if not (0 <= self.num_bots <= MAX_BOTS):
            raise ValueError(f"num_bots must be 0-{MAX_BOTS}, got {self.num_bots}")

    @property
    def num_humans_needed(self) -> int:
        """Total number of human players required for this game."""
        return 4 - self.num_bots

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players.values()]

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0
