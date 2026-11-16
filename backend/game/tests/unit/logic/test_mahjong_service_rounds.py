import pytest

from game.logic.decision import Discard
from game.logic.events import (
    EventType,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.runtime import GameRuntime
from game.logic.service import Call, GameOver, RoundOver
from game.logic.tiles import tile_to_34
from game.logic.types import (
    ExhaustiveDrawResult,
)
from game.logic.win import get_waiting_tiles
from game.tests.helpers.builders import (
    answer_with_defaults,
    create_dealt_game_state,
    create_player,
    start_game_in_play,
)
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_wall
from game.tests.unit.logic.helpers import (
    _first_human,
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
    runtime = GameRuntime(state=create_dealt_game_state(players, seed="a" * 192))
    if live_tiles is not None:
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:live_tiles]}))

    assert get_waiting_tiles(players[1]) == {tile_to_34(_DEALER_LAST_DISCARD)}
    return runtime


class TestMahjongGameServiceAfterDiscardRoundEnd:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_the_callers_pass_ron_on_the_last_discard__should_handle_the_exhaustive_draw(self, service):
        runtime = _dealer_before_ronnable_discard(live_tiles=0)

        discarded = service.act(runtime, 0, Discard(tile=_DEALER_LAST_DISCARD))
        assert [e.type for e in discarded if e.type in (EventType.CALL_PROMPT, EventType.ROUND_END)] == [
            EventType.CALL_PROMPT,
        ]
        assert service.get_awaiting(runtime) == Call(seats=frozenset({1}))

        answered = answer_with_defaults(service, runtime, seats=frozenset({1, 2, 3}))
        round_end = next(e for e in answered if e.type == EventType.ROUND_END)
        assert isinstance(round_end.result, ExhaustiveDrawResult)
        assert round_end.result.tempai_seats == [1]
        assert service.build_reconnection_snapshot(runtime, 0).latest_discard_seat == 0
        assert service.get_awaiting(runtime) == RoundOver()


class TestGameEndAwaiting:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_discard_ends_game__should_return_game_end_and_await_nothing(self, service):
        runtime = start_game_in_play(service, humans=1, seed="a" * 192).runtime
        game_state = runtime.state
        player = _first_human(game_state)

        for seat in range(4):
            _update_player(runtime, seat=seat, score=-10000)

        _update_round_state(
            runtime,
            current_player_seat=player.seat,
            wall=make_wall(),
        )

        game_state = runtime.state
        player = _first_human(game_state)
        tiles = list(player.tiles)
        if len(tiles) < 14:
            tiles.append(0)

        _update_player(runtime, seat=player.seat, tiles=tuple(tiles[:14]))
        game_state = runtime.state
        player = _first_human(game_state)
        tile_id = player.tiles[-1]

        events = service.act(runtime, player.seat, Discard(tile=tile_id))
        game_end_events = [e for e in events if e.type == EventType.GAME_END]
        assert len(game_end_events) == 1
        assert service.get_awaiting(runtime) == GameOver()
