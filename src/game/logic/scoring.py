"""
Scoring calculation for Mahjong game.

Handles hand value calculation and score application for wins (tsumo, ron, double ron).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig

from game.logic.meld_wrapper import frozen_melds_to_melds
from game.logic.settings import GameSettings, RenhouValue, build_optional_rules
from game.logic.state import seat_to_wind
from game.logic.state_utils import update_player
from game.logic.tiles import WINDS_34, hand_to_34_array
from game.logic.types import (
    DoubleRonResult,
    DoubleRonWinner,
    HandResultInfo,
    NagashiManganResult,
    RonResult,
    TsumoResult,
)
from game.logic.utils import _hand_config_debug, _melds_debug
from game.logic.win import (
    all_player_tiles,
    is_chiihou,
    is_haitei,
    is_houtei,
    is_renhou,
    is_tenhou,
)

if TYPE_CHECKING:
    from game.logic.state import (
        MahjongGameState,
        MahjongPlayer,
        MahjongRoundState,
    )

logger = logging.getLogger(__name__)


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


# dead wall layout (14 tiles as 7 stacks of 2):
# top row:    [0] [1] [2] [3] [4] [5] [6]
# bottom row: [7] [8] [9] [10] [11] [12] [13]
# dora indicators: top row indices 2, 3, 4, 5, 6
# ura dora: bottom row beneath each indicator: indices 7, 8, 9, 10, 11
# replacement draws: from index 13 (end) via pop()
URA_DORA_START_INDEX = 7


def _build_hand_config(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
    *,
    is_tsumo: bool,
    is_chankan: bool = False,
) -> HandConfig:
    """Build HandConfig with all relevant flags for scoring."""
    haitei_flag = is_tsumo and is_haitei(round_state)
    houtei_flag = not is_tsumo and is_houtei(round_state)
    tenhou_flag = is_tsumo and is_tenhou(player, round_state)
    chiihou_flag = is_tsumo and is_chiihou(player, round_state)
    renhou_flag = (
        not is_tsumo and settings.renhou_value != RenhouValue.NONE and is_renhou(player, round_state)
    )

    return HandConfig(
        is_tsumo=is_tsumo,
        is_riichi=player.is_riichi,
        is_ippatsu=player.is_ippatsu and settings.has_ippatsu,
        is_daburu_riichi=player.is_daburi,
        is_rinshan=player.is_rinshan,
        is_chankan=is_chankan,
        is_haitei=haitei_flag,
        is_houtei=houtei_flag,
        is_tenhou=tenhou_flag,
        is_chiihou=chiihou_flag,
        is_renhou=renhou_flag,
        player_wind=seat_to_wind(player.seat, round_state.dealer_seat),
        round_wind=WINDS_34[round_state.round_wind],
        options=build_optional_rules(settings),
    )


def _collect_dora_indicators(
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    settings: GameSettings,
) -> list[int]:
    """Collect dora and ura dora indicators for scoring."""
    if settings.has_omote_dora:
        dora_indicators = list(round_state.dora_indicators) if round_state.dora_indicators else []
    else:
        dora_indicators = []

    if settings.has_uradora and player.is_riichi and round_state.dead_wall and round_state.dora_indicators:
        # base ura dora: always 1 indicator (the first ura beneath the initial dora)
        # kan ura dora: additional indicators beneath kan-revealed dora (index 1+)
        ura_count = 1 if not settings.has_kan_uradora else len(round_state.dora_indicators)
        for i in range(ura_count):
            ura_index = URA_DORA_START_INDEX + i
            if ura_index < len(round_state.dead_wall):
                dora_indicators.append(round_state.dead_wall[ura_index])

    return dora_indicators


def _evaluate_hand(  # noqa: PLR0913
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    tiles: list[int],
    win_tile: int,
    config: HandConfig,
    dora_indicators: list[int],
) -> HandResult:
    """Run hand calculator and return result with error logging."""
    calculator = HandCalculator()
    melds = frozen_melds_to_melds(player.melds)
    result = calculator.estimate_hand_value(
        tiles=tiles,
        win_tile=win_tile,
        melds=melds,
        dora_indicators=dora_indicators,
        config=config,
    )

    if result.error:
        tile_counts_34 = hand_to_34_array(tiles)
        discard_ids = [discard.tile_id for discard in player.discards]
        logger.error(
            f"hand calculation error: {result.error} "
            f"(seat={player.seat} name={player.name} "
            f"tiles={tiles} tiles_34={tile_counts_34} tiles_count={len(tiles)} "
            f"win_tile={win_tile} melds={_melds_debug(player.melds)} dora_indicators={dora_indicators} "
            f"discards={discard_ids} discards_count={len(discard_ids)} "
            f"round_wind={round_state.round_wind} dealer_seat={round_state.dealer_seat} "
            f"phase={round_state.phase.value} wall_count={len(round_state.wall)} "
            f"pending_dora_count={round_state.pending_dora_count} "
            f"config={_hand_config_debug(config)})"
        )
        return HandResult(error=result.error)

    yaku_list = [str(y) for y in result.yaku] if result.yaku else []
    return HandResult(
        han=result.han or 0,
        fu=result.fu or 0,
        cost_main=result.cost["main"] if result.cost else 0,
        cost_additional=result.cost["additional"] if result.cost else 0,
        yaku=yaku_list,
    )


def calculate_hand_value(  # noqa: PLR0913
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    win_tile: int,
    settings: GameSettings,
    *,
    is_tsumo: bool,
    is_chankan: bool = False,
) -> HandResult:
    """
    Calculate the value of a winning hand using the mahjong library's HandCalculator.

    Builds HandConfig with all relevant flags and OptionalRules for scoring.
    Returns a HandResult with han, fu, cost breakdown, and yaku list.
    """
    config = _build_hand_config(player, round_state, settings, is_tsumo=is_tsumo, is_chankan=is_chankan)
    dora_indicators = _collect_dora_indicators(player, round_state, settings)
    tiles = all_player_tiles(player)
    return _evaluate_hand(player, round_state, tiles, win_tile, config, dora_indicators)


def calculate_hand_value_with_tiles(  # noqa: PLR0913
    player: MahjongPlayer,
    round_state: MahjongRoundState,
    tiles: list[int],
    win_tile: int,
    settings: GameSettings,
    *,
    is_tsumo: bool,
    is_chankan: bool = False,
) -> HandResult:
    """
    Calculate the value of a winning hand using explicit tiles list.

    Accepts tiles directly instead of reading from player.tiles. Use this for
    ron calculations where the win tile needs to be included in the tiles list.

    Args:
        player: The winning player (for flags like riichi, ippatsu, etc.)
        round_state: Current round state (for dora, ura dora, winds)
        tiles: Complete 136-format tile list including closed hand and meld tiles
        win_tile: The winning tile ID
        settings: Game settings for scoring rules
        is_tsumo: Whether this is a tsumo win
        is_chankan: Whether this is a chankan win

    """
    config = _build_hand_config(player, round_state, settings, is_tsumo=is_tsumo, is_chankan=is_chankan)
    dora_indicators = _collect_dora_indicators(player, round_state, settings)
    return _evaluate_hand(player, round_state, tiles, win_tile, config, dora_indicators)


def _apply_score_changes(
    game_state: MahjongGameState,
    score_changes: dict[int, int],
    *,
    clear_riichi: bool = True,
) -> tuple[MahjongRoundState, MahjongGameState]:
    """Apply score changes to round state and optionally clear riichi sticks."""
    new_round_state = game_state.round_state
    for seat, change in score_changes.items():
        player = new_round_state.players[seat]
        new_round_state = update_player(new_round_state, seat, score=player.score + change)

    updates: dict[str, object] = {"round_state": new_round_state}
    if clear_riichi:
        updates["riichi_sticks"] = 0

    new_game_state = game_state.model_copy(update=updates)
    return new_round_state, new_game_state


def _tsumo_payment_for_seat(
    seat: int,
    *,
    is_dealer_win: bool,
    dealer_seat: int,
    hand_result: HandResult,
    honba_bonus_per_loser: int,
) -> int:
    """
    Calculate the tsumo payment amount a given seat owes.
    """
    if is_dealer_win or seat == dealer_seat:
        return hand_result.cost_main + honba_bonus_per_loser
    return hand_result.cost_additional + honba_bonus_per_loser


def apply_tsumo_score(
    game_state: MahjongGameState,
    winner_seat: int,
    hand_result: HandResult,
) -> tuple[MahjongRoundState, MahjongGameState, TsumoResult]:
    """
    Apply score changes for a tsumo win.

    Returns (new_round_state, new_game_state, result).

    Payment structure (normal):
    - If winner is dealer: each non-dealer pays main_cost
    - If winner is non-dealer: dealer pays main_cost, others pay additional_cost
    - Winner also gets: riichi_sticks * 1000 + honba * 300
    - Each loser pays: +honba/3 bonus (300 total = 100 per loser)

    Payment structure (pao / liability):
    - The liable player pays the full tsumo amount alone
    - Other players pay nothing
    """
    round_state = game_state.round_state
    settings = game_state.settings
    winner = round_state.players[winner_seat]
    is_dealer_win = winner_seat == round_state.dealer_seat
    honba_bonus_per_loser = game_state.honba_sticks * settings.honba_tsumo_bonus_per_loser

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    if winner.pao_seat is not None:
        # pao tsumo: liable player pays the full amount
        total_payment = sum(
            _tsumo_payment_for_seat(
                s,
                is_dealer_win=is_dealer_win,
                dealer_seat=round_state.dealer_seat,
                hand_result=hand_result,
                honba_bonus_per_loser=honba_bonus_per_loser,
            )
            for s in range(4)
            if s != winner_seat
        )
        score_changes[winner.pao_seat] = -total_payment
        score_changes[winner_seat] = total_payment
    else:
        # normal tsumo scoring
        total_payment = 0
        for seat in range(4):
            if seat == winner_seat:
                continue
            payment = _tsumo_payment_for_seat(
                seat,
                is_dealer_win=is_dealer_win,
                dealer_seat=round_state.dealer_seat,
                hand_result=hand_result,
                honba_bonus_per_loser=honba_bonus_per_loser,
            )
            score_changes[seat] = -payment
            total_payment += payment
        score_changes[winner_seat] = total_payment

    # winner receives riichi sticks
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value
    score_changes[winner_seat] += riichi_bonus

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        TsumoResult(
            winner_seat=winner_seat,
            hand_result=HandResultInfo(han=hand_result.han, fu=hand_result.fu, yaku=hand_result.yaku),
            score_changes=score_changes,
            riichi_sticks_collected=riichi_bonus // settings.riichi_stick_value,
            pao_seat=winner.pao_seat,
        ),
    )


def apply_ron_score(
    game_state: MahjongGameState,
    winner_seat: int,
    loser_seat: int,
    hand_result: HandResult,
) -> tuple[MahjongRoundState, MahjongGameState, RonResult]:
    """
    Apply score changes for a ron win.

    Returns (new_round_state, new_game_state, result).

    Payment structure (normal):
    - Loser pays: main_cost + honba * 300
    - Winner gets: main_cost + riichi_sticks * 1000 + honba * 300

    Payment structure (pao / liability, pao_seat != loser_seat):
    - Loser and pao player split the payment 50/50
    - Winner receives the full amount

    If pao_seat == loser_seat, normal ron applies (pao player pays full as they would anyway).
    """
    round_state = game_state.round_state
    settings = game_state.settings
    winner = round_state.players[winner_seat]

    # honba bonus from loser
    honba_bonus = game_state.honba_sticks * settings.honba_ron_bonus

    total_payment = hand_result.cost_main + honba_bonus
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    if winner.pao_seat is not None and winner.pao_seat != loser_seat:
        # pao ron with different pao player: split 50/50
        half = total_payment // 2
        score_changes[loser_seat] = -half
        score_changes[winner.pao_seat] -= half
        score_changes[winner_seat] = total_payment
    else:
        # normal ron (including pao_seat == loser_seat case)
        score_changes[loser_seat] = -total_payment
        score_changes[winner_seat] = total_payment

    # winner receives riichi sticks
    score_changes[winner_seat] += riichi_bonus

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        RonResult(
            winner_seat=winner_seat,
            loser_seat=loser_seat,
            hand_result=HandResultInfo(han=hand_result.han, fu=hand_result.fu, yaku=hand_result.yaku),
            score_changes=score_changes,
            riichi_sticks_collected=riichi_bonus // settings.riichi_stick_value,
            pao_seat=winner.pao_seat,
        ),
    )


def apply_double_ron_score(
    game_state: MahjongGameState,
    winners: list[tuple[int, HandResult]],  # list of (seat, hand_result)
    loser_seat: int,
) -> tuple[MahjongRoundState, MahjongGameState, DoubleRonResult]:
    """
    Apply score changes for a double ron.

    Returns (new_round_state, new_game_state, result).

    Payment structure:
    - Loser pays each winner separately: main_cost + honba * 300
    - Riichi sticks go to winner closest to loser's right (counter-clockwise)
    - Each winner's pao is evaluated independently (same logic as single ron)
    """
    round_state = game_state.round_state
    settings = game_state.settings

    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}
    honba_bonus = game_state.honba_sticks * settings.honba_ron_bonus
    riichi_bonus = game_state.riichi_sticks * settings.riichi_stick_value

    # determine who gets riichi sticks: winner closest to loser's right (counter-clockwise)
    winner_seats = [w[0] for w in winners]
    riichi_receiver = None
    for offset in range(1, 4):
        check_seat = (loser_seat + offset) % 4
        if check_seat in winner_seats:
            riichi_receiver = check_seat
            break

    winner_results = []

    for winner_seat, hand_result in winners:
        winner = round_state.players[winner_seat]
        payment = hand_result.cost_main + honba_bonus

        if winner.pao_seat is not None and winner.pao_seat != loser_seat:
            # pao ron with different pao player: split 50/50
            half = payment // 2
            score_changes[loser_seat] -= half
            score_changes[winner.pao_seat] -= half
        else:
            # normal ron (including pao_seat == loser_seat case)
            score_changes[loser_seat] -= payment

        winner_total = payment
        if winner_seat == riichi_receiver:
            winner_total += riichi_bonus

        score_changes[winner_seat] += winner_total

        winner_results.append(
            DoubleRonWinner(
                winner_seat=winner_seat,
                hand_result=HandResultInfo(han=hand_result.han, fu=hand_result.fu, yaku=hand_result.yaku),
                riichi_sticks_collected=(
                    riichi_bonus // settings.riichi_stick_value if winner_seat == riichi_receiver else 0
                ),
                pao_seat=winner.pao_seat,
            )
        )

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes)

    return (
        new_round_state,
        new_game_state,
        DoubleRonResult(
            loser_seat=loser_seat,
            winners=winner_results,
            score_changes=score_changes,
        ),
    )


def apply_nagashi_mangan_score(
    game_state: MahjongGameState,
    qualifying_seats: list[int],
    tempai_seats: list[int],
    noten_seats: list[int],
) -> tuple[MahjongRoundState, MahjongGameState, NagashiManganResult]:
    """
    Apply nagashi mangan scoring.

    Returns (new_round_state, new_game_state, result).

    Each qualifying player receives mangan tsumo payment:
    - Dealer: 4000 from each non-dealer (12000 total)
    - Non-dealer: 4000 from dealer + 2000 from each non-dealer (8000 total)
    """
    round_state = game_state.round_state
    settings = game_state.settings
    score_changes: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0}

    for winner_seat in qualifying_seats:
        is_dealer = winner_seat == round_state.dealer_seat
        for seat in range(4):
            if seat == winner_seat:
                continue
            payment = (
                settings.nagashi_mangan_dealer_payment
                if is_dealer or seat == round_state.dealer_seat
                else settings.nagashi_mangan_non_dealer_payment
            )
            score_changes[seat] -= payment
            score_changes[winner_seat] += payment

    new_round_state, new_game_state = _apply_score_changes(game_state, score_changes, clear_riichi=False)

    return (
        new_round_state,
        new_game_state,
        NagashiManganResult(
            qualifying_seats=qualifying_seats,
            tempai_seats=tempai_seats,
            noten_seats=noten_seats,
            score_changes=score_changes,
        ),
    )
