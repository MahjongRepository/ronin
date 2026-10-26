import json
import re
from typing import TYPE_CHECKING, Any

import pytest

from game.logic.enums import GameAction, RoundResultType
from game.logic.events import EventType, RoundEndEvent
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.rng import RNG_VERSION
from game.logic.settings import NUM_PLAYERS, GameSettings
from game.logic.tiles import NUM_TILES
from game.replay import run_replay
from game.replay.external.tenhou import TenhouConverter
from game.replay.loader import load_replay_from_string
from game.replay.models import ReplayInput, ReplayTrace
from game.replay.runner import ReplayOptions
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.replay_format import REPLAY_VERSION

if TYPE_CHECKING:
    from game.logic.state import MahjongGameState
    from game.logic.types import RoundResult

SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")
NAME_BY_SEAT = {0: "Charlie", 1: "Bob", 2: "Alice", 3: "Diana"}
DEALER, PON_CALLER, PENCHAN_SEAT, KANCHAN_SEAT = 0, 1, 2, 3
DEALT_HAND_SIZE = 13
KAN_DECLARER_FILLER_SIZE = DEALT_HAND_SIZE - 3

PIN_3_COPIES = [tile_copies(copy, pin="3")[0] for copy in range(4)]
PIN_3_DISCARD, PIN_3_ADDED = PIN_3_COPIES[2], PIN_3_COPIES[3]
PON_CALLER_DISCARD = tile_copies(2, honors="5")[0]
PON_CALLER_HAND = (*PIN_3_COPIES[:2], *tile_copies(2, man="1469", sou="1479", honors="235"))
PENCHAN_PIN_3_HAND = tile_copies(0, pin="1299", man="789", sou="456789")
KANCHAN_PIN_3_HAND = (*tile_copies(1, pin="24", man="123", sou="345678"), *tile_copies(0, honors="11"))
INERT_DRAWS = tile_copies(0, honors="666")
TENHOU_PIN_3_PON = '<N who="1" m="18027" />'
TENHOU_PIN_3_ADDED_KAN = '<N who="1" m="18035" />'

MAN_1_COPIES = [tile_copies(copy, man="1")[0] for copy in range(4)]
KOKUSHI_WAITING_ON_MAN_1_HANDS = (
    (*tile_copies(0, man="9", pin="19", sou="19", honors="1234567"), *tile_copies(3, man="9")),
    (*tile_copies(1, man="9", pin="19", sou="19", honors="1234567"), *tile_copies(3, pin="1")),
    (*tile_copies(2, man="9", pin="19", sou="19", honors="1234567"), *tile_copies(3, sou="1")),
)


TURNS_TO_ADDED_KAN = [
    (DEALER, GameAction.DISCARD, {"tile_id": PIN_3_DISCARD}),
    (PON_CALLER, GameAction.CALL_PON, {"tile_id": PIN_3_DISCARD}),
    (PENCHAN_SEAT, GameAction.PASS, {}),
    (KANCHAN_SEAT, GameAction.PASS, {}),
    (PON_CALLER, GameAction.DISCARD, {"tile_id": PON_CALLER_DISCARD}),
    *(
        (seat, GameAction.DISCARD, {"tile_id": tile})
        for seat, tile in zip((PENCHAN_SEAT, KANCHAN_SEAT, DEALER), INERT_DRAWS, strict=True)
    ),
    (PON_CALLER, GameAction.CALL_KAN, {"tile_id": PIN_3_ADDED, "kan_type": "added"}),
]


def _filler(count: int, *, taken: set[int]) -> list[int]:
    return [tile for tile in range(NUM_TILES) if tile not in taken][:count]


def _added_kan_wall() -> tuple[int, ...]:
    hands = (PON_CALLER_HAND, PENCHAN_PIN_3_HAND, KANCHAN_PIN_3_HAND)
    draws = (PIN_3_DISCARD, *INERT_DRAWS, PIN_3_ADDED)
    dealer_hand = _filler(DEALT_HAND_SIZE, taken={tile for hand in hands for tile in hand} | set(draws))
    return make_start_wall((dealer_hand, *hands), draws=draws)


