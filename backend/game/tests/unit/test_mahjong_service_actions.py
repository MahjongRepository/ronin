"""
Unit tests for MahjongGameService action handling.

Covers service-level entry point guards (game not found, player not in game,
unknown action), ValidationError wrapping in _dispatch_and_process,
_process_action_result_internal branching (chankan), and
_handle_chankan_prompt (player caller wait, AI player response).

Tests for individual action handler validation (wrong turn, missing tile,
invalid tile, no prompt) live in test_action_handlers_immutable.py and
test_action_handlers_edge_cases.py.
"""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from game.logic.action_result import ActionResult
from game.logic.enums import CallType, GameAction, GameErrorCode
from game.logic.events import (
    CallPromptEvent,
    ErrorEvent,
    EventType,
    SeatTarget,
    ServiceEvent,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt
from game.tests.unit.helpers import (
    _find_player,
    _update_round_state,
)


class TestMahjongGameServiceErrors:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_action_game_not_found(self, service):
        events = await service.handle_action("nonexistent", "Player", GameAction.DISCARD, {"tile_id": 0})

        assert any(e.event == EventType.ERROR for e in events)
        error_event = next(e for e in events if e.event == EventType.ERROR)
        assert isinstance(error_event.data, ErrorEvent)
        assert "not found" in error_event.data.message

    async def test_handle_action_player_not_in_game(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Unknown", GameAction.DISCARD, {"tile_id": 0})

        assert any(e.event == EventType.ERROR for e in events)
        error_event = next(e for e in events if e.event == EventType.ERROR)
        assert isinstance(error_event.data, ErrorEvent)
        assert "not in game" in error_event.data.message

    async def test_handle_action_unknown_action(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Player", "unknown_action", {})

        assert any(e.event == EventType.ERROR for e in events)
        error_event = next(e for e in events if e.event == EventType.ERROR)
        assert isinstance(error_event.data, ErrorEvent)
        assert "unknown action" in error_event.data.message


class TestMahjongGameServiceValidationError:
    """Tests for ValidationError handling in _dispatch_and_process."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_action_validation_error_on_invalid_data(self, service):
        """Trigger ValidationError by sending data with wrong types to a data-requiring action."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Player", GameAction.DISCARD, {"tile_id": "not_an_int"})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.VALIDATION_ERROR
        assert "invalid action data" in events[0].data.message

    @pytest.mark.parametrize(
        "action",
        [GameAction.DECLARE_RIICHI, GameAction.CALL_PON, GameAction.CALL_CHI, GameAction.CALL_KAN],
    )
    async def test_dispatch_data_actions_validation_error(self, service, action):
        """Exercise _dispatch_action dispatch branches with missing required fields."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_action("game1", "Player", action, {})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert events[0].data.code == GameErrorCode.VALIDATION_ERROR


class TestDispatchActionBranches:
    """Covers _dispatch_action routing branches for no-data actions and data=None fallback."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.mark.parametrize(
        "action",
        [GameAction.DECLARE_TSUMO, GameAction.CALL_RON, GameAction.CALL_KYUUSHU],
    )
    async def test_dispatch_no_data_actions(self, service, action):
        """No-data dispatch branches (TSUMO, RON, KYUUSHU) return a result."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        result = service._dispatch_action(game_state, 0, action)
        assert result is not None

    async def test_dispatch_data_action_with_none_data(self, service):
        """data=None is coerced to empty dict before dispatching data actions."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        # data=None -> {} -> ValidationError on required field, proving the None->dict coercion runs
        with pytest.raises(ValidationError):
            service._dispatch_action(game_state, 0, GameAction.DISCARD, None)


class TestMahjongGameServiceProcessActionResult:
    """Tests for _process_action_result_internal branching."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_action_result_chankan_prompt(self, service):
        """Verify _process_action_result_internal handles chankan prompts."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=player.seat,
            pending_seats=frozenset({ai_player_seats[0]}),
            callers=(ai_player_seats[0],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=player.seat,
            callers=[ai_player_seats[0]],
            target="all",
        )
        result = ActionResult(
            events=[chankan_prompt],
            needs_post_discard=False,
        )

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with patch(
            "game.logic.call_resolution.complete_added_kan_after_chankan_decline",
            return_value=(cleared_round, game_state, []),
        ):
            events = await service._process_action_result_internal("game1", result)

        assert len(events) >= 1


class TestMahjongGameServiceHandleChankanPrompt:
    """Tests for _handle_chankan_prompt."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_chankan_prompt_returns_events_for_player_caller(self, service):
        """Verify chankan returns events when player is a pending caller."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(player.seat,),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[player.seat],
                target="all",
            ),
            target=SeatTarget(seat=player.seat),
        )
        events = [chankan_prompt]

        result = await service._handle_chankan_prompt("game1", events)

        assert result == events

    async def test_chankan_prompt_processes_ai_player_response(self, service):
        """Verify chankan processes AI player responses when no player caller."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=ai_player_seats[0],
            pending_seats=frozenset({ai_player_seats[1]}),
            callers=(ai_player_seats[1],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=ai_player_seats[0],
                callers=[ai_player_seats[1]],
                target="all",
            ),
            target=SeatTarget(seat=ai_player_seats[1]),
        )
        events = [chankan_prompt]

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with patch(
            "game.logic.call_resolution.complete_added_kan_after_chankan_decline",
            return_value=(cleared_round, game_state, []),
        ):
            result = await service._handle_chankan_prompt("game1", events)

        assert len(result) >= 1

    async def test_chankan_prompt_no_pending_prompt(self, service):
        """Returns events immediately when no pending prompt."""
        await service.start_game("game1", ["Player"], seed="a" * 192)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[1],
                target="all",
            ),
            target=SeatTarget(seat=1),
        )
        events = [chankan_prompt]

        result = await service._handle_chankan_prompt("game1", events)

        assert result == events
