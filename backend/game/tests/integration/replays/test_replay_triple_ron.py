import json
import re

import pytest

from game.logic.enums import GameAction
from game.logic.events import EventType, RoundEndEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameSettings, GameType
from game.replay import run_replay
from game.replay.external.tenhou import TenhouConverter
from game.replay.loader import load_replay_from_string
from game.replay.models import ReplayInput
from game.replay.runner import ReplayOptions
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


@pytest.mark.parametrize(
    ("settings", "tenhou_go_and_round_ends"),
    [
        pytest.param(
            GameSettings(),
            [("9", "", ""), ("", "", "ron3")],
            id="triple_ron_aborts",
        ),
        pytest.param(
            GameSettings(has_triple_ron_abort=False),
            [("9", "", ""), ("", "1", ""), ("", "2", "")],
            id="third_declarer_head_bumped",
        ),
        pytest.param(
            GameSettings(game_type=GameType.TONPUSEN, has_double_ron=False, has_triple_ron_abort=False),
            [("1", "", ""), ("", "1", "")],
            id="tonpusen_head_bump_over_two_declarers",
        ),
    ],
)
def test_triple_ron_replay__when_recorded_and_reloaded__should_reproduce_the_live_game_and_its_tenhou_log(
    settings, tenhou_go_and_round_ends
):
    wall = make_start_wall(
        (PIN_3_TRIPLE_RON_DEALER_HAND, *PIN_3_TRIPLE_RON_CALLER_HANDS),
        draws=(PIN_3_TRIPLE_RON_DISCARD,),
    )
    service = MahjongGameService()
    start = service.start_game("triple-ron", list(PLAYERS), seed=SEED, settings=settings, wall=list(wall))
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

    assert len([e for e in recorded_events if isinstance(e, RoundEndEvent)]) == 1

    record = ReplayRecord(seed=SEED, rng_version=RNG_VERSION, settings=settings)
    ReplayCollector(FakeReplayStorage()).collect_events(record, recorded_events)
    loaded = load_replay_from_string("\n".join([json.dumps({"version": REPLAY_VERSION}), *record.lines]))
    assert loaded.settings == settings
    assert [(e.player_name, e.action) for e in loaded.events] == [
        (DEALER, GameAction.DISCARD),
        *((player, GameAction.CALL_RON) for player in RON_CALLERS_BY_SEAT_ORDER),
    ]
    tenhou_xml = TenhouConverter([json.loads(line) for line in record.lines]).convert()
    tenhou_tags = r'<GO type="(\d+)"|<AGARI [^>]*who="(\d)"|<RYUUKYOKU type="(\w+)"'
    assert re.findall(tenhou_tags, tenhou_xml) == tenhou_go_and_round_ends

    trace = run_replay(
        ReplayInput(
            seed=loaded.seed,
            player_names=loaded.player_names,
            settings=loaded.settings,
            wall=wall,
            events=loaded.events,
        ),
        ReplayOptions(auto_confirm_rounds=False),
    )
    input_steps = [step for step in trace.steps if not step.synthetic]
    assert len(input_steps) == len(loaded.events)
    assert [e.type for e in input_steps[-1].emitted_events].count(EventType.ROUND_END) == 1
    assert trace.final_state == runtime.state
