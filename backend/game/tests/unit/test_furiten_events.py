import pytest

from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import GameAction, RoundPhase
from game.logic.events import EventType, FuritenEvent, SeatTarget, ServiceEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.runtime import GameRuntime
from game.logic.state import Discard
from game.logic.tiles import NUM_TILES, tile_to_34
from game.logic.wall import DEAD_WALL_SIZE
from game.logic.win import get_waiting_tiles
from game.tests.conftest import create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import (
    _find_player,
    _update_player,
    _update_round_state,
)

WAITING_SEAT = 1
THREE_MAN_WAIT = tile_copies(0, man="3")[0]
SIX_MAN_WAIT = tile_copies(0, man="6")[0]
WAITING_SEAT_FOUR_MAN = tile_copies(0, man="4")[0]
WAITING_SEAT_PIN_CHI_PAIR = (tile_copies(0, pin="1")[0], tile_copies(0, pin="2")[0])
WAITING_SEAT_MAN_CHI_PAIR = (WAITING_SEAT_FOUR_MAN, tile_copies(0, man="5")[0])
WAITING_SEAT_HAKU = tile_copies(3, honors="5")[0]
DEALER_THREE_MAN = tile_copies(1, man="3")[0]
DEALER_EAST = tile_copies(1, honors="1")[0]
DEALER_THREE_PIN = tile_copies(3, pin="3")[0]
SEVEN_MAN = tile_copies(0, man="7")[0]
CHUN = tile_copies(3, honors="7")[0]


def _next_seat_after_dealer(runtime: GameRuntime) -> int:
    return (runtime.state.round_state.dealer_seat + 1) % 4


def _waiting_seat_runtime(
    *, waiting_seat_draw: int, waiting_seat_discard: Discard, is_riichi: bool = False
) -> GameRuntime:
    players = (
        create_player(
            seat=0,
            tiles=(
                DEALER_THREE_PIN,
                *tile_copies(1, honors="1234567"),
                *tile_copies(2, honors="12"),
                *tile_copies(3, sou="246"),
                DEALER_THREE_MAN,
            ),
            discards=(Discard(tile_id=tile_copies(2, honors="7")[0]),),
        ),
        create_player(
            seat=WAITING_SEAT,
            tiles=tile_copies(0, pin="123456789", sou="11", man="45"),
            discards=(waiting_seat_discard,),
            is_riichi=is_riichi,
        ),
        create_player(
            seat=2,
            tiles=tile_copies(1, pin="123456789", sou="2468"),
            discards=(Discard(tile_id=tile_copies(1, sou="9")[0]),),
        ),
        create_player(
            seat=3,
            tiles=tile_copies(2, pin="123456789", sou="3579"),
            discards=(Discard(tile_id=tile_copies(2, sou="1")[0]),),
        ),
    )
    all_discards = tuple(player.discards[0].tile_id for player in players)
    dealt = {tile for player in players for tile in player.tiles} | set(all_discards)
    undealt = [tile for tile in range(NUM_TILES) if tile not in dealt and tile != waiting_seat_draw]
    round_state = create_round_state(
        players=players,
        wall=(waiting_seat_draw, *undealt[:-DEAD_WALL_SIZE]),
        dead_wall=undealt[-DEAD_WALL_SIZE:],
        phase=RoundPhase.PLAYING,
        all_discards=all_discards,
    )
    assert get_waiting_tiles(round_state.players[WAITING_SEAT]) == {
        tile_to_34(THREE_MAN_WAIT),
        tile_to_34(SIX_MAN_WAIT),
    }
    return GameRuntime(game_id="game1", state=create_game_state(round_state), ai=AIPlayerController({}))


def _discard_furiten_runtime(*, waiting_seat_draw: int) -> GameRuntime:
    runtime = _waiting_seat_runtime(
        waiting_seat_draw=waiting_seat_draw, waiting_seat_discard=Discard(tile_id=THREE_MAN_WAIT)
    )
    assert [e.data for e in runtime.furiten.check_changes(runtime.state.round_state)] == [
        FuritenEvent(is_furiten=True, target=SeatTarget(seat=WAITING_SEAT)),
    ]
    return runtime


