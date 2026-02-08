import pytest

from game.logic.events import EventType
from game.session.models import Game
from game.tests.mocks import MockConnection


class TestSessionManagerNumBots:
    """Tests for unified num_bots game creation in SessionManager."""

    async def test_num_bots_0_does_not_start_on_first_join(self, manager):
        """Game with num_bots=0 does NOT auto-start when first player joins."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1", num_bots=0)

        await manager.join_game(conn, "game1", "Alice")

        game_started_events = [m for m in conn.sent_messages if m.get("type") == EventType.GAME_STARTED]
        assert len(game_started_events) == 0

    async def test_num_bots_0_does_not_start_on_third_join(self, manager):
        """Game with num_bots=0 does NOT auto-start when 3rd player joins."""
        conns = [MockConnection() for _ in range(3)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == EventType.GAME_STARTED]
            assert len(game_started_events) == 0

    async def test_num_bots_0_starts_on_fourth_join(self, manager):
        """Game with num_bots=0 auto-starts when 4th player joins."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == EventType.GAME_STARTED]
            assert len(game_started_events) == 1

    async def test_num_bots_0_all_players_assigned_seats(self, manager):
        """All 4 human players are assigned seats after game starts."""
        conns = [MockConnection() for _ in range(4)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=0)

        for i, c in enumerate(conns):
            await manager.join_game(c, "game1", f"Player{i}")

        game = manager.get_game("game1")
        for player in game.players.values():
            assert player.seat is not None

    async def test_num_bots_3_starts_on_first_join(self, manager):
        """Game with num_bots=3 (default) auto-starts on first join."""
        conn = MockConnection()
        manager.register_connection(conn)
        manager.create_game("game1")

        await manager.join_game(conn, "game1", "Alice")

        game_started_events = [m for m in conn.sent_messages if m.get("type") == EventType.GAME_STARTED]
        assert len(game_started_events) == 1

    async def test_num_bots_2_starts_on_second_join(self, manager):
        """Game with num_bots=2 auto-starts when 2nd human joins."""
        conns = [MockConnection() for _ in range(2)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=2)

        await manager.join_game(conns[0], "game1", "Alice")
        game_started_events = [m for m in conns[0].sent_messages if m.get("type") == EventType.GAME_STARTED]
        assert len(game_started_events) == 0

        await manager.join_game(conns[1], "game1", "Bob")
        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == EventType.GAME_STARTED]
            assert len(game_started_events) == 1

    async def test_num_bots_1_starts_on_third_join(self, manager):
        """Game with num_bots=1 auto-starts when 3rd human joins."""
        conns = [MockConnection() for _ in range(3)]
        for c in conns:
            manager.register_connection(c)
        manager.create_game("game1", num_bots=1)

        await manager.join_game(conns[0], "game1", "Alice")
        await manager.join_game(conns[1], "game1", "Bob")

        for c in conns[:2]:
            game_started_events = [m for m in c.sent_messages if m.get("type") == EventType.GAME_STARTED]
            assert len(game_started_events) == 0

        await manager.join_game(conns[2], "game1", "Charlie")
        for c in conns:
            game_started_events = [m for m in c.sent_messages if m.get("type") == EventType.GAME_STARTED]
            assert len(game_started_events) == 1

    async def test_create_game_invalid_num_bots(self):
        """Game rejects num_bots outside 0-3 range."""
        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=5)

        with pytest.raises(ValueError, match="num_bots must be 0-3"):
            Game(game_id="game1", num_bots=-1)

    async def test_get_games_info_includes_num_bots(self, manager):
        """get_games_info includes num_bots field for each game."""
        manager.create_game("game1", num_bots=3)
        manager.create_game("game2", num_bots=0)

        infos = manager.get_games_info()
        info_map = {info.game_id: info for info in infos}

        assert info_map["game1"].num_bots == 3
        assert info_map["game2"].num_bots == 0
