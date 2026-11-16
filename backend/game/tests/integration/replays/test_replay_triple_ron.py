import re

from game.engine import RNG_VERSION, Discard, EventType, MahjongGameService, Refusal, Ron, RoundEndEvent
from game.messaging.roster import GameRoster
from game.replay import run_replay
from game.replay.external.tenhou import TenhouConverter
from game.replay.loader import load_replay_from_bytes
from game.replay.models import ReplayInput
from game.replay.runner import ReplayOptions
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.builders import start_game_in_play
from game.tests.helpers.hands import (
    PIN_3_TRIPLE_RON_CALLER_HANDS,
    PIN_3_TRIPLE_RON_DEALER_HAND,
    PIN_3_TRIPLE_RON_DISCARD,
)
from game.tests.helpers.start_wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.keys import WireKey
from game.wire.replay_format import REPLAY_VERSION, decode_replay_records, encode_replay_records

SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
ROSTER = GameRoster(game_id="triple-ron", names=("Charlie", "Bob", "Alice", "Diana"), ai_seats=frozenset())
DEALER = "Charlie"
RON_CALLERS_BY_SEAT_ORDER = ("Bob", "Alice", "Diana")


def test_triple_ron_replay__when_recorded_and_reloaded__should_reproduce_the_aborted_live_game_and_its_tenhou_log():
    wall = make_start_wall(
        (PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS),
        draws=(PIN_3_TRIPLE_RON_DISCARD,),
    )
    service = MahjongGameService()
    start = start_game_in_play(service, seed=SEED, walls=[wall])
    runtime = start.runtime
    seat_by_player = {name: seat for seat, name in enumerate(ROSTER.names)}
    recorded_events = list(start.events)
    plays = [
        (DEALER, Discard(tile=PIN_3_TRIPLE_RON_DISCARD)),
        *((player, Ron()) for player in RON_CALLERS_BY_SEAT_ORDER),
    ]
    for player, action in plays:
        events = service.act(runtime, seat_by_player[player], action)
        assert not isinstance(events, Refusal), events
        recorded_events += events

    assert len([e for e in recorded_events if isinstance(e, RoundEndEvent)]) == 1

    record = ReplayRecord(seed=SEED, rng_version=RNG_VERSION, roster=ROSTER)
    ReplayCollector(FakeReplayStorage()).collect_events(record, recorded_events)
    loaded = load_replay_from_bytes(encode_replay_records([{WireKey.REPLAY_VERSION: REPLAY_VERSION}, *record.records]))
    assert [(e.player_name, e.action) for e in loaded.events] == [
        (DEALER, Discard(tile=PIN_3_TRIPLE_RON_DISCARD)),
        *((player, Ron()) for player in RON_CALLERS_BY_SEAT_ORDER),
    ]
    tenhou_xml = TenhouConverter(
        decode_replay_records(encode_replay_records([{WireKey.REPLAY_VERSION: REPLAY_VERSION}, *record.records]))[1:]
    ).convert()
    tenhou_tags = r'<GO type="(\d+)"|<AGARI [^>]*who="(\d)"|<RYUUKYOKU type="(\w+)"'
    assert re.findall(tenhou_tags, tenhou_xml) == [("9", "", ""), ("", "", "ron3")]

    trace = run_replay(
        ReplayInput(
            seed=loaded.seed,
            player_names=loaded.player_names,
            walls=(wall,),
            events=loaded.events,
        ),
        ReplayOptions(advance_rounds=False),
    )
    input_steps = [step for step in trace.steps if not step.synthetic]
    assert len(input_steps) == len(loaded.events)
    assert [e.type for e in input_steps[-1].emitted_events].count(EventType.ROUND_END) == 1
    assert trace.final_state == runtime.state
