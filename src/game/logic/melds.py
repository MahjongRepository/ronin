"""
Meld operations for Mahjong game (pon, chi, kan).
"""

from typing import TYPE_CHECKING

from mahjong.meld import Meld

from game.logic.enums import MeldCallType
from game.logic.round import add_dora_indicator, draw_from_dead_wall
from game.logic.state import MahjongPlayer
from game.logic.tiles import DRAGONS_34, WINDS_34, is_honor, tile_to_34
from game.logic.win import get_waiting_tiles

TILES_PER_SUIT = 9

if TYPE_CHECKING:
    from game.logic.state import MahjongRoundState

# minimum tiles needed in wall to declare kan (need replacement draw)
MIN_WALL_FOR_KAN = 2

# maximum number of kans allowed per round across all players
MAX_KANS_PER_ROUND = 4

# meld size constants
TILES_FOR_PON = 2
TILES_FOR_OPEN_KAN = 3
TILES_FOR_CLOSED_KAN = 4

# chi sequence position limits (0-indexed tile values within a suit)
CHI_LOWEST_MAX_VALUE = 6  # tile can be lowest (e.g., 1 in 123) if value <= 6
CHI_MIDDLE_MIN_VALUE = 1  # tile can be middle if value >= 1
CHI_MIDDLE_MAX_VALUE = 7  # tile can be middle if value <= 7
CHI_HIGHEST_MIN_VALUE = 2  # tile can be highest (e.g., 3 in 123) if value >= 2


def _count_total_kans(round_state: MahjongRoundState) -> int:
    """
    Count total kans declared across all players in the round.
    """
    total = 0
    for player in round_state.players:
        total += sum(1 for m in player.melds if m.type in (Meld.KAN, Meld.SHOUMINKAN))
    return total


DRAGON_SET_COUNT_FOR_PAO = 3  # pao triggers on 3rd dragon set (daisangen)
WIND_SET_COUNT_FOR_PAO = 4  # pao triggers on 4th wind set (daisuushii)

_DRAGON_TILES = frozenset(DRAGONS_34)
_WIND_TILES = frozenset(WINDS_34)

# pao-eligible meld types (pon, open kan, added kan)
_PAO_MELD_TYPES = (Meld.PON, Meld.KAN, Meld.SHOUMINKAN)


def _check_pao(player: MahjongPlayer, discarder_seat: int, called_tile_34: int) -> None:
    """
    Check and set pao liability after a pon/open kan call.

    Pao triggers when:
    - 3rd dragon set is completed (Big Three Dragons / daisangen)
    - 4th wind set is completed (Big Four Winds / daisuushii)
    """
    pao_rules: list[tuple[frozenset[int], int]] = [
        (_DRAGON_TILES, DRAGON_SET_COUNT_FOR_PAO),
        (_WIND_TILES, WIND_SET_COUNT_FOR_PAO),
    ]
    for tile_set, threshold in pao_rules:
        if called_tile_34 in tile_set:
            count = sum(
                1
                for m in player.melds
                if m.tiles and tile_to_34(m.tiles[0]) in tile_set and m.type in _PAO_MELD_TYPES
            )
            if count >= threshold:
                player.pao_seat = discarder_seat
            break


def get_kuikae_tiles(
    call_type: MeldCallType, called_tile_34: int, sequence_tiles_34: list[int] | None = None
) -> list[int]:
    """
    Compute tiles forbidden to discard after a meld call (kuikae restriction).

    For pon: the called tile type is forbidden.
    For chi: the called tile type plus the suji tile at the opposite end of the sequence.
    """
    forbidden = [called_tile_34]

    if call_type == MeldCallType.CHI and sequence_tiles_34 is not None:
        # chi suji kuikae: forbid the tile at the opposite end of the sequence
        all_tiles = sorted([called_tile_34, *sequence_tiles_34])
        suit = called_tile_34 // TILES_PER_SUIT

        if called_tile_34 == all_tiles[0]:
            # called tile is the lowest in the sequence, suji extends one step beyond the highest
            suji = all_tiles[2] + 1
            if suji // TILES_PER_SUIT == suit:
                forbidden.append(suji)
        elif called_tile_34 == all_tiles[2]:
            # called tile is the highest in the sequence, suji extends one step below the lowest
            suji = all_tiles[0] - 1
            if suji >= 0 and suji // TILES_PER_SUIT == suit:
                forbidden.append(suji)
        # if called tile is middle, no suji kuikae applies

    return forbidden


