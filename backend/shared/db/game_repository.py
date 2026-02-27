"""SQLite-backed game repository."""

import asyncio
import json
import sqlite3
from typing import TYPE_CHECKING

import structlog

from shared.dal.game_repository import GameRepository
from shared.dal.models import PlayedGame, PlayedGameStanding

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
        num_rounds_played: int | None = None,
        standings: list[PlayedGameStanding] | None = None,
    ) -> None:
        """Update a game's end state. Only updates games that have not already ended.

        When standings is None (abandoned games), preserves existing standings
        from game start (player names, seats, user_ids without scores).
        """
        async with self._lock:
            ended_at_iso = ended_at.isoformat()
            if standings is not None:
                standings_json = json.dumps([s.model_dump() for s in standings])
                cursor = self._db.connection.execute(
                    "UPDATE played_games SET "
                    "ended_at = ?, "
                    "end_reason = ?, "
                    "data = json_set(data, "
                    "  '$.ended_at', ?, "
                    "  '$.end_reason', ?, "
                    "  '$.num_rounds_played', ?, "
                    "  '$.standings', json(?) "
                    ") "
                    "WHERE id = ? AND ended_at IS NULL",
                    (ended_at_iso, end_reason, ended_at_iso, end_reason, num_rounds_played, standings_json, game_id),
                )
            else:
                # Abandoned: do NOT overwrite standings -- preserve start-time player data
                cursor = self._db.connection.execute(
                    "UPDATE played_games SET "
                    "ended_at = ?, "
                    "end_reason = ?, "
                    "data = json_set(data, "
                    "  '$.ended_at', ?, "
                    "  '$.end_reason', ?, "
                    "  '$.num_rounds_played', ? "
                    ") "
                    "WHERE id = ? AND ended_at IS NULL",
                    (ended_at_iso, end_reason, ended_at_iso, end_reason, num_rounds_played, game_id),
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

    async def get_recent_games(self, limit: int = 20) -> list[PlayedGame]:
        """Retrieve the most recent games, ordered by started_at descending."""
        rows = self._db.connection.execute(
            "SELECT data FROM played_games ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [PlayedGame.model_validate(json.loads(row[0])) for row in rows]
