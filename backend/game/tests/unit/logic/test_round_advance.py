from typing import TYPE_CHECKING

import pytest

from game.logic.decision import Discard
from game.logic.enums import RoundPhase
from game.logic.events import EventType, GameEndedEvent, RoundStartedEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.refusal import Refusal, RefusalCode, RefusalKind
from game.logic.service import Dealt, GameOver, RoundOver, Turn
from game.tests.helpers.builders import start_game_in_play
from game.tests.unit.logic.helpers import _update_player, _update_round_state

if TYPE_CHECKING:
    from game.logic.events import GameEvent
    from game.logic.runtime import GameRuntime

FOUR_PLAYERS = ["Alice", "Bob", "Charlie", "Dave"]


def _exhaust_the_wall(service: MahjongGameService, runtime: GameRuntime) -> list[GameEvent]:
    current_seat = runtime.state.round_state.current_player_seat
    wall = runtime.state.round_state.wall
    _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": ()}))
    drawn_tile = runtime.state.round_state.players[current_seat].tiles[-1]
    events = service.act(runtime, current_seat, Discard(tile=drawn_tile))
    assert not isinstance(events, Refusal), events
    return events


class TestRoundOver:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_deal_next_round__when_the_round_is_over__should_deal_it_for_begin_round_to_draw(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        _exhaust_the_wall(service, runtime)
        assert service.get_awaiting(runtime) == RoundOver()

        dealt = service.deal_next_round(runtime)
        assert [type(e) for e in dealt] == [RoundStartedEvent] * 4
        assert service.get_awaiting(runtime) == Dealt()
        assert (runtime.state.round_number, runtime.state.round_state.result) == (1, None)

        begun = service.begin_round(runtime)
        dealer = runtime.state.round_state.dealer_seat
        others = [seat for seat in range(4) if seat != dealer]
        assert [(e.type, e.target.seat) for e in begun] == [
            (EventType.DRAW, dealer),
            *((EventType.DRAW_NOTICE, seat) for seat in others),
        ]
        assert service.get_awaiting(runtime) == Turn(seat=dealer)

    def test_act__when_the_round_is_over__should_refuse_it_as_the_wrong_phase(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        _exhaust_the_wall(service, runtime)
        assert runtime.state.round_state.phase == RoundPhase.FINISHED
        seat = runtime.state.round_state.current_player_seat
        tile_id = runtime.state.round_state.players[seat].tiles[0]

        refusal = service.act(runtime, seat, Discard(tile=tile_id))
        assert refusal == Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.WRONG_PHASE)

    def test_round_end__when_the_game_ends__should_await_nothing(self, service):
        runtime = start_game_in_play(service, seed="a" * 192).runtime
        busted_seat = (runtime.state.round_state.current_player_seat + 1) % 4
        _update_player(runtime, seat=busted_seat, score=-1000)

        ended = _exhaust_the_wall(service, runtime)
        assert [type(e) for e in ended if isinstance(e, GameEndedEvent)] == [GameEndedEvent]
        assert service.get_awaiting(runtime) == GameOver()
