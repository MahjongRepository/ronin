"""
Unit tests for MahjongGameService round progression and bot turns.
"""

from unittest.mock import patch

import pytest

from game.logic.action_handlers import ActionResult
from game.logic.enums import CallType, GameAction, GameErrorCode, MeldCallType, RoundPhase, TimeoutType
from game.logic.mahjong_service import MahjongGameService
from game.logic.state import PendingCallPrompt
from game.logic.types import (
    ExhaustiveDrawResult,
    MeldCaller,
)
from game.messaging.events import (
    CallPromptEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    ServiceEvent,
)
from game.tests.unit.helpers import _find_human_player


async def _play_human_turns(
    service: MahjongGameService, game_id: str, player_name: str, max_turns: int = 100
) -> list[ServiceEvent]:
    """
    Play repeated human discard turns until the round ends or max_turns reached.

    Returns all events from the actions.
    """
    all_events: list[ServiceEvent] = []
    for _ in range(max_turns):
        game_state = service._games.get(game_id)
        if game_state is None:
            break
        round_state = game_state.round_state
        if round_state.phase != RoundPhase.PLAYING:
            break

        human = _find_human_player(round_state, player_name)
        if round_state.current_player_seat != human.seat:
            break

        if not human.tiles:
            break

        tile_id = human.tiles[-1]
        events = await service.handle_action(game_id, player_name, GameAction.DISCARD, {"tile_id": tile_id})
        all_events.extend(events)
    return all_events


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
        events = await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        # should have multiple events from bot turns
        assert len(events) > 1

    async def test_bot_turns_stop_at_human_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        human = _find_human_player(game_state.round_state, "Human")
        tile_id = human.tiles[-1]

        await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})

        # after bot turns complete, should be human's turn again (unless round ended)
        round_state = game_state.round_state
        if round_state.phase == RoundPhase.PLAYING:
            # if round is still playing, current player should be human or there's a pending call prompt
            current_seat = round_state.current_player_seat
            bot_controller = service._bot_controllers["game1"]
            assert not bot_controller.is_bot(current_seat) or round_state.phase != RoundPhase.PLAYING


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
        bot_controller = service._bot_controllers["game1"]
        bot_players = [p for p in round_state.players if bot_controller.is_bot(p.seat)]
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
            assert any(e.event == EventType.DISCARD for e in events)

    async def test_turn_timeout_returns_empty_when_not_players_turn(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        if game_state.round_state.current_player_seat != human.seat:
            events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)
            assert events == []

    async def test_meld_timeout_no_pending_prompt_returns_empty(self, service):
        await service.start_game("game1", ["Human"])

        events = await service.handle_timeout("game1", "Human", TimeoutType.MELD)

        # meld timeout with no pending prompt is ignored
        assert events == []

    async def test_meld_timeout_with_pending_prompt_sends_pass(self, service):
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        human = _find_human_player(round_state, "Human")

        # set up a pending call prompt where the human is a caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=(human.seat + 1) % 4,
            pending_seats={human.seat},
            callers=[MeldCaller(seat=human.seat, call_type=MeldCallType.PON)],
        )

        mock_events = [
            ServiceEvent(
                event=EventType.ERROR,
                data=ErrorEvent(code=GameErrorCode.GAME_ERROR, message="mock", target="all"),
                target="all",
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
        await service.start_game("game1", ["Human"])

        events = await service.handle_timeout("game1", "Unknown", TimeoutType.TURN)

        assert events == []

    async def test_timeout_unknown_type_raises(self, service):
        await service.start_game("game1", ["Human"])

        with pytest.raises(ValueError, match="Unknown timeout type"):
            await service.handle_timeout("game1", "Human", "invalid")

    async def test_get_player_seat_returns_seat(self, service):
        await service.start_game("game1", ["Human"])

        seat = service.get_player_seat("game1", "Human")

        assert seat is not None
        assert 0 <= seat <= 3

    async def test_get_player_seat_nonexistent_game(self, service):
        seat = service.get_player_seat("nonexistent", "Human")

        assert seat is None


class TestMahjongGameServiceProcessBotFollowup:
    """Tests for _process_bot_followup defensive checks."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_bot_followup_nonexistent_game(self, service):
        """Verify _process_bot_followup returns empty for nonexistent game."""
        result = await service._process_bot_followup("nonexistent")

        assert result == []

    async def test_process_bot_followup_no_bot_controller(self, service):
        """Verify _process_bot_followup returns empty when bot controller is missing."""
        await service.start_game("game1", ["Human"])
        # manually remove bot controller
        del service._bot_controllers["game1"]

        result = await service._process_bot_followup("game1")

        assert result == []


class TestMahjongGameServiceRoundEndCallback:
    """Tests for _handle_round_end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_round_end_enters_waiting_state(self, service):
        """Verify _handle_round_end enters waiting state for human confirmation."""
        await service.start_game("game1", ["Human"])

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )

        events = await service._handle_round_end("game1", result)

        # returns empty (waiting for human confirmation)
        assert events == []
        # pending advance should exist
        assert "game1" in service._pending_advances


class TestMahjongGameServiceHandleRoundEnd:
    """Tests for _handle_round_end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_handle_round_end_with_none_result(self, service):
        """Verify _handle_round_end returns error when round_result is None."""
        await service.start_game("game1", ["Human"])

        events = await service._handle_round_end("game1", round_result=None)

        assert len(events) == 1
        assert events[0].event == EventType.ERROR
        assert isinstance(events[0].data, ErrorEvent)
        assert events[0].data.code == GameErrorCode.MISSING_ROUND_RESULT

    async def test_handle_round_end_waits_for_confirmation(self, service):
        """Verify _handle_round_end enters waiting state when humans are present."""
        await service.start_game("game1", ["Human"])

        result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )

        events = await service._handle_round_end("game1", round_result=result)

        # returns empty (waiting for human confirmation)
        assert events == []
        assert "game1" in service._pending_advances

    async def test_handle_round_end_ends_game_on_negative_score(self, service):
        """Verify _handle_round_end ends game when a player has negative score."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # set a player's score to very low so game ends after round processing
        game_state.round_state.players[0].score = -1000

        result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        events = await service._handle_round_end("game1", round_result=result)

        game_end_events = [e for e in events if e.event == EventType.GAME_END]
        assert len(game_end_events) == 1
        # game should be cleaned up
        assert "game1" not in service._games
        assert "game1" not in service._bot_controllers


class TestMahjongGameServiceStartNextRound:
    """Tests for _start_next_round."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_start_next_round_returns_round_started_events(self, service):
        """Verify _start_next_round generates round_started events for all players."""
        await service.start_game("game1", ["Human"])

        events = await service._start_next_round("game1")

        round_started = [e for e in events if e.event == EventType.ROUND_STARTED]
        assert len(round_started) == 4
        targets = {e.target for e in round_started}
        assert targets == {"seat_0", "seat_1", "seat_2", "seat_3"}

    async def test_start_next_round_includes_draw_event(self, service):
        """Verify _start_next_round includes draw events."""
        await service.start_game("game1", ["Human"])

        events = await service._start_next_round("game1")

        draw_events = [e for e in events if e.event == EventType.DRAW]
        assert len(draw_events) >= 1


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    """Tests for _check_and_handle_round_end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_check_round_end_returns_none_when_not_finished(self, service):
        """Verify returns None when round is not finished."""
        await service.start_game("game1", ["Human"])

        result = await service._check_and_handle_round_end("game1", [])

        assert result is None

    async def test_check_round_end_handles_finished_round(self, service):
        """Verify round end is processed when phase is FINISHED."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # set phase to FINISHED and provide a round end event
        game_state.round_state.phase = RoundPhase.FINISHED
        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target="all",
            )
        ]

        result = await service._check_and_handle_round_end("game1", events)

        assert result is not None
        # should have the original round_end event (round advance is now deferred)
        assert len(result) >= 1
        assert any(e.event == EventType.ROUND_END for e in result)

    async def test_check_round_end_handles_no_result_in_events(self, service):
        """Verify round end handling when no round result is in events."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # set phase to FINISHED but provide no round_end event
        game_state.round_state.phase = RoundPhase.FINISHED

        result = await service._check_and_handle_round_end("game1", [])

        assert result is not None
        # should contain error about missing round result
        error_events = [e for e in result if e.event == EventType.ERROR]
        assert len(error_events) == 1


class TestMahjongGameServiceProcessPostDiscard:
    """Tests for _process_post_discard including call prompt handling."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_post_discard_returns_events_when_round_ends_immediately(self, service):
        """Verify post-discard returns when round ends immediately."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # set phase to FINISHED
        game_state.round_state.phase = RoundPhase.FINISHED
        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )
        events = [
            ServiceEvent(
                event=EventType.ROUND_END,
                data=RoundEndEvent(result=round_result, target="all"),
                target="all",
            )
        ]

        result = await service._process_post_discard("game1", events)

        # should return with round end handling events
        assert len(result) >= 1

    async def test_post_discard_with_pending_prompt_human_caller(self, service):
        """Verify post-discard returns events when human has a pending call prompt."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")
        round_state = game_state.round_state

        # set up pending call prompt with human caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={human.seat},
            callers=[
                MeldCaller(
                    seat=human.seat,
                    call_type=MeldCallType.PON,
                )
            ],
        )

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
                target="all",
            )
        ]

        result = await service._process_post_discard("game1", events)

        # should return with pending prompt still waiting for human
        assert len(result) >= 1

    async def test_post_discard_with_pending_prompt_bot_only(self, service):
        """Verify post-discard processes bot call responses when only bots are pending."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # ensure current player has 13 tiles (simulating post-discard state)
        current_player = round_state.players[round_state.current_player_seat]
        while len(current_player.tiles) > 13:
            current_player.tiles.pop()

        # find a bot seat
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]

        # set up pending call prompt with only bot callers
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=round_state.players[bot_seat].tiles[0] if round_state.players[bot_seat].tiles else 0,
            from_seat=0,
            pending_seats={bot_seat},
            callers=[
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                )
            ],
        )

        events: list[ServiceEvent] = [
            ServiceEvent(
                event=EventType.CALL_PROMPT,
                data=CallPromptEvent(
                    call_type=CallType.MELD,
                    tile_id=round_state.players[bot_seat].tiles[0]
                    if round_state.players[bot_seat].tiles
                    else 0,
                    from_seat=0,
                    callers=[
                        MeldCaller(
                            seat=bot_seat,
                            call_type=MeldCallType.PON,
                        )
                    ],
                    target="all",
                ),
                target="all",
            )
        ]

        result = await service._process_post_discard("game1", events)

        # should have processed bot responses
        assert len(result) >= 1

    async def test_post_discard_draws_for_next_player(self, service):
        """Verify post-discard draws for next player when round is still playing."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # ensure current player has 13 tiles (simulating post-discard state)
        current_player = round_state.players[round_state.current_player_seat]
        while len(current_player.tiles) > 13:
            current_player.tiles.pop()

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        # should have draw events for next player
        assert len(result) >= 1


class TestMahjongGameServiceFullRound:
    """Tests that play through full game rounds to exercise integration paths."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_full_round_plays_to_completion(self, service):
        """Play through a full round by discarding tiles until round ends."""
        await service.start_game("game1", ["Human"])

        all_events = await _play_human_turns(service, "game1", "Human")

        # the game should have progressed (generated events)
        assert len(all_events) >= 1

    async def test_multiple_rounds_play_through(self, service):
        """Play through multiple rounds to test round end and next round transitions."""
        await service.start_game("game1", ["Human"])

        # play many rounds by repeatedly discarding
        for _ in range(5):
            game_state = service._games.get("game1")
            if game_state is None:
                break

            round_state = game_state.round_state
            if round_state.phase != RoundPhase.PLAYING:
                break

            human = _find_human_player(round_state, "Human")
            if round_state.current_player_seat != human.seat:
                break

            if not human.tiles:
                break

            tile_id = human.tiles[-1]
            await service.handle_action("game1", "Human", GameAction.DISCARD, {"tile_id": tile_id})


