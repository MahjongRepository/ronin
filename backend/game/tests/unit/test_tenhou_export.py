import json
import re
from typing import TYPE_CHECKING, Any

import pytest
from mahjong.constants import HONOR_INDICES, TERMINAL_INDICES

from game.logic.enums import GameAction, WaitKind
from game.logic.events import (
    EventType,
    GameEndedEvent,
    GamePlayerInfo,
    GameStartedEvent,
    RoundEndEvent,
    ServiceEvent,
)
from game.logic.mahjong_service import MahjongGameService
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameSettings, GameType, RenhouValue
from game.logic.tiles import NUM_TILES
from game.logic.types import DoubleRonResult, DoubleRonWinner, HandResultInfo, PlayerStanding, YakuInfo
from game.logic.wall import DEAD_WALL_SIZE
from game.messaging.event_payload import service_event_payload
from game.replay.external.tenhou import TenhouConverter
from game.session.replay_collector import ReplayCollector, ReplayRecord
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import make_start_wall
from game.tests.mocks.replay_storage import FakeReplayStorage
from game.wire.enums import WireEventType

if TYPE_CHECKING:
    from game.logic.service import GameStart

SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
DEALER, DRAGON_CALLER, DRAGON_FEEDER, SOU_9_DISCARDER = 0, 1, 2, 3
HAKU_DISCARD, HATSU_DISCARD, CHUN_DISCARD = tile_copies(2, honors="567")
SOU_9_DISCARD = tile_copies(1, sou="9")[0]
NORTH_DISCARD = tile_copies(0, honors="4")[0]
DRAGON_CALLER_DISCARDS = tile_copies(0, honors="123")
DEALER_ITTSUU_TANKI_HAND = (HAKU_DISCARD, *tile_copies(1, man="123456789", pin="123"))
DAISANGEN_TANKI_HAND = (*tile_copies(0, honors="556677", man="123", sou="9"), *DRAGON_CALLER_DISCARDS)
DRAGON_FEEDER_HAND = (HATSU_DISCARD, CHUN_DISCARD, *tile_copies(2, man="2468", pin="2468", sou="246"))
SOU_9_DISCARDER_HAND = (*tile_copies(2, man="1357", pin="1357", sou="1357"), *tile_copies(3, man="9"))
DRAWS = (tile_copies(2, sou="9")[0], *tile_copies(1, pin="99"), NORTH_DISCARD, SOU_9_DISCARD)
DAISANGEN_AGARI_HAND = "0,4,8,104,105"
DEALER_ITTSUU_AGARI_HAND = "1,5,9,13,17,21,25,29,33,37,41,45,105,106"
DAISANGEN_YAKU = 'yakuman="39"'
DRAGON_PONS_NEWEST_FIRST = "51817,50281,48747"

KAN_CALLER = 1
PIN_3_PON_DISCARD, PIN_3_ADDED = tile_copies(2, pin="3")[0], tile_copies(3, pin="3")[0]
KAN_CALLER_PON_DISCARD = tile_copies(0, honors="4")[0]
RINSHAN_WEST = tile_copies(1, honors="3")[0]
KAN_CALLER_ITTSUU_WEST_TANKI_HAND = (
    *tile_copies(0, pin="33", man="123456789", honors="3"),
    KAN_CALLER_PON_DISCARD,
)
PIN_3_FEEDER_HAND = (PIN_3_PON_DISCARD, *tile_copies(1, man="1357", sou="1357", pin="1579"))
KAN_BYSTANDER_HANDS = tuple(
    (*tile_copies(copy, man="2468", sou="2468", pin="2468"), tile_copies(copy, honors="7")[0]) for copy in (2, 3)
)
SOUTH_DRAWS = tile_copies(1, honors="222")
KAN_GAME_DRAWS = (*SOUTH_DRAWS, tile_copies(1, honors="4")[0], PIN_3_ADDED)