def _kokushi_wall(robber_count: int) -> tuple[int, ...]:
    robber_hands = KOKUSHI_WAITING_ON_MAN_1_HANDS[:robber_count]
    taken = {tile for hand in robber_hands for tile in hand} | set(MAN_1_COPIES)
    bystander_count = NUM_PLAYERS - 1 - robber_count
    other_tiles = _filler(KAN_DECLARER_FILLER_SIZE + DEALT_HAND_SIZE * bystander_count, taken=taken)
    dealer_hand = (*MAN_1_COPIES[:3], *other_tiles[:KAN_DECLARER_FILLER_SIZE])
    bystander_hands = [
        other_tiles[start : start + DEALT_HAND_SIZE]
        for start in range(KAN_DECLARER_FILLER_SIZE, len(other_tiles), DEALT_HAND_SIZE)
    ]
    return make_start_wall((dealer_hand, *robber_hands, *bystander_hands), draws=(MAN_1_COPIES[3],))


def _play_record_and_replay(
    wall: tuple[int, ...],
    actions: list[tuple[int, GameAction, dict[str, Any]]],
    settings: GameSettings,
) -> tuple[MahjongGameState, list[RoundResult], ReplayInput, ReplayTrace, str]:
    service = MahjongGameService()
    start = service.start_game("chankan", list(PLAYERS), seed=SEED, settings=settings, wall=list(wall))
    runtime = start.runtime
    assert {NAME_BY_SEAT[seat]: seat for seat in range(NUM_PLAYERS)} == dict(zip(PLAYERS, start.seats, strict=True))

    recorded_events = list(start.events)
    for seat, action, data in actions:
        update = service.handle_action(runtime, seat=seat, action=action, data=data)
        assert [e.data for e in update.events if e.event == EventType.ERROR] == []
        recorded_events += update.events

    record = ReplayRecord(seed=SEED, rng_version=RNG_VERSION, settings=settings)
    ReplayCollector(FakeReplayStorage()).collect_events(record, recorded_events)
    loaded = load_replay_from_string("\n".join([json.dumps({"version": REPLAY_VERSION}), *record.lines]))
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
    round_ends = [e.data.result for e in recorded_events if isinstance(e.data, RoundEndEvent)]
    tenhou_xml = TenhouConverter([json.loads(line) for line in record.lines]).convert()
    return runtime.state, round_ends, loaded, trace, tenhou_xml


def _tenhou_melds_and_round_ends(tenhou_xml: str) -> list[str]:
    return re.findall(r"<N [^>]*>|<AGARI|<RYUUKYOKU", tenhou_xml)


@pytest.mark.parametrize(
    ("responses", "round_end_types", "pon_caller_meld", "replayed_tail", "tenhou_tags"),
    [
        pytest.param(
            [(PENCHAN_SEAT, GameAction.CALL_RON), (KANCHAN_SEAT, GameAction.PASS)],
            [RoundResultType.RON],
            FrozenMeld.PON,
            [(PON_CALLER, GameAction.CALL_KAN), (PENCHAN_SEAT, GameAction.CALL_RON)],
            [TENHOU_PIN_3_PON, TENHOU_PIN_3_ADDED_KAN, "<AGARI"],
            id="single_ron",
        ),
        pytest.param(
            [(PENCHAN_SEAT, GameAction.CALL_RON), (KANCHAN_SEAT, GameAction.CALL_RON)],
            [RoundResultType.DOUBLE_RON],
            FrozenMeld.PON,
            [
                (PON_CALLER, GameAction.CALL_KAN),
                (PENCHAN_SEAT, GameAction.CALL_RON),
                (KANCHAN_SEAT, GameAction.CALL_RON),
            ],
            [TENHOU_PIN_3_PON, TENHOU_PIN_3_ADDED_KAN, "<AGARI", "<AGARI"],
            id="double_ron",
        ),
        pytest.param(
            [(PENCHAN_SEAT, GameAction.PASS), (KANCHAN_SEAT, GameAction.PASS)],
            [],
            FrozenMeld.SHOUMINKAN,
            [(DEALER, GameAction.DISCARD), (PON_CALLER, GameAction.CALL_KAN)],
            [TENHOU_PIN_3_PON, TENHOU_PIN_3_ADDED_KAN],
            id="declined",
        ),
    ],
)
def test_chankan_replay__when_added_kan_is_robbed_or_declined__should_reproduce_the_live_game_and_its_tenhou_log(
    responses, round_end_types, pon_caller_meld, replayed_tail, tenhou_tags
):
    live_state, round_ends, loaded, trace, tenhou_xml = _play_record_and_replay(
        _added_kan_wall(),
        [*TURNS_TO_ADDED_KAN, *((seat, action, {}) for seat, action in responses)],
        GameSettings(),
    )

    assert [r.type for r in round_ends] == round_end_types
    assert [m.meld_type for m in live_state.round_state.players[PON_CALLER].melds] == [pon_caller_meld]
    loaded_tail = [(e.player_name, e.action) for e in loaded.events[-len(replayed_tail) :]]
    assert loaded_tail == [(NAME_BY_SEAT[seat], action) for seat, action in replayed_tail]
    assert trace.final_state == live_state
    assert _tenhou_melds_and_round_ends(tenhou_xml) == tenhou_tags


