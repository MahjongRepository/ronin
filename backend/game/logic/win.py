from __future__ import annotations

from typing import TYPE_CHECKING

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.meld_wrapper import frozen_melds_to_melds
from game.logic.settings import NUM_PLAYERS, GameSettings, RenhouValue, build_optional_rules
from game.logic.shanten import is_complete_closed, mask_to_tile_types, waits_mask
from game.logic.state import seat_to_wind
from game.logic.state_utils import update_player
from game.logic.tiles import NUM_TILE_TYPES, WAITING_HAND_REMAINDER, WINDS_34, hand_to_34_array, tile_to_34
from game.logic.wall import is_wall_exhausted

if TYPE_CHECKING:
    from collections.abc import Callable

    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )

# the 13 terminal/honor tile types required for kokushi musou
KOKUSHI_TILES_34 = frozenset({0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33})
KOKUSHI_MIN_UNIQUE_TYPES = 12


def all_player_tiles(player: MahjongPlayer) -> list[int]:
    """
    Build a complete 136-format tile list from closed hand tiles and meld tiles.

    The mahjong library expects ALL tiles (closed + open melds) to be passed to HandCalculator.estimate_hand_value.
    """
    return all_tiles_from_hand_and_melds(player.tiles, player.melds)


def all_tiles_from_hand_and_melds(
    hand_tiles: list[int] | tuple[int, ...],
    melds: list | tuple,
) -> list[int]:
    """
    Build a complete 136-format tile list from explicit hand tiles and melds.

    Accepts hand tiles and melds directly rather than reading from a player object.
    """
    return [*hand_tiles, *(t for meld in melds for t in meld.tiles)]


def check_tsumo(player: MahjongPlayer) -> bool:
    """
    Check if the player's hand is a winning hand (agari).

    The closed tiles must form the rest of a complete hand beside the melds: 4 sets + 1 pair, or a special hand like
    kokushi/chiitoitsu.
    """
    return check_tsumo_with_tiles(player.tiles)


def can_declare_tsumo(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    *,
    settings: GameSettings,
) -> bool:
    """
    Check if player can declare tsumo (self-draw win).

    Requirements:
    - The player drew: right after their own pon or chi there is no drawn tile, and the "win tile" would be the
      called discard
    - Hand must be a winning hand
    - For open hands, must have at least one yaku (no yaku = can't win)

    Furiten does not apply: it forbids ron only.
    """
    if round_state.is_after_meld_call:
        return False

    # first check if hand is winning
    if not check_tsumo(player):
        return False

    # for closed hands, always can declare (menzen tsumo is always a yaku)
    if not player.has_open_melds():
        return True

    # for open hands, need to verify at least one yaku exists
    return _has_yaku_for_open_hand(player, round_state, settings=settings)


def get_waiting_tiles(player: MahjongPlayer) -> set[int]:
    """
    Find all tiles that would complete the player's hand.

    Returns a set of tile_34 values (0-33): the waits of the closed tiles, without a type whose 4 copies are all in the
    player's own hand and melds (karaten).

    Waits belong to a waiting hand (3n+1 closed tiles). Any other hand has none of its own (a drawn hand after the draw
    or the player's own pon or chi, or a hand no deal can produce), so asking for them is an engine invariant breach and
    raises AssertionError rather than answering an empty set for the wrong hand.
    """
    if len(player.tiles) % 3 != WAITING_HAND_REMAINDER:
        raise AssertionError(f"seat {player.seat} holds {len(player.tiles)} tiles, not a waiting hand of 3n+1")

    return mask_to_tile_types(waits_mask(hand_to_34_array(player.tiles), player.melds))


def is_furiten(player: MahjongPlayer) -> bool:
    """
    Check if player is in furiten state.

    A player is furiten if any of their waiting tiles appears in their own discards. Furiten players can still win by
    tsumo but cannot win by ron.
    """
    return is_furiten_on_waits(player, get_waiting_tiles(player))


def is_furiten_on_waits(player: MahjongPlayer, waiting_tiles: set[int]) -> bool:
    """
    Check discard furiten against waits already computed for the player (the tile_34 set get_waiting_tiles returns).
    """
    return any(tile_to_34(discard.tile_id) in waiting_tiles for discard in player.discards)