def _game_started_replay_line(game_type: GameType) -> dict[str, Any]:
    event = ServiceEvent(
        data=GameStartedEvent(
            game_id="game1",
            game_type=game_type,
            players=[GamePlayerInfo(seat=i, name=f"P{i}", is_ai_player=False) for i in range(4)],
            dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
        ),
    )
    return {**service_event_payload(event), "sd": "a" * 192, "rv": RNG_VERSION}


@pytest.mark.parametrize(
    ("game_started_line", "go_tag"),
    [
        pytest.param(_game_started_replay_line(GameType.HANCHAN), '<GO type="9" lobby="0"/>', id="hanchan"),
        pytest.param(_game_started_replay_line(GameType.TONPUSEN), '<GO type="1" lobby="0"/>', id="tonpusen"),
    ],
)
def test_tenhou_converter__when_game_started__should_set_go_type_from_game_length(game_started_line, go_tag):
    xml = TenhouConverter([game_started_line]).convert()
    assert xml.count(go_tag) == 1


def _game_end_replay_line(final_scores: dict[int, int]) -> dict[str, Any]:
    standings = [PlayerStanding(seat=seat, score=score, final_score=0) for seat, score in final_scores.items()]
    event = ServiceEvent(data=GameEndedEvent(winner_seat=0, standings=standings, leftover_riichi_bonus=0))
    return json.loads(json.dumps(service_event_payload(event)))


def _double_ron_winner(seat: int, score_changes: dict[int, int]) -> DoubleRonWinner:
    return DoubleRonWinner(
        winner_seat=seat,
        hand_result=HandResultInfo(han=2, fu=30, yaku=[YakuInfo(yaku_id=0, han=2)], points=2000),
        score_changes=score_changes,
        riichi_sticks_collected=0,
        closed_tiles=[],
        melds=[],
    )


def test_tenhou_converter__when_game_ending_double_ron__should_give_each_agari_its_changes_and_the_last_the_owari():
    round_started_line = {
        "t": WireEventType.ROUND_STARTED,
        "w": 0,
        "dl": 0,
        "h": 0,
        "r": 1,
        "di": [0],
        "dc": [1, 1],
        "p": [{"s": seat, "sc": 250, "tl": []} for seat in range(4)],
    }
    result = DoubleRonResult(
        loser_seat=1,
        winning_tile=0,
        winners=[
            _double_ron_winner(2, {0: 0, 1: -3000, 2: 4000, 3: 0}),
            _double_ron_winner(0, {0: 2000, 1: -2000, 2: 0, 3: 0}),
        ],
        scores={0: 25000, 1: 25000, 2: 25000, 3: 24000},
        score_changes={0: 2000, 1: -5000, 2: 4000, 3: 0},
    )
    round_end_line = json.loads(json.dumps(service_event_payload(ServiceEvent(data=RoundEndEvent(result=result)))))
    game_end_line = _game_end_replay_line({0: 27000, 1: 20000, 2: 29000, 3: 24000})

    xml = TenhouConverter([round_started_line, round_end_line, game_end_line]).convert()

    assert re.findall(r'<AGARI ba="([^"]*)"[^>]*who="(\d)"[^>]* sc="([^"]*)"', xml) == [
        ("0,1", "2", "250,0,250,-30,250,40,240,0"),
        ("0,0", "0", "250,20,220,-20,290,0,240,0"),
    ]
    assert re.findall(r'sc="[^"]*"( owari="[^"]*")? />', xml) == ["", ' owari="270,0.0,200,0.0,290,0.0,240,0.0"']


def _start_game(wall: tuple[int, ...], settings: GameSettings | None) -> tuple[MahjongGameService, GameStart]:
    service = MahjongGameService()
    start = service.start_game(
        "tenhou", ["Alice", "Bob", "Charlie", "Diana"], seed=SEED, wall=list(wall), settings=settings
    )
    return service, start


def _replay_lines(recorded_events: list[ServiceEvent]) -> list[dict[str, Any]]:
    record = ReplayRecord(seed=SEED, rng_version=RNG_VERSION)
    ReplayCollector(FakeReplayStorage()).collect_events(record, recorded_events)
    return [json.loads(line) for line in record.lines]