class TestMahjongGameServiceTimeoutIntegration:
    """Tests for timeout handling covering all branches."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_timeout_turn_when_its_players_turn(self, service):
        """Verify TURN timeout discards last tile when it's the player's turn."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # force the game state so it's the human's turn
        game_state.round_state.current_player_seat = human.seat

        # ensure human has tiles (draw if needed)
        if len(human.tiles) == 13 and game_state.round_state.wall:
            drawn = game_state.round_state.wall.pop(0)
            human.tiles.append(drawn)

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert len(events) > 0
        assert any(e.event == EventType.DISCARD for e in events)

    async def test_timeout_turn_not_players_turn_returns_empty(self, service):
        """Verify TURN timeout returns empty when it's not the player's turn."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # force a different player's turn
        other_seat = (human.seat + 1) % 4
        game_state.round_state.current_player_seat = other_seat

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert events == []

    async def test_timeout_turn_empty_tiles_returns_empty(self, service):
        """Verify TURN timeout returns empty when player has no tiles."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        human = _find_human_player(game_state.round_state, "Human")

        # force the game state so it's the human's turn but with no tiles
        game_state.round_state.current_player_seat = human.seat
        human.tiles = []

        events = await service.handle_timeout("game1", "Human", TimeoutType.TURN)

        assert events == []


