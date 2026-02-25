import pytest

from game.session.models import Game


class TestSessionManagerNumAIPlayers:
    """Tests for num_ai_players validation in Game model."""

    async def test_create_game_invalid_num_ai_players(self):
        """Game rejects num_ai_players outside 0-3 range."""
        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=5)

        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=-1)
