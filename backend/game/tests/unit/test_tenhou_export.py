from typing import Any

import pytest

from game.logic.events import GamePlayerInfo, GameStartedEvent, ServiceEvent
from game.logic.rng import RNG_VERSION
from game.logic.settings import GameType
from game.messaging.event_payload import service_event_payload
from game.replay.external.tenhou import TenhouConverter


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


def _replay_line_recorded_before_game_type() -> dict[str, Any]:
    line = _game_started_replay_line(GameType.HANCHAN)
    return {key: value for key, value in line.items() if key != "gt"}


@pytest.mark.parametrize(
    ("game_started_line", "go_tag"),
    [
        pytest.param(_game_started_replay_line(GameType.HANCHAN), '<GO type="9" lobby="0"/>', id="hanchan"),
        pytest.param(_game_started_replay_line(GameType.TONPUSEN), '<GO type="1" lobby="0"/>', id="tonpusen"),
        pytest.param(_replay_line_recorded_before_game_type(), '<GO type="9" lobby="0"/>', id="no_gt"),
    ],
)
def test_tenhou_converter__when_game_started__should_set_go_type_from_game_length(game_started_line, go_tag):
    xml = TenhouConverter([game_started_line]).convert()
    assert xml.count(go_tag) == 1
