"""
Round initialization and management for Mahjong game.
"""

from __future__ import annotations

import structlog
from mahjong.agari import Agari

from game.logic import wall as wall_ops
from game.logic.exceptions import InvalidDiscardError
from game.logic.meld_compact import frozen_meld_to_compact
from game.logic.scoring import apply_nagashi_mangan_score
from game.logic.settings import NUM_PLAYERS
from game.logic.shanten import calculate_shanten
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongRoundState,
)
from game.logic.state_utils import (
    add_discard_to_player,
    add_tile_to_player,
    remove_tile_from_player,
    update_all_discards,
    update_player,
)
from game.logic.tiles import NUM_TILE_TYPES, hand_to_34_array, is_terminal_or_honor, tile_to_34
from game.logic.types import ExhaustiveDrawResult, NagashiManganResult, TenpaiHand
from game.logic.win import MAX_TILE_COPIES

logger = structlog.get_logger()

# hand size constants
HAND_SIZE_AFTER_DRAW = 14


def check_exhaustive_draw(round_state: MahjongRoundState) -> bool:
    """
    Check if the wall is exhausted (no more tiles to draw).

    Returns True if wall is empty, indicating an exhaustive draw condition.
    """
    return wall_ops.is_wall_exhausted(round_state.wall)


def _get_hand_waiting_tiles(tiles: list[int]) -> set[int]:
    """
    Find waiting tiles based on hand tiles only (ignoring melds for agari check).

    Uses agari.is_agari without open_sets since the mahjong library's agari
    checker expects meld tiles to be included in the tiles_34 array when
    open_sets is provided. For tenpai/karaten checks, we only have hand tiles
    (excluding melds), so passing None is correct.
    """
    tiles_34 = hand_to_34_array(tiles)
    waiting = set()
    for tile_34 in range(NUM_TILE_TYPES):
        if tiles_34[tile_34] >= MAX_TILE_COPIES:
            continue
        tiles_34[tile_34] += 1
        if Agari.is_agari(tiles_34, None):
            waiting.add(tile_34)
        tiles_34[tile_34] -= 1

    return waiting


def draw_tile(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, int | None]:
    """
    Draw a tile from the wall for the current player.

    Returns (new_round_state, drawn_tile).
    Returns (unchanged_state, None) if wall is empty.
    """
    new_wall, tile = wall_ops.draw_tile(round_state.wall)
    if tile is None:
        return round_state, None

    new_state = round_state.model_copy(update={"wall": new_wall})
    new_state = add_tile_to_player(new_state, new_state.current_player_seat, tile)
    return new_state, tile


