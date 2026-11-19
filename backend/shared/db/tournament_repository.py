from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING

from shared.dal.models import Tournament, TournamentGame, TournamentGameCounts
from shared.dal.tournament_repository import TournamentRepository

if TYPE_CHECKING:
    import sqlite3

    from shared.dal.models import GameEndReason, PlayedGameStanding
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

    async def count_games_by_owner(self, owner_user_id: str) -> dict[str, TournamentGameCounts]:
        """
        Return the game counts of this user's tournaments by tournament id; a tournament without games is absent.
        """
        return await self._db.submit_read(partial(_count_games_by_owner, owner_user_id=owner_user_id))

    async def rename_tournament(self, tournament_id: str, name: str) -> None:
        """
        Give the tournament a new name.
        """
        await self._db.submit_write(partial(_update_tournament_name, tournament_id=tournament_id, name=name))

    async def delete_tournament(self, tournament_id: str) -> None:
        """
        Remove the tournament and the record of its games in one write.
        """
        await self._db.submit_write(partial(_delete_tournament, tournament_id=tournament_id))

    async def add_game(self, game: TournamentGame) -> None:
        """
        Insert a game started for a tournament.
        """
        await self._db.submit_write(partial(_insert_game, game=game))

    async def get_game(self, game_id: str) -> TournamentGame | None:
        """
        Return the tournament game with this id, or None when no tournament started it.
        """
        return await self._db.submit_read(partial(_select_game, game_id=game_id))

    async def list_games(self, tournament_id: str) -> list[TournamentGame]:
        """
        Return the tournament's games, oldest first.
        """
        return await self._db.submit_read(partial(_select_games, tournament_id=tournament_id))

    async def list_unfinished_games(self) -> list[TournamentGame]:
        """
        Return every tournament's games that have no finish yet, oldest first.
        """
        return await self._db.submit_read(_select_unfinished_games)

    async def finish_game(
        self, game_id: str, *, ended_at: float, end_reason: GameEndReason, result: list[PlayedGameStanding]
    ) -> bool:
        """
        Record a tournament game's finish; return False when the game is unknown or already finished.
        """
        return await self._db.submit_write(
            partial(_update_game_finish, game_id=game_id, ended_at=ended_at, end_reason=end_reason, result=result)
        )


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


def _count_games_by_owner(conn: sqlite3.Connection, *, owner_user_id: str) -> dict[str, TournamentGameCounts]:
    rows = conn.execute(
        "SELECT g.tournament_id, SUM(g.ended_at IS NULL), SUM(g.ended_at IS NOT NULL) FROM tournament_games g "
        "JOIN tournaments t ON t.id = g.tournament_id WHERE t.owner_user_id = ? GROUP BY g.tournament_id",
        (owner_user_id,),
    ).fetchall()
    return {
        tournament_id: TournamentGameCounts(playing=playing, finished=finished)
        for tournament_id, playing, finished in rows
    }


def _update_tournament_name(conn: sqlite3.Connection, *, tournament_id: str, name: str) -> None:
    conn.execute("UPDATE tournaments SET name = ? WHERE id = ?", (name, tournament_id))


def _delete_tournament(conn: sqlite3.Connection, *, tournament_id: str) -> None:
    conn.execute("DELETE FROM tournament_games WHERE tournament_id = ?", (tournament_id,))
    conn.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))


def _tournament_from_row(row: tuple[str, str, str, float]) -> Tournament:
    tournament_id, name, owner_user_id, created_at = row
    return Tournament(id=tournament_id, name=name, owner_user_id=owner_user_id, created_at=created_at)


def _insert_game(conn: sqlite3.Connection, *, game: TournamentGame) -> None:
    conn.execute(
        "INSERT INTO tournament_games (game_id, tournament_id, players, created_at) VALUES (?, ?, ?, ?)",
        (game.game_id, game.tournament_id, json.dumps(game.players), game.created_at),
    )


def _select_game(conn: sqlite3.Connection, *, game_id: str) -> TournamentGame | None:
    row = conn.execute(
        "SELECT game_id, tournament_id, players, created_at, ended_at, end_reason, result FROM tournament_games "
        "WHERE game_id = ?",
        (game_id,),
    ).fetchone()
    return None if row is None else _game_from_row(row)


def _select_games(conn: sqlite3.Connection, *, tournament_id: str) -> list[TournamentGame]:
    rows = conn.execute(
        "SELECT game_id, tournament_id, players, created_at, ended_at, end_reason, result FROM tournament_games "
        "WHERE tournament_id = ? ORDER BY created_at, rowid",
        (tournament_id,),
    ).fetchall()
    return [_game_from_row(row) for row in rows]


def _select_unfinished_games(conn: sqlite3.Connection) -> list[TournamentGame]:
    rows = conn.execute(
        "SELECT game_id, tournament_id, players, created_at, ended_at, end_reason, result FROM tournament_games "
        "WHERE ended_at IS NULL ORDER BY created_at, rowid"
    ).fetchall()
    return [_game_from_row(row) for row in rows]


def _update_game_finish(
    conn: sqlite3.Connection,
    *,
    game_id: str,
    ended_at: float,
    end_reason: GameEndReason,
    result: list[PlayedGameStanding],
) -> bool:
    cursor = conn.execute(
        "UPDATE tournament_games SET ended_at = ?, end_reason = ?, result = ? WHERE game_id = ? AND ended_at IS NULL",
        (ended_at, end_reason, json.dumps([standing.model_dump(mode="json") for standing in result]), game_id),
    )
    return cursor.rowcount > 0


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