def is_effective_furiten(player: MahjongPlayer) -> bool:
    """
    Check if player is in any form of furiten state.

    Combines temporary furiten, riichi furiten, and discard furiten. Short-circuits on cheap boolean flags before
    computing expensive discard furiten.
    """
    if player.is_temporary_furiten:
        return True

    if player.is_riichi_furiten:
        return True

    return is_furiten(player)


def _has_yaku_for_open_hand(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> bool:
    """
    Check if an open hand has at least one yaku.

    Uses HandCalculator to verify the hand has valid yaku.
    """
    # the win tile is the last tile added to hand (the drawn tile)
    win_tile = player.tiles[-1]

    # configure hand for tsumo
    config = HandConfig(
        is_tsumo=True,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu and settings.has_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        is_haitei=is_haitei(round_state),
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=build_optional_rules(settings),
    )

    result = HandCalculator.estimate_hand_value(
        tiles=all_player_tiles(player),
        win_tile=win_tile,
        melds=frozen_melds_to_melds(player.melds),
        dora_indicators=round_state.wall.dora_indicators,
        config=config,
    )
    return result.error is None


def is_haitei(round_state: MahjongRoundState) -> bool:
    """
    Check if current situation is haitei (last tile draw from wall).

    Haitei raoyue is a yaku for winning by tsumo on the last tile of the wall.
    """
    return is_wall_exhausted(round_state.wall)


def is_houtei(round_state: MahjongRoundState) -> bool:
    """
    Check wall exhaustion prerequisite for houtei (last discard).

    Houtei raoyui is a yaku for winning by ron on the last discard of the game. This only checks the wall condition; the
    caller must ensure the context is a ron (not tsumo) to correctly award the yaku.
    """
    return is_wall_exhausted(round_state.wall)


def is_tenhou(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player's win qualifies as tenhou (heavenly hand).

    Tenhou requirements:
    - Player is the dealer
    - No discards have been made by anyone
    - No calls from any player (including closed kans)
    - Win on first draw (tsumo on dealt hand)
    """
    return (
        player.seat == round_state.dealer_seat and len(round_state.all_discards) == 0 and not round_state.has_any_call()
    )


def is_chiihou(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player's win qualifies as chiihou (earthly hand).

    Chiihou requirements:
    - Player is not the dealer
    - Player has not yet discarded (first draw of the round)
    - No calls from any player (including closed kans)
    - Win on first draw (tsumo on first turn)
    """
    return player.seat != round_state.dealer_seat and len(player.discards) == 0 and not round_state.has_any_call()


def is_renhou(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player's ron qualifies as renhou (blessing of man).

    Renhou requires:
    - Player is not the dealer
    - No calls have been made by any player (open melds or closed kans)
    - Player has not yet had their first draw (no discards)
    """
    if player.seat == round_state.dealer_seat:
        return False

    if round_state.has_any_call():
        return False

    # player has not yet discarded (before their first turn)
    return len(player.discards) == 0


def _find_chankan_seats(
    round_state: MahjongRoundState,
    caller_seat: int,
    kan_tile: int,
    *,
    extra_filter: Callable[[MahjongPlayer], bool] | None = None,
) -> list[int]:
    """
    Find seats eligible for chankan (robbing a kan) on the given tile.

    Iterates the other seats counter-clockwise from the kan caller, filtering by waiting tiles and furiten status, so
    the result is in head-bump order. An optional extra_filter predicate (e.g. kokushi tenpai check) can restrict
    eligibility further.
    """
    kan_tile_34 = tile_to_34(kan_tile)
    chankan_seats = []
    for offset in range(1, NUM_PLAYERS):
        seat = (caller_seat + offset) % NUM_PLAYERS
        player = round_state.players[seat]
        if extra_filter and not extra_filter(player):
            continue

        # check if player is waiting on this tile
        waiting = get_waiting_tiles(player)
        if kan_tile_34 not in waiting:
            continue

        # check riichi furiten (permanent for the hand)
        if player.is_riichi_furiten:
            continue

        # check temporary furiten
        if player.is_temporary_furiten:
            continue

        if is_furiten_on_waits(player, waiting):
            continue

        chankan_seats.append(seat)

    return chankan_seats


def is_chankan_possible(round_state: MahjongRoundState, caller_seat: int, kan_tile: int) -> list[int]:
    """
    Find seats that can ron on an added kan (chankan).

    When a player upgrades a pon to a kan (added/shouminkan), other players who are waiting on that tile can declare ron
    (chankan).
    """
    return _find_chankan_seats(round_state, caller_seat, kan_tile)


def is_kokushi_tenpai(player: MahjongPlayer) -> bool:
    """
    Check if a player's waiting hand (13 tiles, between turns) is specifically kokushi musou tenpai.

    Kokushi requires a closed hand with 12 or 13 of the 13 terminal/honor tile types (a hand with a meld holds at most
    10 tiles, so it falls short).  Tenpai forms:
    - 12 unique types + 1 pair: waiting for the missing 13th type
    - 13 unique types (no pair): 13-way wait for any type
    """
    tiles_34 = hand_to_34_array(player.tiles)

    # every tile must be a kokushi terminal/honor type
    for i in range(NUM_TILE_TYPES):
        if tiles_34[i] > 0 and i not in KOKUSHI_TILES_34:
            return False

    unique_types = sum(1 for i in KOKUSHI_TILES_34 if tiles_34[i] > 0)
    return unique_types >= KOKUSHI_MIN_UNIQUE_TYPES


def is_kokushi_chankan_possible(
    round_state: MahjongRoundState,
    caller_seat: int,
    kan_tile: int,
) -> list[int]:
    """
    Find seats that can rob a closed kan (ankan) with kokushi musou.

    Only kokushi musou may rob a concealed quad; no other hand qualifies.
    """
    return _find_chankan_seats(round_state, caller_seat, kan_tile, extra_filter=is_kokushi_tenpai)


def check_tsumo_with_tiles(tiles: list[int] | tuple[int, ...]) -> bool:
    """
    Check if the given closed tiles complete a hand beside the player's melds (agari).

    Takes a local tile list (closed hand plus the win tile) instead of mutating player.tiles. Melds are complete sets,
    so the closed tiles alone decide the shape.
    """
    return is_complete_closed(hand_to_34_array(tiles))


def can_ron_on_completing_tile(
    player: MahjongPlayer,
    *,
    discarded_tile: int,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> bool:
    """
    Check if player may call ron on a discarded tile already known to complete their hand (check_tsumo_with_tiles).

    Requirements:
    - Player must not be in furiten
    - For open hands, and closed hands without riichi, must have at least one yaku
    """
    if player.is_riichi_furiten:
        return False

    if player.is_temporary_furiten:
        return False

    if is_furiten(player):
        return False

    if not player.has_open_melds() and player.is_riichi:
        return True

    return _has_yaku_for_ron_with_tiles(
        player,
        round_state,
        win_tile=discarded_tile,
        tiles=[*player.tiles, discarded_tile],
        settings=settings,
    )


def _has_yaku_for_ron_with_tiles(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    win_tile: int,
    tiles: list[int],
    settings: GameSettings,
) -> bool:
    """
    Check if a ron call has at least one yaku, using a local tile list.

    Doesn't rely on player.tiles.
    """
    config = HandConfig(
        is_tsumo=False,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu and settings.has_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_renhou=settings.renhou_value != RenhouValue.NONE and is_renhou(player, round_state),
        is_houtei=is_houtei(round_state),
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=build_optional_rules(settings),
    )

    result = HandCalculator.estimate_hand_value(
        tiles=all_tiles_from_hand_and_melds(tiles, player.melds),
        win_tile=win_tile,
        melds=frozen_melds_to_melds(player.melds),
        dora_indicators=round_state.wall.dora_indicators,
        config=config,
    )
    return result.error is None


def apply_temporary_furiten(
    round_state: MahjongRoundState,
    seat: int,
) -> MahjongRoundState:
    """
    Apply temporary furiten to a player who passed on a ron opportunity.

    Returns a new round state with the player's is_temporary_furiten set to True.
    """
    return update_player(round_state, seat, is_temporary_furiten=True)
