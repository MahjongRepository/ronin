import json
import re

from game.logic.enums import AbortiveDrawType, GameAction
from game.logic.events import EventType, RoundEndEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.replay import run_replay
from game.replay.external.tenhou import TenhouConverter
from game.replay.loader import load_replay_from_string
from game.replay.models import ReplayInput
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
)
from game.tests.helpers.wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.replay_format import REPLAY_VERSION

SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")
DEALER = "Charlie"
RON_CALLERS_BY_SEAT_ORDER = ("Bob", "Alice", "Diana")
TENHOU_RON_CALLER_HANDS = (
    ' hai1="0,4,8,12,16,20,24,28,32,36,40,124,125"'
    ' hai2="48,52,72,76,80,84,88,92,96,100,104,128,129"'
    ' hai3="5,9,13,17,21,25,45,49,53,56,93,97,101"'
)


def test_triple_ron_replay__when_recorded_and_reloaded__should_reproduce_the_abort_and_its_tenhou_log():
    wall = make_start_wall(
        (PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS),
        draws=(PIN_3_TRIPLE_RON_DISCARD,),
    )
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
    tenhou_xml = TenhouConverter([json.loads(line) for line in record.lines]).convert()
    assert re.findall(r'<RYUUKYOKU type="ron3" [^>]*sc="[^"]*"([^>]*) />', tenhou_xml) == [TENHOU_RON_CALLER_HANDS]

    trace = run_replay(
        ReplayInput(seed=loaded.seed, player_names=loaded.player_names, wall=wall, events=loaded.events),
    )
    input_steps = [step for step in trace.steps if not step.synthetic]
    assert len(input_steps) == len(loaded.events)
    assert [e.event for e in input_steps[-1].emitted_events].count(EventType.ROUND_END) == 1
    assert input_steps[-1].state_after == runtime.state
