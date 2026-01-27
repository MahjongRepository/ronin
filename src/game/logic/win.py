"""
Win detection for Mahjong game.

Handles checking for winning conditions (tsumo, ron) and furiten detection.
Scoring functions are in the scoring module.
"""

from typing import TYPE_CHECKING

from mahjong.agari import Agari
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.shanten import Shanten

from game.logic.state import seat_to_wind
from game.logic.tiles import hand_to_34_array, tile_to_34

if TYPE_CHECKING:
    from mahjong.meld import Meld

    from game.logic.state import MahjongPlayer, MahjongRoundState

# maximum copies of a single tile
MAX_TILE_COPIES = 4


def check_tsumo(player: MahjongPlayer) -> bool:
    """
    Check if the player's hand is a winning hand (agari).

    Uses the mahjong library's Agari class to determine if the hand
    can form 4 melds + 1 pair (or special hands like kokushi/chiitoitsu).
    """
    tiles_34 = hand_to_34_array(player.tiles)

    # convert open melds to 34-format for the agari check
    open_sets_34 = _melds_to_34_sets(player.melds)

    agari = Agari()
    return agari.is_agari(tiles_34, open_sets_34)


def can_declare_tsumo(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
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
    tiles_34 = hand_to_34_array(player.tiles)
    shanten = Shanten()
    current_shanten = shanten.calculate_shanten(tiles_34)

    # if not in tempai (shanten > 0), no waiting tiles
    if current_shanten != 0:
        return set()

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


def can_call_ron(player: MahjongPlayer, discarded_tile: int, round_state: MahjongRoundState) -> bool:
    """
    Check if player can call ron on a discarded tile.

    Requirements:
    - Hand must win with the discarded tile
    - Player must not be in furiten
    - For open hands, must have at least one yaku
    """
    # temporarily add the discarded tile to check for win
    original_tiles = list(player.tiles)
    player.tiles.append(discarded_tile)

    # check if hand wins
    is_winning = check_tsumo(player)

    if not is_winning:
        player.tiles = original_tiles
        return False

    # restore tiles before furiten check (furiten uses hand without win tile)
    player.tiles = original_tiles

    # check furiten
    if is_furiten(player):
        return False

    # for closed hands with riichi, ron is always valid (riichi is a yaku)
    if not player.has_open_melds() and player.is_riichi:
        return True

    # for all other cases (open hands or closed non-riichi), verify yaku exists
    # temporarily add tile back for yaku check
    player.tiles.append(discarded_tile)
    has_yaku = _has_yaku_for_ron(player, round_state, discarded_tile)
    player.tiles = original_tiles

    return has_yaku


def _has_yaku_for_ron(player: MahjongPlayer, round_state: MahjongRoundState, win_tile: int) -> bool:
    """
    Check if a ron call has at least one yaku.

    Similar to _has_yaku_for_open_hand but for ron (not tsumo).
    """
    options = OptionalRules(
        has_aka_dora=True,
        has_open_tanyao=True,
        has_double_yakuman=False,
    )

    config = HandConfig(
        is_tsumo=False,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu,
        is_daburu_riichi=player.is_daburi,
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=round_state.round_wind,
        options=options,
    )

    calculator = HandCalculator()
    result = calculator.estimate_hand_value(
        tiles=list(player.tiles),
        win_tile=win_tile,
        melds=player.melds if player.melds else None,
        dora_indicators=round_state.dora_indicators if round_state.dora_indicators else None,
        config=config,
    )

    return result.error != HandCalculator.ERR_NO_YAKU


def _has_yaku_for_open_hand(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
    """
    Check if an open hand has at least one yaku.

    Uses HandCalculator to verify the hand has valid yaku.
    """
    # the win tile is the last tile added to hand (the drawn tile)
    if not player.tiles:
        return False

    win_tile = player.tiles[-1]

    # build tiles array (all tiles in hand)
    tiles = list(player.tiles)

    # configure hand for tsumo
    config = HandConfig(
        is_tsumo=True,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=round_state.round_wind,
    )

    calculator = HandCalculator()
    result = calculator.estimate_hand_value(
        tiles=tiles,
        win_tile=win_tile,
        melds=player.melds if player.melds else None,
        dora_indicators=round_state.dora_indicators if round_state.dora_indicators else None,
        config=config,
    )

    # if error is "no_yaku", the hand has no valid yaku
    return result.error != HandCalculator.ERR_NO_YAKU


def _melds_to_34_sets(melds: list[Meld]) -> list[list[int]] | None:
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


def is_tenhou(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
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


def is_chiihou(player: MahjongPlayer, round_state: MahjongRoundState) -> bool:
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

        # check if player is not furiten
        if is_furiten(player):
            continue

        # for open hands, verify there's at least one yaku
        if player.has_open_melds():
            # temporarily add tile to check for yaku
            original_tiles = list(player.tiles)
            player.tiles.append(kan_tile)
            has_yaku = _has_yaku_for_ron(player, round_state, kan_tile)
            player.tiles = original_tiles
            if not has_yaku:
                continue

        chankan_seats.append(seat)

    return chankan_seats
