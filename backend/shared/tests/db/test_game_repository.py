"""Tests for SqliteGameRepository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from shared.dal.models import PlayedGame
from shared.db.connection import Database
from shared.db.game_repository import SqliteGameRepository

if TYPE_CHECKING:
    from pathlib import Path


def _game(
    game_id: str = "g1",
    player_ids: list[str] | None = None,
    started_at: datetime | None = None,
) -> PlayedGame:
    return PlayedGame(
        game_id=game_id,
        started_at=started_at or datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
        player_ids=player_ids or ["p1", "p2", "p3", "p4"],
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
        assert result.player_ids == ["p1", "p2", "p3", "p4"]
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

    async def test_finish_nonexistent_game_is_noop(self, repo: SqliteGameRepository) -> None:
        # Should log a warning but not raise
        end_time = datetime(2025, 1, 15, 13, 0, 0, tzinfo=UTC)
        await repo.finish_game("nonexistent", ended_at=end_time)


class TestGetByPlayer:
    async def test_returns_games_for_player(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(_game("g1", player_ids=["p1", "p2"]))
        await repo.create_game(_game("g2", player_ids=["p1", "p3"]))
        await repo.create_game(_game("g3", player_ids=["p2", "p3"]))

        games = await repo.get_games_by_player("p1")
        game_ids = [g.game_id for g in games]
        assert set(game_ids) == {"g1", "g2"}

    async def test_returns_empty_for_unknown_player(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(_game())
        assert await repo.get_games_by_player("unknown") == []

    async def test_ordered_by_started_at_descending(self, repo: SqliteGameRepository) -> None:
        await repo.create_game(
            _game(
                "g_old",
                player_ids=["p1"],
                started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ),
        )
        await repo.create_game(
            _game(
                "g_new",
                player_ids=["p1"],
                started_at=datetime(2025, 6, 1, tzinfo=UTC),
            ),
        )
        await repo.create_game(
            _game(
                "g_mid",
                player_ids=["p1"],
                started_at=datetime(2025, 3, 1, tzinfo=UTC),
            ),
        )

        games = await repo.get_games_by_player("p1")
        assert [g.game_id for g in games] == ["g_new", "g_mid", "g_old"]
