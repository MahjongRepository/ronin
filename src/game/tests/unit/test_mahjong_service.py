"""
Unit tests for MahjongGameService initialization and lifecycle.
"""

import pytest

from game.logic.enums import CallType
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt, RoundPhase
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

    async def test_start_game_returns_game_started_event(self, service):
        events = await service.start_game("game1", ["Human"])

        # single game_started event broadcast to all
        game_started_events = [e for e in events if e.event == "game_started"]
        assert len(game_started_events) == 1
        assert game_started_events[0].target == "all"
        assert game_started_events[0].data.game_id == "game1"
        assert len(game_started_events[0].data.players) == 4

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
    """Tests for cleanup_game method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_cleanup_game_removes_game_state(self, service):
        """Verify cleanup_game removes game and bot controller state."""
        await service.start_game("game1", ["Human"])

        assert "game1" in service._games
        assert "game1" in service._bot_controllers

        service.cleanup_game("game1")

        assert "game1" not in service._games
        assert "game1" not in service._bot_controllers

    async def test_cleanup_game_nonexistent_is_safe(self, service):
        """Verify cleanup_game is safe to call with nonexistent game_id."""
        service.cleanup_game("nonexistent")

        assert "nonexistent" not in service._games


class TestMahjongGameServiceAllHumans:
    """Tests for start_game with 4 human players (PVP mode, no bots)."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_four_humans_zero_bots_in_controller(self, service):
        """0 bots created in BotController when starting with 4 humans."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        bot_controller = service._bot_controllers["game1"]
        bot_count = sum(1 for seat in range(4) if bot_controller.is_bot(seat))
        assert bot_count == 0

    async def test_four_humans_all_marked_not_bot_in_game_started(self, service):
        """All 4 players marked as is_bot=False in game_started event."""
        events = await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        game_started_events = [e for e in events if e.event == "game_started"]
        assert len(game_started_events) == 1

        players = game_started_events[0].data.players
        assert len(players) == 4
        for player in players:
            assert player.is_bot is False

    async def test_four_humans_all_names_present(self, service):
        """All 4 human player names appear in the game_started event."""
        names = ["Alice", "Bob", "Charlie", "Dave"]
        events = await service.start_game("game1", names)

        game_started_events = [e for e in events if e.event == "game_started"]
        player_names = {p.name for p in game_started_events[0].data.players}
        assert player_names == set(names)

    async def test_four_humans_no_bot_followup_for_dealer(self, service):
        """Bot followup is not triggered when dealer is human (all humans)."""
        events = await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        # with 4 humans, exactly 1 turn event should be present for the dealer
        # (no bot followup chain that would generate additional events)
        turn_events = [e for e in events if e.event == "turn"]
        assert len(turn_events) == 1

    async def test_four_humans_creates_four_players(self, service):
        """start_game with 4 humans creates all 4 players."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        game_state = service._games["game1"]
        assert len(game_state.round_state.players) == 4

    async def test_four_humans_valid_tile_counts(self, service):
        """All 4 human players have valid tile counts after start."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        game_state = service._games["game1"]
        for player in game_state.round_state.players:
            # dealer has 14 tiles (just drew), others have 13
            assert len(player.tiles) in (13, 14), (
                f"player {player.seat} ({player.name}) has {len(player.tiles)} tiles"
            )


class TestMahjongGameServiceReplacePlayerWithBot:
    """Tests for replace_player_with_bot()."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_replace_registers_bot_in_controller(self, service):
        """Replacing a human player registers a bot at their seat."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        bot_controller = service._bot_controllers["game1"]
        human = _find_human_player(game_state.round_state, "Alice")
        human_seat = human.seat

        assert bot_controller.is_bot(human_seat) is False

        service.replace_player_with_bot("game1", "Alice")

        assert bot_controller.is_bot(human_seat) is True

    async def test_replace_nonexistent_game_is_safe(self, service):
        """Replacing a player in a nonexistent game does nothing."""
        service.replace_player_with_bot("nonexistent", "Alice")

    async def test_replace_nonexistent_player_is_safe(self, service):
        """Replacing a nonexistent player does nothing."""
        await service.start_game("game1", ["Alice"])

        service.replace_player_with_bot("game1", "Unknown")

        # no new bots added beyond the original 3
        bot_controller = service._bot_controllers["game1"]
        assert len(bot_controller._bots) == 3

    async def test_replace_finds_seat_before_registering_bot(self, service):
        """Seat lookup happens before bot registration (since _find_player_seat skips bot seats)."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Alice")
        human_seat = human.seat

        service.replace_player_with_bot("game1", "Alice")

        # the bot is now at the human's former seat
        bot_controller = service._bot_controllers["game1"]
        assert bot_controller.is_bot(human_seat) is True
        # all 4 seats are now bots
        assert len(bot_controller._bots) == 4

    async def test_replace_same_player_twice_is_safe(self, service):
        """Replacing an already-replaced player is a no-op (seat not found)."""
        await service.start_game("game1", ["Alice"])

        service.replace_player_with_bot("game1", "Alice")
        # second call: _find_player_seat skips bot seats, returns None
        service.replace_player_with_bot("game1", "Alice")

        bot_controller = service._bot_controllers["game1"]
        assert len(bot_controller._bots) == 4

    async def test_replace_without_bot_controller_is_safe(self, service):
        """Replacing a player when bot controller is missing does nothing."""
        await service.start_game("game1", ["Alice"])

        # remove bot controller to simulate edge case
        del service._bot_controllers["game1"]

        service.replace_player_with_bot("game1", "Alice")


