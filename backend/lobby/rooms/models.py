"""Room models for the lobby server."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import BaseModel


class LobbyPlayerInfo(BaseModel):
    """Player info for room state messages (sent over WebSocket)."""

    name: str
    ready: bool


@dataclass
class LobbyPlayer:
    """Player connected to a lobby room via WebSocket."""

    connection_id: str
    user_id: str
    username: str
    ready: bool = False


@dataclass
class LobbyRoom:
    """Pre-game room managed by the lobby server."""

    room_id: str
    num_ai_players: int = 3
    host_connection_id: str | None = None
    transitioning: bool = False
    created_at: float = field(default_factory=time.monotonic)
    players: dict[str, LobbyPlayer] = field(default_factory=dict)  # connection_id -> LobbyPlayer

    @property
    def players_needed(self) -> int:
        return 4 - self.num_ai_players

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_full(self) -> bool:
        return self.player_count >= self.players_needed

    @property
    def is_empty(self) -> bool:
        return self.player_count == 0

    @property
    def all_ready(self) -> bool:
        return self.is_full and all(p.ready for p in self.players.values())

    @property
    def player_names(self) -> list[str]:
        return [p.username for p in self.players.values()]

    def get_player_info(self) -> list[LobbyPlayerInfo]:
        return [LobbyPlayerInfo(name=p.username, ready=p.ready) for p in self.players.values()]

    def has_user(self, user_id: str) -> bool:
        """Check if a user is already in this room (prevents multi-tab seat hogging)."""
        return any(p.user_id == user_id for p in self.players.values())
