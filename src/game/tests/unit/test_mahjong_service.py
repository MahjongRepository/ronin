"""
Unit tests for MahjongGameService.
"""

import pytest

from game.logic.mahjong_service import MahjongGameService
from game.logic.state import RoundPhase


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

    async def test_start_game_first_player_is_human(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        assert game_state.round_state.players[0].name == "Human"
        assert game_state.round_state.players[0].is_bot is False

    async def test_start_game_fills_with_bots(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        for i in range(1, 4):
            assert game_state.round_state.players[i].is_bot is True

    async def test_start_game_returns_game_started_events(self, service):
        events = await service.start_game("game1", ["Human"])

        # should have game_started events for each player
        game_started_events = [e for e in events if e.get("event") == "game_started"]
        assert len(game_started_events) == 4

    async def test_start_game_events_target_correct_seats(self, service):
        events = await service.start_game("game1", ["Human"])

        game_started_events = [e for e in events if e.get("event") == "game_started"]
        targets = {e["target"] for e in game_started_events}
        assert targets == {"seat_0", "seat_1", "seat_2", "seat_3"}

    async def test_start_game_includes_draw_event_for_dealer(self, service):
        events = await service.start_game("game1", ["Human"])

        draw_events = [e for e in events if e.get("event") == "draw"]
        assert len(draw_events) >= 1

    async def test_start_game_includes_turn_event_for_dealer(self, service):
        events = await service.start_game("game1", ["Human"])

        turn_events = [e for e in events if e.get("event") == "turn"]
        assert len(turn_events) >= 1

    async def test_start_game_creates_bot_controllers(self, service):
        await service.start_game("game1", ["Human"])

        assert "game1" in service._bots
        assert len(service._bots["game1"]) == 3

    async def test_start_game_players_have_13_tiles(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        for player in game_state.round_state.players:
            # dealer has 14 (drew first tile)
            if player.seat == game_state.round_state.dealer_seat:
                assert len(player.tiles) == 14
            else:
                assert len(player.tiles) == 13


class TestMahjongGameServiceDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_discard_validates_player_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # try to discard as wrong player (if dealer is seat 0, seat 1 can't discard)
        if game_state.round_state.dealer_seat == 0:
            events = await service.handle_action("game1", "Bot1", "discard", {"tile_id": 0})
            assert any(e.get("event") == "error" for e in events)

    async def test_discard_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "discard", {})

        assert any(e.get("event") == "error" for e in events)

    async def test_discard_validates_tile_in_hand(self, service):
        await service.start_game("game1", ["Human"])

        # use a tile that's definitely not in any hand
        invalid_tile = 999

        events = await service.handle_action("game1", "Human", "discard", {"tile_id": invalid_tile})

        assert any(e.get("event") == "error" for e in events)

    async def test_discard_creates_discard_event(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        player = game_state.round_state.players[0]
        tile_id = player.tiles[-1]  # discard last tile

        events = await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        discard_events = [e for e in events if e.get("event") == "discard"]
        assert len(discard_events) >= 1

    async def test_discard_removes_tile_from_hand(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        player = game_state.round_state.players[0]
        tile_id = player.tiles[-1]
        initial_count = player.tiles.count(tile_id)

        await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        # tile count should decrease
        assert player.tiles.count(tile_id) == initial_count - 1


class TestMahjongGameServiceRiichi:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_riichi_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "declare_riichi", {})

        assert any(e.get("event") == "error" for e in events)


class TestMahjongGameServiceTsumo:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_tsumo_validates_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # make sure it's not seat 1's turn
        if game_state.round_state.current_player_seat != 1:
            events = await service.handle_action("game1", "Bot1", "declare_tsumo", {})
            assert any(e.get("event") == "error" for e in events)


class TestMahjongGameServiceRon:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_ron_requires_tile_id_and_from_seat(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_ron", {})

        assert any(e.get("event") == "error" for e in events)


class TestMahjongGameServiceMelds:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_pon_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_pon", {})

        assert any(e.get("event") == "error" for e in events)

    async def test_chi_requires_tile_id_and_sequence(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_chi", {})

        assert any(e.get("event") == "error" for e in events)

    async def test_kan_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_kan", {})

        assert any(e.get("event") == "error" for e in events)


class TestMahjongGameServicePass:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_pass_returns_acknowledgement(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "pass", {})

        assert any(e.get("event") == "pass_acknowledged" for e in events)


class TestMahjongGameServiceErrors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_action_game_not_found(self, service):
        events = await service.handle_action("nonexistent", "Human", "discard", {"tile_id": 0})

        assert any(e.get("event") == "error" for e in events)
        error_event = next(e for e in events if e.get("event") == "error")
        assert "not found" in error_event["data"]["message"]

    async def test_handle_action_player_not_in_game(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Unknown", "discard", {"tile_id": 0})

        assert any(e.get("event") == "error" for e in events)
        error_event = next(e for e in events if e.get("event") == "error")
        assert "not in game" in error_event["data"]["message"]

    async def test_handle_action_unknown_action(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "unknown_action", {})

        assert any(e.get("event") == "error" for e in events)
        error_event = next(e for e in events if e.get("event") == "error")
        assert "unknown action" in error_event["data"]["message"]


class TestMahjongGameServiceFindPlayerSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_player_seat_returns_correct_seat(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat(game_state, "Human")

        assert seat == 0

    async def test_find_player_seat_returns_none_for_unknown(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat(game_state, "Unknown")

        assert seat is None


class TestMahjongGameServiceBotTurns:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_bot_turns_process_automatically(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        player = game_state.round_state.players[0]
        tile_id = player.tiles[-1]

        # after human discards, bots should take turns until human's turn again
        events = await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        # should have multiple events from bot turns
        assert len(events) > 1

    async def test_bot_turns_stop_at_human_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        player = game_state.round_state.players[0]
        tile_id = player.tiles[-1]

        await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        # after bot turns complete, should be human's turn again (unless round ended)
        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING:
            # if round is still playing, check we're back to human or waiting for call
            current_seat = round_state.current_player_seat
            current_player = round_state.players[current_seat]
            # either human's turn or there's a pending call prompt
            assert current_player.is_bot is False or round_state.phase != RoundPhase.PLAYING


class TestMahjongGameServiceBotTurnsCallPrompt:
    """Tests for bot turn handling when call prompts are pending for human players."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_bots_stop_when_human_can_call(self, service):
        """
        Verify bots don't take extra turns when a human can respond to a call prompt.

        Scenario: Bot3 discards, human can call pon. Bots should stop and wait
        for the human's response rather than Bot3 taking another turn.
        """
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # after game start, each bot should have at most 1 discard per full rotation
        # no bot should have 2+ discards before human acts (except after human passes)
        # verify no bot has more than 1 more discard than any other bot
        discard_counts = [len(round_state.players[seat].discards) for seat in range(1, 4)]
        max_diff = max(discard_counts) - min(discard_counts)
        assert max_diff <= 1, f"bot discard counts uneven: {discard_counts}"

    async def test_bot_tile_counts_valid_after_call_prompt(self, service):
        """
        Verify bots have valid tile counts when waiting for human call response.

        If a bot discards twice, they'd have 12 tiles which is invalid.
        """
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # all players should have valid tile counts: 13 (just discarded) or 14 (has drawn)
        for player in round_state.players:
            tile_count = len(player.tiles)
            assert tile_count in (13, 14), (
                f"player {player.seat} ({player.name}) has {tile_count} tiles, expected 13 or 14"
            )


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

        assert game1.round_state.players[0].name == "Alice"
        assert game2.round_state.players[0].name == "Bob"

    async def test_actions_affect_correct_game(self, service):
        await service.start_game("game1", ["Alice"])
        await service.start_game("game2", ["Bob"])

        game1 = service._games["game1"]
        player1 = game1.round_state.players[0]
        tile_id = player1.tiles[-1]

        await service.handle_action("game1", "Alice", "discard", {"tile_id": tile_id})

        # game2 should be unaffected
        game2 = service._games["game2"]
        player2 = game2.round_state.players[0]
        # player2 should still have 14 tiles (dealer hasn't discarded)
        assert len(player2.tiles) == 14