def _play_and_record_replay_lines(
    wall: tuple[int, ...],
    actions: list[tuple[int, GameAction, dict[str, Any]]],
    settings: GameSettings | None = None,
) -> list[dict[str, Any]]:
    service, start = _start_game(wall, settings)
    recorded_events = list(start.events)
    for seat, action, data in actions:
        update = service.handle_action(start.runtime, seat=seat, action=action, data=data)
        assert [e.data for e in update.events if e.event == EventType.ERROR] == []
        recorded_events += update.events

    return _replay_lines(recorded_events)


def _play_by_tsumogiri_and_record_replay_lines(wall: tuple[int, ...], settings: GameSettings) -> list[dict[str, Any]]:
    service, start = _start_game(wall, settings)
    recorded_events = list(start.events)
    awaiting = start.awaiting
    while awaiting.kind in (WaitKind.TURN, WaitKind.CALL):
        seat = min(awaiting.seats)
        if awaiting.kind == WaitKind.CALL:
            update = service.handle_action(start.runtime, seat=seat, action=GameAction.PASS, data={})
        else:
            drawn_tile = start.runtime.state.round_state.players[seat].tiles[-1]
            update = service.handle_action(
                start.runtime, seat=seat, action=GameAction.DISCARD, data={"tile_id": drawn_tile}
            )

        assert [e.data for e in update.events if e.event == EventType.ERROR] == []
        recorded_events += update.events
        awaiting = update.awaiting

    return _replay_lines(recorded_events)


@pytest.mark.parametrize(
    ("dealer_response", "agari_hands_melds_yaku_and_seats"),
    [
        pytest.param(
            GameAction.PASS, [(DAISANGEN_AGARI_HAND, DRAGON_PONS_NEWEST_FIRST, DAISANGEN_YAKU, "1", "3", "2")], id="ron"
        ),
        pytest.param(
            GameAction.CALL_RON,
            [
                (DEALER_ITTSUU_AGARI_HAND, "", 'yaku="24,2"', "0", "3", ""),
                (DAISANGEN_AGARI_HAND, DRAGON_PONS_NEWEST_FIRST, DAISANGEN_YAKU, "1", "3", "2"),
            ],
            id="double_ron",
        ),
    ],
)
def test_tenhou_converter__when_daisangen_rons_after_a_liable_pon__should_write_a_yakuman_agari_with_pao_who(
    dealer_response, agari_hands_melds_yaku_and_seats
):
    wall = make_start_wall(
        (DEALER_ITTSUU_TANKI_HAND, DAISANGEN_TANKI_HAND, DRAGON_FEEDER_HAND, SOU_9_DISCARDER_HAND), draws=DRAWS
    )
    dragon_feeds = [(DEALER, HAKU_DISCARD), (DRAGON_FEEDER, HATSU_DISCARD), (DRAGON_FEEDER, CHUN_DISCARD)]
    dragon_pons = [
        action
        for (feeder, dragon), caller_discard in zip(dragon_feeds, DRAGON_CALLER_DISCARDS, strict=True)
        for action in (
            (feeder, GameAction.DISCARD, {"tile_id": dragon}),
            (DRAGON_CALLER, GameAction.CALL_PON, {"tile_id": dragon}),
            (DRAGON_CALLER, GameAction.DISCARD, {"tile_id": caller_discard}),
        )
    ]
    lines = _play_and_record_replay_lines(
        wall,
        [
            *dragon_pons,
            (DRAGON_FEEDER, GameAction.DISCARD, {"tile_id": NORTH_DISCARD}),
            (SOU_9_DISCARDER, GameAction.DISCARD, {"tile_id": SOU_9_DISCARD}),
            (DEALER, dealer_response, {}),
            (DRAGON_CALLER, GameAction.CALL_RON, {}),
        ],
    )

    xml = TenhouConverter(lines).convert()
    agari = (
        r'<AGARI [^>]*hai="([^"]*)"(?: m="([^"]*)")? machi="\d+" ten="[^"]*" (\w+="[^"]*") '
        r'[^>]*who="(\d)" fromWho="(\d)"(?: paoWho="(\d)")? sc='
    )
    assert re.findall(agari, xml) == agari_hands_melds_yaku_and_seats


