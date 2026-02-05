"""
Round initialization and management for Mahjong game.
"""

import logging

from mahjong.agari import Agari
from mahjong.shanten import Shanten

from game.logic.enums import RoundPhase
from game.logic.scoring import apply_nagashi_mangan_score
from game.logic.state import Discard, MahjongGameState, MahjongPlayer, MahjongRoundState
from game.logic.tiles import generate_wall, hand_to_34_array, is_terminal_or_honor, sort_tiles, tile_to_34
from game.logic.types import ExhaustiveDrawResult, NagashiManganResult, SeatConfig
from game.logic.win import MAX_TILE_COPIES

logger = logging.getLogger(__name__)

# dead wall constants
DEAD_WALL_SIZE = 14
# dora indicator positions in dead wall: indices 2, 3, 4, 5, 6 (initial + up to 4 for kans)
FIRST_DORA_INDEX = 2
MAX_DORA_INDICATORS = 5

# hand size constants
HAND_SIZE_AFTER_DRAW = 14


def init_round(game_state: MahjongGameState) -> None:
    """
    Initialize a new round by generating wall, dealing tiles, and setting up dora.

    Modifies game_state.round_state in place.
    """
    round_state = game_state.round_state

    # generate wall using seed + round_number
    wall = generate_wall(game_state.seed, game_state.round_number)

    # cut dead wall (14 tiles from end)
    dead_wall = wall[-DEAD_WALL_SIZE:]
    wall = wall[:-DEAD_WALL_SIZE]

    # set up walls
    round_state.wall = wall
    round_state.dead_wall = dead_wall

    # set first dora indicator (dead_wall[2])
    round_state.dora_indicators = [dead_wall[FIRST_DORA_INDEX]]

    # reset player states for new round
    _reset_players(round_state)

    # deal tiles: each player draws 4 tiles x 3, then 1 more (total 13 each)
    _deal_tiles(round_state)

    # sort each player's hand
    for player in round_state.players:
        player.tiles = sort_tiles(player.tiles)

    # set current player to dealer
    round_state.current_player_seat = round_state.dealer_seat

    # reset round tracking
    round_state.turn_count = 0
    round_state.all_discards = []
    round_state.players_with_open_hands = []
    round_state.pending_dora_count = 0
    round_state.pending_call_prompt = None

    # set phase to playing
    round_state.phase = RoundPhase.PLAYING


def _reset_players(round_state: MahjongRoundState) -> None:
    """
    Reset player states for a new round.
    """
    for player in round_state.players:
        player.tiles = []
        player.discards = []
        player.melds = []
        player.is_riichi = False
        player.is_ippatsu = False
        player.is_daburi = False
        player.is_rinshan = False
        player.kuikae_tiles = []
        player.pao_seat = None
        player.is_temporary_furiten = False
        player.is_riichi_furiten = False


def _deal_tiles(round_state: MahjongRoundState) -> None:
    """
    Deal tiles to players following standard dealing order.

    Each player draws 4 tiles x 3 rounds, then 1 more (total 13).
    Dealing starts from dealer and goes counter-clockwise.
    """
    dealer = round_state.dealer_seat

    # deal 4 tiles x 3 rounds
    for _ in range(3):
        for i in range(4):
            seat = (dealer + i) % 4
            player = round_state.players[seat]
            for _ in range(4):
                tile = round_state.wall.pop(0)
                player.tiles.append(tile)

    # deal 1 more tile to each player
    for i in range(4):
        seat = (dealer + i) % 4
        player = round_state.players[seat]
        tile = round_state.wall.pop(0)
        player.tiles.append(tile)


def add_dora_indicator(round_state: MahjongRoundState) -> int:
    """
    Reveal the next dora indicator from dead wall.

    Called after a kan is declared. Returns the tile_id of the new indicator.
    Dora indicators are at dead wall indices 2, 3, 4, 5, 6.
    """
    current_count = len(round_state.dora_indicators)
    if current_count >= MAX_DORA_INDICATORS:
        logger.error(
            f"cannot add more than {MAX_DORA_INDICATORS} dora indicators, current count: {current_count}"
        )
        raise ValueError("cannot add more than 5 dora indicators")

    # next dora index: 3, 4, 5, 6 for 2nd, 3rd, 4th, 5th dora
    next_index = FIRST_DORA_INDEX + current_count
    new_indicator = round_state.dead_wall[next_index]
    round_state.dora_indicators.append(new_indicator)

    return new_indicator


