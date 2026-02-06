"""
Win detection for Mahjong game.

Handles checking for winning conditions (tsumo, ron) and furiten detection.
Scoring functions are in the scoring module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mahjong.agari import Agari
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.shanten import Shanten

from game.logic.meld_wrapper import FrozenMeld, frozen_melds_to_melds
from game.logic.state import seat_to_wind
from game.logic.state_utils import update_player
from game.logic.tiles import WINDS_34, hand_to_34_array, tile_to_34

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongPlayer,
        MahjongRoundState,
    )

# maximum copies of a single tile
MAX_TILE_COPIES = 4

# shared optional rules for hand evaluation (aka dora, open tanyao, double yakuman)
GAME_OPTIONAL_RULES = OptionalRules(
    has_aka_dora=True,
    has_open_tanyao=True,
    has_double_yakuman=True,
)


def all_player_tiles(player: MahjongPlayer) -> list[int]:
    """
    Build a complete 136-format tile list from closed hand tiles and meld tiles.

    The mahjong library expects ALL tiles (closed + open melds) to be passed to
    HandCalculator.estimate_hand_value and Agari.is_agari.
    Meld tiles that already exist in player.tiles are not double-counted.
    """
    hand_ids = set(player.tiles)
    all_tiles = list(player.tiles)
    for meld in player.melds:
        if meld.tiles:
            all_tiles.extend(t for t in meld.tiles if t not in hand_ids)
    return all_tiles


def all_tiles_from_hand_and_melds(
    hand_tiles: list[int] | tuple[int, ...],
    melds: list | tuple,
) -> list[int]:
    """
    Build a complete 136-format tile list from explicit hand tiles and melds.

    Accepts hand tiles and melds directly rather than reading from a player object.
    Meld tiles that already exist in hand_tiles are not double-counted.
    """
    hand_ids = set(hand_tiles)
    all_tiles = list(hand_tiles)
    for meld in melds:
        if meld.tiles:
            all_tiles.extend(t for t in meld.tiles if t not in hand_ids)
    return all_tiles


def _hand_with_melds_to_34_array(player: MahjongPlayer) -> list[int]:
    """
    Build a 34-format tile count array from closed hand tiles and meld tiles.

    The Agari library expects tiles_34 to contain ALL tiles (closed + open melds),
    because it subtracts open sets internally during the agari check.
    """
    return hand_to_34_array(all_player_tiles(player))


def check_tsumo(player: MahjongPlayer) -> bool:
    """
    Check if the player's hand is a winning hand (agari).

    Uses the mahjong library's Agari class to determine if the hand
    can form 4 melds + 1 pair (or special hands like kokushi/chiitoitsu).
    """
    tiles_34 = _hand_with_melds_to_34_array(player)

    # convert open melds to 34-format for the agari check
    open_sets_34 = _melds_to_34_sets(player.melds)

    agari = Agari()
    return agari.is_agari(tiles_34, open_sets_34)


def can_declare_tsumo(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player can declare tsumo (self-draw win).

    Requirements:
    - Hand must be a winning hand
    - For open hands, must have at least one yaku (no yaku = can't win)
    """
    # first check if hand is winning
    if not check_tsumo(player):
        return False

    # for closed hands, always can declare (menzen tsumo is always a yaku)
    if not player.has_open_melds():
        return True

    # for open hands, need to verify at least one yaku exists
    return _has_yaku_for_open_hand(player, round_state)


def get_waiting_tiles(player: MahjongPlayer) -> set[int]:
    """
    Find all tiles that would complete the player's hand.

    Uses shanten calculator to identify which tiles would bring shanten to -1 (agari).
    Returns a set of tile_34 values (0-33) that complete the hand.
    """
    # shanten operates on closed hand tiles only
    closed_tiles_34 = hand_to_34_array(player.tiles)
    shanten = Shanten()
    current_shanten = shanten.calculate_shanten(closed_tiles_34)

    if current_shanten != 0:
        return set()

    # agari requires all tiles (closed + melds) because it subtracts open sets internally
    tiles_34 = _hand_with_melds_to_34_array(player)

    waiting = set()

    # check each of the 34 tile types
    for tile_34 in range(34):
        # skip if already 4 of this tile (can't draw a 5th)
        if tiles_34[tile_34] >= MAX_TILE_COPIES:
            continue

        # add tile and check if hand becomes agari
        tiles_34[tile_34] += 1
        agari = Agari()
        open_sets = _melds_to_34_sets(player.melds)
        if agari.is_agari(tiles_34, open_sets):
            waiting.add(tile_34)
        tiles_34[tile_34] -= 1

    return waiting


