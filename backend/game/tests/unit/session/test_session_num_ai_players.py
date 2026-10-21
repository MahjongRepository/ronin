import pytest

from game.session.models import Game


class TestSessionManagerNumAIPlayers:
    async def test_game__when_num_ai_players_out_of_range__should_raise_value_error(self):
        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=5)

        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=-1)
