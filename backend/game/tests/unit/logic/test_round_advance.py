from typing import TYPE_CHECKING

import pytest

from game.logic.enums import GameAction, GameErrorCode, RoundPhase, WaitKind
from game.logic.events import ErrorEvent, EventType, GameEndedEvent, RoundStartedEvent
from game.logic.mahjong_service import MahjongGameService
from game.tests.helpers.builders import start_game_in_play
from game.tests.unit.logic.helpers import _update_player, _update_round_state

if TYPE_CHECKING:
    from game.logic.runtime import GameRuntime
    from game.logic.service import GameUpdate

FOUR_PLAYERS = ["Alice", "Bob", "Charlie", "Dave"]


def _exhaust_the_wall(service: MahjongGameService, runtime: GameRuntime) -> GameUpdate:
    current_seat = runtime.state.round_state.current_player_seat
    wall = runtime.state.round_state.wall
    _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
    drawn_tile = runtime.state.round_state.players[current_seat].tiles[-1]
    return service.handle_action(runtime, seat=current_seat, action=GameAction.DISCARD, data={"tile_id": drawn_tile})


class TestRoundOver:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_deal_next_round__when_the_round_is_over__should_deal_it_for_begin_round_to_draw(self, service):
        runtime = start_game_in_play(service, "game1", FOUR_PLAYERS, seed="a" * 192).runtime
        ended = _exhaust_the_wall(service, runtime)
        assert (ended.awaiting.kind, ended.awaiting.seats, ended.awaiting.round_number) == (
            WaitKind.ROUND_OVER,
            frozenset(),
            0,
        )

        dealt = service.deal_next_round(runtime)
        assert [type(e) for e in dealt.events] == [RoundStartedEvent] * 4
        assert (dealt.awaiting.kind, dealt.awaiting.seats, dealt.awaiting.round_number) == (
            WaitKind.DEALT,
            frozenset(),
            1,
        )
        assert runtime.state.round_state.result is None

        begun = service.begin_round(runtime)
        dealer = runtime.state.round_state.dealer_seat
        assert [(e.type, e.target.seat) for e in begun.events] == [(EventType.DRAW, dealer)]
        assert (begun.awaiting.kind, begun.awaiting.seats) == (WaitKind.TURN, frozenset({dealer}))

    @pytest.mark.parametrize(
        ("phase_call", "message"),
        [
            pytest.param(MahjongGameService.begin_round, "no dealt round to begin", id="begin_round"),
            pytest.param(MahjongGameService.deal_next_round, "no round over to deal", id="deal_next_round"),
        ],
    )
    def test_phase_call__when_the_game_waits_on_a_turn__should_raise(self, service, phase_call, message):
        runtime = start_game_in_play(service, "game1", FOUR_PLAYERS, seed="a" * 192).runtime
        state_before = runtime.state

        with pytest.raises(AssertionError, match=message):
            phase_call(service, runtime)
        assert runtime.state is state_before

    def test_handle_action__when_the_round_is_over__should_return_invalid_action_error(self, service):
        runtime = start_game_in_play(service, "game1", FOUR_PLAYERS, seed="a" * 192).runtime
        _exhaust_the_wall(service, runtime)
        assert runtime.state.round_state.phase == RoundPhase.FINISHED
        seat = runtime.state.round_state.current_player_seat
        tile_id = runtime.state.round_state.players[seat].tiles[0]

        events = service.handle_action(runtime, seat=seat, action=GameAction.DISCARD, data={"tile_id": tile_id}).events
        assert [(type(e), e.code) for e in events] == [(ErrorEvent, GameErrorCode.INVALID_ACTION)]
        assert "not in progress" in events[0].message

    def test_round_end__when_the_game_ends__should_await_nothing(self, service):
        runtime = start_game_in_play(service, "game1", FOUR_PLAYERS, seed="a" * 192).runtime
        busted_seat = (runtime.state.round_state.current_player_seat + 1) % 4
        _update_player(runtime, seat=busted_seat, score=-1000)

        ended = _exhaust_the_wall(service, runtime)
        assert [type(e) for e in ended.events if isinstance(e, GameEndedEvent)] == [GameEndedEvent]
        assert (ended.awaiting.kind, ended.awaiting.seats) == (WaitKind.NONE, frozenset())
