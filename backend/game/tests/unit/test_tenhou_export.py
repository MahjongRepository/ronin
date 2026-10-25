import json
import re
from typing import Any

import pytest

from game.logic.events import GamePlayerInfo, GameStartedEvent, RoundEndEvent, ServiceEvent
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameType
from game.logic.types import DoubleRonResult, DoubleRonWinner, HandResultInfo, YakuInfo
from game.messaging.event_payload import service_event_payload
from game.replay.external.tenhou import TenhouConverter
from game.wire.enums import WireEventType


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


def _double_ron_winner(seat: int, score_changes: dict[int, int]) -> DoubleRonWinner:
    return DoubleRonWinner(
        winner_seat=seat,
        hand_result=HandResultInfo(han=2, fu=30, yaku=[YakuInfo(yaku_id=0, han=2)], points=2000),
        score_changes=score_changes,
        riichi_sticks_collected=0,
        closed_tiles=[],
        melds=[],
    )


def test_tenhou_converter__when_double_ron__should_give_each_agari_its_own_changes_and_the_sticks_to_the_first():
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

    xml = TenhouConverter([round_started_line, round_end_line]).convert()

    assert re.findall(r'<AGARI ba="([^"]*)"[^>]*who="(\d)"[^>]* sc="([^"]*)"', xml) == [
        ("0,1", "2", "250,0,250,-30,250,40,240,0"),
        ("0,0", "0", "250,20,220,-20,290,0,240,0"),
    ]
