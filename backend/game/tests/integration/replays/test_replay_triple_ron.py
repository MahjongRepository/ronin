import json

from game.logic.enums import AbortiveDrawType, GameAction
from game.logic.events import EventType, RoundEndEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.settings import NUM_PLAYERS
from game.logic.tiles import NUM_TILES
from game.logic.wall import DEAL_BLOCKS, TILES_PER_DEAL_BLOCK
from game.replay import run_replay
from game.replay.loader import load_replay_from_string
from game.replay.models import ReplayInput
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
)
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.replay_format import REPLAY_VERSION

SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")
DEALER = "Charlie"
RON_CALLERS_BY_SEAT_ORDER = ("Bob", "Alice", "Diana")
DEAL_ROUND_SIZE = TILES_PER_DEAL_BLOCK * NUM_PLAYERS
FINAL_DEAL_START = DEAL_BLOCKS * DEAL_ROUND_SIZE
DEALER_FIRST_DRAW_POSITION = FINAL_DEAL_START + NUM_PLAYERS


def _deal_positions(seat: int) -> list[int]:
    blocks = [
        position
        for block in range(DEAL_BLOCKS)
        for position in range(
            block * DEAL_ROUND_SIZE + seat * TILES_PER_DEAL_BLOCK,
            block * DEAL_ROUND_SIZE + (seat + 1) * TILES_PER_DEAL_BLOCK,
        )
    ]
    return [*blocks, FINAL_DEAL_START + seat]


def _build_pin_3_triple_ron_wall() -> tuple[int, ...]:
    hands = (PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS)
    placed = {
        position: tile
        for seat, hand in enumerate(hands)
        for position, tile in zip(_deal_positions(seat), hand, strict=True)
    }
    placed[DEALER_FIRST_DRAW_POSITION] = PIN_3_TRIPLE_RON_DISCARD
    rest = iter(tile for tile in range(NUM_TILES) if tile not in placed.values())
    return tuple(placed[position] if position in placed else next(rest) for position in range(NUM_TILES))


def test_triple_ron_replay__when_recorded_and_reloaded__should_reproduce_the_abort():
    wall = _build_pin_3_triple_ron_wall()
    service = MahjongGameService()
    start = service.start_game("triple-ron", list(PLAYERS), seed=SEED, wall=list(wall))
    runtime = start.runtime
    seat_by_player = dict(zip(PLAYERS, start.seats, strict=True))
    recorded_events = list(start.events)
    recorded_events += service.handle_action(
        runtime, seat=seat_by_player[DEALER], action=GameAction.DISCARD, data={"tile_id": PIN_3_TRIPLE_RON_DISCARD}
    ).events
    for player in RON_CALLERS_BY_SEAT_ORDER:
        recorded_events += service.handle_action(
            runtime, seat=seat_by_player[player], action=GameAction.CALL_RON, data={}
        ).events

    recorded_round_ends = [e.data for e in recorded_events if isinstance(e.data, RoundEndEvent)]
    assert len(recorded_round_ends) == 1
    assert recorded_round_ends[0].result.reason == AbortiveDrawType.TRIPLE_RON
    assert recorded_round_ends[0].result.ron_seats == [seat_by_player[p] for p in RON_CALLERS_BY_SEAT_ORDER]

    record = ReplayRecord(seed=SEED, rng_version=RNG_VERSION)
    ReplayCollector(FakeReplayStorage()).collect_events(record, recorded_events)
    loaded = load_replay_from_string("\n".join([json.dumps({"version": REPLAY_VERSION}), *record.lines]))
    assert [(e.player_name, e.action) for e in loaded.events] == [
        (DEALER, GameAction.DISCARD),
        *((player, GameAction.CALL_RON) for player in RON_CALLERS_BY_SEAT_ORDER),
    ]

    trace = run_replay(
        ReplayInput(seed=loaded.seed, player_names=loaded.player_names, wall=wall, events=loaded.events),
    )
    input_steps = [step for step in trace.steps if not step.synthetic]
    assert len(input_steps) == len(loaded.events)
    assert [e.event for e in input_steps[-1].emitted_events].count(EventType.ROUND_END) == 1
    assert input_steps[-1].state_after == runtime.state