def _with_first_rinshan_tile(wall: tuple[int, ...], tile: int) -> tuple[int, ...]:
    tiles = list(wall)
    first_rinshan_position = NUM_TILES - DEAD_WALL_SIZE
    tile_position = tiles.index(tile)
    tiles[tile_position], tiles[first_rinshan_position] = tiles[first_rinshan_position], tiles[tile_position]
    return tuple(tiles)


def test_tenhou_converter__when_added_kan_caller_wins_on_the_rinshan_tile__should_list_the_kan_alone_and_the_win_tile():
    wall = make_start_wall(
        (PIN_3_FEEDER_HAND, KAN_CALLER_ITTSUU_WEST_TANKI_HAND, *KAN_BYSTANDER_HANDS), draws=KAN_GAME_DRAWS
    )
    lines = _play_and_record_replay_lines(
        _with_first_rinshan_tile(wall, RINSHAN_WEST),
        [
            (DEALER, GameAction.DISCARD, {"tile_id": PIN_3_PON_DISCARD}),
            (KAN_CALLER, GameAction.CALL_PON, {"tile_id": PIN_3_PON_DISCARD}),
            (KAN_CALLER, GameAction.DISCARD, {"tile_id": KAN_CALLER_PON_DISCARD}),
            (2, GameAction.DISCARD, {"tile_id": SOUTH_DRAWS[1]}),
            (3, GameAction.DISCARD, {"tile_id": SOUTH_DRAWS[2]}),
            (DEALER, GameAction.DISCARD, {"tile_id": KAN_GAME_DRAWS[3]}),
            (KAN_CALLER, GameAction.CALL_KAN, {"tile_id": PIN_3_ADDED, "kan_type": "added"}),
            (KAN_CALLER, GameAction.DECLARE_TSUMO, {}),
        ],
    )

    xml = TenhouConverter(lines).convert()
    assert re.findall(r'<N who="1" m="(\d+)" />', xml) == ["18027", "18035"]
    assert re.findall(r'<AGARI [^>]*hai="([^"]*)" m="([^"]*)" machi="(\d+)"', xml) == [
        ("0,4,8,12,16,20,24,28,32,116,117", "18035", "117")
    ]


PIN_8_DISCARD = tile_copies(2, pin="8")[0]
SEVEN_PAIRS_PIN_8_TANKI_HAND = tile_copies(1, pin="2233445566778")
NON_TENPAI_HANDS = (
    (*tile_copies(1, man="1357", sou="1357"), *tile_copies(0, honors="12345")),
    (*tile_copies(2, man="2468", sou="2468"), *tile_copies(2, honors="12345")),
    (*tile_copies(3, man="2468", sou="2468"), *tile_copies(3, honors="12345")),
)


def test_tenhou_converter__when_renhou_scores_as_a_yakuman__should_write_it_under_tenhou_renhou_id():
    dealer_hand, *bystander_hands = NON_TENPAI_HANDS
    wall = make_start_wall((dealer_hand, SEVEN_PAIRS_PIN_8_TANKI_HAND, *bystander_hands), draws=(PIN_8_DISCARD,))
    lines = _play_and_record_replay_lines(
        wall,
        [(DEALER, GameAction.DISCARD, {"tile_id": PIN_8_DISCARD}), (1, GameAction.CALL_RON, {})],
        settings=GameSettings(renhou_value=RenhouValue.YAKUMAN),
    )

    xml = TenhouConverter(lines).convert()
    assert re.findall(r'<AGARI [^>]* ten="[^"]*,5" (\w+="[^"]*") ', xml) == ['yakuman="36"']


NINE_TERMINAL_TYPES_HAND = (*tile_copies(0, man="19", pin="19", sou="19", honors="123"), *tile_copies(0, man="2345"))
HAKU_DRAW = tile_copies(0, honors="5")[0]
KYUUSHU_WALL = make_start_wall((NINE_TERMINAL_TYPES_HAND,), draws=(HAKU_DRAW,))

