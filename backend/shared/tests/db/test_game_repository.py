"""Tests for SqliteGameRepository."""

from __future__ import annotations

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
    async def test_create_and_get_game(self, repo: SqliteGameRepository) -> None:
        game = _game()
        await repo.create_game(game)

        result = await repo.get_game("g1")
        assert result is not None
        assert result.game_id == "g1"
        assert result.ended_at is None
        assert result.end_reason is None

    async def test_get_returns_none_for_unknown(self, repo: SqliteGameRepository) -> None:
        assert await repo.get_game("nonexistent") is None

    async def test_duplicate_create_is_safe(self, repo: SqliteGameRepository) -> None:
        game = _game()
        await repo.create_game(game)
        # Second create should not raise, just log a warning
        await repo.create_game(game)

        result = await repo.get_game("g1")
        assert result is not None


class TestFinishGame:
    async def test_finish_completed_game(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(_game())
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("g1", ended_at=end_time, end_reason="completed")

        result = await repo.get_game("g1")
        assert result is not None
        assert result.ended_at == end_time
        assert result.end_reason == "completed"

    async def test_finish_does_not_overwrite_already_ended(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(_game())
        first_end = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("g1", ended_at=first_end, end_reason="completed")

        second_end = datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC)
        await repo.finish_game("g1", ended_at=second_end, end_reason="abandoned")

        # Original end state is preserved
        result = await repo.get_game("g1")
        assert result is not None
        assert result.ended_at == first_end
        assert result.end_reason == "completed"

    async def test_finish_with_standings_persists_scores(self, repo: SqliteGameRepository) -> None:
        standings = [
            PlayedGameStanding(name="Alice", seat=0, user_id="u1", score=35000, final_score=30),
            PlayedGameStanding(name="Bob", seat=1, user_id="u2", score=25000, final_score=0),
        ]
        await repo.create_game(_game())
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("g1", ended_at=end_time, num_rounds_played=8, standings=standings)

        result = await repo.get_game("g1")
        assert result is not None
        assert result.num_rounds_played == 8
        assert len(result.standings) == 2
        assert result.standings[0].name == "Alice"
        assert result.standings[0].final_score == 30
        assert result.standings[1].name == "Bob"

    async def test_finish_abandoned_preserves_start_standings(self, repo: SqliteGameRepository) -> None:
        """Abandoned games (standings=None) keep the start-time player data."""
        game = PlayedGame(
            game_id="g1",
            started_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
            standings=[PlayedGameStanding(name="Alice", seat=0, user_id="u1")],
        )
        await repo.create_game(game)
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("g1", ended_at=end_time, end_reason="abandoned")

        result = await repo.get_game("g1")
        assert result is not None
        assert result.end_reason == "abandoned"
        # Start-time standings preserved (not overwritten with empty list)
        assert len(result.standings) == 1
        assert result.standings[0].name == "Alice"
        assert result.standings[0].score is None  # no scores for abandoned games

    async def test_finish_nonexistent_game_is_noop(self, repo: SqliteGameRepository) -> None:
        # Should log a warning but not raise
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("nonexistent", ended_at=end_time)


class TestGetRecentGames:
    async def test_empty_returns_empty_list(self, repo: SqliteGameRepository) -> None:
        result = await repo.get_recent_games()
        assert result == []

    async def test_returns_games_ordered_by_started_at_desc(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(_game("g1", datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)))
        await repo.create_game(_game("g2", datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)))
        await repo.create_game(_game("g3", datetime(2025, 1, 15, 11, 0, 0, tzinfo=UTC)))

        result = await repo.get_recent_games()
        assert [g.game_id for g in result] == ["g2", "g3", "g1"]

    async def test_respects_limit(self, repo: SqliteGameRepository) -> None:
        for i in range(5):
            await repo.create_game(_game(f"g{i}", datetime(2025, 1, 15, i, 0, 0, tzinfo=UTC)))

        result = await repo.get_recent_games(limit=3)
        assert len(result) == 3
        assert result[0].game_id == "g4"
