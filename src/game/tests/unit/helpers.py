from mahjong.tile import TilesConverter

from game.logic.enums import BotType
from game.logic.state import MahjongPlayer, MahjongRoundState
from game.logic.types import SeatConfig


def _string_to_34_tiles(
    sou: str | None = "",
    pin: str | None = "",
    man: str | None = "",
    honors: str | None = "",
) -> list[int]:
    tiles = TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)
    return [t // 4 for t in tiles]


def _string_to_open_34_set(
    sou: str | None = "",
    pin: str | None = "",
    man: str | None = "",
    honors: str | None = "",
) -> list[int]:
    open_set = TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)
    open_set[0] //= 4
    open_set[1] //= 4
    open_set[2] //= 4
    return open_set


def _string_to_34_tile(
    sou: str | None = "",
    pin: str | None = "",
    man: str | None = "",
    honors: str | None = "",
) -> int:
    item = TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)
    item[0] //= 4
    return item[0]


def _string_to_136_tile(
    sou: str | None = "",
    pin: str | None = "",
    man: str | None = "",
    honors: str | None = "",
) -> int:
    return TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)[0]


def _find_human_player(round_state: MahjongRoundState, name: str) -> MahjongPlayer:
    """Find the human player by name."""
    for player in round_state.players:
        if player.name == name:
            return player
    raise ValueError(f"player {name} not found")


def _default_seat_configs() -> list[SeatConfig]:
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="Tsumogiri 1", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 2", bot_type=BotType.TSUMOGIRI),
        SeatConfig(name="Tsumogiri 3", bot_type=BotType.TSUMOGIRI),
    ]
