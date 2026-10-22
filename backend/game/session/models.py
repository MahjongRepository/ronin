from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from game.logic.settings import MAX_AI_PLAYERS, GameSettings

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol
    from shared.dal.models import GameEndReason


def validate_num_ai_players(num_ai_players: int) -> None:
    """
    Validate num_ai_players is within the allowed range (0 to MAX_AI_PLAYERS).
    """
    if not (0 <= num_ai_players <= MAX_AI_PLAYERS):
        raise ValueError(f"num_ai_players must be 0-{MAX_AI_PLAYERS}, got {num_ai_players}")


class PlayerSpec(BaseModel):
    """
    Player info for direct game creation.

    The game_ticket field is the signed game ticket string -- the game server uses it as the session token in
    SessionStore, so clients can later present the same ticket in JOIN_GAME to match their session.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    user_id: str = Field(min_length=1, max_length=100)
    game_ticket: str = Field(min_length=1, max_length=2000)


@dataclass
class SessionData:
    """
    Persistent session identity that survives WebSocket disconnects.

    Track a player's session across connection lifecycle events. A session is created when the lobby creates a pending
    game and cleaned up when the game ends.
    """

    session_token: str
    player_name: str
    game_id: str
    user_id: str = ""  # from verified game ticket, for audit/logging
    seat: int | None = None
    disconnected_at: float | None = None  # time.monotonic() timestamp, None if connected
    remaining_bank_seconds: float | None = None  # preserved bank time for reconnection


@dataclass
class Player:
    """
    Represent a connected player in the session layer.

    Lifecycle:
    - Created when joining a pending game via JOIN_GAME (game_id is set)
    - On game start (_start_mahjong_game): seat is assigned
    - On leave_game: game_id and seat are cleared to None
    - On unregister: Player is removed from the registry entirely
    """

    connection: ConnectionProtocol
    name: str
    session_token: str
    user_id: str = ""  # from verified game ticket
    game_id: str | None = None
    seat: int | None = None

    @property
    def connection_id(self) -> str:
        return self.connection.connection_id


@dataclass
class Game:
    game_id: str
    num_ai_players: int = 3
    started: bool = False
    end_reason: GameEndReason | None = None
    players: dict[str, Player] = field(default_factory=dict)
    settings: GameSettings = field(default_factory=GameSettings)

    def __post_init__(self) -> None:
        """
        Validate num_ai_players is within the allowed range.
        """
        validate_num_ai_players(self.num_ai_players)

    @property
    def ended(self) -> bool:
        """
        Whether a path claimed the game's end: set once, by the completion or by fail_game, before any await.
        """
        return self.end_reason is not None

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players.values()]

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0