def _furiten_events(events: list[ServiceEvent]) -> list[FuritenEvent]:
    return [e.data for e in events if isinstance(e.data, FuritenEvent)]


class TestCheckFuritenChanges:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_check_furiten_changes__when_state_unchanged__should_emit_nothing(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state

        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 0

    def test_check_furiten_changes__when_temporary_furiten_starts__should_emit_furiten_event(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        waiting_seat = _next_seat_after_dealer(runtime)
        _update_player(runtime, seat=waiting_seat, is_temporary_furiten=True)

        game_state = runtime.state
        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 1
        assert events[0].event == EventType.FURITEN
        assert isinstance(events[0].data, FuritenEvent)
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=waiting_seat)

    def test_check_furiten_changes__when_furiten_clears__should_emit_event_with_false(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        waiting_seat = _next_seat_after_dealer(runtime)

        runtime.furiten._state[waiting_seat] = True
        _update_player(runtime, seat=waiting_seat, is_temporary_furiten=False)

        game_state = runtime.state
        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 1
        assert events[0].data.is_furiten is False

    def test_check_furiten_changes__when_called_twice__should_emit_once(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        waiting_seat = _next_seat_after_dealer(runtime)

        _update_player(runtime, seat=waiting_seat, is_temporary_furiten=True)
        game_state = runtime.state
        events1 = runtime.furiten.check_changes(game_state.round_state)
        assert len(events1) == 1

        events2 = runtime.furiten.check_changes(game_state.round_state)
        assert len(events2) == 0

    def test_check_furiten_changes__when_one_player_changes__should_target_only_that_seat(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        _update_player(runtime, seat=1, is_temporary_furiten=True)

        game_state = runtime.state
        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 1
        assert events[0].target == SeatTarget(seat=1)

    def test_check_furiten_changes__when_round_finished__should_emit_nothing(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        _update_round_state(runtime, phase=RoundPhase.FINISHED)
        _update_player(runtime, seat=0, is_temporary_furiten=True)

        game_state = runtime.state
        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 0

    def test_check_furiten_changes__when_riichi_furiten_starts__should_emit_furiten_event(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        _update_player(runtime, seat=2, is_riichi_furiten=True)

        game_state = runtime.state
        events = runtime.furiten.check_changes(game_state.round_state)
        assert len(events) == 1
        assert events[0].data.is_furiten is True
        assert events[0].target == SeatTarget(seat=2)


class TestFuritenEventsInGameFlow:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_furiten_events__when_action_changes_furiten__should_emit_event_to_player(self, service):
        runtime = service.start_game("game1", ["Player"], seed="a" * 192).runtime
        game_state = runtime.state
        player = _find_player(game_state.round_state, "Player")
        assert game_state.round_state.current_player_seat == player.seat

        # Pretend the server previously told the client they were in furiten.
        # When handle_action runs and computes furiten=False (the actual state),
        # _append_furiten_changes will detect the True->False transition.
        runtime.furiten._state[player.seat] = True
        tile_id = player.tiles[-1]
        events = service.handle_action(
            runtime, seat=player.seat, action=GameAction.DISCARD, data={"tile_id": tile_id}
        ).events
        furiten_events = [e for e in events if e.event == EventType.FURITEN and isinstance(e.data, FuritenEvent)]
        assert len(furiten_events) == 1
        assert furiten_events[0].data.is_furiten is False
        assert furiten_events[0].target == SeatTarget(seat=player.seat)

    def test_furiten_events__when_game_starts__should_emit_none(self, service):
        events = service.start_game("game1", ["Player"], seed="a" * 192).events
        furiten_events = [e for e in events if e.event == EventType.FURITEN]
        assert len(furiten_events) == 0

    def test_furiten_events__when_discard_waiting_seat_draws__should_keep_furiten_through_its_turn(self, service):
        runtime = _discard_furiten_runtime(waiting_seat_draw=CHUN)

        drawn = service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": DEALER_EAST})
        assert runtime.state.round_state.current_player_seat == WAITING_SEAT
        assert runtime.state.round_state.players[WAITING_SEAT].tiles[-1] == CHUN
        assert _furiten_events(drawn.events) == []
        assert service.build_reconnection_snapshot(runtime, WAITING_SEAT).is_furiten is True
        assert service.build_reconnection_snapshot(runtime, 0).is_furiten is False

        discarded = service.handle_action(runtime, seat=WAITING_SEAT, action=GameAction.DISCARD, data={"tile_id": CHUN})
        assert _furiten_events(discarded.events) == []
        assert service.build_reconnection_snapshot(runtime, WAITING_SEAT).is_furiten is True

    def test_furiten_events__when_discard_furiten_seat_calls_chi__should_keep_furiten_through_its_meld_turn(
        self, service
    ):
        runtime = _discard_furiten_runtime(waiting_seat_draw=CHUN)

        prompted = service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": DEALER_THREE_PIN})
        prompt = runtime.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.pending_seats == frozenset({WAITING_SEAT})
        assert _furiten_events(prompted.events) == []

        called = service.handle_action(
            runtime,
            seat=WAITING_SEAT,
            action=GameAction.CALL_CHI,
            data={"tile_id": DEALER_THREE_PIN, "sequence_tiles": WAITING_SEAT_PIN_CHI_PAIR},
        )
        assert runtime.state.round_state.is_after_meld_call is True
        assert runtime.state.round_state.current_player_seat == WAITING_SEAT
        assert _furiten_events(called.events) == []
        assert service.build_reconnection_snapshot(runtime, WAITING_SEAT).is_furiten is True

    def test_furiten_events__when_own_discard_drops_the_discarded_wait__should_clear_furiten(self, service):
        runtime = _discard_furiten_runtime(waiting_seat_draw=SEVEN_MAN)
        service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": DEALER_EAST})

        discarded = service.handle_action(
            runtime, seat=WAITING_SEAT, action=GameAction.DISCARD, data={"tile_id": WAITING_SEAT_FOUR_MAN}
        )
        assert get_waiting_tiles(runtime.state.round_state.players[WAITING_SEAT]) == {tile_to_34(SIX_MAN_WAIT)}
        assert _furiten_events(discarded.events) == [
            FuritenEvent(is_furiten=False, target=SeatTarget(seat=WAITING_SEAT))
        ]
        assert service.build_reconnection_snapshot(runtime, WAITING_SEAT).is_furiten is False

    @pytest.mark.parametrize(
        ("is_riichi", "response", "response_data"),
        [
            (False, GameAction.PASS, {}),
            (True, GameAction.PASS, {}),
            (False, GameAction.CALL_CHI, {"tile_id": DEALER_THREE_MAN, "sequence_tiles": WAITING_SEAT_MAN_CHI_PAIR}),
        ],
    )
    def test_furiten_events__when_seat_declines_ron_then_takes_its_turn__should_show_furiten_through_the_turn(
        self, service, is_riichi, response, response_data
    ):
        runtime = _waiting_seat_runtime(
            waiting_seat_draw=CHUN,
            waiting_seat_discard=Discard(tile_id=WAITING_SEAT_HAKU, is_riichi_discard=is_riichi),
            is_riichi=is_riichi,
        )
        assert runtime.furiten.check_changes(runtime.state.round_state) == []

        service.handle_action(runtime, seat=0, action=GameAction.DISCARD, data={"tile_id": DEALER_THREE_MAN})
        prompt = runtime.state.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.caller(WAITING_SEAT).can_ron is True

        declined = service.handle_action(runtime, seat=WAITING_SEAT, action=response, data=response_data)
        assert runtime.state.round_state.current_player_seat == WAITING_SEAT
        assert len(runtime.state.round_state.players[WAITING_SEAT].tiles) % 3 == 2
        assert _furiten_events(declined.events) == [FuritenEvent(is_furiten=True, target=SeatTarget(seat=WAITING_SEAT))]
        assert service.build_reconnection_snapshot(runtime, WAITING_SEAT).is_furiten is True
