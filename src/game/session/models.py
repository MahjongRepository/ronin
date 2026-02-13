from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from game.logic.settings import GameSettings

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol

MAX_BOTS = 3
TOTAL_PLAYERS = 4


def validate_num_bots(num_bots: int) -> None:
    """Validate num_bots is within the allowed range (0 to MAX_BOTS)."""
    if not (0 <= num_bots <= MAX_BOTS):
        raise ValueError(f"num_bots must be 0-{MAX_BOTS}, got {num_bots}")


@dataclass
class SessionData:
    """Persistent session identity that survives WebSocket disconnects.

    Track a player's session across connection lifecycle events.
    A session is created during room-to-game transition and cleaned up when the game ends.
    """

    session_token: str
    player_name: str
    game_id: str
    seat: int | None = None
    disconnected_at: float | None = None  # time.monotonic() timestamp, None if connected


@dataclass
class Player:
    """Represent a connected player in the session layer.

    Lifecycle:
    - Created during room-to-game transition (game_id is set)
    - On game start (_start_mahjong_game): seat is assigned
    - On leave_game: game_id and seat are cleared to None
    - On unregister: Player is removed from the registry entirely
    """

    connection: ConnectionProtocol
    name: str
    session_token: str
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
    settings: GameSettings = field(default_factory=GameSettings)

    def __post_init__(self) -> None:
        """Validate num_bots is within the allowed range."""
        validate_num_bots(self.num_bots)

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players.values()]

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0
