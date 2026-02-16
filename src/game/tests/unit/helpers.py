from typing import TYPE_CHECKING

from mahjong.tile import TilesConverter

if TYPE_CHECKING:
    from game.logic.mahjong_service import MahjongGameService
    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )


def _string_to_34_tiles(
    sou: str | None = "",
    pin: str | None = "",
    man: str | None = "",
    honors: str | None = "",
) -> list[int]:
    tiles = TilesConverter.string_to_136_array(sou=sou, pin=pin, man=man, honors=honors)
    return [t // 4 for t in tiles]


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


def _find_player(round_state: MahjongRoundState, name: str) -> MahjongPlayer:
    """Find a player by name."""
    for player in round_state.players:
        if player.name == name:
            return player
    raise ValueError(f"player {name} not found")


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
    game_state = service._games[game_id]
    new_round = game_state.round_state.model_copy(update=updates)
    new_game = game_state.model_copy(update={"round_state": new_round})
    service._games[game_id] = new_game
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
    game_state = service._games[game_id]
    round_state = game_state.round_state
    players = list(round_state.players)
    old_player = players[seat]
    new_player = old_player.model_copy(update=updates)
    players[seat] = new_player
    new_round = round_state.model_copy(update={"players": tuple(players)})
    new_game = game_state.model_copy(update={"round_state": new_round})
    service._games[game_id] = new_game
    return new_player
