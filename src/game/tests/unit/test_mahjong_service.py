"""
Unit tests for MahjongGameService initialization and lifecycle.
"""

import pytest

from game.logic.mahjong_service import MahjongGameService
from game.tests.unit.helpers import _find_human_player


class TestMahjongGameServiceInit:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_start_game_initializes_game_state(self, service):
        await service.start_game("game1", ["Human"])

        assert "game1" in service._games
        game_state = service._games["game1"]
        assert game_state is not None

    async def test_start_game_creates_four_players(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        assert len(game_state.round_state.players) == 4

    async def test_start_game_has_one_human(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        human_player = _find_human_player(game_state.round_state, "Human")
        assert human_player.name == "Human"

    async def test_start_game_fills_with_bots(self, service):
        await service.start_game("game1", ["Human"])

        bot_controller = service._bot_controllers["game1"]
        bot_count = sum(1 for seat in range(4) if bot_controller.is_bot(seat))
        assert bot_count == 3

    async def test_start_game_returns_game_started_events(self, service):
        events = await service.start_game("game1", ["Human"])

        # should have game_started events for each player
        game_started_events = [e for e in events if e.event == "game_started"]
        assert len(game_started_events) == 4

    async def test_start_game_events_target_correct_seats(self, service):
        events = await service.start_game("game1", ["Human"])

        game_started_events = [e for e in events if e.event == "game_started"]
        targets = {e.target for e in game_started_events}
        assert targets == {"seat_0", "seat_1", "seat_2", "seat_3"}

    async def test_start_game_includes_draw_event_for_dealer(self, service):
        events = await service.start_game("game1", ["Human"])

        draw_events = [e for e in events if e.event == "draw"]
        assert len(draw_events) >= 1

    async def test_start_game_includes_turn_event_for_dealer(self, service):
        events = await service.start_game("game1", ["Human"])

        turn_events = [e for e in events if e.event == "turn"]
        assert len(turn_events) >= 1

    async def test_start_game_creates_bot_controllers(self, service):
        await service.start_game("game1", ["Human"])

        assert "game1" in service._bot_controllers
        # bot controller has 3 bots mapped by seat
        assert len(service._bot_controllers["game1"]._bots) == 3

    async def test_start_game_players_have_valid_tile_counts(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        for player in game_state.round_state.players:
            # after start_game, bot turns may have been processed
            # valid tile counts: 13 (waiting/just discarded) or 14 (has drawn)
            assert len(player.tiles) in (13, 14), (
                f"player {player.seat} ({player.name}) has {len(player.tiles)} tiles"
            )


class TestMahjongGameServiceFindPlayerSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_player_seat_returns_correct_seat(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat("game1", game_state, "Human")

        # seat is assigned randomly, just verify it's valid
        assert seat is not None
        assert 0 <= seat <= 3

    async def test_find_player_seat_returns_none_for_unknown(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat("game1", game_state, "Unknown")

        assert seat is None

    async def test_find_player_seat_skips_bot_seats(self, service):
        """Searching for a bot name returns None because bot seats are skipped."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        bot_controller = service._bot_controllers["game1"]

        # find a bot's name to search for
        bot_name = None
        for player in game_state.round_state.players:
            if bot_controller.is_bot(player.seat):
                bot_name = player.name
                break

        seat = service._find_player_seat("game1", game_state, bot_name)

        assert seat is None

    async def test_find_player_seat_ignores_bot_with_same_name(self, service):
        await service.start_game("game1", ["Tsumogiri 1"])
        game_state = service._games["game1"]

        seat = service._find_player_seat("game1", game_state, "Tsumogiri 1")

        # should find the human player, not the bot
        assert seat is not None
        bot_controller = service._bot_controllers["game1"]
        assert bot_controller.is_bot(seat) is False


class TestMahjongGameServiceMultipleGames:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_multiple_games_independent(self, service):
        await service.start_game("game1", ["Alice"])
        await service.start_game("game2", ["Bob"])

        assert "game1" in service._games
        assert "game2" in service._games

        game1 = service._games["game1"]
        game2 = service._games["game2"]

        # find players by name instead of assuming seat 0
        alice = _find_human_player(game1.round_state, "Alice")
        bob = _find_human_player(game2.round_state, "Bob")

        assert alice.name == "Alice"
        assert bob.name == "Bob"

    async def test_actions_affect_correct_game(self, service):
        await service.start_game("game1", ["Alice"])
        await service.start_game("game2", ["Bob"])

        game1 = service._games["game1"]
        alice = _find_human_player(game1.round_state, "Alice")
        tile_id = alice.tiles[-1]

        # record bob's tile count before alice acts
        game2 = service._games["game2"]
        bob = _find_human_player(game2.round_state, "Bob")
        bob_tiles_before = len(bob.tiles)

        await service.handle_action("game1", "Alice", "discard", {"tile_id": tile_id})

        # game2 should be unaffected - bob's tile count should be unchanged
        assert len(bob.tiles) == bob_tiles_before


class TestMahjongGameServiceCleanup:
    """Tests for _cleanup_game method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_game_removes_game_state(self, service):
        """Verify _cleanup_game removes game and bot controller state."""
        await service.start_game("game1", ["Human"])

        assert "game1" in service._games
        assert "game1" in service._bot_controllers

        service._cleanup_game("game1")

        assert "game1" not in service._games
        assert "game1" not in service._bot_controllers

    async def test_cleanup_game_nonexistent_is_safe(self, service):
        """Verify _cleanup_game is safe to call with nonexistent game_id."""
        service._cleanup_game("nonexistent")

        assert "nonexistent" not in service._games
