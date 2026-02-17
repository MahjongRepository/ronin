"""
Meld operations for Mahjong game (pon, chi, kan).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from game.logic.enums import MeldCallType
from game.logic.exceptions import InvalidMeldError
from game.logic.meld_wrapper import FrozenMeld
from game.logic.round import (
    add_dora_indicator,
    draw_from_dead_wall,
)
from game.logic.state_utils import clear_all_players_ippatsu, update_player
from game.logic.tiles import DRAGONS_34, WINDS_34, is_honor, tile_to_34
from game.logic.wall import increment_pending_dora, tiles_remaining
from game.logic.win import get_waiting_tiles

if TYPE_CHECKING:
    from game.logic.settings import GameSettings
    from game.logic.state import MahjongPlayer, MahjongRoundState

TILES_PER_SUIT = 9

logger = logging.getLogger(__name__)

# meld size constants
TILES_FOR_PON = 2
TILES_FOR_OPEN_KAN = 3
TILES_FOR_CLOSED_KAN = 4

# chi sequence position limits (0-indexed tile values within a suit)
CHI_LOWEST_MAX_VALUE = 6  # tile can be lowest (e.g., 1 in 123) if value <= 6
CHI_MIDDLE_MIN_VALUE = 1  # tile can be middle if value >= 1
CHI_MIDDLE_MAX_VALUE = 7  # tile can be middle if value <= 7
CHI_HIGHEST_MIN_VALUE = 2  # tile can be highest (e.g., 3 in 123) if value >= 2

_DRAGON_TILES = frozenset(DRAGONS_34)
_WIND_TILES = frozenset(WINDS_34)

# pao-eligible meld types (pon, open kan, added kan)
_PAO_MELD_TYPES = (FrozenMeld.PON, FrozenMeld.KAN, FrozenMeld.SHOUMINKAN)


def _count_total_kans(round_state: MahjongRoundState) -> int:
    """
    Count total kans declared across all players in the round.
    """
    total = 0
    for player in round_state.players:
        total += sum(1 for m in player.melds if m.type in (FrozenMeld.KAN, FrozenMeld.SHOUMINKAN))
    return total


def get_kuikae_tiles(
    call_type: MeldCallType,
    called_tile_34: int,
    sequence_tiles_34: list[int] | None = None,
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


def _build_same_suit_tile_map(tiles: list[int] | tuple[int, ...], discarded_34: int) -> dict[int, list[int]]:
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


def can_call_open_kan(
    player: MahjongPlayer,
    discarded_tile: int,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> bool:
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

    if tiles_remaining(round_state.wall) < settings.min_wall_for_kan:
        return False

    if _count_total_kans(round_state) >= settings.max_kans_per_round:
        return False

    discarded_34 = tile_to_34(discarded_tile)
    matching_count = sum(1 for t in player.tiles if tile_to_34(t) == discarded_34)

    return matching_count >= TILES_FOR_OPEN_KAN


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

    tenpai_player = player.model_copy(update={"tiles": tuple(tiles_13)})
    original_waits = get_waiting_tiles(tenpai_player)

    if not original_waits:
        return False

    # if the kan tile is one of the waits, the kan would change the waits
    # (e.g., 78p + 999p can wait on 9p via 789p + 9p pair reading)
    if tile_34 in original_waits:
        return False

    # simulate kan: remove all 4 tiles from hand and add as a kan meld.
    # calculate_shanten operates on closed hand tiles only, so tiles must
    # be moved from hand to the meld (not duplicated in both).
    kan_tiles = tuple(t for t in player.tiles if tile_to_34(t) == tile_34)
    remaining_tiles = tuple(t for t in player.tiles if tile_to_34(t) != tile_34)
    kan_meld = FrozenMeld(
        meld_type=FrozenMeld.KAN,
        tiles=kan_tiles,
        opened=False,
        who=player.seat,
    )
    temp_player = player.model_copy(
        update={
            "tiles": remaining_tiles,
            "melds": (*player.melds, kan_meld),
        },
    )

    new_waits = get_waiting_tiles(temp_player)

    return new_waits == original_waits


def get_possible_closed_kans(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> list[int]:
    """
    Get list of tile_34 values for which player can declare closed kan.

    Returns a list of tile_34 indices representing tiles the player has 4 of.
    """
    if tiles_remaining(round_state.wall) < settings.min_wall_for_kan:
        return []

    if _count_total_kans(round_state) >= settings.max_kans_per_round:
        return []

    tile_counts: dict[int, int] = {}
    for t in player.tiles:
        t34 = tile_to_34(t)
        tile_counts[t34] = tile_counts.get(t34, 0) + 1

    possible = []
    for t34, count in tile_counts.items():
        if count >= TILES_FOR_CLOSED_KAN:
            if player.is_riichi:
                if _kan_preserves_waits_for_riichi(player, t34):
                    possible.append(t34)
            else:
                possible.append(t34)

    return possible


def get_possible_added_kans(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> list[int]:
    """
    Get list of tile_34 values for which player can declare added kan.

    Returns a list of tile_34 indices for pons that can be upgraded.
    """
    if player.is_riichi:
        return []

    if tiles_remaining(round_state.wall) < settings.min_wall_for_kan:
        return []

    if _count_total_kans(round_state) >= settings.max_kans_per_round:
        return []

    possible = []
    for meld in player.melds:
        if meld.type == FrozenMeld.PON:
            meld_tile_34 = tile_to_34(meld.tiles[0])
            if any(tile_to_34(t) == meld_tile_34 for t in player.tiles):
                possible.append(meld_tile_34)

    return possible


def _check_pao(
    player: MahjongPlayer,
    discarder_seat: int,
    called_tile_34: int,
    settings: GameSettings,
) -> int | None:
    """
    Check for pao liability after a meld call (pon, open kan, or added kan).

    Pao triggers when:
    - daisangen_pao_set_threshold dragon sets are completed (Big Three Dragons / daisangen)
    - daisuushii_pao_set_threshold wind sets are completed (Big Four Winds / daisuushii)

    Returns the pao_seat if triggered, None otherwise.
    """
    pao_rules: list[tuple[frozenset[int], int, bool]] = [
        (_DRAGON_TILES, settings.daisangen_pao_set_threshold, settings.has_daisangen_pao),
        (_WIND_TILES, settings.daisuushii_pao_set_threshold, settings.has_daisuushii_pao),
    ]
    for tile_set, threshold, enabled in pao_rules:
        if called_tile_34 not in tile_set:
            continue
        if not enabled:
            continue
        count = sum(1 for m in player.melds if tile_to_34(m.tiles[0]) in tile_set and m.type in _PAO_MELD_TYPES)
        if count + 1 >= threshold:
            return discarder_seat
    return None


def _validate_kan_preconditions(
    round_state: MahjongRoundState,
    settings: GameSettings,
    *,
    reject_riichi: bool = False,
    player: MahjongPlayer | None = None,
    kan_label: str = "kan",
) -> None:
    """Validate common kan preconditions (defense-in-depth guards).

    Raises InvalidMeldError if:
    - reject_riichi is True and the player is in riichi
    - The wall doesn't have enough tiles for a kan replacement draw
    - The maximum kans per round has been reached
    """
    if reject_riichi and player is not None and player.is_riichi:
        raise InvalidMeldError(f"cannot call {kan_label} while in riichi")

    if tiles_remaining(round_state.wall) < settings.min_wall_for_kan:
        raise InvalidMeldError("not enough tiles in wall for kan")

    if _count_total_kans(round_state) >= settings.max_kans_per_round:
        raise InvalidMeldError("maximum kans per round reached")


def _remove_matching_tiles(
    hand: tuple[int, ...],
    tile_34: int,
    count: int,
    meld_name: str,
    seat: int,
) -> tuple[list[int], list[int]]:
    """
    Find and remove up to ``count`` tiles matching ``tile_34`` from hand.

    Return ``(removed_tiles, new_hand)``.
    Raise ``InvalidMeldError`` if fewer than ``count`` matching tiles are found.
    """
    removed_tiles: list[int] = []
    new_hand: list[int] = []
    for t in hand:
        if tile_to_34(t) == tile_34 and len(removed_tiles) < count:
            removed_tiles.append(t)
        else:
            new_hand.append(t)

    if len(removed_tiles) != count:
        logger.warning(
            "cannot call %s for seat %d: need %d matching tiles, found %d",
            meld_name,
            seat,
            count,
            len(removed_tiles),
        )
        raise InvalidMeldError(
            f"cannot call {meld_name}: need {count} matching tiles, found {len(removed_tiles)}",
        )

    return removed_tiles, new_hand


def _finalize_meld_state(
    state: MahjongRoundState,
    caller_seat: int,
    *,
    mark_open: bool,
) -> MahjongRoundState:
    """Apply shared post-meld state updates: track open hand, clear ippatsu, set current player."""
    if mark_open and caller_seat not in state.players_with_open_hands:
        new_open_hands = (*state.players_with_open_hands, caller_seat)
        state = state.model_copy(update={"players_with_open_hands": new_open_hands})

    state = clear_all_players_ippatsu(state)
    return state.model_copy(update={"current_player_seat": caller_seat})


def _handle_kan_dora_and_draw(
    state: MahjongRoundState,
    settings: GameSettings,
    *,
    is_closed_kan: bool,
) -> MahjongRoundState:
    """Handle dora reveal/deferral and dead wall draw for kan declarations."""
    if settings.has_kandora:
        if is_closed_kan:
            if settings.kandora_immediate_for_closed_kan:
                state, _dora_indicator = add_dora_indicator(state)
            else:
                state = state.model_copy(update={"wall": increment_pending_dora(state.wall)})
        elif settings.kandora_deferred_for_open_kan:
            state = state.model_copy(update={"wall": increment_pending_dora(state.wall)})
        else:
            state, _dora_indicator = add_dora_indicator(state)

    state, _drawn_tile = draw_from_dead_wall(state)
    return state


def call_pon(
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
    settings: GameSettings,
) -> tuple[MahjongRoundState, FrozenMeld]:
    """
    Execute a pon call on a discarded tile.

    Removes 2 matching tiles from caller's hand, creates a FrozenMeld object,
    updates game state (open hands, ippatsu flags, current player).
    Returns (new_round_state, created_meld).
    """
    caller = round_state.players[caller_seat]
    tile_34 = tile_to_34(tile_id)

    removed_tiles, new_hand = _remove_matching_tiles(caller.tiles, tile_34, TILES_FOR_PON, "pon", caller_seat)

    # create meld with all 3 tiles (2 from hand + called tile)
    meld_tiles = tuple(sorted([*removed_tiles, tile_id]))
    meld = FrozenMeld(
        meld_type=FrozenMeld.PON,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )

    new_melds = (*caller.melds, meld)

    # check pao liability (before updating state so we can check existing melds)
    pao_seat = _check_pao(caller, discarder_seat, tile_34, settings)

    # set kuikae restriction based on settings
    kuikae_tiles: tuple[int, ...] = ()
    if settings.has_kuikae:
        kuikae_tiles = tuple(get_kuikae_tiles(MeldCallType.PON, tile_34))

    # update player state
    player_updates: dict[str, object] = {
        "tiles": tuple(new_hand),
        "melds": new_melds,
        "kuikae_tiles": kuikae_tiles,
    }
    if pao_seat is not None:
        player_updates["pao_seat"] = pao_seat

    new_state = update_player(round_state, caller_seat, **player_updates)
    new_state = _finalize_meld_state(new_state, caller_seat, mark_open=True)
    # Pon requires a subsequent discard without drawing; mark state for tsumogiri detection
    new_state = new_state.model_copy(update={"is_after_meld_call": True})

    return new_state, meld


def _validate_chi_sequence(tile_id: int, sequence_tiles: tuple[int, int]) -> None:
    """Validate that the called tile and sequence tiles form a consecutive run in one suit.

    Raises InvalidMeldError if:
    - Any tile is an honor tile (chi requires numbered tiles)
    - Tiles span multiple suits
    - Tiles do not form three consecutive values
    """
    all_34 = sorted(tile_to_34(t) for t in (tile_id, *sequence_tiles))
    if any(is_honor(t) for t in all_34):
        raise InvalidMeldError("chi is not allowed with honor tiles")
    suits = {t // TILES_PER_SUIT for t in all_34}
    if len(suits) != 1:
        raise InvalidMeldError("chi tiles must be from the same suit")
    if all_34[1] - all_34[0] != 1 or all_34[2] - all_34[1] != 1:
        raise InvalidMeldError("chi tiles must form a consecutive sequence")


def call_chi(  # noqa: PLR0913
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
    sequence_tiles: tuple[int, int],
    settings: GameSettings,
) -> tuple[MahjongRoundState, FrozenMeld]:
    """
    Execute a chi call on a discarded tile.

    Removes sequence_tiles from caller's hand, creates a FrozenMeld object,
    updates game state (open hands, ippatsu flags, current player).
    Returns (new_round_state, created_meld).
    """
    caller = round_state.players[caller_seat]

    # validate sequence forms a consecutive run in the same suit
    _validate_chi_sequence(tile_id, sequence_tiles)

    # remove sequence tiles from hand
    new_hand = list(caller.tiles)
    for t in sequence_tiles:
        try:
            new_hand.remove(t)
        except ValueError:
            raise InvalidMeldError(f"chi tile {t} not found in hand") from None

    # create meld with all 3 tiles (2 from hand + called tile)
    meld_tiles = tuple(sorted([sequence_tiles[0], sequence_tiles[1], tile_id]))
    meld = FrozenMeld(
        meld_type=FrozenMeld.CHI,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )

    new_melds = (*caller.melds, meld)

    # set kuikae restriction based on settings
    kuikae: list[int] = []
    if settings.has_kuikae:
        called_34 = tile_to_34(tile_id)
        sequence_tiles_34 = [tile_to_34(t) for t in sequence_tiles]
        if settings.has_kuikae_suji:
            kuikae = get_kuikae_tiles(MeldCallType.CHI, called_34, sequence_tiles_34)
        else:
            # only forbid the called tile type (no suji restriction)
            kuikae = [called_34]

    # update player state
    new_state = update_player(
        round_state,
        caller_seat,
        tiles=tuple(new_hand),
        melds=new_melds,
        kuikae_tiles=tuple(kuikae),
    )
    new_state = _finalize_meld_state(new_state, caller_seat, mark_open=True)
    # Chi requires a subsequent discard without drawing; mark state for tsumogiri detection
    new_state = new_state.model_copy(update={"is_after_meld_call": True})

    return new_state, meld


def call_open_kan(
    round_state: MahjongRoundState,
    caller_seat: int,
    discarder_seat: int,
    tile_id: int,
    settings: GameSettings,
) -> tuple[MahjongRoundState, FrozenMeld]:
    """
    Execute an open kan (daiminkan) call on a discarded tile.

    Removes 3 matching tiles from caller's hand, creates a FrozenMeld object,
    updates game state. The caller must draw from dead wall after this.
    Returns (new_round_state, created_meld).
    """
    caller = round_state.players[caller_seat]
    tile_34 = tile_to_34(tile_id)

    _validate_kan_preconditions(
        round_state,
        settings,
        reject_riichi=True,
        player=caller,
        kan_label="open kan",
    )

    removed_tiles, new_hand = _remove_matching_tiles(
        caller.tiles,
        tile_34,
        TILES_FOR_OPEN_KAN,
        "open kan",
        caller_seat,
    )

    # create meld with all 4 tiles (3 from hand + called tile)
    meld_tiles = tuple(sorted([*removed_tiles, tile_id]))
    meld = FrozenMeld(
        meld_type=FrozenMeld.KAN,
        tiles=meld_tiles,
        opened=True,
        called_tile=tile_id,
        who=caller_seat,
        from_who=discarder_seat,
    )

    new_melds = (*caller.melds, meld)

    # check pao liability (before updating state so we can check existing melds)
    pao_seat = _check_pao(caller, discarder_seat, tile_34, settings)

    # update player state
    player_updates: dict[str, object] = {
        "tiles": tuple(new_hand),
        "melds": new_melds,
    }
    if pao_seat is not None:
        player_updates["pao_seat"] = pao_seat

    new_state = update_player(round_state, caller_seat, **player_updates)
    new_state = _finalize_meld_state(new_state, caller_seat, mark_open=True)
    new_state = _handle_kan_dora_and_draw(new_state, settings, is_closed_kan=False)

    return new_state, meld


def call_closed_kan(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
    settings: GameSettings,
) -> tuple[MahjongRoundState, FrozenMeld]:
    """
    Execute a closed kan (ankan) declaration.

    Player declares kan with 4 tiles from hand. The hand remains closed.
    Returns (new_round_state, created_meld).
    """
    player = round_state.players[seat]
    tile_34 = tile_to_34(tile_id)

    # riichi guard: closed kan must preserve waits (stricter than the generic riichi rejection)
    if player.is_riichi and not _kan_preserves_waits_for_riichi(player, tile_34):
        raise InvalidMeldError("closed kan in riichi must not change waiting tiles")

    _validate_kan_preconditions(round_state, settings)

    removed_tiles, new_hand = _remove_matching_tiles(
        player.tiles,
        tile_34,
        TILES_FOR_CLOSED_KAN,
        "closed kan",
        seat,
    )

    # create meld with all 4 tiles (closed kan - opened=False)
    meld_tiles = tuple(sorted(removed_tiles))
    meld = FrozenMeld(
        meld_type=FrozenMeld.KAN,
        tiles=meld_tiles,
        opened=False,
        who=seat,
    )

    new_melds = (*player.melds, meld)

    # update player state
    new_state = update_player(
        round_state,
        seat,
        tiles=tuple(new_hand),
        melds=new_melds,
    )
    # closed kan does NOT make the hand open (mark_open=False)
    new_state = _finalize_meld_state(new_state, seat, mark_open=False)
    new_state = _handle_kan_dora_and_draw(new_state, settings, is_closed_kan=True)

    return new_state, meld


def call_added_kan(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
    settings: GameSettings,
) -> tuple[MahjongRoundState, FrozenMeld]:
    """
    Execute an added kan (shouminkan) declaration.

    Player upgrades an existing pon to a kan by adding the 4th tile.
    Note: This can be robbed by other players (chankan) if they are waiting on this tile.
    Returns (new_round_state, upgraded_meld).
    """
    player = round_state.players[seat]
    tile_34 = tile_to_34(tile_id)

    _validate_kan_preconditions(
        round_state,
        settings,
        reject_riichi=True,
        player=player,
        kan_label="added kan",
    )

    # find the pon meld to upgrade
    pon_meld: FrozenMeld | None = None
    pon_index = -1
    for i, meld in enumerate(player.melds):
        if meld.type == FrozenMeld.PON:
            meld_tile_34 = tile_to_34(meld.tiles[0])
            if meld_tile_34 == tile_34:
                pon_meld = meld
                pon_index = i
                break

    if pon_meld is None:
        logger.warning("cannot call added kan for seat %d: no pon of tile type %d", seat, tile_34)
        raise InvalidMeldError(f"cannot call added kan: no pon of tile type {tile_34}")

    # verify tile is in hand
    if tile_id not in player.tiles:
        logger.warning("cannot call added kan for seat %d: tile %d not in hand", seat, tile_id)
        raise InvalidMeldError(f"cannot call added kan: tile {tile_id} not in hand")

    # remove the 4th tile from hand
    new_hand = list(player.tiles)
    new_hand.remove(tile_id)

    # upgrade the meld from pon to kan (shouminkan)
    new_tiles = tuple(sorted([*pon_meld.tiles, tile_id]))
    upgraded_meld = FrozenMeld(
        meld_type=FrozenMeld.SHOUMINKAN,
        tiles=new_tiles,
        opened=True,
        called_tile=pon_meld.called_tile,
        who=seat,
        from_who=pon_meld.from_who,
    )

    # replace the pon meld with upgraded kan
    new_melds = list(player.melds)
    new_melds[pon_index] = upgraded_meld

    # update player state
    new_state = update_player(
        round_state,
        seat,
        tiles=tuple(new_hand),
        melds=tuple(new_melds),
    )
    # added kan keeps the hand open (already open from the pon), no need to re-mark
    new_state = _finalize_meld_state(new_state, seat, mark_open=False)
    new_state = _handle_kan_dora_and_draw(new_state, settings, is_closed_kan=False)

    return new_state, upgraded_meld