def reveal_pending_dora(round_state: MahjongRoundState) -> list[int]:
    """
    Reveal any pending dora indicators queued by open/added kan.

    Called after a discard to implement the rule that open and added kan
    dora indicators are revealed after the replacement tile is discarded,
    not immediately when the kan is declared.

    Returns list of newly revealed dora indicator tile_ids.
    """
    revealed: list[int] = []
    while round_state.pending_dora_count > 0:
        new_indicator = add_dora_indicator(round_state)
        revealed.append(new_indicator)
        round_state.pending_dora_count -= 1
    return revealed


def create_players(seat_configs: list[SeatConfig]) -> list[MahjongPlayer]:
    """
    Create players from seat configurations.
    """
    return [MahjongPlayer(seat=i, name=config.name) for i, config in enumerate(seat_configs)]


def draw_tile(round_state: MahjongRoundState) -> int | None:
    """
    Draw a tile from the wall for the current player.

    Returns the drawn tile_id, or None if wall is empty.
    """
    if not round_state.wall:
        return None

    tile = round_state.wall.pop(0)
    current_player = round_state.players[round_state.current_player_seat]
    current_player.tiles.append(tile)

    return tile


def draw_from_dead_wall(round_state: MahjongRoundState) -> int:
    """
    Draw a replacement tile from the dead wall after kan.

    After drawing, replenishes the dead wall by moving the last tile
    from the live wall to maintain 14 dead wall tiles.
    Sets the player's is_rinshan flag to True.
    Returns the drawn tile_id.
    """
    # draw from dead wall (from the end, which is the replacement draw area)
    tile = round_state.dead_wall.pop()
    current_player = round_state.players[round_state.current_player_seat]
    current_player.tiles.append(tile)
    current_player.is_rinshan = True

    # replenish dead wall from live wall (append to maintain dora indicator positions at front)
    if round_state.wall:
        replenish_tile = round_state.wall.pop()
        round_state.dead_wall.append(replenish_tile)

    return tile


def discard_tile(
    round_state: MahjongRoundState,
    seat: int,
    tile_id: int,
    *,
    is_riichi: bool = False,
) -> Discard:
    """
    Discard a tile from a player's hand.

    Validates the tile is in hand, removes it, creates a Discard record,
    and updates game state appropriately.
    """
    player = round_state.players[seat]

    if tile_id not in player.tiles:
        logger.warning(f"seat {seat} tried to discard tile {tile_id} not in hand, hand={player.tiles}")
        raise ValueError(f"tile {tile_id} not in player's hand")

    # validate kuikae restriction
    if player.kuikae_tiles and tile_to_34(tile_id) in player.kuikae_tiles:
        logger.warning(f"seat {seat} tried to discard tile {tile_id} forbidden by kuikae restriction")
        raise ValueError(f"tile {tile_id} is forbidden by kuikae restriction")

    # check if this is tsumogiri (discarding the just-drawn tile)
    # the drawn tile is always the last tile in hand (appended by draw_tile)
    is_tsumogiri = len(player.tiles) > 0 and player.tiles[-1] == tile_id

    # remove tile from hand
    player.tiles.remove(tile_id)

    # create discard record
    discard = Discard(
        tile_id=tile_id,
        is_tsumogiri=is_tsumogiri,
        is_riichi_discard=is_riichi,
    )
    player.discards.append(discard)

    # track in all_discards for four winds check
    round_state.all_discards.append(tile_id)

    # clear ippatsu only for the discarding player
    # (their ippatsu window ends when they discard, others' ippatsu is cleared on meld calls)
    player.is_ippatsu = False

    # clear temporary furiten (resets each time the player discards)
    player.is_temporary_furiten = False

    # clear rinshan flag
    player.is_rinshan = False

    # clear kuikae restriction after discard
    player.kuikae_tiles = []

    return discard


def advance_turn(round_state: MahjongRoundState) -> int:
    """
    Advance to the next player's turn (counter-clockwise: 0->1->2->3->0).

    Returns the new current player seat.
    """
    round_state.current_player_seat = (round_state.current_player_seat + 1) % 4
    round_state.turn_count += 1
    return round_state.current_player_seat


def check_exhaustive_draw(round_state: MahjongRoundState) -> bool:
    """
    Check if the wall is exhausted (no more tiles to draw).

    Returns True if wall is empty, indicating an exhaustive draw condition.
    """
    return len(round_state.wall) == 0


