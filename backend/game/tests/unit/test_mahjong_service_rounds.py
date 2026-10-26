from unittest.mock import patch

import pytest

from game.logic.action_handlers import handle_discard
from game.logic.action_result import ActionResult
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import CallType, GameAction, MeldCallType, PromptKind, RoundPhase, TimeoutType, WaitKind
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    DiscardEvent,
    ErrorEvent,
    EventType,
    RoundEndEvent,
    SeatTarget,
)
from game.logic.exceptions import GeneratedActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.runtime import GameRuntime
from game.logic.service import Awaiting
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.types import (
    DiscardActionData,
    ExhaustiveDrawResult,
    TenpaiHand,
)
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_wall
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)

_DEALER_LAST_DISCARD = tile_copies(3, pin="3")[0]


def _dealer_before_ronnable_discard(*, human_seat: int = 0, live_tiles: int | None = None) -> GameRuntime:
    players = (
        create_player(seat=0, tiles=(_DEALER_LAST_DISCARD, *tile_copies(0, sou="123456789", honors="1234"))),
        create_player(seat=1, tiles=tile_copies(0, man="123456789", pin="1255")),
        create_player(seat=2, tiles=(*tile_copies(0, pin="3"), *tile_copies(1, sou="123456789", honors="123"))),
        create_player(seat=3, tiles=(*tile_copies(1, pin="33"), *tile_copies(2, sou="123456789", honors="12"))),
    )
    runtime = GameRuntime(
        game_id="game1",
        state=create_dealt_game_state(players, seed="a" * 192),
        ai=AIPlayerController({seat: AIPlayer() for seat in range(4) if seat != human_seat}),
    )
    if live_tiles is not None:
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:live_tiles]}))

    assert get_waiting_tiles(players[1]) == {tile_to_34(_DEALER_LAST_DISCARD)}
    return runtime


def _dealer_discard(runtime: GameRuntime) -> ActionResult:
    result = handle_discard(runtime.state, seat=0, data=DiscardActionData(tile_id=_DEALER_LAST_DISCARD))
    assert isinstance(result, ActionResult)
    runtime.commit(result.state)
    return result


