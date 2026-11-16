import pytest

from game.engine import (
    BroadcastTarget,
    Discard,
    EventType,
    GameStartedEvent,
    MahjongGameService,
)
from game.tests.helpers.builders import answer_with_defaults, start_game_in_play


class TestGameCreationAndJoin:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_new_game__when_one_human_plays__should_broadcast_one_game_started(self, service):
        events = start_game_in_play(service, humans=1, seed="a" * 192).events
        game_started_events = [e for e in events if e.type == EventType.GAME_STARTED]
        assert len(game_started_events) == 1
        event = game_started_events[0]
        assert isinstance(event, GameStartedEvent)
        assert event.target == BroadcastTarget()
        assert event.dealer_seat in range(4)


class TestGameServiceIntegration:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    def test_act__when_human_discards_repeatedly__should_process_multiple_discards(self, service):
        start = start_game_in_play(service, humans=1, seed="a" * 192)
        runtime = start.runtime
        human_seat = start.human_seats[0]

        actions_processed = 0
        for _ in range(10):
            game_state = runtime.state
            if game_state.round_state.result is not None:
                break

            round_state = game_state.round_state
            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]

            if current_seat == human_seat and player.tiles:
                tile_to_discard = player.tiles[-1]
                service.act(runtime, human_seat, Discard(tile=tile_to_discard))
                answer_with_defaults(service, runtime, seats=start.default_seats)
                actions_processed += 1

        assert actions_processed >= 2, "expected multiple discards to be processed"
