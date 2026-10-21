from mahjong.tile import TilesConverter

from game.logic.enums import RoundPhase
from game.logic.events import DoraRevealedEvent
from game.logic.turn import emit_deferred_dora_events
from game.tests.conftest import create_player, create_round_state


def _default_round_state(pending_dora_count: int = 0):
    wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
    dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
    all_tiles = TilesConverter.string_to_136_array(man="123456789", pin="111")
    players = tuple(
        create_player(
            seat=i,
            tiles=tuple(all_tiles[i * 3 : (i + 1) * 3 + 10]),
        )
        for i in range(4)
    )
    return create_round_state(
        players=players,
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=(dead_wall[2],),
        pending_dora_count=pending_dora_count,
        phase=RoundPhase.PLAYING,
    )


class TestEmitDeferredDoraEventsImmutable:
    def test_emit_deferred_dora_events__when_one_dora_pending__should_reveal_one_indicator(self):
        round_state = _default_round_state(pending_dora_count=1)
        initial_dora_count = len(round_state.wall.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.wall.dora_indicators) == initial_dora_count + 1
        assert new_state.wall.pending_dora_count == 0
        assert len(events) == 1
        assert isinstance(events[0], DoraRevealedEvent)
        # original state unchanged
        assert len(round_state.wall.dora_indicators) == initial_dora_count
        assert round_state.wall.pending_dora_count == 1

    def test_emit_deferred_dora_events__when_no_dora_pending__should_emit_nothing(self):
        round_state = _default_round_state(pending_dora_count=0)

        new_state, events = emit_deferred_dora_events(round_state)

        assert new_state.wall.dora_indicators == round_state.wall.dora_indicators
        assert len(events) == 0

    def test_emit_deferred_dora_events__when_two_dora_pending__should_reveal_two_indicators(self):
        round_state = _default_round_state(pending_dora_count=2)
        initial_dora_count = len(round_state.wall.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.wall.dora_indicators) == initial_dora_count + 2
        assert new_state.wall.pending_dora_count == 0
        assert len(events) == 2
        assert all(isinstance(e, DoraRevealedEvent) for e in events)
