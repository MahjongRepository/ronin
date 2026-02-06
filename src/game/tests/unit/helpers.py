from typing import TYPE_CHECKING

from mahjong.tile import TilesConverter

from game.logic.enums import BotType
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.types import SeatConfig

if TYPE_CHECKING:
    from game.logic.mahjong_service import MahjongGameService


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


def _update_round_state(
    service: MahjongGameService,
    game_id: str,
    **updates: object,
) -> MahjongRoundState:
    """
    Update round state for testing with frozen state.

    Creates a new frozen round state with the given updates and assigns it to the game.
    Returns the new round state.
    """
    game_state = service._games[game_id]  # noqa: SLF001
    new_round = game_state.round_state.model_copy(update=updates)
    new_game = game_state.model_copy(update={"round_state": new_round})
    service._games[game_id] = new_game  # noqa: SLF001
    return new_round


def _update_player(
    service: MahjongGameService,
    game_id: str,
    seat: int,
    **updates: object,
) -> MahjongPlayer:
    """
    Update a player's state for testing with frozen state.

    Creates a new frozen player with the given updates and assigns it to the game.
    Returns the new player.
    """
    game_state = service._games[game_id]  # noqa: SLF001
    round_state = game_state.round_state
    players = list(round_state.players)
    old_player = players[seat]
    new_player = old_player.model_copy(update=updates)
    players[seat] = new_player
    new_round = round_state.model_copy(update={"players": tuple(players)})
    new_game = game_state.model_copy(update={"round_state": new_round})
    service._games[game_id] = new_game  # noqa: SLF001
    return new_player


def _update_game_state(
    service: MahjongGameService,
    game_id: str,
    **updates: object,
) -> MahjongGameState:
    """
    Update game state for testing with frozen state.

    Creates a new frozen game state with the given updates and assigns it.
    Returns the new game state.
    """
    game_state = service._games[game_id]  # noqa: SLF001
    new_game = game_state.model_copy(update=updates)
    service._games[game_id] = new_game  # noqa: SLF001
    return new_game