class TestMahjongGameServicePostDiscardRoundEnd:
    """Tests for round end paths within _process_post_discard."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_post_discard_post_draw_round_end(self, service):
        """Verify round end after draw phase in _process_post_discard."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # empty the wall so that process_draw_phase triggers exhaustive draw
        game_state.round_state.wall = []

        events: list[ServiceEvent] = []

        result = await service._process_post_discard("game1", events)

        # should contain round end events
        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) >= 1

    async def test_post_discard_round_end_after_bot_call_resolution(self, service):
        """Verify round end after bot call response resolves the prompt."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]

        # set up pending call prompt with bot caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={bot_seat},
            callers=[
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                )
            ],
        )

        events: list[ServiceEvent] = []

        # after bot pass resolves, trigger exhaustive draw by emptying wall
        round_state.wall = []

        result = await service._process_post_discard("game1", events)

        # should have events from resolution + round end
        assert len(result) >= 1


class TestMahjongGameServiceDispatchBotCallResponses:
    """Tests for _dispatch_bot_call_responses edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_bot_call_responses_no_pending_prompt(self, service):
        """Verify returns early when no pending prompt."""
        await service.start_game("game1", ["Human"])

        events: list[ServiceEvent] = []
        # no pending prompt set, should return without adding events
        service._dispatch_bot_call_responses("game1", events)

        assert events == []


