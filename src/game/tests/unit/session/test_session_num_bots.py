import pytest

from game.session.models import Game

from .helpers import create_started_game


class TestSessionManagerNumBots:
    """Tests for unified num_bots game creation via room flow in SessionManager."""

    async def test_num_bots_3_starts_game(self, manager):
        """Room with num_bots=3 starts a game when the single human readies up."""
        await create_started_game(manager, "game1", num_bots=3, player_names=["Alice"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_bots_2_starts_game(self, manager):
        """Room with num_bots=2 starts a game when both humans ready up."""
        await create_started_game(manager, "game1", num_bots=2, player_names=["Alice", "Bob"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_bots_0_starts_game(self, manager):
        """Room with num_bots=0 starts a game when all 4 humans ready up."""
        await create_started_game(manager, "game1", num_bots=0, player_names=["P0", "P1", "P2", "P3"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_num_bots_0_all_players_assigned_seats(self, manager):
        """All 4 human players are assigned seats after game starts."""
        await create_started_game(manager, "game1", num_bots=0, player_names=["P0", "P1", "P2", "P3"])

        game = manager.get_game("game1")
        for player in game.players.values():
            assert player.seat is not None

    async def test_num_bots_1_starts_game(self, manager):
        """Room with num_bots=1 starts a game when all 3 humans ready up."""
        await create_started_game(manager, "game1", num_bots=1, player_names=["Alice", "Bob", "Charlie"])

        game = manager.get_game("game1")
        assert game is not None
        assert game.started is True

    async def test_create_game_invalid_num_bots(self):
        """Game rejects num_bots outside 0-3 range."""
        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=5)

        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=-1)
