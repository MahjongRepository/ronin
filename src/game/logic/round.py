"""
Round initialization and management for Mahjong game.
"""

from mahjong.shanten import Shanten

from game.logic.state import Discard, MahjongGameState, MahjongPlayer, MahjongRoundState, RoundPhase
from game.logic.tiles import generate_wall, hand_to_34_array, sort_tiles
from game.logic.types import ExhaustiveDrawResult, SeatConfig

# dead wall constants
DEAD_WALL_SIZE = 14
# dora indicator positions in dead wall: indices 2, 3, 4, 5 (up to 4 dora for kans)
FIRST_DORA_INDEX = 2
MAX_DORA_INDICATORS = 4

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
    Dora indicators are at dead wall indices 2, 3, 4, 5.
    """
    current_count = len(round_state.dora_indicators)
    if current_count >= MAX_DORA_INDICATORS:
        raise ValueError("cannot add more than 4 dora indicators")

    # next dora index: 3, 4, 5 for 2nd, 3rd, 4th dora
    next_index = FIRST_DORA_INDEX + current_count
    new_indicator = round_state.dead_wall[next_index]
    round_state.dora_indicators.append(new_indicator)

    return new_indicator


def create_players(seat_configs: list[SeatConfig]) -> list[MahjongPlayer]:
    """
    Create players from seat configurations.
    """
    return [
        MahjongPlayer(seat=i, name=config.name, is_bot=config.is_bot) for i, config in enumerate(seat_configs)
    ]


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

    Sets the player's is_rinshan flag to True.
    Returns the drawn tile_id.
    """
    # draw from dead wall (from the end, which is the replacement draw area)
    tile = round_state.dead_wall.pop()
    current_player = round_state.players[round_state.current_player_seat]
    current_player.tiles.append(tile)
    current_player.is_rinshan = True

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
        raise ValueError(f"tile {tile_id} not in player's hand")

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

    # clear rinshan flag
    player.is_rinshan = False

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
    Check if player is in tempai (one tile away from winning).

    Uses the mahjong library's shanten calculator. A shanten of 0 means tempai.
    Accounts for melds by only considering tiles currently in hand.

    If player has 14 tiles (after drawing), checks if any discard leaves them in tempai.
    If player has 13 tiles (waiting), directly checks shanten.
    """
    tiles = player.tiles
    shanten = Shanten()

    if len(tiles) == HAND_SIZE_AFTER_DRAW:
        # after drawing, check if any discard leaves us in tempai
        for i in range(len(tiles)):
            remaining = tiles[:i] + tiles[i + 1 :]
            tiles_34 = hand_to_34_array(remaining)
            if shanten.calculate_shanten(tiles_34) == 0:
                return True
        return False

    tiles_34 = hand_to_34_array(tiles)
    shanten_value = shanten.calculate_shanten(tiles_34)
    return shanten_value == 0


def process_exhaustive_draw(round_state: MahjongRoundState) -> ExhaustiveDrawResult:
    """
    Process an exhaustive draw (wall empty, no winner).

    Calculates noten payments: 3000 points total split from noten players to tempai players.
    - If all 4 tempai or all 4 noten: no payment
    - 1 tempai, 3 noten: each noten pays 1000 to tempai
    - 2 tempai, 2 noten: each noten pays 1500 to each tempai (750 each)
    - 3 tempai, 1 noten: noten pays 1000 to each tempai
    """
    tempai_seats = []
    noten_seats = []

    for player in round_state.players:
        if is_tempai(player):
            tempai_seats.append(player.seat)
        else:
            noten_seats.append(player.seat)

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
