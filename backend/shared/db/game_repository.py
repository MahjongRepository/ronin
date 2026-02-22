"""SQLite-backed game repository."""

import asyncio
import json
import sqlite3
from typing import TYPE_CHECKING

import structlog

from shared.dal.game_repository import GameRepository
from shared.dal.models import PlayedGame

if TYPE_CHECKING:
    from datetime import datetime

    from shared.db.connection import Database

logger = structlog.get_logger()


class SqliteGameRepository(GameRepository):
    """SQLite implementation of GameRepository.

    Stores full game snapshots as JSON with indexed columns for queries.
    Uses json_each for player-based lookups.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._lock = asyncio.Lock()

    async def create_game(self, game: PlayedGame) -> None:
        """Insert a game record. Logs a warning and returns on duplicate game_id."""
        async with self._lock:
            try:
                self._db.connection.execute(
                    "INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?)",
                    (
                        game.game_id,
                        game.started_at.isoformat(),
                        game.ended_at.isoformat() if game.ended_at else None,
                        game.end_reason,
                        game.model_dump_json(),
                    ),
                )
                self._db.connection.commit()
            except sqlite3.IntegrityError:
                self._db.connection.rollback()
                logger.warning("game already exists, ignoring duplicate create", game_id=game.game_id)

    async def finish_game(
        self,
        game_id: str,
        ended_at: datetime,
        end_reason: str = "completed",
    ) -> None:
        """Update a game's end state. Only updates games that have not already ended."""
        async with self._lock:
            ended_at_iso = ended_at.isoformat()
            cursor = self._db.connection.execute(
                "UPDATE played_games SET "
                "ended_at = ?, "
                "end_reason = ?, "
                "data = json_set(data, '$.ended_at', ?, '$.end_reason', ?) "
                "WHERE id = ? AND ended_at IS NULL",
                (ended_at_iso, end_reason, ended_at_iso, end_reason, game_id),
            )
            self._db.connection.commit()
            if cursor.rowcount == 0:
                logger.warning("finish_game had no effect (not found or already ended)", game_id=game_id)

    async def get_game(self, game_id: str) -> PlayedGame | None:
        """Retrieve a single game by its id."""
        row = self._db.connection.execute(
            "SELECT data FROM played_games WHERE id = ?",
            (game_id,),
        ).fetchone()
        if row is None:
            return None
        return PlayedGame.model_validate(json.loads(row[0]))

    async def get_games_by_player(self, player_id: str) -> list[PlayedGame]:
        """Retrieve all games a player participated in, ordered by started_at descending."""
        rows = self._db.connection.execute(
            "SELECT pg.data FROM played_games pg, json_each(pg.data, '$.player_ids') je "
            "WHERE je.value = ? "
            "ORDER BY pg.started_at DESC",
            (player_id,),
        ).fetchall()
        return [PlayedGame.model_validate(json.loads(row[0])) for row in rows]