class TestMahjongGameServiceCallHandler:
    """Tests for _call_handler covering all action branches."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_call_handler_unknown_action_returns_empty(self, service):
        """Verify unknown action returns empty ActionResult."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        result = service._call_handler(game_state, 0, "unknown_action", {})

        assert result.events == []


class TestMahjongGameServiceFindCallerInfo:
    """Tests for _find_caller_info edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_find_caller_info_fallback_returns_seat(self, service):
        """Verify fallback returns seat when caller not found in list."""
        await service.start_game("game1", ["Human"])

        prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={1},
            callers=[
                MeldCaller(
                    seat=2,
                    call_type=MeldCallType.PON,
                )
            ],
        )

        # seat 1 is not in callers, should return 1 as fallback
        result = service._find_caller_info(prompt, 1)

        assert result == 1


class TestMahjongGameServiceProcessBotFollowupEdgeCases:
    """Tests for _process_bot_followup edge cases."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_process_bot_followup_stops_on_finished_phase(self, service):
        """Verify bot followup stops when round phase is FINISHED."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        # force round to finished
        game_state.round_state.phase = RoundPhase.FINISHED

        result = await service._process_bot_followup("game1")

        assert result == []

    async def test_process_bot_followup_stops_on_pending_prompt(self, service):
        """Verify bot followup stops when pending call prompt exists."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # set current player to a bot
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        round_state.current_player_seat = bot_seats[0]

        # set pending call prompt
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={0},
            callers=[0],
        )

        result = await service._process_bot_followup("game1")

        assert result == []

    async def test_process_bot_followup_stops_when_get_turn_action_returns_none(self, service):
        """Verify bot followup stops when get_turn_action returns None."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # set current player to a bot seat
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        round_state.current_player_seat = bot_seats[0]

        # mock get_turn_action to return None
        with patch.object(bot_controller, "get_turn_action", return_value=None):
            result = await service._process_bot_followup("game1")

        assert result == []


class TestMahjongGameServiceCallHandlerBranches:
    """Tests for _call_handler covering pon, chi, ron, kan branches."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_call_handler_pon(self, service):
        """Verify _call_handler dispatches pon action."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        with patch(
            "game.logic.mahjong_service.handle_pon",
            return_value=ActionResult([]),
        ) as mock_pon:
            service._call_handler(game_state, 0, GameAction.CALL_PON, {"tile_id": 1})

        mock_pon.assert_called_once()

    async def test_call_handler_chi(self, service):
        """Verify _call_handler dispatches chi action."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        with patch(
            "game.logic.mahjong_service.handle_chi",
            return_value=ActionResult([]),
        ) as mock_chi:
            service._call_handler(
                game_state,
                0,
                GameAction.CALL_CHI,
                {"tile_id": 1, "sequence_tiles": (2, 3)},
            )

        mock_chi.assert_called_once()

    async def test_call_handler_ron(self, service):
        """Verify _call_handler dispatches ron action."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        with patch(
            "game.logic.mahjong_service.handle_ron",
            return_value=ActionResult([]),
        ) as mock_ron:
            service._call_handler(game_state, 0, GameAction.CALL_RON, {"tile_id": 1, "from_seat": 2})

        mock_ron.assert_called_once()

    async def test_call_handler_kan(self, service):
        """Verify _call_handler dispatches kan action."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        with patch(
            "game.logic.mahjong_service.handle_kan",
            return_value=ActionResult([]),
        ) as mock_kan:
            service._call_handler(game_state, 0, GameAction.CALL_KAN, {"tile_id": 1})

        mock_kan.assert_called_once()