def discard_tile(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> tuple[MahjongRoundState, Discard]:
    """
    Discard a tile from a player's hand.

    Returns (new_round_state, discard_record).
    Raises InvalidDiscardError if tile not in hand or violates kuikae.
    """
    player = round_state.players[seat]

    if tile_id not in player.tiles:
        logger.warning("discard tile not in hand", seat=seat, tile_id=tile_id)
        raise InvalidDiscardError(f"tile {tile_id} not in player's hand")

    # validate kuikae restriction
    if player.kuikae_tiles and tile_to_34(tile_id) in player.kuikae_tiles:
        logger.warning("discard forbidden by kuikae restriction", seat=seat, tile_id=tile_id)
        raise InvalidDiscardError(f"tile {tile_id} is forbidden by kuikae restriction")

    # Tsumogiri: discarding the just-drawn tile (last in hand).
    # After a meld call (pon/chi), no tile was drawn, so tsumogiri is impossible.
    is_tsumogiri = not round_state.is_after_meld_call and player.tiles[-1] == tile_id

    # create discard record
    discard = Discard(
        tile_id=tile_id,
        is_tsumogiri=is_tsumogiri,
        is_riichi_discard=is_riichi,
    )

    # build new state
    new_state = remove_tile_from_player(round_state, seat, tile_id)
    new_state = add_discard_to_player(new_state, seat, discard)
    new_state = update_all_discards(new_state, tile_id)

    # clear player and round flags
    new_state = update_player(
        new_state,
        seat,
        is_ippatsu=False,
        is_temporary_furiten=False,
        is_rinshan=False,
        kuikae_tiles=(),
    )
    if round_state.is_after_meld_call:
        new_state = new_state.model_copy(update={"is_after_meld_call": False})

    return new_state, discard


def add_dora_indicator(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, int]:
    """
    Reveal the next dora indicator from dead wall.

    Called after a kan is declared. Returns (new_state, new_indicator_tile_id).
    Dora indicators are at dead wall indices 2, 3, 4, 5, 6.
    """
    new_wall, indicator = wall_ops.add_dora_indicator(round_state.wall)
    new_state = round_state.model_copy(update={"wall": new_wall})
    return new_state, indicator


def reveal_pending_dora(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, list[int]]:
    """
    Reveal any pending dora indicators queued by open/added kan.

    Called after a discard to implement the rule that open and added kan
    dora indicators are revealed after the replacement tile is discarded,
    not immediately when the kan is declared.

    Returns (new_state, list_of_newly_revealed_dora_indicator_tile_ids).
    """
    new_wall, revealed = wall_ops.reveal_pending_dora(round_state.wall)
    new_state = round_state.model_copy(update={"wall": new_wall})
    return new_state, revealed


def draw_from_dead_wall(
    round_state: MahjongRoundState,
) -> tuple[MahjongRoundState, int]:
    """
    Draw a replacement tile from the dead wall after kan.

    After drawing, replenishes the dead wall by moving the last tile
    from the live wall to maintain 14 dead wall tiles.
    Sets the player's is_rinshan flag to True.
    Returns (new_state, drawn_tile).
    """
    new_wall, tile = wall_ops.draw_from_dead_wall(round_state.wall)

    current_seat = round_state.current_player_seat
    new_state = round_state.model_copy(update={"wall": new_wall})
    new_state = add_tile_to_player(new_state, current_seat, tile)
    new_state = update_player(new_state, current_seat, is_rinshan=True)

    return new_state, tile


def is_tempai(
    tiles: tuple[int, ...] | list[int],
    melds: tuple | list,
) -> bool:
    """
    Check if the given tiles are in tenpai (one tile away from winning).

    Uses local tile copies. Accepts keishiki tenpai (formal/structural
    tenpai) where winning tiles may be unavailable in the wall or other players'
    hands. Exception: pure karaten (all copies of all winning tiles are in the
    player's own hand + melds) is NOT considered tenpai.

    Args:
        tiles: The player's hand tiles (13 or 14 tiles).
        melds: The player's melds (for karaten check).

    Returns:
        True if the hand is in tenpai, False otherwise.

    """
    tiles_list = list(tiles)

    if len(tiles_list) == HAND_SIZE_AFTER_DRAW:
        # after drawing, check if any discard leaves us in tenpai (excluding pure karaten)
        for i in range(len(tiles_list)):
            remaining = tiles_list[:i] + tiles_list[i + 1 :]
            tiles_34 = hand_to_34_array(remaining)
            # check if in tenpai and not pure karaten
            if calculate_shanten(tiles_34) == 0 and not _is_pure_karaten(remaining, melds):
                return True
        return False

    tiles_34 = hand_to_34_array(tiles_list)
    if calculate_shanten(tiles_34) != 0:
        return False

    return not _is_pure_karaten(tiles_list, melds)


def _is_pure_karaten(
    tiles: list[int],
    melds: tuple | list,
) -> bool:
    """
    Check if all winning tiles are entirely in the player's own hand + melds.

    Uses local tile and meld lists rather than player object.
    Pure karaten means the player holds all 4 copies of every tile they are
    waiting on. This is not considered valid tenpai.
    """
    waiting = _get_hand_waiting_tiles(tiles)
    if not waiting:
        return True  # no waiting tiles at all  # pragma: no cover

    # count tiles in player's hand + melds
    tile_counts = hand_to_34_array(tiles)
    for meld in melds:
        for t in meld.tiles:
            tile_counts[tile_to_34(t)] += 1

    # pure karaten: ALL waiting tiles have all 4 copies in player's possession
    return all(tile_counts[t34] >= MAX_TILE_COPIES for t34 in waiting)


def process_exhaustive_draw(
    game_state: MahjongGameState,
) -> tuple[
    MahjongRoundState,
    MahjongGameState,
    ExhaustiveDrawResult | NagashiManganResult,
]:
    """
    Process an exhaustive draw (wall empty, no winner).

    Checks for nagashi mangan first. If any player qualifies, delegates to
    apply_nagashi_mangan_score(). Otherwise calculates noten payments:
    3000 points total split from noten players to tempai players.
    - If all 4 tempai or all 4 noten: no payment
    - 1 tempai, 3 noten: each noten pays 1000, tempai receives 3000
    - 2 tempai, 2 noten: each noten pays 1500, each tempai receives 1500
    - 3 tempai, 1 noten: noten pays 3000, each tempai receives 1000
    """
    round_state = game_state.round_state

    # compute tempai/noten (used by both nagashi mangan and normal exhaustive draw)
    tempai_seats = []
    noten_seats = []
    tenpai_hands = []

    for player in round_state.players:
        if is_tempai(player.tiles, player.melds):
            tempai_seats.append(player.seat)
            tenpai_hands.append(
                TenpaiHand(
                    seat=player.seat,
                    closed_tiles=list(player.tiles),
                    melds=[frozen_meld_to_compact(m) for m in player.melds],
                ),
            )
        else:
            noten_seats.append(player.seat)

    # check nagashi mangan first
    settings = game_state.settings
    if settings.has_nagashi_mangan:
        qualifying = check_nagashi_mangan(round_state)
        if qualifying:
            return apply_nagashi_mangan_score(game_state, qualifying, tempai_seats, noten_seats, tenpai_hands)

    scores = {p.seat: p.score for p in round_state.players}
    score_changes: dict[int, int] = dict.fromkeys(range(NUM_PLAYERS), 0)

    # calculate noten payments
    tempai_count = len(tempai_seats)
    noten_count = len(noten_seats)

    if tempai_count > 0 and noten_count > 0:
        total_payment = settings.noten_penalty_total
        payment_per_noten = total_payment // noten_count
        payment_per_tempai = total_payment // tempai_count

        for seat in noten_seats:
            score_changes[seat] = -payment_per_noten

        for seat in tempai_seats:
            score_changes[seat] = payment_per_tempai

    # apply score changes to create new round state
    new_round_state = round_state
    for seat, change in score_changes.items():
        player = new_round_state.players[seat]
        new_round_state = update_player(new_round_state, seat, score=player.score + change)

    # update game state with new round state
    new_game_state = game_state.model_copy(update={"round_state": new_round_state})

    return (
        new_round_state,
        new_game_state,
        ExhaustiveDrawResult(
            tempai_seats=tempai_seats,
            noten_seats=noten_seats,
            tenpai_hands=tenpai_hands,
            scores=scores,
            score_changes=score_changes,
        ),
    )


def check_nagashi_mangan(
    round_state: MahjongRoundState,
) -> list[int]:
    """
    Check which players qualify for nagashi mangan at exhaustive draw.

    Requirements:
    - All discards are terminals or honors
    - None of the player's discards were claimed by opponents

    Returns list of qualifying seat numbers.
    """
    qualifying = []
    for player in round_state.players:
        if not player.discards:
            continue

        # check all discards are terminal/honor
        all_terminal_honor = all(is_terminal_or_honor(tile_to_34(d.tile_id)) for d in player.discards)
        if not all_terminal_honor:
            continue

        # check none of the discards were claimed
        # a claimed discard means another player has a meld with from_who == player.seat
        was_claimed = False
        for other in round_state.players:
            if other.seat == player.seat:
                continue
            for meld in other.melds:
                if meld.from_who == player.seat:
                    was_claimed = True
                    break
            if was_claimed:
                break

        if not was_claimed:
            qualifying.append(player.seat)

    return qualifying
