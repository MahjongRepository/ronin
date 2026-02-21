"""Tests for DAL persistence models."""

from datetime import UTC, datetime

from shared.dal.models import PlayedGame


class TestPlayedGame:
    def test_serialization_roundtrip(self):
        game = PlayedGame(
            game_id="g1",
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            ended_at=datetime(2025, 1, 1, 1, 0, tzinfo=UTC),
            end_reason="abandoned",
            player_ids=["p1", "p2"],
        )
        restored = PlayedGame.model_validate_json(game.model_dump_json())
        assert restored == game
