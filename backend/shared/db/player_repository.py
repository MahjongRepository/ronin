"""SQLite-backed player repository."""

import asyncio
import json
import logging
import sqlite3
from typing import TYPE_CHECKING

from shared.auth.models import Player
from shared.dal.player_repository import PlayerRepository

if TYPE_CHECKING:
    from shared.db.connection import Database

logger = logging.getLogger(__name__)


class SqlitePlayerRepository(PlayerRepository):
    """SQLite implementation of PlayerRepository.

    Uses a single INSERT under an asyncio lock to avoid race windows
    between existence checks and inserts. Relies on database uniqueness
    constraints and maps IntegrityError to domain ValueError.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = asyncio.Lock()

    async def create_player(self, player: Player) -> None:
        """Insert a player. Raises ValueError on duplicate id, username, or api_key_hash."""
        async with self._lock:
            try:
                self._db.connection.execute(
                    "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
                    (
                        player.user_id,
                        player.username,
                        player.api_key_hash,
                        player.model_dump_json(),
                    ),
                )
                self._db.connection.commit()
            except sqlite3.IntegrityError as exc:
                self._db.connection.rollback()
                error_msg = str(exc).lower()
                if "players.id" in error_msg:
                    raise ValueError(
                        f"Player with id '{player.user_id}' already exists",
                    ) from exc
                if "players.username" in error_msg or "idx_players_username" in error_msg:
                    raise ValueError(
                        f"Username '{player.username}' already taken",
                    ) from exc
                if "players.api_key_hash" in error_msg or "idx_players_api_key_hash" in error_msg:
                    raise ValueError(
                        "API key hash already in use",
                    ) from exc
                raise ValueError(str(exc)) from exc  # pragma: no cover

    async def get_by_username(self, username: str) -> Player | None:
        """Look up a player by username (case-insensitive)."""
        row = self._db.connection.execute(
            "SELECT data FROM players WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if row is None:
            return None
        return Player.model_validate(json.loads(row[0]))

    async def get_by_api_key_hash(self, api_key_hash: str) -> Player | None:
        """Look up a player by API key hash."""
        row = self._db.connection.execute(
            "SELECT data FROM players WHERE api_key_hash = ?",
            (api_key_hash,),
        ).fetchone()
        if row is None:
            return None
        return Player.model_validate(json.loads(row[0]))
