"""
Scoring calculation for Mahjong game.

Handles hand value calculation and score application for wins (tsumo, ron, double ron).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules

from game.logic.state import seat_to_wind
from game.logic.win import is_chiihou, is_haitei, is_houtei, is_tenhou

if TYPE_CHECKING:
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


# ura dora indices in dead wall (after the dora indicators)
# dora indicators at 2, 3, 4, 5; ura dora at 9, 10, 11, 12
URA_DORA_START_INDEX = 9


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
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
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