def is_furiten(player: MahjongPlayer) -> bool:
    """
    Check if player is in furiten state.

    A player is furiten if any of their waiting tiles appears in their own discards.
    Furiten players can still win by tsumo but cannot win by ron.
    """
    waiting_tiles = get_waiting_tiles(player)

    if not waiting_tiles:
        return False

    # check if any waiting tile is in player's discards
    for discard in player.discards:
        discard_34 = tile_to_34(discard.tile_id)
        if discard_34 in waiting_tiles:
            return True

    return False


def is_effective_furiten(player: MahjongPlayer) -> bool:
    """
    Check if player is in any form of furiten state.

    Combines temporary furiten, riichi furiten, and discard furiten.
    Short-circuits on cheap boolean flags before computing expensive discard furiten.
    """
    if player.is_temporary_furiten:
        return True
    if player.is_riichi_furiten:
        return True
    return is_furiten(player)


def _has_yaku_for_open_hand(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if an open hand has at least one yaku.

    Uses HandCalculator to verify the hand has valid yaku.
    """
    # the win tile is the last tile added to hand (the drawn tile)
    if not player.tiles:
        return False

    win_tile = player.tiles[-1]

    # configure hand for tsumo
    config = HandConfig(
        is_tsumo=True,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        is_haitei=is_haitei(round_state),
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=GAME_OPTIONAL_RULES,
    )

    calculator = HandCalculator()
    result = calculator.estimate_hand_value(
        tiles=all_player_tiles(player),
        win_tile=win_tile,
        melds=frozen_melds_to_melds(player.melds),
        dora_indicators=round_state.dora_indicators if round_state.dora_indicators else None,
        config=config,
    )

    return result.error is None


def _melds_to_34_sets(melds: tuple[FrozenMeld, ...]) -> list[list[int]] | None:
    """
    Convert melds to 34-format sets for agari check.

    Returns a list of lists, where each inner list contains the tile_34 indices
    of the meld tiles. Returns None if no melds.
    """
    if not melds:
        return None

    open_sets = []
    for meld in melds:
        if meld.tiles:
            meld_34 = [tile_to_34(t) for t in meld.tiles]
            open_sets.append(meld_34)

    return open_sets if open_sets else None


def is_haitei(round_state: MahjongRoundState) -> bool:
    """
    Check if current situation is haitei (last tile draw from wall).

    Haitei raoyue is a yaku for winning by tsumo on the last tile of the wall.
    """
    return len(round_state.wall) == 0


def is_houtei(round_state: MahjongRoundState) -> bool:
    """
    Check if current situation is houtei (last discard).

    Houtei raoyui is a yaku for winning by ron on the last discard of the game.
    """
    return len(round_state.wall) == 0


def is_tenhou(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player's win qualifies as tenhou (heavenly hand).

    Tenhou requirements:
    - Player is the dealer
    - No discards have been made by anyone
    - No open melds exist
    - Win on first draw (tsumo on dealt hand)
    """
    return (
        player.seat == round_state.dealer_seat
        and len(round_state.all_discards) == 0
        and not round_state.players_with_open_hands
    )


def is_chiihou(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player's win qualifies as chiihou (earthly hand).

    Chiihou requirements:
    - Player is not the dealer
    - No discards have been made by anyone
    - No open melds exist
    - Win on first draw (tsumo on first turn)
    """
    return (
        player.seat != round_state.dealer_seat
        and len(round_state.all_discards) == 0
        and not round_state.players_with_open_hands
    )


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
    # no open melds from any player
    if round_state.players_with_open_hands:
        return False
    # no melds at all (including closed kans)
    if any(p.melds for p in round_state.players):
        return False
    # player has not yet discarded (before their first turn)
    return len(player.discards) == 0


def is_chankan_possible(round_state: MahjongRoundState, caller_seat: int, kan_tile: int) -> list[int]:
    """
    Find seats that can ron on an added kan (chankan).

    When a player upgrades a pon to a kan (added/shouminkan), other players
    who are waiting on that tile can declare ron (chankan).

    Returns list of seat numbers that can call chankan on this tile.
    """
    kan_tile_34 = tile_to_34(kan_tile)
    chankan_seats = []

    for seat in range(4):
        if seat == caller_seat:
            continue

        player = round_state.players[seat]

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

        # check permanent furiten (discarded a winning tile)
        if is_furiten(player):
            continue

        # chankan itself is always a valid yaku (1 han), so open hands
        # don't need a separate yaku check here
        chankan_seats.append(seat)

    return chankan_seats


def check_tsumo_with_tiles(player: MahjongPlayer, tiles: list[int]) -> bool:
    """
    Check if the given tiles form a winning hand (agari).

    Uses a local tile list instead of mutating player.tiles.
    Used for ron/tsumo checks.
    """
    tiles_34 = hand_to_34_array(tiles)
    # add meld tiles to get full tile count
    for meld in player.melds:
        if meld.tiles:
            for t in meld.tiles:
                tiles_34[tile_to_34(t)] += 1

    open_sets_34 = _melds_to_34_sets(player.melds)
    agari = Agari()
    return agari.is_agari(tiles_34, open_sets_34)


def can_call_ron(
    player: MahjongPlayer,
    discarded_tile: int,
    round_state: MahjongRoundState,
) -> bool:
    """
    Check if player can call ron on a discarded tile.

    Uses local tile copies. Requirements:
    - Hand must win with the discarded tile
    - Player must not be in furiten
    - For open hands, must have at least one yaku
    """
    # create local tile list with the discarded tile
    tiles_with_win = [*list(player.tiles), discarded_tile]

    # check if hand wins with local tiles
    is_winning = check_tsumo_with_tiles(player, tiles_with_win)
    if not is_winning:
        return False

    # check riichi furiten (permanent for the hand)
    if player.is_riichi_furiten:
        return False

    # check temporary furiten (passed on ron this go-around)
    if player.is_temporary_furiten:
        return False

    # check permanent furiten (discarded a winning tile)
    if is_furiten(player):
        return False

    # for closed hands with riichi, ron is always valid (riichi is a yaku)
    if not player.has_open_melds() and player.is_riichi:
        return True

    # for all other cases (open hands or closed non-riichi), verify yaku exists
    # use local tile list for yaku check
    return _has_yaku_for_ron_with_tiles(player, round_state, discarded_tile, tiles_with_win)


def _has_yaku_for_ron_with_tiles(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    win_tile: int,
    tiles: list[int],
    *,
    is_chankan: bool = False,
) -> bool:
    """
    Check if a ron call has at least one yaku, using a local tile list.

    Doesn't rely on player.tiles.
    """
    config = HandConfig(
        is_tsumo=False,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_renhou=is_renhou(player, round_state),
        is_chankan=is_chankan,
        is_houtei=is_houtei(round_state),
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=GAME_OPTIONAL_RULES,
    )

    # build all tiles: local tiles + meld tiles (excluding duplicates already in tiles)
    tile_ids = set(tiles)
    all_tiles = list(tiles)
    for meld in player.melds:
        if meld.tiles:
            all_tiles.extend(t for t in meld.tiles if t not in tile_ids)

    calculator = HandCalculator()
    result = calculator.estimate_hand_value(
        tiles=all_tiles,
        win_tile=win_tile,
        melds=frozen_melds_to_melds(player.melds),
        dora_indicators=round_state.dora_indicators if round_state.dora_indicators else None,
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
