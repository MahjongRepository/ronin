from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING

from shared.dal.models import Tournament, TournamentGame
from shared.dal.tournament_repository import TournamentRepository

if TYPE_CHECKING:
    import sqlite3

    from shared.db.connection import Database


class SqliteTournamentRepository(TournamentRepository):
    """
    SQLite implementation of TournamentRepository.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create_tournament(self, tournament: Tournament) -> None:
        """
        Insert a tournament.
        """
        await self._db.submit_write(partial(_insert_tournament, tournament=tournament))

    async def get_tournament(self, tournament_id: str) -> Tournament | None:
        """
        Return the tournament with this id, or None when there is none.
        """
        return await self._db.submit_read(partial(_select_tournament, tournament_id=tournament_id))

    async def list_tournaments_by_owner(self, owner_user_id: str) -> list[Tournament]:
        """
        Return the tournaments this user owns, newest first.
        """
        return await self._db.submit_read(partial(_select_tournaments_by_owner, owner_user_id=owner_user_id))

    async def add_game(self, game: TournamentGame) -> None:
        """
        Insert a game started for a tournament.
        """
        await self._db.submit_write(partial(_insert_game, game=game))

    async def list_games(self, tournament_id: str) -> list[TournamentGame]:
        """
        Return the tournament's games, oldest first.
        """
        return await self._db.submit_read(partial(_select_games, tournament_id=tournament_id))


def _insert_tournament(conn: sqlite3.Connection, *, tournament: Tournament) -> None:
    conn.execute(
        "INSERT INTO tournaments (id, name, owner_user_id, created_at) VALUES (?, ?, ?, ?)",
        (tournament.id, tournament.name, tournament.owner_user_id, tournament.created_at),
    )


def _select_tournament(conn: sqlite3.Connection, *, tournament_id: str) -> Tournament | None:
    row = conn.execute(
        "SELECT id, name, owner_user_id, created_at FROM tournaments WHERE id = ?", (tournament_id,)
    ).fetchone()
    return None if row is None else _tournament_from_row(row)


def _select_tournaments_by_owner(conn: sqlite3.Connection, *, owner_user_id: str) -> list[Tournament]:
    rows = conn.execute(
        "SELECT id, name, owner_user_id, created_at FROM tournaments WHERE owner_user_id = ? ORDER BY created_at DESC",
        (owner_user_id,),
    ).fetchall()
    return [_tournament_from_row(row) for row in rows]


def _tournament_from_row(row: tuple[str, str, str, float]) -> Tournament:
    tournament_id, name, owner_user_id, created_at = row
    return Tournament(id=tournament_id, name=name, owner_user_id=owner_user_id, created_at=created_at)


def _insert_game(conn: sqlite3.Connection, *, game: TournamentGame) -> None:
    conn.execute(
        "INSERT INTO tournament_games (game_id, tournament_id, players, created_at) VALUES (?, ?, ?, ?)",
        (game.game_id, game.tournament_id, json.dumps(game.players), game.created_at),
    )


def _select_games(conn: sqlite3.Connection, *, tournament_id: str) -> list[TournamentGame]:
    rows = conn.execute(
        "SELECT game_id, tournament_id, players, created_at, ended_at, end_reason, result FROM tournament_games "
        "WHERE tournament_id = ? ORDER BY created_at, rowid",
        (tournament_id,),
    ).fetchall()
    return [_game_from_row(row) for row in rows]


def _game_from_row(row: tuple[str, str, str, float, float | None, str | None, str | None]) -> TournamentGame:
    game_id, tournament_id, players, created_at, ended_at, end_reason, result = row
    return TournamentGame.model_validate(
        {
            "game_id": game_id,
            "tournament_id": tournament_id,
            "players": json.loads(players),
            "created_at": created_at,
            "ended_at": ended_at,
            "end_reason": end_reason,
            "result": None if result is None else json.loads(result),
        }
    )
