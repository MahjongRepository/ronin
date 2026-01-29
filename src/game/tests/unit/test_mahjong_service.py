"""
Unit tests for MahjongGameService.
"""

import pytest

from game.logic.enums import TimeoutType
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import MahjongPlayer, MahjongRoundState, RoundPhase
from game.messaging.events import ErrorEvent


def _find_human_player(round_state: MahjongRoundState, name: str) -> MahjongPlayer:
    """Find the human player by name."""
    for player in round_state.players:
        if player.name == name:
            return player
    raise ValueError(f"player {name} not found")


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
        assert human_player.is_bot is False

    async def test_start_game_fills_with_bots(self, service):
        await service.start_game("game1", ["Human"])

        game_state = service._games["game1"]
        bot_count = sum(1 for p in game_state.round_state.players if p.is_bot)
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


class TestMahjongGameServiceDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_discard_validates_player_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        # try to discard when it's not human's turn
        if game_state.round_state.current_player_seat != human.seat:
            events = await service.handle_action("game1", "Human", "discard", {"tile_id": 0})
            assert any(e.event == "error" for e in events)

    async def test_discard_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "discard", {})

        assert any(e.event == "error" for e in events)

    async def test_discard_validates_tile_in_hand(self, service):
        await service.start_game("game1", ["Human"])

        # use a tile that's definitely not in any hand
        invalid_tile = 999

        events = await service.handle_action("game1", "Human", "discard", {"tile_id": invalid_tile})

        assert any(e.event == "error" for e in events)

    async def test_discard_creates_discard_event(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]  # discard last tile

        events = await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        discard_events = [e for e in events if e.event == "discard"]
        assert len(discard_events) >= 1

    async def test_discard_removes_tile_from_hand(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]
        initial_count = human.tiles.count(tile_id)

        await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        # tile count should decrease
        assert human.tiles.count(tile_id) == initial_count - 1


class TestMahjongGameServiceRiichi:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_riichi_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "declare_riichi", {})

        assert any(e.event == "error" for e in events)


class TestMahjongGameServiceTsumo:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_tsumo_validates_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        # try to call tsumo when it's not human's turn
        if game_state.round_state.current_player_seat != human.seat:
            events = await service.handle_action("game1", "Human", "declare_tsumo", {})
            assert any(e.event == "error" for e in events)


class TestMahjongGameServiceRon:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_ron_requires_tile_id_and_from_seat(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_ron", {})

        assert any(e.event == "error" for e in events)


class TestMahjongGameServiceMelds:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_pon_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_pon", {})

        assert any(e.event == "error" for e in events)

    async def test_chi_requires_tile_id_and_sequence(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_chi", {})

        assert any(e.event == "error" for e in events)

    async def test_kan_requires_tile_id(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "call_kan", {})

        assert any(e.event == "error" for e in events)


class TestMahjongGameServicePass:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_pass_returns_acknowledgement(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "pass", {})

        assert any(e.event == "pass_acknowledged" for e in events)


class TestMahjongGameServiceErrors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_action_game_not_found(self, service):
        events = await service.handle_action("nonexistent", "Human", "discard", {"tile_id": 0})

        assert any(e.event == "error" for e in events)
        error_event = next(e for e in events if e.event == "error")
        assert isinstance(error_event.data, ErrorEvent)
        assert "not found" in error_event.data.message

    async def test_handle_action_player_not_in_game(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Unknown", "discard", {"tile_id": 0})

        assert any(e.event == "error" for e in events)
        error_event = next(e for e in events if e.event == "error")
        assert isinstance(error_event.data, ErrorEvent)
        assert "not in game" in error_event.data.message

    async def test_handle_action_unknown_action(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_action("game1", "Human", "unknown_action", {})

        assert any(e.event == "error" for e in events)
        error_event = next(e for e in events if e.event == "error")
        assert isinstance(error_event.data, ErrorEvent)
        assert "unknown action" in error_event.data.message


class TestMahjongGameServiceFindPlayerSeat:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_player_seat_returns_correct_seat(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat(game_state, "Human")

        # seat is assigned randomly, just verify it's valid
        assert seat is not None
        assert 0 <= seat <= 3

    async def test_find_player_seat_returns_none_for_unknown(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        seat = service._find_player_seat(game_state, "Unknown")

        assert seat is None

    async def test_find_player_seat_ignores_bot_with_same_name(self, service):
        await service.start_game("game1", ["Tsumogiri 1"])
        game_state = service._games["game1"]

        seat = service._find_player_seat(game_state, "Tsumogiri 1")

        # should find the human player, not the bot
        assert seat is not None
        player = game_state.round_state.players[seat]
        assert player.is_bot is False


class TestMahjongGameServiceBotTurns:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_bot_turns_process_automatically(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]

        # after human discards, bots should take turns until human's turn again
        events = await service.handle_action("game1", "Human", "discard", {"tile_id": tile_id})

        # should have multiple events from bot turns
        assert len(events) > 1

    async def test_bot_turns_stop_at_human_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]

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
        """
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # verify no bot has more than 1 more discard than any other bot
        bot_players = [p for p in round_state.players if p.is_bot]
        discard_counts = [len(p.discards) for p in bot_players]
        max_diff = max(discard_counts) - min(discard_counts)
        assert max_diff <= 1, f"bot discard counts uneven: {discard_counts}"

    async def test_bot_tile_counts_valid_after_call_prompt(self, service):
        """
        Verify bots have valid tile counts when waiting for human call response.
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


class TestMahjongGameServiceHandleTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_turn_timeout_discards_last_tile(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # only works when it's actually the human's turn
        if game_state.round_state.current_player_seat == human.seat:
            events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)
            assert len(events) > 0
            # tsumogiri produces a discard event (bot turns may follow)
            assert any(e.event == "discard" for e in events)

    async def test_turn_timeout_returns_empty_when_not_players_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        if game_state.round_state.current_player_seat != human.seat:
            events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)
            assert events == []

    async def test_meld_timeout_sends_pass(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_timeout("game1", "Human", TimeoutType.MELD)

        assert any(e.event == "pass_acknowledged" for e in events)

    async def test_timeout_nonexistent_game_returns_empty(self, service):
        events = await service.handle_timeout("nonexistent", "Human", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_player_returns_empty(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_timeout("game1", "Unknown", TimeoutType.TURN)

        assert events == []

    async def test_get_player_seat_returns_seat(self, service):
        await service.start_game("game1", ["Human"])

        seat = service.get_player_seat("game1", "Human")

        assert seat is not None
        assert 0 <= seat <= 3

    async def test_get_player_seat_nonexistent_game(self, service):
        seat = service.get_player_seat("nonexistent", "Human")

        assert seat is None