class TestMahjongGameServiceProcessBotActionsAfterReplacement:
    """Tests for process_bot_actions_after_replacement()."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_nonexistent_game_returns_empty(self, service):
        """Processing bot actions for a nonexistent game returns empty list."""
        events = await service.process_bot_actions_after_replacement("nonexistent", seat=0)

        assert events == []

    async def test_non_playing_phase_returns_empty(self, service):
        """Processing bot actions when round is not PLAYING returns empty list."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]

        # force phase to FINISHED
        game_state.round_state.phase = RoundPhase.FINISHED

        events = await service.process_bot_actions_after_replacement("game1", seat=0)

        assert events == []

    async def test_processes_bot_turn_after_replacement(self, service):
        """After replacement, bot processes its pending turn if it's the current player."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        human = _find_human_player(round_state, "Alice")
        human_seat = human.seat

        # force the current player to be the human's seat
        round_state.current_player_seat = human_seat
        # ensure the human has 14 tiles (their turn to act)
        while len(human.tiles) < 14:
            if round_state.wall:
                human.tiles.append(round_state.wall.pop())
        # trim other players to 13 tiles
        for p in round_state.players:
            if p.seat != human_seat:
                while len(p.tiles) > 13:
                    p.tiles.pop()

        # clear any pending call prompt
        round_state.pending_call_prompt = None

        # replace the human with a bot
        service.replace_player_with_bot("game1", "Alice")

        # process bot actions
        events = await service.process_bot_actions_after_replacement("game1", human_seat)

        # bot should have generated events (at minimum a discard)
        assert len(events) > 0

    async def test_handles_pending_call_prompt(self, service):
        """After replacement, bot resolves its pending call prompt response."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_human_player(round_state, "Alice")

        # set up a pending call prompt where Alice is a pending caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 1) % 4,
            pending_seats={alice.seat},
            callers=[alice.seat],
        )

        # replace Alice with a bot
        service.replace_player_with_bot("game1", "Alice")

        # process bot actions after replacement
        await service.process_bot_actions_after_replacement("game1", alice.seat)

        # the bot should have resolved the call prompt (tsumogiri bot declines ron)
        # prompt should be cleared since Alice was the only pending caller
        assert round_state.pending_call_prompt is None

    async def test_pending_call_with_other_human_callers_returns_early(self, service):
        """When other human callers remain pending after bot dispatch, returns early."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_human_player(round_state, "Alice")
        bob = _find_human_player(round_state, "Bob")

        # set up a call prompt where both Alice and Bob are pending callers
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 2) % 4,  # different from both Alice and Bob
            pending_seats={alice.seat, bob.seat},
            callers=[alice.seat, bob.seat],
        )

        # replace Alice with a bot
        service.replace_player_with_bot("game1", "Alice")

        # process bot actions - bot resolves Alice's response, Bob still pending
        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

        # Bob is still a human caller pending response
        assert round_state.pending_call_prompt is not None
        assert bob.seat in round_state.pending_call_prompt.pending_seats
        assert alice.seat not in round_state.pending_call_prompt.pending_seats
        # events may contain bot's pass response events
        assert isinstance(events, list)

    async def test_round_end_after_call_prompt_resolution(self, service):
        """When round ends after call prompt resolution, returns round end events."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_human_player(round_state, "Alice")

        # empty the wall to force exhaustive draw after turn advance
        round_state.wall.clear()

        # set up a call prompt where Alice is the only pending caller
        discarder_seat = (alice.seat + 1) % 4
        tile_id = (
            round_state.players[discarder_seat].tiles[0] if round_state.players[discarder_seat].tiles else 0
        )
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=discarder_seat,
            pending_seats={alice.seat},
            callers=[alice.seat],
        )

        # replace Alice with a bot
        service.replace_player_with_bot("game1", "Alice")

        # process bot actions - bot passes, prompt resolves, turn advances,
        # exhaustive draw triggers because wall is empty
        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

        # should contain round_end event (round ended due to exhaustive draw)
        round_end_events = [e for e in events if e.event == "round_end"]
        assert len(round_end_events) >= 1
