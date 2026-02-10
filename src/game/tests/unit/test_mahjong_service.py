"""Unit tests for MahjongGameService lifecycle and service-level edge cases."""

import importlib
import inspect

import pytest

from game.logic.enums import CallType, GameAction, GameErrorCode, GamePhase, RoundPhase
from game.logic.events import (
    ErrorEvent,
    EventType,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.settings import GameSettings
from game.logic.state import PendingCallPrompt
from game.logic.types import (
    ExhaustiveDrawResult,
    TenpaiHand,
)
from game.tests.unit.helpers import (
    _find_human_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceFindPlayerSeat:
    """Tests for _find_player_seat_frozen edge cases: bot skipping, name collision."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_player_seat_returns_none_for_unknown(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        seat = service._find_player_seat_frozen("game1", game_state, "Unknown")

        assert seat is None

    async def test_find_player_seat_skips_bot_seats(self, service):
        """Searching for a bot name returns None because bot seats are skipped."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        bot_controller = service._bot_controllers["game1"]

        bot_name = None
        for player in game_state.round_state.players:
            if bot_controller.is_bot(player.seat):
                bot_name = player.name
                break

        seat = service._find_player_seat_frozen("game1", game_state, bot_name)

        assert seat is None

    async def test_find_player_seat_ignores_bot_with_same_name(self, service):
        """Human named 'Tsumogiri 1' is found despite a bot with the same name."""
        await service.start_game("game1", ["Tsumogiri 1"])
        game_state = service._games["game1"]

        seat = service._find_player_seat_frozen("game1", game_state, "Tsumogiri 1")

        assert seat is not None
        bot_controller = service._bot_controllers["game1"]
        assert bot_controller.is_bot(seat) is False


class TestMahjongGameServiceAllHumans:
    """Tests for PVP mode (4 humans, 0 bots) edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_four_humans_zero_bots_in_controller(self, service):
        """0 bots created in BotController when starting with 4 humans."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        bot_controller = service._bot_controllers["game1"]
        bot_count = sum(1 for seat in range(4) if bot_controller.is_bot(seat))
        assert bot_count == 0

    async def test_four_humans_no_bot_followup_for_dealer(self, service):
        """Bot followup is not triggered when dealer is human (all humans)."""
        events = await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        # with 4 humans, exactly 1 draw event for dealer (no bot followup chain)
        draw_events = [e for e in events if e.event == EventType.DRAW]
        assert len(draw_events) == 1


class TestMahjongGameServiceReplacePlayerWithBot:
    """Tests for replace_player_with_bot() disconnect handling."""

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

        bot_controller = service._bot_controllers["game1"]
        assert len(bot_controller._bots) == 3

    async def test_replace_finds_seat_before_registering_bot(self, service):
        """Seat lookup happens before bot registration (since _find_player_seat skips bot seats)."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Alice")
        human_seat = human.seat

        service.replace_player_with_bot("game1", "Alice")

        bot_controller = service._bot_controllers["game1"]
        assert bot_controller.is_bot(human_seat) is True
        assert len(bot_controller._bots) == 4

    async def test_replace_same_player_twice_is_safe(self, service):
        """Replacing an already-replaced player is a no-op (seat not found)."""
        await service.start_game("game1", ["Alice"])

        service.replace_player_with_bot("game1", "Alice")
        service.replace_player_with_bot("game1", "Alice")

        bot_controller = service._bot_controllers["game1"]
        assert len(bot_controller._bots) == 4

    async def test_replace_without_bot_controller_is_safe(self, service):
        """Replacing a player when bot controller is missing does nothing."""
        await service.start_game("game1", ["Alice"])

        del service._bot_controllers["game1"]

        service.replace_player_with_bot("game1", "Alice")


class TestMahjongGameServiceProcessBotActionsAfterReplacement:
    """Tests for process_bot_actions_after_replacement() complex flows."""

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

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        events = await service.process_bot_actions_after_replacement("game1", seat=0)

        assert events == []

    async def test_processes_bot_turn_after_replacement(self, service):
        """After replacement, bot processes its pending turn if it's the current player."""
        await service.start_game("game1", ["Alice"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        human = _find_human_player(round_state, "Alice")
        human_seat = human.seat

        human_tiles = list(human.tiles)
        wall = list(round_state.wall)
        while len(human_tiles) < 14:
            if wall:
                human_tiles.append(wall.pop())

        new_players = []
        for p in round_state.players:
            if p.seat == human_seat:
                new_players.append(p.model_copy(update={"tiles": tuple(human_tiles)}))
            elif len(p.tiles) > 13:
                new_players.append(p.model_copy(update={"tiles": tuple(list(p.tiles)[:13])}))
            else:
                new_players.append(p)

        _update_round_state(
            service,
            "game1",
            current_player_seat=human_seat,
            wall=tuple(wall),
            players=tuple(new_players),
            pending_call_prompt=None,
        )

        service.replace_player_with_bot("game1", "Alice")

        events = await service.process_bot_actions_after_replacement("game1", human_seat)

        assert len(events) > 0

    async def test_handles_pending_call_prompt(self, service):
        """After replacement, bot resolves its pending call prompt response."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_human_player(round_state, "Alice")

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 1) % 4,
            pending_seats=frozenset({alice.seat}),
            callers=(alice.seat,),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        service.replace_player_with_bot("game1", "Alice")

        await service.process_bot_actions_after_replacement("game1", alice.seat)

        updated_round = service._games["game1"].round_state
        # Alice was the only pending caller, so after bot resolves the prompt should be cleared.
        # Bot followup may create new MELD prompts, but Alice's seat must not remain pending.
        if updated_round.pending_call_prompt is not None:
            assert alice.seat not in updated_round.pending_call_prompt.pending_seats

    async def test_pending_call_with_other_human_callers_returns_early(self, service):
        """When other human callers remain pending after bot dispatch, returns early."""
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        alice = _find_human_player(round_state, "Alice")
        bob = _find_human_player(round_state, "Bob")

        prompt = PendingCallPrompt(
            call_type=CallType.RON,
            tile_id=round_state.players[0].tiles[0] if round_state.players[0].tiles else 0,
            from_seat=(alice.seat + 2) % 4,
            pending_seats=frozenset({alice.seat, bob.seat}),
            callers=(alice.seat, bob.seat),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        service.replace_player_with_bot("game1", "Alice")

        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

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
        alice = _find_human_player(round_state, "Alice")

        discarder_seat = (alice.seat + 1) % 4
        tile_id = (
            round_state.players[discarder_seat].tiles[0] if round_state.players[discarder_seat].tiles else 0
        )
        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=tile_id,
            from_seat=discarder_seat,
            pending_seats=frozenset({alice.seat}),
            callers=(alice.seat,),
        )

        _update_round_state(service, "game1", wall=(), pending_call_prompt=prompt)

        service.replace_player_with_bot("game1", "Alice")

        events = await service.process_bot_actions_after_replacement("game1", alice.seat)

        round_end_events = [e for e in events if e.event == EventType.ROUND_END]
        assert len(round_end_events) >= 1


class TestDispatchAction:
    """Tests for _dispatch_action unified routing to action handlers."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_action_routes_chi(self, service):
        """_dispatch_action routes CALL_CHI to handle_chi."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(
            game_state,
            0,
            GameAction.CALL_CHI,
            {"tile_id": 0, "sequence_tiles": (1, 2)},
        )
        assert result is not None

    async def test_dispatch_action_routes_ron(self, service):
        """_dispatch_action routes CALL_RON to handle_ron."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, GameAction.CALL_RON, {})
        assert result is not None

    async def test_dispatch_action_routes_kan(self, service):
        """_dispatch_action routes CALL_KAN to handle_kan."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(
            game_state,
            0,
            GameAction.CALL_KAN,
            {"tile_id": 0, "kan_type": "closed"},
        )
        assert result is not None

    async def test_dispatch_action_routes_pass(self, service):
        """_dispatch_action routes PASS to handle_pass."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, GameAction.PASS)
        assert result is not None

    async def test_dispatch_action_routes_tsumo(self, service):
        """_dispatch_action routes DECLARE_TSUMO to handle_tsumo."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, GameAction.DECLARE_TSUMO)
        assert result is not None

    async def test_dispatch_action_routes_discard(self, service):
        """_dispatch_action routes DISCARD to handle_discard."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(
            game_state,
            0,
            GameAction.DISCARD,
            {"tile_id": 0},
        )
        assert result is not None

    async def test_dispatch_action_routes_kyuushu(self, service):
        """_dispatch_action routes CALL_KYUUSHU to handle_kyuushu."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, GameAction.CALL_KYUUSHU)
        # kyuushu may fail (conditions not met) but the handler is invoked
        assert result is not None

    async def test_dispatch_action_returns_none_for_unknown(self, service):
        """_dispatch_action returns None for unrecognized actions."""
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, GameAction.CONFIRM_ROUND)
        assert result is None


class TestSeedDeterminism:
    """Verify that start_game with same seed produces deterministic results."""

    async def test_same_seed_produces_deterministic_seats(self):
        service1 = MahjongGameService()
        service2 = MahjongGameService()

        await service1.start_game("game1", ["Human"], seed=42.0)
        await service2.start_game("game2", ["Human"], seed=42.0)

        state1 = service1._games["game1"]
        state2 = service2._games["game2"]

        names1 = [p.name for p in state1.round_state.players]
        names2 = [p.name for p in state2.round_state.players]
        assert names1 == names2

    async def test_same_seed_produces_deterministic_wall(self):
        service1 = MahjongGameService()
        service2 = MahjongGameService()

        await service1.start_game("game1", ["Human"], seed=42.0)
        await service2.start_game("game2", ["Human"], seed=42.0)

        state1 = service1._games["game1"]
        state2 = service2._games["game2"]

        tiles1 = [p.tiles for p in state1.round_state.players]
        tiles2 = [p.tiles for p in state2.round_state.players]
        assert tiles1 == tiles2
        assert state1.round_state.wall == state2.round_state.wall


class TestAutoCleanup:
    """Tests for auto_cleanup flag controlling state preservation after game end."""

    async def test_auto_cleanup_false_preserves_state_after_game_end(self):
        """auto_cleanup=False preserves game state in self._games after game end."""
        service = MahjongGameService(auto_cleanup=False)
        await service.start_game("game1", ["Human"], seed=2.0)

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
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
        await service.start_game("game1", ["Human"], seed=2.0)

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = await service._handle_round_end("game1", round_result=result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" not in service._games


class TestServiceAccessors:
    """Tests for read-only service accessors: error paths and multi-human edge case."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_get_game_state_returns_none_for_nonexistent(self, service):
        """get_game_state returns None for unknown game_id."""
        state = service.get_game_state("nonexistent")

        assert state is None

    async def test_get_game_seed_returns_seed_after_start(self, service):
        """get_game_seed returns the seed used to start the game."""
        await service.start_game("game1", ["Human"], seed=2.0)

        assert service.get_game_seed("game1") == 2.0

    async def test_get_game_seed_returns_none_for_nonexistent(self, service):
        """get_game_seed returns None for unknown game_id."""
        assert service.get_game_seed("nonexistent") is None

    async def test_is_round_advance_pending_true_after_round_end(self, service):
        """is_round_advance_pending returns True after round ends (human must confirm)."""
        await service.start_game("game1", ["Human"], seed=2.0)

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        await service._handle_round_end("game1", result)

        assert service.is_round_advance_pending("game1") is True

    async def test_is_round_advance_pending_false_for_nonexistent(self, service):
        """is_round_advance_pending returns False for unknown game_id."""
        assert service.is_round_advance_pending("nonexistent") is False

    async def test_get_pending_round_advance_human_names_empty_for_nonexistent(self, service):
        """get_pending_round_advance_human_names returns empty list for unknown game_id."""
        names = service.get_pending_round_advance_human_names("nonexistent")
        assert names == []

    async def test_get_pending_round_advance_human_names_empty_when_not_pending(self, service):
        """Returns empty list when game exists but no advance pending."""
        await service.start_game("game1", ["Human"], seed=2.0)

        names = service.get_pending_round_advance_human_names("game1")
        assert names == []

    async def test_get_pending_round_advance_human_names_multi_human(self):
        """get_pending_round_advance_human_names returns all unconfirmed humans."""
        service = MahjongGameService()
        await service.start_game("game1", ["Alice", "Bob", "Charlie", "Dave"])

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        await service._handle_round_end("game1", result)

        names = service.get_pending_round_advance_human_names("game1")
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


class TestDomainModuleBoundary:
    """Verify domain modules have no replay-only imports."""

    async def test_domain_modules_not_modified(self):
        """Verify domain modules (turn.py, action_handlers.py, call_resolution.py) have no replay imports."""
        for module_name in [
            "game.logic.turn",
            "game.logic.action_handlers",
            "game.logic.call_resolution",
        ]:
            module = importlib.import_module(module_name)
            source = inspect.getsource(module)
            assert "ReplayTarget" not in source
            assert "ReplayDrawEvent" not in source
            assert "ReplayRoundDataEvent" not in source
            assert "ReplayWinDetailEvent" not in source
