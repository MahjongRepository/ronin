from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from shared.dal.models import PlayedGame, PlayedGameStanding
from shared.db.connection import Database
from shared.db.game_repository import SqliteGameRepository

if TYPE_CHECKING:
    from pathlib import Path


def _game(
    game_id: str = "g1",
    started_at: datetime | None = None,
) -> PlayedGame:
    return PlayedGame(
        game_id=game_id,
        started_at=started_at or datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def repo(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.connect()
    yield SqliteGameRepository(db)
    db.close()


class TestCreateAndGet:
    async def test_game_repository__when_game_created__should_return_it_unfinished(self, repo: SqliteGameRepository):
        game = _game()
        await repo.create_game(game)

        result = await repo.get_game("g1")
        assert result is not None
        assert result.game_id == "g1"
        assert result.ended_at is None
        assert result.end_reason is None

    async def test_game_repository__when_game_unknown__should_return_none(self, repo: SqliteGameRepository):
        assert await repo.get_game("nonexistent") is None

    async def test_game_repository__when_game_created_twice__should_not_raise(self, repo: SqliteGameRepository):
        game = _game()
        await repo.create_game(game)
        # Second create should not raise, just log a warning
        await repo.create_game(game)

        result = await repo.get_game("g1")
        assert result is not None


class TestFinishGame:
    async def test_game_repository__when_game_finished__should_store_end_time_and_reason(
        self, repo: SqliteGameRepository
    ):
        await repo.create_game(_game())
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game(game_id="g1", ended_at=end_time, end_reason="completed")

        result = await repo.get_game("g1")
        assert result is not None
        assert result.ended_at == end_time
        assert result.end_reason == "completed"

    async def test_game_repository__when_game_already_ended__should_keep_original_end(self, repo: SqliteGameRepository):
        await repo.create_game(_game())
        first_end = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game(game_id="g1", ended_at=first_end, end_reason="completed")

        second_end = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        await repo.finish_game(game_id="g1", ended_at=second_end, end_reason="abandoned")

        # Original end state is preserved
        result = await repo.get_game("g1")
        assert result is not None
        assert result.ended_at == first_end
        assert result.end_reason == "completed"

    async def test_game_repository__when_finished_with_standings__should_persist_scores(
        self, repo: SqliteGameRepository
    ):
        standings = [
            PlayedGameStanding(name="Alice", seat=0, user_id="u1", score=35000, final_score=30),
            PlayedGameStanding(name="Bob", seat=1, user_id="u2", score=25000, final_score=0),
        ]
        await repo.create_game(_game())
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game(game_id="g1", ended_at=end_time, num_rounds_played=8, standings=standings)

        result = await repo.get_game("g1")
        assert result is not None
        assert result.num_rounds_played == 8
        assert len(result.standings) == 2
        assert result.standings[0].name == "Alice"
        assert result.standings[0].final_score == 30
        assert result.standings[1].name == "Bob"

    async def test_game_repository__when_abandoned__should_keep_start_standings(self, repo: SqliteGameRepository):
        game = PlayedGame(
            game_id="g1",
            started_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            standings=[PlayedGameStanding(name="Alice", seat=0, user_id="u1")],
        )
        await repo.create_game(game)
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game(game_id="g1", ended_at=end_time, end_reason="abandoned")

        result = await repo.get_game("g1")
        assert result is not None
        assert result.end_reason == "abandoned"
        # Start-time standings preserved (not overwritten with empty list)
        assert len(result.standings) == 1
        assert result.standings[0].name == "Alice"
        assert result.standings[0].score is None  # no scores for abandoned games

    async def test_game_repository__when_finishing_unknown_game__should_warn_without_creating_it(
        self, repo: SqliteGameRepository, caplog: pytest.LogCaptureFixture
    ):
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        with caplog.at_level(logging.WARNING):
            await repo.finish_game(game_id="nonexistent", ended_at=end_time)

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert [r.msg["event"] for r in warning_records] == ["finish_game had no effect (not found or already ended)"]
        assert await repo.get_game("nonexistent") is None


class TestGetRecentGames:
    async def test_game_repository_recent_games__when_no_games__should_return_empty(self, repo: SqliteGameRepository):
        result = await repo.get_recent_games()
        assert result == []

    async def test_game_repository_recent_games__when_several_games__should_order_by_started_at_desc(
        self, repo: SqliteGameRepository
    ):
        await repo.create_game(_game("g1", datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)))
        await repo.create_game(_game("g2", datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)))
        await repo.create_game(_game("g3", datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)))

        result = await repo.get_recent_games()
        assert [g.game_id for g in result] == ["g2", "g3", "g1"]

    async def test_game_repository_recent_games__when_limit_given__should_cap_results(self, repo: SqliteGameRepository):
        for i in range(5):
            await repo.create_game(_game(f"g{i}", datetime(2025, 1, 15, i, 0, 0, tzinfo=UTC)))

        result = await repo.get_recent_games(limit=3)
        assert len(result) == 3
        assert result[0].game_id == "g4"