RIICHI_TENPAI_HANDS = (
    (*tile_copies(0, man="123456789", pin="123"), *tile_copies(0, pin="9")),
    (*tile_copies(1, man="123456789", sou="123"), *tile_copies(1, sou="9")),
    (*tile_copies(2, man="123456789", pin="456"), *tile_copies(2, honors="7")),
    (*tile_copies(3, man="123456789", sou="456"), *tile_copies(3, honors="5")),
)
WIND_DRAWS = tile_copies(0, honors="1234")
FOUR_RIICHI_WALL = make_start_wall(RIICHI_TENPAI_HANDS, draws=WIND_DRAWS)

MAN_5_RINSHAN, MAN_5_RON_DISCARD = tile_copies(1, man="5")[0], tile_copies(3, man="5")[0]
KAN_CALLER_WEST_DISCARD = tile_copies(0, honors="3")[0]
TRIPLE_RON_DEALER_HAND = (
    PIN_3_PON_DISCARD,
    *tile_copies(2, man="1357"),
    *tile_copies(3, man="9"),
    *tile_copies(1, sou="19"),
    *tile_copies(2, pin="9"),
    *tile_copies(1, honors="67"),
    *tile_copies(2, honors="67"),
)
MAN_25_WAIT_TANYAO_HAND = (*tile_copies(1, pin="22456", sou="234678"), *tile_copies(1, man="34"))
MAN_58_WAIT_TANYAO_HAND = (
    *tile_copies(2, pin="456", sou="345678"),
    *tile_copies(0, pin="88"),
    *tile_copies(1, man="67"),
)
EAST_DRAWS = tile_copies(1, honors="11")
ADDED_KAN_TRIPLE_RON_WALL = _with_first_rinshan_tile(
    make_start_wall(
        (TRIPLE_RON_DEALER_HAND, KAN_CALLER_ITTSUU_WEST_TANKI_HAND, MAN_25_WAIT_TANYAO_HAND, MAN_58_WAIT_TANYAO_HAND),
        draws=(*KAN_GAME_DRAWS, *EAST_DRAWS, MAN_5_RON_DISCARD),
    ),
    MAN_5_RINSHAN,
)
ADDED_KAN_TRIPLE_RON_ACTIONS = [
    (DEALER, GameAction.DISCARD, {"tile_id": PIN_3_PON_DISCARD}),
    (KAN_CALLER, GameAction.CALL_PON, {"tile_id": PIN_3_PON_DISCARD}),
    (KAN_CALLER, GameAction.DISCARD, {"tile_id": KAN_CALLER_PON_DISCARD}),
    (2, GameAction.DISCARD, {"tile_id": SOUTH_DRAWS[1]}),
    (3, GameAction.DISCARD, {"tile_id": SOUTH_DRAWS[2]}),
    (DEALER, GameAction.DISCARD, {"tile_id": KAN_GAME_DRAWS[3]}),
    (KAN_CALLER, GameAction.CALL_KAN, {"tile_id": PIN_3_ADDED, "kan_type": "added"}),
    (KAN_CALLER, GameAction.DISCARD, {"tile_id": KAN_CALLER_WEST_DISCARD}),
    (2, GameAction.DISCARD, {"tile_id": EAST_DRAWS[0]}),
    (3, GameAction.DISCARD, {"tile_id": EAST_DRAWS[1]}),
    (DEALER, GameAction.DISCARD, {"tile_id": MAN_5_RON_DISCARD}),
    *((seat, GameAction.CALL_RON, {}) for seat in (1, 2, 3)),
]