class TestMahjongGameServiceHandleTimeout:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_meld_timeout_without_pending_prompt__should_return_no_events(self, service):
        start = service.start_game("game1", ["Player"], seed="a" * 192)
        runtime = start.runtime
        player_seat = start.seats[0]

        events = service.handle_timeout(runtime, seat=player_seat, timeout_type=TimeoutType.MELD).events
        assert events == []

    def test_handle_timeout__when_meld_timeout_with_pending_prompt__should_pass_for_the_seat(self, service):
        runtime = _dealer_before_ronnable_discard(human_seat=3)
        service._process_action_result_internal(runtime, _dealer_discard(runtime))
        prompt = runtime.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.pending_seats == {3}

        events = service.handle_timeout(runtime, seat=3, timeout_type=TimeoutType.MELD).events
        assert (events[0].type, events[0].target) == (EventType.DRAW, SeatTarget(seat=1))
        assert not any(isinstance(e, ErrorEvent) for e in events)

    def test_handle_timeout__when_turn_timeout_and_prompt_pending_for_others__should_return_no_events(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        round_state = game_state.round_state
        player = _find_player(round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=(player.seat + 1) % 4,
            pending_seats=frozenset({(player.seat + 2) % 4}),
            callers=(Caller(seat=(player.seat + 2) % 4, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(runtime, pending_call_prompt=prompt)

        events = service.handle_timeout(runtime, seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events == []


class TestMahjongGameServiceCheckAndHandleRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_check_and_handle_round_end__when_round_finished__should_handle_it_once(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime

        round_result = ExhaustiveDrawResult(
            tempai_seats=[0],
            noten_seats=[1, 2, 3],
            tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
            scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
            score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
        )
        _update_round_state(runtime, phase=RoundPhase.FINISHED, result=round_result)
        events = [
            RoundEndEvent(result=round_result),
        ]

        result = service._check_and_handle_round_end(runtime, events)
        assert result is True
        assert [e.type for e in events] == [EventType.ROUND_END]
        assert runtime.pending_confirm is not None

        with pytest.raises(AssertionError, match="round end already handled"):
            service._check_and_handle_round_end(runtime, [])


class TestMahjongGameServiceAfterDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_discard_prompt_waits_for_human_player__should_return_its_events(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        prompt = PendingCallPrompt(
            kind=PromptKind.DISCARD,
            tile_id=0,
            from_seat=0,
            pending_seats=frozenset({player.seat}),
            callers=(Caller(seat=player.seat, melds=(MeldOption(call_type=MeldCallType.PON),)),),
        )
        _update_round_state(runtime, pending_call_prompt=prompt)

        prompt_event = CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=0,
            from_seat=0,
            callers=[player.seat],
            target=SeatTarget(seat=player.seat),
        )

        result = service._process_action_result_internal(runtime, ActionResult([prompt_event], state=runtime.state))
        assert [(e.type, e.target) for e in result] == [(EventType.CALL_PROMPT, SeatTarget(seat=player.seat))]

    def test_process_action_result__when_discard_prompt_waits_only_for_ai_player__should_answer_it_and_draw(
        self, service
    ):
        runtime = _dealer_before_ronnable_discard()

        result = service._process_action_result_internal(runtime, _dealer_discard(runtime))
        assert [(e.type, e.target) for e in result] == [
            (EventType.DISCARD, BroadcastTarget()),
            (EventType.CALL_PROMPT, SeatTarget(seat=1)),
            (EventType.CALL_PROMPT, SeatTarget(seat=3)),
            (EventType.DRAW, SeatTarget(seat=1)),
        ]
        assert runtime.state.round_state.pending_call_prompt is None


class TestMahjongGameServiceTimeoutIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_turn_timeout_on_players_turn__should_discard_tile(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        player_tiles = list(player.tiles)
        live_tiles = list(game_state.round_state.wall.live_tiles)
        if len(player_tiles) == 13 and live_tiles:
            player_tiles.append(live_tiles.pop(0))

        _update_player(runtime, seat=player.seat, tiles=tuple(player_tiles))
        new_wall = game_state.round_state.wall.model_copy(update={"live_tiles": tuple(live_tiles)})
        _update_round_state(runtime, current_player_seat=player.seat, wall=new_wall)

        events = service.handle_timeout(runtime, seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events[0] == DiscardEvent(seat=player.seat, tile_id=player_tiles[-1], is_tsumogiri=True)

    def test_handle_timeout__when_turn_timeout_off_players_turn__should_return_no_events(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        other_seat = (player.seat + 1) % 4
        _update_round_state(runtime, current_player_seat=other_seat)

        events = service.handle_timeout(runtime, seat=player.seat, timeout_type=TimeoutType.TURN).events
        assert events == []


class TestMahjongGameServiceAfterDiscardRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_ai_passes_ron_on_the_last_discard__should_handle_the_exhaustive_draw(self, service):
        runtime = _dealer_before_ronnable_discard(live_tiles=0)

        update = service.handle_action(
            runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": _DEALER_LAST_DISCARD}
        )
        assert [e.type for e in update.events if e.type in (EventType.CALL_PROMPT, EventType.ROUND_END)] == [
            EventType.CALL_PROMPT,
            EventType.ROUND_END,
        ]
        round_end = next(e for e in update.events if e.type == EventType.ROUND_END)
        assert isinstance(round_end.result, ExhaustiveDrawResult)
        assert round_end.result.tempai_seats == [1]
        assert runtime.pending_confirm is not None
        assert (update.awaiting.kind, update.awaiting.seats) == (WaitKind.ROUND_ADVANCE, frozenset({0}))
        assert service._process_ai_player_followup(runtime) == []


class TestMahjongGameServiceProcessAIPlayerFollowupEdgeCases:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_ai_player_followup__when_ai_has_no_turn_action__should_raise(self, service):
        runtime = _dealer_before_ronnable_discard()
        tsumogiri = tile_copies(0, honors="1")[0]

        with (
            patch.object(runtime.ai, "get_turn_action", return_value=None),
            pytest.raises(GeneratedActionError, match="AI seat 1 returned no turn action"),
        ):
            service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": tsumogiri})


class TestGameEndAwaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_action__when_discard_ends_game__should_return_game_end_and_await_nothing(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        for seat in range(4):
            _update_player(runtime, seat=seat, score=-10000)

        _update_round_state(
            runtime,
            current_player_seat=player.seat,
            wall=make_wall(),
        )

        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")
        tiles = list(player.tiles)
        if len(tiles) < 14:
            tiles.append(0)

        _update_player(runtime, seat=player.seat, tiles=tuple(tiles[:14]))
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")
        tile_id = player.tiles[-1]

        waiting = service.get_awaiting(runtime)
        update = service.handle_action(runtime, seat=player.seat, action=GameAction.DISCARD, data={"tile_id": tile_id})
        game_end_events = [e for e in update.events if e.type == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert update.awaiting == Awaiting(
            kind=WaitKind.NONE, seats=frozenset(), wait_id=waiting.wait_id + 1, round_number=waiting.round_number
        )


class TestTurnTimeoutKuikaeIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_handle_timeout__when_turn_timeout_with_kuikae_restriction__should_discard_tile(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")

        hand_tiles = list(player.tiles[:11])
        last_tile = hand_tiles[-1]
        kuikae_34 = tile_to_34(last_tile)

        _update_player(
            runtime,
            seat=player.seat,
            tiles=tuple(hand_tiles),
            kuikae_tiles=(kuikae_34,),
        )
        _update_round_state(runtime, current_player_seat=player.seat)

        events = service.handle_timeout(runtime, seat=player.seat, timeout_type=TimeoutType.TURN).events
        player_discard = events[0]
        assert isinstance(player_discard, DiscardEvent)
        assert player_discard.seat == player.seat
        assert tile_to_34(player_discard.tile_id) != kuikae_34
