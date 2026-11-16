from unittest.mock import patch

import pytest

from game.logic.action_handlers import handle_discard
from game.logic.action_result import ActionResult
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.decision import Discard
from game.logic.enums import CallType, MeldCallType, PromptKind, WaitKind
from game.logic.events import (
    BroadcastTarget,
    CallPromptEvent,
    EventType,
    SeatTarget,
)
from game.logic.exceptions import GeneratedActionError
from game.logic.mahjong_service import MahjongGameService
from game.logic.runtime import GameRuntime
from game.logic.service import Awaiting
from game.logic.state import Caller, MeldOption, PendingCallPrompt
from game.logic.tiles import tile_to_34
from game.logic.types import (
    ExhaustiveDrawResult,
)
from game.logic.win import get_waiting_tiles
from game.tests.helpers.builders import create_dealt_game_state, create_player, start_game_in_play
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_wall
from game.tests.unit.logic.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)

_DEALER_LAST_DISCARD = tile_copies(3, pin="3")[0]


def _dealer_before_ronnable_discard(*, live_tiles: int | None = None) -> GameRuntime:
    players = (
        create_player(seat=0, tiles=(_DEALER_LAST_DISCARD, *tile_copies(0, sou="123456789", honors="1234"))),
        create_player(seat=1, tiles=tile_copies(0, man="123456789", pin="1255")),
        create_player(seat=2, tiles=(*tile_copies(0, pin="3"), *tile_copies(1, sou="123456789", honors="123"))),
        create_player(seat=3, tiles=(*tile_copies(1, pin="33"), *tile_copies(2, sou="123456789", honors="12"))),
    )
    runtime = GameRuntime(
        game_id="game1",
        state=create_dealt_game_state(players, seed="a" * 192),
        ai=AIPlayerController({seat: AIPlayer() for seat in range(1, 4)}),
    )
    if live_tiles is not None:
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:live_tiles]}))

    assert get_waiting_tiles(players[1]) == {tile_to_34(_DEALER_LAST_DISCARD)}
    return runtime


def _dealer_discard(runtime: GameRuntime) -> ActionResult:
    result = handle_discard(runtime.state, seat=0, action=Discard(tile=_DEALER_LAST_DISCARD))
    assert isinstance(result, ActionResult)
    runtime.commit(result.state)
    return result


class TestMahjongGameServiceAfterDiscard:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_process_action_result__when_discard_prompt_waits_for_human_player__should_return_its_events(self, service):
        runtime = start_game_in_play(service, "game1", ["Player"], seed="a" * 192).runtime
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


class TestMahjongGameServiceAfterDiscardRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_ai_passes_ron_on_the_last_discard__should_handle_the_exhaustive_draw(self, service):
        runtime = _dealer_before_ronnable_discard(live_tiles=0)

        update = service.act(runtime, 0, Discard(tile=_DEALER_LAST_DISCARD))
        assert [e.type for e in update.events if e.type in (EventType.CALL_PROMPT, EventType.ROUND_END)] == [
            EventType.CALL_PROMPT,
            EventType.ROUND_END,
        ]
        round_end = next(e for e in update.events if e.type == EventType.ROUND_END)
        assert isinstance(round_end.result, ExhaustiveDrawResult)
        assert round_end.result.tempai_seats == [1]
        assert service.build_reconnection_snapshot(runtime, 0).latest_discard_seat == 0
        assert (update.awaiting.kind, update.awaiting.seats) == (WaitKind.ROUND_OVER, frozenset())
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
            service.act(runtime, 0, Discard(tile=tsumogiri))


class TestGameEndAwaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_discard_ends_game__should_return_game_end_and_await_nothing(self, service):
        runtime = start_game_in_play(service, "game1", ["Player"], seed="a" * 192).runtime
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
        update = service.act(runtime, player.seat, Discard(tile=tile_id))
        game_end_events = [e for e in update.events if e.type == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert update.awaiting == Awaiting(kind=WaitKind.NONE, seats=frozenset(), round_number=waiting.round_number)
