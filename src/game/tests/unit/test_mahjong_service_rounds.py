"""
Unit tests for MahjongGameService round progression and bot turns.

Tests service-level handle_timeout branching (meld timeout, defensive guards,
error paths), _process_bot_followup edge cases (nonexistent game, missing
controller, finished phase, pending prompt, None action), _check_and_handle_round_end
(not-finished, finished with result, finished without result),
_process_post_discard branching (round-end-immediate, human-pending, bot-only,
draw-for-next-player, post-draw-round-end, bot-call-resolution-round-end),
_dispatch_bot_call_responses (no prompt, bot action dispatch),
_find_caller_info assertion path, timeout forced-state tests (turn on/off,
empty tiles), and chankan prompt resolution leading to round end.
"""

from unittest.mock import patch

import pytest

from game.logic.action_result import ActionResult
from game.logic.enums import CallType, GameAction, GameErrorCode, MeldCallType, RoundPhase, TimeoutType
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.exceptions import InvalidActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt
from game.logic.types import (
    ExhaustiveDrawResult,
    MeldCaller,
    TenpaiHand,
)
from game.tests.unit.helpers import (
    _find_human_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceHandleTimeout:
    """Tests for handle_timeout branching: meld timeout, defensive guards, error paths."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_meld_timeout_no_pending_prompt_returns_empty(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        events = await service.handle_timeout("game1", "Human", TimeoutType.MELD)

        assert events == []

    async def test_meld_timeout_with_pending_prompt_sends_pass(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        human = _find_human_player(round_state, "Human")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=(human.seat + 1) % 4,
            pending_seats=frozenset({human.seat}),
            callers=(MeldCaller(seat=human.seat, call_type=MeldCallType.PON),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        mock_events = [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(code=GameErrorCode.GAME_ERROR, message="mock", target="all"),
                target=BroadcastTarget(),
            )
        ]
        with patch.object(service, "handle_action", return_value=mock_events) as mock_action:
            events = await service.handle_timeout("game1", "Human", TimeoutType.MELD)

        mock_action.assert_called_once_with("game1", "Human", GameAction.PASS, {})
        assert events == mock_events

    async def test_timeout_nonexistent_game_returns_empty(self, service):
        events = await service.handle_timeout("nonexistent", "Human", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_player_returns_empty(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        events = await service.handle_timeout("game1", "Unknown", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_type_raises(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        with pytest.raises(InvalidActionError, match="Unknown timeout type"):
            await service.handle_timeout("game1", "Human", "invalid")


class TestMahjongGameServiceProcessBotFollowup:
    """Tests for _process_bot_followup defensive checks."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_bot_followup_nonexistent_game(self, service):
        result = await service._process_bot_followup("nonexistent")

        assert result == []

    async def test_process_bot_followup_no_bot_controller(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        del service._bot_controllers["game1"]

        result = await service._process_bot_followup("game1")

        assert result == []


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    """Tests for _check_and_handle_round_end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_check_round_end_returns_none_when_not_finished(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        result = await service._check_and_handle_round_end("game1", [])

        assert result is None

    async def test_check_round_end_handles_finished_round(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target=BroadcastTarget(),
            )
        ]

        result = await service._check_and_handle_round_end("game1", events)

        assert result is not None
        assert len(result) >= 1
        assert any(e.event == EventType.ROUND_END for e in result)

    async def test_check_round_end_handles_no_result_in_events(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        result = await service._check_and_handle_round_end("game1", [])

        assert result is not None
        error_events = [e for e in result if e.event == EventType.ERROR]
        assert len(error_events) == 1


class TestMahjongGameServiceProcessPostDiscard:
    """Tests for _process_post_discard including call prompt handling."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_post_discard_returns_events_when_round_ends_immediately(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target=BroadcastTarget(),
            )
        ]

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1

    async def test_post_discard_with_pending_prompt_human_caller(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({human.seat}),
            callers=(
                MeldCaller(
                    seat=human.seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=0,
                    from_seat=0,
                    callers=[human.seat],
                    target="all",
                ),
                target=SeatTarget(seat=human.seat),
            )
        ]

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1

    async def test_post_discard_with_pending_prompt_bot_only(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, "game1", current_seat, tiles=tuple(list(current_player.tiles)[:13]))
            round_state = service._games["game1"].round_state

        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]
        bot_tile = round_state.players[bot_seat].tiles[0] if round_state.players[bot_seat].tiles else 0

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=bot_tile,
            from_seat=0,
            pending_seats=frozenset({bot_seat}),
            callers=(
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=bot_tile,
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=bot_seat,
                            call_type=MeldCallType.PON,
                        )
                    ],
                    target="all",
                ),
                target=SeatTarget(seat=bot_seat),
            )
        ]

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1

    async def test_post_discard_draws_for_next_player(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, "game1", current_seat, tiles=tuple(list(current_player.tiles)[:13]))

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1


