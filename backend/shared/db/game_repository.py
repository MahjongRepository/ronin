import json
from functools import partial
from typing import TYPE_CHECKING

import structlog

from shared.dal.game_repository import GameRepository
from shared.dal.models import PlayedGame

if TYPE_CHECKING:
    import sqlite3

    from shared.db.connection import Database

logger = structlog.get_logger()


class SqliteGameRepository(GameRepository):
    """
    SQLite implementation of GameRepository.

    Stores full game snapshots as JSON with indexed columns for queries.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def create_game(self, game: PlayedGame) -> None:
        self._db.post_write(partial(_insert_game_start, game=game), operation="create_game", game_id=game.game_id)

    def finish_game(self, game: PlayedGame) -> None:
        self._db.post_write(partial(_upsert_game_finish, game=game), operation="finish_game", game_id=game.game_id)

    async def get_recent_games(self, limit: int = 20) -> list[PlayedGame]:
        """
        Retrieve the most recent games, ordered by started_at descending.
        """
        return await self._db.submit_read(partial(_select_recent_games, limit=limit))


def _game_row(game: PlayedGame) -> tuple[str, str, str | None, str | None, str]:
    return (
        game.game_id,
        game.started_at.isoformat(),
        game.ended_at.isoformat() if game.ended_at else None,
        game.end_reason,
        game.model_dump_json(),
    )


def _insert_game_start(conn: sqlite3.Connection, *, game: PlayedGame) -> None:
    cursor = conn.execute(
        "INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO NOTHING",
        _game_row(game),
    )
    if cursor.rowcount == 0:
        logger.warning("game already recorded, ignoring its start", game_id=game.game_id)


def _upsert_game_finish(conn: sqlite3.Connection, *, game: PlayedGame) -> None:
    cursor = conn.execute(
        "INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET "
        "ended_at = excluded.ended_at, end_reason = excluded.end_reason, data = excluded.data "
        "WHERE played_games.ended_at IS NULL",
        _game_row(game),
    )
    if cursor.rowcount == 0:
        logger.warning("game already finished, keeping its first finish", game_id=game.game_id)


def _select_recent_games(conn: sqlite3.Connection, *, limit: int) -> list[PlayedGame]:
    rows = conn.execute(
        "SELECT data FROM played_games ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [PlayedGame.model_validate(json.loads(row[0])) for row in rows]
