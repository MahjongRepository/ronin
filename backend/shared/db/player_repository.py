import json
import sqlite3
from functools import partial
from typing import TYPE_CHECKING

from shared.dal.models import Player
from shared.dal.player_repository import PlayerRepository

if TYPE_CHECKING:
    from shared.db.connection import Database


class SqlitePlayerRepository(PlayerRepository):
    """
    SQLite implementation of PlayerRepository.

    A single INSERT, with no existence check before it, relies on the database's uniqueness constraints and maps their
    IntegrityError to a domain ValueError.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_player(self, player: Player) -> None:
        """
        Insert a player.

        Raises ValueError on duplicate id, username, or api_key_hash.
        """
        await self._db.submit_write(partial(_insert_player, player=player))

    async def set_api_key_hash(self, user_id: str, api_key_hash: str) -> None:
        """
        Replace the API key hash of the player with this id.

        Raises ValueError when no player has that id.
        """
        await self._db.submit_write(partial(_update_api_key_hash, user_id=user_id, api_key_hash=api_key_hash))

    async def get_by_username(self, username: str) -> Player | None:
        """
        Look up a player by username (case-insensitive).
        """
        query = "SELECT data FROM players WHERE username = ? COLLATE NOCASE"
        return await self._db.submit_read(partial(_select_player, query=query, value=username))

    async def get_by_api_key_hash(self, api_key_hash: str) -> Player | None:
        """
        Look up a player by API key hash.
        """
        query = "SELECT data FROM players WHERE api_key_hash = ?"
        return await self._db.submit_read(partial(_select_player, query=query, value=api_key_hash))


def _insert_player(conn: sqlite3.Connection, *, player: Player) -> None:
    try:
        conn.execute(
            "INSERT INTO players (id, username, api_key_hash, data) VALUES (?, ?, ?, ?)",
            (player.user_id, player.username, player.api_key_hash, player.model_dump_json()),
        )
    except sqlite3.IntegrityError as exc:
        raise _duplicate_player_error(player, exc) from exc


def _update_api_key_hash(conn: sqlite3.Connection, *, user_id: str, api_key_hash: str) -> None:
    cursor = conn.execute(
        "UPDATE players SET api_key_hash = ?, data = json_set(data, '$.api_key_hash', ?) WHERE id = ?",
        (api_key_hash, api_key_hash, user_id),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"Player with id '{user_id}' does not exist")


def _duplicate_player_error(player: Player, exc: sqlite3.IntegrityError) -> ValueError:
    error_msg = str(exc).lower()
    if "players.id" in error_msg:
        return ValueError(f"Player with id '{player.user_id}' already exists")

    if "players.username" in error_msg or "idx_players_username" in error_msg:
        return ValueError(f"Username '{player.username}' already taken")

    if "players.api_key_hash" in error_msg or "idx_players_api_key_hash" in error_msg:
        return ValueError("API key hash already in use")

    return ValueError(str(exc))


def _select_player(conn: sqlite3.Connection, *, query: str, value: str) -> Player | None:
    row = conn.execute(query, (value,)).fetchone()
    if row is None:
        return None

    return Player.model_validate(json.loads(row[0]))