def test_chankan_replay__when_head_bump_drops_a_robbers_ron__should_declare_it_in_the_replay_as_live():
    live_state, round_ends, loaded, trace, tenhou_xml = _play_record_and_replay(
        _added_kan_wall(),
        [*TURNS_TO_ADDED_KAN, (KANCHAN_SEAT, GameAction.CALL_RON, {}), (PENCHAN_SEAT, GameAction.CALL_RON, {})],
        GameSettings(has_double_ron=False),
    )

    assert [(r.type, r.winner_seat, r.head_bumped_seats) for r in round_ends] == [
        (RoundResultType.RON, PENCHAN_SEAT, [KANCHAN_SEAT]),
    ]
    assert [(e.player_name, e.action) for e in loaded.events[-3:]] == [
        (NAME_BY_SEAT[PON_CALLER], GameAction.CALL_KAN),
        (NAME_BY_SEAT[PENCHAN_SEAT], GameAction.CALL_RON),
        (NAME_BY_SEAT[KANCHAN_SEAT], GameAction.CALL_RON),
    ]
    assert trace.final_state == live_state
    assert _tenhou_melds_and_round_ends(tenhou_xml) == [TENHOU_PIN_3_PON, TENHOU_PIN_3_ADDED_KAN, "<AGARI"]


@pytest.mark.parametrize(
    ("robber_count", "result_type", "tenhou_round_end"),
    [
        pytest.param(1, RoundResultType.RON, "<AGARI", id="ron"),
        pytest.param(3, RoundResultType.ABORTIVE_DRAW, "<RYUUKYOKU", id="triple_ron"),
    ],
)
def test_chankan_replay__when_kokushi_robs_a_closed_kan__should_reproduce_the_live_game_and_its_tenhou_log(
    robber_count, result_type, tenhou_round_end
):
    robber_seats = range(1, robber_count + 1)
    live_state, round_ends, loaded, trace, tenhou_xml = _play_record_and_replay(
        _kokushi_wall(robber_count),
        [
            (DEALER, GameAction.CALL_KAN, {"tile_id": MAN_1_COPIES[3], "kan_type": "closed"}),
            *((seat, GameAction.CALL_RON, {}) for seat in robber_seats),
        ],
        GameSettings(),
    )

    assert [r.type for r in round_ends] == [result_type]
    assert [(e.player_name, e.action, e.data) for e in loaded.events] == [
        (NAME_BY_SEAT[DEALER], GameAction.CALL_KAN, {"tile_id": MAN_1_COPIES[3], "kan_type": "closed"}),
        *((NAME_BY_SEAT[seat], GameAction.CALL_RON, {}) for seat in robber_seats),
    ]
    assert trace.final_state == live_state
    assert _tenhou_melds_and_round_ends(tenhou_xml) == ['<N who="0" m="0" />', tenhou_round_end]
