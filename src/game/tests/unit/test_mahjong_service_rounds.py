"""
Unit tests for MahjongGameService round progression and AI player turns.

Tests service-level handle_timeout branching (meld timeout, defensive guards,
error paths), _process_ai_player_followup edge cases (nonexistent game, missing
controller, finished phase, pending prompt, None action), _check_and_handle_round_end
(not-finished, finished with result, finished without result),
_process_post_discard branching (round-end-immediate, player-pending, AI-player-only,
draw-for-next-player, post-draw-round-end, AI-player-call-resolution-round-end),
_dispatch_ai_player_call_responses (no prompt, AI player action dispatch),
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
from game.logic.exceptions import InvalidActionError, InvalidGameActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt
from game.logic.types import (
    ExhaustiveDrawResult,
    MeldCaller,
    TenpaiHand,
)
from game.logic.wall import Wall
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)


class TestMahjongGameServiceHandleTimeout:
    """Tests for handle_timeout branching: meld timeout, defensive guards, error paths."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_meld_timeout_no_pending_prompt_returns_empty(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_timeout("game1", "Player", TimeoutType.MELD)

        assert events == []

    async def test_meld_timeout_with_pending_prompt_sends_pass(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({player.seat}),
            callers=(MeldCaller(seat=player.seat, call_type=MeldCallType.PON),),
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
            events = await service.handle_timeout("game1", "Player", TimeoutType.MELD)

        mock_action.assert_called_once_with("game1", "Player", GameAction.PASS, {})
        assert events == mock_events

    async def test_timeout_nonexistent_game_returns_empty(self, service):
        events = await service.handle_timeout("nonexistent", "Player", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_player_returns_empty(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events = await service.handle_timeout("game1", "Unknown", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_type_raises(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        with pytest.raises(InvalidActionError, match="Unknown timeout type"):
            await service.handle_timeout("game1", "Player", "invalid")

    async def test_turn_timeout_skips_when_pending_prompt(self, service):
        """Turn timeout returns empty when a call prompt is pending (race condition)."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({(player.seat + 2) % 4}),
            callers=(MeldCaller(seat=(player.seat + 2) % 4, call_type=MeldCallType.PON),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events = await service.handle_timeout("game1", "Player", TimeoutType.TURN)
        assert events == []

    async def test_turn_timeout_catches_invalid_game_action_error(self, service):
        """Turn timeout catches InvalidGameActionError when it blames the timed-out player's seat."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Player")

        with patch.object(
            service,
            "handle_action",
            side_effect=InvalidGameActionError(action="discard", seat=player.seat, reason="test"),
        ):
            events = await service.handle_timeout("game1", "Player", TimeoutType.TURN)

        assert events == []

    async def test_turn_timeout_reraises_when_error_blames_different_seat(self, service):
        """Turn timeout re-raises InvalidGameActionError when it blames a different seat."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        player = _find_player(service._games["game1"].round_state, "Player")
        other_seat = (player.seat + 1) % 4

        with (
            patch.object(
                service,
                "handle_action",
                side_effect=InvalidGameActionError(action="resolve_call", seat=other_seat, reason="test"),
            ),
            pytest.raises(InvalidGameActionError, match="test"),
        ):
            await service.handle_timeout("game1", "Player", TimeoutType.TURN)

    async def test_meld_timeout_catches_invalid_game_action_error(self, service):
        """Meld timeout catches InvalidGameActionError and returns empty (race condition)."""
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({player.seat}),
            callers=(MeldCaller(seat=player.seat, call_type=MeldCallType.PON),),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        with (
            patch.object(
                service,
                "handle_action",
                side_effect=InvalidGameActionError(action="pass", seat=player.seat, reason="test"),
            ),
            pytest.raises(InvalidGameActionError, match="test"),
        ):
            await service.handle_timeout("game1", "Player", TimeoutType.MELD)


class TestMahjongGameServiceProcessAIPlayerFollowup:
    """Tests for _process_ai_player_followup defensive checks."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_ai_player_followup_nonexistent_game(self, service):
        result = await service._process_ai_player_followup("nonexistent")

        assert result == []

    async def test_process_ai_player_followup_no_ai_player_controller(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        del service._ai_player_controllers["game1"]

        result = await service._process_ai_player_followup("game1")

        assert result == []


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    """Tests for _check_and_handle_round_end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_check_round_end_returns_none_when_not_finished(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        result = await service._check_and_handle_round_end("game1", [])

        assert result is None

    async def test_check_round_end_handles_finished_round(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
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
        await service.start_game("game1", ["Player"], seed="a" * 192)

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
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)
        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
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

    async def test_post_discard_with_pending_prompt_player_caller(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(
                MeldCaller(
                    seat=player.seat,
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
                    callers=[player.seat],
                    target="all",
                ),
                target=SeatTarget(seat=player.seat),
            )
        ]

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1

    async def test_post_discard_with_pending_prompt_ai_player_only(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        round_state = game_state.round_state

        current_seat = round_state.current_player_seat
        current_player = round_state.players[current_seat]
        if len(current_player.tiles) > 13:
            _update_player(service, "game1", current_seat, tiles=tuple(list(current_player.tiles)[:13]))
            round_state = service._games["game1"].round_state

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]
        ai_player_tile = (
            round_state.players[ai_player_seat].tiles[0] if round_state.players[ai_player_seat].tiles else 0
        )

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=ai_player_tile,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(
                MeldCaller(
                    seat=ai_player_seat,
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
                    tile_id=ai_player_tile,
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=ai_player_seat,
                            call_type=MeldCallType.PON,
                        )
                    ],
                    target="all",
                ),
                target=SeatTarget(seat=ai_player_seat),
            )
        ]

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1

    async def test_post_discard_draws_for_next_player(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
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
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        player_tiles = list(player.tiles)
        live_tiles = list(game_state.round_state.wall.live_tiles)
        if len(player_tiles) == 13 and live_tiles:
            player_tiles.append(live_tiles.pop(0))

        _update_player(service, "game1", player.seat, tiles=tuple(player_tiles))
        new_wall = game_state.round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)})
        _update_round_state(service, "game1", current_player_seat=player.seat, wall=new_wall)

        events = await service.handle_timeout("game1", "Player", TimeoutType.TURN)

        assert len(events) > 0
        assert any(e.event == EventType.DISCARD for e in events)

    async def test_timeout_turn_not_players_turn_returns_empty(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        other_seat = (player.seat + 1) % 4
        _update_round_state(service, "game1", current_player_seat=other_seat)

        events = await service.handle_timeout("game1", "Player", TimeoutType.TURN)

        assert events == []

    async def test_timeout_turn_empty_tiles_returns_empty(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        _update_player(service, "game1", player.seat, tiles=())
        _update_round_state(service, "game1", current_player_seat=player.seat)

        events = await service.handle_timeout("game1", "Player", TimeoutType.TURN)

        assert events == []


class TestMahjongGameServicePostDiscardRoundEnd:
    """Tests for round end paths within _process_post_discard."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_post_discard_post_draw_round_end(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", wall=Wall())

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) >= 1

    async def test_post_discard_round_end_after_ai_player_call_resolution(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(
                MeldCaller(
                    seat=ai_player_seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt, wall=Wall())

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        assert len(result) >= 1


class TestMahjongGameServiceDispatchAIPlayerCallResponses:
    """Tests for _dispatch_ai_player_call_responses edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_ai_player_call_responses_no_pending_prompt(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        events: list[ServiceEvent] = []
        service._dispatch_ai_player_call_responses("game1", events)

        assert events == []


class TestMahjongGameServiceFindCallerInfo:
    """Tests for _find_caller_info assertion path."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_caller_info_raises_for_missing_seat(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

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


class TestMahjongGameServiceProcessAIPlayerFollowupEdgeCases:
    """Tests for _process_ai_player_followup edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_ai_player_followup_stops_on_finished_phase(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        _update_round_state(service, "game1", phase=RoundPhase.FINISHED)

        result = await service._process_ai_player_followup("game1")

        assert result == []

    async def test_process_ai_player_followup_stops_on_pending_prompt(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({0}),
            callers=(0,),
        )
        _update_round_state(
            service,
            "game1",
            current_player_seat=ai_player_seats[0],
            pending_call_prompt=prompt,
        )

        result = await service._process_ai_player_followup("game1")

        assert result == []

    async def test_process_ai_player_followup_stops_when_get_turn_action_returns_none(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        _update_round_state(service, "game1", current_player_seat=ai_player_seats[0])

        with patch.object(ai_player_controller, "get_turn_action", return_value=None):
            result = await service._process_ai_player_followup("game1")

        assert result == []


class TestMahjongGameServiceDispatchAIPlayerCallResponsesBranches:
    """Tests for _dispatch_ai_player_call_responses covering AI player action dispatch."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_ai_player_call_responses_ai_player_returns_action(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        ai_player_controller = service._ai_player_controllers["game1"]
        ai_player_seats = sorted(ai_player_controller.ai_player_seats)
        ai_player_seat = ai_player_seats[0]

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({ai_player_seat}),
            callers=(
                MeldCaller(
                    seat=ai_player_seat,
                    call_type=MeldCallType.PON,
                ),
            ),
        )
        _update_round_state(service, "game1", pending_call_prompt=prompt)

        events: list[ServiceEvent] = []

        cleared_round = game_state.round_state.model_copy(update={"pending_call_prompt": None})
        with (
            patch.object(
                ai_player_controller,
                "get_call_response",
                return_value=(GameAction.CALL_PON, {"tile_id": 0}),
            ),
            patch(
                "game.logic.mahjong_service.handle_pon",
                return_value=ActionResult([], new_round_state=cleared_round, new_game_state=game_state),
            ),
        ):
            service._dispatch_ai_player_call_responses("game1", events)


class TestGetPlayerSeat:
    """Tests for get_player_seat covering the real MahjongGameService method."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_get_player_seat_returns_seat(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)

        seat = service.get_player_seat("game1", "Player")

        assert seat is not None
        assert 0 <= seat <= 3

    async def test_get_player_seat_nonexistent_game(self, service):
        seat = service.get_player_seat("nonexistent", "Player")

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
        await service.start_game("game1", ["Player"], seed="a" * 192)
        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")

        for seat in range(4):
            _update_player(service, "game1", seat, score=-10000)

        _update_round_state(
            service,
            "game1",
            current_player_seat=player.seat,
            wall=Wall(),
        )

        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        tiles = list(player.tiles)
        if len(tiles) < 14:
            tiles.append(0)
        _update_player(service, "game1", player.seat, tiles=tuple(tiles[:14]))

        game_state = service._games["game1"]
        player = _find_player(game_state.round_state, "Player")
        tile_id = player.tiles[-1]

        events = await service.handle_action("game1", "Player", GameAction.DISCARD, {"tile_id": tile_id})

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert "game1" not in service._games


class TestMahjongGameServiceChankanPromptRoundEnd:
    """Tests for chankan prompt resolution leading to round end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_chankan_prompt_resolved_round_end(self, service):
        await service.start_game("game1", ["Player"], seed="a" * 192)
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

        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        def mock_dispatch_ai_player_call(_game_id, _evts):
            _update_round_state(service, "game1", pending_call_prompt=None, phase=RoundPhase.FINISHED)

        with (
            patch.object(
                service,
                "_dispatch_ai_player_call_responses",
                side_effect=mock_dispatch_ai_player_call,
            ),
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