def is_tempai(player: MahjongPlayer) -> bool:
    """
    Check if player is in tenpai (one tile away from winning).

    Accepts keishiki tenpai (formal/structural tenpai) where winning tiles may
    be unavailable in the wall or other players' hands.
    Exception: pure karaten (all copies of all winning tiles are in the
    player's own hand + melds) is NOT considered tenpai.

    If player has 14 tiles (after drawing), checks if any discard leaves them in tenpai.
    If player has 13 tiles (waiting), directly checks shanten.
    """
    tiles = player.tiles
    shanten = Shanten()

    if len(tiles) == HAND_SIZE_AFTER_DRAW:
        # after drawing, check if any discard leaves us in tenpai (excluding pure karaten)
        original_tiles = list(player.tiles)
        try:
            for i in range(len(original_tiles)):
                remaining = original_tiles[:i] + original_tiles[i + 1 :]
                tiles_34 = hand_to_34_array(remaining)
                if shanten.calculate_shanten(tiles_34) == 0:
                    # check pure karaten with the remaining tiles
                    player.tiles = remaining
                    if not _is_pure_karaten(player):
                        return True
            return False
        finally:
            player.tiles = original_tiles

    tiles_34 = hand_to_34_array(tiles)
    if shanten.calculate_shanten(tiles_34) != 0:
        return False

    return not _is_pure_karaten(player)


def _is_pure_karaten(player: MahjongPlayer) -> bool:
    """
    Check if all winning tiles are entirely in the player's own hand + melds.

    Pure karaten means the player holds all 4 copies of every tile they are
    waiting on. This is not considered valid tenpai.
    """
    waiting = _get_hand_waiting_tiles(player.tiles)
    if not waiting:
        return True  # no waiting tiles at all

    # count tiles in player's hand + melds
    tile_counts = hand_to_34_array(player.tiles)
    for meld in player.melds:
        if meld.tiles:
            for t in meld.tiles:
                tile_counts[tile_to_34(t)] += 1

    # pure karaten: ALL waiting tiles have all 4 copies in player's possession
    return all(tile_counts[t34] >= MAX_TILE_COPIES for t34 in waiting)


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
    agari = Agari()
    for tile_34 in range(34):
        if tiles_34[tile_34] >= MAX_TILE_COPIES:
            continue
        tiles_34[tile_34] += 1
        if agari.is_agari(tiles_34, None):
            waiting.add(tile_34)
        tiles_34[tile_34] -= 1

    return waiting


def check_nagashi_mangan(round_state: MahjongRoundState) -> list[int]:
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


def process_exhaustive_draw(game_state: MahjongGameState) -> ExhaustiveDrawResult | NagashiManganResult:
    """
    Process an exhaustive draw (wall empty, no winner).

    Checks for nagashi mangan first. If any player qualifies, delegates to
    apply_nagashi_mangan_score(). Otherwise calculates noten payments:
    3000 points total split from noten players to tempai players.
    - If all 4 tempai or all 4 noten: no payment
    - 1 tempai, 3 noten: each noten pays 1000 to tempai
    - 2 tempai, 2 noten: each noten pays 1500 to each tempai (750 each)
    - 3 tempai, 1 noten: noten pays 1000 to each tempai
    """
    round_state = game_state.round_state

    # compute tempai/noten (used by both nagashi mangan and normal exhaustive draw)
    tempai_seats = []
    noten_seats = []

    for player in round_state.players:
        if is_tempai(player):
            tempai_seats.append(player.seat)
        else:
            noten_seats.append(player.seat)

    # check nagashi mangan first
    qualifying = check_nagashi_mangan(round_state)
    if qualifying:
        return apply_nagashi_mangan_score(game_state, qualifying, tempai_seats, noten_seats)

    score_changes = {0: 0, 1: 0, 2: 0, 3: 0}

    # calculate noten payments (3000 total split)
    tempai_count = len(tempai_seats)
    noten_count = len(noten_seats)

    if tempai_count > 0 and noten_count > 0:
        # total 3000 points transferred from noten to tempai
        total_payment = 3000
        payment_per_noten = total_payment // noten_count
        payment_per_tempai = total_payment // tempai_count

        for seat in noten_seats:
            score_changes[seat] = -payment_per_noten

        for seat in tempai_seats:
            score_changes[seat] = payment_per_tempai

    # apply score changes to players
    for player in round_state.players:
        player.score += score_changes[player.seat]

    return ExhaustiveDrawResult(
        tempai_seats=tempai_seats,
        noten_seats=noten_seats,
        score_changes=score_changes,
    )
