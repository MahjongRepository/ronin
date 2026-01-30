"""
Unit tests for MahjongGameService action handling.
"""

from unittest.mock import patch

import pytest

from game.logic.action_handlers import ActionResult
from game.logic.enums import CallType
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt, RoundPhase
from game.logic.types import (
    ExhaustiveDrawResult,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    ServiceEvent,
)
from game.tests.unit.helpers import _find_human_player


class TestMahjongGameServiceDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_discard_validates_player_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # force current player to a different seat so the human is out of turn
        round_state.current_player_seat = 1
        # ensure all players have 13 tiles so subsequent draws work correctly
        for player in round_state.players:
            while len(player.tiles) > 13:
                player.tiles.pop()

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
        round_state = game_state.round_state

        # force current player to a different seat so the human is out of turn
        round_state.current_player_seat = 1
        # ensure all players have 13 tiles so subsequent draws work correctly
        for player in round_state.players:
            while len(player.tiles) > 13:
                player.tiles.pop()

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


class TestMahjongGameServiceValidationError:
    """Tests for ValidationError handling in _dispatch_and_process."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_action_validation_error_on_invalid_data(self, service):
        """Trigger ValidationError by sending data with wrong types to a data-requiring action."""
        await service.start_game("game1", ["Human"])

        # send discard with tile_id as a non-integer string that fails pydantic validation
        events = await service.handle_action("game1", "Human", "discard", {"tile_id": "not_an_int"})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == "validation_error"
        assert "invalid action data" in events[0].data.message

    async def test_dispatch_action_unknown_data_action(self, service):
        """Trigger unknown action branch for data-requiring actions."""
        await service.start_game("game1", ["Human"])

        # send an action that matches no handler
        events = await service.handle_action("game1", "Human", "unknown_action", {"some": "data"})

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == "unknown_action"


class TestMahjongGameServiceProcessActionResult:
    """Tests for _process_action_result_internal."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_action_result_round_end(self, service):
        """Verify _process_action_result_internal returns round end events when round is finished."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # set phase to FINISHED to trigger round end path
        game_state.round_state.phase = RoundPhase.FINISHED

        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        result = ActionResult(
            events=[RoundEndEvent(result=round_result, target="all")],
            needs_post_discard=False,
        )

        events = await service._process_action_result_internal("game1", result)

        # should contain round end handling
        assert len(events) >= 1

    async def test_process_action_result_post_discard(self, service):
        """Verify _process_action_result_internal delegates to post-discard processing."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # ensure current player has 13 tiles (simulating post-discard state)
        current_player = round_state.players[round_state.current_player_seat]
        while len(current_player.tiles) > 13:
            current_player.tiles.pop()

        result = ActionResult(
            events=[
                DiscardEvent(
                    seat=0,
                    tile_id=0,
                    tile="1m",
                    is_tsumogiri=True,
                    is_riichi=False,
                    target="all",
                )
            ],
            needs_post_discard=True,
        )

        events = await service._process_action_result_internal("game1", result)

        # should have processed post-discard logic
        assert len(events) >= 1

    async def test_process_action_result_chankan_prompt(self, service):
        """Verify _process_action_result_internal handles chankan prompts."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        round_state = game_state.round_state

        # find bot seats
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        # set up pending call prompt for chankan
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=human.seat,
            pending_seats={bot_seats[0]},
            callers=[bot_seats[0]],
        )

        chankan_prompt = CallPromptEvent(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=human.seat,
            callers=[bot_seats[0]],
            target="all",
        )
        result = ActionResult(
            events=[chankan_prompt],
            needs_post_discard=False,
        )

        # mock complete_added_kan_after_chankan_decline to avoid tile validation issues
        with patch(
            "game.logic.action_handlers.complete_added_kan_after_chankan_decline",
            return_value=[],
        ):
            events = await service._process_action_result_internal("game1", result)

        # should have processed chankan
        assert len(events) >= 1


class TestMahjongGameServiceHandleChankanPrompt:
    """Tests for _handle_chankan_prompt."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_chankan_prompt_returns_events_for_human_caller(self, service):
        """Verify chankan returns events when human is a pending caller."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        round_state = game_state.round_state

        # set up pending call prompt with human caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=0,
            pending_seats={human.seat},
            callers=[human.seat],
        )

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[human.seat],
                target="all",
            ),
            target="all",
        )
        events = [chankan_prompt]

        result = await service._handle_chankan_prompt("game1", events, chankan_prompt)

        # should return immediately with events since human needs to respond
        assert result == events

    async def test_chankan_prompt_processes_bot_response(self, service):
        """Verify chankan processes bot responses when no human caller."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # find bot seats
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        # set up pending call prompt with only bot callers
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=bot_seats[0],
            pending_seats={bot_seats[1]},
            callers=[bot_seats[1]],
        )

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=bot_seats[0],
                callers=[bot_seats[1]],
                target="all",
            ),
            target="all",
        )
        events = [chankan_prompt]

        # mock complete_added_kan_after_chankan_decline to avoid tile validation issues
        with patch(
            "game.logic.action_handlers.complete_added_kan_after_chankan_decline",
            return_value=[],
        ):
            result = await service._handle_chankan_prompt("game1", events, chankan_prompt)

        # bot should have responded, prompt resolved
        assert len(result) >= 1

    async def test_chankan_prompt_no_pending_prompt(self, service):
        """Verify chankan returns events immediately when no pending prompt."""
        await service.start_game("game1", ["Human"])

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=0,
                callers=[1],
                target="all",
            ),
            target="all",
        )
        events = [chankan_prompt]

        result = await service._handle_chankan_prompt("game1", events, chankan_prompt)

        # should return immediately with no pending prompt
        assert result == events
