"""Unit tests for MahjongGameService lifecycle and service-level edge cases."""

import pytest

from game.logic.enums import CallType, GameErrorCode, GamePhase, RoundPhase
from game.logic.events import (
    ErrorEvent,
    EventType,
    SeatTarget,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.settings import GameSettings
from game.logic.state import PendingCallPrompt
from game.logic.types import (
    ExhaustiveDrawResult,
    TenpaiHand,
)
from game.logic.wall import Wall
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceFindPlayerSeat:
    """Tests for _find_player_seat edge cases: AI player skipping, name collision."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_player_seat_returns_none_for_unknown(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        seat = service._find_player_seat("game1", "Unknown")

        assert seat is None

    async def test_find_player_seat_skips_ai_player_seats(self, service):
        """Searching for an AI player name returns None because AI player seats are skipped."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        ai_player_controller = service._ai_player_controllers["game1"]

        ai_player_name = None
        for player in game_state.round_state.players:
            if ai_player_controller.is_ai_player(player.seat):
                ai_player_name = player.name
                break

        seat = service._find_player_seat("game1", ai_player_name)

        assert seat is None


class TestMahjongGameServiceAllPlayers:
    """Tests for PVP mode (4 players, 0 AI players) edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_four_players_zero_ai_players_in_controller(self, service):
        """0 AI players created in AIPlayerController when starting with 4 players."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_count = sum(1 for seat in range(4) if ai_player_controller.is_ai_player(seat))
        assert ai_player_count == 0

    async def test_four_players_no_ai_player_followup_for_dealer(self, service):
        """AI player followup is not triggered when dealer is a player (all players)."""
        events = await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        # with 4 players, exactly 1 draw event for dealer (no AI player followup chain)
        draw_events = [e for e in events if e.event == EventType.DRAW]
        assert len(draw_events) == 1


class TestMahjongGameServiceReplaceWithAIPlayer:
    """Tests for replace_with_ai_player() disconnect handling."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_replace_registers_ai_player_in_controller(self, service):
        """Replacing a player registers an AI player at their seat."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        ai_player_controller = service._ai_player_controllers["game1"]
        player = _find_player(game_state.round_state, "Alice")
        player_seat = player.seat

        assert ai_player_controller.is_ai_player(player_seat) is False

        service.replace_with_ai_player("game1", "Alice")

        assert ai_player_controller.is_ai_player(player_seat) is True

    async def test_replace_nonexistent_game_is_safe(self, service):
        """Replacing a player in a nonexistent game does nothing."""
        service.replace_with_ai_player("nonexistent", "Alice")

    async def test_replace_nonexistent_player_is_safe(self, service):
        """Replacing a nonexistent player does nothing."""
        await service.start_game("game1", ["Alice"])

        service.replace_with_ai_player("game1", "Unknown")

        ai_player_controller = service._ai_player_controllers["game1"]
        assert len(ai_player_controller._ai_players) == 3

    async def test_replace_same_player_twice_is_safe(self, service):
        """Replacing an already-replaced player is a no-op (seat not found)."""
        await service.start_game("game1", ["Alice"])

        service.replace_with_ai_player("game1", "Alice")
        service.replace_with_ai_player("game1", "Alice")

        ai_player_controller = service._ai_player_controllers["game1"]
        assert len(ai_player_controller._ai_players) == 4


class TestMahjongGameServiceProcessAIPlayerActionsAfterReplacement:
    """Tests for process_ai_player_actions_after_replacement() complex flows."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_non_playing_phase_returns_empty(self, service):
        """Processing AI player actions when round is not PLAYING returns empty list."""
        await service.start_game("game1", ["Alice"])

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        events = await service.process_ai_player_actions_after_replacement("game1", seat=0)

        assert events == []

    async def test_processes_ai_player_turn_after_replacement(self, service):
        """After replacement, AI player processes its pending turn if it's the current player."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Alice")
        player_seat = player.seat

        player_tiles = list(player.tiles)
        live_tiles = list(round_state.wall.live_tiles)
        while len(player_tiles) < 14:
            if live_tiles:
                player_tiles.append(live_tiles.pop())

        new_players = []
        for p in round_state.players:
            if p.seat == player_seat:
                new_players.append(p.model_copy(update={"tiles": tuple(player_tiles)}))
            elif len(p.tiles) > 13:
                new_players.append(p.model_copy(update={"tiles": tuple(list(p.tiles)[:13])}))
            else:
                new_players.append(p)

        new_wall = round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)})
        _update_round_state(
            service,
            "game1",
            current_player_seat=player_seat,
            wall=new_wall,
            players=tuple(new_players),
            pending_call_prompt=None,
        )

        service.replace_with_ai_player("game1", "Alice")

        events = await service.process_ai_player_actions_after_replacement("game1", player_seat)

        assert len(events) > 0

    async def test_handles_pending_call_prompt(self, service):
        """After replacement, AI player resolves its pending call prompt response."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 1) % 4,
            pending_seats=frozenset({alice.seat}),
            callers=(alice.seat,),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        service.replace_with_ai_player("game1", "Alice")

        await service.process_ai_player_actions_after_replacement("game1", alice.seat)

        updated_round = service._games["game1"].round_state
        # Alice was the only pending caller, so after AI player resolves the prompt should be cleared.
        # AI player followup may create new MELD prompts, but Alice's seat must not remain pending.
        if updated_round.pending_call_prompt is not None:
            assert alice.seat not in updated_round.pending_call_prompt.pending_seats

    async def test_pending_call_with_other_player_callers_returns_early(self, service):
        """When other player callers remain pending after AI player dispatch, returns early."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")
        bob = _find_player(round_state, "Bob")

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 2) % 4,
            pending_seats=frozenset({alice.seat, bob.seat}),
            callers=(alice.seat, bob.seat),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        service.replace_with_ai_player("game1", "Alice")

        events = await service.process_ai_player_actions_after_replacement("game1", alice.seat)

        updated_round = service._games["game1"].round_state
        assert updated_round.pending_call_prompt is not None
        assert bob.seat in updated_round.pending_call_prompt.pending_seats
        assert alice.seat not in updated_round.pending_call_prompt.pending_seats
        assert isinstance(events, list)

    async def test_round_end_after_call_prompt_resolution(self, service):
        """When round ends after call prompt resolution, returns round end events."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_player(round_state, "Alice")

        discarder_seat = (alice.seat + 1) % 4
        tile_id = round_state.players[discarder_seat].tiles[0] if round_state.players[discarder_seat].tiles else 0
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=discarder_seat,
            pending_seats=frozenset({alice.seat}),
            callers=(alice.seat,),
        )

        _update_round_state(service, "game1", wall=Wall(), pending_call_prompt=prompt)

        service.replace_with_ai_player("game1", "Alice")

        events = await service.process_ai_player_actions_after_replacement("game1", alice.seat)

        round_end_events = [e for e in events if e.event == EventType.ROUND_END]
        assert len(round_end_events) >= 1


class TestSeedDeterminism:
    """Verify that start_game with same seed produces deterministic results."""

    async def test_same_seed_produces_deterministic_game(self):
        service1 = MahjongGameService()
        service2 = MahjongGameService()

        await service1.start_game("game1", ["Player"], seed="b" * 192)
        await service2.start_game("game2", ["Player"], seed="b" * 192)

        state1 = service1._games["game1"]
        state2 = service2._games["game2"]

        names1 = [p.name for p in state1.round_state.players]
        names2 = [p.name for p in state2.round_state.players]
        assert names1 == names2

        tiles1 = [p.tiles for p in state1.round_state.players]
        tiles2 = [p.tiles for p in state2.round_state.players]
        assert tiles1 == tiles2
        assert state1.round_state.wall == state2.round_state.wall


class TestAutoCleanup:
    """Tests for auto_cleanup flag controlling state preservation after game end."""

    async def test_auto_cleanup_false_preserves_state_after_game_end(self):
        """auto_cleanup=False preserves game state in self._games after game end."""
        service = MahjongGameService(auto_cleanup=False)
        await service.start_game("game1", ["Player"], seed="a" * 192)

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: -10000, 1: -10000, 2: -10000, 3: -10000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = await service._handle_round_end("game1", round_result=result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" in service._games
        assert service._games["game1"].game_phase == GamePhase.FINISHED

    async def test_auto_cleanup_true_removes_state_after_game_end(self):
        """auto_cleanup=True (default) removes game state after game end."""
        service = MahjongGameService(auto_cleanup=True)
        await service.start_game("game1", ["Player"], seed="a" * 192)

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: -10000, 1: -10000, 2: -10000, 3: -10000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = await service._handle_round_end("game1", round_result=result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" not in service._games


class TestServiceAccessors:
    """Tests for read-only service accessors and round advance logic."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_is_round_advance_pending_true_after_round_end(self, service):
        """is_round_advance_pending returns True after round ends (player must confirm)."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        await service._handle_round_end("game1", result)

        assert service.is_round_advance_pending("game1") is True

    async def test_get_pending_round_advance_player_names_multi_player(self):
        """get_pending_round_advance_player_names returns all unconfirmed players."""
        service = MahjongGameService()
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        await service._handle_round_end("game1", result)

        names = service.get_pending_round_advance_player_names("game1")
        assert set(names) == {"Alice", "Bob", "Charlie", "Dave"}


class TestMahjongGameServiceUnsupportedSettings:
    """Tests for unsupported settings returning ErrorEvent instead of crashing."""

    async def test_unsupported_settings_returns_error_event(self):
        """start_game with unsupported settings returns ErrorEvent, not exception."""
        settings = GameSettings(num_players=3)
        service = MahjongGameService(settings=settings)
        events = await service.start_game("game1", ["Alice"])

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION
        assert "num_players=3" in events[0].data.message


class TestMahjongGameServiceInvalidSeed:
    """Tests for invalid seed values returning ErrorEvent instead of crashing."""

    async def test_invalid_seed_returns_error_event(self):
        """start_game with an invalid seed returns ErrorEvent, not exception."""
        service = MahjongGameService()
        events = await service.start_game("game1", ["Alice"], seed="bad-seed")

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION

    async def test_non_string_seed_returns_error_event(self):
        """start_game with a non-string seed returns ErrorEvent, not exception."""
        service = MahjongGameService()
        events = await service.start_game("game1", ["Alice"], seed=12345)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.INVALID_ACTION


class TestServiceGuardClauses:
    """Covers early-return guard clauses for nonexistent games/players."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_get_game_seed_nonexistent(self, service):
        assert service.get_game_seed("nonexistent") is None

    async def test_get_pending_names_nonexistent_game(self, service):
        assert service.get_pending_round_advance_player_names("nonexistent") == []

    async def test_get_pending_names_no_advance_pending(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        assert service.get_pending_round_advance_player_names("game1") == []

    async def test_find_player_seat_nonexistent_game(self, service):
        assert service._find_player_seat("nonexistent", "Player") is None

    async def test_process_ai_actions_nonexistent_game(self, service):
        events = await service.process_ai_player_actions_after_replacement("nonexistent", seat=0)
        assert events == []

    async def test_replace_without_ai_player_controller_is_safe(self, service):
        await service.start_game("game1", ["Alice"], seed="a" * 192)
        del service._ai_player_controllers["game1"]
        service.replace_with_ai_player("game1", "Alice")


class TestMahjongGameServiceRestoreHumanPlayer:
    """Tests for restore_human_player() reconnection method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_restore_removes_ai_from_seat(self, service):
        """restore_human_player removes the AI at the given seat."""
        await service.start_game("game1", ["Alice"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player("game1", "Alice")
        assert service._ai_player_controllers["game1"].is_ai_player(seat) is True

        service.restore_human_player("game1", seat)
        assert service._ai_player_controllers["game1"].is_ai_player(seat) is False

    async def test_restore_allows_find_player_seat(self, service):
        """After restore, _find_player_seat can find the human player again."""
        await service.start_game("game1", ["Alice"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player("game1", "Alice")
        assert service._find_player_seat("game1", "Alice") is None

        service.restore_human_player("game1", seat)
        assert service._find_player_seat("game1", "Alice") == seat

    async def test_restore_nonexistent_game_is_safe(self, service):
        """Restoring in a nonexistent game does nothing."""
        service.restore_human_player("nonexistent", 0)


class TestMahjongGameServiceBuildReconnectionSnapshot:
    """Tests for build_reconnection_snapshot()."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_snapshot_contains_full_game_state(self, service):
        """Snapshot includes all fields needed for reconnection."""
        await service.start_game("game1", ["Alice"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Alice")

        snapshot = service.build_reconnection_snapshot("game1", player.seat)

        assert snapshot is not None
        assert snapshot.game_id == "game1"
        assert snapshot.my_tiles == list(player.tiles)
        assert len(snapshot.player_states) == 4
        assert len(snapshot.players) == 4
        assert snapshot.dealer_seat == game_state.round_state.dealer_seat
        assert snapshot.dealer_dice == game_state.dealer_dice
        assert snapshot.round_number == game_state.round_number
        assert snapshot.current_player_seat == game_state.round_state.current_player_seat
        assert snapshot.dora_indicators == list(game_state.round_state.wall.dora_indicators)
        assert snapshot.honba_sticks == game_state.honba_sticks
        assert snapshot.riichi_sticks == game_state.riichi_sticks
        assert snapshot.tiles_remaining == len(game_state.round_state.wall.live_tiles)
        for ps in snapshot.player_states:
            assert isinstance(ps.discards, list)
            assert isinstance(ps.melds, list)
            assert isinstance(ps.is_riichi, bool)
            game_player = game_state.round_state.players[ps.seat]
            assert ps.score == game_player.score

    async def test_snapshot_reflects_ai_status_after_restore(self, service):
        """After restore_human_player, the snapshot marks the seat as non-AI."""
        await service.start_game("game1", ["Alice"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Alice")
        seat = player.seat

        service.replace_with_ai_player("game1", "Alice")
        service.restore_human_player("game1", seat)

        snapshot = service.build_reconnection_snapshot("game1", seat)

        assert snapshot is not None
        reconnected_player = next(p for p in snapshot.players if p.seat == seat)
        assert reconnected_player.is_ai_player is False

    async def test_snapshot_nonexistent_game_returns_none(self, service):
        assert service.build_reconnection_snapshot("nonexistent", 0) is None


class TestMahjongGameServiceBuildDrawEventForSeat:
    """Tests for build_draw_event_for_seat()."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_returns_draw_event_for_current_player(self, service):
        """Returns a draw event targeted to the current player's seat."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._games["game1"]
        current_seat = game_state.round_state.current_player_seat

        events = service.build_draw_event_for_seat("game1", current_seat)

        assert len(events) == 1
        assert events[0].event == EventType.DRAW
        assert isinstance(events[0].target, SeatTarget)
        assert events[0].target.seat == current_seat

    async def test_returns_empty_for_non_current_player(self, service):
        """Returns empty when it's not the given seat's turn."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._games["game1"]
        other_seat = (game_state.round_state.current_player_seat + 1) % 4

        events = service.build_draw_event_for_seat("game1", other_seat)

        assert events == []

    async def test_returns_empty_when_player_has_no_tiles(self, service):
        """Returns empty when the current player has no tiles (defensive guard)."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"], seed="a" * 192)
        game_state = service._games["game1"]
        current_seat = game_state.round_state.current_player_seat

        _update_player(service, "game1", current_seat, tiles=())

        events = service.build_draw_event_for_seat("game1", current_seat)
        assert events == []

    async def test_returns_empty_for_nonexistent_game(self, service):
        events = service.build_draw_event_for_seat("nonexistent", 0)
        assert events == []
