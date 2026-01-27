from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.messaging.protocol import ConnectionProtocol


@dataclass
class Player:
    connection: ConnectionProtocol
    name: str
    game_id: str | None = None

    @property
    def connection_id(self) -> str:
        return self.connection.connection_id


@dataclass
class Game:
    game_id: str
    players: dict[str, Player] = field(default_factory=dict)
    game_state: dict = field(default_factory=dict)

    @property
    def player_names(self) -> list[str]:
        return [p.name for p in self.players.values()]

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0
