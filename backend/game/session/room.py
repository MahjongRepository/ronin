"""Room model for pre-game lobby phase."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel

from game.logic.settings import NUM_PLAYERS, GameSettings
from game.session.models import validate_num_ai_players

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol


class RoomPlayerInfo(BaseModel):
    """Player info for room state messages."""

    name: str
    ready: bool


@dataclass
class RoomPlayer:
    """Represent a player in a room (pre-game lobby).

    Tracks the player's connection, name, readiness, and room association.
    """

    connection: ConnectionProtocol
    name: str
    room_id: str
    session_token: str
    user_id: str = ""  # from verified game ticket
    ready: bool = False

    @property
    def connection_id(self) -> str:
        return self.connection.connection_id


@dataclass
class Room:
    """Pre-game lobby where players gather before starting a game.

    Players join the room, toggle readiness, and chat. The game starts
    only when all required players are ready.
    """

    room_id: str
    num_ai_players: int = 3
    host_connection_id: str | None = None
    transitioning: bool = False
    players: dict[str, RoomPlayer] = field(default_factory=dict)  # connection_id -> RoomPlayer
    settings: GameSettings = field(default_factory=GameSettings)

    def __post_init__(self) -> None:
        """Validate num_ai_players is within the allowed range."""
        validate_num_ai_players(self.num_ai_players)

    @property
    def players_needed(self) -> int:
        return NUM_PLAYERS - self.num_ai_players

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players.values()]

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def total_seats(self) -> int:
        return NUM_PLAYERS

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0

    @property
    def is_full(self) -> bool:
        return self.player_count >= self.players_needed

    @property
    def all_ready(self) -> bool:
        """Check if all required players are present and ready."""
        return self.is_full and all(p.ready for p in self.players.values())

    def get_player_info(self) -> list[RoomPlayerInfo]:
        """Return player info for room state messages."""
        return [RoomPlayerInfo(name=p.name, ready=p.ready) for p in self.players.values()]