def can_call_pon(player: MahjongPlayer, discarded_tile: int) -> bool:
    """
    Check if player can call pon on a discarded tile.

    Requirements:
    - Player has 2 matching tiles in hand (same tile_34 type)
    - Player is not in riichi
    """
    if player.is_riichi:
        return False

    discarded_34 = tile_to_34(discarded_tile)
    matching_count = sum(1 for t in player.tiles if tile_to_34(t) == discarded_34)

    return matching_count >= TILES_FOR_PON


def call_pon(
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> Meld:
    """
    Execute a pon call on a discarded tile.

    Removes 2 matching tiles from caller's hand, creates a Meld object,
    updates game state (open hands, ippatsu flags, current player).
    Returns the created Meld.
    """
    caller = round_state.players[caller_seat]
    tile_34 = tile_to_34(tile_id)

    # find and remove 2 matching tiles from hand
    removed_tiles = []
    new_hand = []
    for t in caller.tiles:
        if tile_to_34(t) == tile_34 and len(removed_tiles) < TILES_FOR_PON:
            removed_tiles.append(t)
        else:
            new_hand.append(t)

    if len(removed_tiles) != TILES_FOR_PON:
        raise ValueError(f"cannot call pon: need {TILES_FOR_PON} matching tiles, found {len(removed_tiles)}")

    caller.tiles = new_hand

    # create meld with all 3 tiles (2 from hand + called tile)
    meld_tiles = sorted([*removed_tiles, tile_id])
    meld = Meld(
        meld_type=Meld.PON,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )
    caller.melds.append(meld)

    # track open hand
    if caller_seat not in round_state.players_with_open_hands:
        round_state.players_with_open_hands.append(caller_seat)

    # clear ippatsu for all players
    for p in round_state.players:
        p.is_ippatsu = False

    # set current player to caller (they must discard next)
    round_state.current_player_seat = caller_seat

    # set kuikae restriction
    caller.kuikae_tiles = get_kuikae_tiles(MeldCallType.PON, tile_34)

    # check pao liability
    _check_pao(caller, discarder_seat, tile_34)

    return meld


def can_call_chi(
    player: MahjongPlayer,
    discarded_tile: int,
    discarder_seat: int,
    caller_seat: int,
) -> list[tuple[int, int]]:
    """
    Check if player can call chi on a discarded tile.

    Requirements:
    - Caller must be kamicha (player to the left of discarder: discarder_seat + 1 mod 4)
    - Tile must be numbered (not honor)
    - Player has tiles to form at least one sequence
    - Player is not in riichi

    Returns list of possible chi combinations. Each tuple contains the two tiles
    from hand that would complete the sequence with the discarded tile.
    """
    if player.is_riichi:
        return []

    expected_caller = (discarder_seat + 1) % 4
    if caller_seat != expected_caller:
        return []

    discarded_34 = tile_to_34(discarded_tile)

    if is_honor(discarded_34):
        return []

    tile_value = discarded_34 % 9
    hand_tiles_by_34 = _build_same_suit_tile_map(player.tiles, discarded_34)

    return _find_chi_combinations(discarded_34, tile_value, hand_tiles_by_34)


def _build_same_suit_tile_map(tiles: list[int], discarded_34: int) -> dict[int, list[int]]:
    """
    Build a map of tiles in hand that are in the same suit as discarded tile.
    """
    result: dict[int, list[int]] = {}
    discarded_suit = discarded_34 // 9

    for t in tiles:
        t34 = tile_to_34(t)
        if t34 // 9 == discarded_suit:
            if t34 not in result:
                result[t34] = []
            result[t34].append(t)

    return result


def _find_chi_combinations(
    discarded_34: int,
    tile_value: int,
    hand_tiles: dict[int, list[int]],
) -> list[tuple[int, int]]:
    """
    Find all valid chi combinations for a discarded tile.
    """
    combinations: list[tuple[int, int]] = []

    # discarded tile is lowest in sequence (e.g., 1 in 123)
    if tile_value <= CHI_LOWEST_MAX_VALUE:
        _add_combination_if_valid(combinations, hand_tiles, discarded_34 + 1, discarded_34 + 2)

    # discarded tile is middle in sequence (e.g., 2 in 123)
    if CHI_MIDDLE_MIN_VALUE <= tile_value <= CHI_MIDDLE_MAX_VALUE:
        _add_combination_if_valid(combinations, hand_tiles, discarded_34 - 1, discarded_34 + 1)

    # discarded tile is highest in sequence (e.g., 3 in 123)
    if tile_value >= CHI_HIGHEST_MIN_VALUE:
        _add_combination_if_valid(combinations, hand_tiles, discarded_34 - 2, discarded_34 - 1)

    return combinations


def _add_combination_if_valid(
    combinations: list[tuple[int, int]],
    hand_tiles: dict[int, list[int]],
    tile34_a: int,
    tile34_b: int,
) -> None:
    """
    Add a chi combination if both required tiles exist in hand.
    """
    if tile34_a in hand_tiles and tile34_b in hand_tiles:
        combinations.append((hand_tiles[tile34_a][0], hand_tiles[tile34_b][0]))


def call_chi(
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
    sequence_tiles: tuple[int, int],
) -> Meld:
    """
    Execute a chi call on a discarded tile.

    Removes sequence_tiles from caller's hand, creates a Meld object,
    updates game state (open hands, ippatsu flags, current player).
    Returns the created Meld.
    """
    caller = round_state.players[caller_seat]

    # remove sequence tiles from hand
    new_hand = list(caller.tiles)
    for t in sequence_tiles:
        new_hand.remove(t)
    caller.tiles = new_hand

    # create meld with all 3 tiles (2 from hand + called tile)
    meld_tiles = sorted([sequence_tiles[0], sequence_tiles[1], tile_id])
    meld = Meld(
        meld_type=Meld.CHI,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )
    caller.melds.append(meld)

    # track open hand
    if caller_seat not in round_state.players_with_open_hands:
        round_state.players_with_open_hands.append(caller_seat)

    # clear ippatsu for all players
    for p in round_state.players:
        p.is_ippatsu = False

    # set current player to caller (they must discard next)
    round_state.current_player_seat = caller_seat

    # set kuikae restriction
    sequence_tiles_34 = [tile_to_34(t) for t in sequence_tiles]
    caller.kuikae_tiles = get_kuikae_tiles(MeldCallType.CHI, tile_to_34(tile_id), sequence_tiles_34)

    return meld


def can_call_open_kan(player: MahjongPlayer, discarded_tile: int, round_state: MahjongRoundState) -> bool:
    """
    Check if player can call open kan (daiminkan) on a discarded tile.

    Requirements:
    - Player has 3 matching tiles in hand (same tile_34 type)
    - Player is not in riichi
    - Wall must have at least 2 tiles remaining (need replacement draw)
    - Total kans in round must be less than 4
    """
    if player.is_riichi:
        return False

    if len(round_state.wall) < MIN_WALL_FOR_KAN:
        return False

    if _count_total_kans(round_state) >= MAX_KANS_PER_ROUND:
        return False

    discarded_34 = tile_to_34(discarded_tile)
    matching_count = sum(1 for t in player.tiles if tile_to_34(t) == discarded_34)

    return matching_count >= TILES_FOR_OPEN_KAN


def can_call_closed_kan(player: MahjongPlayer, tile_34: int, round_state: MahjongRoundState) -> bool:
    """
    Check if player can call closed kan (ankan) for a specific tile type.

    Requirements:
    - Player has 4 of the tile in hand
    - Wall must have at least 2 tiles remaining (need replacement draw)
    - Total kans in round must be less than 4
    - If in riichi, kan must not change waiting tiles
    """
    if len(round_state.wall) < MIN_WALL_FOR_KAN:
        return False

    if _count_total_kans(round_state) >= MAX_KANS_PER_ROUND:
        return False

    matching_count = sum(1 for t in player.tiles if tile_to_34(t) == tile_34)

    if matching_count < TILES_FOR_CLOSED_KAN:
        return False

    if player.is_riichi:
        return _kan_preserves_waits_for_riichi(player, tile_34)

    return True


def _kan_preserves_waits_for_riichi(player: MahjongPlayer, tile_34: int) -> bool:
    """
    Check if declaring kan on this tile preserves the waiting tiles.

    In riichi, a closed kan can only be declared if:
    1. It doesn't change the waiting tiles
    2. The tile is not one of the waiting tiles
    """
    # reduce to 13 tiles by removing one copy of the kan tile
    tiles_13 = list(player.tiles)
    for i, t in enumerate(tiles_13):
        if tile_to_34(t) == tile_34:
            tiles_13.pop(i)
            break

    tenpai_player = MahjongPlayer(
        seat=player.seat, name=player.name, tiles=tiles_13, melds=list(player.melds)
    )
    original_waits = get_waiting_tiles(tenpai_player)

    if not original_waits:
        return False

    # if the kan tile is one of the waits, cannot kan
    if tile_34 in original_waits:
        return False

    # simulate kan state with all 14 tiles retained; the hand calculator
    # subtracts the kan meld tiles internally when evaluating tenpai.
    kan_tiles = [t for t in player.tiles if tile_to_34(t) == tile_34]
    kan_meld = Meld(
        meld_type=Meld.KAN,
        tiles=kan_tiles,
        opened=False,
        who=player.seat,
    )
    temp_player = MahjongPlayer(
        seat=player.seat,
        name=player.name,
        tiles=list(player.tiles),
        melds=[*player.melds, kan_meld],
    )

    new_waits = get_waiting_tiles(temp_player)

    return new_waits == original_waits


def can_call_added_kan(player: MahjongPlayer, tile_34: int, round_state: MahjongRoundState) -> bool:
    """
    Check if player can call added kan (shouminkan) for a specific tile type.

    Requirements:
    - Player has an existing pon of this tile type
    - Player has the 4th tile in hand
    - Wall must have at least 2 tiles remaining
    - Total kans in round must be less than 4
    - Player is not in riichi (cannot add kan in riichi)
    """
    if player.is_riichi:
        return False

    if len(round_state.wall) < MIN_WALL_FOR_KAN:
        return False

    if _count_total_kans(round_state) >= MAX_KANS_PER_ROUND:
        return False

    # check for existing pon of this tile type
    has_pon = False
    for meld in player.melds:
        if meld.type == Meld.PON and meld.tiles:
            meld_tile_34 = tile_to_34(meld.tiles[0])
            if meld_tile_34 == tile_34:
                has_pon = True
                break

    if not has_pon:
        return False

    # check for 4th tile in hand
    matching_count = sum(1 for t in player.tiles if tile_to_34(t) == tile_34)
    return matching_count >= 1


def call_open_kan(
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
) -> Meld:
    """
    Execute an open kan (daiminkan) call on a discarded tile.

    Removes 3 matching tiles from caller's hand, creates a Meld object,
    updates game state. The caller must draw from dead wall after this.
    Returns the created Meld.
    """
    caller = round_state.players[caller_seat]
    tile_34 = tile_to_34(tile_id)

    # find and remove 3 matching tiles from hand
    removed_tiles = []
    new_hand = []
    for t in caller.tiles:
        if tile_to_34(t) == tile_34 and len(removed_tiles) < TILES_FOR_OPEN_KAN:
            removed_tiles.append(t)
        else:
            new_hand.append(t)

    if len(removed_tiles) != TILES_FOR_OPEN_KAN:
        raise ValueError(
            f"cannot call open kan: need {TILES_FOR_OPEN_KAN} matching tiles, found {len(removed_tiles)}"
        )

    caller.tiles = new_hand

    # create meld with all 4 tiles (3 from hand + called tile)
    meld_tiles = sorted([*removed_tiles, tile_id])
    meld = Meld(
        meld_type=Meld.KAN,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )
    caller.melds.append(meld)

    # track open hand
    if caller_seat not in round_state.players_with_open_hands:
        round_state.players_with_open_hands.append(caller_seat)

    # clear ippatsu for all players
    for p in round_state.players:
        p.is_ippatsu = False

    # set current player to caller (they will draw from dead wall and then discard)
    round_state.current_player_seat = caller_seat

    # defer dora indicator reveal until after discard (open kan rule)
    round_state.pending_dora_count += 1

    # check pao liability
    _check_pao(caller, discarder_seat, tile_34)

    # draw from dead wall (sets is_rinshan flag)
    draw_from_dead_wall(round_state)

    return meld


def call_closed_kan(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
) -> Meld:
    """
    Execute a closed kan (ankan) declaration.

    Player declares kan with 4 tiles from hand. The hand remains closed.
    Returns the created Meld.
    """
    player = round_state.players[seat]
    tile_34 = tile_to_34(tile_id)

    # find and remove all 4 matching tiles from hand
    removed_tiles = []
    new_hand = []
    for t in player.tiles:
        if tile_to_34(t) == tile_34 and len(removed_tiles) < TILES_FOR_CLOSED_KAN:
            removed_tiles.append(t)
        else:
            new_hand.append(t)

    if len(removed_tiles) != TILES_FOR_CLOSED_KAN:
        raise ValueError(
            f"cannot call closed kan: need {TILES_FOR_CLOSED_KAN} matching tiles, found {len(removed_tiles)}"
        )

    player.tiles = new_hand

    # create meld with all 4 tiles (closed kan - opened=False)
    meld_tiles = sorted(removed_tiles)
    meld = Meld(
        meld_type=Meld.KAN,
        tiles=meld_tiles,
        opened=False,
        who=seat,
    )
    player.melds.append(meld)

    # closed kan does NOT make the hand open
    # do NOT add to players_with_open_hands

    # clear ippatsu for all players
    for p in round_state.players:
        p.is_ippatsu = False

    # current player remains the same (they will draw and discard)
    round_state.current_player_seat = seat

    # add new dora indicator
    add_dora_indicator(round_state)

    # draw from dead wall (sets is_rinshan flag)
    draw_from_dead_wall(round_state)

    return meld


def call_added_kan(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
) -> Meld:
    """
    Execute an added kan (shouminkan) declaration.

    Player upgrades an existing pon to a kan by adding the 4th tile.
    Note: This can be robbed by other players (chankan) if they are waiting on this tile.
    Returns the upgraded Meld.
    """
    player = round_state.players[seat]
    tile_34 = tile_to_34(tile_id)

    # find the pon meld to upgrade
    pon_meld = None
    pon_index = -1
    for i, meld in enumerate(player.melds):
        if meld.type == Meld.PON and meld.tiles:
            meld_tile_34 = tile_to_34(meld.tiles[0])
            if meld_tile_34 == tile_34:
                pon_meld = meld
                pon_index = i
                break

    if pon_meld is None:
        raise ValueError(f"cannot call added kan: no pon of tile type {tile_34}")

    # remove the 4th tile from hand
    if tile_id not in player.tiles:
        raise ValueError(f"cannot call added kan: tile {tile_id} not in hand")

    player.tiles.remove(tile_id)

    # upgrade the meld from pon to kan (shouminkan)
    if pon_meld.tiles is None:
        raise ValueError("pon meld tiles cannot be None for kan upgrade")
    new_tiles = sorted([*pon_meld.tiles, tile_id])
    upgraded_meld = Meld(
        meld_type=Meld.SHOUMINKAN,
        tiles=new_tiles,
        opened=True,
        called_tile=pon_meld.called_tile,
        who=seat,
        from_who=pon_meld.from_who,
    )
    player.melds[pon_index] = upgraded_meld

    # clear ippatsu for all players
    for p in round_state.players:
        p.is_ippatsu = False

    # current player remains the same
    round_state.current_player_seat = seat

    # defer dora indicator reveal until after discard (added kan rule)
    round_state.pending_dora_count += 1

    # draw from dead wall (sets is_rinshan flag)
    draw_from_dead_wall(round_state)

    return upgraded_meld


def get_possible_closed_kans(player: MahjongPlayer, round_state: MahjongRoundState) -> list[int]:
    """
    Get list of tile_34 values for which player can declare closed kan.

    Returns a list of tile_34 indices representing tiles the player has 4 of.
    """
    if len(round_state.wall) < MIN_WALL_FOR_KAN:
        return []

    if _count_total_kans(round_state) >= MAX_KANS_PER_ROUND:
        return []

    tile_counts: dict[int, int] = {}
    for t in player.tiles:
        t34 = tile_to_34(t)
        tile_counts[t34] = tile_counts.get(t34, 0) + 1

    possible = []
    for t34, count in tile_counts.items():
        if count >= TILES_FOR_CLOSED_KAN:
            if player.is_riichi:
                if _kan_preserves_waits_for_riichi(player, t34):  # pragma: no cover
                    possible.append(t34)
            else:
                possible.append(t34)

    return possible


def get_possible_added_kans(player: MahjongPlayer, round_state: MahjongRoundState) -> list[int]:
    """
    Get list of tile_34 values for which player can declare added kan.

    Returns a list of tile_34 indices for pons that can be upgraded.
    """
    if player.is_riichi:
        return []

    if len(round_state.wall) < MIN_WALL_FOR_KAN:
        return []

    if _count_total_kans(round_state) >= MAX_KANS_PER_ROUND:
        return []

    possible = []
    for meld in player.melds:
        if meld.type == Meld.PON and meld.tiles:
            meld_tile_34 = tile_to_34(meld.tiles[0])
            # check if player has the 4th tile
            if any(tile_to_34(t) == meld_tile_34 for t in player.tiles):
                possible.append(meld_tile_34)

    return possible