class TestMahjongGameServiceTimeoutIntegration:
    """Tests for timeout handling with forced state covering deterministic branches."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_timeout_turn_when_its_players_turn(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        human_tiles = list(human.tiles)
        wall = list(game_state.round_state.wall)
        if len(human_tiles) == 13 and wall:
            human_tiles.append(wall.pop(0))

        _update_player(service, "game1", human.seat, tiles=tuple(human_tiles))
        _update_round_state(service, "game1", current_player_seat=human.seat, wall=tuple(wall))

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert len(events) > 0
        assert any(e.event == EventType.DISCARD for e in events)

    async def test_timeout_turn_not_players_turn_returns_empty(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        other_seat = (human.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=other_seat)

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert events == []

    async def test_timeout_turn_empty_tiles_returns_empty(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        _update_player(service, "game1", human.seat, tiles=())
        _update_round_state(service, "game1", current_player_seat=human.seat)

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert events == []


class TestMahjongGameServicePostDiscardRoundEnd:
    """Tests for round end paths within _process_post_discard."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_post_discard_post_draw_round_end(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_round_state(service, "game1", wall=())

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) >= 1

    async def test_post_discard_round_end_after_bot_call_resolution(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({bot_seat}),
            callers=(
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt, wall=())

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1


class TestMahjongGameServiceDispatchBotCallResponses:
    """Tests for _dispatch_bot_call_responses edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_bot_call_responses_no_pending_prompt(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        events: list[ServiceEvent] = []
        service._dispatch_bot_call_responses("game1", events)

        assert events == []


class TestMahjongGameServiceFindCallerInfo:
    """Tests for _find_caller_info assertion path."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_caller_info_raises_for_missing_seat(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({1}),
            callers=(
                MeldCaller(
                    seat=2,
                    call_type=MeldCallType.PON,
                ),
            ),
        )

        with pytest.raises(AssertionError, match="seat 1 not found in prompt callers"):
            service._find_caller_info(prompt, 1)


class TestMahjongGameServiceProcessBotFollowupEdgeCases:
    """Tests for _process_bot_followup edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_bot_followup_stops_on_finished_phase(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        result = await service._process_bot_followup("game1")

        assert result == []

    async def test_process_bot_followup_stops_on_pending_prompt(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({0}),
            callers=(0,),
        )
        _update_round_state(service, "game1", current_player_seat=bot_seats[0], pending_call_prompt=prompt)

        result = await service._process_bot_followup("game1")

        assert result == []

    async def test_process_bot_followup_stops_when_get_turn_action_returns_none(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        _update_round_state(service, "game1", current_player_seat=bot_seats[0])

        with patch.object(bot_controller, "get_turn_action", return_value=None):
            result = await service._process_bot_followup("game1")

        assert result == []


class TestMahjongGameServiceDispatchBotCallResponsesBranches:
    """Tests for _dispatch_bot_call_responses covering bot action dispatch."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_bot_call_responses_bot_returns_action(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({bot_seat}),
            callers=(
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events: list[ServiceEvent] = []

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with (
            patch.object(
                bot_controller,
                "get_call_response",
                return_value=(GameAction.CALL_PON, {"tile_id": 0}),
            ),
            patch(
                "game.logic.mahjong_service.handle_pon",
                return_value=ActionResult([], new_round_state=cleared_round, new_game_state=game_state),
            ),
        ):
            service._dispatch_bot_call_responses("game1", events)


class TestGetPlayerSeat:
    """Tests for get_player_seat covering the real MahjongGameService method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_get_player_seat_returns_seat(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)

        seat = service.get_player_seat("game1", "Human")

        assert seat is not None
        assert 0 <= seat <= 3

    async def test_get_player_seat_nonexistent_game(self, service):
        seat = service.get_player_seat("nonexistent", "Human")

        assert seat is None


class TestGameEndCleanupSafety:
    """Regression: handle_action returns events without KeyError after game-end cleanup.

    cleanup_game removes the game from self._games during game-end handling.
    Without the safe .get() guard, handle_action raises KeyError when re-reading
    state after _dispatch_and_process.
    """

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_action_returns_events_after_game_end_cleanup(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        _update_round_state(
            service,
            "game1",
            current_player_seat=human.seat,
            wall=(),
        )

        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        tiles = list(human.tiles)
        if len(tiles) < 14:
            tiles.append(0)
        _update_player(service, "game1", human.seat, tiles=tuple(tiles[:14]))

        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]

        events = await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" not in service._games


class TestMahjongGameServiceChankanPromptRoundEnd:
    """Tests for chankan prompt resolution leading to round end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_chankan_prompt_resolved_round_end(self, service):
        await service.start_game("game1", ["Human"], seed=2.0)
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.CHANKAN,
            tile_id=0,
            from_seat=bot_seats[0],
            pending_seats=frozenset({bot_seats[1]}),
            callers=(bot_seats[1],),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        chankan_prompt = ServiceEvent(
            event=EventType.CALL_PROMPT,
            data=CallPromptEvent(
                call_type=CallType.CHANKAN,
                tile_id=0,
                from_seat=bot_seats[0],
                callers=[bot_seats[1]],
                target="all",
            ),
            target=SeatTarget(seat=bot_seats[1]),
        )
        events = [chankan_prompt]

        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        def mock_dispatch_bot_call(_game_id, _evts):
            _update_round_state(service, "game1", pending_call_prompt=None, phase=RoundPhase.FINISHED)

        with (
            patch.object(service, "_dispatch_bot_call_responses", side_effect=mock_dispatch_bot_call),
            patch.object(
                service,
                "_check_and_handle_round_end",
                return_value=[
                    ServiceEvent(
                        event=EventType.ROUND_END,
                        data=RoundEndEvent(result=round_result, target="all"),
                        target=BroadcastTarget(),
                    )
                ],
            ),
        ):
            result = await service._handle_chankan_prompt("game1", events)

        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) == 1
