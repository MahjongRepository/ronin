from collections import Counter
from typing import TYPE_CHECKING

from mahjong.tile import TilesConverter

from game.logic.state import Discard
from game.logic.tiles import NUM_TILES
from game.logic.wall import DeadWall, TileStack, Wall

if TYPE_CHECKING:
    from game.logic.runtime import GameRuntime
    from game.logic.state import (
        MahjongGameState,
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
    for player in round_state.players:
        if player.name == name:
            return player

    raise ValueError(f"player {name} not found")


def _imply_claimed_discards(players: list[MahjongPlayer]) -> list[MahjongPlayer]:
    """
    Give every meld called from another seat the discard record it implies, when the staged state lacks it.
    """
    for player in players:
        for meld in player.melds:
            if meld.called_tile is None or meld.from_who is None or meld.from_who == player.seat:
                continue

            source = players[meld.from_who]
            claimed = sum(
                1
                for p in players
                for m in p.melds
                if m.from_who == source.seat and m.who != source.seat and m.called_tile == meld.called_tile
            )
            if sum(1 for d in source.discards if d.tile_id == meld.called_tile) < claimed:
                players[meld.from_who] = source.model_copy(
                    update={"discards": (*source.discards, Discard(tile_id=meld.called_tile))},
                )

    return players


def _staged_tiles(players: list[MahjongPlayer], wall: Wall, *, keep: int | None) -> Counter[int]:
    """
    Count the tiles the staged state fixes: melds, unclaimed discards, and the staged hand or live wall.
    """
    taken = Counter(wall.live_tiles if keep is None else players[keep].tiles)
    for player in players:
        taken.update(d.tile_id for d in player.discards)
        for meld in player.melds:
            taken.update(meld.tiles)
            if meld.called_tile is not None and meld.from_who is not None and meld.from_who != player.seat:
                taken[meld.called_tile] -= 1

    return taken


def _rebalance_tiles(game_state: MahjongGameState, *, keep: int | None) -> MahjongGameState:
    """
    Restore tile ownership after a test staged hands, melds or a wall directly, so the next commit accepts the state.

    What the test staged wins: the hand of seat `keep`, or the live wall (kept exactly as given) when keep is None. A
    meld called from another seat gets the discard it implies; other hands and the dead wall swap tiles the staged part
    now owns for free ones (dead wall roles and dora reveals unchanged). The tiles nobody owns then go to the live wall
    when a hand was staged, or become discards, dealt round-robin from the dealer and appended to all_discards, when the
    wall was staged, since a shorter wall means those tiles were drawn and discarded.
    """
    round_state = game_state.round_state
    wall = round_state.wall
    players = _imply_claimed_discards(list(round_state.players))
    taken = _staged_tiles(players, wall, keep=keep)
    free = iter(t for t in range(NUM_TILES - 1, -1, -1) if taken[t] == 0 and t not in wall.live_tiles)

    def claim(tile: int) -> int:
        tile = tile if taken[tile] == 0 else next(free)
        taken[tile] += 1
        return tile

    for seat, player in enumerate(players):
        if seat != keep:
            players[seat] = player.model_copy(update={"tiles": tuple(claim(t) for t in player.tiles)})

    dead = wall.dead_wall
    new_dead = DeadWall(
        rinshan=tuple(claim(t) for t in dead.rinshan),
        indicators=tuple(TileStack(top=claim(s.top), bottom=claim(s.bottom)) for s in dead.indicators),
        reserve=tuple(claim(t) for t in dead.reserve),
        revealed_count=dead.revealed_count,
        pending_reveals=dead.pending_reveals,
    )

    live = tuple(t for t in wall.live_tiles if taken[t] == 0) if keep is not None else wall.live_tiles
    taken.update(live)
    missing = [t for t in range(NUM_TILES) if taken[t] == 0]
    all_discards = round_state.all_discards
    if keep is None:
        for i, tile in enumerate(missing):
            seat = (round_state.dealer_seat + i) % len(players)
            players[seat] = players[seat].model_copy(
                update={"discards": (*players[seat].discards, Discard(tile_id=tile))}
            )

        all_discards = (*all_discards, *missing)
    else:
        live = (*live, *missing)

    new_wall = wall.model_copy(update={"live_tiles": live, "dead_wall": new_dead})
    new_round = round_state.model_copy(
        update={"players": tuple(players), "wall": new_wall, "all_discards": all_discards}
    )
    return game_state.model_copy(update={"round_state": new_round})


def _update_round_state(runtime: GameRuntime, **updates: object) -> MahjongRoundState:
    game_state = runtime.state
    new_round = game_state.round_state.model_copy(update=updates)
    runtime.state = _rebalance_tiles(game_state.model_copy(update={"round_state": new_round}), keep=None)
    return runtime.state.round_state


def _update_player(runtime: GameRuntime, *, seat: int, **updates: object) -> MahjongPlayer:
    game_state = runtime.state
    round_state = game_state.round_state
    players = list(round_state.players)
    new_player = players[seat].model_copy(update=updates)
    players[seat] = new_player
    new_round = round_state.model_copy(update={"players": tuple(players)})
    runtime.state = _rebalance_tiles(game_state.model_copy(update={"round_state": new_round}), keep=seat)
    return runtime.state.round_state.players[seat]
