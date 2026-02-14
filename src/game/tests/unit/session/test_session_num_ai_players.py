import pytest

from game.session.models import Game

from .helpers import create_started_game


class TestSessionManagerNumAIPlayers:
    """Tests for unified num_ai_players game creation via room flow in SessionManager."""

    async def test_num_ai_players_3_starts_game(self, manager):
        """Room with num_ai_players=3 starts a game when the single player readies up."""
        await create_started_game(manager, "game1", num_ai_players=3, player_names=["Alice"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_ai_players_2_starts_game(self, manager):
        """Room with num_ai_players=2 starts a game when both players ready up."""
        await create_started_game(manager, "game1", num_ai_players=2, player_names=["Alice", "Bob"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_ai_players_0_starts_game(self, manager):
        """Room with num_ai_players=0 starts a game when all 4 players ready up."""
        await create_started_game(manager, "game1", num_ai_players=0, player_names=["P0", "P1", "P2", "P3"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_ai_players_0_all_players_assigned_seats(self, manager):
        """All 4 players are assigned seats after game starts."""
        await create_started_game(manager, "game1", num_ai_players=0, player_names=["P0", "P1", "P2", "P3"])

        game = manager.get_game("game1")
        for player in game.players.values():
            assert player.seat is not None

    async def test_num_ai_players_1_starts_game(self, manager):
        """Room with num_ai_players=1 starts a game when all 3 players ready up."""
        await create_started_game(
            manager,
            "game1",
            num_ai_players=1,
            player_names=["Alice", "Bob", "Charlie"],
        )

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_create_game_invalid_num_ai_players(self):
        """Game rejects num_ai_players outside 0-3 range."""
        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=5)

        with pytest.raises(ValueError, match="num_ai_players must be 0-3"):
            Game(game_id="game1", num_ai_players=-1)