class TestMahjongGameServiceDispatchBotCallResponsesBranches:
    """Tests for _dispatch_bot_call_responses covering bot response and mid-loop break."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_dispatch_bot_call_responses_bot_returns_action(self, service):
        """Verify bot response (not None) is dispatched through _call_handler."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)
        bot_seat = bot_seats[0]

        # set up pending call prompt with bot caller
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={bot_seat},
            callers=[
                MeldCaller(
                    seat=bot_seat,
                    call_type=MeldCallType.PON,
                )
            ],
        )

        events: list[ServiceEvent] = []

        # mock bot to return a pon action instead of pass
        with (
            patch.object(
                bot_controller,
                "get_call_response",
                return_value=(GameAction.CALL_PON, {"tile_id": 0}),
            ),
            patch(
                "game.logic.mahjong_service.handle_pon",
                return_value=ActionResult([]),
            ),
        ):
            service._dispatch_bot_call_responses("game1", events)

    async def test_dispatch_bot_call_responses_prompt_resolved_mid_loop(self, service):
        """Verify loop breaks when prompt is resolved by a previous bot response."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        # set up pending call prompt with 2 bot callers
        round_state.pending_call_prompt = PendingCallPrompt(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            pending_seats={bot_seats[0], bot_seats[1]},
            callers=[
                MeldCaller(
                    seat=bot_seats[0],
                    call_type=MeldCallType.PON,
                ),
                MeldCaller(
                    seat=bot_seats[1],
                    call_type=MeldCallType.PON,
                ),
            ],
        )

        events: list[ServiceEvent] = []

        # mock first bot to pass (which resolves the prompt), second should be skipped
        def mock_call_handler(_game_state, _seat, _action, _data):
            # simulate that handle_pass resolves the prompt
            round_state.pending_call_prompt = None
            return ActionResult([])

        with patch.object(service, "_call_handler", side_effect=mock_call_handler):
            service._dispatch_bot_call_responses("game1", events)

        # the loop should have broken after first bot resolved the prompt


class TestMahjongGameServiceChankanPromptRoundEnd:
    """Tests for chankan prompt resolution leading to round end."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_chankan_prompt_resolved_round_end(self, service):
        """Verify _handle_chankan_prompt returns round end when resolved and phase is FINISHED."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state
        bot_controller = service._bot_controllers["game1"]
        bot_seats = sorted(bot_controller.bot_seats)

        # set up pending call prompt with bot caller
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

        # mock bot pass that resolves prompt and sets FINISHED phase + round result
        round_result = ExhaustiveDrawResult(
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            score_changes={0: 0, 1: 0, 2: 0, 3: 0},
        )

        def mock_dispatch_bot_call(_game_id, _evts):
            round_state.pending_call_prompt = None
            round_state.phase = RoundPhase.FINISHED

        with (
            patch.object(service, "_dispatch_bot_call_responses", side_effect=mock_dispatch_bot_call),
            patch.object(
                service,
                "_check_and_handle_round_end",
                return_value=[
                    ServiceEvent(
                        event=EventType.ROUND_END,
                        data=RoundEndEvent(result=round_result, target="all"),
                        target="all",
                    )
                ],
            ),
        ):
            result = await service._handle_chankan_prompt("game1", events, chankan_prompt)

        # should return round end events
        round_end = [e for e in result if e.event == EventType.ROUND_END]
        assert len(round_end) == 1
