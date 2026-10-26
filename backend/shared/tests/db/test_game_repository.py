from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from shared.dal.models import GameEndReason, PlayedGame, PlayedGameStanding
from shared.db.connection import Database
from shared.db.game_repository import SqliteGameRepository

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

_STARTED_AT = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
_ENDED_AT = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)


def _start(game_id: str = "g1", started_at: datetime = _STARTED_AT) -> PlayedGame:
    return PlayedGame(
        game_id=game_id,
        started_at=started_at,
        game_type="hanchan",
        standings=[
            PlayedGameStanding(name="Alice", seat=0, user_id="u1"),
            PlayedGameStanding(name="AI", seat=1),
        ],
    )


def _finish(
    game_id: str = "g1",
    end_reason: GameEndReason = GameEndReason.COMPLETED,
    ended_at: datetime = _ENDED_AT,
    started_at: datetime = _STARTED_AT,
) -> PlayedGame:
    return _start(game_id, started_at).model_copy(
        update={
            "ended_at": ended_at,
            "end_reason": end_reason,
            "num_rounds_played": 8,
            "standings": [
                PlayedGameStanding(name="AI", seat=1, score=35000, final_score=30),
                PlayedGameStanding(name="Alice", seat=0, user_id="u1", score=25000, final_score=-30),
            ],
        },
    )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
async def db(db_path: Path) -> AsyncIterator[Database]:
    database = Database(db_path)
    await database.open()
    yield database
    await database.close()


@pytest.fixture
def repo(db: Database) -> SqliteGameRepository:
    return SqliteGameRepository(db)


def _select_all_games(conn: sqlite3.Connection) -> list[PlayedGame]:
    rows = conn.execute("SELECT data FROM played_games").fetchall()
    return [PlayedGame.model_validate_json(row[0]) for row in rows]


class TestRecordGame:
    async def test_game_repository__when_game_created__should_store_it_unfinished(
        self, repo: SqliteGameRepository, db: Database
    ):
        repo.create_game(_start())

        assert await db.submit_read(_select_all_games) == [_start()]

    async def test_game_repository__when_game_created_twice__should_keep_the_first_and_warn(
        self, repo: SqliteGameRepository, db: Database, caplog: pytest.LogCaptureFixture
    ):
        repo.create_game(_start())
        with caplog.at_level(logging.WARNING):
            repo.create_game(_start().model_copy(update={"game_type": "tonpusen"}))
            games = await db.submit_read(_select_all_games)

        assert games == [_start()]
        assert [r.msg["event"] for r in caplog.records] == ["game already recorded, ignoring its start"]

    async def test_game_repository__when_finished__should_replace_the_start_record_whole(
        self, repo: SqliteGameRepository
    ):
        repo.create_game(_start())
        repo.finish_game(_finish())

        assert await repo.get_recent_completed_games() == [_finish()]

    async def test_game_repository__when_finished_without_a_start_row__should_store_the_whole_record(
        self, repo: SqliteGameRepository
    ):
        repo.finish_game(_finish())

        assert await repo.get_recent_completed_games() == [_finish()]

    async def test_game_repository__when_already_finished__should_keep_the_first_finish(
        self, repo: SqliteGameRepository, caplog: pytest.LogCaptureFixture
    ):
        repo.create_game(_start())
        repo.finish_game(_finish())
        with caplog.at_level(logging.WARNING):
            repo.finish_game(
                _finish(end_reason=GameEndReason.ABANDONED, ended_at=datetime(2025, 1, 15, 14, tzinfo=UTC))
            )
            repo.create_game(_start())
            games = await repo.get_recent_completed_games()

        assert games == [_finish()]
        assert [r.msg["event"] for r in caplog.records] == [
            "game already finished, keeping its first finish",
            "game already recorded, ignoring its start",
        ]

    async def test_game_repository__when_another_connection_holds_the_lock__should_land_start_then_finish_later(
        self, repo: SqliteGameRepository, db_path: Path
    ):
        other_server = sqlite3.connect(db_path, autocommit=True)
        other_server.execute("BEGIN IMMEDIATE")

        repo.create_game(_start())
        repo.finish_game(_finish())
        recent = asyncio.ensure_future(repo.get_recent_completed_games())
        for _ in range(5):
            await asyncio.sleep(0)
        assert not recent.done()
        other_server.execute("COMMIT")

        assert await recent == [_finish()]
        other_server.close()


class TestGetRecentCompletedGames:
    async def test_recent_completed_games__when_several_games__should_order_by_started_at_desc(
        self, repo: SqliteGameRepository
    ):
        repo.finish_game(_finish("g1", started_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)))
        repo.finish_game(_finish("g2", started_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)))
        repo.finish_game(_finish("g3", started_at=datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)))

        result = await repo.get_recent_completed_games()
        assert [g.game_id for g in result] == ["g2", "g3", "g1"]

    async def test_recent_completed_games__when_newer_games_not_completed__should_skip_them_before_the_limit(
        self, repo: SqliteGameRepository
    ):
        for i in range(4):
            repo.finish_game(_finish(f"done{i}", started_at=datetime(2025, 1, 15, i, 0, 0, tzinfo=UTC)))

        for i in range(2):
            repo.create_game(_start(f"live{i}", datetime(2025, 1, 15, 10 + i, 0, 0, tzinfo=UTC)))
            repo.finish_game(
                _finish(
                    f"left{i}",
                    end_reason=GameEndReason.ABANDONED,
                    started_at=datetime(2025, 1, 15, 12 + i, 0, 0, tzinfo=UTC),
                )
            )

        result = await repo.get_recent_completed_games(limit=3)
        assert [g.game_id for g in result] == ["done3", "done2", "done1"]
