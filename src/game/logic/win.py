"""
Win detection and scoring for Mahjong game.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mahjong.agari import Agari
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.shanten import Shanten

from game.logic.tiles import hand_to_34_array, tile_to_34

if TYPE_CHECKING:
    from mahjong.meld import Meld

    from game.logic.state import MahjongGameState, MahjongPlayer, MahjongRoundState


@dataclass
class HandResult:
    """
    Result of hand value calculation.
    """

    han: int = 0
    fu: int = 0
    cost_main: int = 0  # cost paid by dealer (tsumo) or loser (ron)
    cost_additional: int = 0  # cost paid by non-dealers (tsumo only)
    yaku: list[str] = field(default_factory=list)  # list of yaku names
    error: str | None = None  # error message if calculation failed


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
        if tiles_34[tile_34] >= 4:
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
        player_wind=_seat_to_wind(player.seat, round_state.dealer_seat),
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
        player_wind=_seat_to_wind(player.seat, round_state.dealer_seat),
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


def _seat_to_wind(seat: int, dealer_seat: int) -> int:
    """
    Calculate player's wind based on seat position relative to dealer.

    Dealer is always East (0), and winds rotate counter-clockwise from there.
    """
    # wind offset from dealer: dealer=East(0), dealer+1=South(1), etc.
    return (seat - dealer_seat) % 4


# ura dora indices in dead wall (after the dora indicators)
# dora indicators at 2, 3, 4, 5; ura dora at 9, 10, 11, 12
URA_DORA_START_INDEX = 9


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


def calculate_hand_value(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    win_tile: int,
    *,
    is_tsumo: bool,
    is_chankan: bool = False,
) -> HandResult:
    """
    Calculate the value of a winning hand using the mahjong library's HandCalculator.

    Builds HandConfig with all relevant flags and OptionalRules for scoring.
    Returns a HandResult with han, fu, cost breakdown, and yaku list.
    """
    # build optional rules
    options = OptionalRules(
        has_aka_dora=True,  # red fives enabled
        has_open_tanyao=True,  # kuitan enabled
        has_double_yakuman=False,  # single yakuman max
    )

    # determine special conditions using standalone functions
    haitei_flag = is_tsumo and is_haitei(round_state)
    houtei_flag = not is_tsumo and is_houtei(round_state)
    tenhou_flag = is_tsumo and is_tenhou(player, round_state)
    chiihou_flag = is_tsumo and is_chiihou(player, round_state)

    config = HandConfig(
        is_tsumo=is_tsumo,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        is_chankan=is_chankan,
        is_haitei=haitei_flag,
        is_houtei=houtei_flag,
        is_tenhou=tenhou_flag,
        is_chiihou=chiihou_flag,
        player_wind=_seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=round_state.round_wind,
        options=options,
    )

    # get dora indicators
    dora_indicators = list(round_state.dora_indicators) if round_state.dora_indicators else None

    # get ura dora if riichi (one ura per dora indicator revealed)
    if player.is_riichi and round_state.dead_wall:
        num_ura = len(round_state.dora_indicators)
        ura_indicators = []
        for i in range(num_ura):
            ura_index = URA_DORA_START_INDEX + i
            if ura_index < len(round_state.dead_wall):
                ura_indicators.append(round_state.dead_wall[ura_index])
        if ura_indicators:
            if dora_indicators is None:
                dora_indicators = []
            dora_indicators.extend(ura_indicators)

    calculator = HandCalculator()
    result = calculator.estimate_hand_value(
        tiles=list(player.tiles),
        win_tile=win_tile,
        melds=player.melds if player.melds else None,
        dora_indicators=dora_indicators,
        config=config,
    )

    if result.error:
        return HandResult(error=result.error)

    # extract yaku names
    yaku_list = [str(y) for y in result.yaku] if result.yaku else []

    return HandResult(
        han=result.han,
        fu=result.fu,
        cost_main=result.cost["main"] if result.cost else 0,
        cost_additional=result.cost["additional"] if result.cost else 0,
        yaku=yaku_list,
    )


def apply_tsumo_score(
    game_state: MahjongGameState,
    winner_seat: int,
    hand_result: HandResult,
) -> dict:
    """
    Apply score changes for a tsumo win.

    Payment structure:
    - If winner is dealer: each non-dealer pays main_cost
    - If winner is non-dealer: dealer pays main_cost, others pay additional_cost
    - Winner also gets: riichi_sticks * 1000 + honba * 300
    - Each loser pays: +honba/3 bonus (300 total = 100 per loser)
    """
    round_state = game_state.round_state
    is_dealer_win = winner_seat == round_state.dealer_seat

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    # honba bonus: 100 per loser (300 total split among 3 losers)
    honba_bonus_per_loser = game_state.honba_sticks * 100

    total_payment = 0
    for seat in range(4):
        if seat == winner_seat:
            continue

        if is_dealer_win:
            # dealer tsumo: everyone pays main_cost
            payment = hand_result.cost_main + honba_bonus_per_loser
        elif seat == round_state.dealer_seat:
            # non-dealer tsumo: dealer pays main
            payment = hand_result.cost_main + honba_bonus_per_loser
        else:
            # non-dealer tsumo: non-dealers pay additional
            payment = hand_result.cost_additional + honba_bonus_per_loser

        score_changes[seat] = -payment
        total_payment += payment

    # winner receives total + riichi sticks
    riichi_bonus = game_state.riichi_sticks * 1000
    score_changes[winner_seat] = total_payment + riichi_bonus

    # apply score changes
    for seat, change in score_changes.items():
        round_state.players[seat].score += change

    # clear riichi sticks
    game_state.riichi_sticks = 0

    return {
        "type": "tsumo",
        "winner_seat": winner_seat,
        "hand_result": {
            "han": hand_result.han,
            "fu": hand_result.fu,
            "yaku": hand_result.yaku,
        },
        "score_changes": score_changes,
        "riichi_sticks_collected": riichi_bonus // 1000,
    }


def apply_ron_score(
    game_state: MahjongGameState,
    winner_seat: int,
    loser_seat: int,
    hand_result: HandResult,
) -> dict:
    """
    Apply score changes for a ron win.

    Payment structure:
    - Loser pays: main_cost + honba * 300
    - Winner gets: main_cost + riichi_sticks * 1000 + honba * 300
    """
    round_state = game_state.round_state

    # honba bonus: 300 total from loser
    honba_bonus = game_state.honba_sticks * 300

    payment = hand_result.cost_main + honba_bonus
    riichi_bonus = game_state.riichi_sticks * 1000

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    score_changes[loser_seat] = -payment
    score_changes[winner_seat] = payment + riichi_bonus

    # apply score changes
    for seat, change in score_changes.items():
        round_state.players[seat].score += change

    # clear riichi sticks
    game_state.riichi_sticks = 0

    return {
        "type": "ron",
        "winner_seat": winner_seat,
        "loser_seat": loser_seat,
        "hand_result": {
            "han": hand_result.han,
            "fu": hand_result.fu,
            "yaku": hand_result.yaku,
        },
        "score_changes": score_changes,
        "riichi_sticks_collected": riichi_bonus // 1000,
    }


def apply_double_ron_score(
    game_state: MahjongGameState,
    winners: list[tuple[int, HandResult]],  # list of (seat, hand_result)
    loser_seat: int,
) -> dict:
    """
    Apply score changes for a double ron (two players winning on the same discard).

    Payment structure:
    - Loser pays each winner separately: main_cost + honba * 300
    - Riichi sticks go to winner closest to loser's right (counter-clockwise)
    """
    round_state = game_state.round_state

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    honba_bonus = game_state.honba_sticks * 300
    riichi_bonus = game_state.riichi_sticks * 1000

    # determine who gets riichi sticks: winner closest to loser's right (counter-clockwise)
    # order is: loser_seat -> loser_seat+1 -> loser_seat+2 -> loser_seat+3
    winner_seats = [w[0] for w in winners]
    riichi_receiver = None
    for offset in range(1, 4):
        check_seat = (loser_seat + offset) % 4
        if check_seat in winner_seats:
            riichi_receiver = check_seat
            break

    results = []
    total_loser_payment = 0

    for winner_seat, hand_result in winners:
        payment = hand_result.cost_main + honba_bonus
        total_loser_payment += payment

        winner_total = payment
        if winner_seat == riichi_receiver:
            winner_total += riichi_bonus

        score_changes[winner_seat] += winner_total

        results.append(
            {
                "winner_seat": winner_seat,
                "hand_result": {
                    "han": hand_result.han,
                    "fu": hand_result.fu,
                    "yaku": hand_result.yaku,
                },
                "riichi_sticks_collected": riichi_bonus // 1000 if winner_seat == riichi_receiver else 0,
            }
        )

    score_changes[loser_seat] = -total_loser_payment

    # apply score changes
    for seat, change in score_changes.items():
        round_state.players[seat].score += change

    # clear riichi sticks
    game_state.riichi_sticks = 0

    return {
        "type": "double_ron",
        "loser_seat": loser_seat,
        "winners": results,
        "score_changes": score_changes,
    }