@pytest.mark.parametrize(
    ("wall", "actions", "tenhou_type", "revealed_hands", "riichi_scores"),
    [
        pytest.param(
            KYUUSHU_WALL,
            [(DEALER, GameAction.CALL_KYUUSHU, {})],
            "yao9",
            ' hai0="0,4,8,12,16,32,36,68,72,104,108,112,116,124"',
            [],
            id="kyuushu_kyuuhai_shows_the_declarer",
        ),
        pytest.param(
            FOUR_RIICHI_WALL,
            [(seat, GameAction.DECLARE_RIICHI, {"tile_id": wind}) for seat, wind in enumerate(WIND_DRAWS)],
            "reach4",
            ' hai0="0,4,8,12,16,20,24,28,32,36,40,44,68"'
            ' hai1="1,5,9,13,17,21,25,29,33,73,77,81,105"'
            ' hai2="2,6,10,14,18,22,26,30,34,50,54,58,134"'
            ' hai3="3,7,11,15,19,23,27,31,35,87,91,95,127"',
            [
                ("0", "240,250,250,250"),
                ("1", "240,240,250,250"),
                ("2", "240,240,240,250"),
                ("3", "240,240,240,240"),
            ],
            id="four_riichi_shows_every_hand",
        ),
        pytest.param(
            ADDED_KAN_TRIPLE_RON_WALL,
            ADDED_KAN_TRIPLE_RON_ACTIONS,
            "ron3",
            ' hai1="0,4,8,12,16,17,20,24,28,32"'
            ' hai2="9,13,41,42,49,53,57,77,81,85,93,97,101"'
            ' hai3="21,25,50,54,58,64,65,82,86,90,94,98,102"',
            [],
            id="triple_ron_shows_the_declarers_without_their_meld_tiles",
        ),
    ],
)
def test_tenhou_converter__when_round_aborts__should_reveal_the_hands_tenhou_shows(
    wall, actions, tenhou_type, revealed_hands, riichi_scores
):
    lines = _play_and_record_replay_lines(wall, actions)

    xml = TenhouConverter(lines).convert()
    assert re.findall(r'<RYUUKYOKU type="(\w+)" [^>]*sc="[^"]*"([^>]*) />', xml) == [(tenhou_type, revealed_hands)]
    assert re.findall(r'<REACH who="(\d)" ten="([^"]*)" step="2"/>', xml) == riichi_scores


NAGASHI_SEAT = 1


def test_tenhou_converter__when_tobi_follows_a_nagashi_mangan__should_write_an_nm_ryuukyoku_carrying_the_owari():
    terminals_and_honors = [t for t in range(NUM_TILES) if t // 4 in (*TERMINAL_INDICES, *HONOR_INDICES)]
    simples = [t for t in range(NUM_TILES) if t // 4 not in (*TERMINAL_INDICES, *HONOR_INDICES)]
    tenpai_hands = [simples[seat::4][:13] for seat in range(4)]
    dealt_tiles = {tile for hand in tenpai_hands for tile in hand}
    live_draw_count = NUM_TILES - DEAD_WALL_SIZE - len(dealt_tiles)
    nagashi_draws = iter(terminals_and_honors)
    other_draws = iter([*(t for t in simples if t not in dealt_tiles), *reversed(terminals_and_honors)])
    live_wall_draws = [
        next(nagashi_draws) if draw % 4 == NAGASHI_SEAT else next(other_draws) for draw in range(live_draw_count)
    ]
    wall = make_start_wall(tenpai_hands, draws=live_wall_draws)

    lines = _play_by_tsumogiri_and_record_replay_lines(wall, GameSettings(starting_score=1000))

    xml = TenhouConverter(lines).convert()
    nagashi_ryuukyoku = (
        '<RYUUKYOKU type="nm" ba="0,0" sc="10,-40,10,80,10,-20,10,-20"'
        ' hai0="4,8,12,16,20,24,28,40,44,48,52,56,60"'
        ' hai1="5,9,13,17,21,25,29,41,45,49,53,57,61"'
        ' hai2="6,10,14,18,22,26,30,42,46,50,54,58,62"'
        ' hai3="7,11,15,19,23,27,31,43,47,51,55,59,63"'
        ' owari="-30,-53.0,90,115.0,-10,-21.0,-10,-41.0" />'
    )
    assert re.findall(r"<RYUUKYOKU [^>]*/>", xml) == [nagashi_ryuukyoku]
